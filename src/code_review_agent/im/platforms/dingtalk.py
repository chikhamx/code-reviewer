import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)


class DingTalkHandler:
    """DingTalk platform handler: signature verification + event parsing."""

    def __init__(self, app_key: str = "", app_secret: str = "", robot_code: str = ""):
        self.app_key = app_key
        self.app_secret = app_secret
        self.robot_code = robot_code

    def verify_signature(self, timestamp: str, sign: str) -> bool:
        """Verify DingTalk outgoing robot signature."""
        if not self.app_secret:
            return True
        sign_str = f"{timestamp}\n{self.app_secret}"
        expected = hmac.new(
            self.app_secret.encode(), sign_str.encode(), hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, sign)

    def parse_event(self, body: dict) -> dict:
        """Parse DingTalk event payload."""
        msg_type = body.get("msgtype", "")

        if msg_type == "text":
            return {
                "type": "message",
                "msg_id": body.get("msgId", ""),
                "user_id": body.get("senderStaffId", ""),
                "user_name": body.get("senderNick", ""),
                "text": body.get("text", {}).get("content", ""),
                "conversation_id": body.get("conversationId", ""),
            }

        return {"type": "unknown", "raw": body}
