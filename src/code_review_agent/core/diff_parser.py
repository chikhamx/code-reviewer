import re
from pathlib import Path

from code_review_agent.models.platform import DiffFile, DiffHunk


class DiffParser:
    """Parses unified diff output into structured DiffFile objects."""

    FILE_HEADER_RE = re.compile(r"^diff --git a/(.+) b/(.+)$")
    HUNK_HEADER_RE = re.compile(r"^@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@(.*)$")
    LANGUAGE_MAP = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".tsx": "typescript", ".jsx": "javascript", ".go": "go",
        ".rs": "rust", ".java": "java", ".kt": "kotlin", ".swift": "swift",
        ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
        ".rb": "ruby", ".php": "php", ".cs": "csharp", ".scala": "scala",
        ".sql": "sql", ".sh": "bash", ".yaml": "yaml", ".yml": "yaml",
        ".json": "json", ".xml": "xml", ".html": "html", ".css": "css",
        ".md": "markdown", ".toml": "toml",
    }

    def parse(self, diff_text: str) -> list[DiffFile]:
        files: list[DiffFile] = []
        current_file: DiffFile | None = None
        current_hunk_lines: list[str] = []
        additions = 0
        deletions = 0
        in_hunk = False

        for line in diff_text.split("\n"):
            fm = self.FILE_HEADER_RE.match(line)
            if fm:
                if current_file:
                    self._finalize_hunk(
                        current_file, current_hunk_lines, additions, deletions
                    )
                current_file = DiffFile(
                    path=fm.group(2),
                    old_path=fm.group(1),
                    language=self._detect_language(fm.group(2)),
                )
                current_hunk_lines = []
                additions = 0
                deletions = 0
                in_hunk = False
                files.append(current_file)
                continue

            if current_file is None:
                # Check for other header formats
                if line.startswith("--- a/") or line.startswith("+++ b/"):
                    continue
                continue

            hm = self.HUNK_HEADER_RE.match(line)
            if hm:
                if in_hunk and current_hunk_lines:
                    self._append_hunk(current_file, current_hunk_lines)
                    current_hunk_lines = []
                in_hunk = True
                current_hunk_lines.append(line)
                continue

            if in_hunk:
                current_hunk_lines.append(line)
                if line.startswith("+"):
                    additions += 1
                elif line.startswith("-"):
                    deletions += 1

            # Detect status from non-diff headers
            if line.startswith("new file mode"):
                current_file.status = "added"
            elif line.startswith("deleted file mode"):
                current_file.status = "deleted"
            elif line.startswith("rename from"):
                current_file.status = "renamed"

        if current_file:
            self._finalize_hunk(current_file, current_hunk_lines, additions, deletions)

        return files

    def _append_hunk(self, file: DiffFile, lines: list[str]) -> None:
        header = lines[0]
        hm = self.HUNK_HEADER_RE.match(header)
        if hm:
            old_start = int(hm.group(1))
            old_count = int(hm.group(2) or "1")
            new_start = int(hm.group(3))
            new_count = int(hm.group(4) or "1")
            file.hunks.append(DiffHunk(
                header=header,
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                content="\n".join(lines),
                lines=lines,
            ))

    def _finalize_hunk(
        self, file: DiffFile, lines: list[str], additions: int, deletions: int
    ) -> None:
        if lines:
            self._append_hunk(file, lines)
        file.additions = additions
        file.deletions = deletions

    def _detect_language(self, path: str) -> str:
        suffix = Path(path).suffix.lower()
        return self.LANGUAGE_MAP.get(suffix, "")

    def diff_to_text(self, files: list[DiffFile], max_tokens: int = 80000) -> str:
        """Convert structured diff back to text, respecting token budget."""
        parts: list[str] = []
        token_estimate = 0
        chars_per_token = 3  # rough estimate

        for f in files:
            header = f"### {f.path} ({f.status}, +{f.additions}/-{f.deletions})\n"
            parts.append(header)
            token_estimate += len(header) // chars_per_token

            for hunk in f.hunks:
                content = hunk.content + "\n"
                part_tokens = len(content) // chars_per_token
                if token_estimate + part_tokens > max_tokens:
                    parts.append("... (truncated, diff too large)\n")
                    return "".join(parts)
                parts.append(content)
                token_estimate += part_tokens

        return "".join(parts)
