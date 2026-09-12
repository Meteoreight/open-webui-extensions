# File Translator

## Overview

`tools/file-translator.py` translates files attached to a chat message (`.docx`, `.xlsx`, `.pptx`, `.pdf`) into a target language and attaches the translated copies to the assistant message. Documents are parsed into text segments, grouped into size-limited chunks, translated in parallel by a worker model, and written back into the original document structure — so tables, text boxes, shapes, notes and (for PDF) page layout survive the translation.

Internals:

1. Attached files are read directly from Open WebUI storage (`__files__` → `Files.get_file_by_id` → `Storage.get_file`).
2. The document is parsed at package level:
   - **docx** — `word/document.xml`, headers/footers, footnotes/endnotes, text boxes/shapes, SmartArt drawings, chart parts (best effort)
   - **pptx** — slides, grouped shapes, tables, notes slides, chart/diagram parts (best effort); slide-number fields are skipped
   - **xlsx** — `xl/sharedStrings.xml` (all text cells; formulas/numbers untouched; charts not translated)
   - **pdf** — text blocks with bounding box, font size and color (pymupdf); original text is redacted and the translation is re-inserted in place with automatic font-size shrinking and CJK font embedding
3. Segments are greedily packed into chunks (default 4000 chars); oversized segments are split at sentence boundaries and re-joined after translation.
4. Chunks are translated via the internal Open WebUI API (`generate_chat_completion`) — no API key needed, the calling user's model permissions apply. Two or more chunks run in parallel (`asyncio.gather` + semaphore). Each chunk is a numbered JSON object so segment boundaries survive the round trip.
5. The translated document is uploaded (`upload_file_handler`), persisted on the message (`Chats.add_message_files_by_id_and_message_id`) and attached in the UI via a `chat:message:files` event.

Progress is reported as status events ("Parsing report.docx", "report.docx: translating chunks 3/12", ...) throttled to about ten updates per file.

## Requirements

- Open WebUI with tools enabled (built and verified against the fork in this workspace)
- Python packages (auto-installed from the tool header): `lxml`, `pymupdf`
- A model id configured in the Valves that the calling users are allowed to use

## Installation

1. Open **Admin Panel → Workspace → Tools**
2. Import `tools/file-translator.py` (or paste its content as a new tool)
3. Open the tool's **Valves** and set `translation_model` to the model id of the translation worker (e.g. `gpt-4o-mini`, or any local model id)
4. Enable the tool for the models/chats that need it
5. Optional: register `skills/file-translation.md` as a skill for the main chat model so it knows when and how to call the tool

## Valves

| Valve | Default | Description |
|---|---|---|
| `translation_model` | `""` | **Required.** Model id of the translation worker. |
| `chunk_char_limit` | `4000` | Maximum characters packed into one translation chunk. |
| `max_parallel_translations` | `4` | Maximum concurrent translation requests. |
| `request_timeout` | `300` | Timeout (seconds) per translation request. |
| `temperature` | `0.1` | Sampling temperature for the translation model. |
| `glossary` | `""` | Admin default glossary, one `source=target` pair per line. |
| `show_status` | `True` | Emit progress status events to the UI. |

### UserValves

| Valve | Default | Description |
|---|---|---|
| `default_target_language` | `""` | Used when the model call omits `target_language`. |
| `glossary` | `""` | Per-user persistent glossary. |

## Parameters (`translate_file`)

| Parameter | Type | Description |
|---|---|---|
| `target_language` | string | Language to translate into (e.g. `Japanese`, `en`). Falls back to UserValves. |
| `glossary` | string | Inline glossary, one `source=target` pair per line. |
| `glossary_file` | string | Name or id of an attached glossary file. Comma-separated names allowed. |
| `source_language` | string | Optional source language hint (auto-detected when empty). |

## Glossary

Four sources are merged with per-term precedence (highest first):

1. `glossary` argument (inline, from the conversation)
2. `glossary_file` argument (attached file)
3. UserValves `glossary`
4. admin Valves `glossary`

Supported glossary file formats:

- `.csv` / `.tsv` — column 1 = source term, column 2 = target term; a header row is detected and skipped
- `.xlsx` — first worksheet, first two non-empty cells per row
- `.txt` / `.md` — one `source=target` (or tab-separated) pair per line, `#` starts a comment

## Examples

```
User: Translate report.docx into Japanese.
→ translate_file(target_language="Japanese")

User: spec.xlsx を英語へ。用語集は terms.csv を使って。
→ translate_file(target_language="English", glossary_file="terms.csv")

User: Keep "Neural Engine" as-is in the pptx translation to French.
→ translate_file(target_language="French", glossary="Neural Engine=Neural Engine")
```

## Response format (to the model)

```
Translated into Japanese using a glossary with 12 terms:
- report.docx: 128 segments in 12 chunks -> report_ja.docx (attached)
The translated file(s) have been attached to this message.
```

Failures are reported per file (`FAILED (...)`) instead of raising, and error status events are emitted to the UI.

## Limitations

- PDF output preserves the layout approximately; dense or multi-column pages may reflow.
- Chart text (docx/pptx) is translated best-effort via cached label values.
- xlsx charts and formulas are not translated; only shared text cells are.
- Rich formatting *inside* a paragraph (mixed bold/italic runs) collapses onto the first run's formatting; paragraph-level styles are preserved.
- Chunks whose model reply is not valid JSON after one retry are left in the source language and counted in the summary.
