import logging
from typing import Optional

from code_review_agent.actions.base import ActionDispatcher
from code_review_agent.conversation.manager import ConversationManager
from code_review_agent.core.queue import ReviewJob, ReviewQueue
from code_review_agent.im.normalizer import MessageNormalizer
from code_review_agent.im.sender import IMSender
from code_review_agent.router.intent_router import Intent, IntentRouter

logger = logging.getLogger(__name__)

REVIEW_INTENTS = {Intent.REVIEW_PR, Intent.REVIEW_COMMIT, Intent.REVIEW_BRANCH}


class IMGateway:
    """Unified entry point for all IM platform messages."""

    def __init__(
        self,
        normalizer: MessageNormalizer,
        sender: IMSender,
        intent_router: IntentRouter,
        action_dispatcher: ActionDispatcher,
        conversation_manager: ConversationManager,
        message_store=None,
        review_queue: ReviewQueue | None = None,
    ):
        self.normalizer = normalizer
        self.sender = sender
        self.intent_router = intent_router
        self.action_dispatcher = action_dispatcher
        self.conversations = conversation_manager
        self.store = message_store
        self.queue = review_queue

        # Wire the queue's runner to execute reviews
        if self.queue:
            self.queue.set_runner(self._run_review_job)

    async def handle_message(self, platform: str, raw: dict) -> dict:
        """Process a message: DB write → classify → queue or dispatch → reply."""
        # ── Step 1: Normalize ──
        try:
            normalized = self.normalizer.normalize(platform, raw)
        except Exception as e:
            logger.error("Failed to normalize %s message: %s", platform, e)
            return {"status": "error", "message": str(e)}

        msg_id = normalized.get("msg_id", "")
        session_id = normalized.get("session_id", "")
        text = normalized.get("text", "").strip()
        root_id = normalized.get("root_id", "")

        logger.info(
            ">>> GATEWAY: %s msg_id=%s text=%.80s root=%s",
            platform, msg_id, text, root_id or "-",
        )

        if not text:
            return {"status": "ok", "note": "empty message"}

        # ── Step 2: Write to DB FIRST ──
        if self.store and msg_id:
            msg_root = root_id or msg_id
            self.store.save_message(
                message_id=msg_id,
                session_id=session_id,
                root_id=msg_root,
                parent_id=root_id,
                role="user",
                source_type="im_message",
                content=text,
            )

        # ── Step 3: Chain context ──
        chain_ctx = {}
        if self.store and (root_id or msg_id):
            lookup = root_id or msg_id
            chain_ctx = self.store.build_context(lookup)

        # ── Step 4: Legacy session ──
        session = await self.conversations.get_or_create(
            session_id=session_id,
            platform=platform,
            channel_id=normalized.get("channel_id", ""),
            user_id=normalized.get("user_id", ""),
            user_name=normalized.get("user_name", ""),
        )

        # Dedup
        if msg_id and msg_id in session.metadata.get("processed_ids", []):
            return {"status": "ok", "dedup": True}
        if msg_id:
            session.metadata.setdefault("processed_ids", []).append(msg_id)
            if len(session.metadata["processed_ids"]) > 100:
                session.metadata["processed_ids"] = session.metadata["processed_ids"][-50:]

        # Inject chain findings
        if chain_ctx.get("findings"):
            session.last_review = {
                "title": chain_ctx.get("trigger", {}).get("title", ""),
                "repo": chain_ctx.get("trigger", {}).get("repo", ""),
                "findings": chain_ctx["findings"],
                "diff": chain_ctx.get("trigger", {}).get("diff", ""),
            }

        # ── Step 5: Classify intent ──
        intent = await self.intent_router.classify(text, session)
        if intent and intent.value == "chat" and chain_ctx.get("findings"):
            intent = Intent.SUGGEST_FIX
            logger.info(">>> GATEWAY: chat→suggest_fix (review context available)")
        session.current_intent = intent.value if intent else None
        logger.info(">>> GATEWAY: intent=%s", intent.value if intent else "unknown")

        # ── Step 6: Handle review intents via queue ──
        if intent in REVIEW_INTENTS and self.queue:
            job = ReviewJob(
                job_id=ReviewQueue.make_job_id(),
                session_id=session_id,
                platform=platform,
                normalized=normalized,
                intent=intent.value,
            )
            # Store session for the runner to use
            self.queue._jobs[job.job_id] = job
            # Attach extra data the runner needs
            self._attach_job_context(job, session)

            status_msg = await self.queue.submit(job)
            await self.sender.reply(platform, normalized, status_msg)

            session.history.append({"role": "user", "content": text})
            session.history.append({"role": "assistant", "content": status_msg})
            await self.conversations.save(session)
            return {"status": "ok", "intent": intent.value, "queued": True}

        # ── Step 7: Handle non-review intents synchronously ──
        try:
            response_text = await self.action_dispatcher.dispatch(intent, normalized, session)
        except Exception as e:
            logger.exception("Action dispatch failed for intent %s", intent)
            response_text = f"Sorry, something went wrong: {e}"

        session.history.append({"role": "user", "content": text})
        session.history.append({"role": "assistant", "content": response_text})
        if len(session.history) > 20:
            session.history = session.history[-20:]
        await self.conversations.save(session)

        real_reply_id = None
        try:
            real_reply_id = await self.sender.reply(platform, normalized, response_text)
            logger.info(">>> GATEWAY: reply sent id=%s", real_reply_id)
        except Exception as e:
            logger.error("Failed to send reply: %s", e)

        # Persist reply to chain
        if self.store and msg_id and real_reply_id:
            self.store.save_message(
                message_id=real_reply_id,
                session_id=session_id,
                root_id=root_id or msg_id,
                parent_id=msg_id,
                role="assistant",
                source_type="bot_reply",
                content=response_text,
            )

        return {"status": "ok", "intent": intent.value if intent else "unknown"}

    # ── Queue runner ──

    async def _run_review_job(self, job: ReviewJob) -> str:
        """Execute a review job in the queue. This runs in a background asyncio Task."""
        normalized = job.normalized

        # Re-create session (not safe to share across tasks)
        session = await self.conversations.get_or_create(
            session_id=job.session_id,
            platform=job.platform,
            channel_id=normalized.get("channel_id", ""),
            user_id=normalized.get("user_id", ""),
        )

        # Restore any attached context
        ctx_data = getattr(job, "_ctx", {})
        if ctx_data.get("last_review"):
            session.last_review = ctx_data["last_review"]

        intent = Intent(job.intent)
        try:
            result = await self.action_dispatcher.dispatch(intent, normalized, session)
        except Exception as e:
            logger.exception("Review job %s failed", job.job_id[:8])
            result = f"Review failed: {e}"

        # Send result reply
        await self.sender.reply(job.platform, normalized, result)

        # Update session
        session.history.append({"role": "assistant", "content": result})
        await self.conversations.save(session)

        return result

    @staticmethod
    def _attach_job_context(job: ReviewJob, session) -> None:
        """Attach session context to the job so the runner can restore it."""
        ctx = {}
        if session.last_review:
            ctx["last_review"] = session.last_review
        job._ctx = ctx
