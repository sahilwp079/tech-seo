"""MetaAnalysisAgent — title, description, H1–H6, canonical, OG tags."""

from bs4 import BeautifulSoup
from agents.base_agent import BaseAgent, AgentResult


def _trunc(text: str, n: int = 80) -> str:
    return text if len(text) <= n else text[:n] + "…"


def _analyse_page(page: dict) -> tuple[list[dict], int]:
    html = page.get("html", "")
    url  = page.get("url", "")
    if not html:
        return [], 100

    soup   = BeautifulSoup(html, "lxml")
    issues = []
    score  = 100

    # ── Title ──────────────────────────────────────────────────────────────────
    title_tag = soup.find("title")
    title     = title_tag.get_text(strip=True) if title_tag else ""

    if not title:
        issues.append({
            "type": "missing_title", "severity": "critical",
            "title": "Missing <title> tag",
            "description": "Every page must have a unique <title> tag in <head>. Search engines display it as the clickable headline in results.",
            "section": "<head>",
            "element": "<title>",
            "current_value": "(no <title> tag found)",
            "fix": "Add a <title> tag inside <head> with 50–60 characters that includes your primary keyword near the start.",
            "before": "(no <title> tag present in <head>)",
            "after": "<title>Primary Keyword – Page Name | Brand</title>",
        })
        score -= 25
    elif len(title) > 60:
        issues.append({
            "type": "title_too_long", "severity": "warning",
            "title": f"Title too long ({len(title)} chars)",
            "description": f"Search engines truncate titles beyond ~60 characters. Current title: \"{_trunc(title)}\"",
            "section": "<head>",
            "element": "<title>",
            "current_value": f"{title}  ({len(title)} chars)",
            "fix": f"Shorten the title to under 60 characters while keeping the primary keyword.",
            "before": f"<title>{title}</title>  ← {len(title)} chars",
            "after": f"<title>{title[:57].rstrip()}…</title>  ← target 50–60 chars",
        })
        score -= 10
    elif len(title) < 30:
        issues.append({
            "type": "title_too_short", "severity": "warning",
            "title": f"Title too short ({len(title)} chars)",
            "description": f"Titles shorter than 30 characters don't use the available SEO space. Current: \"{title}\"",
            "section": "<head>",
            "element": "<title>",
            "current_value": f"{title}  ({len(title)} chars)",
            "fix": "Expand the title to 50–60 characters. Include the primary keyword and brand name.",
            "before": f"<title>{title}</title>",
            "after": f"<title>{title} – More Descriptive Title | Brand</title>",
        })
        score -= 5

    # ── Meta description ───────────────────────────────────────────────────────
    desc_tag    = soup.find("meta", attrs={"name": "description"})
    description = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else ""

    if not description:
        issues.append({
            "type": "missing_description", "severity": "warning",
            "title": "Missing meta description",
            "description": "A meta description is shown as the page snippet in search results. Missing descriptions reduce click-through rate.",
            "section": "<head>",
            "element": '<meta name="description">',
            "current_value": "(no meta description found)",
            "fix": "Add a meta description of 120–160 characters with a clear call-to-action and target keyword.",
            "before": "(no <meta name=\"description\"> tag)",
            "after": '<meta name="description" content="Concise description (120–160 chars) with primary keyword and a clear CTA.">',
        })
        score -= 15
    elif len(description) > 160:
        issues.append({
            "type": "description_too_long", "severity": "info",
            "title": f"Meta description too long ({len(description)} chars)",
            "description": f"Search engines truncate descriptions beyond 160 characters. Current: \"{_trunc(description)}\"",
            "section": "<head>",
            "element": '<meta name="description">',
            "current_value": f"{description}  ({len(description)} chars)",
            "fix": "Trim the meta description to under 160 characters.",
            "before": f'<meta name="description" content="{_trunc(description, 120)}…">  ← {len(description)} chars',
            "after": f'<meta name="description" content="{description[:157].rstrip()}…">  ← target 120–160 chars',
        })
        score -= 5

    # ── Canonical ──────────────────────────────────────────────────────────────
    canonical_tag = soup.find("link", rel="canonical")
    canonical     = canonical_tag["href"] if canonical_tag and canonical_tag.get("href") else ""

    if not canonical:
        issues.append({
            "type": "missing_canonical", "severity": "warning",
            "title": "Missing canonical tag",
            "description": "Without a canonical tag, search engines may index multiple URL variants (with/without trailing slash, query params) as separate pages, causing duplicate content.",
            "section": "<head>",
            "element": '<link rel="canonical">',
            "current_value": "(no canonical tag found)",
            "fix": "Add a canonical tag pointing to the preferred URL for this page.",
            "before": "(no <link rel=\"canonical\"> in <head>)",
            "after": f'<link rel="canonical" href="{url}">',
        })
        score -= 10

    # ── Open Graph ─────────────────────────────────────────────────────────────
    og_title = soup.find("meta", property="og:title")
    og_desc  = soup.find("meta", property="og:description")
    og_image = soup.find("meta", property="og:image")
    og_missing = [tag for tag, el in [("og:title", og_title), ("og:description", og_desc), ("og:image", og_image)] if not el]

    if og_missing:
        issues.append({
            "type": "missing_og_title", "severity": "info",
            "title": f"Missing Open Graph tags: {', '.join(og_missing)}",
            "description": "Open Graph tags control how pages appear when shared on Facebook, LinkedIn, and other platforms.",
            "section": "<head>",
            "element": f"<meta property=\"{og_missing[0]}\">",
            "current_value": f"Missing: {', '.join(og_missing)}",
            "fix": "Add all required Open Graph tags inside <head>.",
            "before": f"(missing {', '.join(og_missing)})",
            "after": '\n'.join([
                '<meta property="og:title" content="Page Title Here">',
                '<meta property="og:description" content="Description 120–160 chars">',
                '<meta property="og:image" content="https://example.com/og-image.jpg">  ← min 1200×630px',
                f'<meta property="og:url" content="{url}">',
            ]),
        })
        score -= 5

    # ── H1 ─────────────────────────────────────────────────────────────────────
    h1s = [h.get_text(strip=True) for h in soup.find_all("h1")]

    if not h1s:
        issues.append({
            "type": "missing_h1", "severity": "critical",
            "title": "Missing H1 tag",
            "description": "Every page should have exactly one H1 tag that describes its main topic. It is one of the strongest on-page SEO signals.",
            "section": "<body>",
            "element": "<h1>",
            "current_value": "(no H1 tag found on page)",
            "fix": "Add one H1 tag near the top of the page content containing the primary keyword.",
            "before": "(no <h1> tag in page body)",
            "after": "<h1>Primary Keyword – Main Page Topic</h1>",
        })
        score -= 20
    elif len(h1s) > 1:
        issues.append({
            "type": "multiple_h1", "severity": "warning",
            "title": f"Multiple H1 tags ({len(h1s)} found)",
            "description": f"Only one H1 is expected per page. Found H1s: {'; '.join(_trunc(h, 50) for h in h1s[:4])}",
            "section": "<body>",
            "element": f"<h1> × {len(h1s)}",
            "current_value": " | ".join(_trunc(h, 40) for h in h1s[:3]),
            "fix": f"Keep only the most important H1 and demote the others to H2 or H3.",
            "before": "\n".join(f"<h1>{_trunc(h, 60)}</h1>" for h in h1s[:3]) + ("\n…" if len(h1s) > 3 else ""),
            "after": f"<h1>{_trunc(h1s[0], 60)}</h1>  ← keep this one\n" + "\n".join(f"<h2>{_trunc(h, 60)}</h2>  ← demote to H2" for h in h1s[1:3]),
        })
        score -= 10

    # ── H2 structure ───────────────────────────────────────────────────────────
    h2s = [h.get_text(strip=True) for h in soup.find_all("h2")]
    if h1s and not h2s:
        issues.append({
            "type": "no_h2_tags", "severity": "info",
            "title": "No H2 tags found",
            "description": "H2 tags structure page content into sections, improving both user experience and crawler understanding.",
            "section": "<body>",
            "element": "<h2>",
            "current_value": "(no H2 tags found)",
            "fix": "Divide main content into logical sections using H2 tags with relevant keywords.",
            "before": "(no H2 heading structure)",
            "after": "<h2>Section Topic with Keyword</h2>\n<p>Section content…</p>\n<h2>Another Key Topic</h2>",
        })
        score -= 5

    return issues, max(score, 0)


