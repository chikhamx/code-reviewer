import logging
from typing import AsyncGenerator

from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from code_review_agent.db.models import Base, ReviewRecord

logger = logging.getLogger(__name__)

_async_engine = None
_async_session_factory: async_sessionmaker | None = None


async def init_db(database_url: str) -> None:
    global _async_engine, _async_session_factory

    # Convert sync SQLite URL to async
    if database_url.startswith("sqlite:///"):
        database_url = database_url.replace("sqlite:///", "sqlite+aiosqlite:///")

    _async_engine = create_async_engine(database_url, echo=False)

    async with _async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    _async_session_factory = async_sessionmaker(_async_engine, expire_on_commit=False)
    logger.info("Database initialized")


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
        stmt = (
            select(ReviewRecord)
            .where(ReviewRecord.repo_name == repo_name)
            .order_by(ReviewRecord.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
