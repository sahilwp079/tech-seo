"""RecommendationAgent — groups recommendations by page, deduplicates, enriches with Groq."""

import asyncio
from collections import defaultdict

from agents.base_agent import BaseAgent, AgentResult


class RecommendationAgent(BaseAgent):
    name = "RecommendationAgent"
    dependencies = ["ValidationAgent"]

    async def run(self) -> AgentResult:
        await self._started()
        try:
            issues = self.ctx.store.get_issues(self.ctx.audit_id)
            recs   = self.ctx.store.get_recommendations(self.ctx.audit_id)

            # ── Deduplicate by (issue_type, page_url) — keep highest priority ──
            pri_order = {"high": 0, "medium": 1, "low": 2}
            seen: dict[tuple, dict] = {}
            for rec in recs:
                key = (rec.get("issue_type", ""), rec.get("page_url", ""))
                if key not in seen or pri_order.get(rec.get("priority", "low"), 2) < pri_order.get(seen[key].get("priority", "low"), 2):
                    seen[key] = rec

            deduped = sorted(seen.values(), key=lambda r: (
                pri_order.get(r.get("priority", "low"), 2),
                r.get("page_url", ""),
            ))

            # ── Group by page ──────────────────────────────────────────────────
            by_page: dict[str, list[dict]] = defaultdict(list)
            for rec in deduped:
                by_page[rec.get("page_url", "site-level")].append(rec)

            # ── Enrich with knowledge base ─────────────────────────────────────
            for rec in [r for r in deduped if r.get("priority") == "high"][:5]:
                kb = self.ctx.store.get_knowledge(rec.get("issue_type", ""), n=1)
                if kb:
                    rec["knowledge_context"] = kb[0].get("content", "")

            # ── Groq AI enrichment for critical pages ─────────────────────────
            critical_pages = {
                rec["page_url"]
                for rec in deduped
                if rec.get("priority") == "high" and rec.get("page_url")
            }
            ai_summaries: dict[str, str] = {}
            for page_url in list(critical_pages)[:3]:  # limit to 3 pages to save API calls
                page_recs = [r for r in deduped if r.get("page_url") == page_url and r.get("priority") == "high"]
                summary = await self._ai_enrich(page_url, page_recs, issues)
                if summary:
                    ai_summaries[page_url] = summary

            # Store enriched data back into each rec
            for rec in deduped:
                if rec.get("page_url") in ai_summaries:
                    rec["ai_action_plan"] = ai_summaries[rec["page_url"]]

            await self._completed(score=None, issues_count=len(deduped))
            result = AgentResult(
                agent_name=self.name, success=True,
                issues_count=len(deduped),
                data={
                    "total_recommendations": len(deduped),
                    "pages_affected":        len(by_page),
                    "recommendations":       deduped,
                    "ai_summaries":          ai_summaries,
                },
            )
            return self._validate_contract(result)
        except Exception as exc:
            await self._failed(str(exc))
            return AgentResult(agent_name=self.name, success=False, error=str(exc))

    async def _ai_enrich(self, page_url: str, recs: list[dict], all_issues: list[dict]) -> str:
        """Use Groq to generate a concise, developer-focused action plan for one page."""
        if not self.ctx.groq_api_key or not recs:
            return ""

        # Build a structured prompt from the actual data
        issue_lines = []
        for rec in recs[:6]:
            issue_lines.append(
                f"• [{rec.get('priority','').upper()}] {rec.get('issue_type','').replace('_',' ').title()}\n"
                f"  Section: {rec.get('section','')}\n"
                f"  Element: {rec.get('element','')}\n"
                f"  Fix: {rec.get('action','')}"
            )
        issues_text = "\n".join(issue_lines)

        # RAG: retrieve relevant knowledge articles for each unique issue type on this page
        seen_kb: set[str] = set()
        kb_lines: list[str] = []
        for rec in recs[:6]:
            issue_type = rec.get("issue_type", "")
            if not issue_type or issue_type in seen_kb:
                continue
            seen_kb.add(issue_type)
            articles = self.ctx.store.get_knowledge(issue_type, n=1)
            if articles:
                art = articles[0]
                kb_lines.append(f"[{art.get('title', '')}] {art.get('content', '')}")

        knowledge_block = ""
        if kb_lines:
            knowledge_block = "\nSEO Reference Knowledge:\n" + "\n".join(f"- {l}" for l in kb_lines) + "\n"

        from utils.prompt_manager import prompt_manager
        prompt = prompt_manager.render(
            "executor_prompt",
            page_url=page_url,
            knowledge_block=knowledge_block,
            issues_text=issues_text,
            bullet_count="4–6",
        )

        _usage: dict = {}

        def _call() -> str:
            from groq import Groq
            resp = Groq(api_key=self.ctx.groq_api_key).chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.2,
            )
            if resp.usage:
                _usage["prompt_tokens"]     = resp.usage.prompt_tokens or 0
                _usage["completion_tokens"] = resp.usage.completion_tokens or 0
            return resp.choices[0].message.content or ""

        try:
            from utils.retry import llm_retry
            result = ""
            async for attempt in llm_retry(max_attempts=2):
                with attempt:
                    result = await asyncio.to_thread(_call)
            if _usage:
                from utils.metrics import metrics
                metrics.record_tokens(
                    self.ctx.audit_id,
                    _usage.get("prompt_tokens", 0),
                    _usage.get("completion_tokens", 0),
                )
            return result
        except Exception:
            return ""
