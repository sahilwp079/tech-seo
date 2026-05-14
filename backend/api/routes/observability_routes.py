"""Observability API — metrics, health, and error summary."""

import time

from fastapi import APIRouter, HTTPException

from utils.metrics import metrics
from utils.error_manager import error_manager

router = APIRouter(prefix="/observability", tags=["observability"])

_START_TIME = time.time()


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    """Lightweight liveness probe."""
    try:
        from storage.chroma_store import _get_client
        _get_client()
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {exc}"

    return {
        "status":       "ok" if db_status == "ok" else "degraded",
        "uptime_s":     int(time.time() - _START_TIME),
        "chromadb":     db_status,
    }


# ── Process-level metrics ─────────────────────────────────────────────────────

@router.get("/metrics")
async def get_process_metrics():
    """Aggregate metrics across all audits in this process lifetime."""
    return {
        "process":      metrics.get_process_summary(),
        "tools":        metrics.get_tool_stats(),
        "audit_ids":    metrics.list_audit_ids(),
    }


# ── Per-audit metrics ─────────────────────────────────────────────────────────

@router.get("/metrics/{audit_id}")
async def get_audit_metrics(audit_id: str):
    """Detailed per-agent timing and token usage for one audit."""
    data = metrics.get_audit_metrics(audit_id)
    if not data["agents"] and not data["tokens"]["calls"]:
        raise HTTPException(404, f"No metrics found for audit {audit_id!r}")
    return data


# ── Error summary ─────────────────────────────────────────────────────────────

@router.get("/errors/{audit_id}")
async def get_audit_errors(audit_id: str):
    """Return all recorded errors and recovery status for one audit."""
    errors = error_manager.get_errors(audit_id)
    summary = error_manager.summary(audit_id)
    return {
        "audit_id": audit_id,
        "summary":  summary,
        "errors":   [
            {
                "agent":     e.agent,
                "error":     e.error,
                "attempt":   e.attempt,
                "timestamp": e.timestamp,
                "recovered": e.recovered,
            }
            for e in errors
        ],
    }


# ── Tool stats (alias) ────────────────────────────────────────────────────────

@router.get("/tools/stats")
async def get_tool_stats():
    """Per-tool call counts, failure rates, and average durations."""
    return {"tools": metrics.get_tool_stats()}
