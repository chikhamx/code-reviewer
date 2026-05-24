"""Sends messages back to IM platforms.

Each platform has a different API for sending messages. The sender
uses the platform config from config/im.yaml to authenticate.

All reply methods return the platform-specific message_id on success,
or None on failure.
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

    async def reply(self, platform: str, normalized: dict, text: str) -> str | None:
        """Send a reply message. Returns message_id on success, None on failure."""
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
            return None

    # ── Feishu (Lark) reply ──

    async def _reply_feishu(
        self, chat_id: str, text: str, reply_msg_id: str = "", root_id: str = "",
    ) -> str | None:
        # Prefer SDK client
        if self._feishu:
            try:
                if reply_msg_id:
                    return await self._feishu.reply_message(reply_msg_id, text)
                return await self._feishu.send_message(chat_id, text)
            except Exception as e:
                logger.warning("Feishu SDK send failed, falling back to HTTP: %s", e)

        # Fallback: raw HTTP
        cfg = self.configs.get("feishu", {})
        app_id = cfg.get("app_id", "")
        app_secret = cfg.get("app_secret", "")
        if not app_id or not app_secret:
            logger.warning("Feishu not configured for sending")
            return None

        try:
            token = await self._get_feishu_token(app_id, app_secret)
            if not token:
                return None

            content = json.dumps({"text": text}, ensure_ascii=False)
            body = {"receive_id": chat_id, "msg_type": "text", "content": content}

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://open.feishu.cn/open-apis/im/v1/messages",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    params={"receive_id_type": "chat_id"},
                    json=body,
                )
                if resp.status_code != 200:
                    logger.error("Feishu send failed: HTTP %d", resp.status_code)
                    return None

                data = resp.json()
                if data.get("code", -1) != 0:
                    logger.error("Feishu API error: code=%d msg=%s", data.get("code"), data.get("msg", ""))
                    return None

                msg_id = data.get("data", {}).get("message_id")
                logger.info("Feishu reply sent: msg_id=%s chat_id=%s", msg_id, chat_id)
                return msg_id
        except Exception as e:
            logger.error("Feishu reply failed: %s", e)
            return None

    async def _get_feishu_token(self, app_id: str, app_secret: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                    json={"app_id": app_id, "app_secret": app_secret},
                )
                if resp.status_code != 200:
                    return ""
                data = resp.json()
                if data.get("code", -1) != 0:
                    return ""
                return data.get("tenant_access_token", "")
        except Exception:
            return ""

    # ── DingTalk / WeCom / Slack ──

    async def _reply_dingtalk(self, user_id: str, text: str) -> str | None:
        cfg = self.configs.get("dingtalk", {})
        access_token = cfg.get("access_token", "")
        if not access_token:
            return None
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://oapi.dingtalk.com/robot/send",
                    params={"access_token": access_token},
                    json={"msgtype": "text", "text": {"content": text}},
                )
                return "dingtalk-ok" if resp.status_code == 200 else None
        except Exception as e:
            logger.error("DingTalk reply failed: %s", e)
            return None

    async def _reply_wecom(self, text: str, normalized: dict) -> str | None:
        cfg = self.configs.get("wecom", {})
        webhook_url = cfg.get("webhook_url", "")
        if not webhook_url:
            return None
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    webhook_url,
                    json={"msgtype": "text", "text": {"content": text}},
                )
                return "wecom-ok" if resp.status_code == 200 else None
        except Exception as e:
            logger.error("WeCom reply failed: %s", e)
            return None

    async def _reply_slack(self, channel: str, text: str) -> str | None:
        cfg = self.configs.get("slack", {})
        bot_token = cfg.get("bot_token", "")
        if not bot_token:
            return None
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    json={"channel": channel, "text": text},
                )
                data = resp.json()
                return data.get("ts") if resp.status_code == 200 and data.get("ok") else None
        except Exception as e:
            logger.error("Slack reply failed: %s", e)
            return None

    async def send_notification(self, platform: str, channel_id: str, text: str) -> str | None:
        dummy = {"platform": platform, "channel_id": channel_id, "user_id": "", "msg_id": ""}
        return await self.reply(platform, dummy, text)
