"""Persistent briefing history under ~/.trend-scout/history/.

Each briefing run is JSON-dumped with full state (briefing, agent outputs,
tot_info, run_stats, plan, enabled_agents). The pre-built PDF lives next
to it as a separate binary file (`<run_id>.pdf`) so the JSON stays compact
and reload-from-history is instant — no PDF re-build, no image re-fetch.

Sidebar lists past runs and reloads them. The cache lookup matches directly
on the canonicalized fields (season, target, mode) — robust to schema
changes in input_hash and to records saved before mode-tracking existed.
The stored `input_hash` is kept for forensics / debugging only, not used
for matching.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path


HISTORY_DIR = Path.home() / ".trend-scout" / "history"


def _slug(text: str) -> str:
    """Filesystem-safe slug, lowercase ASCII."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return s[:60] or "untitled"


def compute_input_hash(season: str, target: str, mode: str) -> str:
    """Stable hash over the inputs the user actually controls before the
    pipeline runs: season, target, and the speed/quality mode. The plan
    (research angles) is intentionally NOT in the hash — the planner is
    non-deterministic, so including it would bust the cache on every
    repeat run with identical inputs. Custom agents skip the cache entirely
    in the caller."""
    payload = {
        "season": season.strip().lower(),
        "target": target.strip().lower(),
        "mode": mode.strip().lower(),
    }
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def save_run(
    *,
    season: str,
    target: str,
    briefing: str,
    outputs: list[dict],
    tot_info: dict,
    run_stats: dict,
    plan: dict,
    enabled_agents: list[str],
    input_hash: str,
    pdf_bytes: bytes | None = None,
) -> str:
    """Dump a run to disk. Returns the run id (filename stem).

    If `pdf_bytes` is provided, also writes `<run_id>.pdf` next to the JSON
    so reload-from-history can serve the same PDF without rebuilding."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"{ts}_{_slug(season)}_{_slug(target)}"
    record = {
        "id": run_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "input_hash": input_hash,
        "season": season,
        "target": target,
        "briefing": briefing,
        "outputs": outputs,
        "tot_info": tot_info,
        "run_stats": run_stats,
        "plan": plan,
        "enabled_agents": enabled_agents,
    }
    path = HISTORY_DIR / f"{run_id}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    if pdf_bytes:
        try:
            (HISTORY_DIR / f"{run_id}.pdf").write_bytes(pdf_bytes)
        except Exception:
            pass  # PDF is best-effort, JSON record is what matters
    return run_id


def list_runs(limit: int = 20) -> list[dict]:
    """List recent runs, newest first. Returns a list of meta-dicts (no full
    briefing payload, just enough for a sidebar list)."""
    if not HISTORY_DIR.exists():
        return []
    files = sorted(HISTORY_DIR.glob("*.json"), key=os.path.getmtime, reverse=True)
    out: list[dict] = []
    for p in files[:limit]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            stats = data.get("run_stats") or {}
            out.append({
                "id": data.get("id", p.stem),
                "timestamp": data.get("timestamp", ""),
                "season": data.get("season", ""),
                "target": data.get("target", ""),
                "input_hash": data.get("input_hash", ""),
                "elapsed": stats.get("elapsed", 0),
                "mode": stats.get("mode", ""),
                "agents_count": len(data.get("enabled_agents") or []),
                "sources": stats.get("sources", 0),
            })
        except Exception:
            continue
    return out


def load_run(run_id: str) -> dict | None:
    """Load a full run by id (briefing JSON + sibling PDF if present).
    Returns None if missing or unreadable. The PDF lives in `pdf_bytes`
    on the returned dict and is None for legacy records without one."""
    path = HISTORY_DIR / f"{run_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    pdf_path = HISTORY_DIR / f"{run_id}.pdf"
    if pdf_path.exists():
        try:
            data["pdf_bytes"] = pdf_path.read_bytes()
        except Exception:
            data["pdf_bytes"] = None
    else:
        data["pdf_bytes"] = None
    return data


def find_cached(season: str, target: str, mode: str) -> dict | None:
    """Return the most recent run for (season, target, mode), or None.
    Matches on the canonicalized fields directly — robust to schema changes
    in input_hash and to records that were saved before mode-tracking existed."""
    season_l = season.strip().lower()
    target_l = target.strip().lower()
    mode_l = mode.strip().lower()
    for meta in list_runs(limit=50):
        if (
            meta.get("season", "").strip().lower() == season_l
            and meta.get("target", "").strip().lower() == target_l
            and meta.get("mode", "").strip().lower() == mode_l
        ):
            full = load_run(meta["id"])
            if full:
                return full
    return None


def delete_run(run_id: str) -> bool:
    """Delete the JSON record and any sibling PDF file."""
    deleted = False
    json_path = HISTORY_DIR / f"{run_id}.json"
    if json_path.exists():
        json_path.unlink()
        deleted = True
    pdf_path = HISTORY_DIR / f"{run_id}.pdf"
    if pdf_path.exists():
        try:
            pdf_path.unlink()
        except Exception:
            pass
    return deleted
