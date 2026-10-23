"""Render a policy document as a screenshot (stage 20 image-ingestion fixture).

The corpus needs at least one *image* document: without it the OCR path has nothing real to
parse and the retrieval gold set cannot contain image cases. Rendering is done in code rather
than committing a binary so the fixture stays reproducible — ``scripts/seed.py`` regenerates
the identical PNG from the same text.

A CJK font is mandatory: with a Latin-only face every glyph becomes a box, the OCR output
becomes meaningless, and the "image retrieval" case would be tested against garbage. Font
candidates cover Windows / Linux (Noto CJK) / macOS, and ``SHOPMATE_IMAGE_FONT`` overrides
them. A missing font raises instead of writing a garbled fixture.
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from shopmate_ecommerce_assistant.synthetic.corpus_types import PolicyDoc

WIDTH = 1080
MARGIN = 72
TITLE_SIZE = 46
META_SIZE = 26
HEADING_SIZE = 34
BODY_SIZE = 30
LINE_GAP = 12
PARAGRAPH_GAP = 26

FONT_CANDIDATES: tuple[str, ...] = (
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/System/Library/Fonts/PingFang.ttc",
)


def resolve_font_path() -> Path:
    """Return the first usable CJK font, honouring ``SHOPMATE_IMAGE_FONT``."""
    override = os.environ.get("SHOPMATE_IMAGE_FONT")
    if override:
        candidate = Path(override)
        if candidate.is_file():
            return candidate
        raise RuntimeError(f"SHOPMATE_IMAGE_FONT 指向的文件不存在：{override}")
    for raw in FONT_CANDIDATES:
        candidate = Path(raw)
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        "未找到可用的中文字体，无法渲染图片文档。请安装 Noto Sans CJK，"
        "或用 SHOPMATE_IMAGE_FONT 指定字体文件。"
    )


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wrap by rendered width; Chinese has no spaces, so this is a per-character walk."""
    lines: list[str] = []
    current = ""
    for char in text:
        trial = current + char
        if font.getlength(trial) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = char
    if current:
        lines.append(current)
    return lines


def render_policy_screenshot(doc: PolicyDoc, target: Path) -> Path:
    """Draw ``doc`` as a poster-style screenshot and write it to ``target``."""
    font_path = str(resolve_font_path())
    title_font = ImageFont.truetype(font_path, TITLE_SIZE)
    meta_font = ImageFont.truetype(font_path, META_SIZE)
    heading_font = ImageFont.truetype(font_path, HEADING_SIZE)
    body_font = ImageFont.truetype(font_path, BODY_SIZE)
    max_width = WIDTH - 2 * MARGIN

    # (text, wrapped lines, is_heading) — laid out first so the canvas fits its content.
    blocks: list[tuple[str, list[str], bool]] = []
    for section in doc.sections:
        blocks.append((section.heading, _wrap(section.heading, heading_font, max_width), True))
        for paragraph in section.paragraphs:
            blocks.append((paragraph, _wrap(paragraph, body_font, max_width), False))

    title_lines = _wrap(doc.title, title_font, max_width)
    height = MARGIN * 2 + len(title_lines) * (TITLE_SIZE + LINE_GAP)
    height += META_SIZE + PARAGRAPH_GAP * 2
    for _, lines, is_heading in blocks:
        step = HEADING_SIZE if is_heading else BODY_SIZE
        height += len(lines) * (step + LINE_GAP) + PARAGRAPH_GAP

    image = Image.new("RGB", (WIDTH, max(height, 600)), "white")
    draw = ImageDraw.Draw(image)

    y = MARGIN
    for line in title_lines:
        draw.text((MARGIN, y), line, font=title_font, fill=(17, 24, 39))
        y += TITLE_SIZE + LINE_GAP
    meta = f"版本 {doc.version} · 生效日期 {doc.effective_from[:10]} · 合成演示数据"
    draw.text((MARGIN, y), meta, font=meta_font, fill=(107, 114, 128))
    y += META_SIZE + PARAGRAPH_GAP
    draw.line((MARGIN, y, WIDTH - MARGIN, y), fill=(209, 213, 219), width=2)
    y += PARAGRAPH_GAP

    for _, lines, is_heading in blocks:
        font = heading_font if is_heading else body_font
        fill = (17, 24, 39) if is_heading else (55, 65, 81)
        step = HEADING_SIZE if is_heading else BODY_SIZE
        for line in lines:
            draw.text((MARGIN, y), line, font=font, fill=fill)
            y += step + LINE_GAP
        y += PARAGRAPH_GAP

    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, format="PNG", optimize=True)
    return target


__all__ = ["FONT_CANDIDATES", "render_policy_screenshot", "resolve_font_path"]
