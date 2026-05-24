import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger(__name__)

from code_review_agent.api.health import router as health_router
from code_review_agent.api.management import router as management_router
from code_review_agent.api.webhook_github import router as github_router
from code_review_agent.api.webhook_im import router as im_router

_ws_thread: threading.Thread | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ws_thread
    logger.info("=" * 50)
    logger.info("Code Review Agent starting up")
    try:
        from code_review_agent.bootstrap import bootstrap, attach_to_app
        await bootstrap()
        attach_to_app(app)

        feishu_ws = getattr(app.state, "feishu_ws", None)
        if feishu_ws:
            _ws_thread = threading.Thread(
                target=feishu_ws.start,
                name="feishu-ws",
                daemon=True,
            )
            _ws_thread.start()
            logger.info("Feishu WebSocket listener started")

        logger.info("Code Review Agent ready")
        logger.info("=" * 50)
    except Exception as e:
        logger.error("Bootstrap failed: %s", e, exc_info=True)

    yield

    feishu_ws = getattr(app.state, "feishu_ws", None)
    if feishu_ws:
        feishu_ws.stop()
    logger.info("Code Review Agent shut down")


app = FastAPI(
    title="Code Review Agent",
    description="AI-powered code review agent with IM integration",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router, tags=["health"])
app.include_router(github_router, tags=["github"], prefix="/api/github")
app.include_router(im_router, tags=["im"], prefix="/api/im")
app.include_router(management_router, tags=["management"], prefix="/api")
