import logging
from abc import ABC, abstractmethod

from code_review_agent.router.intent_router import Intent

logger = logging.getLogger(__name__)


class BaseAction(ABC):
    """Abstract base for all action handlers."""

    name: str = "base"

    @abstractmethod
    async def execute(self, normalized: dict, session) -> str:
        """Execute the action and return a response string."""
        ...


class BaseReviewAction(BaseAction):
    """Shared base for review actions (PR, commit, branch).

    Handles: skill loading, project .code-review/ config, diff parsing,
    orchestrator call, and context storage.
    """

    def __init__(self, core_engine=None, llm_router=None, github_client=None, gitlab_client=None, skill_loader=None):
        self.core_engine = core_engine
        self.llm_router = llm_router
        self.github = github_client
        self.gitlab = gitlab_client
        self.skill_loader = skill_loader

    async def run_review_pipeline(self, ctx, repo_name: str, branch: str, session) -> str:
        """Execute the full review pipeline: skills → diff → orchestrator → store context."""
        from code_review_agent.actions.utils import detect_languages, format_result, store_review_context
        from code_review_agent.core.diff_parser import DiffParser

        skill_prompts = ""
        lang_rules: list[dict] = []
        if self.skill_loader:
            langs = detect_languages(ctx.files)
            skill_prompts = self.skill_loader.get_prompts_for_languages(langs)
            lang_rules = self.skill_loader.get_rules_for_languages(langs)

            prompt, rules = await self._load_project_config(repo_name, branch)
            if prompt:
                skill_prompts += "\n\n" + prompt
            lang_rules.extend(rules)

        diff_text = DiffParser().diff_to_text(ctx.files)
        result = await self.core_engine.review(ctx, diff_text, skill_prompts, custom_rules=lang_rules)
        store_review_context(session, result, diff_text)
        return format_result(result)

    async def _load_project_config(self, repo_name: str, branch: str) -> tuple[str, list[dict]]:
        """Load .code-review/review.md and rules.yaml from the project repo."""
        if not self.github or not self.skill_loader:
            return "", []
        prompt = ""
        rules: list[dict] = []
        try:
            content = self.github.get_file_content(repo_name, ".code-review/review.md", ref=branch)
            if content:
                prompt = self.skill_loader.load_project_prompt(content)
        except Exception:
            pass
        try:
            content = self.github.get_file_content(repo_name, ".code-review/rules.yaml", ref=branch)
            if content:
                rules = self.skill_loader.load_project_rules(content)
        except Exception:
            pass
        return prompt, rules


class ActionDispatcher:
    """Routes intents to their corresponding action handlers."""

    def __init__(self, core_engine=None, llm_router=None, fallback=None):
        self.handlers: dict[Intent, BaseAction] = {}
        self.core_engine = core_engine
        self.llm_router = llm_router
        self.fallback = fallback

    def register(self, intent: Intent, handler: BaseAction) -> None:
        self.handlers[intent] = handler

    async def dispatch(self, intent: Intent, normalized: dict, session) -> str:
        handler = self.handlers.get(intent)
        if handler is None:
            logger.warning("No handler for intent %s, falling back to chat", intent)
            handler = self.handlers.get(Intent.CHAT)
        if handler is None:
            return "I didn't understand that. Try 'review PR #42' or 'help'."
        try:
            return await handler.execute(normalized, session)
        except Exception as e:
            logger.exception("Action '%s' failed", handler.name)
            return f"Action failed: {e}"
