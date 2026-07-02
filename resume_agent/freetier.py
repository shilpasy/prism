"""
Free-tier gate: lets visitors try Prism without their own OpenAI key,
while capping the owner's total spend with a hard global daily limit.

The owner sets their key as PRISM_FREE_KEY on the server. A global counter
(persisted to disk) tracks total free runs per day across ALL visitors.
Once the daily cap is reached, the app falls back to bring-your-own-key.

Two limits work together:
  - per-session cap: each visitor gets a few free runs (best-effort; resets on refresh)
  - global daily cap: hard ceiling across ALL visitors — the real spend protector

Environment variables:
  PRISM_FREE_KEY           the owner's OpenAI key used for free runs (unset = no free tier)
  PRISM_DAILY_FREE_LIMIT   max free runs per day across all users (default 10, ~$1/day)
  PRISM_FREE_PER_SESSION   max free runs per browser session (default 2)
  PRISM_FREE_COUNTER       path to the counter file (default /tmp/prism_free_counter.json)
"""
from __future__ import annotations
import json
import os
import threading
from datetime import date
from pathlib import Path

_LOCK = threading.Lock()


def _store_path() -> Path:
    return Path(os.getenv("PRISM_FREE_COUNTER", "/tmp/prism_free_counter.json"))


def _daily_limit() -> int:
    try:
        return int(os.getenv("PRISM_DAILY_FREE_LIMIT", "10"))
    except ValueError:
        return 10


def per_session_limit() -> int:
    """Max free runs per browser session (best-effort; resets on refresh)."""
    try:
        return int(os.getenv("PRISM_FREE_PER_SESSION", "2"))
    except ValueError:
        return 2


def free_key() -> str:
    """The owner-funded key, or empty string if no free tier is configured."""
    return os.getenv("PRISM_FREE_KEY", "").strip()


def _load() -> dict:
    try:
        return json.loads(_store_path().read_text())
    except Exception:
        return {"date": "", "count": 0}


def _save(data: dict) -> None:
    try:
        _store_path().write_text(json.dumps(data))
    except Exception:
        pass  # ephemeral counter — best-effort only


def free_status() -> tuple[int, int, int]:
    """Return (used_today, daily_limit, remaining)."""
    with _LOCK:
        data = _load()
        today = date.today().isoformat()
        if data.get("date") != today:
            data = {"date": today, "count": 0}
            _save(data)
        limit = _daily_limit()
        used = data.get("count", 0)
        return used, limit, max(0, limit - used)


def free_available() -> bool:
    """True if a free-tier key is configured AND today's cap isn't exhausted."""
    if not free_key():
        return False
    _, _, remaining = free_status()
    return remaining > 0


def record_free_use(n: int = 1) -> int:
    """Increment today's counter. Call once per expensive free run. Returns new count."""
    with _LOCK:
        data = _load()
        today = date.today().isoformat()
        if data.get("date") != today:
            data = {"date": today, "count": 0}
        data["count"] = data.get("count", 0) + n
        _save(data)
        return data["count"]
