"""Mail-Agent: drafts personalized follow-up emails after a briefing,
plus a HITL-gated send function.

The LLM call writes one email per recipient, tailored to their role. The
user reviews and edits the drafts in the UI before triggering send.

`send_smtp_emails` auto-detects whether SMTP credentials are configured
in the environment:
  - If `SMTP_USER` and `SMTP_PASSWORD` are set, emails are sent for real
    via the configured host (default: smtp.gmail.com:587, STARTTLS)
  - Otherwise the function returns a `mode="dummy"` summary without
    contacting any server — same code path, no surprises

For Gmail, `SMTP_PASSWORD` must be a 16-char App Password generated under
Google Account → Security → App passwords (2FA must be enabled). The
regular Gmail password will not work.
"""
from __future__ import annotations

import json
import os
import re
import smtplib
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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
    brand_profile_block: str = "",
    tones_block: str = "",
) -> list[MailDraft]:
    """One LLM call drafts a personalized email per recipient. Returns a list
    of {email, subject, body} dicts in the same order as the recipients input.

    The optional `brand_profile_block` and `tones_block` are long-term memory
    injected into the user prompt so emails carry the brand's voice and the
    user's role-specific tone preferences.

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
    )
    if brand_profile_block:
        user += f"{brand_profile_block}\n\n"
    if tones_block:
        user += f"{tones_block}\n\n"
    user += (
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


def send_smtp_emails(
    drafts: list[MailDraft],
    pdf_bytes: bytes | None = None,
    pdf_filename: str = "briefing.pdf",
) -> dict:
    """Send the drafted emails via SMTP, or fall back to a dummy summary
    if no credentials are configured.

    If `pdf_bytes` is provided, the same PDF is attached to every email
    sent — used to ship the full briefing alongside the personalized
    summary text. The dummy path ignores the attachment.

    Required env-vars to enable real sending:
      SMTP_USER       — sender email address (e.g. you@gmail.com)
      SMTP_PASSWORD   — Gmail app password or provider equivalent

    Optional env-vars (defaults shown):
      SMTP_FROM       — From-header (default: SMTP_USER)
      SMTP_HOST       — server hostname (default: smtp.gmail.com)
      SMTP_PORT       — 587 = STARTTLS (default), 465 = SMTPS

    Returns a dict with `mode` ('smtp' or 'dummy'), `count`, `recipients`,
    `sent_at`, `note`, and `attachment` (bool). Raises on hard SMTP failures
    (auth error, connection refused, etc.) so the UI can show a meaningful
    error."""
    user = (os.environ.get("SMTP_USER") or "").strip()
    pw = (os.environ.get("SMTP_PASSWORD") or "").strip()
    sent_at = datetime.now().isoformat(timespec="seconds")
    recipients = [(d.get("email") or "").strip() for d in drafts]
    has_attachment = bool(pdf_bytes)

    if not user or not pw:
        return {
            "mode": "dummy",
            "sent_at": sent_at,
            "count": len(drafts),
            "recipients": recipients,
            "attachment": has_attachment,
            "note": "SMTP_USER / SMTP_PASSWORD not set — no real emails sent",
        }

    sender = (os.environ.get("SMTP_FROM") or user).strip()
    host = (os.environ.get("SMTP_HOST") or "smtp.gmail.com").strip()
    port = int((os.environ.get("SMTP_PORT") or "587").strip())

    sent_count = 0
    with smtplib.SMTP(host, port, timeout=15) as srv:
        srv.ehlo()
        srv.starttls()
        srv.ehlo()
        srv.login(user, pw)
        for d in drafts:
            recipient = (d.get("email") or "").strip()
            if not recipient:
                continue
            msg = MIMEMultipart()
            msg["From"] = sender
            msg["To"] = recipient
            msg["Subject"] = (d.get("subject") or "(no subject)").strip()
            msg.attach(MIMEText((d.get("body") or "").strip(), "plain", "utf-8"))
            if pdf_bytes:
                attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
                attachment.add_header(
                    "Content-Disposition", "attachment", filename=pdf_filename,
                )
                msg.attach(attachment)
            srv.sendmail(sender, [recipient], msg.as_string())
            sent_count += 1

    return {
        "mode": "smtp",
        "sent_at": sent_at,
        "count": sent_count,
        "recipients": recipients,
        "attachment": has_attachment,
        "note": f"sent via {host}",
    }
