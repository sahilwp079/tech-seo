"""
WorkerRegistry — maps intent names to ordered agent chains.

Each chain is a WorkerChain dataclass describing:
  - which agent classes to run (in dependency order)
  - a human-readable description
  - estimated runtime
  - default max_pages cap

The registry supports dynamic registration so new intents
can be added at runtime without modifying core code.
"""

import logging
from dataclasses import dataclass, field
from typing import Type

from agents.base_agent import BaseAgent

_log = logging.getLogger("worker_registry")


@dataclass
class WorkerChain:
    intent:             str
    agents:             list[Type[BaseAgent]]
    description:        str
    estimated_minutes:  int   = 3
    default_max_pages:  int   = 50
    tags:               list[str] = field(default_factory=list)


class WorkerRegistry:
    """Registry mapping intent → WorkerChain.  Thread-safe for reads."""

    def __init__(self) -> None:
        self._chains: dict[str, WorkerChain] = {}

    def register(self, chain: WorkerChain) -> None:
        self._chains[chain.intent] = chain
        _log.debug("Registered worker chain: %s (%d agents)", chain.intent, len(chain.agents))

    def get_chain(self, intent: str) -> WorkerChain:
        """Return the chain for an intent, falling back to seo_audit."""
        chain = self._chains.get(intent) or self._chains.get("seo_audit")
        if not chain:
            raise KeyError(f"No worker chain registered for intent '{intent}' and no fallback")
        return chain

    def list_intents(self) -> list[dict]:
        return [
            {
                "intent":            c.intent,
                "description":       c.description,
                "estimated_minutes": c.estimated_minutes,
                "default_max_pages": c.default_max_pages,
                "agent_count":       len(c.agents),
                "agents":            [a.name for a in c.agents],
                "tags":              c.tags,
            }
            for c in self._chains.values()
        ]

    def has_intent(self, intent: str) -> bool:
        return intent in self._chains


# ── Build the default registry ────────────────────────────────────────────────

def _build_default_registry() -> WorkerRegistry:
    # Import lazily to avoid circular imports at module load time
    from agents.crawl_agent           import CrawlAgent
    from agents.meta_analysis_agent   import MetaAnalysisAgent
    from agents.link_analysis_agent   import LinkAnalysisAgent
    from agents.performance_agent     import PerformanceAgent
    from agents.security_agent        import SecurityAgent
    from agents.indexability_agent    import IndexabilityAgent
    from agents.structured_data_agent import StructuredDataAgent
    from agents.validation_agent      import ValidationAgent
    from agents.recommendation_agent  import RecommendationAgent
    from agents.scoring_agent         import ScoringAgent
    from agents.report_agent          import ReportAgent

    reg = WorkerRegistry()

    # ── Full SEO audit (all agents) ───────────────────────────────────────────
    reg.register(WorkerChain(
        intent="seo_audit",
        agents=[
            CrawlAgent,
            MetaAnalysisAgent, LinkAnalysisAgent, PerformanceAgent,
            StructuredDataAgent, SecurityAgent, IndexabilityAgent,
            ValidationAgent,
            RecommendationAgent, ScoringAgent,
            ReportAgent,
        ],
        description="Complete technical SEO audit — crawls up to 50 pages, runs all 11 analysis agents, generates Excel report",
        estimated_minutes=5,
        default_max_pages=50,
        tags=["full", "comprehensive", "report"],
    ))

    # ── Quick single-page check ───────────────────────────────────────────────
    reg.register(WorkerChain(
        intent="quick_seo_check",
        agents=[
            CrawlAgent,
            MetaAnalysisAgent, SecurityAgent,
            ValidationAgent,
            ScoringAgent,
        ],
        description="Fast single-page audit — meta tags and security headers only, no Excel report",
        estimated_minutes=1,
        default_max_pages=1,
        tags=["fast", "single-page"],
    ))

    # ── Technical performance + indexability audit ────────────────────────────
    reg.register(WorkerChain(
        intent="technical_audit",
        agents=[
            CrawlAgent,
            PerformanceAgent, IndexabilityAgent, SecurityAgent,
            ValidationAgent,
            RecommendationAgent, ScoringAgent,
            ReportAgent,
        ],
        description="Technical audit — performance, crawlability, security headers, Core Web Vitals",
        estimated_minutes=3,
        default_max_pages=10,
        tags=["technical", "performance", "speed"],
    ))

    # ── Content + structured data analysis ───────────────────────────────────
    reg.register(WorkerChain(
        intent="content_analysis",
        agents=[
            CrawlAgent,
            MetaAnalysisAgent, StructuredDataAgent,
            ValidationAgent,
            RecommendationAgent, ScoringAgent,
            ReportAgent,
        ],
        description="Content audit — meta tags, headings, Open Graph, JSON-LD structured data",
        estimated_minutes=2,
        default_max_pages=20,
        tags=["content", "meta", "schema"],
    ))

    # ── Link health audit ─────────────────────────────────────────────────────
    reg.register(WorkerChain(
        intent="link_audit",
        agents=[
            CrawlAgent,
            LinkAnalysisAgent,
            ValidationAgent,
            RecommendationAgent, ScoringAgent,
            ReportAgent,
        ],
        description="Link audit — discovers broken links (4xx/5xx), generic anchor text issues",
        estimated_minutes=3,
        default_max_pages=30,
        tags=["links", "broken-links"],
    ))

    # ── Security headers audit ────────────────────────────────────────────────
    reg.register(WorkerChain(
        intent="security_audit",
        agents=[
            CrawlAgent,
            SecurityAgent,
            ValidationAgent,
            RecommendationAgent, ScoringAgent,
        ],
        description="Security audit — HTTPS, HSTS, CSP, X-Frame-Options, Referrer-Policy",
        estimated_minutes=1,
        default_max_pages=5,
        tags=["security", "headers", "https"],
    ))

    return reg


# ── Process-wide singleton ────────────────────────────────────────────────────
worker_registry = _build_default_registry()
