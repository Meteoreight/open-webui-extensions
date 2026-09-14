"""
title: File Translator
author: Meteoreight
author_url: https://github.com/Meteoreight
git_url: https://github.com/Meteoreight/open-webui-extensions
description: Translate docx, xlsx, pptx and pdf files attached to chat into a target language while preserving document structure (tables, text boxes, charts, notes)
required_open_webui_version: 0.8.9
requirements: lxml, pymupdf
version: 0.1.4
licence: MIT
"""

import asyncio
import csv
import fnmatch
import inspect
import io
import json
import logging
import os
import re
import zipfile
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

# Declare file handling so attached files are handed to this tool instead of
# being injected into the RAG context.
file_handler = True

# XML namespaces
NS_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
NS_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
NS_C = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
NS_X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

TRANSLATABLE_EXTENSIONS = {".docx", ".xlsx", ".pptx", ".pdf"}
GLOSSARY_EXTENSIONS = {".csv", ".tsv", ".txt", ".md", ".xlsx"}

MIME_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".pdf": "application/pdf",
}

# Text that consists only of digits, whitespace and punctuation is not worth
# sending to the translation model.
_SKIP_TEXT_RE = re.compile(r"^[\W\d\s]+$", re.UNICODE)

# Sentence boundaries used when a single segment exceeds the chunk size limit.
_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?。！？…；;]+[\"'”’»）)\]]*\s*|\n+")

_CJK_LANGS = {
    "ja": "japan",
    "japanese": "japan",
    "zh": "china-s",
    "chinese": "china-s",
    "simplified chinese": "china-s",
    "traditional chinese": "china-t",
    "zh-cn": "china-s",
    "zh-tw": "china-t",
    "zh-hans": "china-s",
    "zh-hant": "china-t",
    "ko": "korea",
    "korean": "korea",
}

_PDF_LINE_HEIGHT = 1.1
_PDF_BODY_FONT_SIZE = 9.0
_PDF_MIN_BODY_FONT_SIZE = 6.5

_GLOSSARY_HEADER_WORDS = {
    "source",
    "original",
    "source term",
    "english",
    "en",
    "原語",
    "原文",
    "target",
    "translation",
    "translated",
    "target term",
    "訳語",
    "翻訳",
    "日本語",
    "ja",
    "japanese",
}


def _skippable(text: str) -> bool:
    """Return True when text carries nothing translatable."""
    stripped = text.strip()
    return not stripped or bool(_SKIP_TEXT_RE.match(stripped))


def _stem(name: str) -> str:
    return os.path.splitext(os.path.basename(name))[0]


def _safe_lang_code(language: str) -> str:
    """Reduce a language name/code to a short filename-safe token."""
    token = re.sub(r"[^0-9A-Za-z_-]+", "-", language.strip()).strip("-")
    return (token[:12] or "translated").lower()


def _nearest_ancestor(node, tag: str):
    parent = node.getparent()
    while parent is not None:
        if parent.tag == tag:
            return parent
        parent = parent.getparent()
    return None


def _inside_ancestor(node, *tags) -> bool:
    parent = node.getparent()
    while parent is not None:
        if parent.tag in tags:
            return True
        parent = parent.getparent()
    return False


def _make_first_node_writer(nodes):
    """Writer that puts the full translated text into the first text node and
    blanks the remaining ones, preserving paragraph/first-run formatting."""

    def apply(text: str) -> None:
        first = nodes[0]
        first.text = text
        if text != text.strip():
            first.set(XML_SPACE, "preserve")
        for node in nodes[1:]:
            node.text = ""

    return apply


def _make_node_writer(node):
    def apply(text: str) -> None:
        node.text = text

    return apply


class _ParsedDocument:
    """Extraction result: translatable segments plus write-back callbacks."""

    def __init__(
        self,
        segments: list[tuple[str, Callable[[str], None]]],
        rebuild: Callable[[], bytes],
        warnings: list[str] | None = None,
    ):
        self.segments = segments
        self.rebuild = rebuild
        self.warnings = warnings if warnings is not None else []


# ---------------------------------------------------------------------------
# OOXML (docx / pptx / xlsx) parsing via direct zip + XML editing
# ---------------------------------------------------------------------------


def _ooxml_paragraph_segments(
    root, p_tag: str, t_tag: str, exclude_field_tags: tuple = ()
):
    """Collect paragraph-level segments. The nearest-ancestor rule keeps text
    that belongs to nested structures (text boxes, groups, table cells) out of
    the enclosing paragraph."""
    segments = []
    boundary_tags = {NS_W + "br", NS_W + "cr", NS_W + "tab", NS_A + "br", NS_A + "tab"}
    for paragraph in root.iter(p_tag):
        nodes = []
        for node in paragraph.iter():
            if _nearest_ancestor(node, p_tag) is not paragraph:
                continue
            if exclude_field_tags and _inside_ancestor(node, *exclude_field_tags):
                continue
            if node.tag in boundary_tags:
                text = "".join(item.text or "" for item in nodes)
                if not _skippable(text):
                    segments.append((text, _make_first_node_writer(nodes)))
                nodes = []
            elif node.tag == t_tag:
                nodes.append(node)
        text = "".join(item.text or "" for item in nodes)
        if not _skippable(text):
            segments.append((text, _make_first_node_writer(nodes)))
    return segments


