"""IM platform webhook receivers.

Feishu flow:
  1. User @mentions bot in Feishu group
  2. Feishu sends POST to /api/im/feishu
     Headers: X-Lark-Request-Timestamp, X-Lark-Request-Nonce, X-Lark-Signature
     Body: {"event": {"type": "im.message.receive_v1", "message": {...}, "sender": {...}}}
  3. Verify signature using app_secret
  4. Handle URL verification challenge (first-time setup)
  5. Route to IM gateway for processing
  6. Agent processes → IMSender replies via Feishu API
"""

import json
import logging

from fastapi import APIRouter, Header, Request

from code_review_agent.config import get_config
from code_review_agent.im.platforms.feishu import FeishuHandler

logger = logging.getLogger(__name__)
router = APIRouter()


async def _gateway(request: Request, platform: str, body: dict) -> dict:
    """Route a parsed IM message to the gateway for processing."""
    gateway = getattr(request.app.state, "im_gateway", None)
    if gateway is None:
        logger.warning("IM gateway not initialized — message ignored")
        return {"status": "gateway_unavailable"}
    return await gateway.handle_message(platform, body)


# ── Feishu (Lark) ──

@router.post("/feishu")
async def feishu_webhook(
    request: Request,
    x_lark_request_timestamp: str = Header(default=""),
    x_lark_request_nonce: str = Header(default=""),
    x_lark_signature: str = Header(default=""),
):
    """Receive Feishu event subscription callbacks.

    Feishu sends headers:
      X-Lark-Request-Timestamp: 1603977298
      X-Lark-Request-Nonce: abc123
      X-Lark-Signature: sha256hex...
    """
    # Read raw body for signature verification
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")
    body = json.loads(body_str)

    # Step 0: Verify signature
    cfg = get_config()
    im_cfg = cfg.load_sub_config("im", "config_path")
    feishu_cfg = im_cfg.get("platforms", {}).get("feishu", {})

    feishu = FeishuHandler(
        app_id=feishu_cfg.get("app_id", ""),
        app_secret=feishu_cfg.get("app_secret", ""),
        verification_token=feishu_cfg.get("verification_token", ""),
    )

    if x_lark_request_timestamp and x_lark_signature:
        if not feishu.verify_signature(
            x_lark_request_timestamp,
            x_lark_request_nonce,
            body_str,
            x_lark_signature,
        ):
            logger.warning("Feishu signature verification FAILED")
            # Return 200 anyway so Feishu doesn't retry endlessly
            return {"status": "signature_verification_failed"}

    # Step 1: Handle URL verification challenge
    if body.get("type") == "url_verification":
        challenge = body.get("challenge", "")
        logger.info("Feishu URL verification: challenge received")
        return {"challenge": challenge}

    # Also handle v2 URL verification
    if (
        "schema" in body
        and body.get("header", {}).get("event_type") == "url_verification"
    ):
        challenge = body.get("event", {}).get("challenge", "")
        logger.info("Feishu v2 URL verification: challenge received")
        return {"challenge": challenge}

    # Step 2: Route to gateway
    return await _gateway(request, "feishu", body)


# ── DingTalk ──

@router.post("/dingtalk")
async def dingtalk_webhook(request: Request):
    body = await request.json()
    return await _gateway(request, "dingtalk", body)


# ── WeChat Work ──

@router.post("/wecom")
async def wecom_webhook(request: Request):
    body = await request.json()
    return await _gateway(request, "wecom", body)


# ── Slack ──

@router.post("/slack")
async def slack_webhook(request: Request):
    body = await request.json()

    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge", "")}

    return await _gateway(request, "slack", body)
