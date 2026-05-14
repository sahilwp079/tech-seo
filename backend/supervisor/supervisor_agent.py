"""
SupervisorAgent — top-level controller that implements the full enterprise pipeline:

  User Request
    → Intent Classification
    → Worker Chain Selection
    → Memory Retrieval (RAG context)
    → Workflow State Construction
    → DAG Execution
    → Result Aggregation
    → Workflow State Return

All inter-stage data flows through a typed WorkflowState so every stage
can inspect prior results, errors, and logs without direct coupling.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from supervisor.intent_classifier import IntentClassifier, ClassifiedIntent
from supervisor.worker_registry   import WorkerRegistry, worker_registry, WorkerChain

_log = logging.getLogger("supervisor")


# ── Pydantic contracts ────────────────────────────────────────────────────────

class WorkflowRequest(BaseModel):
    """Typed input contract accepted by SupervisorAgent."""
    url:         str
    instruction: str  = ""        # free-text intent hint from the user
    intent:      str  | None = None  # explicit override (skip classifier)
    max_pages:   int  | None = None  # overrides WorkerChain.default_max_pages
    options:     dict = Field(default_factory=dict)  # future extension point


class WorkflowState(BaseModel):
    """Typed shared state dictionary passed through every pipeline stage."""
    workflow_id:   str
    intent:        str
    confidence:    float
    classifier:    str                    # "rule" | "llm" | "explicit"
    task:          dict                   # original WorkflowRequest fields
    memory:        dict = Field(default_factory=dict)   # RAG context retrieved before execution
    results:       dict = Field(default_factory=dict)   # agent_name → result data
    errors:        list = Field(default_factory=list)   # ErrorRecord summaries
    logs:          list = Field(default_factory=list)   # execution timeline
    status:        str  = "queued"        # queued | running | completed | failed
    audit_id:      str  = ""
    overall_score: int | None = None
    created_at:    str  = Field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at:  str | None = None
    agent_chain:   list[str] = Field(default_factory=list)


class IntentListItem(BaseModel):
    intent:            str
    description:       str
    estimated_minutes: int
    default_max_pages: int
    agent_count:       int
    agents:            list[str]
    tags:              list[str]


# ── SupervisorAgent ───────────────────────────────────────────────────────────

class SupervisorAgent:
    """
    Routes a WorkflowRequest through intent classification → worker chain selection
    → memory retrieval → DAG execution and returns a fully populated WorkflowState.
    """

    def __init__(
        self,
        registry:  WorkerRegistry   = worker_registry,
        groq_key:  str              = "",
    ) -> None:
        self._registry   = registry
        self._classifier = IntentClassifier(groq_api_key=groq_key)

    # ── Main entry point ──────────────────────────────────────────────────────

    async def handle(
        self,
        request:   WorkflowRequest,
        event_bus: Any,
        store:     Any,
    ) -> WorkflowState:
        """
        Execute the full supervisor pipeline and return final WorkflowState.
        store is the chroma_store module; event_bus is core.event_bus.EventBus.
        """
        workflow_id = str(uuid.uuid4())
        state = WorkflowState(
            workflow_id=workflow_id,
            intent="",
            confidence=0.0,
            classifier="",
            task=request.model_dump(),
        )

        try:
            # Stage 1 — Classify intent
            state = await self._stage_classify(state, request)
            _log.info("[%s] intent=%s (%.0f%% confidence)", workflow_id, state.intent, state.confidence * 100)

            # Stage 2 — Select worker chain
            chain = self._registry.get_chain(state.intent)
            state.agent_chain = [a.name for a in chain.agents]
            self._log(state, "chain_selected", {
                "intent": state.intent,
                "agents": state.agent_chain,
                "max_pages": request.max_pages or chain.default_max_pages,
            })

            # Stage 3 — Retrieve memory context (RAG)
            state = await self._stage_retrieve_memory(state, store, request.url)

            # Stage 4 — Execute worker chain via DAG
            state = await self._stage_execute(state, request, chain, event_bus, store)

        except Exception as exc:
            _log.exception("[%s] Supervisor pipeline error: %s", workflow_id, exc)
            state.status       = "failed"
            state.completed_at = datetime.utcnow().isoformat()
            state.errors.append({"stage": "supervisor", "error": str(exc)})

        return state

    # ── Stage 1: Intent classification ────────────────────────────────────────

    async def _stage_classify(
        self, state: WorkflowState, request: WorkflowRequest
    ) -> WorkflowState:
        if request.intent and self._registry.has_intent(request.intent):
            # Caller provided explicit intent — skip classifier
            state.intent     = request.intent
            state.confidence = 1.0
            state.classifier = "explicit"
            self._log(state, "intent_explicit", {"intent": request.intent})
        else:
            classified: ClassifiedIntent = await self._classifier.classify(
                request.instruction, request.url
            )
            # If unknown, fall back to seo_audit
            if classified.intent == "unknown":
                classified.intent    = "seo_audit"
                classified.confidence = 0.5
            state.intent     = classified.intent
            state.confidence = classified.confidence
            state.classifier = classified.classifier
            self._log(state, "intent_classified", {
                "intent":       classified.intent,
                "confidence":   classified.confidence,
                "reasoning":    classified.reasoning,
                "alternatives": classified.alternatives,
            })
        return state

    # ── Stage 2: Memory / RAG context retrieval ───────────────────────────────

    async def _stage_retrieve_memory(
        self, state: WorkflowState, store: Any, url: str
    ) -> WorkflowState:
        try:
            # Retrieve past issues for this domain from ChromaDB vector search
            domain_query = f"SEO issues for {url}"
            similar = store.search_similar_issues(domain_query, n=5)

            # Retrieve relevant knowledge articles for this intent
            kb_articles = store.get_knowledge(state.intent.replace("_", " "), n=3)

            state.memory = {
                "similar_past_issues": similar,
                "knowledge_articles":  kb_articles,
            }
            self._log(state, "memory_retrieved", {
                "similar_issues": len(similar),
                "kb_articles":    len(kb_articles),
            })
        except Exception as exc:
            _log.warning("[%s] Memory retrieval failed: %s", state.workflow_id, exc)
            state.errors.append({"stage": "memory_retrieval", "error": str(exc)})

        return state

    # ── Stage 3: Execute DAG pipeline ────────────────────────────────────────

    async def _stage_execute(
        self,
        state:     WorkflowState,
        request:   WorkflowRequest,
        chain:     WorkerChain,
        event_bus: Any,
        store:     Any,
    ) -> WorkflowState:
        from agents.base_agent import AgentContext
        from core.dag_executor import execute_dag
        from utils.error_manager import error_manager
        from config import settings

        max_pages = request.max_pages or chain.default_max_pages
        audit_id  = store.create_audit(request.url, max_pages)
        state.audit_id = audit_id
        state.status   = "running"

        self._log(state, "execution_started", {
            "audit_id":  audit_id,
            "max_pages": max_pages,
            "agents":    state.agent_chain,
        })

        ctx = AgentContext(
            audit_id=audit_id,
            base_url=request.url,
            max_pages=max_pages,
            event_bus=event_bus,
            store=store,
            groq_api_key=settings.GROQ_API_KEY,
        )

        # Update audit status to running
        from datetime import datetime
        store.update_audit(
            audit_id,
            status="running",
            started_at=datetime.utcnow().isoformat(),
            current_agent=chain.agents[0].name if chain.agents else "",
        )

        # Execute DAG
        dag_results = await execute_dag(chain.agents, ctx)

        # Collect results into state
        for name, result in dag_results.items():
            state.results[name] = {
                "success":      result.success,
                "score":        result.score,
                "issues_count": result.issues_count,
                "duration_ms":  result.duration_ms,
                "retries":      result.retries,
                "error":        result.error,
            }

        # Overall score from ScoringAgent (if present)
        scoring = dag_results.get("ScoringAgent")
        state.overall_score = scoring.score if scoring else None

        # Error summary
        err_summary = error_manager.summary(audit_id)
        if err_summary["total"] > 0:
            state.errors.append({"stage": "execution", "summary": err_summary})

        state.status       = "completed"
        state.completed_at = datetime.utcnow().isoformat()

        self._log(state, "execution_completed", {
            "overall_score": state.overall_score,
            "failed_agents": [n for n, r in dag_results.items() if not r.success],
        })
        return state

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _log(self, state: WorkflowState, event: str, data: dict) -> None:
        entry = {"event": event, "timestamp": datetime.utcnow().isoformat(), **data}
        state.logs.append(entry)
        _log.debug("[%s] %s: %s", state.workflow_id, event, data)

    # ── Registry delegation ───────────────────────────────────────────────────

    def list_intents(self) -> list[dict]:
        return self._registry.list_intents()
