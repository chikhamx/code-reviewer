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

    def compare_branches(self, repo_name: str, base: str, head: str) -> PRContext | None:
        """Compare two branches and return a PRContext-like object with the diff."""
        try:
            repo = self.client.get_repo(repo_name)
            comparison = repo.compare(base, head)

            files: list[DiffFile] = []
            for f in comparison.files:
                df = DiffFile(
                    path=f.filename,
                    status=f.status,
                    additions=f.additions,
                    deletions=f.deletions,
                )
                if f.patch:
                    from code_review_agent.core.diff_parser import DiffParser
                    parsed = DiffParser().parse(
                        f"diff --git a/{f.filename} b/{f.filename}\n{f.patch}"
                    )
                    if parsed:
                        df.hunks = parsed[0].hunks
                files.append(df)

            return PRContext(
                platform="github",
                repo_name=repo_name,
                pr_number=0,
                title=f"Branch: {head} (vs {base})",
                description=f"Comparing {head} against {base}",
                author="",
                branch=head,
                base_branch=base,
                url=f"https://github.com/{repo_name}/compare/{base}...{head}",
                files=files,
                commit_sha=comparison.merge_base_commit.sha if comparison.merge_base_commit else "",
            )
        except Exception as e:
            logger.error("Failed to compare %s...%s in %s: %s", base, head, repo_name, e)
            return None

    def get_commit_diff(self, repo_name: str, commit_sha: str) -> PRContext | None:
        """Get a single commit's diff as a PRContext-like object."""
        try:
            repo = self.client.get_repo(repo_name)
            commit = repo.get_commit(commit_sha)

            files: list[DiffFile] = []
            for f in commit.files:
                df = DiffFile(
                    path=f.filename,
                    status=f.status,
                    additions=f.additions,
                    deletions=f.deletions,
                )
                if f.patch:
                    from code_review_agent.core.diff_parser import DiffParser
                    parsed = DiffParser().parse(
                        f"diff --git a/{f.filename} b/{f.filename}\n{f.patch}"
                    )
                    if parsed:
                        df.hunks = parsed[0].hunks
                files.append(df)

            msg = commit.commit.message if hasattr(commit, 'commit') else ""
            author = commit.author.login if commit.author else ""
            date_str = commit.commit.author.date.isoformat() if hasattr(commit, 'commit') and commit.commit.author else ""

            return PRContext(
                platform="github",
                repo_name=repo_name,
                pr_number=0,
                title=f"Commit {commit_sha[:7]}: {msg[:80].split(chr(10))[0]}",
                description=msg,
                author=author,
                branch="",
                base_branch="",
                url=commit.html_url,
                files=files,
                commit_sha=commit_sha,
            )
        except Exception as e:
            logger.error("Failed to get commit %s in %s: %s", commit_sha[:8], repo_name, e)
            return None

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
