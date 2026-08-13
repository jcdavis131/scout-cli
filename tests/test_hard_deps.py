"""The guard that would have caught a green suite running on a broken env.

One test per declared hard dependency: it must import. If `pip install -e .`
half-succeeded, or a dependency quietly moved to an extra, this fails by name
instead of letting the affected modules skip themselves into a green run.
"""

from __future__ import annotations

import pytest

import hard_deps


def test_dependency_list_parses():
    """The parser must find the manifest's dependencies, not silently find none.

    An empty parse would make every dependency check below vacuously pass — the
    exact failure shape this file exists to prevent, one level up.
    """
    names = hard_deps.declared_runtime_dependencies()
    assert "mcp" in names, names
    assert len(names) >= 5, names


def test_dependency_specifiers_parse():
    """The version specifiers must survive parsing, or the version check is a no-op.

    `SpecifierSet("")` accepts every version, so a parser that dropped the `>=`
    half of each requirement would leave `test_declared_dependency_satisfies_specifier`
    passing unconditionally — a guard that cannot fail, which is this file's
    whole subject. Pinning one known specifier keeps that silent.
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

    This is the check that catches an environment carrying httpx 0.24.1 against a
    declared `httpx>=0.27`: `import httpx` works, so the import guard above is
    green, and every httpx-dependent test runs against an API the manifest says
    is too old to support.
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

    Reporting "no evidence of a violation" as "no violation" is the same laundering
    as skipping: both hand back a green result for a check that never ran.
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


def test_require_fails_it_does_not_skip():
    """The whole point: a missing hard dep is a FAILURE outcome, not a skip.

    `pytest.fail` raises Failed and `pytest.skip` raises Skipped; both are
    BaseException subclasses, so asserting on the type is what pins the
    behaviour. An implementation that quietly went back to `importorskip` would
    still "raise something" here — it would just raise the green one.
    """
    with pytest.raises(pytest.fail.Exception) as excinfo:
        hard_deps.require("scout_no_such_distribution")
    assert not isinstance(excinfo.value, pytest.skip.Exception)
    assert "broken environment" in str(excinfo.value)
