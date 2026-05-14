# SEO Audit Agent — AI-Native Multi-Agent Platform

A full-stack Technical SEO Audit platform powered by **12 autonomous AI agents** running in a parallel DAG pipeline. Submit any website URL and receive a detailed, actionable SEO report with page-level diagnostics, before/after code fixes, a live execution graph, Excel export, and AI-generated summaries — all in real time.

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Live Demo Features](#live-demo-features)
3. [Architecture Overview](#architecture-overview)
4. [The 12 Agents](#the-12-agents)
5. [How Agents Communicate](#how-agents-communicate)
6. [ChromaDB — Primary Database](#chromadb--primary-database)
7. [Issue & Recommendation Detail Schema](#issue--recommendation-detail-schema)
8. [Validation System](#validation-system)
9. [Scoring System](#scoring-system)
10. [Excel Report](#excel-report)
11. [API Reference](#api-reference)
12. [Frontend Pages](#frontend-pages)
13. [How to Run](#how-to-run)
14. [Environment Variables](#environment-variables)
15. [Project Structure](#project-structure)

---

## What It Does

1. You enter a website URL (e.g. `https://example.com`) and choose how many pages to crawl (1–200).
2. The platform launches **12 autonomous agents** that crawl the site and run analysis in parallel.
3. You watch agents execute live in a 6-phase dependency graph streamed over **WebSocket**.
4. When complete, you get:
   - An overall SEO score (0–100)
   - Per-section scores (Meta, Links, Performance, Indexability, Structured Data, Security)
   - Every issue with its **exact page URL, HTML section, element, current value, and copy-paste before/after code fix**
   - A validation quality report with confidence score
   - A downloadable Excel workbook
   - A Groq AI-generated plain-English summary

---

## Live Demo Features

### Real-Time Execution Graph
While the audit runs, a 6-phase graph updates live over WebSocket:

```
Phase 0 — Planning         [Planner Agent ✓]
      ↓
Phase 1 — Discovery        [Crawl Agent ✓]
      ↓
Phase 2 — Parallel Analysis
  [Indexability ✓]  [MetaAnalysis ✓]  [LinkAnalysis ✓]
  [Performance ✓]   [StructuredData ✓] [Security ✓]
      ↓
Phase 3 — Validation       [Validation Agent ✓]
      ↓
Phase 4 — Scoring & Recs   [Recommendation ✓]  [Scoring ✓]
      ↓
Phase 5 — Report           [Report Agent ✓]
```

Each node shows: status colour (gray/blue-pulse/green/red), score, and issue count.

### Detailed Issue Cards (Expandable)
Every issue expands to show:

| Field | Description |
|---|---|
| **Page URL** | Exact page where the issue was found (clickable link) |
| **Affected Section** | `<head>`, `<body>`, `HTTP Response Headers`, `/robots.txt` |
| **Element / Component** | The specific tag: `<title>`, `<img src="..."> × 12`, `Strict-Transport-Security` |
| **Current Value** | What is actually there right now |
| **Issue Detail** | Full technical explanation |
| **Recommended Fix** | Specific actionable instruction |
| **Before** | Dark code block showing the current broken state |
| **After** | Dark code block showing the exact target state |

---

## Architecture Overview

```
┌────────────────────────────────────────────────────┐
│                   Next.js Frontend                  │
│  Dashboard · New Audit · [id] Report Page           │
│  ExecutionGraph · IssueTable · ScoreGauge           │
└──────────────┬────────────────────────┬────────────┘
               │ REST (fetch)           │ WebSocket
               ▼                        ▼
┌────────────────────────────────────────────────────┐
│                  FastAPI Backend                    │
│                                                    │
│  POST /audit/start ──► BackgroundTask              │
│                              │                     │
│                    MasterOrchestratorAgent          │
│                              │                     │
│                    EventBus (async pub/sub)         │
│                              │                     │
│                    DAG Executor                     │
│               (resolves deps, asyncio.gather)       │
│                              │                     │
│              12 Autonomous Agents                   │
└──────────────┬───────────────────────┬─────────────┘
               │                       │
               ▼                       ▼
┌──────────────────────┐   ┌──────────────────────────┐
│    ChromaDB           │   │    Groq API               │
│  (6 collections)      │   │  llama-3.1-8b-instant     │
│  Primary database     │   │  - Validation sanity check│
│  Vector embeddings    │   │  - Rec action plans       │
│  Knowledge base       │   │  - AI audit summary       │
└──────────────────────┘   └──────────────────────────┘
```

---

## The 12 Agents

### Phase 0 — Planning

#### `PlannerAgent`
- Reads `ALL_AGENT_CLASSES` and builds the execution DAG
- Emits a `plan.ready` WebSocket event containing the full dependency graph
- Frontend uses this event to render all 12 agent nodes (all pending) instantly
- Marks itself as **completed** the moment `plan.ready` is emitted

---

### Phase 1 — Discovery

#### `CrawlAgent`
- BFS crawl starting from the base URL, respects `max_pages` cap
- Fetches HTML and response headers for every page
- Stores crawled pages in ChromaDB (`pages` collection)
- Populates `ctx.pages` — the shared in-memory list used by all Phase 2 agents
- Collects: URL, status code, page size, TTFB (crawl_duration_ms), depth, content type

---

### Phase 2 — Parallel Analysis (all 6 run simultaneously)

#### `IndexabilityAgent`
Checks site-level indexability signals:
- **robots.txt** — exists? Has a `Sitemap:` directive?
- **sitemap.xml** — exists? Has `<url>` entries? Is it empty?
- **noindex meta tags** — which pages are blocked from indexing?

Issues generated: `no_robots_txt`, `robots_missing_sitemap_directive`, `no_sitemap`, `empty_sitemap`, `noindex_pages`

---

#### `MetaAnalysisAgent`
Parses every HTML page's `<head>` and `<body>`:
- `<title>` — missing / too long (>60 chars) / too short (<30 chars)
- `<meta name="description">` — missing / too long (>160 chars)
- `<link rel="canonical">` — missing
- Open Graph tags — which of `og:title`, `og:description`, `og:image` are missing
- `<h1>` — missing / multiple found
- `<h2>` — no H2 structure at all

For every issue it captures the **actual title text**, **actual description text**, and generates a copy-paste `<before>` / `<after>` code snippet.

---

#### `LinkAnalysisAgent`
- Extracts every `<a href>` on every crawled page
- HEAD-checks each URL (20 concurrent, falls back to GET on failure)
- Flags HTTP 4xx/5xx broken links with: the broken URL, the anchor text, the status code
- Detects pages with 3+ generic anchors (`"click here"`, `"read more"`, `"here"`)
- Issues: `broken_link`, `generic_anchor_text`

---

#### `PerformanceAgent`
Analyses page weight and load performance from crawl data:
- **Page size** — flags pages >500 KB
- **TTFB** — critical if >3000 ms, warning if >1500 ms
- **Render-blocking scripts** — flags pages with >10 `<script src>` tags without async/defer
- **Lazy loading** — flags `<img>` tags without `loading="lazy"`

Lists the actual script `src` values and image `src` values in the issue element field.

---

#### `StructuredDataAgent`
Parses every `<script type="application/ld+json">` block:
- **Missing JSON-LD** — no structured data at all
- **Invalid JSON-LD** — JSON parse errors (blocks all schema benefits)
- **Missing OG tags** — which of `og:title`, `og:description`, `og:image`, `og:url` are absent
- **Missing Twitter Card** — no `<meta name="twitter:card">`

Provides complete ready-to-paste JSON-LD and OG tag templates in the `after` field.

---

#### `SecurityAgent`
Checks HTTP response headers on every page:
- **No HTTPS** — page served over HTTP
- **Missing HSTS** — `Strict-Transport-Security` absent
- **Missing X-Frame-Options** — clickjacking risk (unless CSP `frame-ancestors` present)
- **Missing X-Content-Type-Options: nosniff** — MIME-sniffing risk
- **Missing Referrer-Policy** — leaks full URLs to third-parties
- **Missing Content-Security-Policy** — XSS attack surface

Each issue includes the exact server config line for Nginx and Apache in the `after` field.

---

### Phase 3 — Validation

#### `ValidationAgent`
Runs 4 quality checks after all analysis agents complete:

| Check | Logic | Confidence Penalty |
|---|---|---|
| **Agent Completeness** | Did all 6 analysis agents complete without failure? | −25 (missing) / −10 (failed) |
| **Score Consistency** | Does any agent score contradict its detected issues? (e.g. score 95 with `missing_title`) | −20 (failed) / −10 (warning) |
| **Cross-Agent Logic** | Any contradictions across agents? (e.g. HTTPS URL but `no_https` flag) | −15 (failed) / −8 (warning) |
| **LLM Sanity Review** | Groq reads top 5 critical issues and flags anything implausible | −5 (warning) |

- Output: `validation_status` (passed / warnings / failed) and `confidence_score` (0–100)
- The full `checks` array is serialised as JSON and stored in the audit record → served via API → rendered in the frontend ValidationCard with expandable details

---

### Phase 4 — Scoring & Recommendations (parallel)

#### `RecommendationAgent`
- Deduplicates recommendations by `(issue_type, page_url)` — keeps highest priority
- Groups all recommendations by page URL
- For pages with high-priority issues, calls Groq to generate a concise, developer-focused **action plan** (4–6 bullet points specifying exactly what file/tag/config to change)
- Enriches top 5 high-priority recs with knowledge base context

#### `ScoringAgent`
Reads all agent scores from `workflow_memory` and computes a weighted average:

| Agent | Weight |
|---|---|
| MetaAnalysisAgent | 20% |
| PerformanceAgent | 20% |
| LinkAnalysisAgent | 15% |
| IndexabilityAgent | 15% |
| StructuredDataAgent | 10% |
| SecurityAgent | 10% |

Stores `overall_score` in the audit record and sets `status = "completed"`.

---

### Phase 5 — Report

#### `ReportAgent`
- Builds a 4-sheet Excel workbook (see [Excel Report](#excel-report))
- Calls Groq to generate a 3-sentence plain-English audit summary for non-technical stakeholders
- Sets `audit.status = "completed"` and emits `audit.completed` WebSocket event
- Saves Excel to `reports/audit_{id}_report.xlsx`

---

## How Agents Communicate

Every agent extends `BaseAgent` and receives a shared `AgentContext`:

```python
@dataclass
class AgentContext:
    audit_id:     str          # UUID
    base_url:     str          # https://example.com
    max_pages:    int          # 1–200
    event_bus:    EventBus     # async pub/sub
    store:        module       # chroma_store module ref
    pages:        list[dict]   # populated by CrawlAgent, shared in-memory
    groq_api_key: str
```

The **EventBus** is an async pub/sub system. The `WebSocket ConnectionManager` subscribes to all events and broadcasts them as JSON to every browser watching that audit:

```
Agent._emit("agent.completed", {score: 93, issues_count: 7})
    │
    ▼
EventBus.publish(AgentEvent)
    │
    ▼
ConnectionManager.event_handler()
    │
    ▼
WebSocket.send_json({event, agent, timestamp, score, issues_count, ...})
    │
    ▼
useAgentEvents.ts → setAgents() → ExecutionGraph re-renders
```

---

## ChromaDB — Primary Database

No MySQL. ChromaDB is the only database. It is file-based and persists to `./chroma_data/`.

| Collection | One document per | Key metadata fields |
|---|---|---|
| `audits` | Audit run | audit_id, url, status, overall_score, validation_status, confidence_score, validation_checks (JSON string), pages_crawled, started_at, completed_at |
| `pages` | Crawled page | url, status_code, page_size_bytes, crawl_duration_ms, depth |
| `issues` | SEO issue found | agent_name, page_url, issue_type, severity, title, description, section, element, current_value, fix, before, after |
| `recommendations` | Fix recommendation | agent_name, page_url, issue_type, priority, action, section, element, before, after |
| `workflow_memory` | Agent lifecycle event | agent_name, event_type, score, issues_count, timestamp |
| `seo_knowledge` | Knowledge article | topic, title, content (embedded for semantic search) |

> **Rules:** All metadata must be `str | int | float | bool` — no `None`, no lists. Use `""` for empty strings, `-1` for null integers. Updates use `upsert()` by document ID.

---

## Issue & Recommendation Detail Schema

Every single issue stored contains seven context fields so developers can act immediately:

```
Issue: "Title too long (87 chars)"

page_url:      https://example.com/about-us
section:       <head>
element:       <title>
current_value: Buy Cheap Widgets Online Now - Best Prices Guaranteed!  (87 chars)
fix:           Shorten the title to under 60 characters while keeping the primary keyword.
before:        <title>Buy Cheap Widgets Online Now - Best Prices Guaranteed!</title>  ← 87 chars
after:         <title>Cheap Widgets – Best Prices | Brand</title>  ← target 50–60 chars
```

```
Issue: "Missing X-Frame-Options"

page_url:      https://example.com/
section:       HTTP Response Headers
element:       X-Frame-Options
current_value: (header not present)
fix:           Add X-Frame-Options: SAMEORIGIN to prevent clickjacking.
before:        (X-Frame-Options header missing)
after:         X-Frame-Options: SAMEORIGIN
               Nginx:  add_header X-Frame-Options SAMEORIGIN always;
               Apache: Header always append X-Frame-Options SAMEORIGIN
```

---

## Validation System

The `ValidationCard` in the frontend shows all 4 check results:

```
🛡️ Audit Validation    [warnings]                    85%  ▼
                                                   confidence
─────────────────────────────────────────────────────────────
 Agent Completeness      [passed]   All 6 agents completed
 Score Consistency       [warning]  1 inconsistency
                                    · score consistency: MetaAnalysisAgent
                                      score 93 > max 80 with missing_title present
 Cross-Agent Logic       [passed]   No contradictions found
 LLM Sanity Review       [passed]   PASS — All findings appear valid.
```

---

## Scoring System

Scores are computed per-page by each analysis agent, averaged across all crawled pages, then combined with weights by `ScoringAgent`:

```
Overall Score = (
  MetaScore × 0.20 +
  PerfScore  × 0.20 +
  LinkScore  × 0.15 +
  IndexScore × 0.15 +
  SchemaScore× 0.10 +
  SecScore   × 0.10
) / total_weight × 100
```

Score colour thresholds: ≥80 = green, ≥50 = yellow, <50 = red.

---

## Excel Report

Downloaded via `GET /api/audit/{id}/excel`. Four sheets:

### Sheet 1 — Summary
Overall score, issue counts by severity (Critical / Warning / Info), site URL, audit timestamp.

### Sheet 2 — Issues Found
Columns: Severity · Agent · Title · Page URL · Section · Element · Current Value · Description · Fix

Sorted: Critical → Warning → Info. Severity cells are colour-coded (red / orange / blue).

### Sheet 3 — Recommendations
Columns: Priority · Agent · Page URL · Section · Element · Action · Before · After

Sorted: High → Medium → Low → grouped by page. Priority cells colour-coded (red / orange / green).

### Sheet 4 — Execution Log
Columns: Agent · Event · Status · Score · Issues Count · Timestamp

Full chronological agent lifecycle from PlannerAgent to ReportAgent.

---

## API Reference

### Start Audit
```
POST /api/audit/start
Body: { "url": "https://example.com", "max_pages": 50 }
Response 202: { "audit_id": "uuid-string", "status": "queued", "url": "..." }
```

### Poll Status
```
GET /api/audit/{id}/status
Response: {
  "audit_id", "status", "overall_score", "pages_crawled",
  "current_agent", "validation_status", "confidence_score",
  "started_at", "completed_at", "error_message"
}
```

### Get Full Report
```
GET /api/audit/{id}/report
Response: {
  "audit_id", "url", "status", "overall_score",
  "validation_status", "confidence_score",
  "validation_checks": [                          ← all 4 check results
    { "name", "status", "message", "details": [...] }
  ],
  "summary": { "total_issues", "critical", "warnings", "info" },
  "sections": {
    "meta":            { "score", "issues": [ {page_url, section, element, current_value, fix, before, after, ...} ] },
    "links":           { ... },
    "performance":     { ... },
    "indexability":    { ... },
    "structured_data": { ... },
    "security":        { ... }
  },
  "recommendations": [ { page_url, priority, action, section, element, before, after, ... } ],
  "workflow_log":     [ { agent_name, event_type, score, timestamp, ... } ]
}
```

### Other Endpoints
```
GET  /api/audit/{id}/excel          → Download .xlsx file
GET  /api/audit/{id}/workflow-log   → Agent execution log
GET  /api/audit/{id}/similar-issues?query=...&n=5  → Semantic search
GET  /api/audit/list                → All audits, newest first
GET  /api/audit/knowledge/search?q=...  → SEO knowledge base search
DELETE /api/audit/{id}              → Soft-delete audit
WS   /api/ws/audit/{id}            → Real-time event stream
```

### WebSocket Events
```json
// plan.ready — initialise the execution graph
{ "event": "plan.ready", "agent": "PlannerAgent", "plan": [
  { "agent": "CrawlAgent", "dependencies": [], "status": "pending" },
  ...
]}

// agent lifecycle
{ "event": "agent.started",    "agent": "MetaAnalysisAgent", "timestamp": "..." }
{ "event": "agent.completed",  "agent": "MetaAnalysisAgent", "score": 93, "issues_count": 7 }
{ "event": "agent.failed",     "agent": "LinkAnalysisAgent", "error": "..." }

// audit done
{ "event": "audit.completed", "overall_score": 78, "issues_count": 42 }
```

---

## Frontend Pages

### `/` — Landing Page
Introduction and "Start Audit" CTA.

### `/dashboard` — Audit Dashboard
- Lists all past audits (newest first)
- Shows: URL, UUID audit ID, overall score circle, status badge, validation badge
- Filter tabs: All / Completed / Running / Failed / Queued
- Click any row to view progress or the full report

### `/audit/new` — New Audit Form
- URL input field
- Max Pages slider (1–200)
- Info grid showing all 12 agents with their phase and description
- Submits → redirects to `/audit/{id}`

### `/audit/[id]` — Live Report Page

**While running:**
- Live Execution Graph (6 phases, 12 nodes updating in real time)
- In-progress banner with current agent name and pages crawled

**When completed:**
- Execution Graph (toggleable)
- Score header: Radial gauge + URL + issue summary badges
- Download Excel button
- 🛡️ Validation Card (expandable, shows all 4 checks with details)
- Score Grid: 6 section scores in coloured tiles
- 6 Section Cards: each with an IssueTable
  - Filter bar: All / Critical / Warning / Info with counts
  - Each issue is an expandable card showing the full diagnostic detail
  - Before/After shown in dark code blocks side by side

---

## How to Run

### Prerequisites
- Python 3.12+
- Node.js 18+
- A Groq API key (free at [console.groq.com](https://console.groq.com))

### 1. Backend

```powershell
cd seo-audit-agent/backend

# Install dependencies
pip install -r requirements.txt

# Create .env file
copy .env.example .env
# Edit .env and add your GROQ_API_KEY

# Start server
python -m uvicorn main:app --reload --port 8000
```

On first startup, ChromaDB initialises all 6 collections and seeds the 12-article SEO knowledge base automatically.

### 2. Frontend

```powershell
cd seo-audit-agent/frontend

npm install
npm run dev
# Open http://localhost:3000
```

### 3. Run an Audit
1. Open `http://localhost:3000/audit/new`
2. Enter a URL (e.g. `https://example.com`)
3. Set max pages (start with 10–20 for a quick test)
4. Click **Start Multi-Agent Audit**
5. Watch the 6-phase execution graph update live
6. When complete, explore the per-section issue cards and download the Excel report

---

## Environment Variables

File: `backend/.env`

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | *(required)* | Your Groq API key for LLM features |
| `CHROMA_DB_PATH` | `./chroma_data` | Where ChromaDB persists data |
| `REPORTS_DIR` | `./reports` | Where Excel files are saved |
| `DEFAULT_MAX_PAGES` | `50` | Default crawl depth if not specified |
| `CRAWL_TIMEOUT_SECONDS` | `10` | Per-request HTTP timeout |

> No database connection string needed — ChromaDB is file-based.

---

## Project Structure

```
seo-audit-agent/
├── backend/
│   ├── main.py                    FastAPI app entry point
│   ├── config.py                  Settings (pydantic-settings)
│   ├── requirements.txt
│   ├── .env / .env.example
│   ├── agents/
│   │   ├── base_agent.py          AgentContext · AgentResult · BaseAgent ABC
│   │   ├── master_orchestrator.py Entry point, run_audit() function
│   │   ├── planner_agent.py       DAG builder, plan.ready emitter
│   │   ├── crawl_agent.py         BFS crawl, populates ctx.pages
│   │   ├── indexability_agent.py  robots.txt · sitemap · noindex
│   │   ├── meta_analysis_agent.py title · desc · H1 · OG · canonical
│   │   ├── link_analysis_agent.py broken links · anchor text
│   │   ├── performance_agent.py   TTFB · size · scripts · lazy-load
│   │   ├── structured_data_agent.py JSON-LD · OG · Twitter Cards
│   │   ├── security_agent.py      HTTPS · HSTS · CSP · X-Frame · nosniff
│   │   ├── validation_agent.py    4 checks + Groq sanity review
│   │   ├── recommendation_agent.py dedup · group by page · Groq action plan
│   │   ├── scoring_agent.py       weighted average overall score
│   │   └── report_agent.py        Excel 4-sheet · Groq AI summary
│   ├── core/
│   │   ├── event_bus.py           Async pub/sub (AgentEvent dataclass)
│   │   ├── connection_manager.py  WebSocket manager + broadcaster
│   │   └── dag_executor.py        Dependency resolver + asyncio.gather runner
│   ├── storage/
│   │   └── chroma_store.py        All ChromaDB CRUD + vector search
│   ├── api/
│   │   ├── router.py
│   │   └── routes/
│   │       ├── audit_routes.py    REST endpoints
│   │       └── ws_routes.py       WebSocket endpoint
│   └── utils/
│       ├── url_utils.py
│       └── logger.py
│
└── frontend/
    └── src/
        ├── app/
        │   ├── page.tsx           Landing
        │   ├── dashboard/page.tsx Audit list
        │   └── audit/
        │       ├── new/page.tsx   Start form
        │       └── [id]/page.tsx  Live graph + completed report
        ├── components/
        │   ├── layout/Navbar.tsx
        │   └── report/
        │       ├── ExecutionGraph.tsx  6-layer live DAG
        │       ├── ScoreGauge.tsx      Radial gauge (recharts)
        │       └── IssueTable.tsx      Expandable cards + before/after
        ├── hooks/
        │   └── useAgentEvents.ts   WebSocket hook → agents state
        ├── lib/
        │   ├── api.ts              Plain fetch wrappers
        │   └── utils.ts            scoreColor · severityColor · cn()
        └── types/audit.ts          All TypeScript interfaces
```

---

## Key Design Decisions

**Why ChromaDB instead of MySQL?**
ChromaDB serves dual purpose: structured storage (via metadata) and vector similarity search (via embeddings). This enables semantic search across past audit issues (`/similar-issues`) and the SEO knowledge base (`/knowledge/search`) without a separate vector database.

**Why a DAG executor instead of sequential phases?**
Phases 2 and 4 contain agents with no inter-dependencies. The DAG executor uses `asyncio.wait(FIRST_COMPLETED)` to unlock the next ready agent the moment its dependencies finish — maximising parallelism and minimising total wall-clock time.

**Why WebSocket instead of polling for agent status?**
Polling creates N requests over the audit duration and delivers updates only at the poll interval. WebSocket delivers each agent state change within milliseconds of it happening, enabling the live animated execution graph.

**Why store `before`/`after` in ChromaDB instead of generating at read time?**
Each analysis agent has the page HTML available at analysis time. Generating contextual code snippets (e.g. the actual broken title text, the actual missing image srcs) at analysis time produces accurate, page-specific examples. Regenerating at read time would require re-fetching and re-parsing pages.
