from code_review_agent.actions.base import BaseAction


class ReviewBranchAction(BaseAction):
    name = "review_branch"

    async def execute(self, normalized: dict, session) -> str:
        return (
            "Branch review is not yet implemented. "
            "Please use `review PR <url>` to review a specific pull request instead."
        )
