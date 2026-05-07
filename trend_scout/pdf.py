"""Native PDF export of the briefing using reportlab.

The PDF mirrors the on-screen render:
  - Header (Trend Scout · season · target · date)
  - Briefing sections as the LLM produced them (## Headings + body)
  - Recommended Colors section gets a hex-tile grid below the bullet list
  - Moodboard grid with the validated images
  - Source list per agent at the end

Image fetches are synchronous httpx calls with a short timeout; failures are
skipped silently so the PDF always builds even if some og:images won't load.
"""
from __future__ import annotations

import io
import re
from datetime import date as date_cls

import httpx
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .synthesis import HEX_INLINE_RE, parse_briefing_sections


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 TrendScout/1.0"
    )
}


def _markdown_inline_to_rl(text: str) -> str:
    """Convert **bold** and `code` to reportlab inline markup, escape XML chars."""
    safe = (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
    safe = _BOLD_RE.sub(r"<b>\1</b>", safe)
    safe = _INLINE_CODE_RE.sub(r'<font face="Courier">\1</font>', safe)
    return safe


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "eyebrow": ParagraphStyle(
            "eyebrow",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=colors.grey,
            spaceAfter=4,
        ),
        "title": ParagraphStyle(
            "ts_title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=28,
            leading=32,
            spaceAfter=4,
            alignment=TA_LEFT,
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=colors.grey,
            spaceAfter=18,
        ),
        "h2": ParagraphStyle(
            "ts_h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "ts_h3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            spaceAfter=4,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            leftIndent=14,
            bulletIndent=2,
            spaceAfter=3,
        ),
        "color_name": ParagraphStyle(
            "color_name",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            spaceAfter=1,
        ),
        "color_hex": ParagraphStyle(
            "color_hex",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=7,
            textColor=colors.grey,
            leading=9,
        ),
        "source": ParagraphStyle(
            "source",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            leftIndent=10,
            bulletIndent=0,
            spaceAfter=2,
        ),
    }


