"""GroqTool — single-turn LLM completion via Groq API."""

import asyncio
from pydantic import BaseModel

from tools.base_tool import BaseTool
from utils.retry import llm_retry


class GroqInput(BaseModel):
    prompt:      str
    system:      str  = "You are a helpful assistant."
    model:       str  = "llama-3.1-8b-instant"
    max_tokens:  int  = 512
    temperature: float = 0.2
    api_key:     str  = ""
    audit_id:    str  = ""   # used for per-audit token accounting


class GroqTool(BaseTool):
    name        = "groq_complete"
    description = (
        "Run a single-turn LLM completion via Groq. "
        "Returns the raw text response. Retries up to 2× on transient errors."
    )
    input_model = GroqInput

    def _get_retry(self):
        return llm_retry(max_attempts=2)

    async def _execute(self, input_data: GroqInput) -> dict:
        from config import settings
        api_key = input_data.api_key or settings.GROQ_API_KEY
        if not api_key:
            raise ValueError("GROQ_API_KEY not configured")

        messages = []
        if input_data.system:
            messages.append({"role": "system", "content": input_data.system})
        messages.append({"role": "user", "content": input_data.prompt})

        _usage: dict = {}

        def _call() -> str:
            from groq import Groq
            resp = Groq(api_key=api_key).chat.completions.create(
                model=input_data.model,
                messages=messages,
                max_tokens=input_data.max_tokens,
                temperature=input_data.temperature,
            )
            if resp.usage:
                _usage["prompt_tokens"]     = resp.usage.prompt_tokens or 0
                _usage["completion_tokens"] = resp.usage.completion_tokens or 0
                _usage["total_tokens"]      = resp.usage.total_tokens or 0
            return resp.choices[0].message.content or ""

        text = await asyncio.to_thread(_call)

        # Record token usage — per-audit if audit_id provided, else global sentinel
        if _usage:
            from utils.metrics import metrics
            target = input_data.audit_id or "__global__"
            metrics.record_tokens(
                target,
                _usage.get("prompt_tokens", 0),
                _usage.get("completion_tokens", 0),
            )

        return {
            "text":              text,
            "model":             input_data.model,
            "prompt_tokens":     _usage.get("prompt_tokens", 0),
            "completion_tokens": _usage.get("completion_tokens", 0),
            "total_tokens":      _usage.get("total_tokens", 0),
        }
