"use client";
import type { AgentState, RevisionInfo } from "@/hooks/useAgentEvents";

// ── Agent metadata ────────────────────────────────────────────────────────────
const AGENT_META: Record<string, { label: string; icon: string; desc: string }> = {
  PlannerAgent:         { label: "Planner",         icon: "🗺️",  desc: "Builds the execution plan" },
  CrawlAgent:           { label: "Crawler",          icon: "🕷️",  desc: "Discovers & crawls all pages" },
  MetaAnalysisAgent:    { label: "Meta Tags",        icon: "🏷️",  desc: "Title, description, H1-H6" },
  LinkAnalysisAgent:    { label: "Links",            icon: "🔗",  desc: "Broken links & redirects" },
  PerformanceAgent:     { label: "Performance",      icon: "⚡",  desc: "Speed & Core Web Vitals" },
  IndexabilityAgent:    { label: "Indexability",     icon: "🔍",  desc: "robots.txt, sitemap, noindex" },
  StructuredDataAgent:  { label: "Structured Data",  icon: "🧩",  desc: "JSON-LD schema validation" },
  SecurityAgent:        { label: "Security",         icon: "🔒",  desc: "HTTPS & security headers" },
  ValidationAgent:      { label: "Validation",       icon: "🛡️",  desc: "Cross-checks all findings" },
  RecommendationAgent:  { label: "Recommendations",  icon: "💡",  desc: "AI-powered fix suggestions" },
  ScoringAgent:         { label: "Scoring",          icon: "📊",  desc: "Weighted overall SEO score" },
  ReportAgent:          { label: "Report",           icon: "📄",  desc: "Generates Excel report" },
};

// ── Status styling ────────────────────────────────────────────────────────────
const CARD_STYLE: Record<string, string> = {
  pending:   "bg-gray-50   border-gray-200  text-gray-400",
  running:   "bg-blue-50   border-blue-400  text-blue-700  shadow-blue-100 shadow-md",
  completed: "bg-green-50  border-green-400 text-green-700",
  failed:    "bg-red-50    border-red-400   text-red-700",
};
const DOT_STYLE: Record<string, string> = {
  pending:   "bg-gray-300",
  running:   "bg-blue-500 animate-ping",
  completed: "bg-green-500",
  failed:    "bg-red-500",
};

// ── DAG layout ────────────────────────────────────────────────────────────────
const LAYERS: { label: string; agents: string[]; parallel?: boolean }[] = [
  { label: "Phase 0 — Planning",                 agents: ["PlannerAgent"] },
  { label: "Phase 1 — Discovery",                agents: ["CrawlAgent"] },
  {
    label: "Phase 2 — Parallel Analysis",        parallel: true,
    agents: ["MetaAnalysisAgent","LinkAnalysisAgent","PerformanceAgent",
             "IndexabilityAgent","StructuredDataAgent","SecurityAgent"],
  },
  { label: "Phase 3 — Validation",               agents: ["ValidationAgent"] },
  { label: "Phase 4 — Recommendations & Score",  agents: ["RecommendationAgent","ScoringAgent"] },
  { label: "Phase 5 — Report Generation",        agents: ["ReportAgent"] },
];