def _chart_segments(root):
    """Best-effort segments for chart/diagram parts: rich-text paragraphs plus
    cached category/series label values (c:v under c:pt)."""
    segments = _ooxml_paragraph_segments(root, NS_A + "p", NS_A + "t")
    for value in root.iter(NS_C + "v"):
        if not _inside_ancestor(value, NS_C + "pt"):
            continue
        text = value.text or ""
        if _skippable(text):
            continue
        segments.append((text, _make_node_writer(value)))
    return segments


def _shared_string_segments(root):
    """Segments for xl/sharedStrings.xml (Excel-written files). One si may
    hold formatting runs; phonetic runs (rPh) are preserved untouched."""
    segments = []
    for si in root.iter(NS_X + "si"):
        nodes = []
        for text_node in si.iter(NS_X + "t"):
            if _inside_ancestor(text_node, NS_X + "rPh"):
                continue
            nodes.append(text_node)
        text = "".join(node.text or "" for node in nodes)
        if _skippable(text):
            continue
        segments.append((text, _make_first_node_writer(nodes)))
    return segments


def _inline_string_segments(root):
    """Segments for inline strings (t="inlineStr" cells written by libraries
    such as openpyxl). Formulas and numeric cells are never touched."""
    segments = []
    for is_node in root.iter(NS_X + "is"):
        nodes = []
        for text_node in is_node.iter(NS_X + "t"):
            if _inside_ancestor(text_node, NS_X + "rPh"):
                continue
            nodes.append(text_node)
        text = "".join(node.text or "" for node in nodes)
        if _skippable(text):
            continue
        segments.append((text, _make_first_node_writer(nodes)))
    return segments


def _rebuild_zip(source: bytes, replacements: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(source)) as zin,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout,
    ):
        for item in zin.infolist():
            data = replacements.get(item.filename, zin.read(item.filename))
            zout.writestr(item, data)
    return out.getvalue()


def _parse_ooxml_package(
    data: bytes,
    text_part_patterns: list[str],
    chart_part_patterns: list[str],
    p_tag: str,
    t_tag: str,
    exclude_field_tags: tuple = (),
) -> _ParsedDocument:
    """Parse an OOXML package at zip level. Text-bearing parts (body, tables,
    text boxes, notes, headers/footers) are edited via paragraph runs; chart
    and diagram parts are handled best-effort. Untouched entries are copied
    byte-identically on rebuild."""
    from lxml import etree

    segments: list[tuple[str, Callable[[str], None]]] = []
    roots: dict[str, object] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            is_text = any(
                fnmatch.fnmatch(name, pattern) for pattern in text_part_patterns
            )
            is_chart = any(
                fnmatch.fnmatch(name, pattern) for pattern in chart_part_patterns
            )
            if not (is_text or is_chart):
                continue
            try:
                root = etree.fromstring(zf.read(name))
            except etree.XMLSyntaxError:
                log.warning("Skipping malformed XML part: %s", name)
                continue
            roots[name] = root
            if is_text:
                segments.extend(
                    _ooxml_paragraph_segments(root, p_tag, t_tag, exclude_field_tags)
                )
            else:
                segments.extend(_chart_segments(root))

    def rebuild() -> bytes:
        replacements = {
            name: etree.tostring(
                root, xml_declaration=True, encoding="UTF-8", standalone=True
            )
            for name, root in roots.items()
        }
        return _rebuild_zip(data, replacements)

    return _ParsedDocument(segments, rebuild)


def parse_docx(data: bytes) -> _ParsedDocument:
    return _parse_ooxml_package(
        data,
        [
            "word/document.xml",
            "word/header*.xml",
            "word/footer*.xml",
            "word/footnotes.xml",
            "word/endnotes.xml",
            "word/diagrams/drawing*.xml",
        ],
        ["word/charts/chart*.xml", "word/diagrams/data*.xml"],
        NS_W + "p",
        NS_W + "t",
    )


def parse_pptx(data: bytes) -> _ParsedDocument:
    return _parse_ooxml_package(
        data,
        ["ppt/slides/slide*.xml", "ppt/notesSlides/notesSlide*.xml"],
        ["ppt/charts/chart*.xml", "ppt/diagrams/data*.xml"],
        NS_A + "p",
        NS_A + "t",
        exclude_field_tags=(NS_A + "fld",),  # slide-number/date fields
    )


