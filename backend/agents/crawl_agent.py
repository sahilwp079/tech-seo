"""CrawlAgent — Phase 1 · BFS page discovery with per-page HTTP retry."""

import time
from collections import deque
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from agents.base_agent import BaseAgent, AgentContext, AgentResult
from config import settings
from tools import tool_registry
from utils.retry import http_retry, RetryError


class CrawlAgent(BaseAgent):
    name = "CrawlAgent"
    dependencies: list[str] = []
    max_retries = 2   # DAG-level agent retry (rarely needed for crawl)

    async def run(self) -> AgentResult:
        await self._started()
        base          = self.ctx.base_url.rstrip("/")
        allowed_netloc = urlparse(base).netloc
        visited: set[str]                  = set()
        queue:   deque[tuple[str, int]]    = deque([(base, 0)])
        pages:   list[dict]                = []

        try:
            async with httpx.AsyncClient(
                timeout=settings.CRAWL_TIMEOUT_SECONDS,
                follow_redirects=True,
                headers={"User-Agent": "SEOAuditBot/1.0"},
            ) as client:
                while queue and len(pages) < self.ctx.max_pages:
                    url, depth = queue.popleft()
                    if url in visited:
                        continue
                    visited.add(url)

                    page = await self._fetch_page(client, url, depth)
                    pages.append(page)
                    self.ctx.store.add_page(self.ctx.audit_id, page)

                    html = page.get("html", "")
                    if html and depth < 5:
                        soup = BeautifulSoup(html, "lxml")
                        for a in soup.find_all("a", href=True):
                            href = urljoin(url, a["href"]).split("#")[0]
                            p = urlparse(href)
                            if p.netloc == allowed_netloc and href not in visited:
                                queue.append((href, depth + 1))

            self.ctx.pages.extend(pages)
            self.ctx.store.update_audit(
                self.ctx.audit_id, pages_crawled=len(pages), current_agent="CrawlAgent"
            )
            await self._emit("agent.progress", {"pages_crawled": len(pages)})
            await self._completed(score=None, issues_count=0)

            failed  = [p["url"] for p in pages if p.get("error")]
            depths  = [p.get("depth", 0) for p in pages]
            result  = AgentResult(
                agent_name=self.name, success=True, issues_count=0,
                data={
                    "pages_crawled":     len(pages),
                    "urls_discovered":   [p["url"] for p in pages],
                    "failed_urls":       failed,
                    "max_depth_reached": max(depths) if depths else 0,
                },
            )
            return self._validate_contract(result)

        except Exception as exc:
            await self._failed(str(exc))
            return AgentResult(agent_name=self.name, success=False, error=str(exc))

    async def _fetch_page(self, client: httpx.AsyncClient, url: str, depth: int) -> dict:
        """Fetch a single page via the tool_registry (fetch_page tool with retry)."""
        result = await tool_registry.invoke("fetch_page", {"url": url})
        if result.success:
            return {**result.data, "depth": depth}
        return {
            "url": url, "status_code": None, "html": "", "depth": depth,
            "error": result.error, "page_size_bytes": 0, "crawl_duration_ms": result.duration_ms,
            "content_type": "", "response_headers": {},
        }
