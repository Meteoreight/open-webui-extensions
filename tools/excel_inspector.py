"""
title: Excel Inspector
author: Meteoreight
author_url: https://github.com/Meteoreight
git_url: https://github.com/Meteoreight/open-webui-extensions
description: Inspect attached xlsx/xlsm workbooks and return structure maps (sheets, used ranges, header rows, column profiles, sample rows, formulas with cached values, merged ranges, data quality notes) with Sheet!Range references for evidence-based answers
required_open_webui_version: 0.8.9
requirements: openpyxl
version: 0.1.0
licence: MIT
"""

import asyncio
import inspect
import io
import json
import logging
import os
import re
import zipfile
from collections import Counter
from collections.abc import Callable
from datetime import date, datetime, time
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

# Declare file handling so attached files are handed to this tool instead of
# being injected into the RAG context.
file_handler = True

SUPPORTED_EXTENSIONS = {".xlsx", ".xlsm"}

NS_X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_R = "{http://schemas.openxmlformats.org/package/2006/relationships}"
RID_ATTR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

_PLAIN_SHEET_NAME = re.compile(r"[A-Za-z0-9_]+\Z")


def _sheet_ref(sheet: str, cell_range: str) -> str:
    """Excel-style sheet-qualified reference, quoting names when required."""
    if _PLAIN_SHEET_NAME.match(sheet):
        return f"{sheet}!{cell_range}"
    return f"'{sheet}'!{cell_range}"


def _type_label(value, data_type: str) -> str:
    if value is None:
        return "empty"
    if data_type == "f":
        return "formula"
    if data_type == "e":
        return "error"
    if isinstance(value, str) and not value.strip():
        return "empty"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, (datetime, date, time)):
        return "datetime"
    if isinstance(value, str):
        return "string"
    return "other"


def _fmt_cell(value, limit: int = 40) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime) and (value.hour, value.minute, value.second) == (
        0,
        0,
        0,
    ):
        value = value.date()
    text = str(value)
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text.replace("|", "\\|").replace("\n", " ")


def _zip_uncompressed_size(data: bytes) -> int:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return sum(item.file_size for item in zf.infolist())


def _sheet_part_paths(data: bytes) -> dict[str, str]:
    """Map sheet names to worksheet part paths via workbook.xml + rels."""
    from lxml import etree

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        if "xl/workbook.xml" not in names or "xl/_rels/workbook.xml.rels" not in names:
            return {}
        workbook = etree.fromstring(zf.read("xl/workbook.xml"))
        rels = etree.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {
        rel.get("Id"): rel.get("Target") for rel in rels.iter(NS_R + "Relationship")
    }

    mapping: dict[str, str] = {}
    for sheet in workbook.iter(NS_X + "sheet"):
        target = rel_targets.get(sheet.get(RID_ATTR))
        if not target:
            continue
        part = target.lstrip("/")
        if not part.startswith("xl/"):
            part = "xl/" + part
        part = part.replace("xl/xl/", "xl/")
        if part in names:
            mapping[sheet.get("name")] = part
    return mapping


def _count_merged_ranges(data: bytes, part_path: str) -> int:
    """Stream-count <mergeCell> elements without loading the sheet XML.

    The trailing space keeps the <mergeCells> container tag from matching.
    """
    needle = b"<mergeCell "
    count = 0
    tail = b""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        with zf.open(part_path) as stream:
            while True:
                chunk = stream.read(1 << 20)
                if not chunk:
                    break
                count += (tail + chunk).count(needle)
                tail = chunk[-len(needle) + 1 :]
    return count


def _detect_header(rows: list[tuple[int, dict]]) -> tuple[int | None, str]:
    """Best-guess header row among the first scanned rows.

    A header row has several non-empty cells, mostly strings, and is at least
    as wide as the widest row nearby. Data rows with numbers score lower.
    """
    first = rows[:15]
    if not first:
        return None, "none"
    stats = []
    for row_idx, cells in first:
        non_empty = len(cells)
        strings = sum(1 for _, label in cells.values() if label == "string")
        stats.append((row_idx, non_empty, strings))
    widest = max((n for _, n, _ in stats), default=0)
    for row_idx, non_empty, strings in stats:
        if non_empty >= 2 and strings >= non_empty * 0.6 and non_empty >= widest * 0.6:
            return row_idx, "high"
    return first[0][0], "low"


