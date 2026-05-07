"""Synthesis (3-draft Tree-of-Thought + picker), reflection, and moodboard
image validation.

After picking the winning briefing, a critic LLM reads it and may trigger
one revision pass. Then og:image URLs from all agent citations are pooled,
their bytes downloaded in parallel, and a single multimodal Gemini call
filters them against the briefing + target group. Survivors render as the
moodboard under the briefing card. Color cards stay text-only — hex tiles
plus name plus code, no per-color image (those visuals live in the moodboard).
"""
from __future__ import annotations

import asyncio
import re
from datetime import date
from typing import Callable

from google.genai import types

from .config import (
    GALLERY_FINAL_CAP,
    GALLERY_PRE_VALIDATION_CAP,
    MAX_AGENT_ROUNDS,
    MAX_IMAGE_BYTES,
    MODEL,
)
from .llm import fetch_image_bytes, generate_with_retry
from .prompts import (
    BRIEFING_PICKER_SYSTEM,
    GALLERY_VALIDATOR_SYSTEM,
    REFLECTION_CRITIC_SYSTEM,
    REFLECTION_REVISER_SYSTEM,
    SYNTHESIS_ANGLES,
    SYNTHESIS_SYSTEM,
)
from .research import run_research_phase


SECTION_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
HEX_INLINE_RE = re.compile(r"#[0-9a-fA-F]{6}\b")

EVAL_WINNER_RE = re.compile(r"WINNER:\s*([123])", re.IGNORECASE)
EVAL_REASON_RE = re.compile(r"REASON:\s*(.+)", re.DOTALL)

GALLERY_VERDICT_RE = re.compile(r"IMAGE\s*(\d+)\s*:\s*(ok|skip)", re.IGNORECASE)

REFL_NEEDS_RE = re.compile(r"NEEDS_REVISION:\s*(yes|no)", re.IGNORECASE)
REFL_ISSUES_RE = re.compile(r"ISSUES:\s*(.+)", re.DOTALL)


# ---------------------------------------------------------------- briefing parsing


def parse_briefing_sections(text: str) -> dict[str, str]:
    """Parse markdown text into ordered dict of section heading -> body."""
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in (text or "").splitlines():
        m = SECTION_HEADING_RE.match(line)
        if m:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = m.group(1).strip()
            buf = []
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def parse_bullets(body: str) -> list[str]:
    """Parse a markdown bullet list, joining continuation lines into one bullet."""
    bullets: list[str] = []
    for raw in (body or "").splitlines():
        if raw.lstrip().startswith("- "):
            bullets.append(raw.lstrip()[2:].strip())
        elif bullets and raw.strip():
            bullets[-1] += " " + raw.strip()
    return bullets


# ---------------------------------------------------------------- LLM synthesis


async def synthesize(
    season: str,
    target: str,
    agent_outputs: list[dict],
    cross_cutting: list[str] | None = None,
    angle: dict | None = None,
) -> str:
    """Aggregate per-agent reports into one Markdown briefing through one lens."""
    blocks: list[str] = []
    for o in agent_outputs:
        block = f"# {o['name']} Agent\n\n{o['text']}"
        cites = o.get("citations") or []
        if cites:
            urls = "\n".join(f"- {c['title']} ({c['url']})" for c in cites)
            block += f"\n\n**Sources:**\n{urls}"
        blocks.append(block)
    today = date.today().isoformat()
    user = (
        f"Today's date: {today}\n"
        f"Season: {season}\n"
        f"Target group: {target}\n"
        f"Brand: DRYKORN\n\n"
        "Frame the briefing for the relationship between today and the requested season "
        "(upcoming / current / past). Do not blur findings across season boundaries.\n\n"
    )
    if cross_cutting:
        themes_block = "\n".join(f"- {t}" for t in cross_cutting)
        user += (
            "Cross-cutting themes proposed by the planner — give these extra weight if "
            "evidence appears across multiple agents:\n"
            f"{themes_block}\n\n"
        )
    user += "Reports from the research agents:\n\n" + "\n\n".join(blocks)
    system = SYNTHESIS_SYSTEM
    if angle:
        system = system + "\n\n" + angle["instruction"]
    config = types.GenerateContentConfig(system_instruction=system)
    if angle:
        config.temperature = 0.85  # diversity across drafts for Tree of Thought
    response = await generate_with_retry(model=MODEL, contents=user, config=config)
    return response.text or ""


