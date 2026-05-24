import json
import logging

from code_review_agent.llm.fallback import FallbackChain
from code_review_agent.llm.prompts import build_review_prompt
from code_review_agent.llm.router import ModelRouter
from code_review_agent.models.review import Finding, FindingCategory, FindingSeverity

logger = logging.getLogger(__name__)


class LLMReviewer:
    """Code reviewer powered by LLM with structured prompt and JSON output."""

    def __init__(self, router: ModelRouter, fallback: FallbackChain):
        self.router = router
        self.fallback = fallback

    async def review(
        self,
        diff_text: str,
        pr_context: dict | None = None,
        skill_prompts: str = "",
    ) -> list[Finding]:
        system, user = build_review_prompt(diff_text, pr_context, skill_prompts)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        resp = await self.fallback.call_with_fallback("review", messages)

        try:
            return self._parse_response(resp.content)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("Failed to parse LLM response: %s", e)
            return []

    def _parse_response(self, content: str) -> list[Finding]:
        # Extract JSON from response (may be wrapped in markdown code fences)
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:])
            if content.endswith("```"):
                content = content[:-3]

        data = json.loads(content)
        findings_data = data.get("findings", [])

        findings: list[Finding] = []
        for item in findings_data:
            try:
                finding = Finding(
                    file=item.get("file", ""),
                    line=item.get("line"),
                    severity=self._parse_severity(item.get("severity", "warning")),
                    category=self._parse_category(item.get("category", "maintainability")),
                    title=item.get("title", "Issue found"),
                    message=item.get("message", ""),
                    suggestion=item.get("suggestion"),
                    rule_id=item.get("rule_id"),
                    code_snippet=item.get("code_snippet"),
                )
                findings.append(finding)
            except Exception as e:
                logger.warning("Skipping malformed finding: %s", e)
                continue

        return findings

    @staticmethod
    def _parse_severity(raw: str) -> FindingSeverity:
        try:
            return FindingSeverity(raw.lower())
        except ValueError:
            return FindingSeverity.warning

    @staticmethod
    def _parse_category(raw: str) -> FindingCategory:
        try:
            return FindingCategory(raw.lower())
        except ValueError:
            return FindingCategory.maintainability
