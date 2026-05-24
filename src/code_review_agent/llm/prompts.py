REVIEW_SYSTEM_PROMPT = """You are an expert code reviewer. Analyze the following code diff and identify issues.

For each finding, provide a structured assessment. Focus on:
1. **Bug Risk**: null pointers, unhandled exceptions, race conditions, off-by-one, logic errors
2. **Security**: injection vulnerabilities, sensitive data exposure, missing auth checks, unsafe deserialization
3. **Performance**: N+1 queries, unnecessary allocations, blocking calls, inefficient algorithms
4. **Maintainability**: naming clarity, single responsibility violations, duplicated code, excessive complexity

Be precise and actionable. Each finding must include:
- The exact file and line number
- A clear description of the problem
- A concrete suggestion for fixing it

Output ONLY valid JSON in this exact format:
{
  "findings": [
    {
      "file": "path/to/file.py",
      "line": 42,
      "severity": "error",
      "category": "security",
      "title": "short title",
      "message": "detailed description",
      "suggestion": "how to fix"
    }
  ],
  "summary": "overall assessment in 2-3 sentences"
}

Severity values: critical, error, warning, info, suggestion
Category values: bug_risk, security, performance, maintainability, style, documentation
"""

INTENT_CLASSIFY_PROMPT = """Classify the user's intent from their message. Output ONLY one of these labels:

- review_pr: User wants to review a specific PR (mentions PR number or GitHub PR URL)
- review_branch: User wants to review a branch
- review_commit: User wants to review specific commits
- explain: User wants code explained
- suggest_fix: User asks how to fix a previously identified issue
- refactor: User wants refactoring suggestions
- search: User wants to search the codebase
- chat: General conversation or questions

User message: {message}

Intent:"""


def build_review_prompt(diff_content: str, pr_context: dict | None = None) -> tuple[str, str]:
    """Build system and user prompts for code review."""
    system = REVIEW_SYSTEM_PROMPT

    context_parts = []
    if pr_context:
        if pr_context.get("title"):
            context_parts.append(f"PR Title: {pr_context['title']}")
        if pr_context.get("description"):
            context_parts.append(f"PR Description: {pr_context['description']}")

    user_parts = []
    if context_parts:
        user_parts.append("## PR Context\n" + "\n".join(context_parts))
    user_parts.append("## Code Diff\n```diff\n" + diff_content + "\n```")
    user_parts.append("\nPlease review the above diff and provide your findings as JSON.")

    return system, "\n\n".join(user_parts)
