"""
title: Action Function Name
author: Your Name
author_url: https://example.com
git_url: https://github.com/username/repo
description: Action button for chat messages
required_open_webui_version: 0.4.0
requirements:
version: 0.1.0
licence: MIT
"""

from pydantic import BaseModel, Field


class Action:
    def __init__(self):
        """Initialize the Action Function."""
        self.valves = self.Valves()

    class Valves(BaseModel):
        """Configuration settings."""
        enabled: bool = Field(
            default=True,
            description="Enable this action"
        )

    async def action(self) -> dict:
        """
        Define the action button configuration.

        :return: Action configuration dict
        """
        return {
            "id": "example_action",
            "name": "Example Action",
            "icon": "star",
            "description": "Perform an example action on the message"
        }

    async def process(
        self,
        body: dict,
        __user__: dict = None,
        __event_emitter__=None
    ) -> str:
        """
        Process the action when button is clicked.

        :param body: Contains message and chat info
        :param __user__: User context
        :param __event_emitter__: Event emitter for feedback
        :return: Result message
        """
        message = body.get("message", {})
        content = message.get("content", "")

        # Your action logic here
        result = f"Action processed: {content[:50]}..."

        if __event_emitter__:
            await __event_emitter__({
                "type": "status",
                "data": {"description": "Action completed!", "done": True}
            })

        return result
