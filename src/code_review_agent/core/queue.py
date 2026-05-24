"""Async review job queue with concurrency control.

Review jobs from IM/API are enqueued and executed by asyncio Tasks
with a configurable Semaphore limiting concurrent executions.

Flow:
  1. Message → DB write → enqueue job → reply "queued" immediately
  2. Sub-agent picks up job → runs review → replies result
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ReviewJob:
    job_id: str
    session_id: str
    platform: str
    normalized: dict
    intent: str
    status: str = "queued"  # queued → running → done → failed
    queued_at: float = field(default_factory=time.monotonic)
    started_at: float = 0.0
    finished_at: float = 0.0
    result: Optional[str] = None
    error: Optional[str] = None
    position: int = 0


class ReviewQueue:
    """Manages concurrent review execution with backpressure."""

    def __init__(self, max_concurrency: int = 3):
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._jobs: dict[str, ReviewJob] = {}
        self._pending: list[ReviewJob] = []
        self.max_concurrency = max_concurrency
        self._runner: Optional[Callable] = None  # async fn(job) -> str

    @property
    def running_count(self) -> int:
        return sum(1 for j in self._jobs.values() if j.status == "running")

    @property
    def queued_count(self) -> int:
        return len(self._pending)

    def set_runner(self, runner: Callable):
        """Set the async function that executes a review job."""
        self._runner = runner

    async def submit(self, job: ReviewJob) -> str:
        """Submit a job. Returns an immediate status message.

        If a slot is free, the job starts immediately. Otherwise it's
        queued and will start when a slot opens.
        """
        self._jobs[job.job_id] = job

        if self.running_count >= self.max_concurrency:
            # All slots taken — queue it
            self._pending.append(job)
            job.position = len(self._pending)
            logger.info(
                "Job %s queued at position %d (running=%d, pending=%d)",
                job.job_id[:8], job.position, self.running_count, self.queued_count,
            )
            return self._format_queued(job)

        # Slot available — start immediately
        return await self._start_job(job)

    async def _start_job(self, job: ReviewJob) -> str:
        """Start a job in a background asyncio Task."""
        job.status = "running"
        job.started_at = time.monotonic()
        logger.info("Job %s started (running=%d)", job.job_id[:8], self.running_count + 1)

        async def _run():
            async with self._semaphore:
                try:
                    if self._runner:
                        job.result = await self._runner(job)
                    else:
                        job.result = "Review engine not available"
                    job.status = "done"
                except Exception as e:
                    logger.exception("Job %s failed", job.job_id[:8])
                    job.error = str(e)
                    job.status = "failed"
                finally:
                    job.finished_at = time.monotonic()
                    elapsed = job.finished_at - job.started_at
                    logger.info(
                        "Job %s completed: status=%s elapsed=%.1fs",
                        job.job_id[:8], job.status, elapsed,
                    )
                    # Dequeue next pending job
                    await self._dequeue_next()

        asyncio.create_task(_run())
        return self._format_started(job)

    async def _dequeue_next(self):
        """Start the next pending job if any."""
        if self._pending:
            job = self._pending.pop(0)
            await self._start_job(job)

    def get_job(self, job_id: str) -> Optional[ReviewJob]:
        return self._jobs.get(job_id)

    def get_stats(self) -> dict:
        return {
            "running": self.running_count,
            "queued": self.queued_count,
            "max_concurrency": self.max_concurrency,
            "total_jobs": len(self._jobs),
        }

    @staticmethod
    def _format_queued(job: ReviewJob) -> str:
        return (
            f"Review queued (#{job.position}). "
            f"Currently running {job.position - 1} review(s) ahead of you. "
            f"Results will be posted here when complete."
        )

    @staticmethod
    def _format_started(job: ReviewJob) -> str:
        return "Starting review... Results will be posted here shortly."

    @staticmethod
    def make_job_id() -> str:
        return uuid.uuid4().hex[:12]
