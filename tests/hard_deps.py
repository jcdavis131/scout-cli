"""A missing HARD dependency must fail the suite, not skip it.

WHY THIS FILE EXISTS. `pytest.importorskip("mcp")` is the right tool for an
OPTIONAL dependency: the test does not apply, so skipping is honest. It is the
wrong tool for a dependency the project declares as required, because the two
outcomes are indistinguishable in the exit code:

    mcp installed, tests pass   -> suite green
    mcp NOT installed, 5 skips  -> suite green

The second case means the whole MCP server surface ran ZERO assertions and the
gate still said pass. That is not hypothetical here: the header of
tests/test_mcp_exit_codes.py already records that the five `importorskip("mcp")`
sites are why an exit-code-laundering bug survived a green suite.

pyproject.toml declares mcp under `[project].dependencies` (not under an extra,
and the comment there says so explicitly: "mcp is a hard dependency above").
So a missing `mcp` means the ENVIRONMENT is broken, not that the test is
inapplicable — and a broken environment should be loud.

`declared_runtime_requirements()` reads that list rather than restating it, so
this guard cannot drift out of sync with the manifest it is guarding.

WHY THE VERSION IS CHECKED TOO. `import mcp` succeeding is not the same claim as
"this environment matches the manifest". The manifest declares `httpx>=0.27`; an
environment carrying httpx 0.24.1 imports it fine, so an import-only guard calls
that clean — the same one-bit-too-coarse mistake as skip-vs-fail, one level in.
A too-old dependency is a broken environment for the same reason a missing one
is, so `require_declared_version()` fails on it by name.
"""

from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version
from pathlib import Path

# `packaging` is a hard install dependency of pytest itself, so it is present
# wherever this file can run at all. Parsing specifiers by hand would reproduce
# the comparison bugs this check exists to catch.
import pytest
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

# Distribution name -> the module its consumers actually import. Only names that
# differ need an entry; everything else imports under its own name.
IMPORT_NAME = {"pyyaml": "yaml"}

_REQUIREMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")


# Stands in for the whole dependency list when the manifest cannot be parsed. It
# is not a legal distribution name, so it can never collide with a real one.
MANIFEST_UNREADABLE = "<pyproject.toml [project].dependencies unreadable>"


def _parse_declared_runtime_requirements() -> list[tuple[str, str]]:
    """The strict parse. Raises on anything it cannot read; callers use the total wrapper."""
    lines = PYPROJECT.read_text(encoding="utf-8").splitlines()
    first = next(i for i, ln in enumerate(lines) if ln.strip() == "dependencies = [")
    reqs = []
    # Comment-strip BEFORE looking for the closing bracket: the comment above
    # `typer>=0.12` contains the literal `typer[all]`, so scanning the raw text
    # for the next `]` ends the list inside a comment and finds nothing.
    for ln in lines[first + 1 :]:
        ln = ln.split("#", 1)[0].strip()
        if ln.startswith("]"):
            break
        ln = ln.strip(",").strip()
        if not (len(ln) > 2 and ln[0] in "\"'" and ln[-1] == ln[0]):
            continue
        req = ln[1:-1].strip()
        m = _REQUIREMENT.match(req)
        if not m:
            continue
        # Drop extras (`typer[all]>=0.12`) and environment markers (`; python_version<"3.11"`)
        # so what is left is the bare version specifier.
        spec = req[m.end() :].split(";", 1)[0].strip()
        if spec.startswith("["):
            spec = spec.split("]", 1)[-1].strip()
        reqs.append((m.group(0).lower(), spec))
    if not reqs:  # a parse that finds nothing must not read as "nothing declared"
        raise AssertionError(f"parsed zero dependencies out of {PYPROJECT}")
    return reqs


def declared_runtime_requirements() -> list[tuple[str, str]]:
    """`[project].dependencies` as (name, version specifier) pairs, in manifest order.

    Parsed from text on purpose: `tomllib` is 3.11+ and this project supports
    3.10 (pyproject.toml:6), so a tomllib import would make the guard itself
    unavailable on the oldest interpreter it is meant to protect.

    The specifier is whatever trails the name (`">=0.27"`), or `""` when the
    manifest pins nothing — which `SpecifierSet` treats as "any version", so an
    unpinned dependency is checked for presence only.

    WHY THIS NEVER RAISES. Both call sites are `@pytest.mark.parametrize(...)`
    arguments, which pytest evaluates during COLLECTION. An exception there is not
    a test failure that gets reported and moved past — it interrupts the session:

        E   StopIteration
        !!!!!! Interrupted: 1 error during collection !!!!!!    # exit 2, 0 tests ran

    Measured 2026-08-13: reformatting `dependencies = [` to `dependencies=[` — what
    any TOML formatter might do — took the entire suite to zero tests run, naming
    only `StopIteration` and nothing about the manifest. A guard against
    "a check that cannot run" must not be the thing that stops the checks running.

    So a failed parse becomes one MANIFEST_UNREADABLE row carrying the cause, which
    `require()` and `require_declared_version()` turn into a named failure while the
    rest of the suite still reports. One row and not zero is the load-bearing part:
    pytest reports an empty parameter set as SKIPPED, so returning `[]` here would
    launder an unreadable manifest into green — the exact shape this file exists for.
    """
    try:
        return _parse_declared_runtime_requirements()
    except Exception as e:  # noqa: BLE001 - any failure to read the manifest, named below
        return [(MANIFEST_UNREADABLE, f"{type(e).__name__}: {e}")]


