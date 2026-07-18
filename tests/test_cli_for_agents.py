"""Agentability regression tests — cli-for-agents skill."""
from __future__ import annotations

import json
import time

from tests._cli import run_cli as _run


def test_root_help_has_examples():
    r = _run(["--help"])
    assert r.returncode == 0
    assert "Examples:" in r.stdout
    assert "scout --json tools list" in r.stdout


def test_root_version():
    r = _run(["--version"])
    assert r.returncode == 0
    assert "scout-cli" in r.stdout
    j = _run(["--json", "--version"])
    assert j.returncode == 0
    data = json.loads(j.stdout)
    assert data["ok"] is True
    assert data["data"]["version"]


def test_secrets_help_has_examples():
    r = _run(["secrets", "set", "--help"])
    assert r.returncode == 0
    assert "Examples:" in r.stdout
    assert "--stdin" in r.stdout
    assert "--value" in r.stdout


def test_secrets_set_via_stdin_and_get_json():
    key = f"AGENT_TEST_{int(time.time())}"
    r = _run(["secrets", "set", key, "--stdin"], input_text="super-secret-value\n")
    assert r.returncode == 0, r.stderr
    r2 = _run(["--json", "secrets", "get", key])
    assert r2.returncode == 0, r2.stderr + r2.stdout
    data = json.loads(r2.stdout)
    assert data["ok"] is True
    assert data["data"]["value"] == "super-secret-value"
    # cleanup
    _run(["secrets", "rm", key, "--force"])


def test_secrets_rm_dry_run_and_force():
    key = f"AGENT_RM_{int(time.time())}"
    _run(["secrets", "set", key, "--value", "tmp"])
    dry = _run(["--json", "secrets", "rm", key, "--dry-run"])
    assert dry.returncode == 0
    payload = json.loads(dry.stdout)
    assert payload["ok"] is True
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["exists"] is True
    # still present
    assert _run(["--json", "secrets", "get", key]).returncode == 0
    rm = _run(["--json", "secrets", "rm", key, "--force"])
    assert rm.returncode == 0
    body = json.loads(rm.stdout)
    assert body["ok"] is True
    assert body["data"]["removed"] is True


def test_secrets_get_missing_exits_nonzero_with_example():
    r = _run(["--json", "secrets", "get", "definitely_missing_key_zz"])
    assert r.returncode == 1
    data = json.loads(r.stdout)
    assert data.get("ok") is False
    assert "error" in data
    assert "example" in data
    assert "scout secrets set" in data["example"]


def test_auth_set_token_noninteractive_fails_fast():
    """Must not hang waiting for a hidden prompt when stdin is not a TTY."""
    t0 = time.monotonic()
    r = _run(["--json", "auth", "set-token", "_agent_probe_no_token"], timeout=5)
    elapsed = time.monotonic() - t0
    assert elapsed < 4.0, f"hung for {elapsed:.1f}s — interactive prompt leaked"
    assert r.returncode == 1
    data = json.loads(r.stdout)
    assert "error" in data
    assert "example" in data
    assert "--token" in data["example"] or "--stdin" in data["example"]


def test_auth_set_token_stdin():
    svc = f"agentprobe{int(time.time()) % 100000}"
    r = _run(["--json", "auth", "set-token", svc, "--stdin"], input_text="tok_abc\n")
    assert r.returncode == 0, r.stderr + r.stdout
    data = json.loads(r.stdout)
    assert data.get("service") == svc or data.get("status") == "ok" or "vault_key" in data
    # logout cleanup
    _run(["auth", "logout", svc, "--delete-vault", "--force"])


def test_auth_logout_dry_run():
    r = _run(["--json", "auth", "logout", "nosuchsvc_zz", "--dry-run"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data.get("dry_run") is True


def test_tools_rm_requires_force():
    name = f"agent_tool_{int(time.time())}"
    add = _run(["--json", "tools", "add", name, "--type", "cli", "--description", "tmp"])
    assert add.returncode == 0, add.stderr
    assert json.loads(add.stdout)["ok"] is True
    denied = _run(["--json", "tools", "rm", name])
    assert denied.returncode == 1
    body = json.loads(denied.stdout)
    assert "--force" in body.get("example", "")
    dry = _run(["--json", "tools", "rm", name, "--dry-run"])
    assert json.loads(dry.stdout)["data"]["dry_run"] is True
    ok = _run(["--json", "tools", "rm", name, "--force"])
    assert ok.returncode == 0
    assert json.loads(ok.stdout)["ok"] is True


def test_tools_get_missing_exits_nonzero():
    r = _run(["--json", "tools", "get", "__no_such_tool__"])
    assert r.returncode == 1
    data = json.loads(r.stdout)
    assert "example" in data
    assert data.get("ok") is False


def test_mcp_help_has_examples():
    r = _run(["mcp", "--help"])
    assert r.returncode == 0
    assert "Examples:" in r.stdout


def test_tasks_delete_help_has_examples():
    r = _run(["tasks", "delete", "--help"])
    assert r.returncode == 0
    assert "Examples:" in r.stdout
    assert "--dry-run" in r.stdout


def test_rtx_releases_help_has_examples():
    r = _run(["rtx", "releases", "--help"])
    assert r.returncode == 0
    assert "Examples:" in r.stdout
    assert "--dry-run" in r.stdout


def test_write_scan_help_has_examples():
    r = _run(["write", "scan", "--help"])
    assert r.returncode == 0
    assert "Examples:" in r.stdout
