"""
Per-agent typed output contracts.

Each agent must produce data that validates against its contract.
The ContractValidator enforces this at runtime and logs violations.

Never allow prose-only or untyped dict outputs between agents.
"""

from pydantic import BaseModel, Field
from contracts.base_contracts import (
    AgentOutputBase,
    IssueContract,
    RecommendationContract,
    ValidationCheckContract,
    CrawledPageContract,
)


# ── PlannerAgent ──────────────────────────────────────────────────────────────

class PlanNode(BaseModel):
    agent:        str
    dependencies: list[str]
    status:       str = "pending"


class PlannerContract(AgentOutputBase):
    plan:         list[PlanNode]
    total_agents: int


# ── CrawlAgent ────────────────────────────────────────────────────────────────

class CrawlContract(AgentOutputBase):
    pages_crawled:     int
    urls_discovered:   list[str] = Field(default_factory=list)
    failed_urls:       list[str] = Field(default_factory=list)
    max_depth_reached: int       = 0


# ── Analysis agents (shared shape) ───────────────────────────────────────────
# MetaAnalysisAgent, LinkAnalysisAgent, PerformanceAgent,
# SecurityAgent, IndexabilityAgent, StructuredDataAgent

class AnalysisAgentContract(AgentOutputBase):
    issues:         list[IssueContract] = Field(default_factory=list)
    pages_analyzed: int = 0


# ── ValidationAgent ───────────────────────────────────────────────────────────

class ValidationContract(AgentOutputBase):
    validation_status: str   # "passed" | "warnings" | "failed"
    confidence:        int   # 0–100
    checks:            list[ValidationCheckContract] = Field(default_factory=list)


# ── RecommendationAgent ───────────────────────────────────────────────────────

class RecommendationAgentContract(AgentOutputBase):
    total_recommendations: int
    pages_affected:        int
    recommendations:       list[RecommendationContract] = Field(default_factory=list)
    ai_summaries:          dict[str, str] = Field(default_factory=dict)  # page_url → plan


# ── ScoringAgent ──────────────────────────────────────────────────────────────

class ScoringContract(AgentOutputBase):
    overall_score: int
    agent_scores:  dict[str, int]   = Field(default_factory=dict)
    weights_used:  dict[str, float] = Field(default_factory=dict)


# ── ReportAgent ───────────────────────────────────────────────────────────────

class ReportContract(AgentOutputBase):
    excel_path:  str = ""
    ai_summary:  str = ""


# ── Registry: agent name → contract class ─────────────────────────────────────

AGENT_CONTRACT_MAP: dict[str, type[AgentOutputBase]] = {
    "PlannerAgent":        PlannerContract,
    "CrawlAgent":          CrawlContract,
    "MetaAnalysisAgent":   AnalysisAgentContract,
    "LinkAnalysisAgent":   AnalysisAgentContract,
    "PerformanceAgent":    AnalysisAgentContract,
    "SecurityAgent":       AnalysisAgentContract,
    "IndexabilityAgent":   AnalysisAgentContract,
    "StructuredDataAgent": AnalysisAgentContract,
    "ValidationAgent":     ValidationContract,
    "RecommendationAgent": RecommendationAgentContract,
    "ScoringAgent":        ScoringContract,
    "ReportAgent":         ReportContract,
}
