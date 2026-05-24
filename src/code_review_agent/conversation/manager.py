import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from code_review_agent.models.conversation import Message, SessionContext

logger = logging.getLogger(__name__)


class ConversationManager:
    """Session storage and lifecycle management. In-memory for now, Redis-backed for production."""

    def __init__(self, ttl: int = 3600, max_history: int = 20):
        self.ttl = ttl
        self.max_history = max_history
        self._sessions: dict[str, SessionContext] = {}

    async def get_or_create(
        self,
        session_id: str,
        platform: str = "",
        channel_id: str = "",
        user_id: str = "",
        user_name: str = "",
    ) -> SessionContext:
        now = datetime.now(timezone.utc)

        if session_id in self._sessions:
            session = self._sessions[session_id]
            if not session.is_expired:
                session.last_active_at = now
                return session
            del self._sessions[session_id]

        session = SessionContext(
            session_id=session_id,
            platform=platform,
            channel_id=channel_id,
            user_id=user_id,
            user_name=user_name,
            created_at=now,
            last_active_at=now,
            ttl=self.ttl,
        )
        self._sessions[session_id] = session
        return session

    async def save(self, session: SessionContext) -> None:
        session.last_active_at = datetime.now(timezone.utc)
        if len(session.history) > self.max_history:
            session.history = session.history[-self.max_history:]
        self._sessions[session.session_id] = session

    async def get(self, session_id: str) -> SessionContext | None:
        session = self._sessions.get(session_id)
        if session and session.is_expired:
            del self._sessions[session_id]
            return None
        return session

    async def expire(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _cleanup(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [
            sid for sid, s in self._sessions.items()
            if (now - s.last_active_at).total_seconds() > self.ttl
        ]
        for sid in expired:
            del self._sessions[sid]

    def get_stats(self) -> dict[str, Any]:
        self._cleanup()
        return {
            "active_sessions": len(self._sessions),
            "ttl": self.ttl,
        }
