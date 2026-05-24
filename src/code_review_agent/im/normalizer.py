"""Converts platform-specific message formats into a unified internal structure.

The normalizer is the FIRST step in the IM gateway pipeline.
It takes a raw webhook payload and produces a standardized dict with keys:
    platform, msg_id, session_id, channel_id, user_id, user_name, text, timestamp, raw
"""

import json
import logging

logger = logging.getLogger(__name__)


class MessageNormalizer:
    """Converts platform-specific message formats into a unified internal structure."""

    def normalize(self, platform: str, raw: dict) -> dict:
        if platform == "feishu":
            return self._normalize_feishu(raw)
        elif platform == "dingtalk":
            return self._normalize_dingtalk(raw)
        elif platform == "wecom":
            return self._normalize_wecom(raw)
        elif platform == "slack":
            return self._normalize_slack(raw)
        else:
            return self._normalize_generic(raw)

    # ── Feishu (Lark) ──

    @staticmethod
    def _normalize_feishu(raw: dict) -> dict:
        """Normalize Feishu v1 or v2 event into internal format.

        Real Feishu v1 payload structure:
        {
            "event": {
                "type": "im.message.receive_v1",
                "message": {
                    "message_id": "om_xxx",
                    "chat_id": "oc_xxx",
                    "chat_type": "group",
                    "message_type": "text",
                    "content": "{\"text\":\"@bot hello\"}"
                },
                "sender": {
                    "sender_id": {"open_id": "ou_xxx", "user_id": "xxx"}
                }
            }
        }
        """
        # v2 format: {schema, header: {event_type}, event: {message, sender}}
        if "schema" in raw and "header" in raw:
            header = raw.get("header", {})
            event = raw.get("event", {})
            message = event.get("message", {})
            sender = event.get("sender", {})
            sender_id = sender.get("sender_id", {})
            chat_id = message.get("chat_id", "")
            open_id = sender_id.get("open_id", sender_id.get("user_id", ""))
            return {
                "platform": "feishu",
                "msg_id": message.get("message_id", ""),
                "session_id": f"feishu:{chat_id}:{open_id}",
                "channel_id": chat_id,
                "user_id": open_id,
                "user_name": "",
                "text": _extract_feishu_text(message),
                "timestamp": header.get("create_time", ""),
                "root_id": message.get("root_id", ""),
                "raw": raw,
            }

        # v1 format
        event = raw.get("event", {})
        message = event.get("message", {})
        sender = event.get("sender", {})
        sender_id = sender.get("sender_id", {})

        chat_id = message.get("chat_id", "")
        open_id = sender_id.get("open_id", sender_id.get("user_id", ""))

        return {
            "platform": "feishu",
            "msg_id": message.get("message_id", ""),
            "session_id": f"feishu:{chat_id}:{open_id}",
            "channel_id": chat_id,
            "user_id": open_id,
            "user_name": "",
            "text": _extract_feishu_text(message),
            "timestamp": event.get("event_time", ""),
            "root_id": message.get("root_id", ""),
            "raw": raw,
        }

    # ── DingTalk ──

    @staticmethod
    def _normalize_dingtalk(raw: dict) -> dict:
        return {
            "platform": "dingtalk",
            "msg_id": raw.get("msgId", ""),
            "session_id": f"dingtalk:{raw.get('conversationId', '')}:{raw.get('senderStaffId', '')}",
            "channel_id": raw.get("conversationId", ""),
            "user_id": raw.get("senderStaffId", ""),
            "user_name": raw.get("senderNick", ""),
            "text": raw.get("text", {}).get("content", ""),
            "timestamp": raw.get("createAt", ""),
            "raw": raw,
        }

    # ── WeChat Work ──

    @staticmethod
    def _normalize_wecom(raw: dict) -> dict:
        from_user = raw.get("From", {})
        return {
            "platform": "wecom",
            "msg_id": raw.get("MsgId", ""),
            "session_id": f"wecom:{raw.get('ChatId', '')}:{from_user.get('UserId', '')}",
            "channel_id": raw.get("ChatId", ""),
            "user_id": from_user.get("UserId", ""),
            "user_name": from_user.get("Name", ""),
            "text": raw.get("Text", {}).get("Content", ""),
            "timestamp": raw.get("CreateTime", ""),
            "raw": raw,
        }

    # ── Slack ──

    @staticmethod
    def _normalize_slack(raw: dict) -> dict:
        event = raw.get("event", {})
        return {
            "platform": "slack",
            "msg_id": event.get("ts", ""),
            "session_id": f"slack:{event.get('channel', '')}:{event.get('user', '')}",
            "channel_id": event.get("channel", ""),
            "user_id": event.get("user", ""),
            "user_name": event.get("user", ""),
            "text": event.get("text", ""),
            "timestamp": event.get("event_ts", ""),
            "raw": raw,
        }

    # ── Generic ──

    @staticmethod
    def _normalize_generic(raw: dict) -> dict:
        return {
            "platform": "generic",
            "msg_id": raw.get("msg_id", raw.get("id", "")),
            "session_id": raw.get("session_id", f"generic:{raw.get('channel', '')}:{raw.get('user', '')}"),
            "channel_id": raw.get("channel_id", ""),
            "user_id": raw.get("user_id", ""),
            "user_name": raw.get("user_name", ""),
            "text": raw.get("text", raw.get("content", "")),
            "timestamp": raw.get("timestamp", ""),
            "raw": raw,
        }


def _extract_feishu_text(message: dict) -> str:
    """Extract plain text from Feishu message content field.

    Feishu sends content as a JSON string: '{"text":"@bot hello world"}'
    We need to extract the inner "text" value.
    """
    content = message.get("content", "")
    if not content:
        return ""

    if isinstance(content, dict):
        # Already parsed
        text = content.get("text", "")
        if isinstance(text, str):
            return text
        return str(content)

    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return content
        if isinstance(parsed, dict):
            text = parsed.get("text", "")
            if isinstance(text, str):
                return text
        return str(parsed)

    return str(content)
