import logging
import re

from code_review_agent.actions.base import BaseAction
from code_review_agent.actions.utils import detect_languages, format_result

logger = logging.getLogger(__name__)


class ReviewBranchAction(BaseAction):
    name = "review_branch"

    def __init__(self, core_engine=None, llm_router=None, github_client=None, gitlab_client=None, skill_loader=None):
        self.core_engine = core_engine
        self.llm_router = llm_router
        self.github = github_client
        self.gitlab = gitlab_client
        self.skill_loader = skill_loader

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
            return "GitHub client not configured. Set GITHUB_TOKEN."

        base = "main"
        session.current_target = f"{repo_name}/compare/{base}...{branch}"
        session.metadata["review_target"] = {"repo": repo_name, "branch": branch}

        try:
            logger.info("Comparing %s...%s in %s", base, branch, repo_name)
            ctx = self.github.compare_branches(repo_name, base, branch)
            if not ctx:
                return f"Could not compare {base}...{branch} in {repo_name}. Does the branch exist?"

            # Skills and prompts
            skill_prompts = ""
            lang_rules: list[dict] = []
            if self.skill_loader:
                langs = detect_languages(ctx.files)
                skill_prompts = self.skill_loader.get_prompts_for_languages(langs)
                lang_rules = self.skill_loader.get_rules_for_languages(langs)

                # Tier 3: project-local .code-review/
                prompt, rules = await self._load_project_config(repo_name, branch)
                if prompt:
                    skill_prompts += "\n\n" + prompt
                lang_rules.extend(rules)

            from code_review_agent.core.diff_parser import DiffParser
            diff_text = DiffParser().diff_to_text(ctx.files)
            result = await self.core_engine.review(ctx, diff_text, skill_prompts, custom_rules=lang_rules)

            return (
                f"Branch Review: {branch} (vs {base}) in {repo_name}\n"
                f"**Files changed**: {len(ctx.files)}\n\n"
                + format_result(result)
            )
        except Exception as e:
            logger.exception("Branch review failed")
            return f"Failed to review branch: {e}"

    async def _load_project_config(self, repo_name: str, branch: str) -> tuple[str, list[dict]]:
        if not self.github or not self.skill_loader:
            return "", []
        prompt = ""
        rules: list[dict] = []
        try:
            content = self.github.get_file_content(repo_name, ".code-review/review.md", ref=branch)
            if content:
                prompt = self.skill_loader.load_project_prompt(content)
        except Exception:
            pass
        try:
            content = self.github.get_file_content(repo_name, ".code-review/rules.yaml", ref=branch)
            if content:
                rules = self.skill_loader.load_project_rules(content)
        except Exception:
            pass
        return prompt, rules