def _scan_sheet(ws, valves) -> dict:
    """Single streaming pass over a worksheet in read-only mode."""
    min_row = min_col = None
    max_row = max_col = None
    non_empty_cells = 0
    type_counts: Counter = Counter()
    formulas: list[tuple[str, str]] = []
    formula_total = 0
    rows: list[tuple[int, dict]] = []
    scan_truncated = False

    for row_idx, row in enumerate(ws.iter_rows(values_only=False), start=1):
        if row_idx > valves.max_rows_scanned:
            scan_truncated = True
            break
        cells: dict[int, tuple] = {}
        for cell in row:
            value = cell.value
            if value is None:
                continue  # EmptyCell has no coordinates; nothing to record
            col_idx = cell.column
            if col_idx > valves.max_columns:
                continue
            label = _type_label(value, cell.data_type)
            if label == "empty":
                continue
            cells[col_idx] = (value, label)
            type_counts[label] += 1
            non_empty_cells += 1
            min_row = row_idx if min_row is None else min_row
            max_row = row_idx
            min_col = col_idx if min_col is None else min(min_col, col_idx)
            max_col = col_idx if max_col is None else max(max_col, col_idx)
            if label == "formula":
                formula_total += 1
                if len(formulas) < valves.max_formulas_reported:
                    formulas.append((str(cell.coordinate), str(value)))
        if cells:
            rows.append((row_idx, cells))

    return {
        "rows": rows,
        "used_range": (
            f"{get_column_letter(min_col)}{min_row}:{get_column_letter(max_col)}{max_row}"
            if min_row is not None
            else ""
        ),
        "min_col": min_col,
        "max_col": max_col,
        "non_empty_cells": non_empty_cells,
        "type_counts": dict(type_counts),
        "formulas": formulas,
        "formula_total": formula_total,
        "scan_truncated": scan_truncated,
    }


def _collect_cached_values(
    data: bytes, sheet_name: str, formulas: list[tuple[str, str]], valves
) -> dict:
    """Read the values Excel cached for formula cells (data_only pass).

    Formulas are never recalculated; cells without a cached value (e.g. files
    written by openpyxl) stay absent from the result.
    """
    wanted = {coord for coord, _ in formulas}
    row_limit = min(
        max(int(re.sub(r"\D", "", coord) or 0) for coord in wanted),
        valves.max_rows_scanned,
    )
    cached: dict[str, object] = {}
    wb = load_workbook(
        io.BytesIO(data), read_only=True, data_only=True, keep_links=False
    )
    try:
        ws = wb[sheet_name]
        for row_idx, row in enumerate(ws.iter_rows(values_only=False), start=1):
            if not wanted or row_idx > row_limit:
                break
            for cell in row:
                if cell.value is None:
                    continue
                coord = str(cell.coordinate)
                if coord in wanted:
                    cached[coord] = cell.value
                    wanted.discard(coord)
    finally:
        wb.close()
    return cached


