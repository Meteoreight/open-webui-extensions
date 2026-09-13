"""Regression tests for the Excel Inspector tool without an Open WebUI server."""

import asyncio
import importlib.util
import io
import json
import re
import sys
import tempfile
import types
import unittest
import zipfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import openpyxl

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "excel_inspector.py"
spec = importlib.util.spec_from_file_location("excel_inspector", MODULE_PATH)
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


def _build_workbook() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws["A1"] = "Sales Report 2026"
    ws.merge_cells("A1:F1")
    for col, header in enumerate(["Date", "Dept", "Amount", "ID", "Note"], start=2):
        ws.cell(row=2, column=col, value=header)
    rows = [
        [date(2026, 1, 5), "Alpha", 100, "A-1", "ok"],
        [date(2026, 2, 5), "Beta", 250, "A-2", 7],
        [date(2026, 3, 5), "Alpha", 80, "A-1", None],
    ]
    for row_idx, row in enumerate(rows, start=3):
        for col, value in enumerate(row, start=2):
            ws.cell(row=row_idx, column=col, value=value)
    ws["G2"] = "Total"
    ws["G3"] = "=SUM(C3:C5)"
    q1 = wb.create_sheet("Q1 Data")
    q1["A1"] = "x"
    q1["B1"] = 1
    hidden = wb.create_sheet("Hidden")
    hidden.sheet_state = "hidden"
    hidden["A1"] = 42
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _patch_cached_value(data: bytes, coord: str, value: str) -> bytes:
    """Insert a cached <v> under a formula cell, like real Excel writes."""
    pattern = re.compile(rb'(<c r="' + coord.encode() + rb'"[^>]*>)(<f>[^<]*</f>)')
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(data)) as zin,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout,
    ):
        for item in zin.infolist():
            payload = zin.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                payload, count = pattern.subn(
                    rb"\g<1>\g<2><v>" + value.encode() + rb"</v>", payload
                )
                assert count == 1, "formula cell not found for caching"
            zout.writestr(item, payload)
    return out.getvalue()


def _fake_open_webui(path: str, size: int | None = None) -> dict:
    model = SimpleNamespace(meta={"size": size} if size is not None else {}, path=path)
    files_mod = types.ModuleType("open_webui.models.files")
    files_mod.Files = SimpleNamespace(get_file_by_id=lambda file_id: model)
    storage_mod = types.ModuleType("open_webui.storage.provider")
    storage_mod.Storage = SimpleNamespace(get_file=lambda p: p)
    return {
        "open_webui": types.ModuleType("open_webui"),
        "open_webui.models": types.ModuleType("open_webui.models"),
        "open_webui.models.files": files_mod,
        "open_webui.storage": types.ModuleType("open_webui.storage"),
        "open_webui.storage.provider": storage_mod,
    }


def _run(tool, **kwargs):
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "sales.xlsx")
        Path(path).write_bytes(kwargs.pop("data", None) or _build_workbook())
        modules = _fake_open_webui(path, kwargs.pop("declared_size", None))
        with patch.dict(sys.modules, modules):
            return asyncio.run(
                tool.inspect_workbook(
                    __files__=[{"type": "file", "id": "f1", "name": "sales.xlsx"}],
                    **kwargs,
                )
            )


