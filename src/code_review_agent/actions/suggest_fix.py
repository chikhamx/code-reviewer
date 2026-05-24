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

        # Build context for all or specific findings
        if idx is not None:
            target_findings = [findings[idx]]
            prefix = "Provide a detailed fix for the following issue."
        else:
            target_findings = findings
            prefix = f"Provide detailed fixes for ALL {len(findings)} issues listed below."

        context_parts = []
        for f in target_findings:
            parts = [
                f"---",
                f"#{f['index']} [{f['severity'].upper()}] {f['file']}:{f['line']}",
                f"Title: {f['title']}",
                f"Description: {f['message']}",
            ]
            if f.get("suggestion"):
                parts.append(f"Hint: {f['suggestion']}")
            if f.get("code_snippet"):
                parts.append(f"Code: {f['code_snippet']}")
            context_parts.append("\n".join(parts))
        context = "\n\n".join(context_parts)

        if review.get("diff"):
            context += f"\n\nRelevant diff:\n```diff\n{review['diff'][:4000]}\n```"

        prompt = (
            f"You are an expert code reviewer. {prefix}\n"
            "For each issue, show the BEFORE and AFTER code and explain why the fix works.\n\n"
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
