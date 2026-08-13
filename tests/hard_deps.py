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

`declared_runtime_dependencies()` reads that list rather than restating it, so
this guard cannot drift out of sync with the manifest it is guarding.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

# Distribution name -> the module its consumers actually import. Only names that
# differ need an entry; everything else imports under its own name.
IMPORT_NAME = {"pyyaml": "yaml"}

_REQUIREMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")


def declared_runtime_dependencies() -> list[str]:
    """The `[project].dependencies` names, lowercased, in manifest order.

    Parsed from text on purpose: `tomllib` is 3.11+ and this project supports
    3.10 (pyproject.toml:6), so a tomllib import would make the guard itself
    unavailable on the oldest interpreter it is meant to protect.
    """
    lines = PYPROJECT.read_text(encoding="utf-8").splitlines()
    first = next(i for i, ln in enumerate(lines) if ln.strip() == "dependencies = [")
    names = []
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
        m = _REQUIREMENT.match(ln[1:-1].strip())
        if m:
            names.append(m.group(0).lower())
    if not names:  # a parse that finds nothing must not read as "nothing declared"
        raise AssertionError(f"parsed zero dependencies out of {PYPROJECT}")
    return names


def require(dist: str) -> object:
    """Import a declared hard dependency, or FAIL — never skip.

    Returns the module so call sites can use it exactly like the
    `pytest.importorskip` they replace.
    """
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
