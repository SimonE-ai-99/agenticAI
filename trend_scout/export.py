"""HTML export for the briefing — printable to PDF from the browser.

Why HTML and not native PDF: a printable HTML doc keeps image URLs live
(they load at print time from the source CDN), needs no extra dependency
beyond what's already in the stack, and renders consistently because the
user's browser handles layout. The user opens the file, hits Cmd/Ctrl+P,
chooses 'Save as PDF'.
"""
from __future__ import annotations

import re
from datetime import date as date_cls
from html import escape

from .synthesis import HEX_INLINE_RE, parse_briefing_sections


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")


def _markdown_inline_to_html(text: str) -> str:
    """Convert **bold** and `code` markers in a single line to HTML."""
    safe = escape(text)
    safe = _BOLD_RE.sub(r"<strong>\1</strong>", safe)
    safe = _INLINE_CODE_RE.sub(r"<code>\1</code>", safe)
    return safe


def _section_body_to_html(body: str) -> str:
    """Render a section body: bullets become <ul>/<li>, paragraphs <p>."""
    lines = (body or "").splitlines()
    out: list[str] = []
    in_list = False
    for raw in lines:
        s = raw.strip()
        if s.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"  <li>{_markdown_inline_to_html(s[2:].strip())}</li>")
        elif not s:
            if in_list:
                out.append("</ul>")
                in_list = False
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p>{_markdown_inline_to_html(s)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _color_cards_html(body: str) -> str:
    """Color section: hex tiles + name + code. No paired image — those live
    in the moodboard below the briefing."""
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
        return ""
    cards = []
    for name, hex_code in swatches[:6]:
        cards.append(
            f'<div class="color-card">'
            f'<div class="color-tile" style="background:{hex_code};"></div>'
            f'<div class="color-name">{escape(name)}</div>'
            f'<div class="color-hex">{hex_code}</div>'
            f'</div>'
        )
    return f'<div class="color-grid">{"".join(cards)}</div>'


def _gallery_html(urls: list[str]) -> str:
    if not urls:
        return ""
    tiles = "".join(
        f'<div class="gallery-tile" style="background-image:url(\'{escape(u)}\');"></div>'
        for u in urls
    )
    return (
        f'<h2 class="moodboard-heading">Moodboard</h2>'
        f'<div class="gallery">{tiles}</div>'
    )


def _sources_html(outputs: list[dict]) -> str:
    if not outputs:
        return ""
    rows = []
    for o in outputs:
        cites = o.get("citations") or []
        if not cites:
            continue
        rows.append(f'<h3>{escape(o["name"])}</h3>')
        rows.append("<ul class='sources'>")
        for c in cites:
            title = escape(c.get("title", "") or c.get("url", ""))
            url = escape(c.get("url", ""))
            rows.append(f'  <li><a href="{url}" target="_blank">{title}</a></li>')
        rows.append("</ul>")
    if not rows:
        return ""
    return f'<h2 class="sources-heading">Sources</h2>{"".join(rows)}'


_PRINT_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

* { box-sizing: border-box; }
body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    color: #0A0A0A;
    background: #FAFAF7;
    max-width: 880px;
    margin: 2rem auto;
    padding: 0 1.5rem;
    line-height: 1.6;
}
.eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.22em;
    font-size: 0.72rem;
    font-weight: 500;
    opacity: 0.55;
    margin-bottom: 0.4rem;
}
h1 {
    font-weight: 700;
    font-size: 2.6rem;
    letter-spacing: -0.04em;
    margin: 0 0 0.4rem 0;
}
h2 {
    font-weight: 600;
    font-size: 1.3rem;
    letter-spacing: -0.01em;
    margin-top: 2rem;
    margin-bottom: 0.8rem;
    border-bottom: 1px solid #ddd;
    padding-bottom: 0.3rem;
}
h3 { font-weight: 600; font-size: 1.05rem; margin-top: 1.2rem; }
p, li { font-size: 0.95rem; }
ul { padding-left: 1.4rem; }
ul.sources li { margin-bottom: 0.3rem; font-size: 0.85rem; }
ul.sources a { color: #0A0A0A; text-decoration: underline; }
code {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.85em;
    background: #eee;
    padding: 0.1rem 0.35rem;
    border-radius: 3px;
}
.meta { opacity: 0.65; font-size: 0.85rem; margin-bottom: 2rem; }

.color-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 0.6rem;
    margin: 1rem 0 2rem;
}
.color-card { display: flex; flex-direction: column; gap: 0.35rem; }
.color-tile { height: 80px; border-radius: 4px; border: 1px solid #ddd; }
.color-name { font-weight: 600; font-size: 0.8rem; }
.color-hex { font-family: ui-monospace, monospace; font-size: 0.7rem; opacity: 0.65; }

.moodboard-heading { margin-top: 2.5rem; }
.gallery {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 0.5rem;
    margin: 1rem 0 2rem;
}
.gallery-tile {
    aspect-ratio: 4 / 5;
    background-size: cover;
    background-position: center;
    background-color: #eee;
    border: 1px solid #ddd;
    border-radius: 4px;
}

.sources-heading { margin-top: 2.5rem; }

@media print {
    body { background: white; max-width: none; margin: 0; padding: 1.5cm; }
    h2 { break-after: avoid; }
    .color-card { break-inside: avoid; }
    .gallery-tile { break-inside: avoid; }
    a { color: #0A0A0A; }
}

.print-hint {
    position: fixed;
    top: 0; left: 0; right: 0;
    background: #0A0A0A;
    color: #FAFAF7;
    padding: 0.6rem 1rem;
    font-size: 0.85rem;
    text-align: center;
    z-index: 100;
}
@media print { .print-hint { display: none; } }
"""


def briefing_to_html(
    *,
    season: str,
    target: str,
    briefing_text: str,
    outputs: list[dict],
    gallery_images: list[str],
) -> str:
    """Build a self-contained printable HTML doc. Image URLs stay external —
    the browser fetches them when the doc opens, and the print dialog can
    save the rendered output as PDF."""
    today = date_cls.today().isoformat()

    section_html_parts: list[str] = []
    sections = parse_briefing_sections(briefing_text)
    for heading, body in sections.items():
        section_html_parts.append(f"<h2>{escape(heading)}</h2>")
        section_html_parts.append(_section_body_to_html(body))
        if heading.lower() == "recommended colors":
            section_html_parts.append(_color_cards_html(body))

    body_html = "\n".join(section_html_parts)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Trend Scout — {escape(season)} · {escape(target)}</title>
<style>{_PRINT_CSS}</style>
</head>
<body>
<div class="print-hint">Open in a browser, then File → Print → Save as PDF.</div>

<div class="eyebrow">DRYKORN · Trend Briefing</div>
<h1>Trend Scout</h1>
<div class="meta">{escape(season)} · {escape(target)} · {today}</div>

{body_html}

{_gallery_html(gallery_images)}

{_sources_html(outputs)}

</body>
</html>
"""
    return html
