from pydantic import BaseModel, Field


class DiffHunk(BaseModel):
    header: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    content: str
    lines: list[str] = Field(default_factory=list)


class DiffFile(BaseModel):
    path: str
    old_path: str | None = None
    status: str = "modified"  # added | modified | deleted | renamed
    language: str = ""
    hunks: list[DiffHunk] = Field(default_factory=list)
    additions: int = 0
    deletions: int = 0


class PRContext(BaseModel):
    platform: str  # github | gitlab
    repo_name: str
    pr_number: int
    title: str
    description: str = ""
    author: str
    branch: str
    base_branch: str
    url: str
    files: list[DiffFile] = Field(default_factory=list)
    commit_sha: str | None = None
    labels: list[str] = Field(default_factory=list)