function fmt(ms: number | null): string {
  if (!ms) return "";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

interface Props {
  agents:    Record<string, AgentState>;
  revisions: RevisionInfo[];
  connected: boolean;
}

export default function ExecutionGraph({ agents, revisions, connected }: Props) {
  const totalAgents = Object.keys(agents).length || 12;
  const completed   = Object.values(agents).filter((a) => a.status === "completed").length;
  const running     = Object.values(agents).filter((a) => a.status === "running").length;
  const failed      = Object.values(agents).filter((a) => a.status === "failed").length;
  const progress    = totalAgents > 0 ? Math.round((completed / totalAgents) * 100) : 0;

  return (
    <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="px-6 py-4 border-b bg-gradient-to-r from-gray-50 to-blue-50 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <h2 className="font-bold text-gray-800 text-base">Live Execution Graph</h2>
          <span className={`flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full font-medium
            ${connected ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-green-500 animate-pulse" : "bg-gray-400"}`}/>
            {connected ? "Live" : "Offline"}
          </span>
          {revisions.length > 0 && (
            <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium">
              🔄 {revisions.length} revision{revisions.length > 1 ? "s" : ""}
            </span>
          )}
        </div>

        {/* Progress bar */}
        <div className="flex items-center gap-3 min-w-[220px]">
          <div className="flex gap-3 text-xs text-gray-500 mr-1">
            {running  > 0 && <span className="text-blue-600  font-medium">{running} running</span>}
            {failed   > 0 && <span className="text-red-600   font-medium">{failed} failed</span>}
            <span>{completed}/{totalAgents} done</span>
          </div>
          <div className="flex-1 bg-gray-200 rounded-full h-2 min-w-[80px]">
            <div
              className="h-2 rounded-full transition-all duration-700"
              style={{
                width: `${progress}%`,
                background: failed > 0 ? "#f87171" : progress === 100 ? "#22c55e" : "#3b82f6",
              }}
            />
          </div>
          <span className={`text-xs font-bold w-9 text-right
            ${progress === 100 ? "text-green-600" : failed > 0 ? "text-red-500" : "text-blue-600"}`}>
            {progress}%
          </span>
        </div>
      </div>

      {/* ── Revision notice banner ──────────────────────────────────────────── */}
      {revisions.map((r) => (
        <div key={r.cycle} className="mx-4 mt-3 flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm">
          <span className="text-amber-500 mt-0.5">🔄</span>
          <div>
            <span className="font-semibold text-amber-800">Revision Cycle {r.cycle}</span>
            <span className="text-amber-600 ml-2">{r.reason}</span>
            {r.checksFailed.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1">
                {r.checksFailed.map((c) => (
                  <span key={c} className="text-xs bg-amber-100 text-amber-700 rounded px-2 py-0.5">{c}</span>
                ))}
              </div>
            )}
          </div>
          {r.validationStatus && (
            <span className={`ml-auto text-xs font-semibold px-2 py-0.5 rounded-full shrink-0
              ${r.validationStatus === "passed" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
              {r.validationStatus === "passed" ? "✓ Passed" : "✗ " + r.validationStatus}
            </span>
          )}
        </div>
      ))}

      {/* ── DAG layers ─────────────────────────────────────────────────────── */}
      <div className="p-6 space-y-2">
        {LAYERS.map((layer, li) => (
          <div key={li}>
            {/* Phase label */}
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">{layer.label}</span>
              {layer.parallel && (
                <span className="text-[10px] text-gray-300 border border-gray-200 rounded px-1.5 py-0.5">runs in parallel</span>
              )}
            </div>

            {/* Agent cards */}
            <div className={`flex flex-wrap gap-2 ${layer.parallel ? "pl-3 border-l-2 border-dashed border-gray-200" : ""}`}>
              {layer.agents.map((agentName) => {
                const a    = agents[agentName];
                const st   = a?.status ?? "pending";
                const meta = AGENT_META[agentName] ?? { label: agentName, icon: "🤖", desc: "" };
                const isRevised = revisions.some((r) => r.agentsRevised.includes(agentName));

                return (
                  <div
                    key={agentName}
                    title={meta.desc}
                    className={`relative flex flex-col gap-0.5 px-3 py-2.5 rounded-xl border text-sm transition-all duration-300 min-w-[130px]
                      ${CARD_STYLE[st]}`}
                  >
                    {/* Revised badge */}
                    {isRevised && (
                      <span className="absolute -top-2 -right-2 text-[10px] bg-amber-400 text-white rounded-full px-1.5 py-0.5 font-bold leading-none">
                        revised
                      </span>
                    )}

                    {/* Status dot + name */}
                    <div className="flex items-center gap-2">
                      <span className="relative flex shrink-0">
                        <span className={`w-2 h-2 rounded-full ${DOT_STYLE[st]}`} />
                        {st === "running" && (
                          <span className="absolute inset-0 rounded-full bg-blue-400 opacity-50 animate-ping" />
                        )}
                      </span>
                      <span className="font-semibold text-xs leading-tight">{meta.icon} {meta.label}</span>
                      {a?.retries > 0 && (
                        <span className="text-[10px] bg-white bg-opacity-70 border border-current rounded px-1">
                          ↻{a.retries}
                        </span>
                      )}
                    </div>

                    {/* Description */}
                    <div className="text-[10px] opacity-60 pl-4 leading-tight">{meta.desc}</div>

                    {/* Metrics row */}
                    {st !== "pending" && (
                      <div className="flex items-center gap-2 pl-4 mt-0.5 flex-wrap">
                        {a?.score != null && a.score > 0 && (
                          <span className="text-[11px] font-bold opacity-90">Score: {a.score}</span>
                        )}
                        {a?.issues_count != null && a.issues_count > 0 && (
                          <span className="text-[10px] bg-white bg-opacity-60 rounded px-1.5 py-0.5">
                            {a.issues_count} issues
                          </span>
                        )}
                        {a?.duration_ms != null && (
                          <span className="text-[10px] opacity-50">{fmt(a.duration_ms)}</span>
                        )}
                      </div>
                    )}

                    {/* Error */}
                    {st === "failed" && a?.error && (
                      <div className="text-[10px] text-red-500 pl-4 leading-tight truncate max-w-[180px]" title={a.error}>
                        {a.error}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Down arrow connector */}
            {li < LAYERS.length - 1 && (
              <div className="flex justify-center my-2 text-gray-300 text-lg select-none">↓</div>
            )}
          </div>
        ))}
      </div>

      {/* ── Legend ─────────────────────────────────────────────────────────── */}
      <div className="px-6 pb-4 flex flex-wrap gap-4 text-[11px] text-gray-400 border-t pt-3 mt-1">
        {[
          { color: "bg-gray-300",  label: "Pending" },
          { color: "bg-blue-500",  label: "Running" },
          { color: "bg-green-500", label: "Completed" },
          { color: "bg-red-500",   label: "Failed" },
        ].map(({ color, label }) => (
          <span key={label} className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${color}`} /> {label}
          </span>
        ))}
        <span className="flex items-center gap-1.5">
          <span className="text-[10px] bg-amber-400 text-white rounded px-1 font-bold">revised</span> Re-run in revision cycle
        </span>
      </div>
    </div>
  );
}