def parse_xlsx(data: bytes) -> _ParsedDocument:
    from lxml import etree

    segments: list[tuple[str, Callable[[str], None]]] = []
    roots: dict[str, object] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        if "xl/sharedStrings.xml" in names:
            root = etree.fromstring(zf.read("xl/sharedStrings.xml"))
            roots["xl/sharedStrings.xml"] = root
            segments.extend(_shared_string_segments(root))
        for name in names:
            if fnmatch.fnmatch(name, "xl/worksheets/sheet*.xml"):
                root = etree.fromstring(zf.read(name))
                part_segments = _inline_string_segments(root)
                if part_segments:
                    roots[name] = root
                    segments.extend(part_segments)

    def rebuild() -> bytes:
        replacements = {
            name: etree.tostring(
                root, xml_declaration=True, encoding="UTF-8", standalone=True
            )
            for name, root in roots.items()
        }
        return _rebuild_zip(data, replacements)

    return _ParsedDocument(segments, rebuild)


# ---------------------------------------------------------------------------
# PDF parsing (pymupdf): block-level redact + re-insert
# ---------------------------------------------------------------------------


def _import_pymupdf():
    try:
        import pymupdf

        return pymupdf
    except ImportError:
        try:
            import fitz as pymupdf

            return pymupdf
        except ImportError:
            return None


def _dominant(values: list) -> Any:
    """Most common value by occurrence count; falls back to the first."""
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


def _pdf_font_for(text: str, target_language: str) -> str:
    lang = (target_language or "").strip().lower()
    for prefix, font in _CJK_LANGS.items():
        if lang == prefix or lang.startswith(prefix + "-"):
            return font
    # Use an available wide-coverage built-in font for non-Latin text.
    # "cjk" is not a valid PyMuPDF font name for insert_textbox().
    if any(ord(ch) > 0x24F for ch in text):
        return "japan"
    return "helv"


def parse_pdf(data: bytes, target_language: str) -> _ParsedDocument:
    pymupdf = _import_pymupdf()
    if pymupdf is None:
        raise RuntimeError("pymupdf is not installed")

    doc = pymupdf.open(stream=data, filetype="pdf")
    page_blocks: list[tuple[object, list[dict]]] = []
    warnings: list[str] = []

    segments: list[tuple[str, Callable[[str], None]]] = []
    for page in doc:
        blocks = []
        try:
            raw = page.get_text("dict")
        except Exception:
            log.exception("Failed to extract text from a PDF page")
            continue
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            lines = block.get("lines", [])
            text = "\n".join(
                "".join(span.get("text", "") for span in line.get("spans", []))
                for line in lines
            )
            if _skippable(text):
                continue
            spans = [
                span
                for line in lines
                for span in line.get("spans", [])
                if span.get("text", "").strip()
            ]
            sizes = []
            colors = []
            for span in spans:
                weight = max(1, len(span.get("text", "")))
                sizes.extend([span.get("size", 11)] * weight)
                colors.extend([span.get("color", 0)] * weight)
            record = {
                "rect": pymupdf.Rect(block["bbox"]),
                "text": text,
                "translated": text,
                "size": _dominant(sizes) or 11.0,
                "color": _dominant(colors) or 0,
            }
            blocks.append(record)

            def apply(translated: str, record=record) -> None:
                record["translated"] = translated

            segments.append((text, apply))
        page_blocks.append((page, blocks))

    def rebuild() -> bytes:
        for page_number, (page, blocks) in enumerate(page_blocks, start=1):
            if not blocks:
                continue
            replacements = []
            for record in blocks:
                if record["translated"] == record["text"]:
                    continue
                fontname = _pdf_font_for(record["translated"], target_language)
                style = _fit_pdf_text(
                    page, record["rect"], record["translated"], record["size"], fontname
                )
                if style is None:
                    warnings.append(
                        f"page {page_number}: a translated text block did not fit and was kept in the source language"
                    )
                    continue
                replacements.append((record, style))
            if not replacements:
                continue
            for record, _ in replacements:
                page.add_redact_annot(record["rect"])
            try:
                page.apply_redactions(
                    images=getattr(pymupdf, "PDF_REDACT_IMAGE_NONE", 2)
                )
            except TypeError:
                page.apply_redactions()
            for record, (font_size, fontname) in replacements:
                color_int = record["color"]
                color = (
                    ((color_int >> 16) & 255) / 255.0,
                    ((color_int >> 8) & 255) / 255.0,
                    (color_int & 255) / 255.0,
                )
                leftover = page.insert_textbox(
                    record["rect"],
                    record["translated"],
                    fontsize=font_size,
                    fontname=fontname,
                    color=color,
                    align=0,
                    lineheight=_PDF_LINE_HEIGHT,
                )
                if leftover < 0:
                    raise RuntimeError(
                        f"PDF text insertion failed on page {page_number}"
                    )
        return doc.tobytes()

    return _ParsedDocument(segments, rebuild, warnings)


