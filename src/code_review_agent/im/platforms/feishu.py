"""Feishu (Lark) platform handler: signature verification + event parsing.

Handles both Feishu v1 event format AND the newer v2 schema format.

v1 format (event subscription):
    {"type": "url_verification", "token": "...", "challenge": "..."}
    {"event": {"type": "im.message.receive_v1", "message": {...}, "sender": {...}}}

v2 format (new event subscription):
    {"schema": "2.0", "header": {"event_type": "im.message.receive_v1", "token": "..."}, "event": {...}}
"""

import hashlib
import hmac
import json
import logging

logger = logging.getLogger(__name__)


class FeishuHandler:
    """Feishu (Lark) platform handler."""

    def __init__(self, app_id: str = "", app_secret: str = "", verification_token: str = ""):
        self.app_id = app_id
        self.app_secret = app_secret
        self.verification_token = verification_token

    def verify_signature(self, timestamp: str, nonce: str, body: str, signature: str) -> bool:
        """Verify Feishu v1 event subscription signature.

        Feishu sends headers: X-Lark-Request-Timestamp, X-Lark-Request-Nonce,
        X-Lark-Signature. The signature is SHA256 of timestamp+nonce+secret+body.
        """
        if not self.app_secret:
            logger.warning("Feishu signature verification skipped: no app_secret configured")
            return True
        sign_str = f"{timestamp}{nonce}{self.app_secret}{body}"
        expected = hashlib.sha256(sign_str.encode()).hexdigest()
        if not hmac.compare_digest(expected, signature):
            logger.warning("Feishu signature mismatch")
            return False
        return True

    def parse_event(self, body: dict) -> dict:
        """Parse Feishu event payload, supporting both v1 and v2 formats."""

        # v2 format: {schema, header: {event_type, token}, event: {...}}
        if "schema" in body and "header" in body:
            header = body.get("header", {})
            event_type = header.get("event_type", "")
            raw_event = body.get("event", {})

            if event_type == "im.message.receive_v1":
                return self._parse_message_v2(raw_event, header.get("token", ""))
            return {"type": "unknown", "raw": body}

        # v1 format
        # URL verification challenge
        if body.get("type") == "url_verification":
            return {
                "type": "url_verification",
                "token": body.get("token", ""),
                "challenge": body.get("challenge", ""),
            }

        # v1 event callback
        event = body.get("event", {})
        event_type = event.get("type", "")

        if event_type == "im.message.receive_v1":
            return self._parse_message_v1(body, event)

        # Event callback challenge (initial URL verification)
        if "challenge" in body:
            return {
                "type": "url_verification",
                "token": body.get("token", ""),
                "challenge": body.get("challenge", ""),
            }

        return {"type": "unknown", "raw": body}

    def _parse_message_v1(self, body: dict, event: dict) -> dict:
        """Parse v1 im.message.receive_v1 event."""
        message = event.get("message", {})
        sender = event.get("sender", {})
        sender_id = sender.get("sender_id", {})

        return {
            "type": "message",
            "msg_id": message.get("message_id", ""),
            "chat_id": message.get("chat_id", ""),
            "chat_type": message.get("chat_type", ""),
            "user_id": sender_id.get("open_id", sender_id.get("user_id", "")),
            "msg_type": message.get("message_type", message.get("msg_type", "text")),
            "content": message.get("content", ""),
            "root_id": message.get("root_id", ""),
            "parent_id": message.get("parent_id", ""),
            "mentions": message.get("mentions", []),
        }

    def _parse_message_v2(self, event: dict, token: str) -> dict:
        """Parse v2 im.message.receive_v1 event."""
        message = event.get("message", {})
        sender = event.get("sender", {})
        sender_id = sender.get("sender_id", {})

        return {
            "type": "message",
            "msg_id": message.get("message_id", ""),
            "chat_id": message.get("chat_id", ""),
            "chat_type": message.get("chat_type", ""),
            "user_id": sender_id.get("open_id", sender_id.get("user_id", "")),
            "msg_type": message.get("message_type", message.get("msg_type", "text")),
            "content": message.get("content", ""),
            "root_id": message.get("root_id", ""),
            "parent_id": message.get("parent_id", ""),
            "mentions": message.get("mentions", []),
        }
