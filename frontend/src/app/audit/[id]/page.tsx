"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAgentEvents } from "@/hooks/useAgentEvents";
import ExecutionGraph from "@/components/report/ExecutionGraph";
import ExecutionLog   from "@/components/report/ExecutionLog";
import ScoreGauge     from "@/components/report/ScoreGauge";
import IssueTable     from "@/components/report/IssueTable";
import { scoreColor } from "@/lib/utils";
import type { ValidationResult } from "@/types/audit";

const API = "http://localhost:8000/api";

const SECTIONS = [
  { key: "meta",            label: "Meta Tags & Headings",  icon: "🏷️" },
  { key: "links",           label: "Broken Links",          icon: "🔗" },
  { key: "performance",     label: "Performance",           icon: "⚡" },
  { key: "indexability",    label: "Indexability",          icon: "🔍" },
  { key: "structured_data", label: "Structured Data",       icon: "🧩" },
  { key: "security",        label: "Security Headers",      icon: "🔒" },
] as const;

type Tab = "report" | "execution" | "log";

// ── Validation status styling ─────────────────────────────────────────────────
const VS: Record<string, { bg: string; text: string; border: string }> = {
  passed:   { bg: "bg-green-50",  text: "text-green-700",  border: "border-green-200" },
  warnings: { bg: "bg-yellow-50", text: "text-yellow-700", border: "border-yellow-200" },
  failed:   { bg: "bg-red-50",    text: "text-red-700",    border: "border-red-200" },
  skipped:  { bg: "bg-gray-50",   text: "text-gray-500",   border: "border-gray-200" },
};
const CS: Record<string, string> = {
  passed:  "text-green-600 bg-green-50",
  warning: "text-yellow-700 bg-yellow-50",
  failed:  "text-red-600 bg-red-50",
  skipped: "text-gray-500 bg-gray-50",
};

