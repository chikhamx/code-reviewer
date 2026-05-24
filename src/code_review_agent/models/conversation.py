from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str  # user | assistant | system
    content: str
    msg_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SessionContext(BaseModel):
    session_id: str
    platform: str
    channel_id: str
    user_id: str
    user_name: str = ""
    history: list[dict] = Field(default_factory=list)
    current_intent: str | None = None
    current_target: str | None = None
    pinned_code: str | None = None
    chat_stage: str = "idle"  # idle → clarify → confirm → execute
    research_context: dict = Field(default_factory=dict)  # accumulated clarification data
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_active_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ttl: int = 3600

    @property
    def is_expired(self) -> bool:
        return (datetime.now(timezone.utc) - self.last_active_at).total_seconds() > self.ttl
