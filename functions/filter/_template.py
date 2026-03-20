"""
title: Filter Function Name
author: Your Name
author_url: https://example.com
git_url: https://github.com/username/repo
description: Filter to modify input/output messages
required_open_webui_version: 0.4.0
requirements:
version: 0.1.0
licence: MIT
"""

from pydantic import BaseModel, Field
from typing import Optional


class Filter:
    def __init__(self):
        """Initialize the Filter Function."""
        self.valves = self.Valves()

    class Valves(BaseModel):
        """Configuration settings."""
        enabled: bool = Field(
            default=True,
            description="Enable this filter"
        )

    async def inlet(
        self,
        body: dict,
        __user__: dict = None
    ) -> dict:
        """
        Process incoming messages before they reach the model.

        :param body: The request body
        :param __user__: User context
        :return: Modified request body
        """
        messages = body.get("messages", [])

        # Modify messages before sending to model
        # Example: Add system message, filter content, etc.

        return body

    async def outlet(
        self,
        body: dict,
        __user__: dict = None
    ) -> dict:
        """
        Process outgoing messages after they come from the model.

        :param body: The response body
        :param __user__: User context
        :return: Modified response body
        """
        messages = body.get("messages", [])

        # Modify messages after receiving from model
        # Example: Format response, add citations, etc.

        return body
