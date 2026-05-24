import logging
import re

from code_review_agent.actions.base import BaseReviewAction
from code_review_agent.router.intent_router import IntentRouter

logger = logging.getLogger(__name__)


class ReviewPRAction(BaseReviewAction):
    name = "review_pr"

    async def execute(self, normalized: dict, session) -> str:
        text = normalized.get("text", "")
        pr_url = IntentRouter.extract_pr_url(text)

        if not pr_url:
            match = re.search(
                r"(?:review|审查)\s*(?:PR|pull|mr)?\s*#?\s*(\d+)\s*(?:in|of|for)?\s*([\w.-]+/[\w.-]+)",
                text, re.IGNORECASE,
            )
            if match:
                pr_number, repo_name = int(match.group(1)), match.group(2)
            else:
                return "Please specify a PR. Examples:\n- `review https://github.com/org/repo/pull/42`\n- `review PR #42 in org/repo`"
        else:
            parts = self._parse_github_url(pr_url) or self._parse_gitlab_url(pr_url)
            if not parts:
                return f"Could not parse PR URL: {pr_url}"
            repo_name, pr_number = parts

        if not self.github:
            return "GitHub client not configured."

        session.current_target = pr_url or f"{repo_name}#{pr_number}"
        session.metadata["review_target"] = {"repo": repo_name, "pr": pr_number}

        try:
            pr_ctx = self.github.get_pr_context(repo_name, pr_number)
            formatted = await self.run_review_pipeline(pr_ctx, repo_name, pr_ctx.branch, session)
            return f"Reviewing PR #{pr_number} in {repo_name}...\n\n{formatted}"
        except Exception as e:
            logger.exception("PR review failed")
            return f"Failed to review PR: {e}"

    @staticmethod
    def _parse_github_url(url: str) -> tuple[str, int] | None:
        m = re.match(r"https?://github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)", url)
        return (m.group(1), int(m.group(2))) if m else None

    @staticmethod
    def _parse_gitlab_url(url: str) -> tuple[str, int] | None:
        m = re.match(r"https?://gitlab\.com/([\w.-]+/[\w.-]+)/-/merge_requests/(\d+)", url)
        return (m.group(1), int(m.group(2))) if m else None
