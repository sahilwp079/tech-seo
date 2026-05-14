"""
Shared base contracts used across all agents.

These are the atomic data types that flow between agents.
Every agent input/output must be expressible in terms of these types.
"""

from typing import Literal
from pydantic import BaseModel, Field, field_validator


# ── Severity / priority literals ──────────────────────────────────────────────

Severity = Literal["critical", "warning", "info"]
Priority = Literal["high", "medium", "low"]
AgentStatus = Literal["passed", "warnings", "failed", "skipped"]


# ── Atomic shared types ───────────────────────────────────────────────────────

class IssueContract(BaseModel):
    """A single SEO issue found by an analysis agent."""
    issue_type:    str
    severity:      Severity
    title:         str
    description:   str
    page_url:      str = ""
    section:       str = ""
    element:       str = ""
    current_value: str = ""
    fix:           str = ""
    before:        str = ""
    after:         str = ""

    @field_validator("severity")
    @classmethod
    def valid_severity(cls, v: str) -> str:
        allowed = {"critical", "warning", "info"}
        if v not in allowed:
            raise ValueError(f"severity must be one of {allowed}, got '{v}'")
        return v


class RecommendationContract(BaseModel):
    """A single actionable recommendation linked to an issue."""
    issue_type: str
    page_url:   str = ""
    priority:   Priority
    action:     str
    section:    str = ""
    element:    str = ""
    before:     str = ""
    after:      str = ""
    agent_name: str = ""


class ValidationCheckContract(BaseModel):
    """One individual check performed by ValidationAgent."""
    name:    str
    status:  AgentStatus
    message: str
    details: list[dict] = Field(default_factory=list)


class CrawledPageContract(BaseModel):
    """Metadata for a single crawled page."""
    url:               str
    status_code:       int | None = None
    content_type:      str = ""
    page_size_bytes:   int = 0
    crawl_duration_ms: int = 0
    depth:             int = 0
    has_html:          bool = False
    error:             str = ""


# ── Base output contract ──────────────────────────────────────────────────────

class AgentOutputBase(BaseModel):
    """
    Common envelope for every agent's typed output.
    Extend this in agent_contracts.py for each specific agent.
    """
    model_config = {"arbitrary_types_allowed": True}

    agent_name:   str
    success:      bool
    score:        int | None = None
    issues_count: int        = 0
    duration_ms:  int        = 0
    retries:      int        = 0
    error:        str | None = None
