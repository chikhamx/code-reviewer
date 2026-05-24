from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class FindingSeverity(str, Enum):
    critical = "critical"
    error = "error"
    warning = "warning"
    info = "info"
    suggestion = "suggestion"


class FindingCategory(str, Enum):
    bug_risk = "bug_risk"
    security = "security"
    performance = "performance"
    maintainability = "maintainability"
    style = "style"
    documentation = "documentation"


class Finding(BaseModel):
    file: str
    line: int | None = None
    column: int | None = None
    severity: FindingSeverity
    category: FindingCategory
    title: str
    message: str
    suggestion: str | None = None
    rule_id: str | None = None
    code_snippet: str | None = None


class ReviewStats(BaseModel):
    total: int = 0
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)


class ReviewResult(BaseModel):
    pr_title: str
    pr_url: str
    pr_number: int
    branch: str
    base_branch: str
    repo_name: str
    author: str
    risk_level: str = "low"
    summary: str = ""
    findings: list[Finding] = Field(default_factory=list)
    stats: ReviewStats = Field(default_factory=ReviewStats)
    reviewed_at: datetime = Field(default_factory=datetime.utcnow)
    review_duration_ms: int = 0

    def compute_stats(self) -> None:
        self.stats = ReviewStats(total=len(self.findings))
        for f in self.findings:
            sev = f.severity.value
            cat = f.category.value
            self.stats.by_severity[sev] = self.stats.by_severity.get(sev, 0) + 1
            self.stats.by_category[cat] = self.stats.by_category.get(cat, 0) + 1
        self._compute_risk_level()

    def _compute_risk_level(self) -> None:
        critical = self.stats.by_severity.get("critical", 0)
        errors = self.stats.by_severity.get("error", 0)
        if critical > 0:
            self.risk_level = "critical"
        elif errors > 3:
            self.risk_level = "high"
        elif errors > 0:
            self.risk_level = "medium"
        else:
            self.risk_level = "low"
