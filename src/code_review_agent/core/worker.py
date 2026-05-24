"""Celery worker for async review processing."""

import logging

from celery import Celery

from code_review_agent.config import get_config

logger = logging.getLogger(__name__)

config = get_config()
broker_url = config.get("celery", "broker_url", default="redis://localhost:6379/1")
result_backend = config.get("celery", "result_backend", default="redis://localhost:6379/2")

celery_app = Celery(
    "code_review_agent",
    broker=broker_url,
    backend=result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max per review
)


@celery_app.task(name="review_pr_task")
def review_pr_task(repo_name: str, pr_number: int, platform: str = "github"):
    """Async task to review a PR."""
    logger.info("Starting review for %s PR #%d", repo_name, pr_number)

    # This will be wired up with the full app context in production
    # For now, it's a placeholder that can be expanded
    return {
        "status": "queued",
        "repo": repo_name,
        "pr": pr_number,
        "platform": platform,
    }
