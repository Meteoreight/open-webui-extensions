# Excel Inspector

## Overview

`tools/excel_inspector.py` inspects Excel workbooks attached to a chat message (`.xlsx`, `.xlsm`) and returns a structure map the model can reason over: sheet list, used ranges, header row candidates, column profiles (types, empty/distinct/repeated counts, numeric ranges), sample rows, formulas with cached values, merged range counts and data quality notes — all with `Sheet!Range` references (e.g. `Data!B2:F350`, `'Q1 Data'!A1:B1`).

This is the E1 piece of the Excel strategy: **workbooks are treated as structured data, never routed through RAG**. The tool declares `file_handler: true`, so once it is called the attached workbook is removed from the RAG context and the model works only from the inspection report. The LLM is given schema, statistics and samples — never every cell.

Internals:

1. Attached files are read directly from Open WebUI storage (`__files__` → `Files.get_file_by_id` → `Storage.get_file`), rejecting files whose known size exceeds the limit before reading.
2. Guards run before parsing: file size limit, and a zip-bomb guard rejecting workbooks whose declared expanded content exceeds `max_total_uncompressed_mb`.
3. Merged range counts are collected at zip level (streamed `<mergeCell ` count per worksheet part via `xl/workbook.xml` + rels) because read-only openpyxl does not expose merged cells.
4. One streaming pass per sheet (`openpyxl` read-only, `keep_links=False`, external links cut, macros never executed): used range from non-empty cells, type counts, formula cells (coordinate + first 60 chars), rows retained for analysis — all bounded by the row/column/sheet valves.
5. When formulas are found, a second read-only pass with `data_only=True` fetches the **values Excel cached at save time**; formulas are never recalculated. Files written by libraries (no cached values) report "no cached value".
6. Header row detection scores the first scanned rows (width + string share); column profiles, duplicate counting and data quality notes (mixed types, mostly-empty columns, truncated scans) are computed from the scanned region.
7. Each inspected sheet emits a `citation` event, so the ranges appear in the standard citation panel as `sales.xlsx Data!A1:G5`.
8. Heavy work runs in `asyncio.to_thread` under `asyncio.wait_for` (tools share the backend event loop).

## Requirements

- Open WebUI with tools enabled (openpyxl is bundled with Open WebUI; listed in `requirements:` for other environments)
- No API keys, no external calls

## Installation

1. Open **Admin Panel → Workspace → Tools**
2. Import `tools/excel_inspector.py` (or paste its content as a new tool)
3. Optional: register `skills/excel-analysis.md` as a skill so the model always inspects before answering and ends with an Evidence block
4. Optional: import `functions/filter/excel-evidence-guard.py` as a Function and attach it to models that discuss Excel files — it appends a warning under answers that cite no cell ranges

## Valves

| Valve | Default | Description |
|---|---|---|
| `max_file_mb` | `20` | Reject workbook files larger than this. |
| `max_total_uncompressed_mb` | `200` | Zip bomb guard on the expanded content. |
| `max_sheets_per_file` | `20` | Maximum sheets inspected per workbook. |
| `max_rows_scanned` | `1000` | Maximum rows scanned per sheet. |
| `max_columns` | `150` | Maximum column index considered. |
| `max_formulas_reported` | `50` | Formula cells listed with cached values. |
| `sample_rows` | `5` | Sample data rows included per sheet. |
| `timeout_seconds` | `60` | Overall timeout per workbook. |
| `max_report_chars` | `24000` | Truncation length of the returned report. |
| `show_status` | `True` | Emit progress status events. |
| `emit_citations` | `True` | Emit citation events per inspected sheet. |

## Parameters (`inspect_workbook`)

| Parameter | Type | Description |
|---|---|---|
| `sheet` | string | Optional sheet name (case-insensitive). Inspects all sheets when empty. |
| `output_format` | string | `markdown` (default) or `json`. |

## Response format (to the model)

Markdown (or JSON) with one section per sheet: used range, cell type counts, header row best guess, a column profile table, sample rows with row numbers, formula examples with cached values, and data quality notes. The report ends with usage rules: use only the returned names, do not extrapolate beyond sampled rows, and end the final answer with an Evidence block citing ranges.

Failures are reported per file (`FAILED (...)`) instead of raising: `.xls` re-save guidance, oversize/zip-bomb rejections, password-protected or corrupted workbooks, timeouts (suggest narrowing with `sheet`).

## Limitations

- `.xls` (legacy binary) is not supported; the tool asks for an `.xlsx` re-save.
- Formulas show Excel's cached value; a missing cached value means unknown.
- Hidden sheets are inspected and marked `hidden`; hidden rows/columns are not detected (read-only mode).
- Row/column scan caps mean statistics cover the scanned region only (noted as `scan truncated`).
- On timeout the tool returns promptly but the worker thread finishes in the background.

## Related pieces (E3)

- `skills/excel-analysis.md` — when and how to call `inspect_workbook`, and the Evidence block rule.
- `functions/filter/excel-evidence-guard.py` — outlet filter appending a warning to Excel-related answers without cell references. It detects the Excel context from `inspect_workbook` function calls or Excel citations in the conversation, and never rewrites the answer itself.
