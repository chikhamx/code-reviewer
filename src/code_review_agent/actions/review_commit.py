import logging
import re

from code_review_agent.actions.base import BaseReviewAction

logger = logging.getLogger(__name__)


class ReviewCommitAction(BaseReviewAction):
    name = "review_commit"

    async def execute(self, normalized: dict, session) -> str:
        text = normalized.get("text", "")

        match = re.search(
            r"(?:review|审查)\s*(?:commits?|提交)\s+([a-f0-9]{7,40})\s*(?:in\s+([\w.-]+/[\w.-]+))?",
            text, re.IGNORECASE,
        )
        if not match:
            return (
                "Please specify a commit to review. Examples:\n"
                "- `review commit abc1234 in org/repo`\n"
                "- `review commit abc1234def5678`"
            )

        commit_sha = match.group(1)
        repo_name = match.group(2) or session.metadata.get("review_target", {}).get("repo", "")

        if not repo_name:
            return "Which repository? Say `review commit <sha> in <org/repo>`"
        if not self.github:
            return "GitHub client not configured."

        session.current_target = f"{repo_name}/commit/{commit_sha}"
        session.metadata["review_target"] = {"repo": repo_name, "commit": commit_sha}

        try:
            logger.info("Fetching commit %s in %s", commit_sha[:8], repo_name)
            ctx = self.github.get_commit_diff(repo_name, commit_sha)
            if not ctx:
                return f"Could not fetch commit {commit_sha[:8]} in {repo_name}."

            formatted = await self.run_review_pipeline(ctx, repo_name, "", session)
            return f"Commit Review: {commit_sha[:7]} in {repo_name}\n**Files changed**: {len(ctx.files)}\n\n{formatted}"
        except Exception as e:
            logger.exception("Commit review failed")
            return f"Failed to review commit: {e}"
