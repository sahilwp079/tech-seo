"""Audit API routes — ChromaDB-backed, no MySQL."""

import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import storage.chroma_store as store
from agents.master_orchestrator import run_audit
from config import settings
from core.connection_manager import manager
from core.event_bus import EventBus

router = APIRouter(prefix="/audit", tags=["audit"])


class StartRequest(BaseModel):
    url: str
    max_pages: int = 50


# ── Start audit ───────────────────────────────────────────────────────────────

@router.post("/start", status_code=202)
async def start_audit(body: StartRequest, background_tasks: BackgroundTasks):
    audit_id = store.create_audit(body.url, body.max_pages)
    background_tasks.add_task(_run, audit_id, body.url, body.max_pages)
    return {"audit_id": audit_id, "status": "queued", "url": body.url}


async def _run(audit_id: str, url: str, max_pages: int) -> None:
    bus = EventBus()
    bus.subscribe_all(manager.event_handler)
    await run_audit(audit_id, url, max_pages, bus)


# ── Status & report ───────────────────────────────────────────────────────────

@router.get("/{audit_id}/status")
async def get_status(audit_id: str):
    audit = store.get_audit(audit_id)
    if not audit:
        raise HTTPException(404, "Audit not found")
    # Count revision cycles from workflow log
    wf_log = store.get_workflow_log(audit_id)
    revision_cycles = sum(
        1 for e in wf_log if e.get("event_type") == "revision_summary"
    )
    return {
        "audit_id":          audit_id,
        "status":            audit.get("status", "queued"),
        "overall_score":     audit.get("overall_score", -1),
        "pages_crawled":     audit.get("pages_crawled", 0),
        "current_agent":     audit.get("current_agent", ""),
        "validation_status": audit.get("validation_status", ""),
        "confidence_score":  audit.get("confidence_score", -1),
        "revision_cycles":   revision_cycles,
        "started_at":        audit.get("started_at", ""),
        "completed_at":      audit.get("completed_at", ""),
        "error_message":     audit.get("error_message", ""),
        "created_at":        audit.get("created_at", ""),
    }


