"""
BaseAgent — foundation for all agents in the multi-agent platform.

Every agent:
  - Receives an AgentContext at construction time
  - Implements async run() → AgentResult
  - Declares its name and dependencies for DAG scheduling
  - Emits structured events via EventBus → WebSocket
  - Tracks execution time automatically
  - Logs failures to the centralized ErrorManager
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AgentContext:
    """Shared state passed to every agent during an audit run."""
    audit_id:     str
    base_url:     str
    max_pages:    int
    event_bus:    object           # core.event_bus.EventBus
    store:        object           # storage.chroma_store module reference
    pages:        list[dict] = field(default_factory=list)   # populated by CrawlAgent
    groq_api_key: str = ""


@dataclass
class AgentResult:
    agent_name:   str
    success:      bool
    score:        int | None = None
    issues_count: int = 0
    data:         dict = field(default_factory=dict)
    error:        str | None = None
    duration_ms:  int = 0          # wall-clock time for this agent's run()
    retries:      int = 0          # number of retry attempts made
    contract:     object = None    # validated Pydantic contract model (optional)


class BaseAgent(ABC):
    name:        str       = "BaseAgent"
    dependencies: list[str] = []
    max_retries:  int       = 3    # used by DAGExecutor for unhandled-exception retry

    def __init__(self, context: AgentContext) -> None:
        self.ctx = context
        self._start_time: float = 0.0

    @abstractmethod
    async def run(self) -> AgentResult:
        ...

    # ── internal helpers ─────────────────────────────────────────────────────

    def _elapsed_ms(self) -> int:
        return int((time.monotonic() - self._start_time) * 1000) if self._start_time else 0

    async def _emit(self, event_type: str, data: dict = {}) -> None:
        from core.event_bus import AgentEvent
        await self.ctx.event_bus.publish(
            AgentEvent(
                audit_id=self.ctx.audit_id,
                agent_name=self.name,
                event_type=event_type,
                data=data,
            )
        )

    # ── lifecycle events ──────────────────────────────────────────────────────

    async def _started(self) -> None:
        self._start_time = time.monotonic()
        try:
            from utils.metrics import metrics
            metrics.agent_started(self.name, self.ctx.audit_id)
        except Exception:
            pass
        await self._emit("agent.started", {"status": "running"})
        self.ctx.store.log_workflow(
            self.ctx.audit_id, self.name, "started", {"status": "running"}
        )

    async def _completed(self, score: int | None, issues_count: int) -> None:
        duration = self._elapsed_ms()
        try:
            from utils.metrics import metrics
            metrics.agent_finished(
                self.name, self.ctx.audit_id,
                success=True, score=score if score is not None else -1,
            )
        except Exception:
            pass
        await self._emit("agent.completed", {
            "status":       "completed",
            "score":        score,
            "issues_count": issues_count,
            "duration_ms":  duration,
        })
        self.ctx.store.log_workflow(
            self.ctx.audit_id, self.name, "completed", {
                "status":       "completed",
                "score":        score if score is not None else -1,
                "issues_count": issues_count,
                "duration_ms":  duration,
            }
        )

    async def _failed(self, error: str) -> None:
        from utils.error_manager import error_manager
        error_manager.record(
            audit_id=self.ctx.audit_id,
            agent=self.name,
            error=error,
            attempt=1,
        )
        try:
            from utils.metrics import metrics
            metrics.agent_finished(
                self.name, self.ctx.audit_id,
                success=False, error=error,
            )
        except Exception:
            pass
        await self._emit("agent.failed", {
            "status":      "failed",
            "error":       error,
            "duration_ms": self._elapsed_ms(),
        })
        self.ctx.store.log_workflow(
            self.ctx.audit_id, self.name, "failed", {"status": "failed"}
        )

    def _validate_contract(self, result: "AgentResult") -> "AgentResult":
        """
        Validate result.data against this agent's registered Pydantic contract.
        Attaches the typed model to result.contract if valid.
        Logs a warning on violation but never blocks execution.
        """
        from contracts.validator import contract_validator
        payload = {
            "agent_name":   self.name,
            "success":      result.success,
            "score":        result.score,
            "issues_count": result.issues_count,
            "duration_ms":  result.duration_ms,
            "error":        result.error,
            **result.data,
        }
        typed = contract_validator.enforce(self.name, payload)
        result.contract = typed
        return result

    async def _retry_triggered(self, attempt: int, max_attempts: int, error: str = "") -> None:
        from utils.error_manager import error_manager
        error_manager.record(
            audit_id=self.ctx.audit_id,
            agent=self.name,
            error=error or f"attempt {attempt} failed",
            attempt=attempt,
            recovered=False,
        )
        await self._emit("retry_triggered", {
            "attempt":      attempt,
            "max_attempts": max_attempts,
            "error":        error,
        })