async def pick_best_briefing(
    briefings: list[str], season: str, target: str
) -> tuple[int, str]:
    """Tree-of-Thought picker: choose the strongest among 3 full-briefing drafts."""
    block = "\n\n--- BRIEFING SEPARATOR ---\n\n".join(
        f"BRIEFING {i + 1} ({SYNTHESIS_ANGLES[i]['name']}):\n{b}"
        for i, b in enumerate(briefings)
    )
    user = (
        f"Season: {season}\n"
        f"Target group: {target}\n"
        f"Brand: DRYKORN\n\n"
        f"{block}"
    )
    response = await generate_with_retry(
        model=MODEL,
        contents=user,
        config=types.GenerateContentConfig(system_instruction=BRIEFING_PICKER_SYSTEM),
    )
    text = response.text or ""
    w = EVAL_WINNER_RE.search(text)
    r = EVAL_REASON_RE.search(text)
    winner = int(w.group(1)) - 1 if w else 0
    winner = max(0, min(winner, len(briefings) - 1))
    reason = r.group(1).strip() if r else ""
    return winner, reason


# ---------------------------------------------------------------- reflection


async def reflect_on_briefing(
    briefing: str, season: str, target: str
) -> dict:
    """Day-3 reflection: a critic LLM reads the picked briefing and returns
    {needs_revision: bool, issues: str}. Only one revision pass — no infinite loop."""
    today = date.today().isoformat()
    user = (
        f"Today's date: {today}\n"
        f"Season: {season}\n"
        f"Target group: {target}\n"
        f"Brand: DRYKORN\n\n"
        f"Briefing draft:\n\n{briefing}"
    )
    response = await generate_with_retry(
        model=MODEL,
        contents=user,
        config=types.GenerateContentConfig(system_instruction=REFLECTION_CRITIC_SYSTEM),
    )
    text = response.text or ""
    n = REFL_NEEDS_RE.search(text)
    i = REFL_ISSUES_RE.search(text)
    needs = bool(n and n.group(1).lower() == "yes")
    issues = i.group(1).strip() if i else ""
    return {"needs_revision": needs, "issues": issues}


async def revise_briefing(
    briefing: str, issues: str, season: str, target: str
) -> str:
    """Re-write the briefing addressing the critic's issues. One pass only."""
    today = date.today().isoformat()
    user = (
        f"Today's date: {today}\n"
        f"Season: {season}\n"
        f"Target group: {target}\n"
        f"Brand: DRYKORN\n\n"
        f"Editor's flagged issues:\n{issues}\n\n"
        f"Current briefing draft to revise:\n\n{briefing}"
    )
    response = await generate_with_retry(
        model=MODEL,
        contents=user,
        config=types.GenerateContentConfig(system_instruction=REFLECTION_REVISER_SYSTEM),
    )
    return response.text or briefing


# ---------------------------------------------------------------- image collection


def collect_gallery_images(agent_outputs: list[dict]) -> list[str]:
    """All og:image URLs from all agents, deduped, in agent order, capped pre-validation."""
    urls: list[str] = []
    seen: set[str] = set()
    for out in agent_outputs:
        for c in out.get("citations") or []:
            img = c.get("image")
            if img and img not in seen:
                seen.add(img)
                urls.append(img)
                if len(urls) >= GALLERY_PRE_VALIDATION_CAP:
                    return urls
    return urls


