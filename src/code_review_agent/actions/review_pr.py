import logging

from code_review_agent.actions.base import BaseAction
from code_review_agent.actions.utils import detect_languages, format_result
from code_review_agent.router.intent_router import IntentRouter

logger = logging.getLogger(__name__)


class ReviewPRAction(BaseAction):
    name = "review_pr"

    def __init__(self, core_engine, llm_router, github_client=None, gitlab_client=None, skill_loader=None):
        self.core_engine = core_engine
        self.llm_router = llm_router
        self.github = github_client
        self.gitlab = gitlab_client
        self.skill_loader = skill_loader

    async def execute(self, normalized: dict, session) -> str:
        text = normalized.get("text", "")
        pr_url = IntentRouter.extract_pr_url(text)

        if not pr_url:
            import re
            match = re.search(
                r"(?:review|审查)\s*(?:PR|pull|mr)?\s*#?\s*(\d+)\s*(?:in|of|for)?\s*([\w.-]+/[\w.-]+)",
                text, re.IGNORECASE,
            )
            if match:
                pr_number = int(match.group(1))
                repo_name = match.group(2)
            else:
                return (
                    "Please specify a PR to review. Examples:\n"
                    "- `review https://github.com/org/repo/pull/42`\n"
                    "- `review PR #42 in org/repo`"
                )
        else:
            parts = self._parse_github_url(pr_url)
            if not parts:
                parts = self._parse_gitlab_url(pr_url)
            if not parts:
                return f"Could not parse PR URL: {pr_url}"
            repo_name, pr_number = parts

        session.current_target = pr_url or f"{repo_name}#{pr_number}"
        session.metadata["review_target"] = {"repo": repo_name, "pr": pr_number}

        if not self.github:
            return "No GitHub/GitLab client configured."

        try:
            pr_ctx = self.github.get_pr_context(repo_name, pr_number)
            return await self._run_review(pr_ctx, repo_name)
        except Exception as e:
            logger.exception("PR review failed")
            return f"Failed to review PR: {e}"

    async def _run_review(self, pr_ctx, repo_name: str) -> str:
        """Run the review pipeline: skills, prompts, orchestrator."""
        skill_prompts = ""
        lang_rules: list[dict] = []
        if self.skill_loader:
            langs = detect_languages(pr_ctx.files)
            skill_prompts = self.skill_loader.get_prompts_for_languages(langs)
            lang_rules = self.skill_loader.get_rules_for_languages(langs)

            # Tier 3: project-local .code-review/
            local_prompts, local_rules = await self._load_project_config(
                repo_name, pr_ctx.branch
            )
            if local_prompts:
                skill_prompts += "\n\n" + local_prompts
            lang_rules.extend(local_rules)

        from code_review_agent.core.diff_parser import DiffParser
        diff_text = DiffParser().diff_to_text(pr_ctx.files)
        result = await self.core_engine.review(
            pr_ctx, diff_text, skill_prompts, custom_rules=lang_rules,
        )
        return (
            f"Reviewing PR #{pr_ctx.pr_number} in {repo_name}...\n\n"
            + format_result(result)
        )

    async def _load_project_config(self, repo_name: str, branch: str) -> tuple[str, list[dict]]:
        if not self.github or not self.skill_loader:
            return "", []
        prompt = ""
        rules: list[dict] = []
        try:
            content = self.github.get_file_content(repo_name, ".code-review/review.md", ref=branch)
            if content:
                logger.info("Loaded .code-review/review.md from %s", repo_name)
                prompt = self.skill_loader.load_project_prompt(content)
        except Exception:
            pass
        try:
            content = self.github.get_file_content(repo_name, ".code-review/rules.yaml", ref=branch)
            if content:
                rules = self.skill_loader.load_project_rules(content)
                logger.info("Loaded .code-review/rules.yaml from %s (%d rules)", repo_name, len(rules))
        except Exception:
            pass
        return prompt, rules

    @staticmethod
    def _parse_github_url(url: str) -> tuple[str, int] | None:
        import re
        m = re.match(r"https?://github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)", url)
        if m:
            return m.group(1), int(m.group(2))
        return None

    @staticmethod
    def _parse_gitlab_url(url: str) -> tuple[str, int] | None:
        import re
        m = re.match(r"https?://gitlab\.com/([\w.-]+/[\w.-]+)/-/merge_requests/(\d+)", url)
        if m:
            return m.group(1), int(m.group(2))
        return None
