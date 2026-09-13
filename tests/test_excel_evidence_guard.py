"""Regression tests for the Excel Evidence Guard outlet filter."""

import asyncio
import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "functions"
    / "filter"
    / "excel-evidence-guard.py"
)
spec = importlib.util.spec_from_file_location("excel_evidence_guard", MODULE_PATH)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

INSPECTOR_OUTPUT = [
    {"type": "message", "content": [{"type": "text", "text": "let me inspect"}]},
    {
        "type": "function_call",
        "name": "inspect_workbook",
        "call_id": "c1",
        "arguments": "{}",
    },
    {"type": "function_call_output", "call_id": "c1", "output": "ok"},
    {"type": "message", "content": [{"type": "text", "text": "The total is 430."}]},
]


def _body(content="The total is 430.", output=None, sources=None):
    assistant = {"id": "m2", "role": "assistant", "content": content}
    if output is not None:
        assistant["output"] = output
    if sources is not None:
        assistant["sources"] = sources
    return {
        "id": "m2",
        "messages": [
            {"id": "m1", "role": "user", "content": "sum the sheet"},
            assistant,
        ],
    }


class GuardTests(unittest.TestCase):
    def _outlet(self, body):
        return asyncio.run(guard.Filter().outlet(body))

    def test_appends_warning_when_inspector_used_without_refs(self):
        body = self._outlet(_body(output=INSPECTOR_OUTPUT))
        content = body["messages"][1]["content"]
        self.assertIn("The total is 430.", content)
        self.assertIn("⚠️", content)
        self.assertIn("excel_inspector", content)

    def test_no_warning_when_cell_refs_present(self):
        body = self._outlet(
            _body(content="Total is 430 (Data!D3:D5).", output=INSPECTOR_OUTPUT)
        )
        self.assertEqual(body["messages"][1]["content"], "Total is 430 (Data!D3:D5).")

    def test_bare_range_counts_as_reference(self):
        body = self._outlet(
            _body(content="Total is 430 for B2:F20.", output=INSPECTOR_OUTPUT)
        )
        self.assertNotIn("⚠️", body["messages"][1]["content"])

    def test_quoted_sheet_reference_counts(self):
        body = self._outlet(
            _body(content="See 'Q1 Data'!A1:B1.", output=INSPECTOR_OUTPUT)
        )
        self.assertNotIn("⚠️", body["messages"][1]["content"])

    def test_no_excel_context_untouched(self):
        body = self._outlet(_body())
        self.assertEqual(body["messages"][1]["content"], "The total is 430.")

    def test_excel_sources_trigger_warning(self):
        sources = [
            {
                "source": {"id": "x", "name": "sales.xlsx Data!B2:F5", "type": "file"},
                "document": ["..."],
                "metadata": [
                    {"source": "sales.xlsx Data!B2:F5", "name": "sales.xlsx Data!B2:F5"}
                ],
            }
        ]
        body = self._outlet(_body(sources=sources))
        self.assertIn("⚠️", body["messages"][1]["content"])

    def test_xlsx_filename_in_function_arguments_triggers(self):
        output = [
            {
                "type": "function_call",
                "name": "inspect_workbook",
                "arguments": '{"sheet": "Data"}',
            },
        ]
        body = self._outlet(_body(output=output))
        self.assertIn("⚠️", body["messages"][1]["content"])

    def test_disabled_valve_untouched(self):
        flt = guard.Filter()
        flt.valves.enabled = False
        body = asyncio.run(flt.outlet(_body(output=INSPECTOR_OUTPUT)))
        self.assertEqual(body["messages"][1]["content"], "The total is 430.")

    def test_empty_assistant_content_untouched(self):
        body = self._outlet(_body(content="", output=INSPECTOR_OUTPUT))
        self.assertEqual(body["messages"][1]["content"], "")

    def test_content_list_gets_warning_appended(self):
        content = [{"type": "text", "text": "The total is 430."}]
        body = self._outlet(_body(content=content, output=INSPECTOR_OUTPUT))
        self.assertEqual(len(body["messages"][1]["content"]), 2)
        self.assertIn("⚠️", body["messages"][1]["content"][1]["text"])

    def test_targets_message_matching_body_id(self):
        body = _body(output=INSPECTOR_OUTPUT)
        body["id"] = "m9"
        body["messages"].append(
            {"id": "m9", "role": "assistant", "content": "Newer draft."}
        )
        result = self._outlet(body)
        self.assertEqual(result["messages"][1]["content"], "The total is 430.")
        self.assertIn("⚠️", result["messages"][2]["content"])


if __name__ == "__main__":
    unittest.main()