def declared_runtime_dependencies() -> list[str]:
    """Just the names from `declared_runtime_requirements()`, in manifest order."""
    return [name for name, _ in declared_runtime_requirements()]


def _fail_if_manifest_unreadable(dist: str, spec: str) -> None:
    """Turn the MANIFEST_UNREADABLE sentinel into a failure that names the real cause.

    Both guards below need this: without it the sentinel still fails, but under a
    message about a missing import or missing metadata, which sends the reader after
    a dependency when the actual problem is that the manifest never parsed.
    """
    if dist != MANIFEST_UNREADABLE:
        return
    # `require()` is handed a bare name, so recover the cause from the sentinel row
    # rather than reporting the parse failure without saying what it was.
    if not spec:
        spec = next(
            (s for name, s in declared_runtime_requirements() if name == dist), ""
        )
    pytest.fail(
        f"the dependency list in {PYPROJECT.name} could not be parsed, so NO declared "
        f"dependency was checked ({spec or 'cause unrecorded'}). This is one failure "
        f"standing in for all of them; it is not a claim that any single dependency is "
        f"wrong. Deliberately a failure and not a collection error: raising while pytest "
        f"builds the parameter list interrupts the whole session (exit 2, zero tests "
        f"run), which is the outage this guard exists to prevent, not cause.",
        pytrace=False,
    )


def require(dist: str) -> object:
    """Import a declared hard dependency, or FAIL — never skip.

    Returns the module so call sites can use it exactly like the
    `pytest.importorskip` they replace.
    """
    _fail_if_manifest_unreadable(dist, "")
    module = IMPORT_NAME.get(dist.lower(), dist)
    try:
        return __import__(module)
    except ImportError as e:
        pytest.fail(
            f"{dist!r} is declared in [project].dependencies of {PYPROJECT.name} "
            f"but `import {module}` failed: {e}. This is a broken environment, not "
            f"an inapplicable test — skipping here would report the untested "
            f"surface as green. Install it (`pip install -e .`) and re-run.",
            pytrace=False,
        )


def require_mcp() -> object:
    """Drop-in for `pytest.importorskip("mcp")` that fails loudly instead."""
    return require("mcp")


def require_declared_version(dist: str, spec: str) -> str:
    """Check the INSTALLED version of `dist` against the manifest's `spec`, or FAIL.

    Deliberately separate from `require()`: call sites there want the module
    object and only care that the import worked, while this is a statement about
    the environment as a whole. Keeping them apart also means a version drift
    fails under its own test name instead of re-flagging every import site.

    Returns the installed version string so a caller can report it.
    """
    _fail_if_manifest_unreadable(dist, spec)
    try:
        found = installed_version(dist)
    except PackageNotFoundError:
        pytest.fail(
            f"{dist!r} is declared in [project].dependencies of {PYPROJECT.name} "
            f"but no installed distribution metadata was found for it, so its "
            f"declared version ({spec or 'any'}) cannot be checked. An unverifiable "
            f"constraint must not read as a satisfied one. Install the project "
            f"(`pip install -e \".[dev]\"`) and re-run.",
            pytrace=False,
        )
    if not spec:
        return found
    try:
        satisfied = Version(found) in SpecifierSet(spec)
    except (InvalidVersion, InvalidSpecifier) as e:
        # Unparseable either way means the constraint was not checked. Say so
        # rather than letting the exception be mistaken for an unrelated error.
        pytest.fail(
            f"cannot compare installed {dist} {found!r} against declared {spec!r}: {e}. "
            f"An uncheckable constraint must not read as a satisfied one.",
            pytrace=False,
        )
    if not satisfied:
        pytest.fail(
            f"{dist} {found} is installed but {PYPROJECT.name} declares {dist}{spec}. "
            f"`import {IMPORT_NAME.get(dist.lower(), dist)}` still succeeds, which is "
            f"why this is checked separately — an import-only guard reports a too-old "
            f"dependency as a clean environment. Install the project "
            f"(`pip install -e \".[dev]\"`) and re-run.",
            pytrace=False,
        )
    return found
