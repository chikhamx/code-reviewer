import json
import logging
import time

from code_review_agent.llm.fallback import FallbackChain
from code_review_agent.llm.router import ModelRouter
from code_review_agent.models.platform import PRContext
from code_review_agent.models.review import Finding, ReviewResult
from code_review_agent.reviewers.llm_reviewer import LLMReviewer
from code_review_agent.reviewers.rule_engine import RuleEngine

logger = logging.getLogger(__name__)


class Orchestrator:
    """Coordinates the full review pipeline: parse -> review -> merge -> output."""

    def __init__(
        self,
        router: ModelRouter,
        fallback: FallbackChain,
        rule_engine: RuleEngine | None = None,
    ):
        self.llm_reviewer = LLMReviewer(router, fallback)
        self.rule_engine = rule_engine or RuleEngine()

    async def review(self, pr_context: PRContext, diff_text: str) -> ReviewResult:
        start = time.monotonic()

        result = ReviewResult(
            pr_title=pr_context.title,
            pr_url=pr_context.url,
            pr_number=pr_context.pr_number,
            branch=pr_context.branch,
            base_branch=pr_context.base_branch,
            repo_name=pr_context.repo_name,
            author=pr_context.author,
        )

        # Run LLM review and rule engine in parallel
        llm_findings: list[Finding] = []
        rule_findings: list[Finding] = []

        try:
            llm_findings = await self.llm_reviewer.review(diff_text, {
                "title": pr_context.title,
                "description": pr_context.description,
                "branch": pr_context.branch,
            })
        except Exception as e:
            logger.error("LLM review failed: %s", e)

        try:
            rule_findings = self.rule_engine.check(pr_context.files)
        except Exception as e:
            logger.error("Rule engine failed: %s", e)

        # Merge and deduplicate
        result.findings = self._merge_findings(llm_findings, rule_findings)
        result.compute_stats()
        result.review_duration_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "Review complete: PR #%d, %d findings, %dms",
            pr_context.pr_number,
            len(result.findings),
            result.review_duration_ms,
        )
        return result

    def _merge_findings(
        self, llm_findings: list[Finding], rule_findings: list[Finding]
    ) -> list[Finding]:
        """Merge findings, deduplicate by (file, line, category), sort by severity."""
        seen: set[tuple] = set()
        merged: list[Finding] = []

        for f in llm_findings + rule_findings:
            key = (f.file, f.line or 0, f.category.value, f.title)
            if key in seen:
                continue
            seen.add(key)
            merged.append(f)

        sev_order = {"critical": 0, "error": 1, "warning": 2, "info": 3, "suggestion": 4}
        merged.sort(key=lambda f: sev_order.get(f.severity.value, 5))
        return merged
