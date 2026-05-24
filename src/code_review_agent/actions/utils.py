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


def store_review_context(session, result, diff_text: str = "") -> None:
    """Store review findings in session so follow-up queries can reference them."""
    findings = []
    for i, f in enumerate(result.findings):
        findings.append({
            "index": i + 1,
            "file": f.file,
            "line": f.line,
            "severity": f.severity.value,
            "category": f.category.value,
            "title": f.title,
            "message": f.message,
            "suggestion": f.suggestion or "",
            "code_snippet": f.code_snippet or "",
        })
    session.last_review = {
        "title": result.pr_title,
        "url": result.pr_url,
        "repo": result.repo_name,
        "findings": findings,
        "diff": diff_text[:8000],  # cap for context window
    }


def format_result(result) -> str:
    headings = [
        f"## Code Review: {result.pr_title}",
        f"**Risk**: {ICON.get(result.risk_level, '')} {result.risk_level.upper()}",
        f"**Findings**: {result.stats.total} issues",
        "",
    ]
    finding_lines = []
    for i, f in enumerate(result.findings):
        finding_lines.append(
            f"- **#{i+1}** [{f.severity.value.upper()}] `{f.file}:{f.line}` — {f.message[:100]}"
        )
    summary = []
    if result.summary:
        summary = ["", f"**Summary**: {result.summary}"]
    return "\n".join(headings + finding_lines + summary)
