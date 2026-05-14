"""Centralized error manager — tracks per-audit failures across agents and tools."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ErrorRecord:
    audit_id: str
    agent: str
    error: str
    attempt: int
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    recovered: bool = False


class ErrorManager:
    """In-process registry of agent/tool errors keyed by audit_id."""

    def __init__(self) -> None:
        self._errors: dict[str, list[ErrorRecord]] = defaultdict(list)

    def record(
        self,
        audit_id: str,
        agent: str,
        error: str,
        attempt: int = 1,
        recovered: bool = False,
    ) -> None:
        self._errors[audit_id].append(
            ErrorRecord(
                audit_id=audit_id,
                agent=agent,
                error=error,
                attempt=attempt,
                recovered=recovered,
            )
        )

    def mark_recovered(self, audit_id: str, agent: str) -> None:
        for rec in self._errors.get(audit_id, []):
            if rec.agent == agent and not rec.recovered:
                rec.recovered = True

    def get_errors(self, audit_id: str) -> list[ErrorRecord]:
        return list(self._errors.get(audit_id, []))

    def has_unrecovered(self, audit_id: str) -> bool:
        return any(not e.recovered for e in self._errors.get(audit_id, []))

    def summary(self, audit_id: str) -> dict:
        errors = self._errors.get(audit_id, [])
        return {
            "total":       len(errors),
            "recovered":   sum(1 for e in errors if e.recovered),
            "unrecovered": sum(1 for e in errors if not e.recovered),
            "agents":      list({e.agent for e in errors}),
        }

    def clear(self, audit_id: str) -> None:
        self._errors.pop(audit_id, None)


# Process-wide singleton imported by agents and orchestrator
error_manager = ErrorManager()
