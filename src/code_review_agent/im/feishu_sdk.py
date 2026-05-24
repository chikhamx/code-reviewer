"""Feishu integration via official lark-oapi SDK.

Provides two classes:
  - FeishuSDKClient: wraps lark_oapi.Client for API calls (send messages, etc.)
  - FeishuWSListener: wraps lark_oapi.ws.Client for WebSocket long connection
    to receive events without needing a public URL / ngrok.

All lark-oapi SDK imports are deferred (lazy) to avoid blocking startup
when network connectivity to Feishu is slow or unavailable.

Usage:
    api = FeishuSDKClient(app_id="cli_xxx", app_secret="xxx")
    await api.send_message(chat_id="oc_xxx", text="hello")

    ws = FeishuWSListener(app_id="cli_xxx", app_secret="xxx")
    ws.on_message = your_async_handler
    ws.start()  # blocking; run in a background thread
"""

import json
import logging
import asyncio
import socket
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from lark_oapi import Client as ApiClient
    from lark_oapi.ws import Client as WSClient
    from lark_oapi.event.dispatcher_handler import EventDispatcherHandler

logger = logging.getLogger(__name__)

_SDK_IMPORT_ERROR: Optional[str] = None

# The lark-oapi SDK makes blocking network calls (e.g. fetching
# tenant_access_token) without configurable timeouts.  We set a
# short default socket timeout so that imports and API calls fail
# fast instead of hanging the whole process.
_SDK_SOCKET_TIMEOUT = 10  # seconds


def _import_lark_oapi():
    """Lazily import lark-oapi SDK. Returns (ApiClient, WSClient, EventDispatcherHandler, im_v1_module)."""
    global _SDK_IMPORT_ERROR
    if _SDK_IMPORT_ERROR is not None:
        raise ImportError(_SDK_IMPORT_ERROR)
    try:
        socket.setdefaulttimeout(_SDK_SOCKET_TIMEOUT)
        from lark_oapi import Client as ApiClient  # noqa: F811
        from lark_oapi.ws import Client as WSClient  # noqa: F811
        from lark_oapi.event.dispatcher_handler import EventDispatcherHandler  # noqa: F811
        import lark_oapi.api.im.v1 as im_v1  # noqa: F811
        return ApiClient, WSClient, EventDispatcherHandler, im_v1
    except ImportError as e:
        _SDK_IMPORT_ERROR = str(e)
        raise
    except Exception as e:
        _SDK_IMPORT_ERROR = f"lark-oapi SDK import failed: {e}"
        raise ImportError(_SDK_IMPORT_ERROR) from e


# ── API Client (message sending) ──

class FeishuSDKClient:
    """Wraps lark_oapi.Client for Feishu Open API calls.

    All SDK imports and client creation are lazy — nothing blocks at init time.
    """

    def __init__(self, app_id: str, app_secret: str, domain: str = "https://open.feishu.cn"):
        self.app_id = app_id
        self.app_secret = app_secret
        self.domain = domain
        self._client = None

    @property
    def client(self):
        if self._client is None:
            ApiClient, _, _, _ = _import_lark_oapi()
            self._client = (
                ApiClient.builder()
                .app_id(self.app_id)
                .app_secret(self.app_secret)
                .domain(self.domain)
                .build()
            )
        return self._client

    async def send_message(
        self, chat_id: str, text: str, receive_id_type: str = "chat_id"
    ) -> Optional[str]:
        try:
            _, _, _, im_v1 = _import_lark_oapi()
            content = json.dumps({"text": text}, ensure_ascii=False)
            body = (
                im_v1.CreateMessageRequestBodyBuilder()
                .content(content)
                .msg_type("text")
                .receive_id(chat_id)
                .build()
            )
            request = (
                im_v1.CreateMessageRequestBuilder()
                .receive_id_type(receive_id_type)
                .request_body(body)
                .build()
            )
            response = await self.client.im.v1.message.acreate(request)
            if response.code != 0:
                logger.error(
                    "Feishu send_message failed: code=%d msg=%s",
                    response.code, response.msg,
                )
                return None
            msg_id = response.data.message_id if response.data else None
            logger.info("Feishu message sent: msg_id=%s chat_id=%s", msg_id, chat_id)
            return msg_id
        except Exception as e:
            logger.error("Feishu send_message exception: %s", e)
            return None

    async def reply_message(
        self, message_id: str, text: str, reply_in_thread: bool = False
    ) -> Optional[str]:
        try:
            _, _, _, im_v1 = _import_lark_oapi()
            content = json.dumps({"text": text}, ensure_ascii=False)
            body = (
                im_v1.ReplyMessageRequestBodyBuilder()
                .content(content)
                .msg_type("text")
                .reply_in_thread(reply_in_thread)
                .build()
            )
            request = (
                im_v1.ReplyMessageRequestBuilder()
                .message_id(message_id)
                .request_body(body)
                .build()
            )
            response = await self.client.im.v1.message.areply(request)
            if response.code != 0:
                logger.error(
                    "Feishu reply_message failed: code=%d msg=%s",
                    response.code, response.msg,
                )
                return None
            msg_id = response.data.message_id if response.data else None
            logger.info("Feishu reply sent: msg_id=%s reply_to=%s", msg_id, message_id)
            return msg_id
        except Exception as e:
            logger.error("Feishu reply_message exception: %s", e)
            return None

    async def get_message(self, message_id: str) -> Optional[dict]:
        try:
            response = await self.client.im.v1.message.aget(message_id)
            if response.code != 0:
                logger.error(
                    "Feishu get_message failed: code=%d msg=%s",
                    response.code, response.msg,
                )
                return None
            return response.data.to_dict() if response.data else None
        except Exception as e:
            logger.error("Feishu get_message exception: %s", e)
            return None


