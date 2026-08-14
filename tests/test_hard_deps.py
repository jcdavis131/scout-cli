"""The guard that would have caught a green suite running on a broken env.
One test per declared hard dependency: it must import. If `pip install -e .` half-succeeded, or a dependency
quietly moved to an extra, this fails by name instead of letting the affected modules skip themselves into a
green run.
"""

from __future__ import annotations

import subprocess
import sys

import hard_deps
import pytest


def test_dependency_list_parses():
    """The parser must find the manifest's dependencies, not silently find none.
    An empty parse would make every dependency check below vacuously pass — the exact failure shape this file
    exists to prevent, one level up.
    """
    names = hard_deps.declared_runtime_dependencies()
    assert "mcp" in names, names
    assert len(names) >= 5, names


def test_dependency_specifiers_parse():
    """The version specifiers must survive parsing, or the version check is a no-op.
    `SpecifierSet("")` accepts every version, so a parser that dropped the `>=` half of each requirement would
    leave `test_declared_dependency_satisfies_specifier` passing unconditionally — a guard that cannot fail,
    which is this file's whole subject. Pinning one known specifier keeps that silent.
    """
    reqs = dict(hard_deps.declared_runtime_requirements())
    assert reqs["mcp"] == ">=1.28.1", reqs
    assert reqs["httpx"] == ">=0.27", reqs
    assert all(reqs.values()), f"a declared dependency lost its specifier: {reqs}"


@pytest.mark.parametrize("dist", hard_deps.declared_runtime_dependencies())
def test_declared_dependency_imports(dist):
    assert hard_deps.require(dist) is not None


@pytest.mark.parametrize("dist,spec", hard_deps.declared_runtime_requirements())
def test_declared_dependency_satisfies_specifier(dist, spec):
    """Importable is not the same claim as "matches the manifest".
    This is the check that catches an environment carrying httpx 0.24.1 against a declared `httpx>=0.27`:
    `import httpx` works, so the import guard above is green, and every httpx-dependent test runs against an
    API the manifest says is too old to support.
    """
    assert hard_deps.require_declared_version(dist, spec)


def test_version_mismatch_fails_it_does_not_pass():
    """A violated specifier must be a FAILURE outcome — not a pass, not a skip."""
    with pytest.raises(pytest.fail.Exception) as excinfo:
        hard_deps.require_declared_version("pytest", "<0.0.1")
    assert not isinstance(excinfo.value, pytest.skip.Exception)
    assert "declares pytest<0.0.1" in str(excinfo.value)


def test_unverifiable_version_fails_it_does_not_pass():
    """Missing metadata means the constraint went unchecked, so it must be loud.
    Reporting "no evidence of a violation" as "no violation" is the same laundering as skipping: both hand
    back a green result for a check that never ran.
    """
    with pytest.raises(pytest.fail.Exception) as excinfo:
        hard_deps.require_declared_version("scout_no_such_distribution", ">=1.0")
    assert not isinstance(excinfo.value, pytest.skip.Exception)
    assert "cannot be checked" in str(excinfo.value)


def test_unparseable_specifier_fails_it_does_not_pass():
    """An uncomparable version pair must not fall through to a pass either."""
    with pytest.raises(pytest.fail.Exception) as excinfo:
        hard_deps.require_declared_version("pytest", "not-a-specifier")
    assert not isinstance(excinfo.value, pytest.skip.Exception)
    assert "uncheckable constraint" in str(excinfo.value)


# An unreadable manifest must fail LOUDLY AT TEST TIME, never during collection. The two parametrize
# decorators above are evaluated while pytest builds the test list, so before this guard existed, anything
# that stopped the parse took the whole session down: `Interrupted: 1 error during collection`, exit 2, zero
# tests run — the sibling modules never even loaded. Measured 2026-08-13; the trigger was reformatting
# `dependencies = [` to `dependencies=[`. Each case below is a manifest that cannot parse.
BROKEN_MANIFESTS = {
    # What a TOML formatter can do to the line the parser keys on.
    "reformatted": '[project]\ndependencies=[\n  "mcp>=1.28.1",\n]\n',
    # The list is found but holds nothing — must not read as "nothing is declared".
    "empty_list": '[project]\ndependencies = [\n]\n',
    # No dependency list at all.
    "absent_key": '[project]\nname = "scout-cli"\n',
    # Not written at all: PYPROJECT.read_text raises before parsing starts.
    "missing_file": None,
}


def _manifest(monkeypatch, tmp_path, body):
    """Point hard_deps at a manifest of our choosing. `None` leaves the file absent."""
    path = tmp_path / "pyproject.toml"
    if body is not None:
        path.write_text(body, encoding="utf-8")
    monkeypatch.setattr(hard_deps, "PYPROJECT", path)
    return path


