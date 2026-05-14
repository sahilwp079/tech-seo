"use client";
import { useEffect, useState } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────
interface WorkflowStep {
  agent_name:   string;
  event_type:   string;
  status:       string;
  score:        number;
  issues_count: number;
  timestamp:    string;
}

interface WorkflowResponse {
  audit_id:      string;
  current_agent: string;
  pages_crawled: number;
  steps:         WorkflowStep[];
}

interface AgentRun {
  agent:        string;
  label:        string;
  icon:         string;
  status:       "running" | "completed" | "failed" | "skipped";
  score:        number | null;
  issues_count: number;
  duration_s:   number | null;
  started_at:   string;
  ended_at:     string | null;
  error:        string | null;
  is_revision:  boolean;
  revision_cycle: number;
}

// ── Agent display metadata ────────────────────────────────────────────────────
const AGENT_META: Record<string, { label: string; icon: string; what: string }> = {
  PlannerAgent:            { label: "Planner",             icon: "🗺️",  what: "Built execution plan" },
  CrawlAgent:              { label: "Website Crawler",     icon: "🕷️",  what: "Discovered & crawled pages" },
  MetaAnalysisAgent:       { label: "Meta Tags & Headings",icon: "🏷️",  what: "Checked title, description, H1-H6" },
  LinkAnalysisAgent:       { label: "Link Checker",        icon: "🔗",  what: "Found broken links & redirects" },
  PerformanceAgent:        { label: "Performance",         icon: "⚡",  what: "Measured page speed" },
  IndexabilityAgent:       { label: "Indexability",        icon: "🔍",  what: "Checked robots.txt & sitemap" },
  StructuredDataAgent:     { label: "Structured Data",     icon: "🧩",  what: "Validated JSON-LD schema" },
  SecurityAgent:           { label: "Security",            icon: "🔒",  what: "Checked HTTPS & headers" },
  ValidationAgent:         { label: "Validation",          icon: "🛡️",  what: "Cross-checked all findings" },
  RecommendationAgent:     { label: "AI Recommendations",  icon: "💡",  what: "Generated fix suggestions" },
  ScoringAgent:            { label: "Score Calculator",    icon: "📊",  what: "Computed weighted SEO score" },
  ReportAgent:             { label: "Report Generator",    icon: "📄",  what: "Exported Excel report" },
  MasterOrchestratorAgent: { label: "Orchestrator",        icon: "🎯",  what: "Managed full audit pipeline" },
};

// ── Phase grouping ────────────────────────────────────────────────────────────
const PHASE_FOR: Record<string, string> = {
  PlannerAgent:            "Planning",
  CrawlAgent:              "Discovery",
  MetaAnalysisAgent:       "Analysis",
  LinkAnalysisAgent:       "Analysis",
  PerformanceAgent:        "Analysis",
  IndexabilityAgent:       "Analysis",
  StructuredDataAgent:     "Analysis",
  SecurityAgent:           "Analysis",
  ValidationAgent:         "Quality Check",
  RecommendationAgent:     "Output",
  ScoringAgent:            "Output",
  ReportAgent:             "Output",
  MasterOrchestratorAgent: "Orchestration",
};

const PHASE_COLOR: Record<string, string> = {
  Planning:       "bg-violet-100 text-violet-700 border-violet-300",
  Discovery:      "bg-blue-100   text-blue-700   border-blue-300",
  Analysis:       "bg-cyan-100   text-cyan-700   border-cyan-300",
  "Quality Check":"bg-amber-100  text-amber-700  border-amber-300",
  Output:         "bg-green-100  text-green-700  border-green-300",
  Orchestration:  "bg-gray-100   text-gray-600   border-gray-300",
};

function fmt(s: number | null): string {
  if (s == null) return "—";
  if (s < 1) return `${Math.round(s * 1000)}ms`;
  return `${s.toFixed(1)}s`;
}

