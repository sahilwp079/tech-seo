"""LinkAnalysisAgent — HEAD-checks every href for broken links."""

import asyncio
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from agents.base_agent import BaseAgent, AgentResult
from config import settings
from tools import tool_registry

_CONCURRENCY = 20


class LinkAnalysisAgent(BaseAgent):
    name = "LinkAnalysisAgent"
    dependencies = ["CrawlAgent"]

    async def run(self) -> AgentResult:
        await self._started()
        try:
            all_issues, all_scores = [], []
            html_pages = [p for p in self.ctx.pages if p.get("html")]

            async with httpx.AsyncClient(
                timeout=settings.CRAWL_TIMEOUT_SECONDS, follow_redirects=True,
                headers={"User-Agent": "SEOAuditBot/1.0"},
                limits=httpx.Limits(max_connections=_CONCURRENCY, max_keepalive_connections=10),
            ) as client:
                sem = asyncio.Semaphore(_CONCURRENCY)

                for page in html_pages:
                    soup  = BeautifulSoup(page["html"], "lxml")
                    links = {}  # href → anchor text

                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if not href or href.startswith("mailto:") or href.startswith("tel:") or href.startswith("#"):
                            continue
                        full = urljoin(page["url"], href).split("#")[0]
                        links[full] = a.get_text(strip=True)[:80] or "(no anchor text)"

                    tasks   = [self._check(client, url, sem) for url in links]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    broken: list[dict] = []
                    for href, res in zip(links, results):
                        code = None if isinstance(res, Exception) else res
                        if code and code >= 400:
                            broken.append({"url": href, "status_code": code, "anchor": links[href]})

                    score = max(0, 100 - len(broken) * 10)
                    all_scores.append(score)

                    for b in broken:
                        severity = "critical" if b["status_code"] >= 400 else "warning"
                        is_internal = urlparse(b["url"]).netloc == urlparse(page["url"]).netloc

                        issue = {
                            "type": "broken_link",
                            "severity": severity,
                            "title": f"Broken link → {b['url']}",
                            "description": (
                                f"The link \"{b['anchor']}\" on this page returns HTTP {b['status_code']}. "
                                f"{'Internal' if is_internal else 'External'} broken links waste crawl budget and harm user experience."
                            ),
                            "section": "<body>",
                            "element": f'<a href="{b["url"]}">{b["anchor"]}</a>',
                            "current_value": f"HTTP {b['status_code']} — {'Not Found' if b['status_code'] == 404 else 'Server Error' if b['status_code'] >= 500 else 'Error'}",
                            "fix": (
                                f"{'Fix or redirect this internal link.' if is_internal else 'Remove or replace this external link.'} "
                                f"Use a 301 redirect if the URL has permanently moved."
                            ),
                            "before": f'<a href="{b["url"]}">{b["anchor"]}</a>  →  HTTP {b["status_code"]}',
                            "after": (
                                f"Option 1: <a href=\"correct-url\">{b['anchor']}</a>  ← update to correct URL\n"
                                f"Option 2: Set up 301 redirect from {b['url']} → correct destination\n"
                                f"Option 3: Remove the link if the destination no longer exists"
                            ),
                        }
                        self.ctx.store.add_issue(self.ctx.audit_id, self.name, issue, page["url"])
                        self.ctx.store.add_recommendation(self.ctx.audit_id, self.name, {
                            "issue_type": "broken_link",
                            "page_url":   page["url"],
                            "priority":   "high",
                            "action":     issue["fix"],
                            "section":    "<body>",
                            "element":    issue["element"],
                            "before":     issue["before"],
                            "after":      issue["after"],
                        })
                        all_issues.append(issue)

                    # ── Anchor text issues ─────────────────────────────────────
                    generic_anchors = [
                        (href, anchor) for href, anchor in links.items()
                        if anchor.lower() in {"click here", "read more", "here", "link", "this", "more"}
                    ]
                    if len(generic_anchors) >= 3:
                        examples = "; ".join(f'"{a}" → {h[:50]}' for h, a in generic_anchors[:3])
                        issue = {
                            "type": "generic_anchor_text",
                            "severity": "info",
                            "title": f"{len(generic_anchors)} links use generic anchor text",
                            "description": f"Generic anchors like 'click here' or 'read more' miss keyword opportunities. Examples: {examples}",
                            "section": "<body>",
                            "element": f"<a> with generic anchor text × {len(generic_anchors)}",
                            "current_value": examples,
                            "fix": "Replace generic anchor text with descriptive keywords that describe the linked page's topic.",
                            "before": '<a href="/services">Click here</a>',
                            "after": '<a href="/services">View Our SEO Services</a>  ← descriptive keyword anchor',
                        }
                        self.ctx.store.add_issue(self.ctx.audit_id, self.name, issue, page["url"])
                        self.ctx.store.add_recommendation(self.ctx.audit_id, self.name, {
                            "issue_type": "generic_anchor_text",
                            "page_url":   page["url"],
                            "priority":   "low",
                            "action":     issue["fix"],
                            "section":    "<body>",
                            "element":    issue["element"],
                            "before":     issue["before"],
                            "after":      issue["after"],
                        })
                        all_issues.append(issue)

            avg = int(sum(all_scores) / len(all_scores)) if all_scores else 100
            await self._completed(avg, len(all_issues))
            return AgentResult(agent_name=self.name, success=True, score=avg,
                               issues_count=len(all_issues), data={"pages_checked": len(html_pages)})
        except Exception as exc:
            await self._failed(str(exc))
            return AgentResult(agent_name=self.name, success=False, error=str(exc))

    async def _check(self, client: httpx.AsyncClient, url: str, sem: asyncio.Semaphore) -> int | None:
        async with sem:
            result = await tool_registry.invoke("check_url", {"url": url})
            return result.data.get("status_code") if result.success else None
