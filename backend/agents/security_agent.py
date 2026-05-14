"""SecurityAgent — HTTPS, HSTS, CSP, X-Frame-Options, security headers."""

from urllib.parse import urlparse
from agents.base_agent import BaseAgent, AgentResult


class SecurityAgent(BaseAgent):
    name = "SecurityAgent"
    dependencies = ["CrawlAgent"]

    async def run(self) -> AgentResult:
        await self._started()
        try:
            all_issues, all_scores = [], []

            for page in [p for p in self.ctx.pages if p.get("html")]:
                headers   = {k.lower(): v for k, v in page.get("response_headers", {}).items()}
                url       = page["url"]
                issues    = []
                score     = 100
                is_https  = urlparse(url).scheme == "https"

                # ── HTTPS ──────────────────────────────────────────────────────
                if not is_https:
                    issues.append({
                        "type": "no_https", "severity": "critical",
                        "title": "Page served over HTTP (not HTTPS)",
                        "description": "HTTPS is a confirmed Google ranking signal. HTTP pages are flagged as 'Not Secure' in Chrome, damaging user trust and conversions.",
                        "section": "HTTP Response",
                        "element": "URL scheme",
                        "current_value": f"http:// (insecure)  →  {url}",
                        "fix": "Install an SSL/TLS certificate (free via Let's Encrypt) and add a 301 redirect from HTTP to HTTPS for all pages.",
                        "before": f"http://{urlparse(url).netloc}{urlparse(url).path}  ← insecure",
                        "after": (
                            f"https://{urlparse(url).netloc}{urlparse(url).path}  ← secure\n"
                            "Server config: Redirect all HTTP → HTTPS with 301\n"
                            "Apache: Redirect permanent / https://yourdomain.com/\n"
                            "Nginx: return 301 https://$host$request_uri;"
                        ),
                    })
                    score -= 40

                # ── HSTS ───────────────────────────────────────────────────────
                if is_https and "strict-transport-security" not in headers:
                    issues.append({
                        "type": "missing_hsts", "severity": "warning",
                        "title": "Missing Strict-Transport-Security (HSTS) header",
                        "description": "Without HSTS, browsers will not automatically upgrade HTTP requests to HTTPS, leaving users vulnerable to protocol downgrade attacks.",
                        "section": "HTTP Response Headers",
                        "element": "Strict-Transport-Security",
                        "current_value": "(header not present in response)",
                        "fix": "Add the HSTS header to your web server configuration.",
                        "before": "(Strict-Transport-Security header missing)",
                        "after": (
                            "Strict-Transport-Security: max-age=31536000; includeSubDomains; preload\n\n"
                            "Nginx:  add_header Strict-Transport-Security \"max-age=31536000; includeSubDomains\" always;\n"
                            "Apache: Header always set Strict-Transport-Security \"max-age=31536000; includeSubDomains\""
                        ),
                    })
                    score -= 15

                # ── X-Frame-Options ────────────────────────────────────────────
                has_xfo = "x-frame-options" in headers
                csp_val = headers.get("content-security-policy", "")
                if not has_xfo and "frame-ancestors" not in csp_val:
                    issues.append({
                        "type": "missing_x_frame_options", "severity": "warning",
                        "title": "Missing X-Frame-Options header",
                        "description": "Without X-Frame-Options, this page can be embedded in iframes on other sites, enabling clickjacking attacks.",
                        "section": "HTTP Response Headers",
                        "element": "X-Frame-Options",
                        "current_value": "(header not present)",
                        "fix": "Add X-Frame-Options: SAMEORIGIN to prevent your page from being framed by other sites.",
                        "before": "(X-Frame-Options header missing)",
                        "after": (
                            "X-Frame-Options: SAMEORIGIN\n\n"
                            "Nginx:  add_header X-Frame-Options SAMEORIGIN always;\n"
                            "Apache: Header always append X-Frame-Options SAMEORIGIN\n"
                            "Modern alt: Content-Security-Policy: frame-ancestors 'self';"
                        ),
                    })
                    score -= 15

                # ── X-Content-Type-Options ────────────────────────────────────
                if headers.get("x-content-type-options", "").lower() != "nosniff":
                    issues.append({
                        "type": "missing_x_content_type_options", "severity": "warning",
                        "title": "Missing X-Content-Type-Options: nosniff",
                        "description": "Without this header, browsers may MIME-sniff a response and execute it as a different content type, enabling content-injection attacks.",
                        "section": "HTTP Response Headers",
                        "element": "X-Content-Type-Options",
                        "current_value": headers.get("x-content-type-options", "(not set)"),
                        "fix": "Add X-Content-Type-Options: nosniff to all responses.",
                        "before": "(X-Content-Type-Options header missing or incorrect)",
                        "after": (
                            "X-Content-Type-Options: nosniff\n\n"
                            "Nginx:  add_header X-Content-Type-Options nosniff always;\n"
                            "Apache: Header always set X-Content-Type-Options nosniff"
                        ),
                    })
                    score -= 10

                # ── Referrer-Policy ───────────────────────────────────────────
                if "referrer-policy" not in headers:
                    issues.append({
                        "type": "missing_referrer_policy", "severity": "info",
                        "title": "Missing Referrer-Policy header",
                        "description": "Without Referrer-Policy, the full URL (including query params and sensitive data) is sent to external sites in the Referer header.",
                        "section": "HTTP Response Headers",
                        "element": "Referrer-Policy",
                        "current_value": "(header not present — browser default applies)",
                        "fix": "Add Referrer-Policy: strict-origin-when-cross-origin to limit referrer data sent to external sites.",
                        "before": "(Referrer-Policy not set — full URL leaked to third-parties)",
                        "after": (
                            "Referrer-Policy: strict-origin-when-cross-origin\n\n"
                            "Nginx:  add_header Referrer-Policy \"strict-origin-when-cross-origin\" always;\n"
                            "Apache: Header always set Referrer-Policy \"strict-origin-when-cross-origin\""
                        ),
                    })
                    score -= 5

                # ── CSP ────────────────────────────────────────────────────────
                if not csp_val:
                    issues.append({
                        "type": "missing_csp", "severity": "info",
                        "title": "No Content-Security-Policy header",
                        "description": "A CSP restricts which resources (scripts, styles, images) the browser may load, preventing XSS and data-injection attacks.",
                        "section": "HTTP Response Headers",
                        "element": "Content-Security-Policy",
                        "current_value": "(header not present)",
                        "fix": "Implement a Content-Security-Policy header. Start with a report-only policy to identify violations before enforcing.",
                        "before": "(Content-Security-Policy header missing)",
                        "after": (
                            "# Start with report-only to test:\n"
                            "Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:;\n\n"
                            "# Then enforce:\n"
                            "Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https:;"
                        ),
                    })
                    score -= 10

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
