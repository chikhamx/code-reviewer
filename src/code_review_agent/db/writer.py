"""Background writer for SQLite — batches writes on a single thread.

SQLite doesn't handle concurrent writes well. All INSERT/UPDATE/DELETE
operations are queued and executed sequentially on a background thread,
avoiding "database is locked" errors and keeping the main event loop
responsive.
"""

import logging
import queue
import threading
import time
from typing import Callable, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class WriteOp:
    """A single write operation to be executed on the DB thread."""

    def __init__(self, fn: Callable[[Session], None], name: str = ""):
        self.fn = fn
        self.name = name
        self.done = threading.Event()
        self.error: Optional[Exception] = None

    def execute(self, session: Session) -> None:
        try:
            self.fn(session)
            session.commit()
        except Exception as e:
            session.rollback()
            self.error = e
            logger.error("DB write '%s' failed: %s", self.name, e)
        finally:
            self.done.set()

    def wait(self, timeout: float = 10.0) -> None:
        if not self.done.wait(timeout):
            logger.warning("DB write '%s' timed out after %.1fs", self.name, timeout)


class DBWriter:
    """Background thread that consumes a queue of WriteOp objects.

    All SQLAlchemy writes go through this single thread to avoid
    SQLite concurrency issues.
    """

    def __init__(self, session_factory):
        self._queue: queue.Queue[WriteOp] = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._session_factory = session_factory

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="db-writer", daemon=True)
        self._thread.start()
        logger.info("DB writer thread started")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("DB writer thread stopped")

    def enqueue(self, fn: Callable[[Session], None], name: str = "") -> WriteOp:
        op = WriteOp(fn, name)
        self._queue.put(op)
        return op

    def enqueue_and_wait(self, fn: Callable[[Session], None], name: str = "", timeout: float = 10.0) -> None:
        op = self.enqueue(fn, name)
        op.wait(timeout)
        if op.error:
            raise op.error

    def _loop(self) -> None:
        while self._running:
            try:
                op = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            session = self._session_factory()
            try:
                op.execute(session)
            finally:
                session.close()
