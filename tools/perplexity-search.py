"""
title: Perplexity Web Search Tool
author: abhshk
modified: meteoreight
version: 0.2.0
license: MIT
"""

from pydantic import BaseModel, Field
from typing import Optional, Callable, Any, Dict, List
import requests


class Tools:
    class Valves(BaseModel):
        PERPLEXITY_API_KEY: str = Field(
            default="", description="Required API key to access Perplexity services"
        )
        PERPLEXITY_API_BASE_URL: str = Field(
            default="https://api.perplexity.ai",
            description="The base URL for Perplexity API endpoints",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "perplexity_web_search",
                    "description": "Search the web using Perplexity AI",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query to look up",
                            },
                            "domain_filter": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "Optional list of domains to restrict or "
                                    "exclude from search results. Bare domains "
                                    "(e.g. 'nasa.gov', 'wikipedia.org') act as an "
                                    "allowlist: only those domains are searched. "
                                    "Entries prefixed with '-' (e.g. "
                                    "'-reddit.com', '-pinterest.com') act as a "
                                    "denylist: those domains are excluded. Use "
                                    "either allowlist OR denylist mode, not both. "
                                    "Up to 20 domains. Paths (e.g. "
                                    "'nature.com/articles') and top-level domains "
                                    "(e.g. '.gov', '.edu') are also supported."
                                ),
                            },
                        },
                        "required": ["query"],
                    },
                },
            }
        ]

    async def perplexity_web_search(
        self,
        query: str,
        domain_filter: Optional[List[str]] = None,
        __event_emitter__: Optional[Callable[[Dict], Any]] = None,
    ) -> str:
        """Search the web using Perplexity AI.

        Args:
            query: The search query to look up.
            domain_filter: Optional list of domains to restrict or exclude
                from search results. Bare domains (e.g. ``"nasa.gov"``) form
                an allowlist; entries prefixed with ``"-"`` (e.g.
                ``"-reddit.com"``) form a denylist. Allowlist and denylist
                modes cannot be combined. Up to 20 domains; paths (e.g.
                ``"nature.com/articles"``) and top-level domains (e.g.
                ``".gov"``) are also supported.
        """
        if not self.valves.PERPLEXITY_API_KEY:
            raise Exception("PERPLEXITY_API_KEY not provided in valves")

        # Status emitter helper
        async def emit_status(
            description: str, status: str = "in_progress", done: bool = False
        ):
            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {
                            "description": description,
                            "status": status,
                            "done": done,
                        },
                    }
                )

        # Initial status
        await emit_status(f"Asking Perplexity: {query}", "searching")

        headers = {
            "Authorization": f"Bearer {self.valves.PERPLEXITY_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "sonar",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful search assistant. Provide concise and accurate information.",
                },
                {"role": "user", "content": query},
            ],
            "web_search_options": {"search_context_size": "medium"},
        }

        try:
            await emit_status("Processing search results...", "processing")

            # Optional domain filtering via Perplexity `search_domain_filter`.
            # Allowlist (bare domains) and denylist (prefixed with "-") cannot
            # be combined in a single request; cap at the API maximum of 20.
            if domain_filter:
                has_allow = any(not d.startswith("-") for d in domain_filter)
                has_deny = any(d.startswith("-") for d in domain_filter)
                if has_allow and has_deny:
                    raise Exception(
                        "domain_filter cannot mix allowlist and denylist "
                        "entries: use bare domains (allowlist) OR '-' prefixed "
                        "domains (denylist), not both."
                    )
                payload["search_domain_filter"] = domain_filter[:20]

            response = requests.post(
                f"{self.valves.PERPLEXITY_API_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()

            content = result["choices"][0]["message"]["content"]
            citations = result.get("citations", [])

            # Emit Perplexity as primary source
            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "citation",
                        "data": {
                            "document": [content],
                            "metadata": [{"source": "Perplexity AI Search"}],
                            "source": {"name": "Perplexity AI"},
                        },
                    }
                )

            # Emit each URL citation
            if citations and __event_emitter__:
                for url in citations:
                    await __event_emitter__(
                        {
                            "type": "citation",
                            "data": {
                                "document": [content],
                                "metadata": [{"source": url}],
                                "source": {"name": url},
                            },
                        }
                    )

            # Complete status
            await emit_status(
                "Search completed successfully", status="complete", done=True
            )

            # Format response with all citations
            response_text = f"{content}\n\nSources:\n"
            response_text += "- Perplexity AI Search\n"
            for url in citations:
                response_text += f"- {url}\n"

            return response_text

        except Exception as e:
            error_msg = f"Error performing web search: {str(e)}"
            await emit_status(error_msg, status="error", done=True)
            return error_msg
