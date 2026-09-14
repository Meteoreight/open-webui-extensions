"""Regression tests for file translation without an Open WebUI server."""

import asyncio
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pymupdf
from lxml import etree
from pydantic import ValidationError

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "file-translator.py"
spec = importlib.util.spec_from_file_location("file_translator", MODULE_PATH)
translator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(translator)


class TranslationTests(unittest.TestCase):
    def test_model_uses_shared_chat_route(self):
        shared_chat = types.ModuleType("open_webui.utils.chat")
        shared_chat.generate_chat_completion = AsyncMock(
            return_value={"choices": [{"message": {"content": '{"0":"Hello"}'}}]}
        )
        modules = {
            "open_webui": types.ModuleType("open_webui"),
            "open_webui.utils": types.ModuleType("open_webui.utils"),
            "open_webui.utils.chat": shared_chat,
        }
        with patch.dict(sys.modules, modules):
            result = asyncio.run(
                translator.Tools()._call_model(
                    None, None, "worker", [{"role": "user", "content": "{}"}]
                )
            )
        self.assertEqual(result, '{"0":"Hello"}')
        form_data = shared_chat.generate_chat_completion.await_args.kwargs["form_data"]
        self.assertEqual(form_data["temperature"], 1.0)
        self.assertEqual(form_data["reasoning_effort"], "low")

    def test_empty_reasoning_effort_is_omitted(self):
        shared_chat = types.ModuleType("open_webui.utils.chat")
        shared_chat.generate_chat_completion = AsyncMock(
            return_value={"choices": [{"message": {"content": '{"0":"Hello"}'}}]}
        )
        modules = {
            "open_webui": types.ModuleType("open_webui"),
            "open_webui.utils": types.ModuleType("open_webui.utils"),
            "open_webui.utils.chat": shared_chat,
        }
        tool = translator.Tools()
        tool.valves.reasoning_effort = ""
        with patch.dict(sys.modules, modules):
            asyncio.run(
                tool._call_model(
                    None, None, "worker", [{"role": "user", "content": "{}"}]
                )
            )
        self.assertNotIn(
            "reasoning_effort",
            shared_chat.generate_chat_completion.await_args.kwargs["form_data"],
        )

    def test_model_retry_requests_only_missing_translations(self):
        tool = translator.Tools()
        tool._call_model = AsyncMock(
            side_effect=[
                json.dumps({"0": "Hello"}),
                json.dumps({"1": "World"}),
            ]
        )
        translated = {}
        untranslated = asyncio.run(
            tool._translate_chunks(
                None,
                None,
                "English",
                "",
                {},
                [(0, 0, "原文A"), (1, 0, "原文B")],
                [[0, 1]],
                None,
                "test.docx",
                translated,
            )
        )
        self.assertEqual(tool._call_model.await_count, 2)
        self.assertEqual(translated, {(0, 0): "Hello", (1, 0): "World"})
        self.assertEqual(untranslated, 0)
        second_payload = tool._call_model.await_args.args[3][-1]["content"]
        self.assertEqual(json.loads(second_payload), {"1": "原文B"})

    def test_empty_json_is_retried_and_counted(self):
        tool = translator.Tools()
        tool._call_model = AsyncMock(return_value="{}")
        translated = {}
        untranslated = asyncio.run(
            tool._translate_chunks(
                None,
                None,
                "English",
                "",
                {},
                [(0, 0, "原文")],
                [[0]],
                None,
                "test.docx",
                translated,
            )
        )
        self.assertEqual(tool._call_model.await_count, 3)
        self.assertEqual(untranslated, 1)
        self.assertEqual(translated, {})

    def test_invalid_json_without_exception_is_retried(self):
        tool = translator.Tools()
        tool._call_model = AsyncMock(return_value="not json at all")
        translated = {}
        with patch.object(translator.asyncio, "sleep", new=AsyncMock()):
            untranslated = asyncio.run(
                tool._translate_chunks(
                    None,
                    None,
                    "English",
                    "",
                    {},
                    [(0, 0, "原文")],
                    [[0]],
                    None,
                    "test.docx",
                    translated,
                )
            )
        self.assertEqual(tool._call_model.await_count, 3)
        self.assertEqual(untranslated, 1)
        self.assertEqual(translated, {})

    def test_rate_limited_with_retry_after_header_waits_then_retries(self):
        class HTTPError(Exception):
            def __init__(self, status_code, headers):
                super().__init__(f"HTTP {status_code}")
                self.status_code = status_code
                self.headers = headers

        tool = translator.Tools()
        tool._call_model = AsyncMock(
            side_effect=[
                HTTPError(429, {"Retry-After": "3"}),
                json.dumps({"0": "Hello"}),
            ]
        )
        translated = {}
        sleep_mock = AsyncMock()
        with patch.object(translator.asyncio, "sleep", new=sleep_mock):
            untranslated = asyncio.run(
                tool._translate_chunks(
                    None,
                    None,
                    "English",
                    "",
                    {},
                    [(0, 0, "原文")],
                    [[0]],
                    None,
                    "test.docx",
                    translated,
                )
            )
        self.assertEqual(tool._call_model.await_count, 2)
        self.assertEqual(translated, {(0, 0): "Hello"})
        self.assertEqual(untranslated, 0)
        self.assertEqual([call.args[0] for call in sleep_mock.await_args_list], [3.0])

    def test_rate_limited_without_header_uses_default_backoff(self):
        class HTTPError(Exception):
            def __init__(self, status_code):
                super().__init__(f"HTTP {status_code} rate limit exceeded")
                self.status_code = status_code
                self.headers = {}

        tool = translator.Tools()
        tool._call_model = AsyncMock(side_effect=HTTPError(429))
        translated = {}
        sleep_mock = AsyncMock()
        with patch.object(translator.asyncio, "sleep", new=sleep_mock):
            untranslated = asyncio.run(
                tool._translate_chunks(
                    None,
                    None,
                    "English",
                    "",
                    {},
                    [(0, 0, "原文")],
                    [[0]],
                    None,
                    "test.docx",
                    translated,
                )
            )
        self.assertEqual(tool._call_model.await_count, 3)
        self.assertEqual(untranslated, 1)
        self.assertEqual(
            [call.args[0] for call in sleep_mock.await_args_list], [15, 30]
        )

    def test_non_rate_limit_error_uses_exponential_backoff(self):
        class Timeout(Exception):
            pass

        tool = translator.Tools()
        tool._call_model = AsyncMock(side_effect=Timeout("boom"))
        translated = {}
        sleep_mock = AsyncMock()
        with patch.object(translator.asyncio, "sleep", new=sleep_mock):
            untranslated = asyncio.run(
                tool._translate_chunks(
                    None,
                    None,
                    "English",
                    "",
                    {},
                    [(0, 0, "原文")],
                    [[0]],
                    None,
                    "test.docx",
                    translated,
                )
            )
        self.assertEqual(tool._call_model.await_count, 3)
        self.assertEqual(untranslated, 1)
        self.assertEqual([call.args[0] for call in sleep_mock.await_args_list], [1, 2])

    def test_docx_breaks_remain_between_translated_segments(self):
        root = etree.fromstring(
            f'<w:p xmlns:w="{translator.NS_W[1:-1]}">'
            "<w:r><w:t>Hello</w:t><w:br/><w:t>world</w:t>"
            "<w:tab/><w:t>again</w:t></w:r></w:p>"
        )
        segments = translator._ooxml_paragraph_segments(
            root, translator.NS_W + "p", translator.NS_W + "t"
        )
        self.assertEqual([text for text, _ in segments], ["Hello", "world", "again"])
        for (_, write), value in zip(segments, ["Bonjour", "monde", "encore"]):
            write(value)
        self.assertEqual(
            [(node.tag, node.text) for node in root.iter() if node is not root],
            [
                (translator.NS_W + "r", None),
                (translator.NS_W + "t", "Bonjour"),
                (translator.NS_W + "br", None),
                (translator.NS_W + "t", "monde"),
                (translator.NS_W + "tab", None),
                (translator.NS_W + "t", "encore"),
            ],
        )

    def test_pdf_keeps_original_when_translation_cannot_fit(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello", fontsize=11)
        parsed = translator.parse_pdf(doc.tobytes(), "English")
        parsed.segments[0][1]("Long translation " * 1000)
        output = pymupdf.open(stream=parsed.rebuild(), filetype="pdf")
        self.assertEqual(output[0].get_text().strip(), "Hello")
        self.assertEqual(len(parsed.warnings), 1)

    def test_pdf_replaces_text_when_translation_fits(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello", fontsize=11)
        parsed = translator.parse_pdf(doc.tobytes(), "English")
        parsed.segments[0][1]("Bonjour")
        output = pymupdf.open(stream=parsed.rebuild(), filetype="pdf")
        self.assertEqual(output[0].get_text().strip(), "Bonjour")
        self.assertFalse(parsed.warnings)

    def test_pdf_replaces_text_with_japanese_language_name(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello world", fontsize=11)
        parsed = translator.parse_pdf(doc.tobytes(), "Japanese")
        parsed.segments[0][1]("こんにちは世界")
        output = pymupdf.open(stream=parsed.rebuild(), filetype="pdf")
        self.assertEqual(output[0].get_text().strip(), "こんにちは世界")
        self.assertFalse(parsed.warnings)

    def test_pdf_body_text_uses_consistent_size(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello world and friends", fontsize=11)
        page.insert_text((72, 108), "Another sentence here", fontsize=11)
        parsed = translator.parse_pdf(doc.tobytes(), "Japanese")
        parsed.segments[0][1]("こんにちは")
        parsed.segments[1][1]("世界")
        output = pymupdf.open(stream=parsed.rebuild(), filetype="pdf")
        spans = [
            span
            for block in output[0].get_text("dict")["blocks"]
            if block["type"] == 0
            for line in block["lines"]
            for span in line["spans"]
        ]
        self.assertEqual([span["text"] for span in spans], ["こんにちは", "世界"])
        self.assertEqual([span["size"] for span in spans], [9.0, 9.0])
        self.assertFalse(parsed.warnings)

    def test_inline_glossary_keeps_first_language_name(self):
        self.assertEqual(
            translator._parse_line_glossary("English=英語\nCat=猫"),
            {"English": "英語", "Cat": "猫"},
        )

    def test_valve_bounds_and_temperature_default(self):
        self.assertEqual(translator.Tools.Valves().temperature, 1.0)
        self.assertEqual(translator.Tools.Valves().max_parallel_translations, 1)
        with self.assertRaises(ValidationError):
            translator.Tools.Valves(chunk_char_limit=0)

    def test_reasoning_effort_default_and_validation(self):
        self.assertEqual(translator.Tools.Valves().reasoning_effort, "low")
        self.assertEqual(
            translator.Tools.Valves(reasoning_effort=" Minimal ").reasoning_effort,
            " Minimal ",
        )
        self.assertEqual(
            translator.Tools.Valves(reasoning_effort="").reasoning_effort, ""
        )
        with self.assertRaises(ValidationError):
            translator.Tools.Valves(reasoning_effort="extreme")


if __name__ == "__main__":
    unittest.main()
