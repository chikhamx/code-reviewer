"""Management API: LLM providers, webhooks, sessions, and simulation."""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class LLMTestRequest(BaseModel):
    provider: str
    model: str
    prompt: str = "ping"


def _state(request: Request):
    return request.app.state


# ── LLM Management ──

@router.get("/llm/providers")
async def list_llm_providers(request: Request):
    state = _state(request)
    if hasattr(state, "model_router"):
        return {
            "providers": state.model_router.list_providers(),
            "models": state.model_router.list_models(),
        }
    return {"providers": [], "models": {}}


@router.post("/llm/test")
async def test_llm(req: LLMTestRequest, request: Request):
    state = _state(request)
    if not hasattr(state, "model_router"):
        raise HTTPException(status_code=503, detail="LLM router not initialized")

    router = state.model_router
    provider = router.get_provider(req.provider)
    try:
        resp = await provider.chat(
            [{"role": "user", "content": req.prompt}],
            model=req.model,
            max_tokens=50,
        )
        return {"status": "ok", "response": resp.content, "model": resp.model}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/llm/usage")
async def get_llm_usage(request: Request):
    state = _state(request)
    if hasattr(state, "cost_tracker"):
        tracker = state.cost_tracker
        return {
            "summary": tracker.get_summary(),
            "total_cost_usd": tracker.get_total_cost(),
        }
    return {"summary": {}, "total_cost_usd": 0}


# ── Webhook Management ──

@router.get("/webhooks")
async def list_webhooks(request: Request):
    state = _state(request)
    if hasattr(state, "webhook_dispatcher"):
        dispatcher = state.webhook_dispatcher
        return {
            "webhooks": [
                {"name": w.name, "enabled": w.enabled, "type": w.type.value, "url": w.url}
                for w in dispatcher.webhooks
            ]
        }
    return {"webhooks": []}


# ── Conversation Management ──

@router.get("/sessions")
async def list_sessions(request: Request):
    state = _state(request)
    if hasattr(state, "conversation_manager"):
        return {"stats": state.conversation_manager.get_stats()}
    return {"stats": {}}


# ── Simulator: test IM messages locally ──

class SimulateMessage(BaseModel):
    platform: str = "feishu"
    text: str
    user_id: str = "test-user-001"
    user_name: str = "Test User"
    chat_id: str = "test-chat-001"


@router.post("/simulate/im")
async def simulate_im_message(req: SimulateMessage, request: Request):
    """Simulate an IM message for local testing.

    POST /api/simulate/im
    {
        "platform": "feishu",
        "text": "review https://github.com/org/repo/pull/42",
        "user_id": "test-user",
        "chat_id": "test-chat"
    }

    This calls the exact same gateway path as a real webhook,
    so you can test the full pipeline without setting up a real bot.
    """
    state = _state(request)
    gateway = getattr(state, "im_gateway", None)
    if gateway is None:
        raise HTTPException(status_code=503, detail="IM gateway not initialized")

    # Build a simulated raw payload matching what the platform would send.
    # For Feishu, this matches the format the normalizer expects.
    if req.platform == "feishu":
        raw = {
            "event": {
                "message": {
                    "message_id": f"sim-msg-{id(req)}",
                    "msg_type": "text",
                    "content": '{"text":"' + req.text + '"}',
                },
                "sender": {
                    "sender_id": {"open_id": req.user_id},
                },
                "open_chat_id": req.chat_id,
            },
        }
    elif req.platform == "dingtalk":
        raw = {
            "msgId": f"sim-msg-{id(req)}",
            "conversationId": req.chat_id,
            "senderStaffId": req.user_id,
            "senderNick": req.user_name,
            "text": {"content": req.text},
        }
    elif req.platform == "wecom":
        raw = {
            "MsgId": f"sim-msg-{id(req)}",
            "MsgType": "text",
            "ChatId": req.chat_id,
            "From": {"UserId": req.user_id, "Name": req.user_name},
            "Text": {"Content": req.text},
        }
    elif req.platform == "slack":
        raw = {
            "event": {
                "type": "message",
                "ts": f"{id(req)}",
                "channel": req.chat_id,
                "user": req.user_id,
                "text": req.text,
            },
        }
    else:
        raw = {
            "text": req.text,
            "user_id": req.user_id,
            "channel_id": req.chat_id,
            "user_name": req.user_name,
        }

    result = await gateway.handle_message(req.platform, raw)
    return {"simulated": True, "platform": req.platform, "result": result}
