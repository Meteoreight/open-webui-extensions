# Open WebUI Extensions

Collection of tools and functions for [Open WebUI](https://openwebui.com/).

## Overview

This repository contains custom extensions to enhance Open WebUI functionality:

- **Tools**: LLM-callable tools that extend AI capabilities
- **Functions**: Plugin components including:
  - **Pipe**: Custom model providers
  - **Filter**: Input/output modifiers
  - **Action**: Chat message buttons

## Tools

### Code Interpreter File Preparer

Prepares uploaded files for Code Interpreter by ensuring they are accessible in `/mnt/uploads/`.

**Features:**
- Lists all attached files with their paths
- Provides usage examples for Python code execution
- Status updates during file processing

**Usage:**
1. Upload files to your chat
2. Call `prepare_files_for_code_interpreter` tool
3. Use the returned paths in `execute_code` tool

### Skills Manager

Standalone tool for managing native Workspace Skills (list/show/create/update/delete) for any model.

**Features:**
- List all user skills with metadata
- Show skill details including content
- Create new skills or overwrite existing ones
- Update skill properties (name, description, content, activation)
- Delete skills
- Multi-language support (EN, ZH, JA, KO, FR, DE, ES, IT, VI, ID)

## Development

### Environment Setup

This project uses `uv` for Python package management:

```bash
# Install dependencies
uv add <package>

# Run commands
uv run <command>

# Run linting
uvx ruff check
```

### Creating New Tools

1. Copy the template file [`tools/_template.py`](tools/_template.py)
2. Update the metadata docstring with your tool information
3. Implement your tool methods in the `Tools` class
4. Follow the Open WebUI tools documentation

### File Structure

Each tool/function file contains:

```python
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
        self.citation = True
        self.valves = self.Valves()

    class Valves(BaseModel):
        # Configuration settings
        pass

    async def tool_method(self, __user__: dict = None, __event_emitter__=None):
        # Tool implementation
        pass
```

## Directory Structure

```
open-webui-extensions/
├── tools/              # LLM-callable tools
│   ├── _template.py
│   ├── code_interpreter_file_preparer.py
│   └── skills_manager.py
└── functions/          # Function plugins
    ├── pipe/           # Custom model providers
    ├── filter/         # Input/output modifiers
    └── action/         # Chat message buttons
```

## References

- [Open WebUI Tools Documentation](https://docs.openwebui.com/features/extensibility/plugin/tools/)
- [Open WebUI Functions Documentation](https://docs.openwebui.com/features/extensibility/plugin/functions/)
- [Open WebUI Community Library](https://openwebui.com/search)

## License

MIT