def _profile_columns(
    scan: dict, valves
) -> tuple[list[dict], int | None, str, list[str]]:
    rows = scan["rows"]
    header_row, confidence = _detect_header(rows)
    notes: list[str] = []
    if confidence == "low":
        notes.append(
            "No clear header row detected; the first non-empty row is used as a best guess."
        )
    if scan["scan_truncated"]:
        notes.append(
            f"Scan truncated at {valves.max_rows_scanned} rows; the used range covers the scanned part only."
        )

    data_rows = [
        (idx, cells) for idx, cells in rows if header_row is None or idx > header_row
    ]
    columns: list[dict] = []
    min_col, max_col = scan["min_col"], scan["max_col"]
    if min_col is None:
        return columns, header_row, confidence, notes

    header_cells: dict[int, tuple] = {}
    if header_row is not None:
        for idx, cells in rows:
            if idx == header_row:
                header_cells = cells
                break

    for col_idx in range(min_col, max_col + 1):
        letter = get_column_letter(col_idx)
        header_value = header_cells.get(col_idx, (None, ""))[0]
        header_label = _fmt_cell(header_value, 30) or letter
        values = [cells[col_idx] for _, cells in data_rows if col_idx in cells]
        labels = [label for _, label in values]
        counts = Counter(label for label in labels if label != "empty")
        non_empty = [
            value for value, label in values if label not in ("empty", "formula")
        ]
        distinct = len(set(non_empty))
        repeated = len(non_empty) - distinct
        numeric = [value for value, label in values if label == "number"]
        empty_count = len(data_rows) - len(values)
        entry = {
            "col": letter,
            "header": header_label,
            "types": ", ".join(
                f"{label} {count}" for label, count in counts.most_common(2)
            )
            or "empty",
            "empty": empty_count,
            "distinct": distinct,
            "repeated": repeated,
            "numeric_min": min(numeric) if len(numeric) >= 2 else None,
            "numeric_max": max(numeric) if len(numeric) >= 2 else None,
        }
        columns.append(entry)

        mixed = [
            label
            for label, count in counts.items()
            if count >= max(1, len(values) * 0.1)
        ]
        if len(mixed) >= 2:
            notes.append(
                f"Column {letter} ({header_label}): mixed types ({entry['types']})."
            )
        if data_rows and empty_count >= len(data_rows) * 0.5:
            notes.append(
                f"Column {letter} ({header_label}): {empty_count} of {len(data_rows)} rows empty."
            )

    return columns, header_row, confidence, notes


def _sample_rows(
    scan: dict, header_row: int | None, valves
) -> tuple[list[str], list[list[str]]]:
    """Sample data rows: (column letters, rows of formatted values with row number first)."""
    rows = scan["rows"]
    data_rows = [
        (idx, cells) for idx, cells in rows if header_row is None or idx > header_row
    ][: valves.sample_rows]
    if not data_rows:
        return [], []
    letters = [
        get_column_letter(col) for col in range(scan["min_col"], scan["max_col"] + 1)
    ]
    samples = []
    for row_idx, cells in data_rows:
        samples.append(
            [str(row_idx)]
            + [
                _fmt_cell(cells[col][0]) if col in cells else ""
                for col in range(scan["min_col"], scan["max_col"] + 1)
            ]
        )
    return letters, samples


def _inspect_bytes(data: bytes, filename: str, sheet_filter: str, valves) -> dict:
    """Full synchronous inspection of one workbook; runs in a worker thread."""
    merged_counts = {}
    for name, part in _sheet_part_paths(data).items():
        try:
            merged_counts[name] = _count_merged_ranges(data, part)
        except Exception:
            log.exception("Failed to count merged cells for %s in %s", name, filename)
            merged_counts[name] = -1

    wb = load_workbook(
        io.BytesIO(data), read_only=True, data_only=False, keep_links=False
    )
    sheets: list[dict] = []
    try:
        names = wb.sheetnames
        selected = (
            names
            if not sheet_filter
            else [name for name in names if name.lower() == sheet_filter]
        )
        for name in selected[: valves.max_sheets_per_file]:
            ws = wb[name]
            state = getattr(ws, "sheet_state", "visible") or "visible"
            try:
                scan = _scan_sheet(ws, valves)
            except Exception as exc:
                log.exception("Failed to scan sheet %s in %s", name, filename)
                sheets.append({"name": name, "state": state, "error": str(exc)})
                continue

            columns, header_row, confidence, notes = _profile_columns(scan, valves)
            sample_letters, samples = _sample_rows(scan, header_row, valves)
            formula_examples = []
            if scan["formulas"]:
                cached = _collect_cached_values(data, name, scan["formulas"], valves)
                for coord, formula in scan["formulas"]:
                    formula_examples.append(
                        {
                            "cell": coord,
                            "formula": formula[:60],
                            "cached": _fmt_cell(cached.get(coord), 30)
                            if coord in cached
                            else None,
                        }
                    )

            header_range = None
            if header_row is not None and scan["min_col"] is not None:
                header_range = (
                    f"{get_column_letter(scan['min_col'])}{header_row}:"
                    f"{get_column_letter(scan['max_col'])}{header_row}"
                )
            sheets.append(
                {
                    "name": name,
                    "state": state,
                    "used_range": scan["used_range"],
                    "non_empty_cells": scan["non_empty_cells"],
                    "rows_scanned": len(scan["rows"]),
                    "scan_truncated": scan["scan_truncated"],
                    "merged_ranges": merged_counts.get(name, 0),
                    "type_counts": scan["type_counts"],
                    "header": {
                        "row": header_row,
                        "range": header_range,
                        "confidence": confidence,
                    },
                    "columns": columns,
                    "sample_columns": sample_letters,
                    "sample_rows": samples,
                    "formulas": {
                        "total": scan["formula_total"],
                        "examples": formula_examples,
                    },
                    "notes": notes,
                }
            )
    finally:
        wb.close()

    report = {"file": filename, "sheets": sheets}
    if sheet_filter and not selected:
        report["sheet_not_found"] = names
    elif len(selected) > valves.max_sheets_per_file:
        report["sheets_truncated"] = len(selected) - valves.max_sheets_per_file
    return report


