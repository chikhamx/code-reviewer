import logging
import re
from enum import Enum

from code_review_agent.llm.fallback import FallbackChain
from code_review_agent.llm.prompts import INTENT_CLASSIFY_PROMPT
from code_review_agent.llm.router import ModelRouter

logger = logging.getLogger(__name__)


class Intent(str, Enum):
    REVIEW_PR = "review_pr"
    REVIEW_BRANCH = "review_branch"
    REVIEW_COMMIT = "review_commit"
    EXPLAIN = "explain"
    SUGGEST_FIX = "suggest_fix"
    REFACTOR = "refactor"
    SEARCH = "search"
    CHAT = "chat"


class IntentRouter:
    """Two-level intent classification: L1 regex fast path, L2 LLM fallback."""

    L1_PATTERNS: list[tuple[str, Intent, int]] = [
        (r"github\.com/[\w.-]+/[\w.-]+/pull/\d+", Intent.REVIEW_PR, 10),
        (r"gitlab\.com/[\w.-]+/[\w.-]+/-/merge_requests/\d+", Intent.REVIEW_PR, 10),
        (r"(review|审查|看一下|check).*(PR|pull|request|mr|merge).*#?\s*\d+", Intent.REVIEW_PR, 8),
        (r"(review|审查|看|check)\s+(分支|branch)", Intent.REVIEW_BRANCH, 7),
        (r"(review|审查|看|check)\s*(最近|last|latest)?\s*(commit|提交)", Intent.REVIEW_COMMIT, 7),
        (r"(解释|说明|这是怎么|what does|explain).*(代码|逻辑|这段|function|这段代码|这里)", Intent.EXPLAIN, 7),
        (r"(怎么修|怎么改|如何修复|建议|方案|fix|suggest).*(问题|这里|这个|第\s*\d)", Intent.SUGGEST_FIX, 8),
        (r"(重构|优化|改写|refactor|clean\s*up).*(代码|这个|函数|方法|模块|class)", Intent.REFACTOR, 8),
        (r"(搜索|找|哪里|grep|search|find).*(代码|文件|实现|用了|哪里|怎么用)", Intent.SEARCH, 7),
        (r"^(帮助|help|菜单|menu|你能做什么|what can you do)\b", Intent.CHAT, 5),
    ]

    def __init__(self, router: ModelRouter, fallback: FallbackChain):
        self.router = router
        self.fallback = fallback

    async def classify(self, text: str, session=None) -> Intent:
        text_lower = text.lower().strip()

        # L1: regex fast match
        best_intent = Intent.CHAT
        best_score = 0
        for pattern, intent, score in self.L1_PATTERNS:
            if re.search(pattern, text_lower):
                if score > best_score:
                    best_intent = intent
                    best_score = score

        if best_score >= 8:
            logger.info("Intent: L1 -> %s (score=%d, text=%.60s)", best_intent.value, best_score, text)
            return best_intent

        logger.info("Intent: L1 no strong match (best=%s score=%d), trying L2 LLM...",
                     best_intent.value, best_score)
        # L2: LLM classification
        try:
            intent = await self._llm_classify(text)
            logger.info("Intent: L2 LLM -> %s", intent.value)
            return intent
        except Exception as e:
            logger.warning("Intent: L2 LLM failed: %s, falling back to chat", e)
            return Intent.CHAT

    async def _llm_classify(self, text: str) -> Intent:
        prompt = INTENT_CLASSIFY_PROMPT.format(message=text)
        resp = await self.fallback.call_with_fallback("intent_classify", [
            {"role": "user", "content": prompt},
        ])
        label = resp.content.strip().lower().replace("-", "_")
        try:
            return Intent(label)
        except ValueError:
            logger.debug("LLM returned unknown intent: %s", label)
            return Intent.CHAT

    @staticmethod
    def extract_pr_url(text: str) -> str | None:
        """Extract PR URL from message text."""
        match = re.search(r"(https?://github\.com/[\w.-]+/[\w.-]+/pull/\d+)", text)
        if match:
            return match.group(1)
        match = re.search(r"(https?://gitlab\.com/[\w.-]+/[\w.-]+/-/merge_requests/\d+)", text)
        if match:
            return match.group(1)
        return None
