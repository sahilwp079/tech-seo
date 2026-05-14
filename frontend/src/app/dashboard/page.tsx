"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { scoreColor } from "@/lib/utils";

const API = "http://localhost:8000/api";

interface AuditItem {
  audit_id: string;
  url: string;
  status: string;
  overall_score: number | null;
  pages_crawled: number;
  validation_status: string;
  created_at: string;
  completed_at: string;
}

const STATUS_STYLES: Record<string, string> = {
  completed: "bg-green-100 text-green-700",
  running:   "bg-blue-100 text-blue-700 animate-pulse",
  failed:    "bg-red-100 text-red-700",
  queued:    "bg-gray-100 text-gray-600",
};

const VAL_STYLES: Record<string, string> = {
  passed:   "bg-green-50 text-green-700",
  warnings: "bg-yellow-50 text-yellow-700",
  failed:   "bg-red-50 text-red-700",
};

export default function DashboardPage() {
  const [audits,  setAudits]  = useState<AuditItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState("");
  const [tab,     setTab]     = useState<string>("all");

  const fetchAudits = async () => {
    try {
      const r = await fetch(`${API}/audit/list`);
      if (!r.ok) throw new Error("Failed to load");
      const d = await r.json();
      setAudits(d.audits ?? []);
    } catch {
      setError("Failed to load audits. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAudits(); }, []);

  const filtered = tab === "all" ? audits : audits.filter((a) => a.status === tab);

  return (
    <div className="max-w-5xl mx-auto p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Audit Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">{audits.length} audit{audits.length !== 1 ? "s" : ""} total</p>
        </div>
        <Link href="/audit/new"
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700 transition">
          + New Audit
        </Link>
      </div>

      {/* Status tabs */}
      <div className="flex gap-1 mb-6 border-b">
        {(["all","completed","running","failed","queued"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition -mb-px capitalize ${
              tab === t ? "border-blue-600 text-blue-600" : "border-transparent text-gray-500 hover:text-gray-800"
            }`}>
            {t}
          </button>
        ))}
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-gray-500 py-8 justify-center">
          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          Loading audits...
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-600 text-sm">{error}</div>
      )}

      {!loading && !error && (
        <div className="space-y-3">
          {filtered.length === 0 && (
            <div className="text-center py-16 text-gray-400">
              <p className="text-5xl mb-4">📋</p>
              <p className="text-lg font-medium text-gray-600">No audits yet</p>
              <p className="text-sm mt-1">Start your first audit to see results here.</p>
              <Link href="/audit/new" className="text-blue-600 hover:underline mt-3 inline-block text-sm font-medium">
                Start your first audit →
              </Link>
            </div>
          )}

          {filtered.map((audit) => (
            <div key={audit.audit_id}
              className="bg-white rounded-xl shadow-sm border p-5 flex items-center gap-4 hover:shadow-md transition">
              {/* Score circle */}
              <div className="w-14 h-14 rounded-full border-4 border-gray-100 flex items-center justify-center shrink-0">
                <span className={`text-lg font-bold ${scoreColor(audit.overall_score ?? null)}`}>
                  {audit.overall_score ?? "—"}
                </span>
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-gray-900 truncate">{audit.url}</p>
                <p className="text-xs text-gray-400 mt-0.5 font-mono">{audit.audit_id}</p>
                <p className="text-xs text-gray-400 mt-0.5">
                  {new Date(audit.created_at).toLocaleString()}
                  {audit.pages_crawled > 0 && (
                    <span className="ml-2 text-gray-500">· {audit.pages_crawled} pages</span>
                  )}
                </p>
              </div>

              {/* Badges + actions */}
              <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
                <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${STATUS_STYLES[audit.status] ?? "bg-gray-100 text-gray-600"}`}>
                  {audit.status}
                </span>
                {audit.validation_status && (
                  <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${VAL_STYLES[audit.validation_status] ?? "bg-gray-100 text-gray-500"}`}>
                    {audit.validation_status}
                  </span>
                )}
                <Link href={`/audit/${audit.audit_id}`}
                  className="text-sm text-blue-600 font-medium hover:underline whitespace-nowrap">
                  {audit.status === "completed" ? "View Report →" : "View Progress →"}
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
