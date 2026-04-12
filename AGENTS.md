# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project

Open WebUI Tools and Functions collection. Each tool/function is a single Python file.

## Directory Structure

```
open-webui-extensions/
├── tools/              # LLM-callable tools
│   └── _template.py    # Template file for new tools
└── functions/          # Function plugins
    ├── pipe/           # Custom model providers
    ├── filter/         # Input/output modifiers
    └── action/         # Chat message buttons
```

## File Structure

Each file has:
1. Top-level docstring with metadata (title, author, description, requirements, version)
2. Main class (`Tools`, `Pipe`, `Filter`, or `Action`)
3. Optional `Valves` / `UserValves` classes for configuration

### Tools
- Methods define callable actions for the LLM
- Use `async` methods for compatibility
- Type hints required for all arguments

### Functions
- **Pipe**: Custom model providers (appears as model in UI)
- **Filter**: `inlet()` for input, `outlet()` for output processing
- **Action**: Adds buttons to chat messages

## Development Environment

- Python project management uses `uv`
  - Add packages: `uv add <package>`
  - Run commands: `uv run <command>`
- Code linting/formatting with `ruff`

## References

- [Open WebUI Tools Docs](https://docs.openwebui.com/features/extensibility/plugin/tools/)
- [Open WebUI Functions Docs](https://docs.openwebui.com/features/extensibility/plugin/functions/)
- [Community Library](https://openwebui.com/search)
