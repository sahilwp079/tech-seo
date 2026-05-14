"""
MasterOrchestratorAgent — top-level controller for the full audit pipeline.

Flow
----
1. Creates audit record in ChromaDB
2. Runs PlannerAgent to build execution DAG
3. Hands agent classes to DAGExecutor for Phase 1 (full run)
4. Checks ValidationAgent result
5. If validation failed → RevisionController identifies targets and reruns
6. Repeats up to max_revision_cycles (default 2)
7. Returns final audit result
"""

import asyncio
import logging
from datetime import datetime
from typing import Type

from agents.base_agent import BaseAgent, AgentContext, AgentResult
from agents.planner_agent import PlannerAgent, ALL_AGENT_CLASSES
from core.dag_executor import execute_dag
from core.event_bus import EventBus
from core.revision_controller import RevisionController
import storage.chroma_store as store

_log = logging.getLogger("master_orchestrator")


class MasterOrchestratorAgent(BaseAgent):
    name = "MasterOrchestratorAgent"
    dependencies: list[str] = []

    async def run(self) -> AgentResult:
        await self._started()
        try:
            store.update_audit(
                self.ctx.audit_id,
                status="running",
                started_at=datetime.utcnow().isoformat(),
                current_agent="PlannerAgent",
            )

            # ── Phase 0: Planning ─────────────────────────────────────────────
            planner      = PlannerAgent(self.ctx)
            plan_result  = await planner.run()
            agent_classes: list[Type[BaseAgent]] = plan_result.data.get(
                "agent_classes", ALL_AGENT_CLASSES
            )
            all_agents_map = {cls.name: cls for cls in agent_classes}

            # ── Phase 1–5: Initial full DAG run ───────────────────────────────
            store.update_audit(self.ctx.audit_id, current_agent="CrawlAgent")
            results = await execute_dag(agent_classes, self.ctx)

            # ── Phase 6: Auto-revision loop ───────────────────────────────────
            revision = RevisionController(max_cycles=2)
            validation_result = results.get("ValidationAgent")

            while revision.needs_revision(validation_result):
                revision.increment()
                checks = (validation_result.data or {}).get("checks", [])

                await self._emit("revision.started", {
                    "cycle":       revision.cycle,
                    "reason":      "ValidationAgent status = failed",
                    "checks_failed": [c["name"] for c in checks if c.get("status") == "failed"],
                })
                _log.warning(
                    "[%s] Starting revision cycle %d",
                    self.ctx.audit_id, revision.cycle,
                )

                # Identify which analysis agents to rerun
                target_names = revision.identify_targets(checks)

                # Clear stale issues/recs for those agents
                revision.clear_stale_data(store, self.ctx.audit_id, target_names)

                # Build partial DAG + pre-completed seed (CrawlAgent already done)
                revision_classes, pre_completed = revision.build_revision_dag(
                    target_names, all_agents_map
                )

                store.update_audit(
                    self.ctx.audit_id,
                    current_agent=f"Revision {revision.cycle}: {', '.join(target_names)}",
                )

                # Run the revision DAG
                revision_results = await execute_dag(
                    revision_classes, self.ctx, pre_completed=pre_completed
                )
                results.update(revision_results)
                validation_result = revision_results.get("ValidationAgent", validation_result)

                new_status = (validation_result.data or {}).get("validation_status", "unknown")
                await self._emit("revision.completed", {
                    "cycle":              revision.cycle,
                    "validation_status":  new_status,
                    "agents_revised":     target_names,
                    "further_revision":   revision.needs_revision(validation_result),
                })
                _log.info(
                    "[%s] Revision %d done — validation_status=%s",
                    self.ctx.audit_id, revision.cycle, new_status,
                )

            # ── Collect final results ─────────────────────────────────────────
            scoring_result = results.get("ScoringAgent")
            overall        = scoring_result.score if scoring_result else None
            failed_agents  = [n for n, r in results.items() if not r.success]

            # Log revision summary to workflow memory
            if revision.cycle > 0:
                store.log_workflow(
                    self.ctx.audit_id, self.name, "revision_summary",
                    {
                        "status":           "completed",
                        "revision_cycles":  revision.cycle,
                        "score":            overall if overall is not None else -1,
                        "issues_count":     0,
                    },
                )

            await self._completed(score=overall, issues_count=0)
            return AgentResult(
                agent_name=self.name,
                success=True,
                score=overall,
                data={
                    "audit_id":        self.ctx.audit_id,
                    "overall_score":   overall,
                    "pages_crawled":   len(self.ctx.pages),
                    "failed_agents":   failed_agents,
                    "revision_cycles": revision.cycle,
                },
            )

        except Exception as exc:
            store.update_audit(
                self.ctx.audit_id,
                status="failed",
                error_message=str(exc),
                completed_at=datetime.utcnow().isoformat(),
            )
            await self._failed(str(exc))
            return AgentResult(agent_name=self.name, success=False, error=str(exc))


async def run_audit(audit_id: str, base_url: str, max_pages: int, event_bus: EventBus) -> dict:
    """Entry point called by the API route background task."""
    ctx = AgentContext(
        audit_id=audit_id,
        base_url=base_url,
        max_pages=max_pages,
        event_bus=event_bus,
        store=store,
        groq_api_key=__import__("config").settings.GROQ_API_KEY,
    )
    orchestrator = MasterOrchestratorAgent(ctx)
    result = await orchestrator.run()
    return result.data
