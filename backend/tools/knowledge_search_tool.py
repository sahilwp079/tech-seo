"""KnowledgeSearchTool — semantic search over the seo_knowledge ChromaDB collection."""

from pydantic import BaseModel

from tools.base_tool import BaseTool


class KnowledgeSearchInput(BaseModel):
    query: str
    n:     int = 3


class KnowledgeSearchTool(BaseTool):
    name        = "search_knowledge"
    description = (
        "Semantic similarity search over the built-in SEO knowledge base. "
        "Returns the top-N most relevant articles for grounding LLM prompts (RAG)."
    )
    input_model = KnowledgeSearchInput

    async def _execute(self, input_data: KnowledgeSearchInput) -> dict:
        import storage.chroma_store as store
        articles = store.get_knowledge(input_data.query, n=input_data.n)
        return {"query": input_data.query, "articles": articles, "count": len(articles)}
