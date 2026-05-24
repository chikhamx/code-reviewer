import logging
import re

from code_review_agent.actions.base import BaseAction

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

        # Parse: "review branch <name> in <org/repo>" or "review branch <name>"
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

        # Default: compare against main/master
        base = "main"

        session.current_target = f"{repo_name}/compare/{base}...{branch}"
        session.metadata["review_target"] = {"repo": repo_name, "branch": branch}

        try:
            logger.info("Comparing %s...%s in %s", base, branch, repo_name)
            ctx = self.github.compare_branches(repo_name, base, branch)
            if not ctx:
                return f"Could not compare {base}...{branch} in {repo_name}. Does the branch exist?"

            # Detect languages and collect skill prompts/rules
            skill_prompts = ""
            lang_rules: list[dict] = []
            if self.skill_loader:
                langs = self._detect_languages(ctx.files)
                skill_prompts = self.skill_loader.get_prompts_for_languages(langs)
                lang_rules = self.skill_loader.get_rules_for_languages(langs)

            from code_review_agent.core.diff_parser import DiffParser
            diff_text = DiffParser().diff_to_text(ctx.files)
            result = await self.core_engine.review(ctx, diff_text, skill_prompts, custom_rules=lang_rules)

            return (
                f"Branch Review: {branch} (vs {base}) in {repo_name}\n"
                f"**Files changed**: {len(ctx.files)}\n\n"
                + self._format_result(result)
            )
        except Exception as e:
            logger.exception("Branch review failed")
            return f"Failed to review branch: {e}"

    def _format_result(self, result) -> str:
        from code_review_agent.models.review import ReviewResult
        icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
        r: ReviewResult = result
        lines = [
            f"## Review: {r.pr_title}",
            f"**Risk**: {icon.get(r.risk_level, '')} {r.risk_level.upper()}",
            f"**Findings**: {r.stats.total} issues",
            "",
        ]
        for f in r.findings:
            lines.append(
                f"- [{f.severity.value.upper()}] `{f.file}:{f.line}` — {f.message[:100]}"
            )
        if r.summary:
            lines.extend(["", f"**Summary**: {r.summary}"])
        return "\n".join(lines)

    @staticmethod
    def _detect_languages(files) -> list[str]:
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
