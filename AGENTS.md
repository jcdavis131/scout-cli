# AGENTS.md

## Cursor Cloud specific instructions

This repo holds two products in one git tree:

- **Scout CLI** (primary): Python Typer CLI packaged as `scout-cli` (module `bigbang/`). Entry points: `scout`, `bb`, `bigbang`, `dv`, `kitty`. Local-first, no database server (state lives under `~/.local/share/bigbang/`). See `README.md` and `pyproject.toml`.
- **arxiviq** (secondary): a zero-backend static site under `arxiviq/site/` (vanilla HTML/CSS/JS, no build step). See `arxiviq/ARCHITECTURE.md`.

### Environment / running

- Dependencies are installed into a virtualenv at `.venv/` (gitignored) by the update script. **Activate it first**: `source .venv/bin/activate`. This puts `scout`/`bb` on `PATH`. Without activation, use `.venv/bin/scout`.
- Creating the venv needs the system package `python3.12-venv` (already baked into the VM snapshot; not part of the update script).
- Standard commands (already documented in `pyproject.toml` / `README.md`): lint `ruff check .`, type-check `mypy bigbang`, test `pytest tests/`, run `scout system doctor`.

### Non-obvious gotchas

- **Run pytest with the venv activated** (`source .venv/bin/activate` then `pytest tests/`). Some tests in `tests/test_cli.py` spawn `python3 ...` subprocesses that resolve via `PATH`; if you run `.venv/bin/pytest` without activation, those tests fail with `ModuleNotFoundError: No module named 'typer'` because bare `python3` points at the system interpreter. With the venv active, all 79 tests pass.
- `ruff check .` currently reports pre-existing lint findings in the repo (unused imports, non-top-level imports); these are not caused by setup and do not block tests or running.
- **arxiviq**: serve locally with `python3 -m http.server 8080` from `arxiviq/site/`. It fetches telemetry from GitHub client-side, so a "data load failed" banner and empty charts are expected without network or baked data (run `python arxiviq/generate_data.py` to bake data, which additionally requires the sibling repo `ava-agi-factory-v6-4`). The page layout still renders.
- Optional services (`ollama` on `:11434`, Docker, Google Tasks, personal-graphify, scout-rtx) are not present here; the CLI degrades gracefully and `scout system doctor` reports them as missing/down without failing core flows.
