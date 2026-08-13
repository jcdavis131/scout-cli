"""A subprocess spawned without a timeout can hang the gate forever, and a hung gate
does not report a failure — it reports nothing.

WHY THIS FILE EXISTS. `tests/test_collection_is_not_booby_trapped.py` guards the start
of a run: a file that exits the interpreter during collection. This guards the middle of
one. `subprocess.run(...)` with no `timeout=` blocks until the child exits, and a child
that never exits blocks the whole session — no failing test, no summary line, no exit
code at all. Whatever is watching the gate then has to invent a verdict from a truncated
stream, and "we never got an answer" is one bit away from "there was nothing to report".

That is not the same shape as a slow suite, and this guard does not claim to fix one.
Measured in this worktree on 2026-08-13, with the repo's own `.venv` interpreter:

    .venv/Scripts/python -m pytest -q      killed at 540s, 66% of 2695 tests
    uv run --frozen --no-sync python -c    exit 0, immediate

So `uv` itself is healthy here and the pytest gate's ETIMEDOUT is the SUITE's wall clock,
not a broken launcher. A missing subprocess timeout is a second, independent way to reach
the same unreadable outcome, and it is the one that has no upper bound: a slow suite
finishes eventually, a hung child does not.

WHAT THE SUITE ALREADY DOES. The convention is real and nearly complete — at the time
this guard was written 58 of the 62 subprocess spawns under `tests/` and `scripts/`
already carried a `timeout=`, with values from 2 to 600. The three test-side gaps
(`test_cli.py` spawning the CLI, `test_dev_loop.py` spawning `git`, `test_policy.py`
spawning `cmd /c mklink`) were closed alongside this file. Every one of those three
spawns a process that can block on something outside the test: a CLI that reads stdin, a
git that wants a credential or waits on `index.lock`, a `cmd` that pops a prompt. This
guard exists so the count cannot quietly go back the other way — the convention was
being followed by habit and nothing was checking it.

WHAT THIS DOES NOT COVER, deliberately:

  * `subprocess.Popen`. Its timeout does not live on the constructor; it lives on the
    `.communicate(timeout=)` / `.wait(timeout=)` that follows, possibly in another
    function. Flagging the constructor would teach a fix that does not work. Nothing in
    the suite uses Popen today, so the hole is currently empty rather than merely
    tolerated.
  * `from subprocess import run`. This matches `subprocess.<fn>(...)` attribute calls
    only. Nothing in `tests/` or `scripts/` imports the names directly today (checked),
    and an alias would need its own resolution pass to catch honestly.
  * Non-subprocess blocking: a socket with no timeout, an `input()`, a `join()` on a
    thread that never ends. Same consequence, different shape, not this file's claim.
  * `scripts/install.py`, which calls `subprocess.check_call` with no timeout. An
    installer waiting on a network install is not the bug described above. It falls out
    of scope by construction rather than by an exception list: the walk below matches
    test-named files and conftests, and `install.py` is neither.

The walk is the sibling guard's, and inherits its framing rather than pytest's: it
matches the shape wherever it appears in the repo, not only under the `testpaths` roots
(`tests`, `scripts`) that a run actually collects from. A `test_*.py` parked outside
those roots is policed here and never executed by the gate — deliberate, since the way
such a file becomes dangerous is someone moving it back in.

WHY ONE TEST AND NOT ONE PER FILE. The sibling guard parametrizes per file so a failure
names its file in the test id. Here the offenders are what matters, not the files, and a
single assertion can list `path:line` for all of them in one message — the reader's next
move is to add `timeout=` at each site, not to bisect which file is at fault.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Mirrors the sibling guard's walk. Directories that are not ours and that no gate runs.
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

# The blocking subprocess entry points. `Popen` is excluded on purpose — see the module
# docstring; its timeout belongs to a later call this check does not follow.
BLOCKING_CALLS = {"run", "call", "check_call", "check_output"}


def _test_named_files() -> list[Path]:
    """Every test-named file in the repo, plus conftests — the sibling guard's walk.

    Named for what it matches, not for what pytest collects: those are the same set only
    while no `test_*.py` lives outside `testpaths`.
    """
    found = []
    for path in REPO.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if (
            path.name.startswith("test_")
            or path.name.endswith("_test.py")
            or path.name == "conftest.py"
        ):
            found.append(path)
    return sorted(found)


def _subprocess_calls(tree: ast.Module) -> list[tuple[int, str, bool]]:
    """Every `subprocess.<blocking>(...)` in the tree, with whether it passed a timeout.

    Returns the timed ones too, so the caller can assert it actually found something and
    is not reporting a clean bill of health from an empty search.
    """
    calls: list[tuple[int, str, bool]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "subprocess"):
            continue
        if func.attr not in BLOCKING_CALLS:
            continue
        has_timeout = any(kw.arg == "timeout" for kw in node.keywords)
        # `**kwargs` could carry a timeout we cannot see. Treat it as covered rather
        # than fail on something unprovable — a false alarm here trains people to
        # ignore this guard, which costs more than the case it would catch.
        if any(kw.arg is None for kw in node.keywords):
            has_timeout = True
        calls.append((node.lineno, func.attr, has_timeout))
    return calls


def _all_calls() -> list[tuple[Path, int, str, bool]]:
    found: list[tuple[Path, int, str, bool]] = []
    for path in _test_named_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, attr, has_timeout in _subprocess_calls(tree):
            found.append((path, lineno, attr, has_timeout))
    return found


def test_the_search_actually_finds_subprocess_calls():
    """Guard the guard: a broken walk or matcher would make the check below vacuous.

    This is the failure mode the check itself is about — an empty result reading exactly
    like a clean one. Without this, renaming `BLOCKING_CALLS` or breaking the glob turns
    the real assertion permanently green.
    """
    files = _test_named_files()
    assert len(files) > 50, f"only found {len(files)} files — the walk is broken"
    calls = _all_calls()
    assert len(calls) > 20, (
        f"only found {len(calls)} subprocess calls across {len(files)} files — the "
        "matcher is broken, so the timeout check below is asserting nothing"
    )


def test_every_subprocess_call_in_the_suite_has_a_timeout():
    missing = [(p, line, attr) for p, line, attr, ok in _all_calls() if not ok]
    assert not missing, (
        "these subprocess calls block with no upper bound:\n"
        + "\n".join(
            f"  {p.relative_to(REPO).as_posix()}:{line}  subprocess.{attr}(...)"
            for p, line, attr in missing
        )
        + "\n\nA child that never exits hangs the whole pytest session: no failing test, "
        "no summary, no exit code — the gate reports nothing, which is not the same "
        "thing as reporting green but is read that way. Pass `timeout=` (the suite's "
        "most common value is 60) so a hang surfaces as a TimeoutExpired naming the "
        "test that hung."
    )
