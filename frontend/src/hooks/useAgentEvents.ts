"use client";
import { useEffect, useRef, useState } from "react";

export interface AgentEvent {
  event: string;
  agent: string;
  timestamp: string;
  status?: string;
  score?: number | null;
  issues_count?: number;
  pages_crawled?: number;
  overall_score?: number;
  duration_ms?: number;
  retries?: number;
  plan?: Array<{ agent: string; dependencies: string[]; status: string }>;
  error?: string;
  // revision events
  cycle?: number;
  reason?: string;
  checks_failed?: string[];
  agents_revised?: string[];
  validation_status?: string;
  further_revision?: boolean;
}

export interface AgentState {
  name: string;
  status: "pending" | "running" | "completed" | "failed";
  score: number | null;
  issues_count: number;
  dependencies: string[];
  duration_ms: number | null;
  retries: number;
  error: string | null;
  startedAt: string | null;
  completedAt: string | null;
  revision_cycle: number; // 0 = initial run, 1+ = revision
}

export interface RevisionInfo {
  cycle: number;
  reason: string;
  checksFailed: string[];
  agentsRevised: string[];
  validationStatus: string;
  started_at: string;
  completed_at: string | null;
}

const WS_BASE = "ws://localhost:8000/api/ws/audit";

export function useAgentEvents(auditId: string | null) {
  const [events,    setEvents]    = useState<AgentEvent[]>([]);
  const [agents,    setAgents]    = useState<Record<string, AgentState>>({});
  const [revisions, setRevisions] = useState<RevisionInfo[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!auditId) return;
    const ws = new WebSocket(`${WS_BASE}/${auditId}`);
    wsRef.current = ws;

    ws.onopen  = () => setConnected(true);
    ws.onclose = () => setConnected(false);

    ws.onmessage = (msg) => {
      const ev: AgentEvent = JSON.parse(msg.data);
      setEvents((prev) => [...prev, ev]);

      // ── Plan ready — initialise agent map ──────────────────────────────────
      if (ev.event === "plan.ready" && ev.plan) {
        setAgents({
          PlannerAgent: {
            name: "PlannerAgent", status: "completed", score: null,
            issues_count: 0, dependencies: [], duration_ms: null,
            retries: 0, error: null, startedAt: ev.timestamp, completedAt: ev.timestamp,
            revision_cycle: 0,
          },
          ...Object.fromEntries(
            ev.plan.map((node) => [
              node.agent,
              {
                name: node.agent, status: "pending", score: null,
                issues_count: 0, dependencies: node.dependencies,
                duration_ms: null, retries: 0, error: null,
                startedAt: null, completedAt: null, revision_cycle: 0,
              },
            ])
          ),
        });
        return;
      }

      // ── Revision events ────────────────────────────────────────────────────
      if (ev.event === "revision.started") {
        setRevisions((prev) => [
          ...prev,
          {
            cycle:            ev.cycle ?? prev.length + 1,
            reason:           ev.reason ?? "Validation failed",
            checksFailed:     ev.checks_failed ?? [],
            agentsRevised:    [],
            validationStatus: "",
            started_at:       ev.timestamp,
            completed_at:     null,
          },
        ]);
        return;
      }

      if (ev.event === "revision.completed") {
        setRevisions((prev) =>
          prev.map((r) =>
            r.cycle === ev.cycle
              ? { ...r, agentsRevised: ev.agents_revised ?? [], validationStatus: ev.validation_status ?? "", completed_at: ev.timestamp }
              : r
          )
        );
        return;
      }

      // ── Agent lifecycle events ─────────────────────────────────────────────
      if (!ev.agent) return;

      setAgents((prev) => {
        const existing: AgentState = prev[ev.agent] ?? {
          name: ev.agent, status: "pending", score: null,
          issues_count: 0, dependencies: [],
          duration_ms: null, retries: 0, error: null,
          startedAt: null, completedAt: null, revision_cycle: 0,
        };

        let next = { ...existing };

        if (ev.event === "agent.started") {
          next.status    = "running";
          next.startedAt = ev.timestamp;
        } else if (ev.event === "agent.completed") {
          next.status      = "completed";
          next.completedAt = ev.timestamp;
          next.score       = ev.score      ?? existing.score;
          next.issues_count = ev.issues_count ?? existing.issues_count;
          next.duration_ms  = ev.duration_ms ?? existing.duration_ms;
          next.retries      = ev.retries     ?? existing.retries;
        } else if (ev.event === "agent.failed") {
          next.status      = "failed";
          next.completedAt = ev.timestamp;
          next.error       = ev.error ?? "Unknown error";
          next.duration_ms = ev.duration_ms ?? existing.duration_ms;
        } else if (ev.event === "retry_triggered") {
          next.retries = (ev.retries ?? 1);
        }

        return { ...prev, [ev.agent]: next };
      });
    };

    return () => ws.close();
  }, [auditId]);

  return { events, agents, revisions, connected };
}
