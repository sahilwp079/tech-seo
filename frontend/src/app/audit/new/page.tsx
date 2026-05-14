"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

const API = "http://localhost:8000/api";

const AGENTS = [
  { name: "PlannerAgent",        phase: "Planning",    desc: "Builds execution DAG and schedules all agents" },
  { name: "CrawlAgent",          phase: "Discovery",   desc: "BFS-crawls the site, discovers pages, collects HTML" },
  { name: "IndexabilityAgent",   phase: "Analysis",    desc: "robots.txt, sitemap.xml, noindex tags" },
  { name: "MetaAnalysisAgent",   phase: "Analysis",    desc: "title, description, H1–H6, canonical, OG tags" },
  { name: "LinkAnalysisAgent",   phase: "Analysis",    desc: "HEAD-checks every href for 4xx/5xx broken links" },
  { name: "PerformanceAgent",    phase: "Analysis",    desc: "TTFB, page size, scripts, lazy loading" },
  { name: "StructuredDataAgent", phase: "Analysis",    desc: "JSON-LD validity, OG tags, Twitter Cards" },
  { name: "SecurityAgent",       phase: "Analysis",    desc: "HTTPS, HSTS, CSP, X-Frame-Options" },
  { name: "ValidationAgent",     phase: "Validation",  desc: "4-check quality gate + Groq LLM sanity review" },
  { name: "RecommendationAgent", phase: "Scoring",     desc: "Deduplicates recs, enriches with knowledge base" },
  { name: "ScoringAgent",        phase: "Scoring",     desc: "Weighted overall score across all agents" },
  { name: "ReportAgent",         phase: "Report",      desc: "Excel workbook + AI summary generation" },
];

const PHASE_COL: Record<string, string> = {
  Planning:   "bg-purple-50 text-purple-700",
  Discovery:  "bg-orange-50 text-orange-700",
  Analysis:   "bg-blue-50   text-blue-700",
  Validation: "bg-yellow-50 text-yellow-700",
  Scoring:    "bg-teal-50   text-teal-700",
  Report:     "bg-green-50  text-green-700",
};

export default function NewAuditPage() {
  const router = useRouter();
  const [url,      setUrl]      = useState("");
  const [maxPages, setMaxPages] = useState(50);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!url.trim()) { setError("Please enter a URL."); return; }
    let normalized = url.trim();
    if (!normalized.startsWith("http")) normalized = "https://" + normalized;

    setLoading(true);
    try {
      const res = await fetch(`${API}/audit/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: normalized, max_pages: maxPages }),
      });
      if (!res.ok) throw new Error((await res.json()).detail ?? "Failed to start audit");
      const { audit_id } = await res.json();
      router.push(`/audit/${audit_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start audit.");
      setLoading(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto p-8 space-y-8">
      <div>
        <a href="/dashboard" className="text-gray-400 hover:text-gray-600 text-sm">← Dashboard</a>
        <h1 className="text-3xl font-bold text-gray-900 mt-2">New SEO Audit</h1>
        <p className="text-gray-500 mt-1">12 autonomous agents · parallel execution · ChromaDB vector memory</p>
      </div>

      <div className="bg-white rounded-xl border shadow-sm p-6">
        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Website URL</label>
            <input
              type="text" value={url} onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com"
              className="w-full border rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Max Pages: <span className="text-blue-600 font-bold">{maxPages}</span>
            </label>
            <input type="range" min={1} max={200} value={maxPages}
              onChange={(e) => setMaxPages(Number(e.target.value))}
              className="w-full accent-blue-500" />
            <div className="flex justify-between text-xs text-gray-400 mt-1">
              <span>1 (fast)</span><span>200 (thorough)</span>
            </div>
          </div>

          {error && <p className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-4 py-2">{error}</p>}

          <button type="submit" disabled={loading}
            className="w-full py-3 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition disabled:opacity-50">
            {loading ? "Starting…" : "🚀 Start Multi-Agent Audit"}
          </button>
        </form>
      </div>

      <div>
        <h2 className="text-lg font-semibold text-gray-800 mb-4">12 Autonomous Agents</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {AGENTS.map((a) => (
            <div key={a.name} className="bg-white border rounded-lg px-4 py-3 flex items-start gap-3">
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium shrink-0 mt-0.5 ${PHASE_COL[a.phase] ?? "bg-gray-100 text-gray-600"}`}>
                {a.phase}
              </span>
              <div>
                <p className="text-sm font-semibold text-gray-800">{a.name}</p>
                <p className="text-xs text-gray-500">{a.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
