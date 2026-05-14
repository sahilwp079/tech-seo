"""
ToolRegistry — central catalog for all tools in the platform.

Features
--------
- Dynamic registration at startup or runtime
- Typed invocation with input validation
- Per-tool call logging with duration and retry count
- Tool introspection (list, schema, describe)
- Idempotent registration (re-registering same tool is a no-op)
"""

import logging
from typing import Any

from tools.base_tool import BaseTool, ToolOutput

_log = logging.getLogger("tool_registry")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._call_counts: dict[str, int]  = {}
        self._fail_counts: dict[str, int]  = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance.  Re-registering the same name is a no-op."""
        if tool.name in self._tools:
            return
        self._tools[tool.name]      = tool
        self._call_counts[tool.name] = 0
        self._fail_counts[tool.name] = 0
        _log.debug("Registered tool: %s", tool.name)

    def register_many(self, *tools: BaseTool) -> None:
        for t in tools:
            self.register(t)

    # ── Invocation ────────────────────────────────────────────────────────────

    async def invoke(self, name: str, input_data: dict | None = None) -> ToolOutput:
        """
        Look up the tool by name, validate input, execute, log metrics.
        Always returns a ToolOutput — never raises.
        """
        tool = self._tools.get(name)
        if not tool:
            return ToolOutput(
                tool_name=name, success=False,
                error=f"Tool '{name}' not registered. Available: {self.names()}",
            )

        self._call_counts[name] += 1
        _log.info("[registry] invoking tool '%s'", name)

        result = await tool.invoke(input_data or {})

        if not result.success:
            self._fail_counts[name] += 1

        # Forward timing to the process-level metrics collector
        try:
            from utils.metrics import metrics
            metrics.record_tool_call(name, result.duration_ms, result.success)
        except Exception:
            pass

        return result

    # ── Introspection ─────────────────────────────────────────────────────────

    def get_tool(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def list_tools(self) -> list[dict]:
        """Return catalog entries for all registered tools."""
        return [t.catalog_entry() for t in self._tools.values()]

    def stats(self) -> list[dict]:
        """Return per-tool call/fail counts for observability."""
        return [
            {
                "name":       name,
                "calls":      self._call_counts.get(name, 0),
                "failures":   self._fail_counts.get(name, 0),
                "error_rate": (
                    round(self._fail_counts.get(name, 0) / self._call_counts[name], 3)
                    if self._call_counts.get(name, 0) > 0 else 0.0
                ),
            }
            for name in self._tools
        ]

    def __contains__(self, name: str) -> bool:
        return name in self._tools
