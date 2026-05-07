"""Gemini client + retry wrapper + grounding-citation extraction +
OG-image enrichment + input guardrail."""
from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import urlparse

import httpx
from google import genai
from google.genai import types

from .prompts import INPUT_VALIDATOR_SYSTEM


_client: genai.Client | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def get_client() -> genai.Client:
    """Return a genai.Client cached per event-loop. Streamlit calls
    `asyncio.run()` multiple times across the page lifecycle (planner, then
    briefing); each call creates a fresh loop, but `genai.Client` binds its
    internal httpx pool to the loop active at first use. Reusing the client
    across loops crashes with `Event loop is closed` on Windows. Re-init
    when we detect a loop switch."""
    global _client, _client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    if _client is None or _client_loop is not current_loop:
        _client = genai.Client()
        _client_loop = current_loop
    return _client


async def generate_with_retry(
    *,
    model: str,
    contents,
    config,
    max_retries: int = 4,
    base_delay: float = 1.5,
):
    """Wrap generate_content with exponential-backoff retry on transient errors
    (503, UNAVAILABLE, overloaded, DEADLINE_EXCEEDED). Quota errors (429) are
    NOT retried since they need user action (project switch, daily reset)."""
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return await get_client().aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as e:
            last_exc = e
            err = str(e).upper()
            transient = (
                "503" in err
                or "OVERLOADED" in err
                or "UNAVAILABLE" in err
                or "DEADLINE_EXCEEDED" in err
                or ("INTERNAL" in err and "ERROR" in err)
            )
            if not transient or attempt >= max_retries - 1:
                raise
            await asyncio.sleep(base_delay * (2 ** attempt))
    if last_exc:
        raise last_exc


def extract_citations(response) -> list[dict]:
    citations: list[dict] = []
    seen: set[str] = set()
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return citations
    metadata = getattr(candidates[0], "grounding_metadata", None)
    if not metadata:
        return citations
    for chunk in getattr(metadata, "grounding_chunks", None) or []:
        web = getattr(chunk, "web", None)
        if not web:
            continue
        uri = getattr(web, "uri", "") or ""
        if not uri or uri in seen:
            continue
        seen.add(uri)
        citations.append({"title": getattr(web, "title", "") or uri, "url": uri})
    return citations


def domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return url


_OG_IMAGE_PATTERNS = [
    r'<meta[^>]+?property=["\']og:image(?::secure_url)?["\'][^>]+?content=["\']([^"\']+)["\']',
    r'<meta[^>]+?content=["\']([^"\']+)["\'][^>]+?property=["\']og:image(?::secure_url)?["\']',
    r'<meta[^>]+?name=["\']twitter:image["\'][^>]+?content=["\']([^"\']+)["\']',
    r'<meta[^>]+?content=["\']([^"\']+)["\'][^>]+?name=["\']twitter:image["\']',
]

_OG_TITLE_PATTERNS = [
    r'<meta[^>]+?property=["\']og:title["\'][^>]+?content=["\']([^"\']+)["\']',
    r'<meta[^>]+?content=["\']([^"\']+)["\'][^>]+?property=["\']og:title["\']',
    r'<meta[^>]+?name=["\']twitter:title["\'][^>]+?content=["\']([^"\']+)["\']',
    r"<title>([^<]+)</title>",
]

# Filter out likely-low-quality images (logos, sprites, favicons, placeholders).
_IMG_SKIP_RE = re.compile(
    r"logo|favicon|sprite|placeholder|default[-_]?image|icon[-_/]|/icons?/|"
    r"\.svg(?:\?|$)|share[-_]?image|opengraph[-_]?default",
    re.IGNORECASE,
)


_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 TrendScout/1.0"
    )
}


def _resolve_image_url(img: str, page_url: str) -> str | None:
    img = img.strip()
    if not img:
        return None
    if _IMG_SKIP_RE.search(img):
        return None
    if img.startswith("//"):
        return "https:" + img
    if img.startswith("/"):
        p = urlparse(page_url)
        return f"{p.scheme}://{p.netloc}{img}"
    return img


async def _fetch_og(
    url: str, client: httpx.AsyncClient
) -> tuple[str, str | None, str | None]:
    """Fetch a page and extract its og:image + og:title.
    The og:title is typically much more descriptive than what Gemini's
    grounding metadata returns ("Vogue" → "Khaite Pre-Fall 2026 - Vogue") and
    enables much better brand-name matching downstream."""
    try:
        r = await client.get(url, timeout=6.0, follow_redirects=True)
        final_url = str(r.url)
        if r.status_code >= 400:
            return final_url, None, None
        html = r.text[:80_000]
        og_image: str | None = None
        for pat in _OG_IMAGE_PATTERNS:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                resolved = _resolve_image_url(m.group(1), final_url)
                if resolved:
                    og_image = resolved
                    break
        og_title: str | None = None
        for pat in _OG_TITLE_PATTERNS:
            m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
            if m:
                t = m.group(1).strip()
                t = t.replace("&amp;", "&").replace("&#x27;", "'").replace("&apos;", "'")
                if t:
                    og_title = t[:200]
                    break
        return final_url, og_image, og_title
    except Exception:
        return url, None, None


async def enrich_citations(citations: list[dict]) -> list[dict]:
    """Attach og:image + og:title to each citation. Returns a new list."""
    if not citations:
        return citations
    async with httpx.AsyncClient(headers=_BROWSER_HEADERS) as client:
        results = await asyncio.gather(*(_fetch_og(c["url"], client) for c in citations))
    enriched: list[dict] = []
    for c, (final_url, img, og_title) in zip(citations, results):
        original_title = c.get("title") or ""
        merged_title = (
            f"{og_title} | {original_title}"
            if og_title and og_title != original_title
            else (og_title or original_title)
        )
        enriched.append({**c, "url": final_url, "image": img, "title": merged_title})
    return enriched


async def validate_input(season: str, target: str, model: str) -> dict:
    """Day-3 input guardrail: ask a small LLM-judge to decide whether the
    user-supplied (season, target) pair is a legitimate fashion-research
    request before we burn the multi-agent pipeline on it.

    Returns {"valid": bool, "reason": str}. Network or parsing failures
    fail OPEN (valid=True) — the guardrail is best-effort, not a hard gate."""
    user = (
        f"season: {season!r}\n"
        f"target group: {target!r}"
    )
    try:
        response = await generate_with_retry(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=INPUT_VALIDATOR_SYSTEM,
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
    except Exception:
        return {"valid": True, "reason": ""}

    text = (response.text or "").strip()
    if text.startswith("```"):
        # Strip accidental markdown fences if the model added them.
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(text)
    except Exception:
        return {"valid": True, "reason": ""}

    return {
        "valid": bool(parsed.get("valid", True)),
        "reason": str(parsed.get("reason", "")).strip(),
    }


async def fetch_image_bytes(url: str, max_bytes: int) -> tuple[bytes, str] | None:
    """Download an image with a hard byte cap. Returns (data, mime_type) or None.
    Used by the moodboard validator to pass image bytes to the multimodal LLM."""
    try:
        async with httpx.AsyncClient(headers=_BROWSER_HEADERS) as client:
            r = await client.get(url, timeout=4.0, follow_redirects=True)
            if r.status_code >= 400:
                return None
            data = r.content
            if not data or len(data) > max_bytes:
                return None
            mime = r.headers.get("content-type", "").split(";")[0].strip().lower()
            if not mime.startswith("image/"):
                return None
            if mime not in {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}:
                return None
            return data, mime
    except Exception:
        return None
