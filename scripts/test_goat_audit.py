#!/usr/bin/env python3
"""Tests for GOAT's D2 dimension, which was wrong in both directions.

D2 scores dead code. Until 2026-08-02 it used two greps over raw source text, and the
audit it produces is what decides which plugin gets worked on next — so a wrong D2 does
not just misreport, it misdirects. `todos` was the LOWEST-scored plugin in the repo (5.33)
partly because all four of its "commented-out code lines" were English:

    # if target is inside default root, no confirm
    # if single file, narrow filter to that file name

and because its Typer entry point `_todos_root` was counted as an unreferenced helper.

The other direction is worse, because it is silent. `src.count(name) <= 1` is a SUBSTRING
count, so a dead `_httpx_client` looked used every time `_httpx_client_fallback` was
mentioned, and dead `_load`/`_save` shims in auth looked used on every `_load_auth` call.
Three genuinely dead functions were hidden that way and are deleted in the same commit.

    pytest scripts/test_goat_audit.py -q      # collected with the rest of the suite
    python scripts/test_goat_audit.py         # standalone, still exits nonzero on failure

WHY THIS FILE IS SHAPED LIKE A PYTEST MODULE AND NOT A SCRIPT. It used to run all of its
checks at import time and end with a bare module-level `sys.exit(...)`. It is named
`test_*.py`, so pytest collects it — and a SystemExit raised during COLLECTION is not a
test failure, it is an INTERNALERROR that aborts the entire session:

    INTERNALERROR> SystemExit: 0
    no tests ran in 0.24s          # exit code 3

Note the `0`. The audit had PASSED, and passing still took the whole gate down with it —
`pytest` from the repo root ran ZERO of the ~2500 tests in `tests/` and reported a
failure whose traceback was 40 lines of `importlib._bootstrap` naming nothing a reader
could act on. Humans never saw it because README and every doc say `pytest tests/`, which
skips this directory; only the automated gate ran bare `pytest`. The checks below are
therefore real test functions, and the only `sys.exit` left is under `__main__`, where
pytest never looks. `tests/test_collection_is_not_booby_trapped.py` fails loudly if this
shape ever regresses here or anywhere else in the tree.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location("goat_audit", _HERE / "goat_audit.py")
goat = importlib.util.module_from_spec(_SPEC)
sys.modules["goat_audit"] = goat
_SPEC.loader.exec_module(goat)


# --- prose must not be counted as code ---------------------------------------------

PROSE = [
    "        # if target is inside default root, no confirm",
    "                # if single file, narrow filter to that file name",
    "            # if it looks like a path containing slash or backslash",
    "                    # if scanning outside root, relative to scan_root or absolute",
    "    # for the record, this is prose",
    "# return early was considered and rejected",
    "# while this is true, it is not code",
    "# TODO",
]


@pytest.mark.parametrize("line", PROSE, ids=lambda s: s.strip()[:52])
def test_prose_is_not_counted_as_commented_out_code(line):
    assert not goat._is_commented_code(line)


# --- real commented-out code must still be counted ---------------------------------

CODE = [
    "    # return True",
    "    # import os",
    "    # if x:",
    "    # for i in range(3):",
    "    # def helper(a, b):",
    "        # while running:",
    "    # client = httpx.Client()",
]


@pytest.mark.parametrize("line", CODE, ids=lambda s: s.strip()[:52])
def test_commented_out_code_is_still_counted(line):
    assert goat._is_commented_code(line)


# --- dead-helper detection ----------------------------------------------------------

SRC = '''
@app.callback(invoke_without_command=True)
def _todos_root(ctx):
    """Entry point. Typer holds the reference; the name appears once in the file."""
    return _scan(ctx)

def _scan(ctx):
    return _scan_markers(ctx)

def _scan_markers(ctx):
    return 1

def _genuinely_dead(x):
    return x

def _named_only_in_a_docstring(x):
    return x

def user_facing(x):
    """Mentions _named_only_in_a_docstring but never calls it."""
    return x
'''


@pytest.fixture(scope="module")
def dead():
    return goat._dead_helpers(ast.parse(SRC))


def test_a_decorator_registered_entry_point_is_not_dead(dead):
    assert "_todos_root" not in dead, dead


def test_a_helper_called_by_the_entry_point_is_not_dead(dead):
    assert "_scan" not in dead, dead


def test_a_helper_whose_name_contains_another_is_not_dead(dead):
    assert "_scan_markers" not in dead, dead


def test_a_genuinely_unused_helper_is_dead(dead):
    assert "_genuinely_dead" in dead, dead


def test_a_name_mentioned_only_in_a_docstring_does_not_count_as_a_use(dead):
    assert "_named_only_in_a_docstring" in dead, dead


def test_public_non_underscore_functions_are_out_of_scope(dead):
    assert "user_facing" not in dead, dead


# The old rule, run on the same source, to pin WHY this changed rather than assert it.

@pytest.fixture(scope="module")
def old_substring_rule():
    return [
        n.name
        for n in ast.parse(SRC).body
        if isinstance(n, ast.FunctionDef)
        and n.name.startswith("_")
        and SRC.count(n.name) <= 1
    ]


def test_the_old_substring_rule_really_did_flag_the_entry_point(old_substring_rule):
    assert "_todos_root" in old_substring_rule, (
        f"old={old_substring_rule} — if this stops being true the docstring above is stale"
    )


def test_the_old_substring_rule_really_did_miss_the_docstring_only_helper(
    old_substring_rule,
):
    assert "_named_only_in_a_docstring" not in old_substring_rule, old_substring_rule


# --- the audit still runs end to end ------------------------------------------------


@pytest.fixture(scope="module")
def todos_report():
    # `audit_plugin` takes a plugin NAME and joins it onto `goat.PLUGINS` itself. This
    # used to pass a full absolute path, which only worked because `PLUGINS / <abs>`
    # discards the left side in pathlib — true today, and silently wrong the moment
    # `name` is used for anything but that join.
    return goat.audit_plugin("todos")


def test_audit_plugin_returns_a_scored_report(todos_report):
    assert isinstance(todos_report, dict) and "mean" in todos_report, str(todos_report)[:200]


def test_todos_no_longer_loses_points_to_prose_comments(todos_report):
    findings = todos_report.get("findings", [])
    assert not any("commented-out" in f for f in findings), str(findings)


if __name__ == "__main__":
    # `raise SystemExit(pytest.main(...))` and not a bare `pytest.main(...)`: the latter
    # RETURNS the status code and the process would exit 0 no matter what failed, which
    # is the exact exit-code laundering this file exists to catch elsewhere.
    raise SystemExit(pytest.main([__file__, "-q"]))
