"""All Streamlit rendering: CSS, briefing card, gallery + color renderers,
and the small custom-agent state callbacks."""
from __future__ import annotations

import re

import streamlit as st

from .config import CUSTOM_AGENT_PROMPT_TEMPLATE
from .llm import domain
from .synthesis import HEX_INLINE_RE, parse_briefing_sections


CSS_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* Typografie */
html, body, .stMarkdown, .stButton button, input, textarea, label, h1, h2, h3, h4 {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}
.block-container { padding-top: 4rem; padding-bottom: 6rem; max-width: 1100px; }
h1 { font-weight: 700 !important; font-size: 3.4rem !important; letter-spacing: -0.045em !important; line-height: 1.05 !important; margin-bottom: 0.4rem !important; }
h2 { font-weight: 600 !important; font-size: 1.5rem !important; letter-spacing: -0.01em !important; border-bottom: none !important; margin-top: 2.5rem !important; margin-bottom: 1rem !important; padding-bottom: 0 !important; }
h3 { font-weight: 600 !important; font-size: 1.35rem !important; margin-top: 2rem !important; }
.stMarkdown p, .stMarkdown li { line-height: 1.7; font-size: 0.98rem; }

/* Header blendet mit Page-Background. Footer + Streamlits Running-Indicator weg.
   Hinweis: der Initial-Flash des Indicators beim Page-Load ist eine
   Streamlit-Framework-Limitation (FOUC) — CSS greift erst nach dem ersten Render. */
header[data-testid="stHeader"] { background: var(--background-color) !important; }
footer,
[data-testid="stStatusWidget"] { display: none !important; }

/* Section-Labels in editorial all-caps */
.ts-eyebrow, .ts-section {
    text-transform: uppercase;
    letter-spacing: 0.22em;
    font-size: 0.72rem;
    font-weight: 500;
    opacity: 0.55;
}
.ts-eyebrow { margin-bottom: 1rem; }
.ts-section { margin-top: 3.5rem; margin-bottom: 1.25rem; }
.ts-rule { height: 1px; background: var(--border-color); margin: 2rem 0; border: 0; }
.ts-meta { opacity: 0.7; font-size: 0.85rem; }

/* Evaluator badge + feedback per agent tab */
.ts-eval {
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-size: 0.7rem;
    font-weight: 500;
    opacity: 0.7;
    margin-top: 0.5rem;
}
.ts-eval-feedback {
    font-size: 0.88rem;
    line-height: 1.6;
    margin-top: 0.5rem;
    margin-bottom: 1.75rem;
    padding: 0.85rem 1rem;
    background: var(--secondary-background-color);
    border-left: 2px solid var(--border-color);
    opacity: 0.85;
}

/* Briefing-Card via st.container(border=True) */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--secondary-background-color) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 4px !important;
}
[data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"] {
    padding: 1rem 0.5rem;
}

/* Sidebar-Labels editorial */
[data-testid="stSidebar"] label {
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-size: 0.7rem !important;
    font-weight: 500 !important;
    opacity: 0.7;
}
[data-testid="stSidebar"] input { border-radius: 0 !important; }

/* History-Liste in der Sidebar: kompakter Text, gedaempfter Subtitle */
.ts-history-meta {
    font-size: 0.65rem;
    line-height: 1.4;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    opacity: 0.5;
    margin: -0.4rem 0 0.85rem 0.1rem;
}

/* Buttons: konsistent dunkel mit hellem Text — in beiden Modi lesbar.
   stDownloadButton wird genauso gestyled wie stButton, damit die zwei nebeneinander
   gestellten Buttons im Briefing-Header (Share + PDF export) identisch aussehen. */
.stButton button,
.stDownloadButton button {
    border-radius: 0 !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.18em !important;
    font-size: 0.78rem !important;
    padding: 0.85rem 1.25rem !important;
    background: #0A0A0A !important;
    color: #FAFAF7 !important;
    border: 1px solid #0A0A0A !important;
}
.stButton button p,
.stButton button span,
.stButton button div,
.stDownloadButton button p,
.stDownloadButton button span,
.stDownloadButton button div {
    color: #FAFAF7 !important;
}
/* Disabled state: greyed out but keeps the same shape. */
.stButton button:disabled,
.stDownloadButton button:disabled {
    opacity: 0.45 !important;
    cursor: not-allowed !important;
}

/* Tabs */
[data-baseweb="tab-list"] { gap: 0; padding: 0; }
[data-baseweb="tab"] {
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.16em !important;
    font-size: 0.75rem !important;
    padding: 0.85rem 1.5rem !important;
}

/* Moodboard-Galerie unter dem Briefing */
.ts-gallery {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 0.65rem;
    margin-top: 1rem;
    margin-bottom: 1rem;
}
.ts-gallery-tile {
    aspect-ratio: 4 / 5;
    background-size: cover;
    background-position: center;
    background-color: var(--secondary-background-color);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    transition: transform 0.15s ease;
}
.ts-gallery-tile:hover { transform: translateY(-1px); }

/* Color-Card-Stack: Hex-Tile + Name + Code (Bilder leben im Moodboard) */
.ts-color-card { display: flex; flex-direction: column; gap: 0.45rem; }
.ts-color-tile {
    height: 96px;
    border-radius: 4px;
    border: 1px solid var(--border-color);
}
.ts-color-name { font-weight: 600; font-size: 0.9rem; line-height: 1.2; }
.ts-color-hex {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.74rem;
    opacity: 0.65;
}

