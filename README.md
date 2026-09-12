# Open WebUI Extensions

Collection of tools, functions, and skills for [Open WebUI](https://openwebui.com/).

## Overview

This repository contains custom extensions to enhance Open WebUI functionality:

- **Tools**: LLM-callable tools that extend AI capabilities
- **Functions**: Plugin components including:
  - **Pipe**: Custom model providers
  - **Filter**: Input/output modifiers
  - **Action**: Chat message buttons
- **Skills**: Reusable instruction sets (Markdown) for guiding AI behavior

## Tools

### File Translator

Translates chat-attached docx / xlsx / pptx / pdf files into a target language and attaches the translated copies to the message. Documents are parsed into segments, translated in parallel chunks by a configurable worker model, and written back into the original structure. See [tools/docs/file-translator.md](tools/docs/file-translator.md) for details.

**Features:**
- Preserves structure: tables, nested tables, text boxes, SmartArt (best effort), docx headers/footers/footnotes, pptx grouped shapes and notes, xlsx cell coordinates, PDF layout (approximate)
- Parallel chunk translation with progress status messages in the UI
- Glossary support (inline argument, attached csv/tsv/xlsx/txt/md glossary file, UserValves, admin Valves) with per-term precedence
- Translation worker model configured by model id in Valves (internal API, no API key needed)

**Usage:**
1. Configure the `translation_model` valve with a model id
2. Attach a docx/xlsx/pptx/pdf file and ask "translate this into Japanese"
3. The model calls `translate_file`; the translated file is attached to the message
4. Optionally attach a glossary file and pass its name as `glossary_file`

### Skills Manager

Standalone tool for managing native Workspace Skills (list/show/create/update) for any model.

**Features:**
- List all user skills with metadata
- Show skill details including content
- Create new skills or overwrite existing ones
- Update skill properties (name, description, content, activation)

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

### Playwright UI Tests

Playwright-based UI smoke tests live under `tests/playwright/` and target an already running Open WebUI instance.

Detailed notes for future agents and maintainers are in [tests/playwright/README.md](tests/playwright/README.md).

1. Copy `.env.playwright.example` to `.env.playwright` and fill in:
   - `PLAYWRIGHT_BASE_URL`
   - `PLAYWRIGHT_MODEL_IDS`
   - `PLAYWRIGHT_RAG_MODEL_ID`
   - `PLAYWRIGHT_SSO_EMAIL`
   - `PLAYWRIGHT_SSO_PASSWORD`
2. If you want to validate file-backed RAG, place a real file in `tests/playwright/fixtures/rag/` or set `PLAYWRIGHT_RAG_FILE`.
3. Install test dependencies with `npm install`.
4. Install the browser binary with `npx playwright install chromium`.
5. Run `npm run test:e2e:playwright`.

The auth setup uses the Microsoft SSO button from the UI and stores Playwright auth state in `tests/playwright/.auth/`.

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

## Skills

Markdown-based instruction sets for guiding AI behavior. Added in Open WebUI v0.8.0.

**Features:**
- Reusable instructions (e.g., code review guidelines, writing style rules)
- `$` mention in chat for direct injection
- Model-attached skills for lazy-loading

**Available skills:**
- `code_interpreter_usage` — recipes for parsing docx/xlsx/pptx/pdf in code interpreter
- `file-translation` — when and how to call the File Translator tool

**File Format:**
```markdown
---
name: skill-name
description: Brief description of the skill
---

# Skill Title

Instructions in Markdown...
```

## Directory Structure

```
open-webui-extensions/
├── skills/             # Markdown instruction sets (v0.8.0+)
│   ├── _template.md
│   └── file-translation.md
├── tools/              # LLM-callable tools
│   ├── _template.py
│   ├── file-translator.py
│   └── skills_manager.py
└── functions/          # Function plugins
    ├── pipe/           # Custom model providers
    ├── filter/         # Input/output modifiers
    └── action/         # Chat message buttons
```

## References

- [Open WebUI Tools Documentation](https://docs.openwebui.com/features/extensibility/plugin/tools/)
- [Open WebUI Functions Documentation](https://docs.openwebui.com/features/extensibility/plugin/functions/)
- [Open WebUI Skills Documentation](https://docs.openwebui.com/features/ai-knowledge/skills/) (v0.8.0+)
- [Open WebUI Community Library](https://openwebui.com/search)

## License

MIT
