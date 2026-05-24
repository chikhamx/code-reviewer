import hashlib
import hmac
import logging
import time

logger = logging.getLogger(__name__)


class SlackHandler:
    """Slack platform handler: signature verification + event parsing."""

    def __init__(self, bot_token: str = "", signing_secret: str = "", app_token: str = ""):
        self.bot_token = bot_token
        self.signing_secret = signing_secret
        self.app_token = app_token

    def verify_signature(self, timestamp: str, body: str, signature: str) -> bool:
        """Verify Slack request signature."""
        if not self.signing_secret:
            return True

        # Slack signatures use v0=<hex hmac>
        if abs(time.time() - int(timestamp)) > 300:
            logger.warning("Slack request timestamp too old")
            return False

        sig_basestring = f"v0:{timestamp}:{body}"
        expected = "v0=" + hmac.new(
            self.signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_event(self, body: dict) -> dict:
        """Parse Slack event payload."""

        # URL verification challenge
        if body.get("type") == "url_verification":
            return {"type": "url_verification", "challenge": body.get("challenge", "")}

        event = body.get("event", {})
        event_type = event.get("type", "")

        if event_type == "message" and event.get("bot_id") is None:
            return {
                "type": "message",
                "msg_id": event.get("ts", ""),
                "user_id": event.get("user", ""),
                "text": event.get("text", ""),
                "channel": event.get("channel", ""),
                "team": event.get("team", body.get("team_id", "")),
            }

        return {"type": "unknown", "raw": body}
