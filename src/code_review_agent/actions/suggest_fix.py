import logging

from code_review_agent.actions.base import BaseAction

logger = logging.getLogger(__name__)


class SuggestFixAction(BaseAction):
    name = "suggest_fix"

    def __init__(self, llm_router=None, fallback=None):
        self.llm_router = llm_router
        self.fallback = fallback

    async def execute(self, normalized: dict, session) -> str:
        text = normalized.get("text", "")

        # Try to find which finding the user is asking about
        target_finding = None
        review = session.last_review
        findings = review.get("findings", [])

        if findings:
            # Match by number: "第1个", "how to fix #1", "fix issue 2"
            import re
            match = re.search(r"(?:第\s*|#|issue\s*|problem\s*|finding\s*)(\d+)", text, re.IGNORECASE)
            if match:
                idx = int(match.group(1)) - 1
                if 0 <= idx < len(findings):
                    target_finding = findings[idx]

        if not target_finding:
            return (
                "Please specify which finding you want fix suggestions for. Examples:\n"
                "- `how to fix #1`\n"
                "- `第2个问题怎么修`\n\n"
                "Run a review first to generate findings."
            )

        f = target_finding
        context = (
            f"File: {f['file']}:{f['line']}\n"
            f"Severity: {f['severity']}\n"
            f"Category: {f['category']}\n"
            f"Issue: {f['title']}\n"
            f"Description: {f['message']}\n"
        )
        if f.get("suggestion"):
            context += f"Initial suggestion: {f['suggestion']}\n"
        if f.get("code_snippet"):
            context += f"Code snippet: {f['code_snippet']}\n"

        prompt = (
            "You are an expert code reviewer. Provide a detailed fix for the following issue.\n"
            "Show the BEFORE and AFTER code, and explain why the fix works.\n\n"
            f"{context}\n\n"
            f"User request: {text}\n"
        )

        if self.fallback:
            resp = await self.fallback.call_with_fallback("suggest_fix", [
                {"role": "user", "content": prompt},
            ])
            return resp.content

        return "Suggest fix action requires LLM configuration."
