"""
ContractValidator — validates agent data payloads against their Pydantic contracts.

Usage inside an agent:
    from contracts.validator import contract_validator
    validated = contract_validator.enforce("ScoringAgent", data_dict)
    # validated is a typed ScoringContract or None if validation fails

Usage for audit-wide reporting:
    report = contract_validator.audit_report(results_dict)
"""

import logging
from typing import Any

from pydantic import ValidationError

from contracts.agent_contracts import AGENT_CONTRACT_MAP, AgentOutputBase

_log = logging.getLogger("contract_validator")


class ContractValidator:
    """
    Validates agent output dicts against their registered Pydantic contracts.

    All validation is non-blocking:
    - `validate()` returns (is_valid, errors) without raising
    - `enforce()` returns the typed model or None on failure (logs the violation)
    - `audit_report()` summarises compliance across all agents in a completed run
    """

    def validate(self, agent_name: str, data: dict) -> tuple[bool, list[str]]:
        """
        Check data against the registered contract for agent_name.
        Returns (True, []) on success or (False, [error_messages]) on failure.
        Returns (True, []) with a warning log if no contract is registered.
        """
        contract_cls = AGENT_CONTRACT_MAP.get(agent_name)
        if not contract_cls:
            _log.debug("[contract] No contract registered for '%s' — skipping", agent_name)
            return True, []

        try:
            contract_cls.model_validate(data)
            return True, []
        except ValidationError as exc:
            errors = [f"{e['loc']}: {e['msg']}" for e in exc.errors()]
            _log.warning(
                "[contract] %s VIOLATION — %d error(s): %s",
                agent_name, len(errors), "; ".join(errors),
            )
            return False, errors

    def enforce(self, agent_name: str, data: dict) -> AgentOutputBase | None:
        """
        Validate and return the typed contract model.
        Returns None (with a logged warning) if validation fails.
        """
        contract_cls = AGENT_CONTRACT_MAP.get(agent_name)
        if not contract_cls:
            return None

        try:
            model = contract_cls.model_validate(data)
            _log.debug("[contract] %s — validated OK", agent_name)
            return model
        except ValidationError as exc:
            errors = [f"{e['loc']}: {e['msg']}" for e in exc.errors()]
            _log.warning(
                "[contract] %s — enforcement failed (%d errors): %s",
                agent_name, len(errors), "; ".join(errors),
            )
            return None

    def audit_report(self, results: dict[str, Any]) -> dict:
        """
        Given a dict of {agent_name: AgentResult}, validate every agent's .data
        against its contract and return a compliance summary.

        results: dict[str, AgentResult]  (from DAGExecutor output)
        """
        report: list[dict] = []
        violations = 0

        for agent_name, result in results.items():
            data = result.data if hasattr(result, "data") else {}
            data_with_meta = {
                "agent_name":   agent_name,
                "success":      getattr(result, "success", False),
                "score":        getattr(result, "score", None),
                "issues_count": getattr(result, "issues_count", 0),
                "duration_ms":  getattr(result, "duration_ms", 0),
                "error":        getattr(result, "error", None),
                **data,
            }
            is_valid, errors = self.validate(agent_name, data_with_meta)
            if not is_valid:
                violations += 1
            report.append({
                "agent":   agent_name,
                "valid":   is_valid,
                "errors":  errors,
            })

        return {
            "total_agents": len(results),
            "compliant":    len(results) - violations,
            "violations":   violations,
            "compliance_pct": round((len(results) - violations) / len(results) * 100)
                              if results else 100,
            "details":      report,
        }

    def schema_for(self, agent_name: str) -> dict:
        """Return the JSON Schema for an agent's output contract."""
        contract_cls = AGENT_CONTRACT_MAP.get(agent_name)
        if not contract_cls:
            return {}
        return contract_cls.model_json_schema()

    def registered_agents(self) -> list[str]:
        return list(AGENT_CONTRACT_MAP.keys())


# Process-wide singleton
contract_validator = ContractValidator()
