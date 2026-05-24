import logging
import re

from code_review_agent.actions.base import BaseAction

logger = logging.getLogger(__name__)

# Chinese number words → index
_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
           "第一": 1, "第二": 2, "第三": 3, "第四": 4, "第五": 5}


class SuggestFixAction(BaseAction):
    name = "suggest_fix"

    def __init__(self, llm_router=None, fallback=None):
        self.llm_router = llm_router
        self.fallback = fallback

    async def execute(self, normalized: dict, session) -> str:
        text = normalized.get("text", "")

        review = session.last_review
        findings = review.get("findings", [])

        if not findings:
            return "No review findings in context. Run a review first, then ask for fixes."

        idx = self._find_target(text, findings)

        if idx is None:
            # Show a summary so user can pick
            lines = ["Which finding would you like a fix for? Reply with the number:"]
            for f in findings:
                lines.append(
                    f"  **#{f['index']}** [{f['severity'].upper()}] `{f['file']}:{f['line']}` — {f['title'][:60]}"
                )
            lines.append("")
            lines.append("Example: `how to fix #1` or `第1个怎么修`")
            return "\n".join(lines)

        f = findings[idx]
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
        if review.get("diff"):
            context += f"\nRelevant diff context:\n```diff\n{review['diff'][:4000]}\n```\n"

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

    def _find_target(self, text: str, findings: list[dict]) -> int | None:
        """Try to identify which finding the user is referencing. Returns index or None."""
        text_lower = text.lower()

        # "第1个", "第 2 个", "#1", "issue #2", "problem 3", "finding #1"
        m = re.search(r"(?:第\s*|#|issue\s*|problem\s*|finding\s*)(\d+)", text_lower)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(findings):
                return idx

        # "第一个", "第二个", "第一", "第二"  (Chinese ordinals)
        for word, num in _CN_NUM.items():
            if word in text:
                idx = num - 1
                if 0 <= idx < len(findings):
                    return idx

        # Match by keyword in finding title/message
        for f in findings:
            title_words = set(re.findall(r"\w+", f["title"].lower()))
            msg_words = set(re.findall(r"\w+", f["message"].lower()))
            text_words = set(re.findall(r"\w+", text_lower))
            overlap = (title_words | msg_words) & text_words
            # Need at least 2 meaningful word overlaps
            meaningful = overlap - {"the", "a", "an", "is", "in", "of", "to", "for", "this", "that", "how", "fix", "修", "怎么"}
            if len(meaningful) >= 2:
                return f["index"] - 1

        # Only one finding — just use it
        if len(findings) == 1:
            return 0

        return None
