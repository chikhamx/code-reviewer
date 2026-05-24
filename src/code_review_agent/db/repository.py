import logging
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from code_review_agent.db.models import Base, ReviewRecord

logger = logging.getLogger(__name__)

_async_engine = None
_async_session_factory: async_sessionmaker | None = None
_sync_engine = None
_sync_session_factory: sessionmaker | None = None


async def init_db(database_url: str) -> None:
    global _async_engine, _async_session_factory
    global _sync_engine, _sync_session_factory

    # Async engine
    if database_url.startswith("sqlite:///"):
        async_url = database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
    else:
        async_url = database_url

    _async_engine = create_async_engine(async_url, echo=False)
    async with _async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    _async_session_factory = async_sessionmaker(_async_engine, expire_on_commit=False)

    # Sync engine (for background writer thread)
    sync_url = database_url.replace("sqlite+aiosqlite:///", "sqlite:///")
    _sync_engine = create_engine(sync_url, echo=False)
    Base.metadata.create_all(_sync_engine)
    _sync_session_factory = sessionmaker(_sync_engine, expire_on_commit=False)

    logger.info("Database initialized (async + sync)")


def get_sync_session_factory() -> sessionmaker:
    if _sync_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _sync_session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if _async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _async_session_factory() as session:
        yield session


async def save_review_record(record: ReviewRecord) -> ReviewRecord:
    if _async_session_factory is None:
        raise RuntimeError("Database not initialized.")
    async with _async_session_factory() as session:
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record


async def get_review_history(repo_name: str, limit: int = 20) -> list[ReviewRecord]:
    if _async_session_factory is None:
        raise RuntimeError("Database not initialized.")
    async with _async_session_factory() as session:
        from sqlalchemy import select
        stmt = (
            select(ReviewRecord)
            .where(ReviewRecord.repo_name == repo_name)
            .order_by(ReviewRecord.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