def _fit_pdf_text(page, rect, text: str, size: float, fontname: str):
    """Fit text at a readable, consistent size without changing the source page."""
    if 9.0 <= size <= 12.0:
        preferred_size = min(float(size), _PDF_BODY_FONT_SIZE)
    elif size > 12.0:
        preferred_size = float(size) * 0.8
    else:
        preferred_size = float(size)
    minimum_size = _PDF_MIN_BODY_FONT_SIZE if size >= 9.0 else 3.0
    for candidate in dict.fromkeys((fontname, "japan")):
        font_size = (
            preferred_size if candidate == fontname else min(preferred_size, 8.0)
        )
        while font_size >= minimum_size:
            try:
                leftover = page.new_shape().insert_textbox(
                    rect,
                    text,
                    fontsize=font_size,
                    fontname=candidate,
                    align=0,
                    lineheight=_PDF_LINE_HEIGHT,
                )
            except Exception:  # noqa: BLE001 - fonts may fail with backend-specific errors
                break
            if leftover >= 0:
                return font_size, candidate
            font_size -= 0.5
    return None


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _split_long_text(text: str, limit: int) -> list[str]:
    """Split oversized text at sentence boundaries; pieces concatenate back to
    the original text exactly (boundary characters stay inside each piece)."""
    if len(text) <= limit:
        return [text]
    pieces: list[str] = []
    start = 0
    for match in _SENTENCE_BOUNDARY_RE.finditer(text):
        end = match.end()
        if end - start >= limit:
            pieces.append(text[start:end])
            start = end
    if start < len(text):
        pieces.append(text[start:])
    out: list[str] = []
    for piece in pieces:
        while len(piece) > limit:
            out.append(piece[:limit])
            piece = piece[limit:]
        out.append(piece)
    return out or [text]


def build_chunks(texts: list[str], limit: int) -> list[list[int]]:
    """Greedily pack text indices into chunks whose combined payload stays
    under limit. Each index appears exactly once, in order."""
    chunks: list[list[int]] = []
    current: list[int] = []
    current_len = 0
    for idx, text in enumerate(texts):
        if current and current_len + len(text) > limit:
            chunks.append(current)
            current = []
            current_len = 0
        current.append(idx)
        current_len += len(text)
    if current:
        chunks.append(current)
    return chunks


# ---------------------------------------------------------------------------
# Glossary parsing
# ---------------------------------------------------------------------------


def _glossary_headerish(first: str | None, second: str | None) -> bool:
    for cell in (first, second):
        if cell and cell.strip().lower() in _GLOSSARY_HEADER_WORDS:
            return True
    return False


def _parse_glossary_rows(rows) -> dict:
    terms: dict = {}
    row_iter = iter(rows)
    first_row = next(row_iter, None)
    if first_row is None:
        return terms
    cells = [c.strip() for c in first_row] if first_row else []
    second = cells[1] if len(cells) > 1 else ""
    if not _glossary_headerish(cells[0] if cells else "", second) and cells and second:
        terms[cells[0]] = second
    for row in row_iter:
        cells = [c.strip() for c in row] if row else []
        if len(cells) >= 2 and cells[0] and cells[1]:
            terms[cells[0]] = cells[1]
    return terms


def _parse_delimited_glossary(text: str, delimiter: str) -> dict:
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    return _parse_glossary_rows(reader)


def _parse_line_glossary(text: str) -> dict:
    terms: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            source, target = line.split("=", 1)
        elif "\t" in line:
            source, target = line.split("\t", 1)
        else:
            continue
        source, target = source.strip(), target.strip()
        if source and target:
            terms[source] = target
    return terms


