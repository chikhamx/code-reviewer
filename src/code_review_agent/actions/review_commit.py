from code_review_agent.actions.base import BaseAction


class ReviewCommitAction(BaseAction):
    name = "review_commit"

    async def execute(self, normalized: dict, session) -> str:
        return (
            "Commit review is not yet implemented. "
            "Please use `review PR <url>` to review a specific pull request."
        )
