---
name: excel-analysis
description: Use when the user attaches an Excel file (xlsx/xlsm) and asks to analyze, summarize, aggregate, check or explain it. Runs the excel_inspector tool first, plans the analysis from the returned structure map, and answers with cell-range evidence.
---

# Excel Analysis

Analyze attached Excel workbooks (`.xlsx` / `.xlsm`) by calling the `inspect_workbook` tool first, then answer from the returned structure map. Never read Excel contents from the RAG context and never guess sheet names, headers or ranges.

## Instructions

1. **Check preconditions.** The user must have attached an xlsx/xlsm file. If the attachment is `.xls`, ask the user to re-save it as `.xlsx` first. If the analysis goal is unclear (what to measure, which sheet, what output form), ask before running anything.
2. **Always inspect first.** Call `inspect_workbook` before answering anything about an Excel file. Optional parameters:
   - `sheet`: a sheet name (case-insensitive) when the user named one; omit to inspect all sheets.
   - `output_format`: `"markdown"` (default) or `"json"`.
3. **Use only returned names.** Sheet names, header labels, column letters and ranges in the answer must come from the inspector output. Never invent or "correct" them.
4. **Compute only from shown values.** Aggregate and count from the sample rows and column statistics in the report. When a question needs totals beyond the sampled rows, say that a full-table aggregation is needed and state what is missing — do not extrapolate silently.
5. **Formulas are not recalculated.** The report shows the formula text and, when present, the value Excel cached at save time. A missing cached value means the value is unknown, not zero.
6. **End with an Evidence block.** The final answer must end with a list of the ranges used, e.g. `sales.xlsx Data!B2:F350`. Quote sheet names that contain spaces or symbols, e.g. `'Q1 Data'!A1:B1`.

## Workflow

1. Ask for the analysis goal if unknown: target sheet, aggregation axis (e.g. department, month), and desired output (table, bullet summary, number).
2. Call `inspect_workbook`.
3. Read the structure map: used ranges, header row, column profile (types, empty/distinct/repeated counts), sample rows, formulas, data quality notes.
4. If the needed sheet was not inspected (e.g. a hidden sheet or a second file), call `inspect_workbook` again with `sheet` set to that sheet name.
5. Build the answer from the report, then append the Evidence block.

## Examples

### Example 1

User: "部門別の売上上位を教えて" (sales.xlsx attached)
Action: call `inspect_workbook`, find the department and amount columns in the profile, compute the ranking from the reported values if within the sample, otherwise state the limitation. End with `Evidence: sales.xlsx Data!B2:F350`.

### Example 2

User: "このブックには何のシートがある？全体の構造を把握したい"
Action: call `inspect_workbook` (all sheets), summarize sheet names, used ranges, headers and data quality notes, and list the ranges.

### Example 3

User: "Sum column C for me" (no file attached)
Action: ask the user to attach the xlsx file first; do not call the tool.

## Notes

- Inspected ranges are emitted as citations and appear in the citation panel automatically.
- The Excel Evidence Guard filter adds a warning under answers that discuss an attached workbook but cite no cell ranges. Citing ranges in the Evidence block satisfies it.
- Progress status ("Inspecting sales.xlsx", ...) is shown automatically while the tool runs.
