"""A subprocess spawned without `timeout=` can hang the whole pytest session: no failing
test, no summary line, no exit code at all — and "we never got an answer" is one bit away
from "there was nothing to report". `test_collection_is_not_booby_trapped.py` guards the
start of a run; this guards the middle of one. Adding it closed the last three gaps, in
`test_cli.py`, `test_dev_loop.py` and `test_policy.py`.

Not covered, deliberately: `subprocess.Popen` (its timeout belongs to a later
`.communicate()`/`.wait()` this check does not follow, so flagging the constructor would
teach a fix that does not work), `from subprocess import run` aliases (unused here), and
non-subprocess blocking such as a socket with no timeout. `scripts/install.py` is out by
construction, not by an exception list: the walk matches test-named files and conftests.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache",
             ".mypy_cache", ".ruff_cache"}

BLOCKING_CALLS = {"run", "call", "check_call", "check_output"}


def _test_named_files() -> list[Path]:
    """The sibling guard's walk: test-named files and conftests anywhere in the repo, not only under the `testpaths` roots a run collects from — a file parked outside them turns dangerous when someone moves it back in."""
    return sorted(
        p for p in REPO.rglob("*.py")
        if not any(part in SKIP_DIRS for part in p.parts)
        and (p.name.startswith("test_") or p.name.endswith("_test.py") or p.name == "conftest.py")
    )


def _all_calls() -> list[tuple[Path, int, str, bool]]:
    """Every `subprocess.<blocking>(...)` in those files; timed ones included too, so a caller can prove the search was not empty."""
    found: list[tuple[Path, int, str, bool]] = []
    for path in _test_named_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                    and func.value.id == "subprocess" and func.attr in BLOCKING_CALLS):
                continue
            # A `**kwargs` could carry a timeout we cannot see. Treat it as covered rather
            # than fail on the unprovable: a false alarm trains people to ignore the guard.
            # `timeout=None` is not unprovable, though — it is subprocess's own spelling of
            # "block until the child exits", so it must count as MISSING, not as present.
            timed = any(kw.arg is None or (kw.arg == "timeout" and not (
                isinstance(kw.value, ast.Constant) and kw.value.value is None))
                for kw in node.keywords)
            found.append((path, node.lineno, func.attr, timed))
    return found


def test_the_search_actually_finds_subprocess_calls():
    """Guard the guard: a broken walk or matcher makes the check below silently vacuous."""
    files = _test_named_files()
    assert len(files) > 50, f"only found {len(files)} files — the walk is broken"
    calls = _all_calls()
    assert len(calls) > 20, f"only {len(calls)} subprocess calls across {len(files)} files — the matcher is broken, so the timeout check below is asserting nothing"


def test_every_subprocess_call_in_the_suite_has_a_timeout():
    missing = [(p, line, attr) for p, line, attr, ok in _all_calls() if not ok]
    assert not missing, (
        "these subprocess calls block with no upper bound:\n"
        + "\n".join(
            f"  {p.relative_to(REPO).as_posix()}:{line}  subprocess.{attr}(...)"
            for p, line, attr in missing
        )
        + "\n\nA child that never exits hangs the whole pytest session: no failing test, no "
        "summary, no exit code — the gate reports nothing, which is not the same thing as "
        "green but is read that way. Pass a numeric `timeout=` (60 is usual here; `None` is "
        "not one) so a hang surfaces as a TimeoutExpired naming the test that hung."
    )
