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
could act on. Humans never saw it because README and every doc said `pytest tests/`, which
skips this directory; only the automated gate ran bare `pytest`. Those docs now say
`python -m pytest -q` with no path, which collects both `testpaths` roots, so the command
a human types reaches this directory too. The checks below are
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


# --- the --check exit-code contract --------------------------------------------------
#
# THE BUG THESE EXIST FOR. `--check` is the gate half of this tool, and it had three
# distinct ways to exit 0 while comparing NOTHING, each printing the same reassuring
# "no regressions vs baseline":
#
#   no .goat_baseline.json  -> `base = {}` -> every `r["plugin"] in base` is False
#   no plugins discovered   -> `reports = []` -> nothing to iterate
#   --plugin <typo>         -> a phantom 0.0 that no baseline can contradict
#
# All three are the same failure: a check that could not run, read as a clean one. The
# tests below assert the exit CODE, not the message, because the exit code is what a
# gate consumes — and they assert the absence of the reassuring line, because a human
# skimming a log consumes that.


@pytest.fixture
def gate(tmp_path, monkeypatch):
    """goat_audit wired to a scratch plugin tree, so exit codes are exact and fast.

    `audit_plugin` is stubbed: these tests are about the gate's control flow, and
    scoring 63 real plugins per case would make the contract expensive to assert.
    The scoring itself is covered by the audit_plugin tests above.
    """
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    monkeypatch.setattr(goat, "PLUGINS", plugins)
    monkeypatch.setattr(goat, "BASELINE", tmp_path / ".goat_baseline.json")
    means: dict[str, float] = {}

    monkeypatch.setattr(goat, "audit_plugin", lambda name, run_tests=False: {
        "plugin": name, "mean": means.get(name, 9.0), "loc": 10, "findings": [],
        "scores": dict.fromkeys(
            ("d1_dependency", "d2_dead_code", "d3_self_contained",
             "d4_test_honesty", "d5_hot_path", "d6_honest_notes"), 9),
    })

    class Gate:
        baseline_path = goat.BASELINE

        def plugin(self, name, mean=9.0):
            (plugins / name).mkdir()
            (plugins / name / "cli.py").write_text("x = 1\n", encoding="utf-8")
            means[name] = mean

        def write_baseline(self, text):  # raw text, so a corrupt file is expressible
            self.baseline_path.write_text(text, encoding="utf-8")

        def run(self, *argv):
            monkeypatch.setattr(sys, "argv", ["goat_audit.py", *argv])
            return goat.main()

    return Gate()


CANNOT_RUN = 2  # distinct from 1: "the gate did not run" is not "the gate found a bug"


def test_a_missing_baseline_cannot_report_no_regressions(gate, capsys):
    gate.plugin("sitemap")
    rc = gate.run("--check")
    assert rc == CANNOT_RUN
    assert "no regressions" not in capsys.readouterr().out


@pytest.mark.parametrize("body, why", [
    ("{}", "empty object"),
    ("[]", "a list, not a score map"),
    ("null", "JSON null"),
    ("{not json", "truncated file"),
    ('"63"', "a bare string"),
])
def test_an_unusable_baseline_cannot_report_no_regressions(gate, capsys, body, why):
    gate.plugin("sitemap")
    gate.write_baseline(body)
    rc = gate.run("--check")
    assert rc == CANNOT_RUN, why
    assert "no regressions" not in capsys.readouterr().out, why


def test_auditing_zero_plugins_cannot_report_no_regressions(gate, capsys):
    gate.write_baseline('{"sitemap": 9.0}')  # a real baseline; the TREE is what is empty
    rc = gate.run("--check")
    assert rc == CANNOT_RUN
    assert "no regressions" not in capsys.readouterr().out


def test_a_typod_plugin_name_cannot_report_no_regressions(gate, capsys):
    gate.plugin("sitemap")
    gate.write_baseline('{"sitemap": 9.0}')
    rc = gate.run("--check", "--plugin", "sitemapp")
    assert rc == CANNOT_RUN
    assert "no regressions" not in capsys.readouterr().out


def test_a_baseline_is_never_written_from_an_empty_audit(gate):
    """--baseline over a tree with no plugins would disarm --check permanently."""
    assert gate.run("--baseline") == CANNOT_RUN
    assert not gate.baseline_path.exists(), gate.baseline_path.read_text(encoding="utf-8")


def test_a_plugin_the_baseline_covers_but_the_run_skipped_is_loud(gate, capsys):
    gate.plugin("sitemap")
    gate.write_baseline('{"sitemap": 9.0, "vanished": 9.0}')
    rc = gate.run("--check")
    assert rc == 1
    assert "BASELINED BUT NOT AUDITED" in capsys.readouterr().err


def test_an_explicit_plugin_subset_is_not_treated_as_vanished_coverage(gate, capsys):
    """--plugin asks for a subset on purpose; that must stay a usable exit 0."""
    gate.plugin("sitemap")
    gate.plugin("todos")
    gate.write_baseline('{"sitemap": 9.0, "todos": 9.0}')
    assert gate.run("--check", "--plugin", "sitemap") == 0
    assert "no regressions" in capsys.readouterr().out


# --- the working paths still work -----------------------------------------------------


def test_a_real_regression_still_exits_1(gate, capsys):
    gate.plugin("sitemap", mean=8.0)
    gate.write_baseline('{"sitemap": 9.0}')
    assert gate.run("--check") == 1
    assert "REGRESSION: sitemap 9.0 -> 8.0" in capsys.readouterr().err


def test_a_clean_check_exits_0_and_says_what_it_compared(gate, capsys):
    gate.plugin("sitemap")
    gate.plugin("todos")
    gate.write_baseline('{"sitemap": 9.0, "todos": 9.0}')
    assert gate.run("--check") == 0
    # The counts are the point: "no regressions" alone reads the same after
    # comparing 63 plugins and after comparing none.
    assert "2 plugins compared against 2 baselined" in capsys.readouterr().out


def test_baseline_then_check_is_a_closed_loop(gate, capsys):
    """The remedy the error messages tell a human to run has to actually work."""
    gate.plugin("sitemap", mean=6.5)
    assert gate.run("--baseline") == 0
    capsys.readouterr()
    assert gate.run("--check") == 0


if __name__ == "__main__":
    # `raise SystemExit(pytest.main(...))` and not a bare `pytest.main(...)`: the latter
    # RETURNS the status code and the process would exit 0 no matter what failed, which
    # is the exact exit-code laundering this file exists to catch elsewhere.
    raise SystemExit(pytest.main([__file__, "-q"]))
