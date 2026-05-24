import logging
import re

from code_review_agent.actions.base import BaseReviewAction

logger = logging.getLogger(__name__)


class ReviewBranchAction(BaseReviewAction):
    name = "review_branch"

    async def execute(self, normalized: dict, session) -> str:
        text = normalized.get("text", "")

        match = re.search(
            r"(?:review|审查)\s*(?:branch|分支)\s+([^\s]+)(?:\s+(?:in|of|for)\s+([\w.-]+/[\w.-]+))?",
            text, re.IGNORECASE,
        )
        if not match:
            return (
                "Please specify a branch to review. Examples:\n"
                "- `review branch feature-x in org/repo`\n"
                "- `review branch main in chikhamx/code-reviewer`"
            )

        branch = match.group(1)
        repo_name = match.group(2) or session.metadata.get("review_target", {}).get("repo", "")

        if not repo_name:
            return "Which repository? Say `review branch <name> in <org/repo>`"
        if not self.github:
            return "GitHub client not configured."

        base = "main"
        session.current_target = f"{repo_name}/compare/{base}...{branch}"
        session.metadata["review_target"] = {"repo": repo_name, "branch": branch}

        try:
            logger.info("Comparing %s...%s in %s", base, branch, repo_name)
            ctx = self.github.compare_branches(repo_name, base, branch)
            if not ctx:
                return f"Could not compare {base}...{branch} in {repo_name}."

            formatted = await self.run_review_pipeline(ctx, repo_name, branch, session)
            return f"Branch Review: {branch} (vs {base}) in {repo_name}\n**Files changed**: {len(ctx.files)}\n\n{formatted}"
        except Exception as e:
            logger.exception("Branch review failed")
            return f"Failed to review branch: {e}"