class MetaAnalysisAgent(BaseAgent):
    name = "MetaAnalysisAgent"
    dependencies = ["CrawlAgent"]

    async def run(self) -> AgentResult:
        await self._started()
        try:
            all_issues, all_scores = [], []
            html_pages = [p for p in self.ctx.pages if p.get("html")]

            for page in html_pages:
                issues, score = _analyse_page(page)
                all_scores.append(score)
                for issue in issues:
                    self.ctx.store.add_issue(self.ctx.audit_id, self.name, issue, page["url"])
                    self.ctx.store.add_recommendation(self.ctx.audit_id, self.name, {
                        "issue_type": issue["type"],
                        "page_url":   page["url"],
                        "priority":   "high" if issue["severity"] == "critical" else "medium" if issue["severity"] == "warning" else "low",
                        "action":     issue["fix"],
                        "section":    issue.get("section", ""),
                        "element":    issue.get("element", ""),
                        "before":     issue.get("before", ""),
                        "after":      issue.get("after", ""),
                    })
                all_issues.extend(issues)

            avg = int(sum(all_scores) / len(all_scores)) if all_scores else 100
            await self._completed(avg, len(all_issues))
            return AgentResult(agent_name=self.name, success=True, score=avg,
                               issues_count=len(all_issues), data={"pages_analysed": len(html_pages)})
        except Exception as exc:
            await self._failed(str(exc))
            return AgentResult(agent_name=self.name, success=False, error=str(exc))
