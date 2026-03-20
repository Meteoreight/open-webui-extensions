"""
title: Code Interpreter File Preparer
author: ten
author_url: https://github.com/Meteoreight
git_url: https://github.com/Meteoreight/open-webui-extensions
description: Prepare uploaded files for Code Interpreter by ensuring they are accessible in /mnt/uploads/
required_open_webui_version: 0.8.9
version: 0.1.0
licence: MIT
"""

from pydantic import BaseModel, Field

# Enable file handling capability
file_handler = True


class Tools:
    def __init__(self):
        """Initialize the Tool."""
        self.citation = True
        self.valves = self.Valves()

    class Valves(BaseModel):
        """Configuration settings for the tool."""

        SHOW_STATUS: bool = Field(
            default=True,
            description="Show status messages in the UI",
        )

    async def prepare_files_for_code_interpreter(
        self,
        __user__: dict = None,
        __event_emitter__=None,
        __files__: list = None,
    ) -> str:
        """
        Prepare uploaded files for Code Interpreter.

        This tool retrieves information about files attached to the chat
        and returns their paths in the /mnt/uploads/ directory where
        they are accessible by the Code Interpreter.

        :param __user__: User context (injected by Open WebUI)
        :param __event_emitter__: Event emitter for status updates
        :param __files__: List of attached files (injected by Open WebUI)
        :return: File paths and usage instructions for Code Interpreter
        """
        if __files__ is None:
            __files__ = []

        # Emit status if enabled
        if self.valves.SHOW_STATUS and __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {"description": "Preparing files for Code Interpreter...", "done": False},
                }
            )

        # Check if files are attached
        if not __files__:
            result = "No files attached to this chat. Please upload files first."
            if self.valves.SHOW_STATUS and __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {"description": "No files found", "done": True},
                    }
                )
            return result

        # Process files
        file_list = []
        for file_info in __files__:
            name = file_info.get("name", "unknown")
            file_type = file_info.get("type", "file")
            file_id = file_info.get("id", "")
            path = f"/mnt/uploads/{name}"

            file_list.append(
                {
                    "name": name,
                    "type": file_type,
                    "id": file_id,
                    "path": path,
                }
            )

        # Build response
        result_lines = [
            f"Prepared {len(file_list)} file(s) for Code Interpreter:\n",
            "| File | Path | Type |",
            "|------|------|------|",
        ]

        for f in file_list:
            result_lines.append(f"| {f['name']} | {f['path']} | {f['type']} |")

        result_lines.extend(
            [
                "",
                "Usage in Code Interpreter (use execute_code tool):",
                "```python",
                "# Example: Read a CSV file",
                "import pandas as pd",
                "df = pd.read_csv('/mnt/uploads/your_file.csv')",
                "print(df.head())",
                "",
                "# Example: Read an Excel file",
                "df = pd.read_excel('/mnt/uploads/your_file.xlsx')",
                "",
                "# Example: Read a text file",
                "with open('/mnt/uploads/your_file.txt', 'r') as f:",
                "    content = f.read()",
                "```",
            ]
        )

        result = "\n".join(result_lines)

        # Emit completion status
        if self.valves.SHOW_STATUS and __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": f"Prepared {len(file_list)} file(s)",
                        "done": True,
                    },
                }
            )

        return result
