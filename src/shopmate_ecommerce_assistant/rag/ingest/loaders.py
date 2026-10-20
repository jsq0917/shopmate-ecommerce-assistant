"""Document loaders for PDF, DOCX, PPTX, Markdown and plain text.

Every loader returns :class:`ParsedBlock` values that keep the origin metadata required by
the citation contract: heading path and (where the format exposes it) page number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from docx import Document as DocxDocument
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph
from pptx import Presentation
from pptx.slide import Slide
from pypdf import PdfReader

from shopmate_ecommerce_assistant.rag.chunking import ParsedBlock
from shopmate_ecommerce_assistant.rag.errors import (
    DocumentParseFailed,
    EmptyDocument,
    UnsupportedDocumentType,
    UnsupportedEncoding,
)

SUPPORTED_SUFFIXES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
}

_ATX_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")
_PAGE_NUMBER_LINE = re.compile(
    r"^\s*(?:第\s*\d+\s*页(?:\s*/?\s*共\s*\d+\s*页)?|-\s*\d+\s*-|\d+)\s*$"
)
_SENTENCE_END = ("。", "！", "？", "；", ".", "!", "?", ";", "：", ":")
_DOCX_HEADING_STYLE = re.compile(r"^(?:Heading|标题)\s*(\d)$")
_CN_CLAUSE = re.compile(r"^第[一二三四五六七八九十百零\d]+[章节条]")


@dataclass(frozen=True, slots=True)
class LoadedDocument:
    """Parsed blocks plus the detected media type."""

    blocks: list[ParsedBlock]
    mime_type: str
    page_count: int


def _trim_heading(text: str) -> str:
    return text.strip().strip("#").strip().strip("【】").strip()


def _is_heading_line(line: str, next_line: str | None, *, is_first: bool) -> bool:
    """Detect a heading in line-oriented formats.

    Clause-style headings (``第一条``), bracketed headings (``【包邮门槛】``) and short
    title-like lines followed by longer prose are treated as headings. Sentences never
    qualify because they end with terminal punctuation.
    """
    candidate = line.strip()
    if not candidate or len(candidate) > 48:
        return False
    if candidate.endswith(_SENTENCE_END):
        return False
    if candidate.startswith("【") and candidate.endswith("】"):
        return True
    if _CN_CLAUSE.match(candidate):
        return True
    if is_first and len(candidate) <= 30:
        return True
    stripped_next = (next_line or "").strip()
    return len(candidate) <= 20 and len(stripped_next) > len(candidate) + 8


def _blocks_from_text(
    text: str,
    *,
    heading_path: tuple[str, ...] = (),
    page_no: int | None = None,
) -> list[ParsedBlock]:
    """Split plain text into paragraph blocks, dropping page-number furniture."""
    lines = [
        line.replace("\u3000", " ").rstrip()
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    blocks: list[ParsedBlock] = []
    buffer: list[str] = []
    current_heading = heading_path
    root_heading: str | None = heading_path[0] if heading_path else None
    seen_content = False

    def flush() -> None:
        if buffer:
            joined = "\n".join(buffer).strip()
            if joined:
                blocks.append(
                    ParsedBlock(text=joined, heading_path=current_heading, page_no=page_no)
                )
            buffer.clear()

    for index, line in enumerate(lines):
        if not line.strip():
            flush()
            continue
        if _PAGE_NUMBER_LINE.match(line):
            continue
        next_line = lines[index + 1] if index + 1 < len(lines) else None
        if _is_heading_line(line, next_line, is_first=not seen_content):
            flush()
            trimmed = _trim_heading(line)
            if root_heading is None:
                root_heading = trimmed
                current_heading = (trimmed,)
            elif trimmed == root_heading:
                current_heading = (root_heading,)
            else:
                current_heading = (root_heading, trimmed)
            seen_content = True
            continue
        seen_content = True
        buffer.append(line.strip())
    flush()
    return blocks


def load_markdown(path: Path) -> LoadedDocument:
    """Load Markdown by ATX heading hierarchy."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UnsupportedEncoding() from exc
    blocks: list[ParsedBlock] = []
    stack: list[tuple[int, str]] = []
    buffer: list[str] = []

    def current_path() -> tuple[str, ...]:
        return tuple(title for _, title in stack)

    def flush() -> None:
        if buffer:
            joined = "\n".join(buffer).strip()
            if joined:
                blocks.append(ParsedBlock(text=joined, heading_path=current_path(), page_no=None))
            buffer.clear()

    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        match = _ATX_HEADING.match(line.strip())
        if match:
            flush()
            level = len(match.group(1))
            title = _trim_heading(match.group(2))
            stack = [item for item in stack if item[0] < level]
            stack.append((level, title))
            continue
        if not line.strip():
            flush()
            continue
        buffer.append(line.strip())
    flush()
    return LoadedDocument(blocks=blocks, mime_type=SUPPORTED_SUFFIXES[".md"], page_count=0)


