"""PerformanceAgent — page weight, TTFB, scripts, lazy loading."""

from bs4 import BeautifulSoup
from agents.base_agent import BaseAgent, AgentResult


def _trunc(text: str, n: int = 80) -> str:
    return text if len(text) <= n else text[:n] + "…"


class PerformanceAgent(BaseAgent):
    name = "PerformanceAgent"
    dependencies = ["CrawlAgent"]

    async def run(self) -> AgentResult:
        await self._started()
        try:
            all_issues, all_scores = [], []

            for page in [p for p in self.ctx.pages if p.get("html")]:
                soup    = BeautifulSoup(page["html"], "lxml")
                url     = page["url"]
                issues  = []
                score   = 100
                size_kb = page.get("page_size_bytes", 0) / 1024
                ttfb    = page.get("crawl_duration_ms", 0)
                scripts = soup.find_all("script", src=True)
                images  = soup.find_all("img")
                unlazy  = [img for img in images if not img.get("loading")]

                # ── Page size ─────────────────────────────────────────────────
                if size_kb > 500:
                    issues.append({
                        "type": "page_too_large", "severity": "warning",
                        "title": f"Page size {size_kb:.0f} KB (exceeds 500 KB)",
                        "description": f"Large pages increase load time for users on slow connections. Page: {url} is {size_kb:.0f} KB.",
                        "section": "HTTP Response",
                        "element": "Page payload",
                        "current_value": f"{size_kb:.0f} KB",
                        "fix": "Compress images with WebP/AVIF, minify CSS/JS, enable Gzip or Brotli compression, and remove unused code.",
                        "before": f"Page size: {size_kb:.0f} KB  (uncompressed, large images/scripts)",
                        "after": "Page size: < 500 KB\nSteps:\n• Convert images to WebP (saves 25–35%)\n• Enable Brotli/Gzip on server\n• Minify CSS and JS bundles\n• Remove unused CSS with PurgeCSS",
                    })
                    score -= 15

                # ── TTFB ──────────────────────────────────────────────────────
                if ttfb > 3000:
                    issues.append({
                        "type": "slow_ttfb", "severity": "critical",
                        "title": f"Very slow TTFB: {ttfb} ms",
                        "description": f"Time to First Byte of {ttfb} ms is well above Google's 800 ms threshold. This directly harms Core Web Vitals.",
                        "section": "HTTP Response",
                        "element": "Server response time",
                        "current_value": f"{ttfb} ms TTFB",
                        "fix": "Upgrade server/hosting tier, add a CDN (Cloudflare/Fastly), enable server-side caching (Redis/Varnish), and optimise database queries.",
                        "before": f"TTFB: {ttfb} ms  ← critical (Google threshold: 800 ms)",
                        "after": "TTFB: < 800 ms\nSteps:\n• Enable full-page caching (Redis/Varnish)\n• Use a CDN (Cloudflare)\n• Optimise slow DB queries\n• Consider server-side rendering or static generation",
                    })
                    score -= 25
                elif ttfb > 1500:
                    issues.append({
                        "type": "moderate_ttfb", "severity": "warning",
                        "title": f"Slow TTFB: {ttfb} ms",
                        "description": f"TTFB of {ttfb} ms exceeds the 800 ms target. Slow server response hurts LCP and overall ranking.",
                        "section": "HTTP Response",
                        "element": "Server response time",
                        "current_value": f"{ttfb} ms TTFB",
                        "fix": "Add server-side caching, optimise database queries, and consider a CDN for static assets.",
                        "before": f"TTFB: {ttfb} ms  ← above 800 ms target",
                        "after": "TTFB: < 800 ms\nSteps:\n• Add Cache-Control headers to static assets\n• Enable page-level caching\n• Use CDN for assets",
                    })
                    score -= 10

                # ── Render-blocking scripts ───────────────────────────────────
                if len(scripts) > 10:
                    script_srcs = [_trunc(s.get("src", "inline"), 70) for s in scripts[:6]]
                    issues.append({
                        "type": "too_many_scripts", "severity": "warning",
                        "title": f"{len(scripts)} render-blocking <script> tags",
                        "description": f"Scripts loaded without async/defer block HTML parsing and delay page render. Found {len(scripts)} <script src=...> tags.",
                        "section": "<head> and <body>",
                        "element": f"<script src=...> × {len(scripts)}",
                        "current_value": "\n".join(script_srcs) + (f"\n… and {len(scripts)-6} more" if len(scripts) > 6 else ""),
                        "fix": "Add defer or async attribute to non-critical scripts. Move analytics/chat scripts to load after DOMContentLoaded.",
                        "before": f'<script src="{script_srcs[0] if script_srcs else "..."}"></script>  ← blocks rendering',
                        "after": f'<script defer src="{script_srcs[0] if script_srcs else "..."}"></script>  ← non-blocking\n'
                                 f'<script async src="analytics.js"></script>  ← for independent scripts',
                    })
                    score -= 10

                # ── Lazy loading ──────────────────────────────────────────────
                if unlazy:
                    unlazy_srcs = [_trunc(img.get("src") or img.get("data-src") or "(no src)", 70) for img in unlazy[:5]]
                    issues.append({
                        "type": "lazy_load_missing", "severity": "info",
                        "title": f"{len(unlazy)} image(s) missing loading='lazy'",
                        "description": f"{len(unlazy)} <img> tags lack the loading='lazy' attribute. Below-the-fold images should be lazy-loaded to improve LCP.",
                        "section": "<body>",
                        "element": f"<img> × {len(unlazy)} without loading='lazy'",
                        "current_value": "\n".join(unlazy_srcs) + (f"\n… and {len(unlazy)-5} more" if len(unlazy) > 5 else ""),
                        "fix": f"Add loading='lazy' to all below-the-fold images. Keep loading='eager' on the largest above-the-fold image (LCP candidate).",
                        "before": f'<img src="{unlazy_srcs[0] if unlazy_srcs else "..."}">',
                        "after": f'<img src="{unlazy_srcs[0] if unlazy_srcs else "..."}" loading="lazy" alt="Descriptive alt text">\n'
                                 f'<!-- Apply to all {len(unlazy)} images except the hero/LCP image -->',
                    })
                    score -= 5

                all_scores.append(max(score, 0))
                for issue in issues:
                    self.ctx.store.add_issue(self.ctx.audit_id, self.name, issue, url)
                    self.ctx.store.add_recommendation(self.ctx.audit_id, self.name, {
                        "issue_type": issue["type"],
                        "page_url":   url,
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
            return AgentResult(agent_name=self.name, success=True, score=avg, issues_count=len(all_issues))
        except Exception as exc:
            await self._failed(str(exc))
            return AgentResult(agent_name=self.name, success=False, error=str(exc))
