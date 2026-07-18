"""Live bridge to the Herdr multiplexer (herdr.dev).

This is the piece FOUNDATION.md/DIFFERENTIATION.md always intended but hadn't
built: `scout herd` used to only `shutil.which("herdr")` and print pairing
prose, and the session field ``herdr_pane`` was never populated. This module
actually talks to a real Herdr binary — reading pane/agent state and letting a
Scout session record the pane it maps to — WITHOUT Scout becoming a multiplexer.
Scout stays the judgment/ledger/policy plane; Herdr owns the PTY panes.

Design rule: **offline-safe**. herdr may not be installed (it isn't on Windows
beta boxes), so every function returns a structured result — never raises, never
hangs (short timeouts) — and the whole `herd` plugin works with or without it.

Herdr exposes a CLI (`herdr <group> <verb> --json`) and an NDJSON socket API;
`herdr api schema --json` is the authoritative protocol for the installed
binary. We drive the CLI here (the shape Herdr's own docs recommend starting
with) and parse defensively because the exact JSON payloads are versioned.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional

HERDR_DOCS = "https://herdr.dev/docs/"
_DEFAULT_TIMEOUT = 4.0


def herdr_path() -> Optional[str]:
    """Absolute path to the herdr binary, or None if not installed."""
    return shutil.which("herdr")


def _parse_json(text: str) -> Optional[Any]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        # NDJSON / multi-object output: try the last complete line
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except Exception:
                continue
    return None


def _run(args: List[str], *, timeout: float = _DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Run `herdr <args>` and return a structured result. Never raises."""
    path = herdr_path()
    if not path:
        return {"available": False, "reason": "herdr not installed", "docs": HERDR_DOCS}
    try:
        proc = subprocess.run(
            [path, *args],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ},
        )
    except subprocess.TimeoutExpired:
        return {"available": True, "ok": False, "reason": f"herdr {' '.join(args)} timed out"}
    except Exception as exc:  # pragma: no cover - defensive
        return {"available": True, "ok": False, "reason": f"{type(exc).__name__}: {exc}"}
    if proc.returncode != 0:
        return {"available": True, "ok": False,
                "reason": (proc.stderr or "").strip()[:400] or f"exit {proc.returncode}"}
    data = _parse_json(proc.stdout)
    return {"available": True, "ok": True, "data": data if data is not None else proc.stdout.strip()}


def _normalize_agents(data: Any) -> List[Dict[str, Any]]:
    """Coerce Herdr's (versioned) agent/pane listing into a stable shape:
    ``[{pane_id, agent, state}]``. Accepts a bare list, {agents:[...]},
    {panes:[...]}, or {result:{...}}; unknown fields are ignored."""
    if isinstance(data, dict):
        for key in ("agents", "panes", "result", "data", "items"):
            if key in data:
                return _normalize_agents(data[key])
        # a single object
        data = [data]
    if not isinstance(data, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        pane = item.get("pane_id") or item.get("paneId") or item.get("id") or item.get("pane")
        agent = item.get("agent") or item.get("agent_name") or item.get("name") or item.get("kind")
        state = (item.get("agent_status") or item.get("state") or item.get("status")
                 or item.get("value") or "unknown")
        out.append({"pane_id": pane, "agent": agent, "state": state})
    return out


def bridge_status() -> Dict[str, Any]:
    """Is a real Herdr bridge live? Reports installed/version/schema-capable and
    the pane/agent count, or a clean not-installed result."""
    path = herdr_path()
    if not path:
        return {"available": False, "installed": False, "reason": "herdr not installed",
                "docs": HERDR_DOCS}
    ver = _run(["--version"], timeout=2.0)
    agents = list_agents()
    return {
        "available": True,
        "installed": True,
        "path": path,
        "version": ver.get("data") if ver.get("ok") else None,
        "schema_capable": _run(["api", "schema", "--json"], timeout=2.0).get("ok", False),
        "agent_panes": len(agents.get("agents", [])) if agents.get("ok") else 0,
        "docs": HERDR_DOCS,
    }


def list_agents() -> Dict[str, Any]:
    """Normalized `[{pane_id, agent, state}]` of Herdr agent panes, or an
    offline result. Tries `herdr agent list --json`."""
    res = _run(["agent", "list", "--json"])
    if not res.get("available"):
        return {"ok": False, "available": False, "reason": res.get("reason"), "agents": []}
    if not res.get("ok"):
        return {"ok": False, "available": True, "reason": res.get("reason"), "agents": []}
    return {"ok": True, "available": True, "agents": _normalize_agents(res.get("data"))}


def schema() -> Dict[str, Any]:
    """The authoritative socket-protocol JSON schema from the installed binary
    (`herdr api schema --json`), or an offline note."""
    return _run(["api", "schema", "--json"], timeout=3.0)


def pairing_notes() -> Dict[str, Any]:
    """Static guidance on running Scout herd alongside Herdr — the two-plane
    split. Kept for the offline case and as human documentation."""
    return {
        "herdr": "PTY panes, mouse layout, remote attach, agent sidebar (WHERE agents live)",
        "scout_herd": "JSON ledger, wait/read/report, tools/MCP/Ava routing, policy (HOW they're driven)",
        "suggested_flow": [
            "herdr                                   # attach the multiplexer",
            "scout herd create --label api --cwd ~/project",
            'scout herd start api --cmd "claude"     # or launch the agent inside a herdr pane',
            "scout herd attach api --pane <pane_id>  # map the Scout session to the real pane",
            "scout --json herd bridge                # live pane/agent state from Herdr",
            "scout --json herd wait api --status done",
        ],
    }
