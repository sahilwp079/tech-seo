"""
MetricsCollector — lightweight in-process observability store.

Tracks per-audit:
  - Agent timing (start, end, duration_ms, retries, success/fail)
  - Token usage from LLM calls (prompt_tokens, completion_tokens, total_tokens)
  - Tool call stats (calls, failures, total_duration_ms)

All data is stored in-memory.  On large deployments, swap the dicts for Redis.
The singleton ``metrics`` is imported by agents, tools, and the groq tool.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class AgentMetric:
    agent_name:  str
    audit_id:    str
    started_at:  float = field(default_factory=time.monotonic)
    ended_at:    float = 0.0
    duration_ms: int   = 0
    success:     bool  = False
    retries:     int   = 0
    score:       int   = -1
    error:       str   = ""

    def finish(self, *, success: bool, retries: int = 0, score: int = -1, error: str = "") -> None:
        self.ended_at    = time.monotonic()
        self.duration_ms = int((self.ended_at - self.started_at) * 1000)
        self.success     = success
        self.retries     = retries
        self.score       = score
        self.error       = error

    def to_dict(self) -> dict:
        return {
            "agent_name":  self.agent_name,
            "audit_id":    self.audit_id,
            "duration_ms": self.duration_ms,
            "success":     self.success,
            "retries":     self.retries,
            "score":       self.score,
            "error":       self.error,
        }


@dataclass
class TokenUsage:
    prompt_tokens:     int = 0
    completion_tokens: int = 0
    total_tokens:      int = 0
    calls:             int = 0

    def add(self, prompt: int, completion: int) -> None:
        self.prompt_tokens     += prompt
        self.completion_tokens += completion
        self.total_tokens      += prompt + completion
        self.calls             += 1

    def to_dict(self) -> dict:
        return {
            "prompt_tokens":     self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens":      self.total_tokens,
            "calls":             self.calls,
        }


@dataclass
class ToolMetric:
    tool_name:        str
    calls:            int = 0
    failures:         int = 0
    total_duration_ms: int = 0

    def record(self, duration_ms: int, success: bool) -> None:
        self.calls             += 1
        self.total_duration_ms += duration_ms
        if not success:
            self.failures += 1

    @property
    def avg_duration_ms(self) -> float:
        return round(self.total_duration_ms / self.calls, 1) if self.calls else 0.0

    @property
    def error_rate(self) -> float:
        return round(self.failures / self.calls, 3) if self.calls else 0.0

    def to_dict(self) -> dict:
        return {
            "tool_name":         self.tool_name,
            "calls":             self.calls,
            "failures":          self.failures,
            "error_rate":        self.error_rate,
            "avg_duration_ms":   self.avg_duration_ms,
            "total_duration_ms": self.total_duration_ms,
        }


class MetricsCollector:
    """
    Thread-safe in-memory metrics store.

    Usage
    -----
    from utils.metrics import metrics

    # Agent timing
    metrics.agent_started("MetaAnalysisAgent", audit_id)
    metrics.agent_finished("MetaAnalysisAgent", audit_id, success=True, score=85)

    # Token usage
    metrics.record_tokens(audit_id, prompt_tokens=120, completion_tokens=80)

    # Tool call
    metrics.record_tool_call("fetch_page", duration_ms=340, success=True)
    """

    def __init__(self) -> None:
        self._lock = Lock()
        # audit_id → list[AgentMetric]
        self._agent_metrics: dict[str, list[AgentMetric]] = defaultdict(list)
        # audit_id → TokenUsage
        self._token_usage: dict[str, TokenUsage] = defaultdict(TokenUsage)
        # tool_name → ToolMetric
        self._tool_metrics: dict[str, ToolMetric] = {}
        # process-level counters
        self._process_start = time.monotonic()
        self._total_audits  = 0

    # ── Agent timing ──────────────────────────────────────────────────────────

    def agent_started(self, agent_name: str, audit_id: str) -> AgentMetric:
        m = AgentMetric(agent_name=agent_name, audit_id=audit_id)
        with self._lock:
            self._agent_metrics[audit_id].append(m)
        return m

    def agent_finished(
        self,
        agent_name: str,
        audit_id:   str,
        *,
        success:    bool,
        retries:    int  = 0,
        score:      int  = -1,
        error:      str  = "",
    ) -> None:
        with self._lock:
            for m in reversed(self._agent_metrics[audit_id]):
                if m.agent_name == agent_name and m.ended_at == 0.0:
                    m.finish(success=success, retries=retries, score=score, error=error)
                    break

    def audit_started(self, audit_id: str) -> None:
        with self._lock:
            self._total_audits += 1
            if audit_id not in self._agent_metrics:
                self._agent_metrics[audit_id] = []

    # ── Token tracking ────────────────────────────────────────────────────────

    def record_tokens(
        self,
        audit_id:          str,
        prompt_tokens:     int,
        completion_tokens: int,
    ) -> None:
        with self._lock:
            self._token_usage[audit_id].add(prompt_tokens, completion_tokens)

    # ── Tool tracking ─────────────────────────────────────────────────────────

    def record_tool_call(self, tool_name: str, duration_ms: int, success: bool) -> None:
        with self._lock:
            if tool_name not in self._tool_metrics:
                self._tool_metrics[tool_name] = ToolMetric(tool_name=tool_name)
            self._tool_metrics[tool_name].record(duration_ms, success)

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_audit_metrics(self, audit_id: str) -> dict[str, Any]:
        with self._lock:
            agents = [m.to_dict() for m in self._agent_metrics.get(audit_id, [])]
            tokens = self._token_usage[audit_id].to_dict()
        return {
            "audit_id": audit_id,
            "agents":   agents,
            "tokens":   tokens,
            "summary": {
                "total_agents":   len(agents),
                "successful":     sum(1 for a in agents if a["success"]),
                "failed":         sum(1 for a in agents if not a["success"]),
                "total_duration_ms": sum(a["duration_ms"] for a in agents),
                "total_retries":  sum(a["retries"] for a in agents),
                "total_tokens":   tokens["total_tokens"],
            },
        }

    def get_tool_stats(self) -> list[dict]:
        with self._lock:
            return [m.to_dict() for m in self._tool_metrics.values()]

    def get_process_summary(self) -> dict[str, Any]:
        uptime_s = int(time.monotonic() - self._process_start)
        with self._lock:
            total_llm_calls  = sum(u.calls for u in self._token_usage.values())
            total_tokens     = sum(u.total_tokens for u in self._token_usage.values())
            total_tool_calls = sum(m.calls for m in self._tool_metrics.values())
            total_audits     = self._total_audits
        return {
            "uptime_seconds":  uptime_s,
            "total_audits":    total_audits,
            "total_llm_calls": total_llm_calls,
            "total_tokens":    total_tokens,
            "total_tool_calls": total_tool_calls,
        }

    def list_audit_ids(self) -> list[str]:
        with self._lock:
            return list(self._agent_metrics.keys())


# Process-level singleton
metrics = MetricsCollector()
