"""
Scout CLI - main entry (formerly BigBang CLI)
`scout`, `bb`, `bigbang`, `dv`, `kitty` all point here via pyproject.toml scripts
Primary command is now `scout` — distinct from any work/meta tooling
"""
import os
import sys
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

import typer
from rich.console import Console

from bigbang.core.cli_ux import examples_epilog
from bigbang.core.contract import ok
from bigbang.core.output import emit, set_json_mode
from bigbang.core.plugin_loader import discover_plugins


def _package_version() -> str:
    try:
        return pkg_version("scout-cli")
    except PackageNotFoundError:
        return "0.7.0"


def _version_callback(value: bool) -> None:
    """Eager --version: print and exit before Typer requires a subcommand."""
    if not value:
        return
    ver = _package_version()
    # Respect --json if already hoisted ahead of --version by ScoutTyper.
    if "--json" in sys.argv:
        set_json_mode(True)
        emit(
            ok(
                {"name": "scout-cli", "version": ver, "module": "bigbang"},
                command="scout --version",
                example="scout --json planes thesis",
            ),
            command="scout --version",
        )
    else:
        typer.echo(f"scout-cli {ver}")
    raise typer.Exit(0)


# Detect which invocation name was used for nicer help
_invoked = Path(sys.argv[0]).name if sys.argv else "scout"
_prog_name = os.path.splitext(_invoked)[0] if _invoked else "scout"
if _prog_name in ("python", "python3", ""):
    _prog_name = "scout"

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
            "scout --help",
            "scout tools --help",
            "scout --json tools list",
            "scout --json system doctor",
            "scout auth set-token github --token <token>",
            "printf '%s' \"$TOKEN\" | scout secrets set GITHUB_TOKEN --stdin",
            "scout agent run \"list my tools\" --execute",
            "scout --json herd status",
            'scout herd start --label api --cmd "pytest -q"',
            "scout --json planes status",
            "scout --json planes compare",
            "scout skill teach --target dottie",
            "scout mcp serve   # stdio MCP for Cursor/Claude/Dottie",
        ]
    ),
)
console = Console()

@app.callback()
def main(
    json: bool = typer.Option(False, "--json", help="Output structured JSON for agents"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logs"),
    version: bool = typer.Option(
        False,
        "--version",
        help="Show package version and exit",
        is_eager=True,
        callback=_version_callback,
    ),
):
    """Scout root. Prefer flags over prompts; use --json for machine output."""
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