def load_text(path: Path) -> LoadedDocument:
    """Load a UTF-8 plain text file."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UnsupportedEncoding() from exc
    return LoadedDocument(
        blocks=_blocks_from_text(text),
        mime_type=SUPPORTED_SUFFIXES[".txt"],
        page_count=0,
    )


def load_pdf(path: Path) -> LoadedDocument:
    """Load a PDF page by page, preserving ``page_no`` (1-based)."""
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise DocumentParseFailed("PDF 文件无法读取") from exc
    if reader.is_encrypted:
        raise DocumentParseFailed("PDF 文件已加密")

    blocks: list[ParsedBlock] = []
    for page_index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            raise DocumentParseFailed(f"第 {page_index} 页无法解析") from exc
        blocks.extend(_blocks_from_text(text, page_no=page_index))
    return LoadedDocument(
        blocks=blocks, mime_type=SUPPORTED_SUFFIXES[".pdf"], page_count=len(reader.pages)
    )


def _table_rows(table: DocxTable) -> list[str]:
    rows: list[str] = []
    for row in table.rows:
        cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
        if any(cells):
            rows.append(" | ".join(cells))
    return rows


def load_docx(path: Path) -> LoadedDocument:
    """Load DOCX paragraphs and tables, mapping Word heading styles to heading paths."""
    try:
        document = DocxDocument(str(path))
    except Exception as exc:
        raise DocumentParseFailed("DOCX 文件无法读取") from exc

    blocks: list[ParsedBlock] = []
    stack: list[tuple[int, str]] = []
    buffer: list[str] = []

    def current_path() -> tuple[str, ...]:
        return tuple(title for _, title in stack)

    def flush() -> None:
        if buffer:
            joined = "\n".join(buffer).strip()
            if joined:
                blocks.append(ParsedBlock(text=joined, heading_path=current_path(), page_no=None))
            buffer.clear()

    for element in document.element.body.iterchildren():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = DocxParagraph(element, document)
            text = paragraph.text.strip()
            if not text:
                flush()
                continue
            style = (paragraph.style.name if paragraph.style is not None else "") or ""
            match = _DOCX_HEADING_STYLE.match(style)
            if match or style.lower() in {"title", "subtitle"}:
                flush()
                level = int(match.group(1)) if match else 1
                stack = [item for item in stack if item[0] < level]
                stack.append((level, text))
                continue
            buffer.append(text)
        elif tag == "tbl":
            flush()
            rows = _table_rows(DocxTable(element, document))
            if rows:
                blocks.append(
                    ParsedBlock(
                        text="\n".join(rows),
                        heading_path=current_path(),
                        page_no=None,
                    )
                )
    flush()
    return LoadedDocument(blocks=blocks, mime_type=SUPPORTED_SUFFIXES[".docx"], page_count=0)


def _slide_blocks(
    slide: Slide, page_no: int, base_heading: tuple[str, ...] = ()
) -> list[ParsedBlock]:
    heading_path: list[str] = list(base_heading)
    blocks: list[ParsedBlock] = []
    title_shape = slide.shapes.title
    if title_shape is not None and title_shape.has_text_frame:
        title = title_shape.text_frame.text.strip()
        if title:
            heading_path.append(title)
    for shape in slide.shapes:
        if title_shape is not None and shape.shape_id == title_shape.shape_id:
            continue
        if shape.has_text_frame:
            text = "\n".join(
                paragraph.text.strip()
                for paragraph in shape.text_frame.paragraphs
                if paragraph.text.strip()
            )
            if text:
                blocks.append(
                    ParsedBlock(text=text, heading_path=tuple(heading_path), page_no=page_no)
                )
        elif getattr(shape, "has_table", False):
            rows = _table_rows(shape.table)
            if rows:
                blocks.append(
                    ParsedBlock(
                        text="\n".join(rows), heading_path=tuple(heading_path), page_no=page_no
                    )
                )
    if not blocks and heading_path:
        blocks.append(
            ParsedBlock(text=heading_path[0], heading_path=tuple(heading_path), page_no=page_no)
        )
    return blocks


def load_pptx(path: Path) -> LoadedDocument:
    """Load PPTX slides; ``page_no`` is the 1-based slide number.

    A cover slide that only carries a title is treated as the document title and is used
    as the prefix of every following slide's heading path.
    """
    try:
        presentation = Presentation(str(path))
    except Exception as exc:
        raise DocumentParseFailed("PPTX 文件无法读取") from exc

    slides = list(presentation.slides)
    document_title: str | None = None
    if slides:
        cover_title = slides[0].shapes.title
        if cover_title is not None and cover_title.has_text_frame:
            document_title = cover_title.text_frame.text.strip() or None

    blocks: list[ParsedBlock] = []
    for index, slide in enumerate(slides, start=1):
        base = (document_title,) if document_title and index > 1 else ()
        blocks.extend(_slide_blocks(slide, index, base))
    return LoadedDocument(
        blocks=blocks, mime_type=SUPPORTED_SUFFIXES[".pptx"], page_count=len(slides)
    )


_LOADERS = {
    ".pdf": load_pdf,
    ".docx": load_docx,
    ".pptx": load_pptx,
    ".md": load_markdown,
    ".markdown": load_markdown,
    ".txt": load_text,
}


def load_document(path: Path) -> LoadedDocument:
    """Dispatch to the loader matching the file suffix.

    Raises:
        UnsupportedDocumentType: unsupported suffix.
        EmptyDocument: the loader produced no blocks.
        DocumentParseFailed: the format could not be parsed.
    """
    suffix = path.suffix.lower()
    loader = _LOADERS.get(suffix)
    if loader is None:
        raise UnsupportedDocumentType(suffix)
    loaded = loader(path)
    if not loaded.blocks:
        raise EmptyDocument()
    return loaded
