"""ValidationAgent — 4-check quality gate after all analysis agents complete."""

import asyncio
import json
from agents.base_agent import BaseAgent, AgentResult

ANALYSIS_AGENTS = [
    "MetaAnalysisAgent", "LinkAnalysisAgent", "PerformanceAgent",
    "StructuredDataAgent", "SecurityAgent", "IndexabilityAgent",
]

CRITICAL_SCORE_CAPS = {
    "missing_title":    ("MetaAnalysisAgent",   80),
    "missing_h1":       ("MetaAnalysisAgent",   85),
    "missing_viewport": ("MobileAgent",         65),
    "no_https":         ("SecurityAgent",       65),
    "no_robots_txt":    ("IndexabilityAgent",   90),
    "slow_ttfb":        ("PerformanceAgent",    80),
    "invalid_json_ld":  ("StructuredDataAgent", 85),
}


class ValidationAgent(BaseAgent):
    name = "ValidationAgent"
    dependencies = [
        "MetaAnalysisAgent", "LinkAnalysisAgent", "PerformanceAgent",
        "StructuredDataAgent", "SecurityAgent", "IndexabilityAgent",
    ]

    async def run(self) -> AgentResult:
        await self._started()
        try:
            issues    = self.ctx.store.get_issues(self.ctx.audit_id)
            wf_log    = self.ctx.store.get_workflow_log(self.ctx.audit_id)
            checks    = []
            confidence = 100

            # Check 1 — completeness
            ran_agents = {e["agent_name"] for e in wf_log if e["event_type"] == "completed"}
            failed_agents = {e["agent_name"] for e in wf_log if e["event_type"] == "failed"}
            missing = [a for a in ANALYSIS_AGENTS if a not in ran_agents]
            if missing or failed_agents:
                status = "failed" if missing else "warning"
                checks.append({"name": "Agent Completeness", "status": status,
                               "message": f"{len(failed_agents)} failed, {len(missing)} missing",
                               "details": [{"agent": a, "note": "did not complete"} for a in missing | failed_agents]})
                confidence -= 25 if missing else 10
            else:
                checks.append({"name": "Agent Completeness", "status": "passed",
                               "message": f"All {len(ANALYSIS_AGENTS)} agents completed", "details": []})

            # Check 2 — score consistency
            issue_types = {i["issue_type"] for i in issues}
            agent_scores: dict[str, int] = {}
            for e in wf_log:
                if e["event_type"] == "completed" and e.get("score", -1) != -1:
                    agent_scores[e["agent_name"]] = e["score"]

            flagged = []
            for issue_type, (agent, max_score) in CRITICAL_SCORE_CAPS.items():
                if issue_type in issue_types:
                    actual = agent_scores.get(agent)
                    if actual is not None and actual > max_score:
                        flagged.append({"agent": agent, "issue_type": issue_type,
                                        "actual_score": actual, "expected_max": max_score,
                                        "note": f"'{issue_type}' present but score {actual} > max {max_score}"})
            status2 = "failed" if len(flagged) >= 3 else ("warning" if flagged else "passed")
            checks.append({"name": "Score Consistency", "status": status2,
                           "message": f"{len(flagged)} inconsistenc{'y' if len(flagged)==1 else 'ies'}" if flagged else "All scores consistent",
                           "details": flagged})
            if status2 == "warning": confidence -= 10
            elif status2 == "failed": confidence -= 20

            # Check 3 — cross-agent logic
            cross = []
            if self.ctx.base_url.startswith("https://") and "no_https" in issue_types:
                cross.append({"rule": "https_url_vs_no_https_flag",
                              "note": "URL uses HTTPS but SecurityAgent flagged no_https"})
            if len(self.ctx.pages) > 1 and "blocked_by_robots" in issue_types:
                cross.append({"rule": "crawled_vs_robots_block",
                              "note": f"{len(self.ctx.pages)} pages crawled but robots block reported"})
            status3 = "failed" if len(cross) >= 2 else ("warning" if cross else "passed")
            checks.append({"name": "Cross-Agent Logic", "status": status3,
                           "message": f"{len(cross)} contradiction(s)" if cross else "No contradictions found",
                           "details": cross})
            if status3 == "warning": confidence -= 8
            elif status3 == "failed": confidence -= 15

            # Check 4 — LLM sanity
            check4 = await self._llm_sanity(issues)
            checks.append(check4)
            if check4["status"] == "warning":
                confidence -= 5

            statuses = {c["status"] for c in checks}
            overall = "failed" if "failed" in statuses else ("warnings" if "warning" in statuses else "passed")

            confidence_final = max(int(confidence), 0)
            validation = {"status": overall, "confidence": confidence_final, "checks": checks}
            self.ctx.store.update_audit(
                self.ctx.audit_id,
                validation_status=overall,
                confidence_score=confidence_final,
                validation_checks=json.dumps(checks),  # persist for API/frontend
            )

            await self._completed(score=confidence_final, issues_count=0)
            result = AgentResult(
                agent_name=self.name, success=True, score=confidence_final,
                data={
                    "validation_status": overall,
                    "confidence":        confidence_final,
                    "checks":            checks,
                },
            )
            return self._validate_contract(result)
        except Exception as exc:
            await self._failed(str(exc))
            return AgentResult(agent_name=self.name, success=False, error=str(exc))

    async def _llm_sanity(self, issues: list[dict]) -> dict:
        from config import settings
        if not settings.GROQ_API_KEY:
            return {"name": "LLM Sanity Review", "status": "skipped",
                    "message": "GROQ_API_KEY not configured", "details": []}

        critical = [i for i in issues if i.get("severity") == "critical"][:5]
        if not critical:
            return {"name": "LLM Sanity Review", "status": "passed",
                    "message": "No critical issues to validate", "details": []}

        lines = "\n".join(f"- [CRITICAL] {i['agent_name']}: {i['title']}" for i in critical)
        from utils.prompt_manager import prompt_manager
        prompt = prompt_manager.render(
            "reviewer_prompt",
            url=self.ctx.base_url,
            issues_text=lines,
        )

        _usage: dict = {}

        def _call() -> str:
            from groq import Groq
            client = Groq(api_key=settings.GROQ_API_KEY)
            resp = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=160, temperature=0.2,
            )
            if resp.usage:
                _usage["prompt_tokens"]     = resp.usage.prompt_tokens or 0
                _usage["completion_tokens"] = resp.usage.completion_tokens or 0
            return resp.choices[0].message.content or ""

        try:
            from utils.retry import llm_retry, RetryError
            raw = ""
            async for attempt in llm_retry(max_attempts=2):
                with attempt:
                    raw = await asyncio.to_thread(_call)
            if _usage:
                from utils.metrics import metrics
                metrics.record_tokens(
                    self.ctx.audit_id,
                    _usage.get("prompt_tokens", 0),
                    _usage.get("completion_tokens", 0),
                )
            verdict = next((l for l in raw.splitlines() if l.startswith("VERDICT:")), "")
            notes   = next((l for l in raw.splitlines() if l.startswith("NOTES:")), "")
            return {
                "name": "LLM Sanity Review",
                "status": "warning" if "CONCERNS" in verdict.upper() else "passed",
                "message": verdict.replace("VERDICT:", "").strip() or "Reviewed",
                "details": [{"note": notes.replace("NOTES:", "").strip()}],
            }
        except Exception as exc:
            return {"name": "LLM Sanity Review", "status": "skipped",
                    "message": f"LLM review failed after retries: {exc}", "details": []}
