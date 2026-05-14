"use client";
import { useState } from "react";
import { severityColor } from "@/lib/utils";

interface IssueRow {
  severity:      "critical" | "warning" | "info";
  title:         string;
  description?:  string | null;
  page_url?:     string | null;
  section?:      string | null;
  element?:      string | null;
  current_value?: string | null;
  fix?:          string | null;
  before?:       string | null;
  after?:        string | null;
  issue_type?:   string;
}

interface Props {
  issues: IssueRow[];
}

const SEV_ORDER = { critical: 0, warning: 1, info: 2 };
const SEVERITIES = ["critical", "warning", "info"] as const;

function CodeBlock({ label, code }: { label: string; code: string }) {
  return (
    <div className="mt-2">
      <p className="text-xs font-semibold text-gray-500 mb-1 uppercase tracking-wide">{label}</p>
      <pre className="bg-gray-900 text-green-300 rounded-lg px-4 py-3 text-xs overflow-x-auto whitespace-pre-wrap leading-relaxed">
        {code}
      </pre>
    </div>
  );
}

function IssueCard({ issue, index, expanded, onToggle }: {
  issue: IssueRow;
  index: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  const sev = issue.severity;
  const borderColor = sev === "critical" ? "border-red-300" : sev === "warning" ? "border-yellow-300" : "border-blue-200";
  const bgColor     = sev === "critical" ? "bg-red-50"      : sev === "warning" ? "bg-yellow-50"      : "bg-blue-50";

  return (
    <div className={`border rounded-xl overflow-hidden ${expanded ? borderColor : "border-gray-200"}`}>
      {/* Header row */}
      <button
        className={`w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-gray-50 transition ${expanded ? bgColor : ""}`}
        onClick={onToggle}
      >
        <span className={`mt-0.5 shrink-0 px-2 py-0.5 rounded text-xs font-bold uppercase ${severityColor(sev)}`}>
          {sev}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-900 leading-snug">{issue.title}</p>
          {issue.page_url && !expanded && (
            <p className="text-xs text-gray-400 mt-0.5 truncate">{issue.page_url}</p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {issue.section && (
            <span className="hidden sm:inline text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">
              {issue.section}
            </span>
          )}
          <span className="text-gray-400 text-xs">{expanded ? "▲" : "▼"}</span>
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="px-5 pb-5 pt-3 border-t border-gray-100 space-y-4 bg-white">

          {/* Metadata grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {issue.page_url && (
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Page URL</p>
                <a href={issue.page_url} target="_blank" rel="noreferrer"
                   className="text-xs text-blue-600 hover:underline break-all">
                  {issue.page_url}
                </a>
              </div>
            )}
            {issue.section && (
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Affected Section</p>
                <code className="text-xs text-purple-700 font-mono">{issue.section}</code>
              </div>
            )}
            {issue.element && (
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Element / Component</p>
                <code className="text-xs text-orange-700 font-mono break-all">{issue.element}</code>
              </div>
            )}
            {issue.current_value && (
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Current Value</p>
                <pre className="text-xs text-red-700 font-mono whitespace-pre-wrap break-all">{issue.current_value}</pre>
              </div>
            )}
          </div>

          {/* Description */}
          {issue.description && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Issue Detail</p>
              <p className="text-sm text-gray-700 leading-relaxed">{issue.description}</p>
            </div>
          )}

          {/* Fix */}
          {issue.fix && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-3">
              <p className="text-xs font-semibold text-green-700 uppercase tracking-wide mb-1">Recommended Fix</p>
              <p className="text-sm text-green-800 leading-relaxed">{issue.fix}</p>
            </div>
          )}

          {/* Before / After */}
          {(issue.before || issue.after) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {issue.before && <CodeBlock label="Before (current state)" code={issue.before} />}
              {issue.after  && <CodeBlock label="After (target state)"   code={issue.after}  />}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function IssueTable({ issues }: Props) {
  const [filter,   setFilter]   = useState<"all" | "critical" | "warning" | "info">("all");
  const [expanded, setExpanded] = useState<number | null>(null);

  const sorted   = [...issues].sort((a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity]);
  const filtered = filter === "all" ? sorted : sorted.filter((i) => i.severity === filter);

  const counts = issues.reduce((acc, i) => {
    acc[i.severity] = (acc[i.severity] ?? 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div>
      {/* Filter bar */}
      <div className="flex flex-wrap gap-2 mb-4">
        <button onClick={() => setFilter("all")}
          className={`px-3 py-1 rounded-full text-xs font-semibold border transition ${
            filter === "all" ? "bg-gray-800 text-white border-gray-800" : "border-gray-200 text-gray-600 hover:border-gray-400"
          }`}>
          All ({issues.length})
        </button>
        {SEVERITIES.map((sev) => (
          counts[sev] ? (
            <button key={sev} onClick={() => setFilter(sev)}
              className={`px-3 py-1 rounded-full text-xs font-semibold border transition capitalize ${
                filter === sev ? severityColor(sev) + " border-current" : "border-gray-200 text-gray-600 hover:border-gray-400"
              }`}>
              {sev} ({counts[sev]})
            </button>
          ) : null
        ))}
      </div>

      {/* Issue cards */}
      <div className="space-y-2">
        {filtered.length === 0 && (
          <p className="text-sm text-gray-400 py-4 text-center">No {filter === "all" ? "" : filter} issues found.</p>
        )}
        {filtered.map((issue, idx) => (
          <IssueCard
            key={idx}
            issue={issue}
            index={idx}
            expanded={expanded === idx}
            onToggle={() => setExpanded(expanded === idx ? null : idx)}
          />
        ))}
      </div>
    </div>
  );
}
