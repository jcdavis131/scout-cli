"""A test-named file that can exit the interpreter at import time kills the whole gate.

THE BUG THIS EXISTS FOR. `scripts/test_goat_audit.py` ran its checks at import time and
ended with a module-level `sys.exit(1 if FAIL else 0)`. pytest collects anything named
`test_*.py`, and collection IMPORTS the module — so that `sys.exit` fired during
collection. A SystemExit there is not a test failure that gets reported and moved past;
it aborts the session:

    INTERNALERROR> SystemExit: 0
    no tests ran in 0.24s          # exit code 3

Two things make this worth a permanent guard rather than a one-line fix and a shrug.

FIRST, IT FAILED WHILE PASSING. The exit status was `0` — the audit had passed. A green
check took down ~2500 tests in `tests/`, none of which ran. Nothing in the output said
"zero tests ran because of scripts/test_goat_audit.py"; it said 40 lines of
`importlib._bootstrap` frames, and the run's only summary line was `exit 3`.

SECOND, ONLY THE ROBOT COULD SEE IT. README, docs/FOUNDATION.md, docs/EXTENDING.md and
docs/ARCHITECTURE.md all say `pytest tests/`, which never walks `scripts/`. Every human
ran the passing command. The automated gate ran bare `pytest` from the repo root and had
been reporting a failure nobody could read for as long as the file had that shape.

WHY AST AND NOT A SUBPROCESS. Actually running `pytest --collect-only` from here would
test the real invariant more directly, but it re-imports every module in the suite and
would make this the slowest test in the file. Parsing is milliseconds and catches the
specific shape that bit us. The tradeoff is stated so the next person knows what this
does NOT cover: an import-time crash that is not an interpreter exit (a bare `raise`, an
`ImportError`, a module-scope `assert`) still aborts collection and is not caught here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Directories that are not ours to police, and that no gate collects from.
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


def _collectible_test_files() -> list[Path]:
    """Every file pytest's default `python_files` patterns would import."""
    found = []
    for path in REPO.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            found.append(path)
    return sorted(found)


def _is_main_guard(test: ast.expr) -> bool:
    """True for `__name__ == "__main__"`, the one branch collection never takes."""
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    )


def _names_an_interpreter_exit(node: ast.AST) -> str | None:
    """Name the construct if this node can terminate the process, else None."""
    if isinstance(node, ast.Raise):
        exc = node.exc
        if isinstance(exc, ast.Call):
            exc = exc.func
        if isinstance(exc, ast.Name) and exc.id == "SystemExit":
            return "raise SystemExit"
    if isinstance(node, ast.Call):
        func = node.func
        # sys.exit(...) / os._exit(...)
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            dotted = f"{func.value.id}.{func.attr}"
            if dotted in {"sys.exit", "os._exit"}:
                return f"{dotted}()"
        # bare exit(...) / quit(...) from the site builtins
        if isinstance(func, ast.Name) and func.id in {"exit", "quit"}:
            return f"{func.id}()"
    return None


def _import_time_exits(tree: ast.Module) -> list[tuple[int, str]]:
    """Find exits reachable on plain import.

    Descends the module body but stops at `def`/`class` (those bodies run when called,
    not when imported) and at `if __name__ == "__main__":` (pytest imports the module,
    so that branch is dead during collection — it is exactly where an exit BELONGS).
    """
    hits: list[tuple[int, str]] = []

    def descend(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                continue
            if isinstance(child, ast.If) and _is_main_guard(child.test):
                continue
            named = _names_an_interpreter_exit(child)
            if named is not None:
                hits.append((getattr(child, "lineno", 0), named))
            descend(child)

    descend(tree)
    return hits


def test_there_are_test_files_to_check():
    """Guard the guard: a bad glob here would make every assertion below vacuous."""
    files = _collectible_test_files()
    assert len(files) > 50, f"only found {len(files)} test files — the walk is broken"
    names = {p.name for p in files}
    assert "test_goat_audit.py" in names, "the file this guard was written for is missing"


@pytest.mark.parametrize(
    "path", _collectible_test_files(), ids=lambda p: p.relative_to(REPO).as_posix()
)
def test_no_test_file_can_exit_the_interpreter_at_import_time(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits = _import_time_exits(tree)
    assert not hits, (
        f"{path.relative_to(REPO).as_posix()} calls "
        + ", ".join(f"{name} at line {line}" for line, name in hits)
        + " at module level. pytest imports this file during COLLECTION, so that exit "
        "raises SystemExit before any test runs and turns the entire session into "
        "`INTERNALERROR ... no tests ran` (exit 3) — including when the exit status is "
        "0. Move it under `if __name__ == \"__main__\":`."
    )
