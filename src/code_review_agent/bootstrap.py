"""Application bootstrap: wires all components together.

This is the central wiring module. It reads configuration, creates all
service instances, and attaches them to the FastAPI app state.

For the Feishu verification flow:
1. Feishu sends webhook to POST /api/im/feishu
2. api/webhook_im.py calls app.state.im_gateway.handle_message("feishu", body)
3. IMGateway: normalize → classify intent → dispatch action → reply
"""

import logging
from pathlib import Path

from code_review_agent.config import Config, get_config, reload_config
from code_review_agent.llm.cost_tracker import CostTracker
from code_review_agent.llm.fallback import FallbackChain
from code_review_agent.llm.health import HealthChecker
from code_review_agent.llm.router import ModelRouter
from code_review_agent.llm.providers import (
    ClaudeProvider,
    CustomProvider,
    OllamaProvider,
    OpenAIProvider,
)

logger = logging.getLogger(__name__)


class AppContext:
    """Holds all initialized service instances."""

    def __init__(self):
        self.config: Config | None = None
        self.model_router: ModelRouter | None = None
        self.fallback_chain: FallbackChain | None = None
        self.cost_tracker: CostTracker | None = None
        self.health_checker: HealthChecker | None = None
        self.rule_engine = None
        self.orchestrator = None
        self.github_client = None
        self.gitlab_client = None
        self.conversation_manager = None
        self.intent_router = None
        self.action_dispatcher = None
        self.im_gateway = None
        self.im_sender = None
        self.webhook_dispatcher = None
        self.platform_commenter = None
        self.feishu_api: object = None  # FeishuSDKClient
        self.feishu_ws: object = None   # FeishuWSListener
        self.skill_loader: object = None  # SkillLoader


_ctx = AppContext()


def get_app_context() -> AppContext:
    return _ctx


