"""
IntentClassifier — maps a natural-language instruction + URL to a typed intent.

Two-stage classification:
  1. Rule-based keyword matching (fast, no API calls)
  2. Groq LLM fallback for ambiguous inputs

Supported intents
-----------------
  seo_audit          Full technical SEO audit (all agents)
  quick_seo_check    Single-page fast check (meta + security only)
  technical_audit    Performance, security, indexability focus
  content_analysis   Meta tags, headings, structured data, OG focus
  link_audit         Broken links + anchor text only
  security_audit     Security headers + HTTPS focus
  unknown            Could not classify — default to seo_audit
"""

import asyncio
import logging
from dataclasses import dataclass, field

_log = logging.getLogger("intent_classifier")

# ── Supported intents ─────────────────────────────────────────────────────────

SUPPORTED_INTENTS = [
    "seo_audit",
    "quick_seo_check",
    "technical_audit",
    "content_analysis",
    "link_audit",
    "security_audit",
    "unknown",
]

# ── Rule-based keyword patterns ───────────────────────────────────────────────

_PATTERNS: dict[str, list[str]] = {
    "quick_seo_check": [
        "quick", "fast", "single page", "one page", "brief", "snapshot", "preview",
    ],
    "technical_audit": [
        "technical", "performance", "speed", "ttfb", "page speed", "core web vitals",
        "crawl", "robots", "sitemap", "indexability", "index",
    ],
    "content_analysis": [
        "content", "meta", "heading", "title", "description", "h1", "h2",
        "open graph", "og tags", "twitter card", "schema", "structured data",
    ],
    "link_audit": [
        "link", "broken link", "anchor", "href", "404", "dead link", "redirect",
    ],
    "security_audit": [
        "security", "https", "ssl", "tls", "header", "hsts", "csp",
        "content security policy", "x-frame", "clickjacking",
    ],
    "seo_audit": [
        "full audit", "complete audit", "seo audit", "full seo", "all checks",
        "everything", "comprehensive", "deep audit",
    ],
}

# Default max_pages per intent
_DEFAULT_PAGES: dict[str, int] = {
    "seo_audit":       50,
    "quick_seo_check":  1,
    "technical_audit": 10,
    "content_analysis": 20,
    "link_audit":      30,
    "security_audit":   5,
    "unknown":         50,
}


@dataclass
class ClassifiedIntent:
    intent:               str
    confidence:           float            # 0.0 – 1.0
    reasoning:            str
    suggested_max_pages:  int
    classifier:           str = "rule"    # "rule" | "llm"
    alternatives:         list[str] = field(default_factory=list)


class IntentClassifier:
    """Classifies a free-text instruction into a typed SEO workflow intent."""

    def __init__(self, groq_api_key: str = "") -> None:
        self._groq_key = groq_api_key

    async def classify(self, instruction: str, url: str = "") -> ClassifiedIntent:
        """
        Main entry point.  Returns a ClassifiedIntent.
        Falls back to "seo_audit" if nothing matches.
        """
        text = (instruction + " " + url).lower()

        result = self._rule_based(text)
        if result.confidence >= 0.7:
            _log.info("Rule-based intent: %s (%.0f%%)", result.intent, result.confidence * 100)
            return result

        # Low-confidence — try LLM
        if self._groq_key:
            llm_result = await self._llm_classify(instruction, url)
            if llm_result:
                _log.info("LLM intent: %s (%.0f%%)", llm_result.intent, llm_result.confidence * 100)
                return llm_result

        # Default fallback
        _log.info("Defaulting to seo_audit (low confidence rule match)")
        result.intent = result.intent if result.intent != "unknown" else "seo_audit"
        return result

    # ── Rule-based ────────────────────────────────────────────────────────────

    def _rule_based(self, text: str) -> ClassifiedIntent:
        scores: dict[str, int] = {intent: 0 for intent in _PATTERNS}

        for intent, keywords in _PATTERNS.items():
            for kw in keywords:
                if kw in text:
                    scores[intent] += 1

        if not any(scores.values()):
            return ClassifiedIntent(
                intent="unknown",
                confidence=0.0,
                reasoning="No keywords matched",
                suggested_max_pages=50,
                classifier="rule",
            )

        best = max(scores, key=lambda k: scores[k])
        total_hits = sum(scores.values())
        confidence = min(scores[best] / max(total_hits, 1) + 0.3, 1.0)

        alts = [k for k, v in scores.items() if v > 0 and k != best]

        return ClassifiedIntent(
            intent=best,
            confidence=round(confidence, 2),
            reasoning=f"Matched {scores[best]} keyword(s) for '{best}'",
            suggested_max_pages=_DEFAULT_PAGES.get(best, 50),
            classifier="rule",
            alternatives=alts,
        )

    # ── LLM fallback ──────────────────────────────────────────────────────────

    async def _llm_classify(self, instruction: str, url: str) -> ClassifiedIntent | None:
        from utils.prompt_manager import prompt_manager
        intent_list = "\n".join(f"- {i}" for i in SUPPORTED_INTENTS if i != "unknown")
        prompt = prompt_manager.render(
            "intent_classifier_prompt",
            url=url or "(not provided)",
            instruction=instruction,
            intent_list=intent_list,
        )

        def _call() -> str:
            from groq import Groq
            resp = Groq(api_key=self._groq_key).chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=80,
                temperature=0.1,
            )
            return resp.choices[0].message.content or ""

        try:
            raw = await asyncio.to_thread(_call)
            lines = {
                l.split(":")[0].strip(): ":".join(l.split(":")[1:]).strip()
                for l in raw.splitlines() if ":" in l
            }
            intent = lines.get("INTENT", "").strip().lower()
            if intent not in SUPPORTED_INTENTS:
                return None
            confidence = float(lines.get("CONFIDENCE", "0.5"))
            return ClassifiedIntent(
                intent=intent,
                confidence=round(confidence, 2),
                reasoning=lines.get("REASONING", "LLM classification"),
                suggested_max_pages=_DEFAULT_PAGES.get(intent, 50),
                classifier="llm",
            )
        except Exception as exc:
            _log.warning("LLM classifier failed: %s", exc)
            return None
