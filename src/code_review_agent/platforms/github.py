import logging
from typing import Any

from code_review_agent.models.platform import DiffFile, PRContext

logger = logging.getLogger(__name__)


class GitHubClient:
    """GitHub API wrapper for PR operations."""

    def __init__(self, token: str, base_url: str = "https://api.github.com"):
        try:
            from github import Github
            from github import GithubIntegration
        except ImportError:
            raise ImportError("PyGithub is required. pip install pygithub")

        self.client = Github(token, base_url=base_url) if token else Github()

    def get_pr_context(
        self, repo_name: str, pr_number: int,
    ) -> PRContext:
        repo = self.client.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        files: list[DiffFile] = []
        for pf in pr.get_files():
            df = DiffFile(
                path=pf.filename,
                status=pf.status,
                additions=pf.additions,
                deletions=pf.deletions,
            )
            if pf.patch:
                from code_review_agent.core.diff_parser import DiffParser
                parsed = DiffParser().parse(
                    f"diff --git a/{pf.filename} b/{pf.filename}\n{pf.patch}"
                )
                if parsed:
                    df.hunks = parsed[0].hunks
            files.append(df)

        return PRContext(
            platform="github",
            repo_name=repo_name,
            pr_number=pr_number,
            title=pr.title,
            description=pr.body or "",
            author=pr.user.login,
            branch=pr.head.ref,
            base_branch=pr.base.ref,
            url=pr.html_url,
            files=files,
            commit_sha=pr.head.sha,
            labels=[label.name for label in pr.labels],
        )

    def post_review_comments(
        self, repo_name: str, pr_number: int, commit_sha: str, findings: list
    ) -> None:
        """Post line-level review comments on a PR."""
        repo = self.client.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        for finding in findings:
            if not finding.line:
                continue
            try:
                pr.create_review_comment(
                    body=self._format_comment(finding),
                    commit_id=commit_sha,
                    path=finding.file,
                    line=finding.line,
                )
            except Exception as e:
                logger.warning("Failed to post comment on %s:%s: %s", finding.file, finding.line, e)

    def get_file_content(self, repo_name: str, path: str, ref: str = "") -> str | None:
        """Fetch a single file's content from the repo. Returns the decoded text or None."""
        try:
            repo = self.client.get_repo(repo_name)
            kwargs = {"path": path}
            if ref:
                kwargs["ref"] = ref
            content_file = repo.get_contents(**kwargs)
            if isinstance(content_file, list):
                content_file = content_file[0]
            return content_file.decoded_content.decode("utf-8")
        except Exception as e:
            logger.debug("Failed to fetch %s from %s: %s", path, repo_name, e)
            return None

    def post_pr_summary(self, repo_name: str, pr_number: int, summary: str) -> None:
        repo = self.client.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        pr.create_issue_comment(summary)

    @staticmethod
    def _format_comment(finding) -> str:
        icon = {
            "critical": "🔴", "error": "🟠", "warning": "🟡",
            "info": "🔵", "suggestion": "💡",
        }.get(finding.severity.value, "ℹ️")

        lines = [
            f"{icon} **{finding.severity.value.upper()}** — {finding.title}",
            f"**Category**: {finding.category.value}",
            f"",
            finding.message,
        ]
        if finding.suggestion:
            lines.extend(["", "**Suggestion**:", finding.suggestion])
        return "\n".join(lines)
