# Perplexity Web Search Tool

Lets an Open WebUI model search the live web through Perplexity's Sonar API
and return a cited, natural-language answer.

- File: [`tools/perplexity-search.py`](../perplexity-search.py)
- Version: **0.2.0**
- Author: abhshk
- License: MIT

## Overview

- Calls Perplexity's `/chat/completions` endpoint with the `sonar` model.
- Returns Perplexity's synthesized answer plus the list of citation URLs.
- Emits status events (`searching` → `processing` → `complete`) and citations
  through Open WebUI's event emitter so they render in the chat UI.
- Supports optional **domain filtering**, so the model can scope a query to
  specific sites or exclude low-signal ones per call.

## Requirements

- Python packages: `requests`, `pydantic`.
- A Perplexity API key (set in Valves).

## Installation

1. In Open WebUI, open **Admin Panel → Workspace → Tools**.
2. Import [`tools/perplexity-search.py`](../perplexity-search.py) (or paste its
   contents into a new tool).
3. Open the tool's **Valves** and set `PERPLEXITY_API_KEY`.
4. Enable the tool on the model(s) that should be able to search the web.

## Configuration (Valves)

| Field | Default | Description |
| --- | --- | --- |
| `PERPLEXITY_API_KEY` | `""` | **Required.** Bearer token for the Perplexity API. |
| `PERPLEXITY_API_BASE_URL` | `https://api.perplexity.ai` | Base URL for the Perplexity API. Override only when routing through a compatible proxy/gateway. |

## Exposed Function

### `perplexity_web_search`

Search the web using Perplexity AI.

**Parameters**

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `query` | `string` | yes | The search query to look up. |
| `domain_filter` | `array[string]` | no | Domains to restrict or exclude. See semantics below. |

#### `domain_filter` semantics

`domain_filter` maps directly to Perplexity's top-level `search_domain_filter`
request parameter. It supports two **mutually exclusive** modes:

- **Allowlist** — bare domains; only those domains are searched.
  ```json
  ["nasa.gov", "wikipedia.org"]
  ```
- **Denylist** — prefix each entry with `-` to exclude it.
  ```json
  ["-reddit.com", "-pinterest.com"]
  ```

Rules:

- Allowlist and denylist **cannot be combined** in a single call. A mix is
  rejected with a clear error **before** the request is sent.
- Maximum **20** domains; additional entries are silently dropped.
- A path may be appended to restrict to a section of a site:
  `"nature.com/articles"`.
- A top-level domain wildcard is allowed: `".gov"`, `".edu"`.

When omitted, no `search_domain_filter` is sent and the search is unrestricted.

## Examples

### Basic search

```python
perplexity_web_search(query="What caused the 2023 Silicon Valley Bank collapse?")
```

### Restrict to authoritative domains (allowlist)

```python
perplexity_web_search(
    query="IPCC AR6 synthesis report key findings",
    domain_filter=["science.org", "nature.com", "arxiv.org"],
)
```

### Exclude low-signal sites (denylist)

```python
perplexity_web_search(
    query="Best practices for PostgreSQL autovacuum tuning",
    domain_filter=["-reddit.com", "-quora.com", "-pinterest.com"],
)
```

## Response Format

The function returns a string containing Perplexity's answer followed by a
`Sources:` list:

```text
<Perplexity answer text>

Sources:
- Perplexity AI Search
- https://example.com/source-1
- https://example.com/source-2
```

Each citation URL is also emitted as a citation event so it renders in the
Open WebUI UI.

## How It Works

The request body sent to `POST {PERPLEXITY_API_BASE_URL}/chat/completions`:

```json
{
  "model": "sonar",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful search assistant. Provide concise and accurate information."
    },
    { "role": "user", "content": "<query>" }
  ],
  "web_search_options": { "search_context_size": "medium" },
  "search_domain_filter": ["<included only when domain_filter is provided>"]
}
```

`search_domain_filter` is added to the payload only when the caller supplies
`domain_filter`.

## References

- [Perplexity Sonar API – Quickstart](https://docs.perplexity.ai/docs/sonar/quickstart)
- [Perplexity Search Filters](https://docs.perplexity.ai/docs/sonar/filters)
- [Perplexity Domain Filter Guide](https://docs.perplexity.ai/docs/search/filters/domain-filter)
- [Open WebUI Tools Documentation](https://docs.openwebui.com/features/extensibility/plugin/tools/)