def _section_to_flowables(body: str, styles: dict) -> list:
    """Convert a markdown section body to reportlab flowables."""
    out = []
    for raw in (body or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("- "):
            out.append(Paragraph(
                f"• {_markdown_inline_to_rl(s[2:].strip())}",
                styles["bullet"],
            ))
        else:
            out.append(Paragraph(_markdown_inline_to_rl(s), styles["body"]))
    return out


def _color_swatch_table(body: str, styles: dict) -> Table | None:
    """Hex-tile grid for the Recommended Colors section."""
    swatches: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in (body or "").splitlines():
        m = HEX_INLINE_RE.search(line)
        if not m:
            continue
        hex_code = m.group(0)
        if hex_code.lower() in seen:
            continue
        seen.add(hex_code.lower())
        name_match = re.search(r"\*\*([^*]+)\*\*", line)
        name = name_match.group(1).strip() if name_match else hex_code
        swatches.append((name, hex_code))
    if not swatches:
        return None

    swatches = swatches[:6]
    n = len(swatches)
    name_row = [Paragraph(name, styles["color_name"]) for name, _ in swatches]
    hex_row = [Paragraph(code, styles["color_hex"]) for _, code in swatches]
    tile_row = ["" for _ in swatches]

    col_w = (A4[0] - 4 * cm) / max(n, 1)
    table = Table(
        [tile_row, name_row, hex_row],
        colWidths=[col_w] * n,
        rowHeights=[1.6 * cm, 0.5 * cm, 0.4 * cm],
    )
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    for i, (_, hex_code) in enumerate(swatches):
        try:
            style.append(("BACKGROUND", (i, 0), (i, 0), HexColor(hex_code)))
        except Exception:
            pass
    table.setStyle(TableStyle(style))
    return table


def _fetch_image_sync(url: str, timeout: float = 4.0) -> bytes | None:
    """Sync httpx fetch — reportlab is sync, so we do the same here.
    Hard timeout, swallow all errors, return None on failure.

    Mime-type filter mirrors `llm.fetch_image_bytes` (jpeg/png/webp/heic/heif)
    so an image that survived the moodboard validator can also reach the PDF.
    Pillow handles jpeg/png/webp natively; heic/heif need pillow-heif which
    is optional — if reportlab's Image() can't decode, the entry is silently
    skipped in `_gallery_table`."""
    try:
        with httpx.Client(headers=_BROWSER_HEADERS, timeout=timeout) as c:
            r = c.get(url, follow_redirects=True)
            if r.status_code >= 400:
                return None
            data = r.content
            if not data or len(data) > 4_000_000:
                return None
            mime = r.headers.get("content-type", "").split(";")[0].strip().lower()
            if not mime.startswith("image/"):
                return None
            if mime not in {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}:
                return None
            return data
    except Exception:
        return None


def _gallery_table(urls: list[str]) -> Table | None:
    """3-col grid of moodboard images. Failed downloads are skipped."""
    if not urls:
        return None
    cells = []
    for u in urls:
        data = _fetch_image_sync(u)
        if data is None:
            continue
        try:
            img = Image(io.BytesIO(data))
            img._restrictSize(5 * cm, 6 * cm)
            cells.append(img)
        except Exception:
            continue
    if not cells:
        return None

    cols = 3
    rows: list[list] = []
    for i in range(0, len(cells), cols):
        row = cells[i:i + cols]
        while len(row) < cols:
            row.append("")
        rows.append(row)

    col_w = (A4[0] - 4 * cm) / cols
    table = Table(rows, colWidths=[col_w] * cols)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _sources_flowables(outputs: list[dict], styles: dict) -> list:
    out: list = []
    has_any = any(o.get("citations") for o in outputs)
    if not has_any:
        return out
    out.append(Paragraph("Sources", styles["h2"]))
    for o in outputs:
        cites = o.get("citations") or []
        if not cites:
            continue
        out.append(Paragraph(o.get("name", ""), styles["h3"]))
        for c in cites:
            title = (c.get("title") or c.get("url") or "").strip()
            url = (c.get("url") or "").strip()
            link = (
                f'<link href="{url}" color="black"><u>{_markdown_inline_to_rl(title)}</u></link>'
                if url else _markdown_inline_to_rl(title)
            )
            out.append(Paragraph(f"• {link}", styles["source"]))
    return out


def briefing_to_pdf(
    *,
    season: str,
    target: str,
    briefing_text: str,
    outputs: list[dict],
    gallery_images: list[str],
) -> bytes:
    """Build a print-ready A4 PDF of the briefing. Returns the PDF as bytes
    so the caller can pipe it straight into st.download_button."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"Trend Scout — {season} · {target}",
    )
    styles = _styles()
    story: list = []

    today = date_cls.today().isoformat()
    story.append(Paragraph("TREND BRIEFING", styles["eyebrow"]))
    story.append(Paragraph("Trend Scout", styles["title"]))
    story.append(Paragraph(f"{season}  ·  {target}  ·  {today}", styles["meta"]))

    sections = parse_briefing_sections(briefing_text)
    for heading, body in sections.items():
        story.append(Paragraph(heading, styles["h2"]))
        story.extend(_section_to_flowables(body, styles))
        if heading.lower() == "recommended colors":
            tbl = _color_swatch_table(body, styles)
            if tbl is not None:
                story.append(Spacer(1, 4 * mm))
                story.append(tbl)

    gallery_tbl = _gallery_table(gallery_images)
    if gallery_tbl is not None:
        story.append(Paragraph("Moodboard", styles["h2"]))
        story.append(Spacer(1, 2 * mm))
        story.append(gallery_tbl)

    sources = _sources_flowables(outputs, styles)
    if sources:
        story.append(PageBreak())
        story.extend(sources)

    doc.build(story)
    return buf.getvalue()
