"""
ChromaDB primary storage layer — replaces MySQL entirely.

Collections
-----------
audits           one document per audit run
pages            one document per crawled page
issues           one document per SEO issue found
recommendations  one document per recommended fix
workflow_memory  one document per agent lifecycle event
seo_knowledge    built-in SEO best-practice articles (seeded once)
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

from config import settings

# ── singleton ─────────────────────────────────────────────────────────────────
_client = None
_collections: dict[str, Any] = {}

COLLECTION_NAMES = ["audits", "pages", "issues", "recommendations", "workflow_memory", "seo_knowledge"]

SEO_KNOWLEDGE = [
    {"id": "kb_title",     "topic": "meta_title",      "title": "Optimising Page Titles",        "content": "The HTML <title> tag is one of the most important on-page SEO elements. Keep titles between 50–60 characters. Include the primary keyword near the start. Each page should have a unique title."},
    {"id": "kb_desc",      "topic": "meta_description", "title": "Writing Meta Descriptions",     "content": "Meta descriptions do not directly affect rankings but significantly impact click-through rate. Write 120–160 characters. Include a clear call-to-action. Use the target keyword naturally."},
    {"id": "kb_h1",        "topic": "headings",         "title": "H1 Best Practices",             "content": "Use exactly one H1 per page that summarises the page's main topic. H2–H6 should create a logical hierarchy. Include target keywords in headings naturally."},
    {"id": "kb_canonical", "topic": "canonical",        "title": "Canonical Tags",                "content": "The rel=canonical tag tells search engines which URL is the master version of a page. Use it on paginated pages, URL parameter variants, and syndicated content."},
    {"id": "kb_cwv",       "topic": "performance",      "title": "Core Web Vitals",               "content": "Target LCP < 2.5s, INP < 200ms, CLS < 0.1. Improve TTFB with caching and CDN. Reduce render-blocking resources by deferring JS and inlining critical CSS."},
    {"id": "kb_mobile",    "topic": "mobile",           "title": "Mobile-First Indexing",         "content": "Google uses the mobile version of a page for indexing. Always include <meta name='viewport'>. Use responsive CSS. Ensure tap targets are at least 48×48 px."},
    {"id": "kb_robots",    "topic": "indexability",     "title": "robots.txt and Crawl Budget",   "content": "robots.txt controls which pages search engines can crawl. Blocking important pages prevents them from being indexed. Always include a Sitemap directive."},
    {"id": "kb_sitemap",   "topic": "sitemap",          "title": "XML Sitemaps",                  "content": "Sitemaps help search engines discover all pages. Include only canonical, indexable URLs. Keep sitemaps under 50,000 URLs. Submit via Google Search Console."},
    {"id": "kb_schema",    "topic": "structured_data",  "title": "Structured Data & Schema",      "content": "JSON-LD schema.org markup helps search engines understand content and enables rich results. Validate with Google's Rich Results Test. Invalid JSON blocks all structured data."},
    {"id": "kb_https",     "topic": "security",         "title": "HTTPS & Security Headers",      "content": "HTTPS is a confirmed Google ranking signal. Add HSTS to prevent protocol downgrade attacks. X-Frame-Options prevents clickjacking. CSP reduces XSS attack surface."},
    {"id": "kb_links",     "topic": "links",            "title": "Broken Link Management",        "content": "Broken internal links harm user experience and waste crawl budget. Fix broken links with 301 redirects. Use descriptive anchor text. Maintain flat site architecture."},
    {"id": "kb_og",        "topic": "open_graph",       "title": "Open Graph & Social Sharing",   "content": "Open Graph tags control how pages appear when shared on social media. Required: og:title, og:description, og:image, og:url. og:image should be at least 1200×630 px."},
]


def _get_client():
    global _client, _collections
    if _client is not None:
        return _client, _collections
    Path(settings.CHROMA_DB_PATH).mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
    ef = ONNXMiniLM_L6_V2()
    for name in COLLECTION_NAMES:
        _collections[name] = _client.get_or_create_collection(name=name, embedding_function=ef)
    _seed_knowledge(_collections["seo_knowledge"])
    return _client, _collections


def _seed_knowledge(col) -> None:
    existing_ids = set(col.get(ids=[a["id"] for a in SEO_KNOWLEDGE])["ids"])
    new = [a for a in SEO_KNOWLEDGE if a["id"] not in existing_ids]
    if new:
        col.add(
            ids=[a["id"] for a in new],
            documents=[a["content"] for a in new],
            metadatas=[{"title": a["title"], "topic": a["topic"]} for a in new],
        )


def _col(name: str):
    _, cols = _get_client()
    return cols[name]


def _now() -> str:
    return datetime.utcnow().isoformat()


# ── Audit CRUD ────────────────────────────────────────────────────────────────

def create_audit(base_url: str, max_pages: int = 50) -> str:
    audit_id = str(uuid.uuid4())
    _col("audits").add(
        ids=[f"audit_{audit_id}"],
        documents=[f"{base_url} SEO audit queued"],
        metadatas=[{
            "audit_id":         audit_id,
            "url":              base_url,
            "status":           "queued",
            "max_pages":        max_pages,
            "overall_score":    -1,
            "pages_crawled":    0,
            "current_agent":    "",
            "validation_status": "",
            "confidence_score": -1,
            "error_message":    "",
            "started_at":       "",
            "completed_at":     "",
            "created_at":       _now(),
        }],
    )
    return audit_id


def update_audit(audit_id: str, **kwargs) -> None:
    doc_id = f"audit_{audit_id}"
    existing = _col("audits").get(ids=[doc_id], include=["metadatas", "documents"])
    if not existing["ids"]:
        return
    meta = existing["metadatas"][0]
    doc  = existing["documents"][0]
    meta.update({k: (v if v is not None else "") for k, v in kwargs.items()})
    # Convert int/None cleanly
    for k in ("overall_score", "confidence_score", "pages_crawled", "max_pages"):
        if k in meta and meta[k] is None:
            meta[k] = -1
    _col("audits").upsert(ids=[doc_id], documents=[doc], metadatas=[meta])


def get_audit(audit_id: str) -> dict | None:
    result = _col("audits").get(ids=[f"audit_{audit_id}"], include=["metadatas"])
    if not result["ids"]:
        return None
    return result["metadatas"][0]


def list_audits(limit: int = 50) -> list[dict]:
    result = _col("audits").get(include=["metadatas"], limit=limit)
    metas = result.get("metadatas") or []
    return sorted(metas, key=lambda m: m.get("created_at", ""), reverse=True)


# ── Pages ─────────────────────────────────────────────────────────────────────

def add_page(audit_id: str, page: dict) -> None:
    url = page["url"]
    page_id = f"page_{audit_id}_{abs(hash(url)) % 10**8}"
    _col("pages").upsert(
        ids=[page_id],
        documents=[f"{url} {page.get('html', '')[:300]}"],
        metadatas=[{
            "audit_id":         audit_id,
            "url":              url,
            "status_code":      page.get("status_code") or -1,
            "page_size_bytes":  page.get("page_size_bytes") or 0,
            "crawl_duration_ms": page.get("crawl_duration_ms") or 0,
            "depth":            page.get("depth") or 0,
            "content_type":     page.get("content_type") or "",
        }],
    )


def get_pages(audit_id: str) -> list[dict]:
    result = _col("pages").get(where={"audit_id": audit_id}, include=["metadatas"])
    return result.get("metadatas") or []


# ── Issues ────────────────────────────────────────────────────────────────────

def add_issue(audit_id: str, agent_name: str, issue: dict, page_url: str = "") -> None:
    issue_id = f"issue_{audit_id}_{uuid.uuid4().hex[:8]}"
    doc = f"{issue.get('title', '')}. {issue.get('description', '')}"
    _col("issues").add(
        ids=[issue_id],
        documents=[doc],
        metadatas=[{
            "audit_id":      audit_id,
            "agent_name":    agent_name,
            "page_url":      page_url,
            "issue_type":    issue.get("type", ""),
            "severity":      issue.get("severity", "info"),
            "title":         issue.get("title", ""),
            "description":   issue.get("description", ""),
            # Detailed context fields
            "section":       str(issue.get("section", ""))[:400],
            "element":       str(issue.get("element", ""))[:400],
            "current_value": str(issue.get("current_value", ""))[:600],
            "fix":           str(issue.get("fix", ""))[:600],
            "before":        str(issue.get("before", ""))[:800],
            "after":         str(issue.get("after", ""))[:800],
        }],
    )


def get_issues(audit_id: str) -> list[dict]:
    result = _col("issues").get(where={"audit_id": audit_id}, include=["metadatas"])
    return result.get("metadatas") or []


def clear_agent_issues(audit_id: str, agent_name: str) -> int:
    """Delete all issues produced by agent_name for this audit. Returns deleted count."""
    col = _col("issues")
    result = col.get(
        where={"$and": [{"audit_id": audit_id}, {"agent_name": agent_name}]},
        include=[],
    )
    ids = result.get("ids") or []
    if ids:
        col.delete(ids=ids)
    return len(ids)


def clear_agent_recommendations(audit_id: str, agent_name: str) -> int:
    """Delete all recommendations produced by agent_name for this audit."""
    col = _col("recommendations")
    result = col.get(
        where={"$and": [{"audit_id": audit_id}, {"agent_name": agent_name}]},
        include=[],
    )
    ids = result.get("ids") or []
    if ids:
        col.delete(ids=ids)
    return len(ids)


def search_similar_issues(query: str, n: int = 5, exclude_audit_id: str | None = None) -> list[dict]:
    try:
        col = _col("issues")
        if col.count() == 0:
            return []
        where = {"audit_id": {"$ne": exclude_audit_id}} if exclude_audit_id else None
        results = col.query(query_texts=[query], n_results=min(n, col.count()), where=where)
        out = []
        for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
            out.append({"document": doc, "metadata": meta, "similarity": round(1 - dist, 3)})
        return out
    except Exception:
        return []


# ── Recommendations ───────────────────────────────────────────────────────────

def add_recommendation(audit_id: str, agent_name: str, rec: dict) -> None:
    rec_id = f"rec_{audit_id}_{uuid.uuid4().hex[:8]}"
    _col("recommendations").add(
        ids=[rec_id],
        documents=[rec.get("action", "")],
        metadatas=[{
            "audit_id":   audit_id,
            "agent_name": agent_name,
            "page_url":   str(rec.get("page_url", ""))[:800],
            "issue_type": rec.get("issue_type", ""),
            "priority":   rec.get("priority", "medium"),
            "action":     str(rec.get("action", ""))[:800],
            "section":    str(rec.get("section", ""))[:200],
            "element":    str(rec.get("element", ""))[:400],
            "before":     str(rec.get("before", ""))[:800],
            "after":      str(rec.get("after", ""))[:800],
        }],
    )


def get_recommendations(audit_id: str) -> list[dict]:
    result = _col("recommendations").get(where={"audit_id": audit_id}, include=["metadatas"])
    return result.get("metadatas") or []


# ── Workflow Memory ───────────────────────────────────────────────────────────

def log_workflow(audit_id: str, agent_name: str, event_type: str, data: dict = {}) -> None:
    log_id = f"wf_{audit_id}_{agent_name}_{uuid.uuid4().hex[:6]}"
    doc = f"Agent {agent_name} {event_type}"
    _col("workflow_memory").add(
        ids=[log_id],
        documents=[doc],
        metadatas=[{
            "audit_id":   audit_id,
            "agent_name": agent_name,
            "event_type": event_type,
            "status":     data.get("status", ""),
            "score":      data.get("score", -1),
            "issues_count": data.get("issues_count", 0),
            "timestamp":  _now(),
        }],
    )


def get_workflow_log(audit_id: str) -> list[dict]:
    result = _col("workflow_memory").get(where={"audit_id": audit_id}, include=["metadatas"])
    metas = result.get("metadatas") or []
    return sorted(metas, key=lambda m: m.get("timestamp", ""))


# ── Knowledge Base ────────────────────────────────────────────────────────────

def get_knowledge(topic: str, n: int = 3) -> list[dict]:
    try:
        col = _col("seo_knowledge")
        results = col.query(query_texts=[topic], n_results=min(n, len(SEO_KNOWLEDGE)))
        out = []
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            out.append({"title": meta.get("title", ""), "content": doc})
        return out
    except Exception:
        return []
