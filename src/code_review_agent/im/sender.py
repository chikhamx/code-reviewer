"""Sends messages back to IM platforms.

Each platform has a different API for sending messages. The sender
uses the platform config from config/im.yaml to authenticate.

For Feishu, preferentially uses the lark-oapi SDK client when available,
falling back to raw HTTP calls the same as before.
"""

import json
import logging
from typing import Optional, TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from code_review_agent.im.feishu_sdk import FeishuSDKClient

logger = logging.getLogger(__name__)


class IMSender:
    """Sends messages back to IM platforms using their native APIs."""

    def __init__(
        self,
        platform_configs: dict | None = None,
        feishu_client: Optional["FeishuSDKClient"] = None,
    ):
        self.configs = platform_configs or {}
        self._feishu = feishu_client

    async def reply(self, platform: str, normalized: dict, text: str) -> bool:
        """Send a reply message back to the user/group.

        Args:
            platform: 'feishu' | 'dingtalk' | 'wecom' | 'slack'
            normalized: The normalized message dict (contains channel_id, msg_id, etc.)
            text: The response text to send
        """
        channel_id = normalized.get("channel_id", "")
        msg_id = normalized.get("msg_id", "")
        root_id = normalized.get("root_id", "")
        user_id = normalized.get("user_id", "")

        if platform == "feishu":
            return await self._reply_feishu(channel_id, text, msg_id, root_id)
        elif platform == "dingtalk":
            return await self._reply_dingtalk(user_id, text)
        elif platform == "wecom":
            return await self._reply_wecom(text, normalized)
        elif platform == "slack":
            return await self._reply_slack(channel_id, text)
        else:
            logger.warning("Unknown platform '%s' for reply", platform)
            return False

    # ── Feishu (Lark) reply ──

    async def _reply_feishu(
        self,
        chat_id: str,
        text: str,
        reply_msg_id: str = "",
        root_id: str = "",
    ) -> bool:
        """Send a text message to a Feishu chat.

        Prefers the SDK client (FeishuSDKClient) if configured. Falls back
        to raw HTTP calls with manually obtained tenant_access_token.
        """
        # Prefer SDK client when available
        if self._feishu:
            try:
                if reply_msg_id:
                    msg_id = await self._feishu.reply_message(reply_msg_id, text)
                else:
                    msg_id = await self._feishu.send_message(chat_id, text)
                return msg_id is not None
            except Exception as e:
                logger.warning("Feishu SDK send failed, falling back to HTTP: %s", e)

        # Fallback: raw HTTP
        cfg = self.configs.get("feishu", {})
        app_id = cfg.get("app_id", "")
        app_secret = cfg.get("app_secret", "")

        if not app_id or not app_secret:
            logger.warning("Feishu not configured for sending (missing app_id/app_secret)")
            return False

        try:
            token = await self._get_feishu_token(app_id, app_secret)
            if not token:
                logger.error("Failed to get Feishu tenant access token")
                return False

            content = json.dumps({"text": text}, ensure_ascii=False)

            body = {
                "receive_id": chat_id,
                "msg_type": "text",
                "content": content,
            }

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://open.feishu.cn/open-apis/im/v1/messages",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    params={"receive_id_type": "chat_id"},
                    json=body,
                )

                if resp.status_code != 200:
                    logger.error(
                        "Feishu send failed: HTTP %d — %s",
                        resp.status_code,
                        resp.text[:500],
                    )
                    return False

                data = resp.json()
                if data.get("code", -1) != 0:
                    logger.error(
                        "Feishu API error: code=%d msg=%s",
                        data.get("code"),
                        data.get("msg", ""),
                    )
                    return False

                logger.info(
                    "Feishu reply sent: msg_id=%s chat_id=%s",
                    data.get("data", {}).get("message_id"),
                    chat_id,
                )
                return True

        except Exception as e:
            logger.error("Feishu reply failed: %s", e)
            return False

    async def _get_feishu_token(self, app_id: str, app_secret: str) -> str:
        """Get Feishu tenant_access_token via HTTP.

        In production, add Redis caching for the 2-hour TTL.
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                    json={"app_id": app_id, "app_secret": app_secret},
                )
                if resp.status_code != 200:
                    logger.error("Feishu token request failed: %s", resp.text[:500])
                    return ""

                data = resp.json()
                code = data.get("code", -1)
                if code != 0:
                    logger.error(
                        "Feishu token API error: code=%d msg=%s",
                        code,
                        data.get("msg", ""),
                    )
                    return ""

                token = data.get("tenant_access_token", "")
                if not token:
                    logger.error("Feishu token API returned empty token")
                return token

        except Exception as e:
            logger.error("Feishu token request failed: %s", e)
            return ""

    # ── DingTalk reply ──

    async def _reply_dingtalk(self, user_id: str, text: str) -> bool:
        cfg = self.configs.get("dingtalk", {})
        access_token = cfg.get("access_token", "")
        if not access_token:
            logger.warning("DingTalk not configured for sending")
            return False

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://oapi.dingtalk.com/robot/send",
                    params={"access_token": access_token},
                    json={"msgtype": "text", "text": {"content": text}},
                )
                return resp.status_code == 200
        except Exception as e:
            logger.error("DingTalk reply failed: %s", e)
            return False

    # ── WeChat Work reply ──

    async def _reply_wecom(self, text: str, normalized: dict) -> bool:
        cfg = self.configs.get("wecom", {})
        webhook_url = cfg.get("webhook_url", "")
        if not webhook_url:
            logger.warning("WeCom not configured for sending")
            return False

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    webhook_url,
                    json={"msgtype": "text", "text": {"content": text}},
                )
                return resp.status_code == 200
        except Exception as e:
            logger.error("WeCom reply failed: %s", e)
            return False

    # ── Slack reply ──

    async def _reply_slack(self, channel: str, text: str) -> bool:
        cfg = self.configs.get("slack", {})
        bot_token = cfg.get("bot_token", "")
        if not bot_token:
            logger.warning("Slack not configured for sending")
            return False

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    json={"channel": channel, "text": text},
                )
                ok = resp.status_code == 200 and resp.json().get("ok", False)
                if not ok:
                    logger.error("Slack reply failed: %s", resp.text[:500])
                return ok
        except Exception as e:
            logger.error("Slack reply failed: %s", e)
            return False

    # ── Generic notification (for webhook dispatcher) ──

    async def send_notification(self, platform: str, channel_id: str, text: str) -> bool:
        """Send a notification to a channel (for push-style alerts, not reply-to-message)."""
        dummy = {"platform": platform, "channel_id": channel_id, "user_id": "", "msg_id": ""}
        return await self.reply(platform, dummy, text)
