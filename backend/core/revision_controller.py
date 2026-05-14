"""
RevisionController — drives auto-revision when ValidationAgent fails.

Flow
----
1. MasterOrchestratorAgent finishes the initial DAG.
2. It calls controller.needs_revision(validation_result).
3. If True:
   a. controller.identify_targets(checks) → which analysis agents to rerun
   b. controller.clear_stale_data(store, audit_id, targets) → delete old issues/recs
   c. execute_dag([targets + downstream], context, pre_completed={CrawlAgent: …})
   d. controller.increment() and loop back to step 2.
4. Max 2 revision cycles — after that the audit completes regardless.

The controller never modifies agent classes; it only selects which ones to include
in a partial DAG and pre-seeds CrawlAgent as already completed.
"""

import logging
from typing import Any, Type

from agents.base_agent import BaseAgent, AgentResult

_log = logging.getLogger("revision_controller")

# Analysis agents that can be targeted for revision
ANALYSIS_AGENTS = [
    "MetaAnalysisAgent",
    "LinkAnalysisAgent",
    "PerformanceAgent",
    "StructuredDataAgent",
    "SecurityAgent",
    "IndexabilityAgent",
]

# Cross-agent logic rules → the agent most likely responsible
_RULE_TO_AGENT: dict[str, str] = {
    "https_url_vs_no_https_flag": "SecurityAgent",
    "crawled_vs_robots_block":    "IndexabilityAgent",
}


class RevisionController:
    """
    Decides whether and how to revise agents after a ValidationAgent failure.

    Parameters
    ----------
    max_cycles : int
        Maximum number of revision cycles (default 2).
        After this the audit continues regardless of validation status.
    """

    def __init__(self, max_cycles: int = 2) -> None:
        self._max   = max_cycles
        self._cycle = 0

    # ── Decision ──────────────────────────────────────────────────────────────

    def needs_revision(self, validation_result: AgentResult | None) -> bool:
        """Return True if we should run a revision cycle."""
        if validation_result is None or not validation_result.success:
            return False
        if self._cycle >= self._max:
            _log.info("Revision limit (%d) reached — skipping further revision", self._max)
            return False
        status = validation_result.data.get("validation_status", "")
        return status == "failed"

    # ── Target identification ─────────────────────────────────────────────────

    def identify_targets(self, checks: list[dict]) -> list[str]:
        """
        Parse ValidationAgent's check results and return the names of analysis
        agents that should be re-run in the revision cycle.
        """
        targets: set[str] = set()

        for check in checks:
            if check.get("status") not in ("failed", "warning"):
                continue

            name = check.get("name", "")

            if name == "Agent Completeness":
                # Details list contains {"agent": "SomeName", "note": "..."}
                for d in check.get("details", []):
                    if agent := d.get("agent", ""):
                        if agent in ANALYSIS_AGENTS:
                            targets.add(agent)

            elif name == "Score Consistency":
                # Details: {"agent": "MetaAnalysisAgent", "actual_score": 90, ...}
                for d in check.get("details", []):
                    if agent := d.get("agent", ""):
                        if agent in ANALYSIS_AGENTS:
                            targets.add(agent)

            elif name == "Cross-Agent Logic":
                # Details: {"rule": "https_url_vs_no_https_flag", "note": "..."}
                for d in check.get("details", []):
                    if agent := _RULE_TO_AGENT.get(d.get("rule", "")):
                        targets.add(agent)

            elif name == "LLM Sanity Review" and check.get("status") == "warning":
                # Conservative: rerun all analysis agents when LLM flags concerns
                targets.update(ANALYSIS_AGENTS)

        result = list(targets)
        _log.info(
            "Revision cycle %d — targeted agents: %s",
            self._cycle + 1, result or "(none identified, defaulting to all)",
        )
        # Fallback: if nothing targeted but status is "failed", rerun everything
        return result or list(ANALYSIS_AGENTS)

    # ── Data cleanup ──────────────────────────────────────────────────────────

    def clear_stale_data(self, store: Any, audit_id: str, agent_names: list[str]) -> None:
        """
        Delete issues and recommendations written by the targeted agents
        so the revision run starts from a clean slate for those agents.
        """
        for agent_name in agent_names:
            i_count = store.clear_agent_issues(audit_id, agent_name)
            r_count = store.clear_agent_recommendations(audit_id, agent_name)
            _log.debug(
                "Cleared %d issues + %d recs for %s", i_count, r_count, agent_name
            )

    # ── DAG construction ──────────────────────────────────────────────────────

    def build_revision_dag(
        self,
        target_names:   list[str],
        all_agents_map: dict[str, Type[BaseAgent]],
    ) -> tuple[list[Type[BaseAgent]], dict[str, AgentResult]]:
        """
        Build the agent list for the revision DAG and a pre_completed seed so
        DAGExecutor treats CrawlAgent as already done (pages are in context).

        Returns
        -------
        (revision_agent_classes, pre_completed_dict)
        """
        from agents.crawl_agent           import CrawlAgent
        from agents.validation_agent      import ValidationAgent
        from agents.recommendation_agent  import RecommendationAgent
        from agents.scoring_agent         import ScoringAgent
        from agents.report_agent          import ReportAgent

        # Analysis agents to rerun
        analysis_classes = [
            all_agents_map[n] for n in target_names if n in all_agents_map
        ]

        # Always rerun the downstream pipeline after any analysis revision
        downstream = [ValidationAgent, RecommendationAgent, ScoringAgent, ReportAgent]

        revision_classes = analysis_classes + downstream

        # Treat CrawlAgent as pre-completed so its dependents unlock immediately
        pre_completed: dict[str, AgentResult] = {
            CrawlAgent.name: AgentResult(
                agent_name=CrawlAgent.name,
                success=True,
                data={"pages_crawled": 0, "note": "pre-completed from initial run"},
            )
        }

        return revision_classes, pre_completed

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def increment(self) -> None:
        self._cycle += 1

    @property
    def cycle(self) -> int:
        return self._cycle

    @property
    def exhausted(self) -> bool:
        return self._cycle >= self._max
