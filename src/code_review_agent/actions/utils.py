"""Shared utilities for action handlers."""

import logging

logger = logging.getLogger(__name__)

EXT_TO_LANG = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
    ".c": "c", ".cpp": "cpp", ".h": "c",
    ".rb": "ruby", ".php": "php", ".swift": "swift",
    ".yaml": "yaml", ".yml": "yaml", ".json": "json",
    ".tf": "terraform", ".sh": "shell", ".sql": "sql",
    ".md": "markdown", ".css": "css", ".html": "html",
}

ICON = {"critical": "🔴", "error": "🟠", "warning": "🟡", "info": "🔵", "suggestion": "💡"}


def detect_languages(files) -> list[str]:
    """Detect programming languages from file extensions."""
    exts: set[str] = set()
    for f in files:
        path = getattr(f, "path", "") if hasattr(f, "path") else str(f)
        for ext, lang in EXT_TO_LANG.items():
            if path.endswith(ext):
                exts.add(lang)
                break
    return sorted(exts)


def format_result(result) -> str:
    headings = [
        f"## Code Review: {result.pr_title}",
        f"**Risk**: {ICON.get(result.risk_level, '')} {result.risk_level.upper()}",
        f"**Findings**: {result.stats.total} issues",
        "",
    ]
    finding_lines = []
    for f in result.findings:
        finding_lines.append(
            f"- [{f.severity.value.upper()}] `{f.file}:{f.line}` — {f.message[:100]}"
        )
    summary = []
    if result.summary:
        summary = ["", f"**Summary**: {result.summary}"]
    return "\n".join(headings + finding_lines + summary)
