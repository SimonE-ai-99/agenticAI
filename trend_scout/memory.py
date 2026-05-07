"""Long-term memory for Trend Scout — brand profile, mail tones, agent library.

Three optional JSON files under ~/.trend-scout/:
  profile.json     — single brand-identity profile (positioning, dos/donts, …)
  mail_tones.json  — per-role tone profiles for the mail agent
  agents.json      — saved custom agents (domain + prompt + suggested angles)

Each loader degrades gracefully: if the file is missing or malformed, returns
None / empty list — the rest of the pipeline keeps working as before. The
streamlit shell reads these at run-start and injects them into the prompts
that need them (synthesis / reflection / mail-agent / agent-generator).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict


MEMORY_DIR = Path.home() / ".trend-scout"
PROFILE_PATH = MEMORY_DIR / "profile.json"
TONES_PATH = MEMORY_DIR / "mail_tones.json"
AGENTS_LIB_PATH = MEMORY_DIR / "agents.json"


class BrandProfile(TypedDict, total=False):
    name: str
    positioning: str
    target_customer: str
    signature_pieces: str
    color_dna: str
    dos: list[str]
    donts: list[str]
    notes: str


class MailTone(TypedDict, total=False):
    role_match: list[str]   # keywords matched against recipient.role (case-insensitive substring)
    tone: str               # natural-language guidance


class SavedAgent(TypedDict, total=False):
    name: str
    domain: str
    prompt: str
    angles: list[str]


# -------------------------------------------------------------------- helpers


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_json(path: Path, data) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return True
    except Exception:
        return False


# -------------------------------------------------------------------- profile


def load_profile() -> BrandProfile | None:
    data = _load_json(PROFILE_PATH)
    return data if isinstance(data, dict) else None


def save_profile(profile: BrandProfile) -> bool:
    return _save_json(PROFILE_PATH, profile)


def render_profile_for_prompt(profile: BrandProfile | None) -> str:
    """Build the brand-context Markdown block that gets prepended to user
    prompts. Empty string if no profile / all fields blank."""
    if not profile:
        return ""
    parts: list[str] = []
    name = (profile.get("name") or "").strip()
    if name:
        parts.append(f"Brand: **{name}**")
    if (profile.get("positioning") or "").strip():
        parts.append(f"Positioning: {profile['positioning'].strip()}")
    if (profile.get("target_customer") or "").strip():
        parts.append(f"Target customer: {profile['target_customer'].strip()}")
    if (profile.get("signature_pieces") or "").strip():
        parts.append(f"Signature pieces: {profile['signature_pieces'].strip()}")
    if (profile.get("color_dna") or "").strip():
        parts.append(f"Color DNA: {profile['color_dna'].strip()}")
    dos = [x.strip() for x in (profile.get("dos") or []) if x.strip()]
    if dos:
        parts.append("Dos:\n" + "\n".join(f"- {x}" for x in dos))
    donts = [x.strip() for x in (profile.get("donts") or []) if x.strip()]
    if donts:
        parts.append("Don'ts:\n" + "\n".join(f"- {x}" for x in donts))
    if (profile.get("notes") or "").strip():
        parts.append(f"Notes: {profile['notes'].strip()}")
    if not parts:
        return ""
    return (
        "Brand profile (long-term memory — apply this lens to every "
        "judgment, theme selection, and tone choice):\n\n"
        + "\n\n".join(parts)
    )


# -------------------------------------------------------------------- tones


def load_tones() -> list[MailTone]:
    data = _load_json(TONES_PATH)
    return data if isinstance(data, list) else []


def save_tones(tones: list[MailTone]) -> bool:
    return _save_json(TONES_PATH, tones)


def render_tones_block(tones: list[MailTone]) -> str:
    """Markdown block for the mail-agent prompt — lists role→tone mappings."""
    if not tones:
        return ""
    lines: list[str] = []
    for t in tones:
        kws = [k.strip() for k in (t.get("role_match") or []) if k.strip()]
        tone = (t.get("tone") or "").strip()
        if kws and tone:
            lines.append(f"- If recipient role contains any of [{', '.join(kws)}]: {tone}")
    if not lines:
        return ""
    return (
        "Tone profiles (apply per recipient — match keywords against the "
        "recipient's role; first match wins, fall back to the role-class "
        "defaults in the system prompt if no keyword matches):\n"
        + "\n".join(lines)
    )


# -------------------------------------------------------------------- agent library


def load_agent_library() -> list[SavedAgent]:
    data = _load_json(AGENTS_LIB_PATH)
    return data if isinstance(data, list) else []


def save_agent_library(agents: list[SavedAgent]) -> bool:
    return _save_json(AGENTS_LIB_PATH, agents)
