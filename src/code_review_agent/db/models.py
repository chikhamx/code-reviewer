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


class MessageRecord(Base):
    """A single message in a review thread chain."""

    __tablename__ = "messages"

    message_id = Column(String(64), primary_key=True)
    session_id = Column(String(128), nullable=False, index=True)
    root_id = Column(String(64), index=True)
    parent_id = Column(String(64))
    role = Column(String(16), nullable=False)      # trigger | review | user | assistant
    source_type = Column(String(32))                # push | pr | manual_chat
    content = Column(Text)
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    @property
    def metadata_dict(self) -> dict:
        return json.loads(self.metadata_json) if self.metadata_json else {}

    def set_metadata(self, data: dict) -> None:
        self.metadata_json = json.dumps(data, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "session_id": self.session_id,
            "root_id": self.root_id,
            "parent_id": self.parent_id,
            "role": self.role,
            "source_type": self.source_type,
            "content": self.content,
            "metadata": self.metadata_dict,
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }


class SessionRecord(Base):
    """Per-group session state."""

    __tablename__ = "sessions"

    session_id = Column(String(128), primary_key=True)
    platform = Column(String(32))
    active_thread_id = Column(String(64))
    history_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def get_history(self) -> list[dict]:
        return json.loads(self.history_json) if self.history_json else []

    def set_history(self, history: list[dict]) -> None:
        self.history_json = json.dumps(history, ensure_ascii=False)