def _render_markdown(report: dict) -> str:
    lines = [f"# Workbook: {report['file']} ({len(report['sheets'])} sheet(s))"]
    if report.get("sheet_not_found") is not None:
        lines.append(
            "Requested sheet not found. Available sheets: "
            + ", ".join(report["sheet_not_found"])
        )
    if report.get("sheets_truncated"):
        lines.append(f"Only the first {len(report['sheets'])} sheet(s) were inspected.")
    for sheet in report["sheets"]:
        if "error" in sheet:
            lines.append(
                f'\n## Sheet "{sheet["name"]}" — could not be scanned ({sheet["error"]})'
            )
            continue
        state = f", {sheet['state']}" if sheet["state"] != "visible" else ""
        trunc = ", scan truncated" if sheet["scan_truncated"] else ""
        lines.append(
            f'\n## Sheet "{sheet["name"]}" — used range {sheet["used_range"] or "(empty)"}{state}{trunc}'
        )
        lines.append(
            f"Non-empty cells: {sheet['non_empty_cells']} | Merged ranges: {sheet['merged_ranges']} "
            f"| Types: {', '.join(f'{k} {v}' for k, v in sorted(sheet['type_counts'].items())) or 'none'}"
        )
        header = sheet["header"]
        if header["row"] is not None:
            lines.append(
                f"Header row (best guess): row {header['row']} ({header['range']}), "
                f"confidence: {header['confidence']}"
            )
        if sheet["columns"]:
            lines.append(
                "\n| Col | Header | Types | Empty | Distinct | Repeated | Numeric range |"
            )
            lines.append("|---|---|---|---|---|---|---|")
            for col in sheet["columns"]:
                numeric = (
                    f"{col['numeric_min']} … {col['numeric_max']}"
                    if col["numeric_min"] is not None
                    else "—"
                )
                lines.append(
                    f"| {col['col']} | {col['header']} | {col['types']} | {col['empty']} "
                    f"| {col['distinct']} | {col['repeated']} | {numeric} |"
                )
        if sheet["sample_rows"]:
            letters = sheet.get("sample_columns") or []
            lines.append("\nSample rows (first column is the row number):")
            lines.append("| # | " + " | ".join(letters) + " |")
            lines.append("|---|" + "---|" * max(1, len(letters)))
            for row in sheet["sample_rows"]:
                lines.append(f"| {row[0]} | " + " | ".join(row[1:]) + " |")
        formulas = sheet["formulas"]
        if formulas["total"]:
            shown = len(formulas["examples"])
            lines.append(
                f"\nFormulas: {formulas['total']} total (first {shown} shown, not recalculated)"
            )
            for item in formulas["examples"]:
                cached = (
                    f" → cached: {item['cached']}"
                    if item["cached"] is not None
                    else " → no cached value"
                )
                lines.append(f"- {item['cell']} = `{item['formula']}`{cached}")
        if sheet["notes"]:
            lines.append("\nData quality notes:")
            lines.extend(f"- {note}" for note in sheet["notes"])
    return "\n".join(lines)