async def _validate_gallery(
    briefing: str, target: str, urls: list[str]
) -> list[str]:
    """Single multimodal pass: load image bytes in parallel, send all of them
    plus the briefing and target group to Gemini, keep only those tagged `ok`.
    Bot-blocked URLs that won't load drop out automatically. Target group is
    explicit so the validator's gender-filter has a reliable signal even if
    the briefing prose doesn't mention it verbatim."""
    if not urls:
        return []

    blob_results = await asyncio.gather(
        *(fetch_image_bytes(u, MAX_IMAGE_BYTES) for u in urls)
    )
    loaded: list[tuple[str, bytes, str]] = []
    for url, blob in zip(urls, blob_results):
        if blob is None:
            continue
        data, mime = blob
        loaded.append((url, data, mime))

    if not loaded:
        return []

    parts: list = [types.Part.from_text(text=(
        f"Target group: {target}\n\n"
        f"Briefing:\n\n{briefing}\n\n"
        f"Candidate images ({len(loaded)} total):"
    ))]
    for label_idx, (_url, data, mime) in enumerate(loaded, start=1):
        parts.append(types.Part.from_text(text=f"\nIMAGE {label_idx}:"))
        parts.append(types.Part.from_bytes(data=data, mime_type=mime))

    response = await generate_with_retry(
        model=MODEL,
        contents=parts,
        config=types.GenerateContentConfig(system_instruction=GALLERY_VALIDATOR_SYSTEM),
    )
    text = response.text or ""

    verdicts: dict[int, bool] = {}
    for m in GALLERY_VERDICT_RE.finditer(text):
        label_idx = int(m.group(1))
        verdicts[label_idx] = m.group(2).lower() == "ok"

    accepted: list[str] = []
    for label_idx, (url, _data, _mime) in enumerate(loaded, start=1):
        if verdicts.get(label_idx, True):  # default ok if model omitted
            accepted.append(url)
            if len(accepted) >= GALLERY_FINAL_CAP:
                break
    return accepted


# ---------------------------------------------------------------- top-level synthesis phase


async def run_synthesis_phase(
    season: str,
    target: str,
    outputs: list[dict],
    cross_cutting: list[str] | None = None,
) -> tuple[str, dict]:
    """Phase 2: Tree-of-Thought synthesis (3 drafts -> picker) + image collection.

    Returns (winning_briefing, tot_info)."""
    draft_tasks = [
        asyncio.create_task(
            synthesize(season, target, outputs, cross_cutting, angle=angle)
        )
        for angle in SYNTHESIS_ANGLES
    ]
    drafts = await asyncio.gather(*draft_tasks)

    winner_idx, reason = await pick_best_briefing(drafts, season, target)
    briefing = drafts[winner_idx]

    # Reflection: critic reads the picked briefing; if issues, one revision pass.
    reflection = await reflect_on_briefing(briefing, season, target)
    revised_briefing: str | None = None
    if reflection["needs_revision"] and reflection["issues"]:
        revised_briefing = await revise_briefing(
            briefing, reflection["issues"], season, target
        )
        briefing = revised_briefing

    candidate_gallery = collect_gallery_images(outputs)
    gallery_images = await _validate_gallery(briefing, target, candidate_gallery)

    tot_info = {
        "drafts": drafts,
        "winner_idx": winner_idx,
        "reason": reason,
        "angle_names": [a["name"] for a in SYNTHESIS_ANGLES],
        "gallery_images": gallery_images,
        "gallery_validation": {
            "candidates": len(candidate_gallery),
            "accepted": len(gallery_images),
        },
        "reflection": {
            "needs_revision": reflection["needs_revision"],
            "issues": reflection["issues"],
            "revised": revised_briefing is not None,
        },
    }
    return briefing, tot_info


async def run_briefing(
    season: str,
    target: str,
    on_agent_done: Callable[[str, float, dict], None],
    agent_specs: list[tuple[str, str, list[str] | None]],
    cross_cutting: list[str] | None = None,
    max_rounds: int = MAX_AGENT_ROUNDS,
) -> tuple[str, list[dict], dict]:
    """Top-level pipeline: research phase → synthesis phase."""
    outputs = await run_research_phase(
        season, target, agent_specs, on_agent_done, max_rounds=max_rounds
    )
    briefing, tot_info = await run_synthesis_phase(
        season, target, outputs, cross_cutting
    )
    return briefing, outputs, tot_info