@pytest.mark.parametrize("case", sorted(BROKEN_MANIFESTS))
def test_unreadable_manifest_yields_exactly_one_loud_parameter(case, monkeypatch, tmp_path):
    """Never zero parameters: pytest reports an empty parameter set as SKIPPED.
    This is the half of the bug that hides. Returning `[]` on a failed parse would make both parametrized
    tests above collect as a single green skip, so a manifest nobody could read would present as a clean run.
    Exactly one sentinel row keeps the outcome red, and carries the cause so the failure names it.
    """
    _manifest(monkeypatch, tmp_path, BROKEN_MANIFESTS[case])
    reqs = hard_deps.declared_runtime_requirements()
    assert len(reqs) == 1, reqs
    assert reqs[0][0] == hard_deps.MANIFEST_UNREADABLE, reqs
    assert reqs[0][1], "the sentinel must carry the cause, not an empty string"
    assert hard_deps.declared_runtime_dependencies() == [hard_deps.MANIFEST_UNREADABLE]


@pytest.mark.parametrize("case", sorted(BROKEN_MANIFESTS))
def test_unreadable_manifest_does_not_abort_collection(case, monkeypatch, tmp_path):
    """Reading a broken manifest must not raise — a raise here kills the whole session.
    `declared_runtime_requirements()` is called from a `@pytest.mark.parametrize` argument, i.e. during
    collection, where an exception is not a reported failure but `Interrupted: 1 error during collection`
    with zero tests run.
    """
    _manifest(monkeypatch, tmp_path, BROKEN_MANIFESTS[case])
    hard_deps.declared_runtime_requirements()  # must return, not raise


@pytest.mark.parametrize("guard", ["require", "require_declared_version"])
def test_sentinel_fails_under_both_guards_naming_the_manifest(guard):
    """Whichever parametrized test receives the sentinel must fail, and say why.
    Without an explicit branch the sentinel still fails, but as "import failed" or "no metadata found" —
    pointing at a dependency when the manifest is what broke.
    """
    with pytest.raises(pytest.fail.Exception) as excinfo:
        if guard == "require":
            hard_deps.require(hard_deps.MANIFEST_UNREADABLE)
        else:
            hard_deps.require_declared_version(hard_deps.MANIFEST_UNREADABLE, "StopIteration: ")
    assert not isinstance(excinfo.value, pytest.skip.Exception)
    assert "could not be parsed" in str(excinfo.value)
    assert "NO declared dependency was checked" in str(excinfo.value)


def test_the_sentinel_cannot_be_a_real_distribution_name():
    """A sentinel that could collide with a real name would swallow a real check."""
    assert not hard_deps._REQUIREMENT.match(hard_deps.MANIFEST_UNREADABLE)


def test_a_readable_manifest_still_parses_normally(monkeypatch, tmp_path):
    """Guard the guard: the totality wrapper must not swallow a manifest that IS fine."""
    _manifest(monkeypatch, tmp_path, '[project]\ndependencies = [\n  "mcp>=1.28.1",\n  "httpx>=0.27",\n]\n')
    assert hard_deps.declared_runtime_requirements() == [("mcp", ">=1.28.1"), ("httpx", ">=0.27")]


def test_require_fails_it_does_not_skip():
    """The whole point: a missing hard dep is a FAILURE outcome, not a skip.
    `pytest.fail` raises Failed and `pytest.skip` raises Skipped; both are BaseException subclasses, so
    asserting on the type is what pins the behaviour. An implementation that quietly went back to
    `importorskip` would still "raise something" here — it would just raise the green one.
    """
    with pytest.raises(pytest.fail.Exception) as excinfo:
        hard_deps.require("scout_no_such_distribution")
    assert not isinstance(excinfo.value, pytest.skip.Exception)
    assert "broken environment" in str(excinfo.value)


def test_the_deferred_mcp_import_actually_resolves():
    """`bigbang/plugins/mcp/cli.py` binds its two client names inside `_check_sdk()` so the mcp SDK stays out
    of every `scout` startup. Every other test of that module monkeypatches those names rather than importing
    across them, so a broken import path there would pass the whole suite while `mcp call` failed for real
    users. This is the one test that crosses it unmocked.

    IDENTITY, NOT `callable()`. `_check_sdk()` rebinds each name only while it is still None, so a stub left
    on the module by an earlier test survives the call and `callable(stub)` is true: measured 2026-08-14,
    stubbing both names passed all three of the previous assertions. Identity is what separates a real
    resolution from a leftover one.
    """
    from bigbang.core import mcp_client
    from bigbang.plugins.mcp import cli as mcp_cli

    assert mcp_cli._check_sdk() is True
    assert mcp_cli.list_mcp_tools_sync is mcp_client.list_mcp_tools_sync
    assert mcp_cli.call_mcp_tool_sync is mcp_client.call_mcp_tool_sync


def test_cli_startup_does_not_import_the_mcp_sdk():
    """The property the deferral buys, asserted rather than trusted: importing the CLI must not drag in
    `mcp`. A module-scope `from bigbang.core.mcp_client import ...` in any plugin puts it back, costs ~366ms
    of a ~792ms startup, and nothing else in the suite would notice.
    """
    probe = "import bigbang.cli, sys; print('mcp' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=60
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False", "importing bigbang.cli pulled in the mcp SDK"