function ts(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function scoreColor(score: number | null): string {
  if (score == null) return "text-gray-400";
  if (score >= 80) return "text-green-600";
  if (score >= 60) return "text-yellow-600";
  return "text-red-600";
}

// ── Convert workflow steps → agent runs ──────────────────────────────────────
function buildRuns(steps: WorkflowStep[]): AgentRun[] {
  const runs: AgentRun[]   = [];
  const starts: Record<string, WorkflowStep> = {};

  // Detect which agents are re-runs (appear more than once as "completed/failed")
  const completionCounts: Record<string, number> = {};
  steps.forEach((s) => {
    if (s.event_type === "completed" || s.event_type === "failed") {
      completionCounts[s.agent_name] = (completionCounts[s.agent_name] ?? 0) + 1;
    }
  });

  const agentSeenCount: Record<string, number> = {};

  steps.forEach((step) => {
    const key = step.agent_name;

    if (step.event_type === "started") {
      starts[key] = step;
    } else if (step.event_type === "completed" || step.event_type === "failed") {
      const start   = starts[key];
      const startTs = start?.timestamp ?? step.timestamp;
      const endTs   = step.timestamp;

      const durS = (new Date(endTs.endsWith("Z") ? endTs : endTs + "Z").getTime() -
                    new Date(startTs.endsWith("Z") ? startTs : startTs + "Z").getTime()) / 1000;

      agentSeenCount[key] = (agentSeenCount[key] ?? 0) + 1;
      const isRevision     = agentSeenCount[key] > 1 && (completionCounts[key] ?? 0) > 1;
      const revisionCycle  = Math.max(0, agentSeenCount[key] - 1);

      const meta = AGENT_META[key] ?? { label: key, icon: "🤖", what: "" };

      runs.push({
        agent:          key,
        label:          meta.label,
        icon:           meta.icon,
        status:         step.event_type === "completed" ? "completed" : "failed",
        score:          step.score > 0 ? step.score : null,
        issues_count:   step.issues_count,
        duration_s:     durS >= 0 ? durS : null,
        started_at:     startTs,
        ended_at:       endTs,
        error:          null,
        is_revision:    isRevision,
        revision_cycle: revisionCycle,
      });

      delete starts[key];
    }
  });

  // In-progress agents (started but not finished yet)
  Object.values(starts).forEach((step) => {
    const meta = AGENT_META[step.agent_name] ?? { label: step.agent_name, icon: "🤖", what: "" };
    runs.push({
      agent:          step.agent_name,
      label:          meta.label,
      icon:           meta.icon,
      status:         "running",
      score:          null,
      issues_count:   0,
      duration_s:     null,
      started_at:     step.timestamp,
      ended_at:       null,
      error:          null,
      is_revision:    false,
      revision_cycle: 0,
    });
  });

  return runs;
}

// ── Row component ─────────────────────────────────────────────────────────────
function RunRow({ run, isLast }: { run: AgentRun; isLast: boolean }) {
  const phase     = PHASE_FOR[run.agent] ?? "Orchestration";
  const phaseStyle = PHASE_COLOR[phase] ?? PHASE_COLOR.Orchestration;

  const statusIcon = run.status === "completed" ? "✓"
    : run.status === "failed"   ? "✗"
    : run.status === "running"  ? "⟳"
    : "○";

  const statusBg = {
    completed: "bg-green-50 border-green-200",
    failed:    "bg-red-50   border-red-200",
    running:   "bg-blue-50  border-blue-200 animate-pulse",
    skipped:   "bg-gray-50  border-gray-200",
  }[run.status];

  const statusText = {
    completed: "text-green-700",
    failed:    "text-red-600",
    running:   "text-blue-600",
    skipped:   "text-gray-400",
  }[run.status];

  return (
    <div className="flex gap-3 group">
      {/* Timeline spine */}
      <div className="flex flex-col items-center shrink-0">
        <div className={`w-7 h-7 rounded-full flex items-center justify-center text-sm font-bold border-2 z-10
          ${run.status === "completed" ? "bg-green-500 border-green-600 text-white"
          : run.status === "failed"    ? "bg-red-500   border-red-600   text-white"
          : run.status === "running"   ? "bg-blue-500  border-blue-600  text-white animate-pulse"
          : "bg-gray-200 border-gray-300 text-gray-400"}`}>
          {statusIcon}
        </div>
        {!isLast && <div className="w-0.5 flex-1 bg-gray-200 mt-1 mb-1 min-h-[20px]" />}
      </div>

      {/* Card */}
      <div className={`flex-1 rounded-xl border px-4 py-3 mb-2 ${statusBg}`}>
        <div className="flex items-start justify-between gap-3 flex-wrap">
          {/* Left — name + phase + what */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-base">{run.icon}</span>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`font-semibold text-sm ${statusText}`}>{run.label}</span>
                <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${phaseStyle}`}>{phase}</span>
                {run.is_revision && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 border border-amber-300 font-semibold">
                    🔄 Revision {run.revision_cycle}
                  </span>
                )}
              </div>
              <div className="text-xs text-gray-400 mt-0.5">
                {AGENT_META[run.agent]?.what}
              </div>
            </div>
          </div>

          {/* Right — metrics */}
          <div className="flex items-center gap-3 text-xs shrink-0 flex-wrap justify-end">
            {run.score != null && (
              <span className={`font-bold text-sm ${scoreColor(run.score)}`}>
                {run.score}<span className="text-gray-400 font-normal text-[10px]">/100</span>
              </span>
            )}
            {run.issues_count > 0 && (
              <span className="bg-white border border-gray-200 rounded-full px-2 py-0.5 text-gray-600">
                {run.issues_count} issue{run.issues_count !== 1 ? "s" : ""}
              </span>
            )}
            <div className="text-right text-gray-400">
              <div>{ts(run.started_at)}</div>
              {run.duration_s != null && (
                <div className="font-medium text-gray-500">{fmt(run.duration_s)}</div>
              )}
            </div>
          </div>
        </div>

        {/* Error message */}
        {run.status === "failed" && run.error && (
          <div className="mt-2 text-xs text-red-600 bg-red-50 rounded px-3 py-1.5 border border-red-200">
            {run.error}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
interface Props {
  auditId:      string;
  pagesCount?:  number;
  totalDurationS?: number | null;
  finalScore?:  number | null;
  isRunning?:   boolean;
}

export default function ExecutionLog({ auditId, pagesCount, totalDurationS, finalScore, isRunning }: Props) {
  const [log,     setLog]     = useState<WorkflowResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!auditId) return;
    let timer: ReturnType<typeof setInterval>;

    const fetch_ = async () => {
      try {
        const r = await fetch(`http://localhost:8000/api/audit/${auditId}/workflow-log`);
        if (r.ok) setLog(await r.json());
      } catch { /* ignore */ }
      setLoading(false);
    };

    fetch_();
    if (isRunning) timer = setInterval(fetch_, 4000);
    return () => clearInterval(timer);
  }, [auditId, isRunning]);

  if (loading) {
    return (
      <div className="bg-white rounded-xl border p-10 flex justify-center">
        <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const runs     = buildRuns(log?.steps ?? []);
  const initRuns = runs.filter((r) => !r.is_revision);
  const revRuns  = runs.filter((r) => r.is_revision);

  // Group revision runs by cycle
  const revMap: Record<number, AgentRun[]> = {};
  revRuns.forEach((r) => {
    (revMap[r.revision_cycle] = revMap[r.revision_cycle] ?? []).push(r);
  });

  const totalSteps = runs.length;
  const doneSteps  = runs.filter((r) => r.status === "completed").length;
  const failSteps  = runs.filter((r) => r.status === "failed").length;

  return (
    <div className="space-y-4">
      {/* ── Summary bar ────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border shadow-sm p-5 flex flex-wrap gap-6">
        <div className="text-center">
          <div className="text-2xl font-bold text-gray-800">{totalSteps}</div>
          <div className="text-xs text-gray-400 mt-0.5">Total Steps</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-green-600">{doneSteps}</div>
          <div className="text-xs text-gray-400 mt-0.5">Completed</div>
        </div>
        {failSteps > 0 && (
          <div className="text-center">
            <div className="text-2xl font-bold text-red-500">{failSteps}</div>
            <div className="text-xs text-gray-400 mt-0.5">Failed</div>
          </div>
        )}
        {Object.keys(revMap).length > 0 && (
          <div className="text-center">
            <div className="text-2xl font-bold text-amber-500">{Object.keys(revMap).length}</div>
            <div className="text-xs text-gray-400 mt-0.5">Revision Cycles</div>
          </div>
        )}
        {pagesCount != null && pagesCount > 0 && (
          <div className="text-center">
            <div className="text-2xl font-bold text-blue-600">{pagesCount}</div>
            <div className="text-xs text-gray-400 mt-0.5">Pages Crawled</div>
          </div>
        )}
        {totalDurationS != null && (
          <div className="text-center">
            <div className="text-2xl font-bold text-purple-600">{fmt(totalDurationS)}</div>
            <div className="text-xs text-gray-400 mt-0.5">Total Time</div>
          </div>
        )}
        {finalScore != null && finalScore > 0 && (
          <div className="text-center">
            <div className={`text-2xl font-bold ${scoreColor(finalScore)}`}>{finalScore}</div>
            <div className="text-xs text-gray-400 mt-0.5">Final Score</div>
          </div>
        )}
      </div>

      {/* ── Initial run ────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="px-5 py-3 bg-gradient-to-r from-blue-50 to-indigo-50 border-b flex items-center gap-2">
          <span className="text-sm font-bold text-blue-800">🚀 Initial Run</span>
          <span className="text-xs text-blue-400">{initRuns.length} steps</span>
        </div>
        <div className="p-5 space-y-0">
          {initRuns.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-6">No steps logged yet.</p>
          ) : (
            initRuns.map((run, i) => (
              <RunRow key={`${run.agent}-${i}`} run={run} isLast={i === initRuns.length - 1} />
            ))
          )}
        </div>
      </div>

      {/* ── Revision cycles ─────────────────────────────────────────────────── */}
      {Object.entries(revMap).map(([cycle, cycleRuns]) => (
        <div key={cycle} className="bg-white rounded-xl border border-amber-200 shadow-sm overflow-hidden">
          <div className="px-5 py-3 bg-gradient-to-r from-amber-50 to-orange-50 border-b border-amber-200 flex items-center gap-2">
            <span className="text-sm font-bold text-amber-800">🔄 Revision Cycle {cycle}</span>
            <span className="text-xs text-amber-400">{cycleRuns.length} agents re-run</span>
            <span className="text-xs text-amber-500 ml-auto">
              Agents revised because initial validation failed — improving quality
            </span>
          </div>
          <div className="p-5 space-y-0">
            {cycleRuns.map((run, i) => (
              <RunRow key={`${run.agent}-rev-${i}`} run={run} isLast={i === cycleRuns.length - 1} />
            ))}
          </div>
        </div>
      ))}

      {/* ── Live indicator ──────────────────────────────────────────────────── */}
      {isRunning && (
        <div className="flex items-center justify-center gap-2 text-sm text-blue-500 py-2">
          <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
          Audit in progress — log auto-refreshes every 4 seconds
        </div>
      )}
    </div>
  );
}
