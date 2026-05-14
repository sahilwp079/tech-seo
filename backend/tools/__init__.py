"""
tools/ — Tool Registry bootstrap.

Import `tool_registry` from this module to get the process-wide
pre-populated registry.  New tools can be added at runtime via
`tool_registry.register(MyTool())`.
"""

from tools.tool_registry         import ToolRegistry
from tools.fetch_page_tool       import FetchPageTool
from tools.check_url_tool        import CheckUrlTool
from tools.groq_tool             import GroqTool
from tools.knowledge_search_tool import KnowledgeSearchTool
from tools.similar_issues_tool   import SimilarIssuesTool

# ── Process-wide singleton ────────────────────────────────────────────────────
tool_registry = ToolRegistry()
tool_registry.register_many(
    FetchPageTool(),
    CheckUrlTool(),
    GroqTool(),
    KnowledgeSearchTool(),
    SimilarIssuesTool(),
)

__all__ = [
    "tool_registry",
    "ToolRegistry",
    "FetchPageTool",
    "CheckUrlTool",
    "GroqTool",
    "KnowledgeSearchTool",
    "SimilarIssuesTool",
]
