"""ScoringAgent — computes weighted overall SEO score from all agent results."""

from agents.base_agent import BaseAgent, AgentResult

SCORE_WEIGHTS = {
    "MetaAnalysisAgent":   0.20,
    "LinkAnalysisAgent":   0.15,
    "PerformanceAgent":    0.20,
    "IndexabilityAgent":   0.15,
    "StructuredDataAgent": 0.10,
    "SecurityAgent":       0.20,
}


class ScoringAgent(BaseAgent):
    name = "ScoringAgent"
    dependencies = ["ValidationAgent"]

    async def run(self) -> AgentResult:
        await self._started()
        try:
            wf_log = self.ctx.store.get_workflow_log(self.ctx.audit_id)
            agent_scores: dict[str, int] = {}
            for e in wf_log:
                if e["event_type"] == "completed" and e.get("score", -1) != -1:
                    agent_scores[e["agent_name"]] = e["score"]

            weighted, total_weight = 0.0, 0.0
            weights_used: dict[str, float] = {}
            for agent_name, weight in SCORE_WEIGHTS.items():
                score = agent_scores.get(agent_name)
                if score is not None:
                    weighted      += score * weight
                    total_weight  += weight
                    weights_used[agent_name] = weight

            overall = round(weighted / total_weight) if total_weight > 0 else 0
            self.ctx.store.update_audit(self.ctx.audit_id, overall_score=overall, status="completed")

            await self._completed(score=overall, issues_count=0)
            result = AgentResult(
                agent_name=self.name, success=True, score=overall,
                data={
                    "overall_score": overall,
                    "agent_scores":  agent_scores,
                    "weights_used":  weights_used,
                },
            )
            return self._validate_contract(result)
        except Exception as exc:
            await self._failed(str(exc))
            return AgentResult(agent_name=self.name, success=False, error=str(exc))
