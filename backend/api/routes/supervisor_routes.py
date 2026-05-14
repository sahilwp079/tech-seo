"""Supervisor API routes — intent-driven workflow execution."""

from fastapi import APIRouter, BackgroundTasks, HTTPException

import storage.chroma_store as store
from core.connection_manager import manager
from core.event_bus import EventBus
from supervisor.supervisor_agent import SupervisorAgent, WorkflowRequest, WorkflowState
from supervisor.worker_registry import worker_registry
from config import settings

router = APIRouter(prefix="/workflow", tags=["workflow"])

# Process-wide supervisor singleton
_supervisor = SupervisorAgent(registry=worker_registry, groq_key=settings.GROQ_API_KEY)

# In-memory workflow state cache (workflow_id → WorkflowState)
# In production this would be stored in Redis or a DB
_workflow_states: dict[str, WorkflowState] = {}


# ── Run workflow ──────────────────────────────────────────────────────────────

@router.post("/run", status_code=202)
async def run_workflow(body: WorkflowRequest, background_tasks: BackgroundTasks):
    """
    Submit a workflow request.  The Supervisor classifies the intent,
    selects the appropriate agent chain, and runs the full pipeline
    in the background.

    Returns workflow_id and classified intent immediately (202 Accepted).
    Poll GET /workflow/{workflow_id}/state for progress.
    """
    # Classify synchronously so the caller sees the intent right away
    from supervisor.intent_classifier import IntentClassifier
    classifier = IntentClassifier(groq_api_key=settings.GROQ_API_KEY)
    classified = await classifier.classify(body.instruction, body.url)
    intent = body.intent or (
        classified.intent if classified.intent != "unknown" else "seo_audit"
    )

    # Get chain to return agent list to caller
    chain = worker_registry.get_chain(intent)
    import uuid
    workflow_id = str(uuid.uuid4())

    # Placeholder state so /state returns immediately
    from supervisor.supervisor_agent import WorkflowState
    from datetime import datetime
    placeholder = WorkflowState(
        workflow_id=workflow_id,
        intent=intent,
        confidence=classified.confidence,
        classifier=classified.classifier,
        task=body.model_dump(),
        status="queued",
        agent_chain=[a.name for a in chain.agents],
    )
    _workflow_states[workflow_id] = placeholder

    background_tasks.add_task(_run_workflow_bg, workflow_id, body)

    return {
        "workflow_id":    workflow_id,
        "status":         "queued",
        "intent":         intent,
        "confidence":     classified.confidence,
        "classifier":     classified.classifier,
        "agent_chain":    [a.name for a in chain.agents],
        "estimated_minutes": chain.estimated_minutes,
    }


async def _run_workflow_bg(workflow_id: str, body: WorkflowRequest) -> None:
    bus = EventBus()
    bus.subscribe_all(manager.event_handler)
    state = await _supervisor.handle(body, bus, store)
    state.workflow_id = workflow_id         # preserve the pre-assigned ID
    _workflow_states[workflow_id] = state


# ── Workflow state ────────────────────────────────────────────────────────────

@router.get("/{workflow_id}/state")
async def get_workflow_state(workflow_id: str) -> WorkflowState:
    """
    Return the current WorkflowState for a submitted workflow.
    Includes intent, confidence, per-agent results, errors, and logs.
    """
    state = _workflow_states.get(workflow_id)
    if not state:
        raise HTTPException(404, f"Workflow '{workflow_id}' not found")
    return state


# ── Available intents ─────────────────────────────────────────────────────────

@router.get("/intents")
async def list_intents():
    """Return all registered intent → agent-chain mappings."""
    return {"intents": _supervisor.list_intents()}


# ── Classify only (dry-run) ───────────────────────────────────────────────────

@router.post("/classify")
async def classify_intent(body: WorkflowRequest):
    """
    Classify the intent for a request without running any agents.
    Useful for previewing which chain would be selected.
    """
    from supervisor.intent_classifier import IntentClassifier
    classifier = IntentClassifier(groq_api_key=settings.GROQ_API_KEY)
    classified = await classifier.classify(body.instruction, body.url)
    intent = body.intent or (
        classified.intent if classified.intent != "unknown" else "seo_audit"
    )
    chain = worker_registry.get_chain(intent)
    return {
        "intent":            intent,
        "confidence":        classified.confidence,
        "reasoning":         classified.reasoning,
        "classifier":        classified.classifier,
        "alternatives":      classified.alternatives,
        "agent_chain":       [a.name for a in chain.agents],
        "estimated_minutes": chain.estimated_minutes,
        "default_max_pages": chain.default_max_pages,
    }
