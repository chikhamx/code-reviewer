"""Message-chain based session store.

All writes go through DBWriter (background thread). Reads are synchronous
(SQLite is fast enough for single-reader access).
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from code_review_agent.db.models import MessageRecord, SessionRecord
from code_review_agent.db.writer import DBWriter

logger = logging.getLogger(__name__)


class MessageChainStore:
    """Persistent store for message chains and session state."""

    def __init__(self, session_factory):
        self._session_factory = session_factory
        self.writer = DBWriter(session_factory)

    def start(self) -> None:
        self.writer.start()

    def stop(self) -> None:
        self.writer.stop()

    # ── Reads (synchronous, on caller thread) ──

    def get_message(self, message_id: str) -> Optional[dict]:
        """Get a single message by ID."""
        session = self._session_factory()
        try:
            row = session.get(MessageRecord, message_id)
            return row.to_dict() if row else None
        finally:
            session.close()

    def get_chain(self, message_id: str) -> list[dict]:
        """Walk the parent chain from message_id up to root.

        Returns [most_recent, ..., root] — empty list if message not found.
        """
        chain = []
        current = message_id
        seen: set[str] = set()
        session = self._session_factory()
        try:
            while current and current not in seen:
                seen.add(current)
                row = session.get(MessageRecord, current)
                if not row:
                    break
                chain.append(row.to_dict())
                current = row.parent_id
        finally:
            session.close()
        return chain

    def build_context(self, message_id: str) -> dict:
        """Build full review context from message chain or thread.

        First walks the parent chain. If no review found there, searches
        the entire thread (same root_id) for a review message.
        """
        chain = self.get_chain(message_id)
        findings = []
        review_msg = None
        trigger = {}
        thread_id = ""
        recent: list[str] = []

        if chain:
            for m in chain:
                if m["role"] == "review" and m.get("metadata", {}).get("findings"):
                    findings = m["metadata"]["findings"]
                    review_msg = m
                    break
            trigger = chain[-1].get("metadata", {}) if chain[-1] else {}
            thread_id = chain[-1].get("root_id") or chain[-1]["message_id"]
            recent = [m["content"] for m in chain[:5] if m.get("content")]

        # Fallback: search the whole thread for a review message
        if not findings and thread_id:
            session = self._session_factory()
            try:
                from sqlalchemy import select
                from code_review_agent.db.models import MessageRecord
                stmt = (
                    select(MessageRecord)
                    .where(MessageRecord.root_id == thread_id)
                    .where(MessageRecord.role == "review")
                    .order_by(MessageRecord.created_at.desc())
                    .limit(1)
                )
                row = session.execute(stmt).scalar_one_or_none()
                if row:
                    meta = row.metadata_dict
                    if meta.get("findings"):
                        findings = meta["findings"]
                        review_msg = row.to_dict()
                        thread_id = row.root_id or thread_id
            finally:
                session.close()

        return {
            "findings": findings,
            "trigger": trigger,
            "recent_messages": recent,
            "thread_id": thread_id,
            "review_message": review_msg,
        }

    def get_session(self, session_id: str) -> Optional[dict]:
        session = self._session_factory()
        try:
            row = session.get(SessionRecord, session_id)
            if not row:
                return None
            return {
                "session_id": row.session_id,
                "platform": row.platform,
                "active_thread_id": row.active_thread_id,
                "history": row.get_history(),
            }
        finally:
            session.close()

    # ── Writes (async, queued to background thread) ──

    def save_message(self, message_id: str, session_id: str, *,
                     root_id: str = "", parent_id: str = "",
                     role: str = "user", source_type: str = "",
                     content: str = "", metadata: dict | None = None) -> None:
        """Queue a message to be persisted."""
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)

        def _write(s: OrmSession) -> None:
            existing = s.get(MessageRecord, message_id)
            if existing:
                existing.content = content
                existing.metadata_json = meta_json
            else:
                s.add(MessageRecord(
                    message_id=message_id,
                    session_id=session_id,
                    root_id=root_id or message_id,
                    parent_id=parent_id,
                    role=role,
                    source_type=source_type,
                    content=content,
                    metadata_json=meta_json,
                ))

        self.writer.enqueue(_write, f"save_msg:{message_id[:16]}")

    def save_session(self, session_id: str, *, platform: str = "",
                     active_thread_id: str = "", history: list[dict] | None = None) -> None:
        def _write(s: OrmSession) -> None:
            row = s.get(SessionRecord, session_id)
            if row:
                if active_thread_id:
                    row.active_thread_id = active_thread_id
                if history is not None:
                    row.set_history(history)
            else:
                s.add(SessionRecord(
                    session_id=session_id,
                    platform=platform,
                    active_thread_id=active_thread_id,
                    history_json=json.dumps(history or [], ensure_ascii=False),
                ))

        self.writer.enqueue(_write, f"save_session:{session_id[:32]}")
