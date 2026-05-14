"""StructuredDataAgent — JSON-LD validity, OG tags, Twitter Cards."""

import json
from bs4 import BeautifulSoup
from agents.base_agent import BaseAgent, AgentResult


class StructuredDataAgent(BaseAgent):
    name = "StructuredDataAgent"
    dependencies = ["CrawlAgent"]

    async def run(self) -> AgentResult:
        await self._started()
        try:
            all_issues, all_scores = [], []

            for page in [p for p in self.ctx.pages if p.get("html")]:
                soup   = BeautifulSoup(page["html"], "lxml")
                url    = page["url"]
                issues = []
                score  = 100

                # ── JSON-LD ────────────────────────────────────────────────────
                ld_scripts  = soup.find_all("script", type="application/ld+json")
                invalid_ld  = []
                valid_types = []
                for script in ld_scripts:
                    try:
                        parsed = json.loads(script.string or "")
                        t = parsed.get("@type", "Unknown") if isinstance(parsed, dict) else "Unknown"
                        valid_types.append(t)
                    except (json.JSONDecodeError, AttributeError) as e:
                        invalid_ld.append(str(e)[:100])

                if not ld_scripts:
                    issues.append({
                        "type": "missing_structured_data", "severity": "warning",
                        "title": "No JSON-LD structured data found",
                        "description": "Structured data helps search engines understand page content and can unlock rich results (breadcrumbs, FAQs, star ratings) in SERPs.",
                        "section": "<head> or <body>",
                        "element": '<script type="application/ld+json">',
                        "current_value": "(no structured data blocks found)",
                        "fix": "Add JSON-LD schema markup. Start with Organization and WebPage types for all pages. Add Article, Product, or FAQ markup where applicable.",
                        "before": "(no <script type=\"application/ld+json\"> blocks present)",
                        "after": (
                            '<script type="application/ld+json">\n'
                            '{\n'
                            '  "@context": "https://schema.org",\n'
                            '  "@type": "WebPage",\n'
                            '  "name": "Page Title",\n'
                            '  "description": "Page description",\n'
                            '  "url": "' + url + '",\n'
                            '  "publisher": {\n'
                            '    "@type": "Organization",\n'
                            '    "name": "Your Brand",\n'
                            '    "logo": "https://example.com/logo.png"\n'
                            '  }\n'
                            '}\n'
                            '</script>'
                        ),
                    })
                    score -= 30

                if invalid_ld:
                    errors_str = "\n".join(invalid_ld[:3])
                    issues.append({
                        "type": "invalid_json_ld", "severity": "critical",
                        "title": f"{len(invalid_ld)} JSON-LD block(s) contain invalid JSON",
                        "description": f"Invalid JSON in structured data blocks causes search engines to ignore them entirely. Errors: {errors_str}",
                        "section": "<head> or <body>",
                        "element": f'<script type="application/ld+json"> × {len(invalid_ld)} invalid',
                        "current_value": f"JSON parse errors:\n{errors_str}",
                        "fix": "Fix JSON syntax errors. Validate your markup at https://validator.schema.org/ and https://search.google.com/test/rich-results",
                        "before": f"JSON-LD block with syntax errors (missing quotes, trailing commas, etc.)",
                        "after": (
                            "✓ Valid JSON-LD — run through validator:\n"
                            "• https://validator.schema.org/\n"
                            "• https://search.google.com/test/rich-results\n"
                            "Common errors: trailing commas, unescaped quotes, missing closing braces"
                        ),
                    })
                    score -= 20

                # ── Open Graph ─────────────────────────────────────────────────
                og_title = soup.find("meta", property="og:title")
                og_desc  = soup.find("meta", property="og:description")
                og_image = soup.find("meta", property="og:image")
                og_url   = soup.find("meta", property="og:url")
                missing_og = [tag for tag, el in [
                    ("og:title", og_title), ("og:description", og_desc),
                    ("og:image", og_image), ("og:url", og_url),
                ] if not el]

                if missing_og:
                    issues.append({
                        "type": "missing_og_tags", "severity": "warning",
                        "title": f"Missing Open Graph tags: {', '.join(missing_og)}",
                        "description": f"These OG tags are missing: {', '.join(missing_og)}. Without them, social media platforms generate poor previews.",
                        "section": "<head>",
                        "element": f"<meta property=\"{missing_og[0]}\">",
                        "current_value": f"Present: {', '.join(t for t, el in [('og:title', og_title), ('og:description', og_desc), ('og:image', og_image)] if el) or 'none'}\nMissing: {', '.join(missing_og)}",
                        "fix": "Add all required Open Graph tags inside <head>. og:image must be at least 1200×630 px for optimal display.",
                        "before": f"Missing Open Graph tags: {', '.join(missing_og)}",
                        "after": (
                            '<meta property="og:title" content="Exact Page Title">\n'
                            '<meta property="og:description" content="Compelling description 120–160 chars">\n'
                            '<meta property="og:image" content="https://example.com/image.jpg">  ← min 1200×630px\n'
                            f'<meta property="og:url" content="{url}">\n'
                            '<meta property="og:type" content="website">'
                        ),
                    })
                    score -= min(20, 5 * len(missing_og))

                # ── Twitter Card ───────────────────────────────────────────────
                if not soup.find("meta", attrs={"name": "twitter:card"}):
                    issues.append({
                        "type": "missing_twitter_card", "severity": "info",
                        "title": "Missing Twitter Card meta tag",
                        "description": "Without Twitter Card tags, tweets linking to this page show a plain URL instead of a rich preview with image and description.",
                        "section": "<head>",
                        "element": '<meta name="twitter:card">',
                        "current_value": "(no twitter:card meta tag found)",
                        "fix": "Add Twitter Card meta tags inside <head>.",
                        "before": "(no twitter:card meta tag)",
                        "after": (
                            '<meta name="twitter:card" content="summary_large_image">\n'
                            '<meta name="twitter:title" content="Page Title">\n'
                            '<meta name="twitter:description" content="Description 120–160 chars">\n'
                            '<meta name="twitter:image" content="https://example.com/image.jpg">  ← min 800×418px'
                        ),
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