def _sheet_citation(filename: str, sheet: dict) -> dict:
    ref = _sheet_ref(sheet["name"], sheet["used_range"] or "A1")
    headers = ", ".join(col["header"] for col in sheet["columns"][:8])
    first_row = " | ".join(sheet["sample_rows"][0][1:6]) if sheet["sample_rows"] else ""
    document = (
        f"{ref}: {sheet['non_empty_cells']} non-empty cells, "
        f"merged ranges: {sheet['merged_ranges']}. Headers: {headers}."
    )
    if first_row:
        document += f" First row: {first_row}."
    return {
        "source": {
            "id": f"excel:{filename}:{sheet['name']}",
            "name": f"{filename} {ref}",
            "type": "file",
        },
        "document": [document[:600]],
        "metadata": [{"source": f"{filename} {ref}", "name": f"{filename} {ref}"}],
    }


class Tools:
    def __init__(self):
        self.citation = False
        self.valves = self.Valves()

    class Valves(BaseModel):
        max_file_mb: int = Field(
            default=20,
            ge=1,
            description="Reject workbook files larger than this many megabytes",
        )
        max_total_uncompressed_mb: int = Field(
            default=200,
            ge=1,
            description="Reject workbooks whose expanded zip content exceeds this size (zip bomb guard)",
        )
        max_sheets_per_file: int = Field(
            default=20,
            ge=1,
            description="Maximum number of sheets inspected per workbook",
        )
        max_rows_scanned: int = Field(
            default=1000,
            ge=1,
            description="Maximum rows scanned per sheet for structure analysis",
        )
        max_columns: int = Field(
            default=150, ge=1, description="Maximum column index considered per sheet"
        )
        max_formulas_reported: int = Field(
            default=50,
            ge=1,
            description="Maximum formula cells listed with their cached values",
        )
        sample_rows: int = Field(
            default=5, ge=0, description="Number of sample data rows included per sheet"
        )
        timeout_seconds: int = Field(
            default=60,
            ge=1,
            description="Overall inspection timeout per workbook in seconds",
        )
        max_report_chars: int = Field(
            default=24000,
            ge=1000,
            description="Truncate the returned report at this length",
        )
        show_status: bool = Field(
            default=True, description="Show progress status messages in the UI"
        )
        emit_citations: bool = Field(
            default=True,
            description="Emit citation events so inspected ranges appear in the citation panel",
        )

    async def _emit(
        self, emitter, description: str, done: bool = False, status: str = "in_progress"
    ):
        if emitter and self.valves.show_status:
            await emitter(
                {
                    "type": "status",
                    "data": {
                        "description": description,
                        "status": status,
                        "done": done,
                    },
                }
            )

    async def _read_file_bytes(self, file_id: str) -> tuple[bytes | None, str | None]:
        """Read a stored file, rejecting known-oversized files before reading."""
        limit = self.valves.max_file_mb * 1024 * 1024
        try:
            from open_webui.models.files import Files
            from open_webui.storage.provider import Storage

            model = Files.get_file_by_id(file_id)
            if inspect.isawaitable(model):
                model = await model
            if model is None:
                return None, "file record not found"
            meta = getattr(model, "meta", None)
            size = meta.get("size") if isinstance(meta, dict) else None
            if isinstance(size, (int, float)) and size > limit:
                return None, (
                    f"file is {size / 1024 / 1024:.1f} MB, above the {self.valves.max_file_mb} MB limit"
                )
            path = Storage.get_file(model.path)
            return await asyncio.to_thread(Path(path).read_bytes), None
        except Exception:
            log.exception("Failed to read file %s from storage", file_id)
            return None, "file could not be read from storage"

    async def inspect_workbook(
        self,
        sheet: str = "",
        output_format: str = "markdown",
        __user__: dict | None = None,
        __files__: list | None = None,
        __event_emitter__: Callable | None = None,
    ) -> str:
        """
        Inspect attached Excel workbooks and return a structure map: sheets,
        used ranges, header rows, column profiles (types, empty/distinct/repeated
        counts), sample rows, formulas with cached values and data quality
        notes. Always call this before answering questions about an Excel file,
        and use the returned sheet names and ranges as evidence.

        :param sheet: Optional sheet name to inspect (case-insensitive). Inspects all sheets when empty.
        :param output_format: "markdown" (default) or "json".
        :param __user__: User context (injected by Open WebUI).
        :param __files__: Attached files (injected by Open WebUI).
        :param __event_emitter__: Event emitter for status updates and citations (injected by Open WebUI).
        :return: Structure report used as grounded context for analysis.
        """
        entries = [
            f
            for f in (__files__ or [])
            if isinstance(f, dict) and f.get("type", "file") == "file" and f.get("id")
        ]
        targets = [
            f
            for f in entries
            if os.path.splitext(f.get("name", ""))[1].lower() in SUPPORTED_EXTENSIONS
        ]
        if not targets:
            legacy = [
                f.get("name", "?")
                for f in entries
                if f.get("name", "").lower().endswith(".xls")
            ]
            if legacy:
                return (
                    "Legacy .xls format is not supported ("
                    + ", ".join(legacy)
                    + "). Ask the user to re-save the file as .xlsx and attach it again."
                )
            attached = ", ".join(f.get("name", "?") for f in entries) or "none"
            return f"No Excel files attached (attached files: {attached}). Ask the user to attach an xlsx or xlsm file."

        fmt = (output_format or "markdown").strip().lower()
        if fmt not in ("markdown", "json"):
            return "Invalid output_format; use 'markdown' or 'json'."

        reports: list[dict] = []
        problems: list[str] = []
        for entry in targets:
            name = entry.get("name", "file")
            await self._emit(__event_emitter__, f"Inspecting {name}")
            data, error = await self._read_file_bytes(entry.get("id"))
            if data is None:
                problems.append(f"- {name}: FAILED ({error})")
                continue
            if len(data) > self.valves.max_file_mb * 1024 * 1024:
                problems.append(
                    f"- {name}: FAILED (file is {len(data) / 1024 / 1024:.1f} MB, "
                    f"above the {self.valves.max_file_mb} MB limit)"
                )
                continue
            try:
                if (
                    _zip_uncompressed_size(data)
                    > self.valves.max_total_uncompressed_mb * 1024 * 1024
                ):
                    problems.append(
                        f"- {name}: FAILED (expanded content exceeds the "
                        f"{self.valves.max_total_uncompressed_mb} MB safety limit)"
                    )
                    continue
                report = await asyncio.wait_for(
                    asyncio.to_thread(
                        _inspect_bytes, data, name, (sheet or "").strip(), self.valves
                    ),
                    timeout=self.valves.timeout_seconds,
                )
            except TimeoutError:
                problems.append(
                    f"- {name}: FAILED (inspection timed out after {self.valves.timeout_seconds}s; "
                    "narrow it down with the sheet parameter)"
                )
                continue
            except Exception as exc:
                log.exception("Failed to inspect %s", name)
                problems.append(
                    f"- {name}: FAILED (workbook could not be opened; "
                    "it may be password-protected or corrupted)"
                    if "password" in str(exc).lower() or "decrypt" in str(exc).lower()
                    else f"- {name}: FAILED ({exc})"
                )
                continue
            reports.append(report)

            if self.valves.emit_citations and __event_emitter__:
                for sheet_report in report.get("sheets", []):
                    if "error" in sheet_report:
                        continue
                    try:
                        await __event_emitter__(
                            {
                                "type": "citation",
                                "data": _sheet_citation(name, sheet_report),
                            }
                        )
                    except Exception:
                        log.exception("Failed to emit citation for %s", name)
            await self._emit(__event_emitter__, f"{name}: inspection complete")

        if fmt == "json":
            body = json.dumps(
                {"workbooks": reports, "problems": problems},
                ensure_ascii=False,
                default=str,
            )
        else:
            sections = [_render_markdown(report) for report in reports]
            sections.append(
                "## How to use this report\n"
                "- Use these exact sheet names, header labels and ranges; do not guess them.\n"
                "- Aggregate only from the values shown here; say so when a full-table total is needed "
                "beyond the sampled rows.\n"
                "- End the final answer with an Evidence block citing ranges like `sales.xlsx Data!B2:F350`."
            )
            if problems:
                sections.append("## Problems\n" + "\n".join(problems))
            body = "\n\n".join(sections)

        if len(body) > self.valves.max_report_chars:
            body = body[: self.valves.max_report_chars] + "\n\n(report truncated)"
        await self._emit(
            __event_emitter__, "Inspection complete", done=True, status="complete"
        )
        return body