def _parse_xlsx_glossary(data: bytes) -> dict:
    """Read the first worksheet of an xlsx glossary (first two string columns
    per row) at zip level, without openpyxl."""
    from lxml import etree

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            sst = etree.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in sst.iter(NS_X + "si"):
                shared.append("".join(t.text or "" for t in si.iter(NS_X + "t")))

        workbook = etree.fromstring(zf.read("xl/workbook.xml"))
        rels = etree.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rel_targets = {
            rel.get("Id"): rel.get("Target")
            for rel in rels.iter(
                "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
            )
        }
        rel_ns = (
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        first_sheet_target = None
        for sheet in workbook.iter(NS_X + "sheet"):
            rid = sheet.get(rel_ns)
            target = rel_targets.get(rid)
            if target:
                first_sheet_target = target
                break
        if not first_sheet_target:
            return {}
        sheet_path = "xl/" + first_sheet_target.lstrip("/")
        sheet_path = sheet_path.replace("xl/xl/", "xl/")
        if sheet_path not in zf.namelist():
            return {}

        rows = []
        sheet_root = etree.fromstring(zf.read(sheet_path))
        for row in sheet_root.iter(NS_X + "row"):
            values = []
            for cell in row.iter(NS_X + "c"):
                cell_type = cell.get("t")
                value_node = cell.find(NS_X + "v")
                value = value_node.text if value_node is not None else None
                if cell_type == "s" and value is not None:
                    try:
                        value = shared[int(value)]
                    except (ValueError, IndexError):
                        value = None
                elif cell_type == "inlineStr":
                    inline = cell.find(NS_X + "is")
                    value = (
                        "".join(t.text or "" for t in inline.iter(NS_X + "t"))
                        if inline is not None
                        else None
                    )
                if value is not None and value.strip():
                    values.append(value)
            if len(values) >= 2:
                rows.append((values[0], values[1]))
    return _parse_glossary_rows(rows)


def parse_glossary_bytes(data: bytes, filename: str) -> dict:
    ext = os.path.splitext(filename)[1].lower()
    try:
        if ext == ".xlsx":
            return _parse_xlsx_glossary(data)
        text = data.decode("utf-8-sig", errors="replace")
        if ext == ".csv":
            sample = text[:4096]
            delimiter = ";" if sample.count(";") > sample.count(",") else ","
            return _parse_delimited_glossary(text, delimiter)
        if ext == ".tsv":
            return _parse_delimited_glossary(text, "\t")
        return _parse_line_glossary(text)
    except Exception:
        log.exception("Failed to parse glossary file %s", filename)
        return {}


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


async def _extract_content(response) -> str:
    """Extract assistant text from a generate_chat_completion response that
    is either a plain dict or a StreamingResponse."""
    content = None
    if hasattr(response, "body_iterator"):
        async for chunk in response.body_iterator:
            data = json.loads(chunk.decode("utf-8", "replace"))
            content = data["choices"][0]["message"]["content"]
        if getattr(response, "background", None) is not None:
            await response.background()
    else:
        content = response["choices"][0]["message"]["content"]
    return content


class Tools:
    def __init__(self):
        self.citation = False
        self.valves = self.Valves()

    class Valves(BaseModel):
        translation_model: str = Field(
            default="", description="Model id used as the translation worker"
        )
        chunk_char_limit: int = Field(
            default=4000, ge=1, description="Maximum characters per translation chunk"
        )
        max_parallel_translations: int = Field(
            default=1, ge=1, description="Maximum concurrent translation requests"
        )
        request_timeout: int = Field(
            default=300, ge=1, description="Timeout in seconds per translation request"
        )
        temperature: float = Field(
            default=1.0, description="Sampling temperature for the translation model"
        )
        reasoning_effort: str = Field(
            default="low",
            pattern=r"(?i)^\s*(minimal|low|medium|high)?\s*$",
            description=(
                "Reasoning effort for the translation model "
                "(minimal, low, medium or high). Leave empty to omit the parameter."
            ),
        )
        glossary: str = Field(
            default="",
            description="Default glossary, one 'source=target' pair per line",
        )
        show_status: bool = Field(
            default=True, description="Show progress status messages in the UI"
        )

    class UserValves(BaseModel):
        default_target_language: str = Field(
            default="",
            description="Language to translate into when the request does not specify one",
        )
        glossary: str = Field(
            default="",
            description="Personal glossary, one 'source=target' pair per line",
        )

    async def _emit(
        self, emitter, description: str, done: bool = False, status: str = "in_progress"
    ) -> None:
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

    async def translate_file(
        self,
        target_language: str = "",
        glossary: str = "",
        glossary_file: str = "",
        source_language: str = "",
        __user__: dict | None = None,
        __request__: Any = None,
        __files__: list | None = None,
        __event_emitter__: Callable | None = None,
        __chat_id__: str = "",
        __message_id__: str = "",
        __metadata__: dict | None = None,
    ) -> str:
        """
        Translate attached docx/xlsx/pptx/pdf files into a target language and
        attach the translated copies to the chat message.

        :param target_language: Language to translate into, e.g. "Japanese" or "en". Falls back to the user's default.
        :param glossary: Optional inline glossary, one "source=target" pair per line, to keep terminology consistent.
        :param glossary_file: Optional name or id of an attached glossary file (csv/tsv/xlsx/txt/md; first column source, second column target).
        :param source_language: Source language hint. Leave empty for auto-detection.
        :param __user__: User context (injected by Open WebUI).
        :param __request__: Request context (injected by Open WebUI).
        :param __files__: Attached files (injected by Open WebUI).
        :param __event_emitter__: Event emitter for status updates (injected by Open WebUI).
        :param __chat_id__: Chat id (injected by Open WebUI).
        :param __message_id__: Message id (injected by Open WebUI).
        :param __metadata__: Chat metadata (injected by Open WebUI).
        :return: English summary of the translation results.
        """
        user_valves = None
        if isinstance(__user__, dict):
            user_valves = __user__.get("valves")

        def user_glossary() -> str:
            if user_valves is None:
                return ""
            return getattr(user_valves, "glossary", "") or ""

        def user_default_language() -> str:
            if user_valves is None:
                return ""
            return getattr(user_valves, "default_target_language", "") or ""

        language = (target_language or user_default_language()).strip()
        if not language:
            return (
                "Translation skipped: no target language specified. "
                "Ask the user which language to translate into, or set a default in UserValves."
            )
        if not self.valves.translation_model:
            return (
                "Translation skipped: the 'translation_model' valve is not configured. "
                "An admin must set it to a model id in the tool settings."
            )
        if __request__ is None:
            return "Translation skipped: no request context was injected; this tool must run inside Open WebUI."

        file_entries = [
            f
            for f in (__files__ or [])
            if isinstance(f, dict) and f.get("type", "file") == "file" and f.get("id")
        ]

        glossary_terms: dict = {}
        for source in (self.valves.glossary or "", user_glossary()):
            glossary_terms.update(_parse_line_glossary(source or ""))
        glossary_names = [
            part.strip() for part in (glossary_file or "").split(",") if part.strip()
        ]
        glossary_entries, unmatched_glossary = self._match_glossary_files(
            file_entries, glossary_names
        )

        targets = [
            f
            for f in file_entries
            if os.path.splitext(f.get("name", ""))[1].lower() in TRANSLATABLE_EXTENSIONS
            and f.get("id") not in {g.get("id") for g in glossary_entries}
        ]
        if not targets:
            missing = (
                f" Attached files: {', '.join(f.get('name', '?') for f in file_entries)}."
                if file_entries
                else ""
            )
            return (
                "No translatable files attached. Ask the user to attach a docx, xlsx, pptx or pdf file."
                + missing
            )

        for entry in glossary_entries:
            name = entry.get("name", "")
            if os.path.splitext(name)[1].lower() not in GLOSSARY_EXTENSIONS:
                continue
            data = await self._read_file_bytes(entry.get("id"))
            if data is None:
                unmatched_glossary.append(name)
                continue
            glossary_terms.update(parse_glossary_bytes(data, name))
        # Inline glossary wins over every persistent source.
        glossary_terms.update(_parse_line_glossary(glossary or ""))

        try:
            from open_webui.models.users import UserModel

            user = UserModel(**__user__) if isinstance(__user__, dict) else __user__
        except Exception:
            log.exception("Falling back to dict user for model calls")
            user = __user__

        results: list[str] = []
        total_untranslated = 0
        total_pdf_unfitted = 0
        attached_count = 0
        for entry in targets:
            name = entry.get("name", "file")
            await self._emit(__event_emitter__, f"Parsing {name}")
            data = await self._read_file_bytes(entry.get("id"))
            if data is None:
                results.append(f"- {name}: FAILED (file could not be read)")
                continue
            try:
                parsed = self._parse_document(data, name, language)
            except Exception as exc:
                log.exception("Failed to parse %s", name)
                results.append(f"- {name}: FAILED ({exc})")
                continue

            texts = [text for text, _ in parsed.segments]
            if not texts:
                results.append(f"- {name}: no translatable text found, skipped")
                continue

            piece_lists = [
                _split_long_text(text, self.valves.chunk_char_limit) for text in texts
            ]
            flat: list[tuple[int, int, str]] = []
            for target_idx, pieces in enumerate(piece_lists):
                for piece_idx, piece in enumerate(pieces):
                    flat.append((target_idx, piece_idx, piece))
            chunks = build_chunks(
                [piece for _, _, piece in flat], self.valves.chunk_char_limit
            )
            await self._emit(
                __event_emitter__,
                f"{name}: extracted {len(texts)} segments into {len(chunks)} chunks",
            )

            translated_pieces: dict[tuple[int, int], str] = {}
            untranslated = await self._translate_chunks(
                __request__,
                user,
                language,
                source_language,
                glossary_terms,
                flat,
                chunks,
                __event_emitter__,
                name,
                translated_pieces,
            )
            total_untranslated += untranslated

            for target_idx, pieces in enumerate(piece_lists):
                joined = "".join(
                    translated_pieces.get((target_idx, piece_idx), piece)
                    for piece_idx, piece in enumerate(pieces)
                )
                parsed.segments[target_idx][1](joined)

            await self._emit(
                __event_emitter__, f"{name}: rebuilding translated document"
            )
            try:
                output = parsed.rebuild()
            except Exception as exc:
                log.exception("Failed to rebuild %s", name)
                results.append(f"- {name}: FAILED while writing ({exc})")
                continue

            ext = os.path.splitext(name)[1].lower()
            out_name = f"{_stem(name)}_{_safe_lang_code(language)}{ext}"
            try:
                await self._attach_file(
                    __request__,
                    user,
                    __metadata__,
                    __event_emitter__,
                    __chat_id__,
                    __message_id__,
                    out_name,
                    MIME_TYPES.get(ext, "application/octet-stream"),
                    output,
                )
            except Exception as exc:
                log.exception("Failed to attach translated file for %s", name)
                results.append(f"- {name}: translated but FAILED to attach ({exc})")
                continue

            attached_count += 1
            note = f"- {name}: {len(texts)} segments in {len(chunks)} chunks -> {out_name} (attached)"
            if untranslated:
                note += f", {untranslated} pieces left untranslated"
            if parsed.warnings:
                total_pdf_unfitted += len(parsed.warnings)
                note += f", {len(parsed.warnings)} PDF text blocks kept in the source language because the translation did not fit"
            results.append(note)

        summary_lines = [
            f"Translated into {language}"
            + (
                f" using a glossary with {len(glossary_terms)} terms"
                if glossary_terms
                else ""
            )
            + ":"
        ]
        summary_lines.extend(results)
        if unmatched_glossary:
            summary_lines.append(
                "Warning: glossary file(s) not found or unreadable: "
                + ", ".join(unmatched_glossary)
            )
        if total_untranslated:
            summary_lines.append(
                f"{total_untranslated} text piece(s) could not be translated and were kept in the source language."
            )
        if total_pdf_unfitted:
            summary_lines.append(
                f"{total_pdf_unfitted} PDF text block(s) could not fit at a readable size and were kept in the source language."
            )
        if attached_count:
            summary_lines.append(
                "The translated file(s) have been attached to this message."
            )
        await self._emit(
            __event_emitter__, "Translation complete", done=True, status="complete"
        )
        return "\n".join(summary_lines)

    # -- helpers -----------------------------------------------------------

    def _parse_document(self, data: bytes, name: str, language: str) -> _ParsedDocument:
        ext = os.path.splitext(name)[1].lower()
        if ext == ".docx":
            return parse_docx(data)
        if ext == ".pptx":
            return parse_pptx(data)
        if ext == ".xlsx":
            return parse_xlsx(data)
        if ext == ".pdf":
            return parse_pdf(data, language)
        raise ValueError(f"unsupported extension: {ext}")

    def _match_glossary_files(self, file_entries: list[dict], wanted: list[str]):
        matched: list[dict] = []
        unmatched: list[str] = []
        for token in wanted:
            hit = None
            token_lower = token.lower()
            for entry in file_entries:
                fname = entry.get("name", "")
                if (
                    token == entry.get("id")
                    or token_lower == fname.lower()
                    or token_lower == _stem(fname).lower()
                    or (len(token_lower) >= 3 and token_lower in fname.lower())
                ):
                    hit = entry
                    break
            if hit is not None:
                matched.append(hit)
            else:
                unmatched.append(token)
        return matched, unmatched

    async def _read_file_bytes(self, file_id: str) -> bytes | None:
        try:
            from open_webui.models.files import Files
            from open_webui.storage.provider import Storage

            model = Files.get_file_by_id(file_id)
            if inspect.isawaitable(model):
                model = await model
            if model is None:
                return None
            path = Storage.get_file(model.path)
            return await asyncio.to_thread(Path(path).read_bytes)
        except Exception:
            log.exception("Failed to read file %s from storage", file_id)
            return None

    def _build_messages(
        self,
        target_language: str,
        source_language: str,
        glossary_terms: dict,
        payload: str,
        strict: bool,
    ) -> list[dict]:
        source_clause = (
            f"from {source_language}" if source_language else "from the source language"
        )
        rules = [
            f"Translate the values of the JSON object {source_clause} into {target_language}.",
            "Return ONLY a valid JSON object with exactly the same keys as the input. Never add, drop, rename or nest keys.",
            "Translate each value independently, preserving meaning, tone, formality level and line breaks.",
            "Never translate URLs, email addresses, code snippets, numbers, formulas or file paths.",
            "Keep placeholders such as {0}, %s, <tag> and {{var}} exactly as they are.",
        ]
        if glossary_terms:
            rules.append(
                "Apply this glossary strictly whenever a source term appears "
                "(source => target): "
                + "; ".join(
                    f"{src} => {dst}" for src, dst in list(glossary_terms.items())[:200]
                )
            )
        if strict:
            rules.append(
                "Your previous reply was not a valid JSON object with the same keys. Output raw JSON only, with no markdown fences, no commentary."
            )
        system = "You are a professional document translator. " + " ".join(rules)
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": payload},
        ]

    def _parse_model_json(self, content: str | None) -> dict | None:
        if not content:
            return None
        text = content.strip()
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    async def _call_model(self, request, user, model: str, messages: list[dict]) -> str:
        from open_webui.utils.chat import generate_chat_completion

        form_data: dict = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": self.valves.temperature,
        }
        effort = (self.valves.reasoning_effort or "").strip().lower()
        if effort:
            form_data["reasoning_effort"] = effort

        response = await generate_chat_completion(
            request,
            form_data=form_data,
            user=user,
        )
        return await _extract_content(response)

    async def _translate_chunks(
        self,
        request,
        user,
        target_language: str,
        source_language: str,
        glossary_terms: dict,
        flat: list[tuple[int, int, str]],
        chunks: list[list[int]],
        emitter,
        name: str,
        translated_pieces: dict[tuple[int, int], str],
    ) -> int:
        semaphore = asyncio.Semaphore(max(1, self.valves.max_parallel_translations))
        total = len(chunks)
        done_count = 0
        report_step = max(1, total // 10)
        untranslated = 0
        lock = asyncio.Lock()

        async def worker(chunk: list[int]) -> None:
            nonlocal done_count, untranslated
            async with semaphore:
                remaining = {str(i): flat[i][2] for i in chunk}
                translated: dict[str, str] = {}
                for attempt in range(3):
                    rate_limited = False
                    messages = self._build_messages(
                        target_language,
                        source_language,
                        glossary_terms,
                        json.dumps(remaining, ensure_ascii=False),
                        strict=attempt > 0,
                    )
                    try:
                        content = await asyncio.wait_for(
                            self._call_model(
                                request, user, self.valves.translation_model, messages
                            ),
                            timeout=self.valves.request_timeout,
                        )
                        parsed = self._parse_model_json(content)
                    except Exception as exc:
                        log.exception(
                            "Translation call failed (attempt %d)", attempt + 1
                        )
                        parsed = None
                        status_code = getattr(exc, "status_code", None)
                        message = str(exc).lower()
                        rate_limited = status_code == 429 or any(
                            word in message
                            for word in ("429", "rate limit", "overload")
                        )
                        if rate_limited and attempt < 2:
                            headers = getattr(exc, "headers", None) or {}
                            retry_after = headers.get("Retry-After") or headers.get(
                                "retry-after"
                            )
                            try:
                                delay = float(retry_after)
                            except (TypeError, ValueError):
                                delay = 15 * (attempt + 1)
                            await asyncio.sleep(min(max(delay, 1), 120))
                    if parsed is not None:
                        for key in list(remaining):
                            value = parsed.get(key)
                            if isinstance(value, str) and value.strip():
                                translated[key] = value
                                del remaining[key]
                    if not remaining:
                        break
                    if parsed is None and attempt < 2 and not rate_limited:
                        await asyncio.sleep(2**attempt)
                async with lock:
                    for idx in chunk:
                        value = translated.get(str(idx))
                        if value is not None:
                            translated_pieces[(flat[idx][0], flat[idx][1])] = value
                    untranslated += len(remaining)
                    done_count += 1
                    if done_count == total or done_count % report_step == 0:
                        await self._emit(
                            emitter, f"{name}: translating chunks {done_count}/{total}"
                        )

        if total == 1:
            await worker(chunks[0])
        else:
            await asyncio.gather(*(worker(chunk) for chunk in chunks))
        return untranslated

    async def _attach_file(
        self,
        request,
        user,
        metadata,
        emitter,
        chat_id: str,
        message_id: str,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> None:
        from fastapi import UploadFile
        from open_webui.routers.files import upload_file_handler
        from starlette.datastructures import Headers

        upload = UploadFile(
            file=io.BytesIO(data),
            filename=filename,
            headers=Headers({"content-type": content_type}),
        )
        file_item = await upload_file_handler(
            request,
            file=upload,
            metadata=metadata or {},
            process=False,
            process_in_background=False,
            user=user,
        )
        file_id = file_item.id
        try:
            url = str(request.url_for("get_file_content_by_id", id=file_id))
        except Exception:  # noqa: BLE001 - fall back if URL construction fails
            url = f"/api/v1/files/{quote(file_id)}/content"
        files = [
            {
                "type": "file",
                "id": file_id,
                "url": url,
                "name": filename,
                "content_type": content_type,
            }
        ]
        if chat_id and message_id:
            try:
                from open_webui.models.chats import Chats

                db_files = await Chats.add_message_files_by_id_and_message_id(
                    chat_id, message_id, files
                )
                if db_files is not None:
                    files = db_files
            except Exception:
                log.exception("Failed to persist message files for %s", filename)
        if emitter:
            await emitter({"type": "chat:message:files", "data": {"files": files}})
