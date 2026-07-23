"""
Scout CLI - main entry (formerly BigBang CLI)
`scout`, `bb`, `bigbang`, `dv`, `kitty` all point here via pyproject.toml scripts
Primary command is now `scout` — distinct from any work/meta tooling
"""

from __future__ import annotations

import os
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import typer
from rich.console import Console

from bigbang.core.cli_ux import examples_epilog
from bigbang.core.output import set_json_mode
from bigbang.core.plugin_loader import discover_plugins

# Detect which invocation name was used for nicer help
_invoked = Path(sys.argv[0]).name if sys.argv else "scout"
_prog_name = Path(_invoked).stem if _invoked else "scout"
if _prog_name in ("python", "python3", ""):
    _prog_name = "scout"


def _package_version() -> str:
    try:
        return version("scout-cli")
    except PackageNotFoundError:
        return "0.0.0-dev"


console = Console()


def _version_callback(value: bool) -> None:
    if not value:
        return
    ver = _package_version()
    # Honor --json if already present / about to be set via hoist.
    want_json = "--json" in sys.argv
    if want_json:
        set_json_mode(True)
        from bigbang.core.output import emit

        emit({"ok": True, "name": "scout-cli", "version": ver}, command="version")
    else:
        console.print(f"scout-cli {ver}")
    raise typer.Exit(0)


class ScoutTyper(typer.Typer):
    """Typer app that accepts --json in any position.

    `scout --json tools list` and `scout tools list --json` both work: any
    `--json` found after a subcommand is hoisted to the front so the shared
    root callback (which owns the option) always sees it.
    """

    def __call__(self, *args, **kwargs):
        argv = sys.argv[1:]
        if "--json" in argv:
            sys.argv = [sys.argv[0], "--json"] + [a for a in argv if a != "--json"]
        return super().__call__(*args, **kwargs)


# Root app - primary name scout, not bb/meta
app = ScoutTyper(
    name="scout",
    help=(
        "Scout CLI 🐾 — personal control plane (ex-BigBang). "
        "Local-first, agent-native, HOME-only. Ava-brained + RTX offload.\n\n"
        "Discover incrementally: [bold]scout --help[/bold] → "
        "[bold]scout <plugin> --help[/bold] → [bold]scout <plugin> <cmd> --help[/bold]."
    ),
    add_completion=True,
    no_args_is_help=True,
    rich_markup_mode="rich",
    epilog=examples_epilog(
        [
            "scout --version",
            "scout --help",
            "scout --json planes world   # digital-world entry for agents",
            "scout tools --help",
            "scout --json tools list",
            "scout --json system doctor",
            "scout auth set-token github --token <token>",
            "printf '%s' \"$TOKEN\" | scout secrets set GITHUB_TOKEN --stdin",
            'scout agent run "list my tools" --execute',
            "scout --json herd status",
            'scout herd start --label api --cmd "pytest -q"',
            "scout --json planes status",
            "scout --json planes compare",
            "scout skill teach --target dottie",
            "scout mcp serve   # stdio MCP for Cursor/Claude/Dottie",
            "SCOUT_YES=1 scout tools rm old-tool --force",
        ]
    ),
)


@app.callback()
def main(
    json: bool = typer.Option(
        False, "--json", help="Output structured JSON for agents"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logs"),
    version: bool = typer.Option(
        False,
        "--version",
        help="Print scout-cli version and exit",
        callback=_version_callback,
        is_eager=True,
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Bypass confirmations (sets SCOUT_YES=1 for this process)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview destructive actions (sets SCOUT_DRY_RUN=1 for this process)",
    ),
):
    """Scout root. Prefer flags over prompts; use --json for machine output."""
    del version  # handled by eager callback
    if yes:
        os.environ["SCOUT_YES"] = "1"
    if dry_run:
        os.environ["SCOUT_DRY_RUN"] = "1"
    set_json_mode(json)


# Auto-discover plugins
discover_plugins(app)


@app.command("doctor")
def doctor_cmd():
    """Check local environment, tools, and free-tier services."""
    # import here to avoid circular
    from bigbang.plugins.system.cli import run_doctor

    run_doctor()


if __name__ == "__main__":
    app()
