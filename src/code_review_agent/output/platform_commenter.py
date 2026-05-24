from code_review_agent.models.review import ReviewResult


class PlatformCommenter:
    """Posts review results as PR comments on Git platforms."""

    def __init__(self, github_client=None, gitlab_client=None):
        self.github = github_client
        self.gitlab = gitlab_client

    async def post(
        self,
        result: ReviewResult,
        repo_name: str,
        pr_number: int,
        commit_sha: str,
        platform: str = "github",
    ) -> bool:
        if platform == "github" and self.github:
            self.github.post_review_comments(repo_name, pr_number, commit_sha, result.findings)
            self.github.post_pr_summary(repo_name, pr_number, self._build_summary(result))
            return True
        elif platform == "gitlab" and self.gitlab:
            await self.gitlab.post_review_comments(repo_name, pr_number, result.findings)
            return True
        return False

    @staticmethod
    def _build_summary(result: ReviewResult) -> str:
        risk_emoji = {
            "critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢",
        }.get(result.risk_level, "⚪")

        lines = [
            f"# 🤖 Code Review: {result.pr_title}",
            f"",
            f"**Risk Level**: {risk_emoji} {result.risk_level.upper()}",
            f"**Branch**: {result.branch} → {result.base_branch}",
            f"**Author**: {result.author}",
            f"**Findings**: {result.stats.total} issues",
            f"",
            f"| Severity | Count |",
            f"|----------|-------|",
        ]
        for sev, count in result.stats.by_severity.items():
            lines.append(f"| {sev} | {count} |")
        lines.append("")
        lines.append(f"**Summary**: {result.summary}")
        lines.append(f"")
        lines.append(f"⏱️ Review completed in {result.review_duration_ms}ms")
        return "\n".join(lines)
