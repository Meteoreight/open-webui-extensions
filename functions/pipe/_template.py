"""
title: Pipe Function Name
author: Your Name
author_url: https://example.com
git_url: https://github.com/username/repo
description: Custom model provider or agent
required_open_webui_version: 0.4.0
requirements: httpx
version: 0.1.0
licence: MIT
"""

from pydantic import BaseModel, Field
from typing import Optional, Generator, AsyncGenerator


class Pipe:
    def __init__(self):
        """Initialize the Pipe Function."""
        self.type = "manifold"
        self.id = "pipe_template"
        self.name = "Template Pipe"
        self.valves = self.Valves()

    class Valves(BaseModel):
        """Configuration settings."""
        api_key: str = Field(
            default="",
            description="API key for the service"
        )
        base_url: str = Field(
            default="https://api.example.com",
            description="Base URL for the API"
        )

    def pipes(self) -> list[dict]:
        """
        Return list of available models.
        Used when type is "manifold" to expose multiple models.
        """
        return [
            {"id": "model-1", "name": "Model 1"},
            {"id": "model-2", "name": "Model 2"},
        ]

    async def pipe(
        self,
        body: dict,
        __user__: dict = None,
        __event_emitter__=None
    ) -> AsyncGenerator[str, None]:
        """
        Main pipe function that processes the request.

        :param body: The request body containing messages and parameters
        :param __user__: User context
        :param __event_emitter__: Event emitter for streaming
        :yield: Streamed response chunks
        """
        messages = body.get("messages", [])

        # Your processing logic here
        response = "This is a response from the pipe function."

        yield response
