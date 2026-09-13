---
name: file-translation
description: Use when the user asks to translate an attached document (docx, xlsx, pptx or pdf) into another language. Triggers the file_translator tool and keeps the document structure where possible.
---

# File Translation

Translate attached docx / xlsx / pptx / pdf files by calling the `translate_file` tool. The tool edits text in the original document structure and attaches translated copies to the message. Do not translate the document contents in chat. Formatting within a paragraph and PDF layout may change.

## Instructions

1. **Check preconditions.** The user must have attached at least one docx / xlsx / pptx / pdf file and said which language to translate into. If no supported file is attached, ask the user to attach one first. If the target language is unclear, ask before calling.
2. **Call the tool** `translate_file` with:
   - `target_language`: the language the user asked for (e.g. `Japanese`, `en`). This is required unless the user has a `default_target_language` configured in their UserValves.
   - `glossary` (optional): inline terminology, one `source=target` pair per line. Build this from terms the user has specified in the conversation.
   - `glossary_file` (optional): the name of an attached glossary file (csv / tsv / xlsx / txt / md; column 1 = source term, column 2 = target). Pass this when the user attached a term list and mentions it, e.g. "translate using terms.csv".
   - `source_language` (optional): only when the user explicitly names the source language.
3. **Multiple files.** The tool translates every supported attached file in one call. Do not call it once per file.
4. **Call the tool exactly once per user request.** If the result reports untranslated pieces or PDF blocks that did not fit, report those numbers to the user and ask what to do; do not automatically call the tool again (a retry doubles time and quota usage). Only re-run when the user explicitly asks for it.
5. **Report the result.** After the tool returns, briefly summarize which files were translated, into which language, and whether a glossary was applied. Mention any failed files, untranslated pieces, PDF blocks that could not fit, or glossary warnings. Tell the user to download the attached files only if the tool reports successful attachments. Do not paste translated document text into the chat unless asked.

## Glossary handling

- If the user mentions fixed terminology (product names, brand terms, technical terms), collect them and pass `glossary` inline, e.g. `Neural Engine=ニューラルエンジン`.
- If the user attached a glossary file but did not name it, ask for the file name (or list it) before calling.
- Users can also store a permanent glossary in their UserValves; the tool merges it automatically with precedence: inline `glossary` > `glossary_file` > UserValves > admin Valves.

## Examples

### Example 1

User: "Translate this report.docx into Japanese." (report.docx attached)
Action: call `translate_file` with `target_language="Japanese"`. Then summarize and point to the attached `report_japanese.docx`.

### Example 2

User: "この仕様書.xlsxを英語に訳して。用語集terms.xlsxも参照して。" (spec.xlsx, terms.xlsx attached)
Action: call `translate_file` with `target_language="English"`, `glossary_file="terms.xlsx"`.

### Example 3

User: "Can you translate the attached slides to French?" (no file attached)
Action: ask the user to attach the pptx first; do not call the tool yet.

## Notes

- Progress status ("Parsing...", "Translating chunks 3/12", ...) is shown to the user automatically while the tool runs.
- PDF translation fits text into the original blocks with a consistent body-text size and compact line spacing. Blocks that would require unreadably small text stay in the source language and are reported.
- Excel formulas, numbers and dates are never translated; only text cells are.
- If the tool reports that `translation_model` is not configured, tell the user an admin must set the model id in the tool's Valves.
