"""
PromptManager — loads, caches, and renders prompt templates from the /prompts directory.

Every LLM prompt in the platform is stored as a .txt file in /prompts/.
Agents never hardcode prompts — they call prompt_manager.render("template_name", **vars).

Features
--------
- Lazy loading with in-memory cache (loaded once per process)
- Safe variable substitution: missing {variables} are kept as-is instead of crashing
- Hot reload support for development (prompt_manager.reload("name"))
- Graceful fallback: returns empty string with warning if file not found
- Composition: load() + render() can be chained with partial variables
"""

import logging
from pathlib import Path

_log = logging.getLogger("prompt_manager")

# Resolve relative to this file's location: utils/../prompts/
_DEFAULT_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class _SafeFormatDict(dict):
    """Returns '{key}' for missing keys so partial renders don't crash."""
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


class PromptManager:
    """
    Central registry for all LLM prompt templates.

    Usage:
        from utils.prompt_manager import prompt_manager

        # Simple load (returns raw template string)
        template = prompt_manager.load("reviewer_prompt")

        # Render with variables (returns filled string)
        filled = prompt_manager.render("reviewer_prompt",
            url="https://example.com",
            issues_text="- Missing title\\n- No H1",
        )
    """

    def __init__(self, prompts_dir: Path = _DEFAULT_PROMPTS_DIR) -> None:
        self._dir   = prompts_dir
        self._cache: dict[str, str] = {}

    # ── Core API ──────────────────────────────────────────────────────────────

    def load(self, name: str) -> str:
        """
        Load a prompt template by name (omit the .txt extension).
        Returns the raw template string.  Returns "" if not found.
        Results are cached after the first load.
        """
        if name in self._cache:
            return self._cache[name]

        path = self._dir / f"{name}.txt"
        if not path.exists():
            _log.warning("[prompts] Template '%s' not found at %s", name, path)
            return ""

        text = path.read_text(encoding="utf-8").strip()
        self._cache[name] = text
        _log.debug("[prompts] Loaded '%s' (%d chars)", name, len(text))
        return text

    def render(self, name: str, **kwargs) -> str:
        """
        Load and render a prompt template with the given keyword arguments.
        Missing variables are kept as literal {placeholder} text.
        Returns "" if the template file does not exist.
        """
        template = self.load(name)
        if not template:
            return ""
        try:
            return template.format_map(_SafeFormatDict(**kwargs))
        except Exception as exc:
            _log.warning("[prompts] Render error for '%s': %s", name, exc)
            return template

    def compose(self, *names: str, separator: str = "\n\n") -> str:
        """Load and concatenate multiple templates (e.g. system + task prompt)."""
        parts = [self.load(n) for n in names if self.load(n)]
        return separator.join(parts)

    # ── Cache management ──────────────────────────────────────────────────────

    def reload(self, name: str) -> str:
        """Force-reload a template from disk (clears cache for that key)."""
        self._cache.pop(name, None)
        return self.load(name)

    def reload_all(self) -> None:
        """Clear the entire cache so all templates reload on next access."""
        self._cache.clear()
        _log.info("[prompts] Cache cleared — all templates will reload on demand")

    def preload_all(self) -> int:
        """Load all .txt files in the prompts directory into cache at startup."""
        count = 0
        for path in self._dir.glob("*.txt"):
            self.load(path.stem)
            count += 1
        _log.info("[prompts] Preloaded %d prompt templates", count)
        return count

    # ── Introspection ─────────────────────────────────────────────────────────

    def list_prompts(self) -> list[str]:
        """Return names of all available prompt templates (without .txt)."""
        return sorted(p.stem for p in self._dir.glob("*.txt"))

    def exists(self, name: str) -> bool:
        return (self._dir / f"{name}.txt").exists()

    def raw_path(self, name: str) -> Path:
        return self._dir / f"{name}.txt"


# ── Process-wide singleton ────────────────────────────────────────────────────
prompt_manager = PromptManager()