async def bootstrap(config_dir: str = "config") -> AppContext:
    """Initialize all components and return the application context.

    Call this once at startup. It wires:
      config → LLM router → fallback chain → orchestrator
      config → GitHub/GitLab clients
      config → conversation manager
      config → intent router → action dispatcher
      config → IM sender → IM gateway
      config → webhook dispatcher
    """
    ctx = _ctx

    # ── 1. Configuration ──
    ctx.config = get_config(config_dir)
    logger.info("Configuration loaded from %s", config_dir)

    # ── 2. LLM Layer ──
    llm_cfg = ctx.config.load_sub_config("llm", "config_path")
    if not llm_cfg:
        llm_cfg = ctx.config.get("llm", default={})
    ctx.model_router = ModelRouter(llm_cfg)
    ctx.fallback_chain = FallbackChain(ctx.model_router)
    ctx.cost_tracker = CostTracker(llm_cfg.get("pricing", {}))
    ctx.health_checker = HealthChecker(ctx.model_router.providers)

    providers = ctx.model_router.list_providers()
    logger.info("LLM providers: %s", providers)
    logger.info("Model aliases: %s", list(ctx.model_router.model_registry.keys()))

    # ── 3. Rule Engine ──
    from code_review_agent.reviewers.rule_engine import RuleEngine
    ctx.rule_engine = RuleEngine()

    # Load custom skills from skills/ directory
    # Tier 1 (global): always loaded. Tier 2 (language): loaded per-review.
    from code_review_agent.skills.loader import SkillLoader
    ctx.skill_loader = SkillLoader("skills")
    global_rules = ctx.skill_loader.get_global_rules()
    for rule in global_rules:
        ctx.rule_engine.add_rule(rule)
    logger.info(
        "Rule engine: %d built-in + %d global skill rules loaded",
        len(ctx.rule_engine.rules) - len(global_rules),
        len(global_rules),
    )

    # ── 4. Orchestrator ──
    from code_review_agent.core.orchestrator import Orchestrator
    ctx.orchestrator = Orchestrator(ctx.model_router, ctx.fallback_chain, ctx.rule_engine)
    logger.info("Orchestrator initialized")

    # ── 5. Git Platform Clients ──
    github_cfg = ctx.config.get("github", default={})
    gitlab_cfg = ctx.config.get("gitlab", default={})

    if github_cfg.get("token"):
        from code_review_agent.platforms.github import GitHubClient
        ctx.github_client = GitHubClient(token=github_cfg["token"])
        logger.info("GitHub client initialized")
    else:
        logger.warning("GitHub token not configured — PR review via GitHub unavailable")

    if gitlab_cfg.get("token"):
        from code_review_agent.platforms.gitlab import GitLabClient
        ctx.gitlab_client = GitLabClient(
            url=gitlab_cfg.get("url", "https://gitlab.com"),
            token=gitlab_cfg["token"],
        )
        logger.info("GitLab client initialized")

    # ── 6. Conversation Manager ──
    from code_review_agent.conversation.manager import ConversationManager
    session_cfg = ctx.config.get("im", default={}).get("session", {})
    ctx.conversation_manager = ConversationManager(
        ttl=session_cfg.get("ttl", 3600),
        max_history=session_cfg.get("max_history_turns", 20),
    )
    logger.info("Conversation manager initialized (ttl=%ds)", session_cfg.get("ttl", 3600))

    # ── 7. Intent Router ──
    from code_review_agent.router.intent_router import IntentRouter
    ctx.intent_router = IntentRouter(ctx.model_router, ctx.fallback_chain)
    logger.info("Intent router initialized")

    # ── 8. Action Dispatcher + Handlers ──
    from code_review_agent.actions.base import ActionDispatcher
    from code_review_agent.router.intent_router import Intent
    from code_review_agent.actions.review_pr import ReviewPRAction
    from code_review_agent.actions.review_branch import ReviewBranchAction
    from code_review_agent.actions.review_commit import ReviewCommitAction
    from code_review_agent.actions.explain import ExplainAction
    from code_review_agent.actions.suggest_fix import SuggestFixAction
    from code_review_agent.actions.refactor import RefactorAction
    from code_review_agent.actions.search import SearchAction
    from code_review_agent.actions.chat import ChatAction

    ctx.action_dispatcher = ActionDispatcher(
        core_engine=ctx.orchestrator,
        llm_router=ctx.model_router,
        fallback=ctx.fallback_chain,
    )

    ctx.action_dispatcher.register(Intent.REVIEW_PR, ReviewPRAction(
        core_engine=ctx.orchestrator,
        llm_router=ctx.model_router,
        github_client=ctx.github_client,
        gitlab_client=ctx.gitlab_client,
        skill_loader=ctx.skill_loader,
    ))
    ctx.action_dispatcher.register(Intent.REVIEW_BRANCH, ReviewBranchAction(
        core_engine=ctx.orchestrator,
        llm_router=ctx.model_router,
        github_client=ctx.github_client,
        gitlab_client=ctx.gitlab_client,
        skill_loader=ctx.skill_loader,
    ))
    ctx.action_dispatcher.register(Intent.REVIEW_COMMIT, ReviewCommitAction())
    ctx.action_dispatcher.register(Intent.EXPLAIN, ExplainAction(
        llm_router=ctx.model_router, fallback=ctx.fallback_chain,
    ))
    ctx.action_dispatcher.register(Intent.SUGGEST_FIX, SuggestFixAction(
        llm_router=ctx.model_router, fallback=ctx.fallback_chain,
    ))
    ctx.action_dispatcher.register(Intent.REFACTOR, RefactorAction(
        llm_router=ctx.model_router, fallback=ctx.fallback_chain,
    ))
    ctx.action_dispatcher.register(Intent.SEARCH, SearchAction())
    ctx.action_dispatcher.register(Intent.CHAT, ChatAction(
        llm_router=ctx.model_router, fallback=ctx.fallback_chain,
    ))
    logger.info("Action dispatcher initialized with %d handlers", len(ctx.action_dispatcher.handlers))

    # ── 9. IM Layer ──
    im_cfg = ctx.config.load_sub_config("im", "config_path")

    from code_review_agent.im.normalizer import MessageNormalizer
    from code_review_agent.im.sender import IMSender
    from code_review_agent.im.gateway import IMGateway

    # Initialize Feishu SDK client only if WebSocket mode is enabled
    # (SDK uses lazy imports to avoid startup hangs when network is limited)
    feishu_cfg = im_cfg.get("platforms", {}).get("feishu", {})
    ctx.feishu_api = None
    use_ws = feishu_cfg.get("use_websocket", True)
    if use_ws and feishu_cfg.get("enabled") and feishu_cfg.get("app_id") and feishu_cfg.get("app_secret"):
        try:
            from code_review_agent.im.feishu_sdk import FeishuSDKClient
            ctx.feishu_api = FeishuSDKClient(
                app_id=feishu_cfg["app_id"],
                app_secret=feishu_cfg["app_secret"],
            )
            logger.info("Feishu SDK client initialized")
        except ImportError as e:
            logger.warning("Feishu SDK not available (lark-oapi import failed): %s", e)

    ctx.im_sender = IMSender(
        platform_configs=im_cfg.get("platforms", {}),
        feishu_client=ctx.feishu_api,
    )
    normalizer = MessageNormalizer()

    ctx.im_gateway = IMGateway(
        normalizer=normalizer,
        sender=ctx.im_sender,
        intent_router=ctx.intent_router,
        action_dispatcher=ctx.action_dispatcher,
        conversation_manager=ctx.conversation_manager,
    )
    logger.info("IM gateway initialized")

    # Initialize Feishu WebSocket listener (for receiving events without ngrok)
    ctx.feishu_ws = None
    if ctx.feishu_api and feishu_cfg.get("use_websocket", True):
        from code_review_agent.im.feishu_sdk import FeishuWSListener

        async def on_feishu_message(raw_event: dict):
            """Route WS events to the IM gateway."""
            try:
                await ctx.im_gateway.handle_message("feishu", raw_event)
            except Exception as e:
                logger.error("WS message handling failed: %s", e)

        ctx.feishu_ws = FeishuWSListener(
            app_id=feishu_cfg["app_id"],
            app_secret=feishu_cfg["app_secret"],
        )
        ctx.feishu_ws.on_message = on_feishu_message
        logger.info("Feishu WS listener created")

    # ── 10. Output Layer ──
    from code_review_agent.output.platform_commenter import PlatformCommenter
    from code_review_agent.output.webhook_dispatcher import WebhookDispatcher
    from code_review_agent.models.webhook import WebhookConfig

    ctx.platform_commenter = PlatformCommenter(
        github_client=ctx.github_client,
        gitlab_client=ctx.gitlab_client,
    )

    webhooks_cfg = ctx.config.load_sub_config("webhooks", "config_path")
    webhook_configs = []
    for wh in webhooks_cfg.get("webhooks", []):
        try:
            webhook_configs.append(WebhookConfig(**wh))
        except Exception as e:
            logger.warning("Skipping invalid webhook config '%s': %s", wh.get("name", "?"), e)
    ctx.webhook_dispatcher = WebhookDispatcher(webhook_configs)
    logger.info("Output layer initialized (%d webhooks)", len(webhook_configs))

    # ── 11. DB (optional) ──
    db_url = ctx.config.get("database", "url", default="")
    if db_url:
        try:
            from code_review_agent.db.repository import init_db
            await init_db(db_url)
            logger.info("Database initialized")
        except Exception as e:
            logger.warning("Database initialization skipped: %s", e)

    logger.info("Bootstrap complete — all components initialized")
    return ctx


def attach_to_app(app):
    """Attach the application context to a FastAPI app's state.

    Call this in the FastAPI startup event.
    """
    ctx = _ctx
    app.state.config = ctx.config
    app.state.model_router = ctx.model_router
    app.state.fallback_chain = ctx.fallback_chain
    app.state.cost_tracker = ctx.cost_tracker
    app.state.health_checker = ctx.health_checker
    app.state.rule_engine = ctx.rule_engine
    app.state.orchestrator = ctx.orchestrator
    app.state.github_client = ctx.github_client
    app.state.gitlab_client = ctx.gitlab_client
    app.state.conversation_manager = ctx.conversation_manager
    app.state.intent_router = ctx.intent_router
    app.state.action_dispatcher = ctx.action_dispatcher
    app.state.im_gateway = ctx.im_gateway
    app.state.im_sender = ctx.im_sender
    app.state.webhook_dispatcher = ctx.webhook_dispatcher
    app.state.platform_commenter = ctx.platform_commenter
    app.state.feishu_api = ctx.feishu_api
    app.state.feishu_ws = ctx.feishu_ws
    app.state.skill_loader = ctx.skill_loader

    logger.info("App context attached to FastAPI state")
