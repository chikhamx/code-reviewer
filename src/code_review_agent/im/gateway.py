import logging

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
    ):
        self.normalizer = normalizer
        self.sender = sender
        self.intent_router = intent_router
        self.action_dispatcher = action_dispatcher
        self.conversations = conversation_manager

    async def handle_message(self, platform: str, raw: dict) -> dict:
        """Process an incoming IM message: normalize -> classify -> dispatch -> reply."""
        logger.info(">>> GATEWAY: processing %s message", platform)
        try:
            normalized = self.normalizer.normalize(platform, raw)
            logger.info(
                ">>> GATEWAY: normalized - text=%s user=%s chat=%s msg_id=%s",
                normalized.get("text", ""),
                normalized.get("user_id", ""),
                normalized.get("channel_id", ""),
                normalized.get("msg_id", ""),
            )
        except Exception as e:
            logger.error("Failed to normalize %s message: %s", platform, e)
            return {"status": "error", "message": str(e)}

        session_id = normalized.get("session_id", "")
        session = await self.conversations.get_or_create(
            session_id=session_id,
            platform=platform,
            channel_id=normalized.get("channel_id", ""),
            user_id=normalized.get("user_id", ""),
            user_name=normalized.get("user_name", ""),
        )
        logger.info(
            ">>> GATEWAY: session=%s stage=%s history_size=%d",
            session_id,
            session.chat_stage,
            len(session.history),
        )

        # Dedup check
        msg_id = normalized.get("msg_id", "")
        if msg_id and msg_id in session.metadata.get("processed_ids", []):
            logger.info(">>> GATEWAY: duplicate message %s, skipping", msg_id)
            return {"status": "ok", "dedup": True}
        if msg_id:
            session.metadata.setdefault("processed_ids", []).append(msg_id)
            if len(session.metadata["processed_ids"]) > 100:
                session.metadata["processed_ids"] = session.metadata["processed_ids"][-50:]

        text = normalized.get("text", "").strip()
        if not text:
            logger.info(">>> GATEWAY: empty text, no action")
            return {"status": "ok", "note": "empty message"}

        # Classify intent
        intent = await self.intent_router.classify(text, session)
        session.current_intent = intent.value if intent else None
        logger.info(">>> GATEWAY: intent=%s", intent.value if intent else "unknown")

        # Dispatch action
        try:
            logger.info(">>> GATEWAY: dispatching action=%s", intent.value if intent else "unknown")
            response_text = await self.action_dispatcher.dispatch(intent, normalized, session)
            preview = response_text[:150].replace("\n", "\\n") if response_text else ""
            logger.info(">>> GATEWAY: response preview=%s", preview)
        except Exception as e:
            logger.exception("Action dispatch failed for intent %s", intent)
            response_text = f"Sorry, something went wrong: {e}"

        # Update session history
        session.history.append({
            "role": "user", "content": text,
        })
        session.history.append({
            "role": "assistant", "content": response_text,
        })
        if len(session.history) > 20:
            session.history = session.history[-20:]
        await self.conversations.save(session)

        # Send reply
        try:
            ok = await self.sender.reply(platform, normalized, response_text)
            logger.info(">>> GATEWAY: reply sent ok=%s", ok)
        except Exception as e:
            logger.error("Failed to send reply to %s: %s", platform, e)

        return {"status": "ok", "intent": intent.value if intent else "unknown"}