# ── WebSocket Listener (event receiving) ──

class FeishuWSListener:
    """Long-connection WebSocket client for receiving Feishu events.

    Uses lark_oapi.ws.Client with EventDispatcherHandler. Run start()
    in a background thread alongside FastAPI.
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        domain: str = "https://open.feishu.cn",
        auto_reconnect: bool = True,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.domain = domain
        self.auto_reconnect = auto_reconnect
        self._ws_client = None
        self._started = False
        self.on_message: Optional[Callable] = None
        self.on_connected: Optional[Callable] = None

    def _build_event_handler(self):
        _, _, EventDispatcherHandler, _ = _import_lark_oapi()

        builder = EventDispatcherHandler.builder(self.app_secret, "")

        def handle_message(event) -> None:
            try:
                logger.info("Feishu WS event received: schema=%s type=%s",
                            getattr(event, 'schema', '?'),
                            getattr(event.header, 'event_type', '?') if hasattr(event, 'header') and event.header else '?')
                raw_event = None
                if event.event:
                    evt_data = event.event
                    msg = evt_data.message
                    sender = evt_data.sender
                    logger.info("WS event data: msg=%s sender=%s",
                                msg is not None, sender is not None)
                    if msg:
                        raw_event = _ws_event_to_raw(msg, sender)
                        logger.info("WS raw_event built: chat_id=%s msg_id=%s",
                                    raw_event['event']['message'].get('chat_id', '?'),
                                    raw_event['event']['message'].get('message_id', '?'))
                    else:
                        logger.warning("WS event has no message field, event keys: %s",
                                       dir(evt_data) if evt_data else 'None')
                else:
                    logger.warning("WS event has no .event attribute, type=%s dir=%s",
                                   type(event).__name__, [x for x in dir(event) if not x.startswith('_')])

                if raw_event and self.on_message:
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(self.on_message(raw_event))
                    except RuntimeError:
                        asyncio.run(self.on_message(raw_event))
            except Exception as e:
                logger.error("Feishu WS event handler error: %s", e, exc_info=True)

        builder.register_p2_im_message_receive_v1(handle_message)
        return builder.build()

    def start(self):
        if self._started:
            logger.warning("Feishu WS listener already started")
            return

        try:
            logger.info("Feishu WS: importing SDK...")
            _, WSClient, _, _ = _import_lark_oapi()
            logger.info("Feishu WS: SDK imported, building event handler...")
            event_handler = self._build_event_handler()
            logger.info("Feishu WS: event handler built, creating WSClient...")
            self._ws_client = WSClient(
                app_id=self.app_id,
                app_secret=self.app_secret,
                event_handler=event_handler,
                domain=self.domain,
                auto_reconnect=self.auto_reconnect,
            )
            logger.info("Feishu WS: WSClient created, connecting...")
            self._started = True

            if self.on_connected:
                try:
                    self.on_connected()
                except Exception:
                    pass

            self._ws_client.start()
        except Exception as e:
            logger.error("Feishu WS start failed: %s", e, exc_info=True)

    def stop(self):
        self._started = False
        logger.info("Feishu WS listener stopped")


def _ws_event_to_raw(msg, sender) -> dict:
    """Convert SDK-typed WS event objects into a raw dict for the normalizer (v1 format).

    msg: EventMessage  →  fields: message_id, chat_id, chat_type, message_type, content, root_id
    sender: EventSender  →  sender_id: UserId (open_id, user_id, union_id)
    """
    raw_message = {}
    for f in ("message_id", "chat_id", "chat_type", "message_type", "content", "root_id"):
        val = getattr(msg, f, None)
        if val is not None:
            raw_message[f] = val

    raw_sender = {}
    if sender and sender.sender_id:
        sid = sender.sender_id
        for f in ("open_id", "user_id", "union_id"):
            val = getattr(sid, f, None)
            if val is not None:
                raw_sender[f] = val

    return {
        "event": {
            "type": "im.message.receive_v1",
            "message": raw_message,
            "sender": {"sender_id": raw_sender},
        }
    }
