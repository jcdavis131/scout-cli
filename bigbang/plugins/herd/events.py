"""Per-session telemetry event stream for herd (FOUNDATION Wave F2).

The global ``audit.jsonl`` is coarse (one row per CLI command). This adds a
structured, append-only *session* event stream you own — the granular telemetry
a capability/RFT checkpoint or the arxiviq surface wants — without ever phoning
home. That last point is load-bearing per DIFFERENTIATION.md: telemetry is a
Trust *boundary*, not a product feature. So:

  * events are written ONLY to a local JSONL you own
    (``~/.local/share/bigbang/herd/events.jsonl``);
  * export is **opt-in** and **you choose the sink** — ``export(sink)`` writes a
    rolled-up ``herd_status.json`` to a directory you name (e.g. the arxiviq
    factory's ``reports/`` dir, which its daemon then commits). Scout never
    picks a sink or uploads on its own.

The event envelope matches the shared telemetry shape used by
``ava/trust.py`` and the factory's ``dottie/telemetry.py`` (source-tagged JSONL)
so the three surfaces read as one system.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bigbang.plugins.herd.store import HERD_DIR

EVENTS_FILE = HERD_DIR / "events.jsonl"

SURFACE = "scout.herd"
_SECRET_MARKERS = ("secret", "token", "password", "apikey", "api_key", "credential", "bearer")
_SECRET_EXACT = {"key", "value"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = str(k).lower()
            out[k] = "[REDACTED]" if (lk in _SECRET_EXACT or any(m in lk for m in _SECRET_MARKERS)) else _scrub(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [_scrub(v) for v in obj]
    return obj


def record(
    event_type: str,
    *,
    session_id: Optional[str] = None,
    label: Optional[str] = None,
    status: Optional[str] = None,
    fields: Optional[Dict[str, Any]] = None,
    events_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """Append one session event. Never raises (telemetry must not break a run)."""
    rec = {
        "ts": _now(),
        "surface": SURFACE,
        "event_type": event_type,
        "session": session_id,
        "label": label,
        "status": status,
        "fields": _scrub(fields or {}),
    }
    path = events_file or EVENTS_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass
    return rec


def tail(n: int = 40, events_file: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = events_file or EVENTS_FILE
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for line in lines[-max(1, n):]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def rollup(n: int = 500, events_file: Optional[Path] = None) -> Dict[str, Any]:
    """Aggregate recent events into a compact status doc: counts by event_type
    and status, per-session last state, and the most recent events."""
    events = tail(n, events_file)
    by_type: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    by_session: Dict[str, Dict[str, Any]] = {}
    for e in events:
        by_type[e.get("event_type", "?")] = by_type.get(e.get("event_type", "?"), 0) + 1
        st = e.get("status")
        if st:
            by_status[st] = by_status.get(st, 0) + 1
        sid = e.get("session")
        if sid:
            by_session[sid] = {"label": e.get("label"), "status": e.get("status"),
                               "event_type": e.get("event_type"), "ts": e.get("ts")}
    return {
        "surface": SURFACE,
        "generated_at": _now(),
        "total_events": len(events),
        "by_event_type": by_type,
        "by_status": by_status,
        "sessions": by_session,
        "recent": events[-12:],
        "disclaimer": "Solo personal project; local telemetry only, never phoned home",
    }


def export(sink: Path, *, events_file: Optional[Path] = None) -> Path:
    """Opt-in LOCAL export: write a rolled-up ``herd_status.json`` into the
    ``sink`` directory the caller chose. Returns the path written.

    This is the ONLY way herd telemetry leaves its local JSONL, and the caller
    always names the sink — pointed at the arxiviq factory's ``reports/`` dir it
    rides that repo's existing git-push daemon onto the branch arxiviq reads."""
    sink = Path(sink).expanduser()
    sink.mkdir(parents=True, exist_ok=True)
    out = sink / "herd_status.json"
    out.write_text(json.dumps(rollup(events_file=events_file), indent=2, ensure_ascii=False),
                   encoding="utf-8")
    return out
