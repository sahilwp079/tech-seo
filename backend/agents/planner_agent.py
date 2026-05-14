"""
PlannerAgent — builds and describes the execution DAG before audit starts.

Responsibilities:
  - Registers all agent classes in execution order
  - Resolves dependency graph
  - Returns the execution plan as a structured dict (used by frontend graph visualisation)
  - Passes agent classes to DAGExecutor for actual execution
"""

from agents.base_agent import BaseAgent, AgentContext, AgentResult

# Import all agent classes in one place
from agents.crawl_agent           import CrawlAgent
from agents.indexability_agent    import IndexabilityAgent
from agents.meta_analysis_agent   import MetaAnalysisAgent
from agents.link_analysis_agent   import LinkAnalysisAgent
from agents.performance_agent     import PerformanceAgent
from agents.structured_data_agent import StructuredDataAgent
from agents.security_agent        import SecurityAgent
from agents.validation_agent      import ValidationAgent
from agents.recommendation_agent  import RecommendationAgent
from agents.scoring_agent         import ScoringAgent
from agents.report_agent          import ReportAgent

# Ordered list — DAGExecutor handles parallelism from dependencies
ALL_AGENT_CLASSES = [
    CrawlAgent,
    IndexabilityAgent,
    MetaAnalysisAgent,
    LinkAnalysisAgent,
    PerformanceAgent,
    StructuredDataAgent,
    SecurityAgent,
    ValidationAgent,
    RecommendationAgent,
    ScoringAgent,
    ReportAgent,
]


class PlannerAgent(BaseAgent):
    name = "PlannerAgent"
    dependencies: list[str] = []

    async def run(self) -> AgentResult:
        await self._started()

        plan = []
        for cls in ALL_AGENT_CLASSES:
            plan.append({
                "agent":        cls.name,
                "dependencies": cls.dependencies,
                "status":       "pending",
            })

        # Store plan in workflow_memory
        for node in plan:
            self.ctx.store.log_workflow(
                self.ctx.audit_id, node["agent"], "planned",
                {"status": "pending"},
            )

        await self._emit("plan.ready", {"plan": plan, "total_agents": len(plan)})
        await self._completed(score=None, issues_count=0)
        result = AgentResult(
            agent_name=self.name,
            success=True,
            data={
                "plan":          plan,
                "total_agents":  len(plan),
                "agent_classes": ALL_AGENT_CLASSES,
            },
        )
        return self._validate_contract(result)