class InspectorTests(unittest.TestCase):
    def test_report_contains_structure(self):
        result = _run(inspector.Tools())
        self.assertIn("Workbook: sales.xlsx (3 sheet(s))", result)
        self.assertIn('Sheet "Data" — used range A1:G5', result)
        self.assertIn("Header row (best guess): row 2", result)
        self.assertIn("2026-01-05", result)
        self.assertIn("Merged ranges: 1", result)
        self.assertIn('Sheet "Hidden" — used range A1:A1, hidden', result)
        self.assertIn("=SUM(C3:C5)", result)
        self.assertIn("no cached value", result)
        self.assertIn("Evidence block", result)

    def test_column_profile_counts(self):
        result = _run(inspector.Tools())
        # Dept column: 3 values, 2 distinct, 1 repeated
        self.assertRegex(result, r"\| C \| Dept \| string 3 \| 0 \| 2 \| 1 \|")
        # Amount numeric range
        self.assertRegex(
            result, r"\| D \| Amount \| number 3 \| 0 \| 3 \| 0 \| 80 … 250 \|"
        )
        self.assertIn("Column F (Note): mixed types", result)

    def test_cached_value_read_from_second_pass(self):
        data = _patch_cached_value(_build_workbook(), "G3", "430")
        result = _run(inspector.Tools(), data=data)
        self.assertIn("G3 = `=SUM(C3:C5)` → cached: 430", result)

    def test_citation_events_emitted(self):
        from unittest.mock import AsyncMock

        emitter = AsyncMock()
        data = _patch_cached_value(_build_workbook(), "G3", "430")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "sales.xlsx")
            Path(path).write_bytes(data)
            with patch.dict(sys.modules, _fake_open_webui(path)):
                asyncio.run(
                    inspector.Tools().inspect_workbook(
                        __files__=[{"type": "file", "id": "f1", "name": "sales.xlsx"}],
                        __event_emitter__=emitter,
                    )
                )
        events = [call.args[0] for call in emitter.await_args_list]
        citations = [e for e in events if e.get("type") == "citation"]
        self.assertEqual(len(citations), 3)
        data_citation = citations[0]["data"]
        self.assertEqual(data_citation["source"]["name"], "sales.xlsx Data!A1:G5")
        self.assertIn("Headers: A, Date, Dept", data_citation["document"][0])
        self.assertNotIn(
            "type", data_citation
        )  # socket handler ignores data with a type key

    def test_json_output(self):
        result = _run(inspector.Tools(), output_format="json")
        parsed = json.loads(result)
        self.assertEqual(len(parsed["workbooks"]), 1)
        sheets = parsed["workbooks"][0]["sheets"]
        self.assertEqual([s["name"] for s in sheets], ["Data", "Q1 Data", "Hidden"])
        self.assertEqual(sheets[0]["formulas"]["examples"][0]["cached"], None)

    def test_sheet_filter_matches_case_insensitive(self):
        result = _run(inspector.Tools(), sheet="q1 data")
        self.assertIn('Sheet "Q1 Data"', result)
        self.assertNotIn('Sheet "Data" —', result)

    def test_sheet_not_found_lists_sheets(self):
        result = _run(inspector.Tools(), sheet="nope")
        self.assertIn(
            "Requested sheet not found. Available sheets: Data, Q1 Data, Hidden", result
        )

    def test_legacy_xls_rejected(self):
        async def call():
            return await inspector.Tools().inspect_workbook(
                __files__=[{"type": "file", "id": "f1", "name": "old.xls"}]
            )

        result = asyncio.run(call())
        self.assertIn("Legacy .xls format is not supported", result)
        self.assertIn("re-save the file as .xlsx", result)

    def test_no_excel_attached_message(self):
        async def call():
            return await inspector.Tools().inspect_workbook(__files__=[])

        self.assertIn("No Excel files attached", asyncio.run(call()))

    def test_declared_size_rejects_before_read(self):
        tool = inspector.Tools()
        tool.valves.max_file_mb = 1
        result = _run(tool, declared_size=2 * 1024 * 1024)
        self.assertIn("FAILED (file is 2.0 MB, above the 1 MB limit)", result)

    def test_zip_expansion_guard(self):
        data = _build_workbook()
        padded = io.BytesIO()
        with (
            zipfile.ZipFile(io.BytesIO(data)) as zin,
            zipfile.ZipFile(padded, "w", zipfile.ZIP_DEFLATED) as zout,
        ):
            for item in zin.infolist():
                zout.writestr(item, zin.read(item.filename))
            zout.writestr("xl/pad.bin", b"\0" * (2 * 1024 * 1024))
        tool = inspector.Tools()
        tool.valves.max_total_uncompressed_mb = 1
        result = _run(tool, data=padded.getvalue())
        self.assertIn("expanded content exceeds the 1 MB safety limit", result)

    def test_scan_truncation_note(self):
        tool = inspector.Tools()
        tool.valves.max_rows_scanned = 2
        result = _run(tool)
        self.assertIn("Scan truncated at 2 rows", result)

    def test_quoted_sheet_reference_in_citation(self):
        from unittest.mock import AsyncMock

        emitter = AsyncMock()
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "sales.xlsx")
            Path(path).write_bytes(_build_workbook())
            with patch.dict(sys.modules, _fake_open_webui(path)):
                asyncio.run(
                    inspector.Tools().inspect_workbook(
                        __files__=[{"type": "file", "id": "f1", "name": "sales.xlsx"}],
                        __event_emitter__=emitter,
                    )
                )
        events = [call.args[0] for call in emitter.await_args_list]
        names = [
            e["data"]["source"]["name"] for e in events if e.get("type") == "citation"
        ]
        self.assertIn("sales.xlsx 'Q1 Data'!A1:B1", names)


if __name__ == "__main__":
    unittest.main()
