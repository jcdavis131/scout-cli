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


@pytest.mark.parametrize("dist", hard_deps.declared_runtime_dependencies())
def test_declared_dependency_imports(dist):
    assert hard_deps.require(dist) is not None


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
