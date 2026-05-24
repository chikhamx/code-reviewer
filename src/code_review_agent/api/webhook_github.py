"""GitHub webhook receiver.

GitHub sends webhook events when a PR is opened, updated, or reopened.
The agent verifies the signature, fetches the PR diff, runs the review
pipeline, and posts findings as a PR comment (if configured).

For local dev without a public URL, use ngrok to expose :8000 and
set the GitHub webhook URL to https://xxxx.ngrok-free.app/api/github/webhook.
"""

import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from code_review_agent.config import get_config

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/webhook")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
):
    """Receive GitHub webhook events and trigger automated code review."""
    body = await request.body()
    body_str = body.decode("utf-8")

    # Verify HMAC signature
    cfg = get_config()
    secret = cfg.get("github", "webhook_secret", default="")
    if secret:
        expected = "sha256=" + hmac.new(
            secret.encode(), body, hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, x_hub_signature_256):
            logger.warning("GitHub webhook: invalid signature")
            raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    action = payload.get("action", "")
    event = x_github_event

    logger.info("GitHub webhook: event=%s action=%s", event, action)

    # Ping event — webhook setup verification
    if event == "ping":
        hook = payload.get("hook", {})
        logger.info("GitHub webhook ping OK (events=%s)", hook.get("events", []))
        return {"status": "ok", "message": "Webhook configured correctly"}

    # PR events that should trigger review
    if event == "pull_request" and action in ("opened", "synchronize", "reopened"):
        pr = payload.get("pull_request", {})
        repo = payload.get("repository", {})
        repo_name = repo.get("full_name", "")
        pr_number = pr.get("number", 0)
        pr_url = pr.get("html_url", "")
        base_branch = pr.get("base", {}).get("ref", "")
        head_branch = pr.get("head", {}).get("ref", "")

        logger.info(
            "PR #%d %s in %s (%s -> %s)",
            pr_number, action, repo_name, head_branch, base_branch,
        )

        # Get the app context and run review asynchronously
        state = request.app.state

        if not hasattr(state, "orchestrator") or state.orchestrator is None:
            logger.warning("Orchestrator not available, review skipped")
            return {"status": "skipped", "reason": "orchestrator_unavailable"}

        if not hasattr(state, "github_client") or state.github_client is None:
            logger.warning("GitHub client not configured, review skipped")
            return {"status": "skipped", "reason": "github_client_unavailable"}

        try:
            # Fetch PR diff and run review
            logger.info("Starting review for %s#%d", repo_name, pr_number)
            diff_text = await state.github_client.get_pr_diff(repo_name, pr_number)

            result = await state.orchestrator.review(
                diff_text=diff_text,
                repo_name=repo_name,
                pr_number=pr_number,
            )

            # Try to post review as PR comment via GitHub API
            commenter = getattr(state, "platform_commenter", None)
            if commenter:
                await commenter.post_review(repo_name, pr_number, result)

            logger.info(
                "Review complete for %s#%d: %d findings",
                repo_name, pr_number, len(result.findings) if result else 0,
            )

            return {
                "status": "reviewed",
                "repo": repo_name,
                "pr": pr_number,
                "url": pr_url,
            }
        except Exception as e:
            logger.exception("Review failed for %s#%d", repo_name, pr_number)
            return {"status": "error", "message": str(e)}

    # Push event — could trigger branch review
    if event == "push":
        repo = payload.get("repository", {})
        repo_name = repo.get("full_name", "")
        ref = payload.get("ref", "")
        commits = payload.get("commits", [])
        logger.info(
            "Push to %s (%s): %d commits",
            repo_name, ref, len(commits),
        )
        return {
            "status": "received",
            "repo": repo_name,
            "ref": ref,
            "commits": len(commits),
            "message": "Push review not yet implemented",
        }

    return {"status": "ignored", "event": event, "action": action}
