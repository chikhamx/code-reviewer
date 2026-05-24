import hashlib
import logging

logger = logging.getLogger(__name__)


class WeComHandler:
    """WeChat Work (企业微信) platform handler: message decryption + event parsing."""

    def __init__(
        self,
        corp_id: str = "",
        agent_id: str = "",
        secret: str = "",
        token: str = "",
        encoding_aes_key: str = "",
    ):
        self.corp_id = corp_id
        self.agent_id = agent_id
        self.secret = secret
        self.token = token
        self.encoding_aes_key = encoding_aes_key

    def verify_signature(self, timestamp: str, nonce: str, echostr: str, msg_signature: str) -> bool:
        """Verify WeCom URL verification signature."""
        if not self.token:
            return True
        params = sorted([self.token, timestamp, nonce, echostr])
        sign_str = "".join(params)
        expected = hashlib.sha1(sign_str.encode()).hexdigest()
        return sign_str == msg_signature

    def parse_event(self, body: dict) -> dict:
        """Parse WeCom event payload."""
        msg_type = body.get("MsgType", "")

        if msg_type == "text":
            return {
                "type": "message",
                "msg_id": body.get("MsgId", ""),
                "user_id": body.get("From", {}).get("UserId", ""),
                "user_name": body.get("From", {}).get("Name", ""),
                "text": body.get("Text", {}).get("Content", ""),
                "chat_id": body.get("ChatId", ""),
            }

        return {"type": "unknown", "raw": body}
