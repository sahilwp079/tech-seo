"""
BaseTool — foundation for all tools in the multi-agent platform.

Every tool:
  - Has a unique name and human-readable description
  - Declares a JSON Schema for its input (for documentation and validation)
  - Implements async _execute(input_data) → dict
  - Gets timing, structured logging, and retry handling for free via invoke()
  - Returns a typed ToolOutput — never bare dicts or exceptions
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError

_log = logging.getLogger("tool")


# ── Contracts ─────────────────────────────────────────────────────────────────

class ToolOutput(BaseModel):
    """Standardised output returned by every tool invocation."""
    tool_name:   str
    success:     bool
    data:        dict  = {}
    error:       str | None = None
    duration_ms: int   = 0
    retries:     int   = 0


# ── Abstract base ─────────────────────────────────────────────────────────────

class BaseTool(ABC):
    name:        ClassVar[str]
    description: ClassVar[str]

    # Subclasses declare their Pydantic input model here
    # e.g.  input_model = FetchPageInput
    input_model: ClassVar[type[BaseModel] | None] = None

    @property
    def input_schema(self) -> dict:
        """JSON Schema for this tool's input — derived from input_model if set."""
        if self.input_model:
            return self.input_model.model_json_schema()
        return {}

    @abstractmethod
    async def _execute(self, input_data: Any) -> dict:
        """
        Core tool logic.
        Receive a validated input object.
        Return a plain dict on success.
        Raise any exception on failure — BaseTool.invoke() handles it.
        """
        ...

    async def invoke(self, raw_input: dict) -> ToolOutput:
        """
        Public entrypoint:
          1. Validate input against input_model (if declared)
          2. Execute _execute() with the retry policy defined by _retry()
          3. Log duration, success/failure
          4. Return a ToolOutput — never raises
        """
        t0      = time.monotonic()
        retries = 0

        # Validate input
        try:
            input_data = self._parse_input(raw_input)
        except (ValidationError, TypeError, ValueError) as exc:
            return ToolOutput(
                tool_name=self.name, success=False,
                error=f"Input validation error: {exc}",
                duration_ms=0,
            )

        # Execute with retry
        try:
            data, retries = await self._invoke_with_retry(input_data)
            ms = int((time.monotonic() - t0) * 1000)
            _log.debug("[tool:%s] OK in %dms (retries=%d)", self.name, ms, retries)
            return ToolOutput(tool_name=self.name, success=True, data=data,
                              duration_ms=ms, retries=retries)
        except Exception as exc:
            ms = int((time.monotonic() - t0) * 1000)
            _log.warning("[tool:%s] FAILED in %dms: %s", self.name, ms, exc)
            return ToolOutput(tool_name=self.name, success=False, error=str(exc),
                              duration_ms=ms, retries=retries)

    async def _invoke_with_retry(self, input_data: Any) -> tuple[dict, int]:
        """
        Execute _execute() using this tool's retry policy.
        Override _get_retry() in subclasses to change the policy.
        Returns (data, retry_count).
        """
        from utils.retry import RetryError
        retry_cfg = self._get_retry()
        attempt = 0

        if retry_cfg is None:
            # No retry — single attempt
            return await self._execute(input_data), 0

        async for a in retry_cfg:
            with a:
                attempt += 1
                data = await self._execute(input_data)
                return data, attempt - 1

        raise RuntimeError("Retry loop exited without result")   # unreachable

    def _get_retry(self):
        """Return a tenacity AsyncRetrying config, or None for no retry."""
        return None

    def _parse_input(self, raw: dict) -> Any:
        if self.input_model:
            return self.input_model.model_validate(raw)
        return raw

    def catalog_entry(self) -> dict:
        """Metadata for tool discovery / documentation."""
        return {
            "name":         self.name,
            "description":  self.description,
            "input_schema": self.input_schema,
        }
