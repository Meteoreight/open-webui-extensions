"""
title: Excel Evidence Guard
author: Meteoreight
author_url: https://github.com/Meteoreight
git_url: https://github.com/Meteoreight/open-webui-extensions
description: Warn when an answer discusses an attached Excel workbook but cites no cell references
required_open_webui_version: 0.8.9
requirements:
version: 0.1.0
licence: MIT
"""

import re

from pydantic import BaseModel, Field

# Sheet-qualified reference ("Data!B2", "'Q1 Data'!B2:F20") or a bare range
# ("B2:F20"). A lone cell like "B2" is not accepted to avoid false positives.
_CELL = r"\$?[A-Za-z]{1,3}\$?\d{1,7}"
_SHEET = r"(?:'[^']+'|[A-Za-z0-9_^\[\]. ]+)"
CELL_REF_RE = re.compile(rf"{_SHEET}!{_CELL}(?:\s*:\s*{_CELL})?|{_CELL}\s*:\s*{_CELL}")

EXCEL_EXTENSIONS = (".xlsx", ".xlsm")
INSPECTOR_MARKERS = ("excel_inspector", "inspect_workbook")

DEFAULT_WARNING = (
    "> ⚠️ This answer discusses the attached Excel workbook but cites no cell "
    "references (e.g. `Data!B2:F20`). Cross-check it against the excel_inspector "
    "report before relying on it."
)


def _mentions_excel(messages: list) -> bool:
    """True when the conversation used the inspector or carries Excel citations."""
    for message in messages:
        if not isinstance(message, dict):
            continue
        output = message.get("output")
        if isinstance(output, list):
            for item in output:
                if isinstance(item, dict) and item.get("type") == "function_call":
                    name = str(item.get("name") or "")
                    arguments = str(item.get("arguments") or "")
                    if any(
                        marker in name or marker in arguments
                        for marker in INSPECTOR_MARKERS
                    ):
                        return True
        sources = message.get("sources")
        if isinstance(sources, list):
            for source in sources:
                if not isinstance(source, dict):
                    continue
                candidates = [source.get("source", {}).get("name", "")]
                candidates += [
                    meta.get("name", "")
                    for meta in source.get("metadata", [])
                    if isinstance(meta, dict)
                ]
                if any(
                    isinstance(name, str) and ext in name.lower()
                    for name in candidates
                    for ext in EXCEL_EXTENSIONS
                ):
                    return True
    return False


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return ""


class Filter:
    def __init__(self):
        self.valves = self.Valves()

    class Valves(BaseModel):
        """Configuration settings."""

        enabled: bool = Field(default=True, description="Enable this filter")
        warning: str = Field(
            default=DEFAULT_WARNING,
            description="Warning appended to answers that cite no Excel cell references",
        )

    async def outlet(
        self,
        body: dict,
        __user__: dict = None,
    ) -> dict:
        """
        Append a warning when the latest assistant message discusses an Excel
        workbook (inspector tool call or Excel citations present in the chat)
        but its answer contains no cell references. The answer text itself is
        never rewritten.

        :param body: The response body
        :param __user__: User context
        :return: The (possibly annotated) response body
        """
        if not self.valves.enabled:
            return body
        messages = body.get("messages") or []
        if not messages or not _mentions_excel(messages):
            return body

        target = None
        message_id = body.get("id")
        for message in reversed(messages):
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            if message_id is None or message.get("id") == message_id:
                target = message
                break
        if target is None:
            return body

        content = target.get("content")
        text = _text_of(content)
        if not text.strip() or CELL_REF_RE.search(text):
            return body

        warning = self.valves.warning.strip()
        if isinstance(content, str):
            target["content"] = f"{text.rstrip()}\n\n{warning}"
        else:
            content.append({"type": "text", "text": f"\n\n{warning}"})
        return body
