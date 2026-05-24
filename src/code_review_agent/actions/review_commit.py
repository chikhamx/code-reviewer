import logging
import re

from code_review_agent.actions.base import BaseAction
from code_review_agent.actions.utils import detect_languages, format_result

logger = logging.getLogger(__name__)


class ReviewCommitAction(BaseAction):
    name = "review_commit"

    def __init__(self, core_engine=None, llm_router=None, github_client=None, gitlab_client=None, skill_loader=None):
        self.core_engine = core_engine
        self.llm_router = llm_router
        self.github = github_client
        self.gitlab = gitlab_client
        self.skill_loader = skill_loader

    async def execute(self, normalized: dict, session) -> str:
        text = normalized.get("text", "")

        # Parse: "review commit <sha> in <org/repo>"
        match = re.search(
            r"(?:review|审查)\s*(?:commit|提交)\s+([a-f0-9]{7,40})\s*(?:in\s+([\w.-]+/[\w.-]+))?",
            text, re.IGNORECASE,
        )
        # Also try parsing multiple commits: "review commits abc1234 def5678 in org/repo"
        if not match:
            match = re.search(
                r"(?:review|审查)\s*(?:commits|提交)\s+([a-f0-9]{7,40})(?:\s+[a-f0-9]{7,40})*\s*(?:in\s+([\w.-]+/[\w.-]+))?",
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
            return "GitHub client not configured. Set GITHUB_TOKEN."

        session.current_target = f"{repo_name}/commit/{commit_sha}"
        session.metadata["review_target"] = {"repo": repo_name, "commit": commit_sha}

        try:
            logger.info("Fetching commit %s in %s", commit_sha[:8], repo_name)
            ctx = self.github.get_commit_diff(repo_name, commit_sha)
            if not ctx:
                return (
                    f"Could not fetch commit {commit_sha[:8]} in {repo_name}.\\n"
                    f"Check that the commit exists and the token has repo access."
                )

            skill_prompts = ""
            lang_rules: list[dict] = []
            if self.skill_loader:
                langs = detect_languages(ctx.files)
                skill_prompts = self.skill_loader.get_prompts_for_languages(langs)
                lang_rules = self.skill_loader.get_rules_for_languages(langs)

            from code_review_agent.core.diff_parser import DiffParser
            diff_text = DiffParser().diff_to_text(ctx.files)
            result = await self.core_engine.review(ctx, diff_text, skill_prompts, custom_rules=lang_rules)

            return (
                f"Commit Review: {commit_sha[:7]} in {repo_name}\n"
                f"**Files changed**: {len(ctx.files)}\n\n"
                + format_result(result)
            )
        except Exception as e:
            logger.exception("Commit review failed")
            return f"Failed to review commit: {e}"
