"""The tools plugin's own commands. 360 loc, no test file until now.

GOAT flagged `tools` with D4 0 ("NO test file") -- the tool REGISTRY is the first
bullet in the README ("one CLI to rule all internet tools") and the surface every
other command (`tools call`, the agent planner, `scout mcp`) sits on top of. Same
shape as `auth` and `secrets` before this: `bigbang.core.registry` had one
round-trip test (tests/test_cli.py::test_registry), but the plugin CLI wrapping it
-- argument validation, --force/--dry-run semantics, and the policy gate on
`tools call` -- had zero.

WHAT THIS COVERS, and why these commands. `call_cmd` is the one with a security
claim worth pinning: every call is supposed to go through `enforce_or_raise`
before any network traffic, using the CAPABILITY MANIFEST stored at register
time (not the separate user URL allowlist `tools import-openapi` uses). A tool
registered with an empty/mismatched domain allowlist must be refused even though
it is already in the registry -- registration and permission are different
questions, and conflating them would mean "add" implicitly grants "call".

conftest.py redirects HOME, so the registry file here is a throwaway shared
across this whole test session; the autouse fixture below removes exactly the
keys a test added so order never matters.
"""

from __future__ import annotations

import json

import pytest
import typer

from bigbang.core.output import set_json_mode
from bigbang.core.registry import get_tool, list_tools, register_tool
from bigbang.plugins.tools import cli as tc


