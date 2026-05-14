"""SimilarIssuesTool — semantic search over all past issues in ChromaDB."""

from pydantic import BaseModel

from tools.base_tool import BaseTool


class SimilarIssuesInput(BaseModel):
    query:            str
    n:                int  = 5
    exclude_audit_id: str  = ""


class SimilarIssuesTool(BaseTool):
    name        = "search_similar_issues"
    description = (
        "Semantic similarity search across all past SEO issues stored in ChromaDB. "
        "Useful for identifying patterns, recurring problems, or providing context "
        "before generating recommendations."
    )
    input_model = SimilarIssuesInput

    async def _execute(self, input_data: SimilarIssuesInput) -> dict:
        import storage.chroma_store as store
        results = store.search_similar_issues(
            query=input_data.query,
            n=input_data.n,
            exclude_audit_id=input_data.exclude_audit_id or None,
        )
        return {"query": input_data.query, "results": results, "count": len(results)}
