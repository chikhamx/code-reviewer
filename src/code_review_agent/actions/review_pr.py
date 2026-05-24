from code_review_agent.actions.base import BaseAction
from code_review_agent.router.intent_router import IntentRouter


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
            # Try to parse "review PR #42 in owner/repo"
            import re
            match = re.search(
                r"(?:review|审查)\s*(?:PR|pull|mr)?\s*#?\s*(\d+)\s*(?:in|of|for)?\s*([\w.-]+/[\w.-]+)",
                text,
                re.IGNORECASE,
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

        # Fetch PR context and diff
        if self.github:
            try:
                pr_ctx = self.github.get_pr_context(repo_name, pr_number)

                # Collect skill rules and prompts based on file languages
                skill_prompts = ""
                lang_rules: list[dict] = []
                if self.skill_loader:
                    langs = self._detect_languages(pr_ctx.files)
                    # Tier 1+2: global + language-specific prompts
                    skill_prompts = self.skill_loader.get_prompts_for_languages(langs)
                    # Tier 2: language-specific rules
                    lang_rules = self.skill_loader.get_rules_for_languages(langs)

                    # Tier 3: project-local .code-review/ from the PR's repo
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
                    f"🔍 Reviewing PR #{pr_number} in {repo_name}...\n\n"
                    + self._format_result(result)
                )
            except Exception as e:
                return f"Failed to review PR: {e}"

        return "No GitHub/GitLab client configured."

    def _format_result(self, result) -> str:
        icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
        lines = [
            f"## Code Review: {result.pr_title}",
            f"**Risk**: {icon.get(result.risk_level, '')} {result.risk_level.upper()}",
            f"**Findings**: {result.stats.total} issues",
            "",
        ]
        for f in result.findings:
            lines.append(
                f"- [{f.severity.value.upper()}] `{f.file}:{f.line}` — {f.message[:100]}"
            )
        if result.summary:
            lines.extend(["", f"**Summary**: {result.summary}"])
        return "\n".join(lines)

    @staticmethod
    def _parse_github_url(url: str) -> tuple[str, int] | None:
        import re
        m = re.match(r"https?://github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)", url)
        if m:
            return m.group(1), int(m.group(2))
        return None

    async def _load_project_config(self, repo_name: str, branch: str) -> tuple[str, list[dict]]:
        """Try to load .code-review/review.md and rules.yaml from the PR repo."""
        if not self.github or not self.skill_loader:
            return "", []
        prompt = ""
        rules: list[dict] = []
        try:
            content = self.github.get_file_content(
                repo_name, ".code-review/review.md", ref=branch
            )
            if content:
                logger.info("Loaded .code-review/review.md from %s", repo_name)
                prompt = self.skill_loader.load_project_prompt(content)
        except Exception:
            pass
        try:
            content = self.github.get_file_content(
                repo_name, ".code-review/rules.yaml", ref=branch
            )
            if content:
                rules = self.skill_loader.load_project_rules(content)
                logger.info("Loaded .code-review/rules.yaml from %s (%d rules)", repo_name, len(rules))
        except Exception:
            pass
        return prompt, rules

    @staticmethod
    def _detect_languages(files) -> list[str]:
        """Detect programming languages from file extensions in the PR."""
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
            ".c": "c", ".cpp": "cpp", ".h": "c",
            ".rb": "ruby", ".php": "php", ".swift": "swift",
            ".yaml": "yaml", ".yml": "yaml", ".json": "json",
            ".tf": "terraform", ".sh": "shell", ".sql": "sql",
            ".md": "markdown", ".css": "css", ".html": "html",
        }
        exts = set()
        for f in files:
            path = getattr(f, "path", "") if hasattr(f, "path") else str(f)
            for ext, lang in ext_map.items():
                if path.endswith(ext):
                    exts.add(lang)
                    break
        return sorted(exts)

    @staticmethod
    def _parse_gitlab_url(url: str) -> tuple[str, int] | None:
        import re
        m = re.match(r"https?://gitlab\.com/([\w.-]+/[\w.-]+)/-/merge_requests/(\d+)", url)
        if m:
            return m.group(1), int(m.group(2))
        return None