@pytest.fixture(autouse=True)
def _json_mode():
    set_json_mode(True)
    yield
    set_json_mode(False)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Undo exactly what a test registers, regardless of test order."""
    before = set(list_tools().keys())
    yield
    from bigbang.core.registry import unregister_tool

    for name in set(list_tools().keys()) - before:
        unregister_tool(name)


def _emitted(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


# --- add / get -----------------------------------------------------------------


def test_add_registers_a_cli_tool(capsys):
    tc.add_cmd(
        name="_t_probe",
        type="cli",
        url=None,
        description="a probe tool",
        tags="api, work",
    )
    payload = _emitted(capsys)
    assert payload["overwrote"] is False
    assert payload["manifest"]["tags"] == ["api", "work"]
    assert get_tool("_t_probe")["description"] == "a probe tool"


def test_add_is_idempotent_and_reports_overwrite(capsys):
    tc.add_cmd(name="_t_probe", type="cli", url=None, description="v1", tags="")
    capsys.readouterr()
    tc.add_cmd(name="_t_probe", type="cli", url=None, description="v2", tags="")
    payload = _emitted(capsys)
    assert payload["overwrote"] is True
    assert get_tool("_t_probe")["description"] == "v2"


def test_add_derives_domain_from_url(capsys):
    tc.add_cmd(
        name="_t_probe",
        type="mcp",
        url="https://mcp.example.com/sse",
        description="",
        tags="",
    )
    payload = _emitted(capsys)
    assert payload["manifest"]["capabilities"]["network"]["domains"] == [
        "mcp.example.com"
    ]
    # fs write is never granted implicitly by `add`
    assert payload["manifest"]["capabilities"]["filesystem"]["write"] is False


def test_add_openapi_records_fetch_failure_instead_of_raising(capsys):
    """No network in this test environment (default-deny policy, unreachable
    host); `add` must still register the tool and say WHY the spec fetch
    failed rather than crash the command."""
    tc.add_cmd(
        name="_t_probe",
        type="openapi",
        url="https://tools.invalid.example/openapi.json",
        description="",
        tags="",
    )
    payload = _emitted(capsys)
    assert "openapi_error" in payload["manifest"]
    assert get_tool("_t_probe") is not None


def test_get_returns_the_stored_manifest(capsys):
    register_tool("_t_probe", {"type": "cli", "description": "x"})
    tc.get_cmd(name="_t_probe")
    payload = _emitted(capsys)
    assert payload["name"] == "_t_probe"
    assert payload["type"] == "cli"


def test_get_of_unknown_tool_exits_nonzero(capsys):
    with pytest.raises(typer.Exit) as exc:
        tc.get_cmd(name="_t_nosuchtool")
    assert exc.value.exit_code == 1
    assert "not found" in _emitted(capsys)["error"]


# --- list / search ---------------------------------------------------------------


def test_list_reports_count_and_entries(capsys):
    register_tool("_t_probe", {"type": "cli", "tags": ["work"]})
    tc.list_cmd(tag=None)
    payload = _emitted(capsys)
    assert "_t_probe" in payload["tools"]
    assert payload["count"] == len(payload["tools"])


def test_list_filters_by_tag(capsys):
    register_tool("_t_probe_a", {"type": "cli", "tags": ["work"]})
    register_tool("_t_probe_b", {"type": "cli", "tags": ["personal"]})
    tc.list_cmd(tag="personal")
    payload = _emitted(capsys)
    assert "_t_probe_b" in payload["tools"]
    assert "_t_probe_a" not in payload["tools"]


def test_search_matches_name_description_and_tags(capsys):
    register_tool(
        "_t_probe_gh",
        {"type": "openapi", "description": "talks to github", "tags": ["dev"]},
    )
    tc.search_cmd(query="github")
    payload = _emitted(capsys)
    assert payload["count"] >= 1
    assert any(r.get("name") == "_t_probe_gh" for r in payload["results"])


def test_search_with_no_matches_returns_empty_not_an_error(capsys):
    tc.search_cmd(query="_no_such_tool_should_ever_match_zzz")
    payload = _emitted(capsys)
    assert payload["results"] == []
    assert payload["count"] == 0


# --- rm ---------------------------------------------------------------------------


def test_rm_dry_run_does_not_remove(capsys):
    register_tool("_t_probe", {"type": "cli"})
    tc.rm_cmd(name="_t_probe", force=False, dry_run=True)
    payload = _emitted(capsys)
    assert payload["dry_run"] is True
    assert payload["exists"] is True
    assert get_tool("_t_probe") is not None


def test_rm_without_force_refuses_to_delete_an_existing_tool(capsys):
    """The one property worth pinning: --force is required, so a scripted
    retry or an agent typo can never surprise-delete a registered tool."""
    register_tool("_t_probe", {"type": "cli"})
    with pytest.raises(typer.Exit) as exc:
        tc.rm_cmd(name="_t_probe", force=False, dry_run=False)
    assert exc.value.exit_code == 1
    assert "--force" in _emitted(capsys)["example"]
    assert get_tool("_t_probe") is not None


def test_rm_with_force_removes_it(capsys):
    register_tool("_t_probe", {"type": "cli"})
    tc.rm_cmd(name="_t_probe", force=True, dry_run=False)
    payload = _emitted(capsys)
    assert payload["ok"] is True
    assert payload["existed"] is True
    assert get_tool("_t_probe") is None


def test_rm_of_a_missing_tool_with_force_is_a_no_op_not_an_error(capsys):
    """Idempotent per the docstring: retrying `rm --force` after it already
    succeeded must not start failing."""
    tc.rm_cmd(name="_t_never_registered", force=True, dry_run=False)
    payload = _emitted(capsys)
    assert payload["ok"] is False
    assert payload["existed"] is False


# --- call: policy gate -------------------------------------------------------------


def test_call_of_unregistered_tool_exits_nonzero(capsys):
    with pytest.raises(typer.Exit) as exc:
        tc.call_cmd(name="_t_nosuchtool", action="whatever", args=None)
    assert exc.value.exit_code == 1
    assert "not registered" in _emitted(capsys)["error"]


def test_call_is_denied_when_registered_domains_do_not_match(capsys):
    """Registration and permission are different questions. A tool sitting in
    the registry with a network capability that does NOT cover the resource
    being called must be refused -- `add` never implicitly grants `call`."""
    register_tool(
        "_t_probe",
        {
            "type": "cli",
            "url": "https://other.example.com",
            "capabilities": {"network": {"enabled": True, "domains": ["only-this.example.com"]}},
        },
    )
    with pytest.raises(typer.Exit) as exc:
        tc.call_cmd(name="_t_probe", action=None, args=None)
    # policy denial is reported via typer.secho, not emit()'s JSON channel --
    # the exit code is the actual gate being asserted here.
    assert exc.value.exit_code == 1


def test_call_is_allowed_when_domain_matches_and_reports_policy_checked(capsys):
    register_tool(
        "_t_probe",
        {
            "type": "cli",
            "url": "https://allowed.example.com/x",
            "capabilities": {
                "network": {"enabled": True, "domains": ["allowed.example.com"]}
            },
        },
    )
    tc.call_cmd(name="_t_probe", action="ping", args=None)
    payload = _emitted(capsys)
    assert "checked" in payload["policy"]
    assert payload["tool"] == "_t_probe"


def test_call_with_no_url_skips_the_network_gate_entirely(capsys):
    """A tool with no url (e.g. a bare `cli` type placeholder) has nothing for
    the policy layer to check against, so `call` must not crash reaching for
    a network capability that was never declared."""
    register_tool("_t_probe", {"type": "cli"})
    tc.call_cmd(name="_t_probe", action=None, args=None)
    payload = _emitted(capsys)
    assert payload["tool"] == "_t_probe"


def test_call_openapi_reports_invalid_json_args_as_a_warning_not_a_crash(capsys):
    """Malformed --args must not crash the command; it degrades to `{}` and
    says so. The manifest's domain matches, so this reaches the openapi
    branch and then hits fetch_spec's OWN default-deny gate (no user
    allowlist configured here) rather than any real network call -- two
    JSON objects come out of one `call`, and only the first is under test."""
    register_tool(
        "_t_probe",
        {
            "type": "openapi",
            "url": "https://allowed.example.com/openapi.json",
            "capabilities": {
                "network": {"enabled": True, "domains": ["allowed.example.com"]}
            },
        },
    )
    tc.call_cmd(name="_t_probe", action="list-things", args="{not valid json")
    out = capsys.readouterr().out
    first, _end = json.JSONDecoder().raw_decode(out)
    assert "args not valid JSON" in first["warning"]


# --- import-openapi: default-deny on the USER allowlist, distinct from `add` ------


def test_import_openapi_is_denied_by_the_default_deny_user_allowlist(capsys):
    """`tools import-openapi` is the one command checked against the persisted
    user allowlist (policy.enforce_user_url_or_raise), separate from the
    per-manifest capability check `call` uses. A fresh install has an empty
    allowlist, so this must refuse before any network call is attempted."""
    with pytest.raises(typer.Exit) as exc:
        tc.import_openapi(url="https://tools.invalid.example/openapi.json", name=None)
    assert exc.value.exit_code == 1
    assert get_tool("api") is None  # nothing got registered on the denied path


# --- generate: guardrails before any codegen work ----------------------------------


def test_generate_of_unregistered_tool_exits_nonzero(capsys):
    with pytest.raises(typer.Exit) as exc:
        tc.generate_cmd(name="_t_nosuchtool")
    assert exc.value.exit_code == 1


def test_generate_refuses_non_openapi_tools(capsys):
    register_tool("_t_probe", {"type": "mcp", "url": "https://x.example.com"})
    with pytest.raises(typer.Exit) as exc:
        tc.generate_cmd(name="_t_probe")
    assert exc.value.exit_code == 1
    assert "openapi" in _emitted(capsys)["error"]


def test_generate_refuses_an_openapi_tool_with_no_url(capsys):
    register_tool("_t_probe", {"type": "openapi", "url": None})
    with pytest.raises(typer.Exit) as exc:
        tc.generate_cmd(name="_t_probe")
    assert exc.value.exit_code == 1
    assert "no url" in _emitted(capsys)["error"]
