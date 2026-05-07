"""Persistent briefing history under ~/.trend-scout/history/.

Each briefing run is JSON-dumped with full state (briefing, agent outputs,
tot_info, run_stats, plan). Sidebar can list past runs and reload them; the
cache lookup uses a hash over (season, target, agent_specs) to detect repeat
queries and serve the previous briefing without re-hitting the API.
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


def compute_input_hash(
    season: str,
    target: str,
    agent_specs: list[tuple[str, str, list[str] | None]],
) -> str:
    """Stable hash over the user-controlled inputs that decide a run's outcome.
    Custom-agent prompts and per-agent query lists are included so editing
    them invalidates the cache; the season+target alone aren't enough."""
    payload = {
        "season": season.strip().lower(),
        "target": target.strip().lower(),
        "agents": [
            {"name": n, "prompt": p, "queries": list(q or [])}
            for n, p, q in agent_specs
        ],
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
) -> str:
    """Dump a run to disk. Returns the run id (filename stem)."""
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
            out.append({
                "id": data.get("id", p.stem),
                "timestamp": data.get("timestamp", ""),
                "season": data.get("season", ""),
                "target": data.get("target", ""),
                "input_hash": data.get("input_hash", ""),
                "elapsed": (data.get("run_stats") or {}).get("elapsed", 0),
            })
        except Exception:
            continue
    return out


def load_run(run_id: str) -> dict | None:
    """Load a full run by id. Returns None if missing or unreadable."""
    path = HISTORY_DIR / f"{run_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def find_cached(input_hash: str) -> dict | None:
    """Return the most recent run whose input_hash matches, or None."""
    for meta in list_runs(limit=50):
        if meta.get("input_hash") == input_hash:
            full = load_run(meta["id"])
            if full:
                return full
    return None


def delete_run(run_id: str) -> bool:
    path = HISTORY_DIR / f"{run_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False