function ValidationCard({ v, open, onToggle }: { v: ValidationResult; open: boolean; onToggle: () => void }) {
  const s = VS[v.status] ?? VS.skipped;
  return (
    <div className={`rounded-xl border ${s.border} ${s.bg} overflow-hidden`}>
      <button onClick={onToggle} className="w-full flex items-center justify-between px-6 py-4 text-left">
        <div className="flex items-center gap-3">
          <span className="text-lg">🛡️</span>
          <span className={`font-semibold text-sm ${s.text}`}>Audit Validation</span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${s.text} border ${s.border}`}>
            {v.status}
          </span>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className={`text-xl font-bold ${s.text}`}>{v.confidence}%</div>
            <div className="text-xs text-gray-400">confidence</div>
          </div>
          <span className="text-gray-400 text-sm">{open ? "▲" : "▼"}</span>
        </div>
      </button>
      {open && (
        <div className="px-6 pb-5 border-t pt-4 space-y-3">
          {v.checks.map((check, i) => (
            <div key={i} className="bg-white rounded-lg border border-gray-100 p-4">
              <div className="flex items-center justify-between mb-1">
                <span className="font-medium text-gray-800 text-sm">{check.name}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full font-semibold capitalize ${CS[check.status] ?? CS.skipped}`}>
                  {check.status}
                </span>
              </div>
              <p className="text-gray-600 text-xs mt-0.5">{check.message}</p>
              {check.details.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {check.details.map((d: Record<string, string>, j) => {
                    const parts = Object.entries(d)
                      .filter(([, v]) => v)
                      .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`);
                    return (
                      <li key={j} className="text-xs text-gray-500 bg-gray-50 rounded px-3 py-1.5 leading-relaxed">
                        {parts.join(" · ")}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function AuditPage() {
  const params  = useParams();
  const router  = useRouter();
  const auditId = params.id as string;

  const [statusData, setStatusData] = useState<Record<string, unknown>>({});
  const [report,     setReport]     = useState<Record<string, unknown> | null>(null);
  const [showVal,    setShowVal]    = useState(false);
  const [activeTab,  setActiveTab]  = useState<Tab>("execution");

  const { agents, revisions, connected } = useAgentEvents(auditId);

  // Poll status every 3s while not completed
  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    const poll = async () => {
      try {
        const r = await fetch(`${API}/audit/${auditId}/status`);
        const d = await r.json();
        setStatusData(d);
        if (d.status === "completed") {
          clearInterval(interval);
          const rr = await fetch(`${API}/audit/${auditId}/report`);
          setReport(await rr.json());
          setActiveTab("report"); // auto-switch to report when done
        }
      } catch { /* ignore */ }
    };
    poll();
    interval = setInterval(poll, 3000);
    return () => clearInterval(interval);
  }, [auditId]);

  const status    = (statusData.status as string) ?? "queued";
  const isRunning = status === "running" || status === "queued";

  // Compute total audit duration (seconds)
  const totalDurationS = (() => {
    if (!statusData.started_at || !statusData.completed_at) return null;
    const s = new Date((statusData.started_at as string).endsWith("Z") ? statusData.started_at as string : statusData.started_at + "Z").getTime();
    const e = new Date((statusData.completed_at as string).endsWith("Z") ? statusData.completed_at as string : statusData.completed_at + "Z").getTime();
    return (e - s) / 1000;
  })();

  // ── Tab definitions ────────────────────────────────────────────────────────
  const tabs: { id: Tab; label: string; icon: string; badge?: string }[] = [
    { id: "execution", label: "Live Graph",     icon: "🔄", badge: isRunning ? "live" : undefined },
    { id: "log",       label: "Execution Log",  icon: "📋" },
    { id: "report",    label: "SEO Report",     icon: "📊", badge: report ? "ready" : undefined },
  ];

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-5">

      {/* ── Breadcrumb ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2 text-sm">
          <a href="/dashboard" className="text-gray-400 hover:text-gray-600 transition">← Dashboard</a>
          <span className="text-gray-200">/</span>
          <span className="text-gray-600 truncate max-w-[300px]">
            {(statusData.url as string) || auditId}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* Status badge */}
          <span className={`text-xs px-3 py-1 rounded-full font-semibold capitalize
            ${status === "completed" ? "bg-green-100 text-green-700"
            : status === "failed"    ? "bg-red-100 text-red-700"
            : status === "running"   ? "bg-blue-100 text-blue-700"
            : "bg-gray-100 text-gray-500"}`}>
            {status === "running" && <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-500 mr-1.5 animate-pulse align-middle" />}
            {status}
          </span>
          {report && (
            <button onClick={() => router.push("/audit/new")}
              className="text-sm px-3 py-1.5 border border-blue-300 text-blue-600 rounded-lg hover:bg-blue-50 transition">
              ↺ New Audit
            </button>
          )}
        </div>
      </div>

      {/* ── In-progress banner ──────────────────────────────────────────────── */}
      {isRunning && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 flex items-center gap-4">
          <div className="w-8 h-8 border-3 border-blue-500 border-t-transparent rounded-full animate-spin shrink-0
            border-[3px]" />
          <div className="flex-1 min-w-0">
            <p className="text-blue-800 font-semibold text-sm">Audit in progress</p>
            <p className="text-blue-500 text-xs mt-0.5 flex flex-wrap gap-3">
              {statusData.pages_crawled
                ? <span>🕷️ {String(statusData.pages_crawled)} pages crawled</span>
                : null}
              {statusData.current_agent
                ? <span className="bg-blue-100 text-blue-700 px-2 py-0.5 rounded font-medium">
                    ▶ {String(statusData.current_agent)}
                  </span>
                : null}
              {revisions.length > 0
                ? <span className="bg-amber-100 text-amber-700 px-2 py-0.5 rounded font-medium">
                    🔄 Revision cycle {revisions.length}
                  </span>
                : null}
            </p>
          </div>
        </div>
      )}

      {/* ── Failed banner ───────────────────────────────────────────────────── */}
      {status === "failed" && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-5">
          <p className="text-red-700 font-semibold">❌ Audit Failed</p>
          <p className="text-red-500 text-sm mt-1">
            {String(statusData.error_message ?? "An unexpected error occurred.")}
          </p>
        </div>
      )}

      {/* ── Report header (when done) ────────────────────────────────────────── */}
      {report && (
        <div className="bg-white rounded-xl shadow-sm border p-6 flex items-center gap-6 flex-wrap">
          <ScoreGauge score={report.overall_score as number} />
          <div className="flex-1 min-w-0">
            <h1 className="text-xl font-bold text-gray-900 truncate">{String(report.url)}</h1>
            <p className="text-xs text-gray-400 mt-1">
              Completed: {report.completed_at ? new Date(report.completed_at as string).toLocaleString() : "—"}
              {totalDurationS != null && (
                <span className="ml-3 text-gray-500">· {totalDurationS.toFixed(1)}s total</span>
              )}
              {(statusData.revision_cycles as number) > 0 && (
                <span className="ml-3 bg-amber-50 text-amber-600 px-2 py-0.5 rounded font-medium">
                  🔄 {String(statusData.revision_cycles)} revision{(statusData.revision_cycles as number) > 1 ? "s" : ""}
                </span>
              )}
            </p>
            <div className="flex flex-wrap gap-2 mt-3">
              {(["critical","warnings","info"] as const).map((k) => (
                <span key={k} className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold
                  ${k==="critical" ? "bg-red-50 text-red-700"
                  : k==="warnings" ? "bg-yellow-50 text-yellow-700"
                  : "bg-blue-50 text-blue-700"}`}>
                  <span className={`w-1.5 h-1.5 rounded-full inline-block
                    ${k==="critical"?"bg-red-500":k==="warnings"?"bg-yellow-400":"bg-blue-400"}`}/>
                  {String((report.summary as Record<string,number>)[k])}{" "}
                  {k.charAt(0).toUpperCase()+k.slice(1)}
                </span>
              ))}
            </div>
          </div>
          <a href={`${API}/audit/${auditId}/excel`} download
            className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white text-sm rounded-lg font-medium
              hover:bg-green-700 transition shrink-0">
            ⬇ Excel Report
          </a>
        </div>
      )}

      {/* ── Tab navigation ──────────────────────────────────────────────────── */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl w-fit">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all
              ${activeTab === tab.id
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"}`}
          >
            <span>{tab.icon}</span>
            <span>{tab.label}</span>
            {tab.badge === "live" && (
              <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
            )}
            {tab.badge === "ready" && (
              <span className="text-[10px] bg-green-100 text-green-700 px-1.5 py-0.5 rounded-full font-semibold">ready</span>
            )}
          </button>
        ))}
      </div>

      {/* ══ Tab: Live Execution Graph ════════════════════════════════════════ */}
      {activeTab === "execution" && (
        <ExecutionGraph agents={agents} revisions={revisions} connected={connected} />
      )}

      {/* ══ Tab: Execution Log ═══════════════════════════════════════════════ */}
      {activeTab === "log" && (
        <ExecutionLog
          auditId={auditId}
          pagesCount={statusData.pages_crawled as number}
          totalDurationS={totalDurationS}
          finalScore={report ? report.overall_score as number : null}
          isRunning={isRunning}
        />
      )}

      {/* ══ Tab: SEO Report ══════════════════════════════════════════════════ */}
      {activeTab === "report" && (
        <>
          {!report ? (
            <div className="bg-white rounded-xl border p-10 text-center text-gray-400">
              <div className="text-4xl mb-3">📊</div>
              <p className="font-medium">Report will appear here when the audit completes.</p>
            </div>
          ) : (
            <div className="space-y-5">
              {/* Validation card */}
              {!!report.validation_status && (
                <ValidationCard
                  v={{
                    status:     report.validation_status as string,
                    confidence: (report.confidence_score as number) ?? 0,
                    checks:     (report.validation_checks as ValidationResult["checks"]) ?? [],
                  } as ValidationResult}
                  open={showVal}
                  onToggle={() => setShowVal(!showVal)}
                />
              )}

              {/* Score grid */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {SECTIONS.map(({ key, label, icon }) => {
                  const sec = (report.sections as Record<string, { score: number | null }>)[key];
                  return (
                    <div key={key} className="bg-white border rounded-xl p-4 text-center shadow-sm hover:shadow-md transition">
                      <div className="text-2xl mb-1">{icon}</div>
                      <div className={`text-2xl font-bold ${scoreColor(sec?.score ?? null)}`}>
                        {sec?.score ?? "—"}
                      </div>
                      <div className="text-xs text-gray-500 mt-0.5 leading-tight">{label}</div>
                    </div>
                  );
                })}
              </div>

              {/* Section cards */}
              {SECTIONS.map(({ key, label, icon }) => {
                const sec = (report.sections as Record<string, { score: number | null; issues: unknown[] }>)[key];
                if (!sec) return null;
                return (
                  <div key={key} className="bg-white rounded-xl shadow-sm border overflow-hidden">
                    <div className="flex items-center justify-between px-6 py-4 border-b bg-gray-50">
                      <h2 className="font-semibold text-gray-800 flex items-center gap-2">
                        <span>{icon}</span>{label}
                      </h2>
                      <span className={`text-xl font-bold ${scoreColor(sec.score)}`}>
                        {sec.score ?? "—"}
                        <span className="text-sm text-gray-400 font-normal">/100</span>
                      </span>
                    </div>
                    <div className="p-6">
                      {sec.issues.length === 0 ? (
                        <p className="text-green-600 text-sm font-medium flex items-center gap-2">
                          <span>✓</span> No issues found!
                        </p>
                      ) : (
                        <IssueTable issues={sec.issues as Parameters<typeof IssueTable>[0]["issues"]} />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
