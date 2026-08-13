"""`mcp` subcommands must not hand the shell a 0 for work that did not happen.

WHY THIS FILE EXISTS. `emit()` prints a payload and returns; it sets no exit code and
logs `status="ok"` regardless of what is in the payload. `mcp serve` compensated
(`raise typer.Exit(1)`), but `mcp list-tools` and `mcp call` did not: an unreachable
server, an unknown server name, or an absent mcp SDK printed an `{"error": ...}` object
and still exited 0. `bb mcp call srv deploy && ship` would run `ship`.

WHY THESE TESTS ARE NOT GUARDED BY `importorskip("mcp")`. The five existing
`importorskip("mcp")` sites are why this bug survived: `mcp>=1.28.1` is a hard
dependency in pyproject.toml, so in an environment missing it the whole `mcp` surface
goes untested and the summary line still says passed. That is the exact shape this
repo's README skip census calls out. Every test here monkeypatches the SDK boundary
instead of importing across it, so they run identically whether or not `mcp` is
installed -- and they are the only coverage of the mcp CLI that does.
"""

from __future__ import annotations

import re
import sys
import types

import pytest
from typer.testing import CliRunner

from bigbang.plugins.mcp import cli as mcp_cli

runner = CliRunner()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _out(result) -> str:
    """Rich colorizes emit()'s JSON; strip it so substring asserts are honest."""
    return _ANSI.sub("", result.stdout)


@pytest.fixture
def registered(monkeypatch):
    """One registered server, and the default-deny URL policy stood down.

    `enforce_user_url_or_raise` would otherwise reject the fake URL before control
    ever reaches the SDK call -- the test would pass on the wrong branch.
    """
    monkeypatch.setattr(
        mcp_cli, "_load_mcp", lambda: {"srv": {"url": "http://127.0.0.1:1/sse"}}
    )
    monkeypatch.setattr(
        mcp_cli, "enforce_user_url_or_raise", lambda url, context="": None
    )


def _boom(*_a, **_k):
    raise RuntimeError("mcp SDK not installed. Run: pip install 'mcp>=1.28.1'")


# ---------------------------------------------------------------------------
# The failure that reported success
# ---------------------------------------------------------------------------


def test_list_tools_exits_nonzero_when_the_sdk_is_missing(registered, monkeypatch):
    monkeypatch.setattr(mcp_cli, "list_mcp_tools_sync", _boom)
    result = runner.invoke(mcp_cli.app, ["list-tools", "srv"])
    assert result.exit_code != 0, "a tool listing that never ran must not exit 0"
    assert "error" in _out(result)


def test_call_exits_nonzero_when_the_sdk_is_missing(registered, monkeypatch):
    monkeypatch.setattr(mcp_cli, "call_mcp_tool_sync", _boom)
    result = runner.invoke(mcp_cli.app, ["call", "srv", "some_tool"])
    assert result.exit_code != 0, "a tool that never ran must not look like a no-op"
    assert "error" in _out(result)


def test_list_tools_exits_nonzero_when_the_server_is_unreachable(
    registered, monkeypatch
):
    """The SDK-missing case and the server-down case share one except branch."""

    def _refused(*_a, **_k):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(mcp_cli, "list_mcp_tools_sync", _refused)
    result = runner.invoke(mcp_cli.app, ["list-tools", "srv"])
    assert result.exit_code != 0
    assert "refused" in _out(result)


def test_unknown_server_exits_nonzero(monkeypatch):
    """`not found` was an early `return` -- same laundering, no exception involved."""
    monkeypatch.setattr(mcp_cli, "_load_mcp", dict)

    listed = runner.invoke(mcp_cli.app, ["list-tools", "nope"])
    assert listed.exit_code != 0
    assert "not found" in _out(listed)

    called = runner.invoke(mcp_cli.app, ["call", "nope", "some_tool"])
    assert called.exit_code != 0
    assert "not found" in _out(called)


# ---------------------------------------------------------------------------
# The one command that already got it right -- pinned so it cannot regress
# ---------------------------------------------------------------------------


def test_serve_exits_nonzero_when_the_server_module_cannot_import(monkeypatch):
    """A stub module without `run_server` makes the from-import fail deterministically.

    Invoking `serve` for real is not an option: where `mcp` IS installed it blocks on a
    stdio server and hangs the suite. Faking the import failure pins the exit code in
    both environments without ever starting anything.
    """
    stub = types.ModuleType("bigbang.plugins.mcp.server")
    monkeypatch.setitem(sys.modules, "bigbang.plugins.mcp.server", stub)

    result = runner.invoke(mcp_cli.app, ["serve"])
    assert result.exit_code != 0
    assert "mcp SDK not installed" in _out(result)


def test_successful_list_tools_still_exits_zero(registered, monkeypatch):
    """The guard above must not turn every invocation into a failure."""
    monkeypatch.setattr(
        mcp_cli, "list_mcp_tools_sync", lambda url: [{"name": "a_tool"}]
    )
    result = runner.invoke(mcp_cli.app, ["list-tools", "srv"])
    assert result.exit_code == 0, _out(result)
    assert "a_tool" in _out(result)