/* Source-Cards mit OG-Image */
.ts-source-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; margin-top: 1rem; }
.ts-source {
    display: flex;
    flex-direction: column;
    background: var(--secondary-background-color);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    text-decoration: none !important;
    color: inherit !important;
    transition: transform 0.15s ease;
    overflow: hidden;
}
.ts-source:hover { transform: translateY(-1px); }
.ts-source-image {
    width: 100%;
    aspect-ratio: 16 / 10;
    background-size: cover;
    background-position: center;
    background-color: var(--background-color);
    border-bottom: 1px solid var(--border-color);
}
.ts-source-content { padding: 0.85rem 1rem 1rem 1rem; }
.ts-source-domain {
    display: flex; align-items: center; gap: 0.4rem;
    font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.18em;
    opacity: 0.6; margin-bottom: 0.45rem;
}
.ts-source-domain img { width: 14px; height: 14px; border-radius: 2px; }
.ts-source-title {
    font-size: 0.92rem; font-weight: 500; line-height: 1.45;
    display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
    overflow: hidden;
}
</style>
"""


def render_briefing_card(briefing_text: str) -> None:
    """Section-aware briefing renderer. Briefing markdown stays untouched —
    section bodies render as pure markdown. Recommended Colors gets a hex
    swatch grid below the bullet list. All photographic visuals live in the
    moodboard below the card, not inside color cards."""
    sections = parse_briefing_sections(briefing_text)
    for heading, body in sections.items():
        st.markdown(f"## {heading}")
        if heading.lower() == "recommended colors":
            st.markdown(body)
            _render_color_palette_grid(body)
        else:
            st.markdown(body)


def render_image_gallery(urls: list[str]) -> None:
    """Render a flat moodboard of all collected og:images under the briefing."""
    if not urls:
        return
    st.markdown('<div class="ts-section">Moodboard</div>', unsafe_allow_html=True)
    tiles = "".join(
        f'<div class="ts-gallery-tile" style="background-image:url(\'{u}\');"></div>'
        for u in urls
    )
    st.markdown(f'<div class="ts-gallery">{tiles}</div>', unsafe_allow_html=True)


def _render_color_palette_grid(body: str) -> None:
    """Swatch grid for Recommended Colors. Each tile = hex block + name + hex code.
    No paired image — those live in the moodboard.

    Scans the body line-by-line for hex codes — robust to whether the LLM
    formatted colors as `- ` bullets or as plain paragraphs."""
    swatches: list[tuple[str, str]] = []
    seen_hex: set[str] = set()
    for line in (body or "").splitlines():
        m = HEX_INLINE_RE.search(line)
        if not m:
            continue
        hex_code = m.group(0)
        if hex_code.lower() in seen_hex:
            continue
        seen_hex.add(hex_code.lower())
        name_match = re.search(r"\*\*([^*]+)\*\*", line)
        name = name_match.group(1).strip() if name_match else hex_code
        swatches.append((name, hex_code))
    if not swatches:
        return
    n = min(len(swatches), 6)
    cols = st.columns(n)
    for col, (name, hex_code) in zip(cols, swatches[:n]):
        with col:
            st.markdown(
                f'<div class="ts-color-card">'
                f'<div class="ts-color-tile" style="background:{hex_code};"></div>'
                f'<div class="ts-color-name">{name}</div>'
                f'<div class="ts-color-hex">{hex_code}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def render_sources(cites: list[dict]) -> None:
    if not cites:
        return
    cards = []
    for c in cites:
        d = domain(c["url"])
        favicon = f"https://www.google.com/s2/favicons?domain={d}&sz=32"
        title = (c["title"] or d).replace("<", "&lt;").replace(">", "&gt;")
        img = c.get("image")
        image_html = (
            f'<div class="ts-source-image" style="background-image:url(\'{img}\');"></div>'
            if img
            else ""
        )
        cards.append(
            f'<a class="ts-source" href="{c["url"]}" target="_blank" rel="noopener">'
            f'{image_html}'
            f'<div class="ts-source-content">'
            f'<div class="ts-source-domain"><img src="{favicon}" alt=""/>{d}</div>'
            f'<div class="ts-source-title">{title}</div>'
            f'</div>'
            f'</a>'
        )
    st.markdown(
        f'<div class="ts-source-grid">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


# -------------------------------------------------- Custom-agent state callbacks


def add_custom_agent() -> None:
    """Streamlit on_click callback: append a new blank custom agent card."""
    cid = st.session_state.get("ca_next_id", 0)
    st.session_state.ca_next_id = cid + 1
    st.session_state.custom_agents.append({
        "id": cid,
        "name": f"CustomAgent{cid + 1}",
        "domain": "",
        "prompt": CUSTOM_AGENT_PROMPT_TEMPLATE,
        "queries_text": "",
    })


def remove_custom_agent(agent_id: int) -> None:
    """Streamlit on_click callback: drop a custom agent card by id."""
    st.session_state.custom_agents = [
        ca for ca in st.session_state.custom_agents if ca["id"] != agent_id
    ]
