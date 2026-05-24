import logging
from typing import Any

import httpx

from code_review_agent.models.platform import DiffFile, PRContext

logger = logging.getLogger(__name__)


class GitLabClient:
    """GitLab API wrapper for MR operations."""

    def __init__(self, url: str = "https://gitlab.com", token: str = ""):
        self.url = url.rstrip("/")
        self.token = token
        self._headers = {"PRIVATE-TOKEN": token} if token else {}

    async def _api(self, path: str, method: str = "GET", **kwargs) -> dict[str, Any]:
        api_url = f"{self.url}/api/v4{path}"
        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method, api_url, headers=self._headers, **kwargs,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_pr_context(self, repo_name: str, mr_number: int) -> PRContext:
        encoded_repo = repo_name.replace("/", "%2F")
        mr_data = await self._api(f"/projects/{encoded_repo}/merge_requests/{mr_number}")
        changes_data = await self._api(
            f"/projects/{encoded_repo}/merge_requests/{mr_number}/changes"
        )

        files: list[DiffFile] = []
        for change in changes_data.get("changes", []):
            df = DiffFile(
                path=change.get("new_path", ""),
                old_path=change.get("old_path"),
                status=self._map_status(change),
                additions=change.get("additions", 0),
                deletions=change.get("deletions", 0),
            )
            diff_content = change.get("diff", "")
            if diff_content:
                from code_review_agent.core.diff_parser import DiffParser
                parsed = DiffParser().parse(diff_content)
                if parsed:
                    df.hunks = parsed[0].hunks
            files.append(df)

        return PRContext(
            platform="gitlab",
            repo_name=repo_name,
            pr_number=mr_number,
            title=mr_data.get("title", ""),
            description=mr_data.get("description", ""),
            author=mr_data.get("author", {}).get("username", ""),
            branch=mr_data.get("source_branch", ""),
            base_branch=mr_data.get("target_branch", ""),
            url=mr_data.get("web_url", ""),
            files=files,
            commit_sha=mr_data.get("sha"),
            labels=mr_data.get("labels", []),
        )

    async def post_review_comments(
        self, repo_name: str, mr_number: int, findings: list,
    ) -> None:
        """Post line-level review comments on a GitLab MR."""
        encoded_repo = repo_name.replace("/", "%2F")
        for finding in findings:
            if not finding.line:
                continue
            try:
                await self._api(
                    f"/projects/{encoded_repo}/merge_requests/{mr_number}/discussions",
                    method="POST",
                    json={
                        "body": self._format_comment(finding),
                        "position": {
                            "position_type": "text",
                            "new_path": finding.file,
                            "new_line": finding.line,
                            "base_sha": "",
                            "start_sha": "",
                            "head_sha": "",
                        },
                    },
                )
            except Exception as e:
                logger.warning(
                    "Failed to post GitLab comment on %s:%s: %s",
                    finding.file, finding.line, e,
                )

    @staticmethod
    def _map_status(change: dict) -> str:
        if change.get("new_file"):
            return "added"
        if change.get("deleted_file"):
            return "deleted"
        if change.get("renamed_file"):
            return "renamed"
        return "modified"

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
