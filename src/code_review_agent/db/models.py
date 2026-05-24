import json
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class ReviewRecord(Base):
    __tablename__ = "review_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(32), nullable=False)
    repo_name = Column(String(255), nullable=False)
    pr_number = Column(Integer, nullable=False)
    pr_title = Column(String(512))
    pr_url = Column(String(1024))
    author = Column(String(255))
    branch = Column(String(255))
    base_branch = Column(String(255))
    risk_level = Column(String(32))
    findings_count = Column(Integer, default=0)
    findings_json = Column(Text)
    summary = Column(Text)
    review_duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def set_findings(self, findings: list) -> None:
        self.findings_count = len(findings)
        self.findings_json = json.dumps(
            [f.model_dump() for f in findings], ensure_ascii=False
        )

    def get_findings(self) -> list[dict]:
        if self.findings_json:
            return json.loads(self.findings_json)
        return []
