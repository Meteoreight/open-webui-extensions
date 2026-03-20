"""
title: Tool Name
author: Your Name
author_url: https://example.com
git_url: https://github.com/username/repo
description: Description of what this tool does
required_open_webui_version: 0.4.0
requirements: requests, httpx
version: 0.1.0
licence: MIT
"""

from pydantic import BaseModel, Field


class Tools:
    def __init__(self):
        """Initialize the Tool."""
        self.citation = True
        self.valves = self.Valves()

    class Valves(BaseModel):
        """Configuration settings for the tool."""
        api_key: str = Field(
            default="",
            description="API key for the service"
        )
        max_results: int = Field(
            default=10,
            description="Maximum number of results to return"
        )

    class UserValves(BaseModel):
        """User-specific configuration."""
        preferred_language: str = Field(
            default="en",
            description="Preferred language for responses"
        )

    async def example_method(
        self,
        query: str,
        __user__: dict = None,
        __event_emitter__=None
    ) -> str:
        """
        Example tool method.

        :param query: The search query
        :param __user__: User context (injected by Open WebUI)
        :param __event_emitter__: Event emitter for status updates
        :return: The result string
        """
        if __event_emitter__:
            await __event_emitter__({
                "type": "status",
                "data": {"description": "Processing...", "done": False}
            })

        # Your logic here
        result = f"Processed: {query}"

        if __event_emitter__:
            await __event_emitter__({
                "type": "status",
                "data": {"description": "Complete!", "done": True}
            })

        return result
