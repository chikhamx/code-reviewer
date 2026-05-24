from code_review_agent.actions.base import BaseAction


class SearchAction(BaseAction):
    name = "search"

    async def execute(self, normalized: dict, session) -> str:
        return (
            "Code search is not yet implemented in this session. "
            "For now, please use `grep` or your IDE to search the codebase."
        )