@router.get("/{audit_id}/report")
async def get_report(audit_id: str):
    audit = store.get_audit(audit_id)
    if not audit:
        raise HTTPException(404, "Audit not found")
    if audit.get("status") != "completed":
        raise HTTPException(400, f"Audit not completed yet (status: {audit.get('status')})")

    issues = store.get_issues(audit_id)
    recs   = store.get_recommendations(audit_id)
    wf_log = store.get_workflow_log(audit_id)

    # Group issues by agent
    agent_groups: dict[str, list[dict]] = {}
    sev_counts = {"critical": 0, "warning": 0, "info": 0}
    for issue in issues:
        ag = issue.get("agent_name", "other")
        agent_groups.setdefault(ag, []).append(issue)
        sev_counts[issue.get("severity", "info")] = sev_counts.get(issue.get("severity", "info"), 0) + 1

    # Per-agent scores from workflow log
    agent_scores: dict[str, int] = {}
    for e in wf_log:
        if e["event_type"] == "completed" and e.get("score", -1) != -1:
            agent_scores[e["agent_name"]] = e["score"]

    SECTION_MAP = {
        "MetaAnalysisAgent":   "meta",
        "LinkAnalysisAgent":   "links",
        "PerformanceAgent":    "performance",
        "IndexabilityAgent":   "indexability",
        "StructuredDataAgent": "structured_data",
        "SecurityAgent":       "security",
    }
    sections = {}
    for agent_name, section_key in SECTION_MAP.items():
        sections[section_key] = {
            "score":  agent_scores.get(agent_name),
            "issues": [
                {
                    "agent_name":    i.get("agent_name"),
                    "issue_type":    i.get("issue_type"),
                    "severity":      i.get("severity"),
                    "title":         i.get("title"),
                    "description":   i.get("description"),
                    "page_url":      i.get("page_url"),
                    "section":       i.get("section", ""),
                    "element":       i.get("element", ""),
                    "current_value": i.get("current_value", ""),
                    "fix":           i.get("fix", ""),
                    "before":        i.get("before", ""),
                    "after":         i.get("after", ""),
                }
                for i in sorted(
                    agent_groups.get(agent_name, []),
                    key=lambda x: {"critical": 0, "warning": 1, "info": 2}.get(x.get("severity", "info"), 2)
                )
            ],
        }

    # Parse persisted validation checks
    raw_checks = audit.get("validation_checks", "")
    try:
        validation_checks = json.loads(raw_checks) if raw_checks else []
    except Exception:
        validation_checks = []

    return {
        "audit_id":           audit_id,
        "url":                audit.get("url", ""),
        "status":             audit.get("status"),
        "overall_score":      audit.get("overall_score", -1),
        "validation_status":  audit.get("validation_status", ""),
        "confidence_score":   audit.get("confidence_score", -1),
        "validation_checks":  validation_checks,
        "started_at":         audit.get("started_at", ""),
        "completed_at":       audit.get("completed_at", ""),
        "summary": {
            "total_issues": len(issues),
            "critical":     sev_counts["critical"],
            "warnings":     sev_counts["warning"],
            "info":         sev_counts["info"],
        },
        "sections": sections,
        "recommendations": sorted(
            [
                {
                    "agent_name": r.get("agent_name"),
                    "page_url":   r.get("page_url", ""),
                    "issue_type": r.get("issue_type"),
                    "priority":   r.get("priority"),
                    "action":     r.get("action"),
                    "section":    r.get("section", ""),
                    "element":    r.get("element", ""),
                    "before":     r.get("before", ""),
                    "after":      r.get("after", ""),
                }
                for r in recs
            ],
            key=lambda r: {"high": 0, "medium": 1, "low": 2}.get(r.get("priority", "low"), 2)
        ),
        "workflow_log": wf_log,
    }


# ── List & delete ─────────────────────────────────────────────────────────────

@router.get("/list")
async def list_audits(limit: int = 20):
    audits = store.list_audits(limit)
    return {"audits": audits, "total": len(audits)}


@router.delete("/{audit_id}", status_code=204)
async def delete_audit(audit_id: str):
    audit = store.get_audit(audit_id)
    if not audit:
        raise HTTPException(404, "Audit not found")
    store.update_audit(audit_id, status="deleted")


# ── Workflow log ──────────────────────────────────────────────────────────────

@router.get("/{audit_id}/workflow-log")
async def get_workflow_log(audit_id: str):
    audit = store.get_audit(audit_id)
    if not audit:
        raise HTTPException(404, "Audit not found")
    return {
        "audit_id":      audit_id,
        "current_agent": audit.get("current_agent", ""),
        "pages_crawled": audit.get("pages_crawled", 0),
        "steps":         store.get_workflow_log(audit_id),
    }


# ── Excel download ────────────────────────────────────────────────────────────

@router.get("/{audit_id}/excel")
async def download_excel(audit_id: str):
    audit = store.get_audit(audit_id)
    if not audit:
        raise HTTPException(404, "Audit not found")
    path = Path(settings.REPORTS_DIR) / f"audit_{audit_id}_report.xlsx"
    if not path.exists():
        raise HTTPException(404, "Excel report not generated yet.")
    return FileResponse(
        path=str(path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"seo_audit_{audit_id}.xlsx",
    )


# ── Semantic search ───────────────────────────────────────────────────────────

@router.get("/{audit_id}/similar-issues")
async def similar_issues(audit_id: str, query: str, n: int = 5):
    return {"query": query, "results": store.search_similar_issues(query, n, exclude_audit_id=audit_id)}


@router.get("/knowledge/search")
async def knowledge_search(q: str, n: int = 3):
    return {"query": q, "articles": store.get_knowledge(q, n)}
