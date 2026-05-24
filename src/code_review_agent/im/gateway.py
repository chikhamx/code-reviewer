import logging
from typing import Optional

from code_review_agent.actions.base import ActionDispatcher
from code_review_agent.conversation.manager import ConversationManager
from code_review_agent.im.normalizer import MessageNormalizer
from code_review_agent.im.sender import IMSender
from code_review_agent.router.intent_router import IntentRouter

logger = logging.getLogger(__name__)


class IMGateway:
    """Unified entry point for all IM platform messages."""

    def __init__(
        self,
        normalizer: MessageNormalizer,
        sender: IMSender,
        intent_router: IntentRouter,
        action_dispatcher: ActionDispatcher,
        conversation_manager: ConversationManager,
        message_store=None,  # MessageChainStore
    ):
        self.normalizer = normalizer
        self.sender = sender
        self.intent_router = intent_router
        self.action_dispatcher = action_dispatcher
        self.conversations = conversation_manager
        self.store = message_store

    async def handle_message(self, platform: str, raw: dict) -> dict:
        """Process an incoming IM message and persist to the message chain."""
        try:
            normalized = self.normalizer.normalize(platform, raw)
        except Exception as e:
            logger.error("Failed to normalize %s message: %s", platform, e)
            return {"status": "error", "message": str(e)}

        msg_id = normalized.get("msg_id", "")
        session_id = normalized.get("session_id", "")
        text = normalized.get("text", "").strip()
        root_id = normalized.get("root_id", "")
        user_id = normalized.get("user_id", "")

        logger.info(
            ">>> GATEWAY: %s msg_id=%s text=%.80s root=%s",
            platform, msg_id, text, root_id or "-",
        )

        if not text:
            return {"status": "ok", "note": "empty message"}

        # ── Persist incoming message to message chain ──
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

        # ── Context from message chain ──
        chain_ctx = {}
        if self.store and (root_id or msg_id):
            lookup = root_id or msg_id
            chain_ctx = self.store.build_context(lookup)
            logger.info(
                ">>> GATEWAY: chain context - findings=%d thread=%s",
                len(chain_ctx.get("findings", [])),
                chain_ctx.get("thread_id", "-")[:20],
            )

        # ── Legacy session ──
        session = await self.conversations.get_or_create(
            session_id=session_id,
            platform=platform,
            channel_id=normalized.get("channel_id", ""),
            user_id=user_id,
            user_name=normalized.get("user_name", ""),
        )

        # Dedup
        if msg_id and msg_id in session.metadata.get("processed_ids", []):
            logger.info(">>> GATEWAY: duplicate message %s, skipping", msg_id)
            return {"status": "ok", "dedup": True}
        if msg_id:
            session.metadata.setdefault("processed_ids", []).append(msg_id)
            if len(session.metadata["processed_ids"]) > 100:
                session.metadata["processed_ids"] = session.metadata["processed_ids"][-50:]

        # Inject chain findings into session for actions that need them
        if chain_ctx.get("findings"):
            session.last_review = {
                "title": chain_ctx.get("trigger", {}).get("title", ""),
                "repo": chain_ctx.get("trigger", {}).get("repo", ""),
                "findings": chain_ctx["findings"],
                "diff": chain_ctx.get("trigger", {}).get("diff", ""),
            }

        # ── Classify intent ──
        intent = await self.intent_router.classify(text, session)
        session.current_intent = intent.value if intent else None
        logger.info(">>> GATEWAY: intent=%s", intent.value if intent else "unknown")

        # ── Dispatch action ──
        try:
            response_text = await self.action_dispatcher.dispatch(intent, normalized, session)
            preview = response_text[:150].replace("\n", "\\n") if response_text else ""
            logger.info(">>> GATEWAY: response preview=%s", preview)
        except Exception as e:
            logger.exception("Action dispatch failed for intent %s", intent)
            response_text = f"Sorry, something went wrong: {e}"

        # ── Persist response to message chain ──
        reply_msg_id: Optional[str] = None
        if self.store and msg_id:
            reply_role = "review" if intent and intent.value in ("review_pr", "review_commit", "review_branch") else "assistant"
            reply_msg_id = f"{msg_id}-reply"  # placeholder, will be updated
            self.store.save_message(
                message_id=reply_msg_id,
                session_id=session_id,
                root_id=root_id or msg_id,
                parent_id=msg_id,
                role=reply_role,
                source_type="bot_reply",
                content=response_text,
                metadata={
                    "findings": session.last_review.get("findings", []),
                    "intent": intent.value if intent else "unknown",
                },
            )

        # ── Update session ──
        session.history.append({"role": "user", "content": text})
        session.history.append({"role": "assistant", "content": response_text})
        if len(session.history) > 20:
            session.history = session.history[-20:]
        await self.conversations.save(session)

        # ── Send reply ──
        try:
            ok = await self.sender.reply(platform, normalized, response_text)
            logger.info(">>> GATEWAY: reply sent ok=%s", ok)
        except Exception as e:
            logger.error("Failed to send reply to %s: %s", platform, e)

        return {"status": "ok", "intent": intent.value if intent else "unknown"}
