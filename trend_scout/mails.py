"""Mail-Agent: drafts personalized follow-up emails after a briefing,
plus a strictly-isolated dummy send function gated behind a HITL approval.

The LLM call writes one email per recipient, tailored to their role. The
user reviews and edits the drafts in the UI before triggering the send
action. `send_smtp_emails` is a no-op stub so the agent can be wired into
the UI safely — replacing it with a real SMTP client is the only change
needed to go live.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import TypedDict

from google.genai import types

from .config import MODEL
from .llm import generate_with_retry
from .prompts import MAIL_AGENT_SYSTEM


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Recipient(TypedDict):
    email: str
    name: str
    role: str


class MailDraft(TypedDict):
    email: str
    subject: str
    body: str


def is_valid_email(addr: str) -> bool:
    """Format-only check, no DNS/MX validation."""
    return bool(_EMAIL_RE.match((addr or "").strip()))


async def draft_emails(
    *,
    briefing: str,
    season: str,
    target: str,
    language: str,
    recipients: list[Recipient],
) -> list[MailDraft]:
    """One LLM call drafts a personalized email per recipient. Returns a list
    of {email, subject, body} dicts in the same order as the recipients input.

    Failures (network, JSON parse) raise — the caller handles them with a
    UI error message; we don't silently fall through, because the user is
    expecting to send something."""
    if not recipients:
        return []

    recipient_block = "\n".join(
        f"- email: {r['email']}, name: {r['name'] or '(no name given)'}, "
        f"role: {r['role'] or '(no role given)'}"
        for r in recipients
    )
    user = (
        f"Season: {season}\n"
        f"Target group: {target}\n"
        f"Output language: {language}\n\n"
        f"Recipients:\n{recipient_block}\n\n"
        f"Briefing to summarize for each recipient:\n\n{briefing}"
    )
    response = await generate_with_retry(
        model=MODEL,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=MAIL_AGENT_SYSTEM,
            temperature=0.4,
            response_mime_type="application/json",
        ),
    )
    text = (response.text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()

    try:
        parsed = json.loads(text)
    except Exception as e:
        raise ValueError(f"Mail agent returned non-JSON output: {e}") from e

    if not isinstance(parsed, list):
        raise ValueError("Mail agent did not return a JSON array.")

    out: list[MailDraft] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        out.append({
            "email": str(item.get("email", "")).strip(),
            "subject": str(item.get("subject", "")).strip(),
            "body": str(item.get("body", "")).strip(),
        })

    # If the model dropped some recipients (rare), align by index — the user
    # can edit anything that ended up empty.
    while len(out) < len(recipients):
        out.append({
            "email": recipients[len(out)]["email"],
            "subject": "",
            "body": "",
        })
    return out[: len(recipients)]


def send_smtp_emails(drafts: list[MailDraft]) -> dict:
    """DUMMY — no real SMTP client wired in. Returns a summary dict so the
    caller can show a confirmation. The only thing that should ever change
    here is to point at a real SMTP / API client; everything upstream
    (drafting, HITL review, approval) stays as-is.

    Audit-friendly: returns the recipient list and timestamp so the caller
    can persist a record of the action."""
    sent_at = datetime.now().isoformat(timespec="seconds")
    return {
        "sent_at": sent_at,
        "count": len(drafts),
        "recipients": [d.get("email", "") for d in drafts],
        "note": "dummy send — no real SMTP wired in",
    }
