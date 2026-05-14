"""IndexabilityAgent — robots.txt, sitemap.xml, noindex detection."""

import httpx
from bs4 import BeautifulSoup

from agents.base_agent import BaseAgent, AgentResult
from config import settings


class IndexabilityAgent(BaseAgent):
    name = "IndexabilityAgent"
    dependencies = ["CrawlAgent"]

    async def run(self) -> AgentResult:
        await self._started()
        base   = self.ctx.base_url.rstrip("/")
        issues: list[dict] = []
        score  = 100

        try:
            async with httpx.AsyncClient(timeout=settings.CRAWL_TIMEOUT_SECONDS,
                                          follow_redirects=True,
                                          headers={"User-Agent": "SEOAuditBot/1.0"}) as client:

                # ── robots.txt ────────────────────────────────────────────────
                robots_found, disallowed = False, []
                robots_url = f"{base}/robots.txt"
                try:
                    r = await client.get(robots_url)
                    if r.status_code == 200:
                        robots_found = True
                        for line in r.text.splitlines():
                            if line.lower().startswith("disallow:"):
                                path = line.split(":", 1)[1].strip()
                                if path:
                                    disallowed.append(path)
                        has_sitemap_directive = any(
                            line.lower().startswith("sitemap:") for line in r.text.splitlines()
                        )
                        if not has_sitemap_directive:
                            issues.append({
                                "type": "robots_missing_sitemap_directive", "severity": "info",
                                "title": "robots.txt has no Sitemap directive",
                                "description": "Adding a Sitemap directive in robots.txt helps search engines discover your sitemap automatically.",
                                "section": "/robots.txt",
                                "element": "Sitemap: directive",
                                "current_value": "(no Sitemap: line found in robots.txt)",
                                "fix": "Add a Sitemap: directive pointing to your sitemap URL.",
                                "before": f"# Current robots.txt has no Sitemap directive",
                                "after": f"Sitemap: {base}/sitemap.xml\n\nUser-agent: *\nDisallow:",
                            })
                            score -= 5
                    else:
                        issues.append({
                            "type": "no_robots_txt", "severity": "warning",
                            "title": "robots.txt not found",
                            "description": f"GET {robots_url} returned HTTP {r.status_code}. Without robots.txt, search engines have no crawl guidance and cannot discover your sitemap via this file.",
                            "section": "/robots.txt",
                            "element": "/robots.txt file",
                            "current_value": f"HTTP {r.status_code} — file missing",
                            "fix": "Create a /robots.txt file at the root of your domain.",
                            "before": f"GET {robots_url}  →  HTTP {r.status_code} (file not found)",
                            "after": (
                                f"GET {robots_url}  →  HTTP 200\n\n"
                                f"File content:\n"
                                f"User-agent: *\n"
                                f"Disallow:\n"
                                f"Sitemap: {base}/sitemap.xml"
                            ),
                        })
                        score -= 10
                except Exception:
                    score -= 5

                # ── sitemap.xml ───────────────────────────────────────────────
                sitemap_found, sitemap_count = False, 0
                sitemap_url = f"{base}/sitemap.xml"
                try:
                    s = await client.get(sitemap_url)
                    if s.status_code == 200:
                        sitemap_found = True
                        sitemap_count = s.text.count("<url>")
                        if sitemap_count == 0:
                            issues.append({
                                "type": "empty_sitemap", "severity": "warning",
                                "title": "sitemap.xml found but contains no <url> entries",
                                "description": f"sitemap.xml at {sitemap_url} exists but has no <url> elements.",
                                "section": "/sitemap.xml",
                                "element": "<url> entries",
                                "current_value": "0 <url> entries found",
                                "fix": "Populate sitemap.xml with all canonical, indexable URLs on your site.",
                                "before": "<?xml version=\"1.0\"?><urlset></urlset>  ← empty",
                                "after": (
                                    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                                    "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n"
                                    f"  <url><loc>{base}/</loc><changefreq>weekly</changefreq><priority>1.0</priority></url>\n"
                                    f"  <url><loc>{base}/about</loc><changefreq>monthly</changefreq><priority>0.8</priority></url>\n"
                                    "  …\n"
                                    "</urlset>"
                                ),
                            })
                            score -= 10
                    else:
                        issues.append({
                            "type": "no_sitemap", "severity": "warning",
                            "title": "sitemap.xml not found",
                            "description": f"GET {sitemap_url} returned HTTP {s.status_code}. A sitemap helps search engines discover all your pages efficiently.",
                            "section": "/sitemap.xml",
                            "element": "/sitemap.xml file",
                            "current_value": f"HTTP {s.status_code} — sitemap missing",
                            "fix": "Generate and submit a sitemap.xml. Submit it to Google Search Console via the Sitemaps report.",
                            "before": f"GET {sitemap_url}  →  HTTP {s.status_code}",
                            "after": (
                                f"GET {sitemap_url}  →  HTTP 200\n\n"
                                "Use a sitemap generator:\n"
                                "• WordPress: Yoast SEO / Rank Math auto-generates sitemaps\n"
                                "• Next.js: add next-sitemap package\n"
                                "• Static: use screaming frog or xml-sitemaps.com\n"
                                "Then submit at: https://search.google.com/search-console → Sitemaps"
                            ),
                        })
                        score -= 15
                except Exception:
                    score -= 5

            # ── noindex pages ──────────────────────────────────────────────────
            noindex_pages: list[str] = []
            for page in self.ctx.pages:
                html = page.get("html", "")
                if not html:
                    continue
                soup = BeautifulSoup(html, "lxml")
                m    = soup.find("meta", attrs={"name": "robots"})
                if m and "noindex" in m.get("content", "").lower():
                    noindex_pages.append(page["url"])

            if noindex_pages:
                examples = "\n".join(noindex_pages[:5])
                issues.append({
                    "type": "noindex_pages", "severity": "info",
                    "title": f"{len(noindex_pages)} page(s) have noindex meta tag",
                    "description": f"These pages are blocked from search engine indexing. If intentional, ignore. If not, remove the noindex tag.\nPages:\n{examples}",
                    "section": "<head> — meta robots",
                    "element": '<meta name="robots" content="noindex">',
                    "current_value": examples + ("\n…" if len(noindex_pages) > 5 else ""),
                    "fix": "If these pages should be indexed, remove the noindex directive. If intentional (e.g., thank-you pages, admin areas), no action needed.",
                    "before": '<meta name="robots" content="noindex, nofollow">  ← blocks indexing',
                    "after": (
                        "Option 1 (index the page):\n"
                        '<meta name="robots" content="index, follow">\n\n'
                        "Option 2 (remove tag entirely — defaults to index, follow):\n"
                        "(remove the <meta name=\"robots\"> tag)"
                    ),
                })

            score = max(score, 0)
            for issue in issues:
                self.ctx.store.add_issue(self.ctx.audit_id, self.name, issue, self.ctx.base_url)
                self.ctx.store.add_recommendation(self.ctx.audit_id, self.name, {
                    "issue_type": issue["type"],
                    "page_url":   self.ctx.base_url,
                    "priority":   "high" if issue["severity"] == "critical" else "medium" if issue["severity"] == "warning" else "low",
                    "action":     issue["fix"],
                    "section":    issue.get("section", ""),
                    "element":    issue.get("element", ""),
                    "before":     issue.get("before", ""),
                    "after":      issue.get("after", ""),
                })

            await self._completed(score, len(issues))
            return AgentResult(agent_name=self.name, success=True, score=score, issues_count=len(issues),
                               data={"robots_txt_found": robots_found, "sitemap_found": sitemap_found,
                                     "sitemap_url_count": sitemap_count, "noindex_pages": noindex_pages})
        except Exception as exc:
            await self._failed(str(exc))
            return AgentResult(agent_name=self.name, success=False, error=str(exc))
