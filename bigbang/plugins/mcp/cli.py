"""
Real MCP SDK client implementation — bigbang/plugins/mcp/cli.py
Uses mcp Python SDK 1.28.1 with SSE -> streamable HTTP fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from bigbang.core.cli_ux import (
    effective_dry_run,
    effective_force,
    examples_epilog,
    fail_agent,
    is_interactive,
)
from bigbang.core.http_utils import sanitize_no_proxy_env
from bigbang.core.output import emit
from bigbang.core.plugin_loader import list_plugin_names
from bigbang.core.policy import enforce_user_url_or_raise
from bigbang.core.registry import list_tools, register_tool, unregister_tool

sanitize_no_proxy_env()

try:
    from bigbang.core.mcp_client import call_mcp_tool_sync, list_mcp_tools_sync

    _CORE_CLIENT = True

    def _check_sdk():
        return True
except ImportError:
    list_mcp_tools_sync = None  # type: ignore
    call_mcp_tool_sync = None  # type: ignore
    _CORE_CLIENT = False

    def _check_sdk():  # type: ignore
        raise RuntimeError("mcp SDK not installed. pip install mcp")


app = typer.Typer(
    name="mcp",
    help="🌐 MCP — client for any MCP server + serve scout as MCP (World plane)",
    no_args_is_help=True,
    epilog=examples_epilog(
        [
            "scout mcp add notion https://mcp.notion.com/sse",
            "scout mcp add notion https://mcp.notion.com/sse --dry-run",
            "scout --json mcp list",
            "scout mcp rm notion --force",
            "scout mcp serve",
        ]
    ),
)

MCP_REG = Path.home() / ".local" / "share" / "bigbang" / "mcp_servers.json"
MCP_REG.parent.mkdir(parents=True, exist_ok=True)


def _load_mcp() -> dict[str, Any]:
    if MCP_REG.exists():
        try:
            return json.loads(MCP_REG.read_text())
        except Exception:
            return {}
    return {}


def _save_mcp(d: dict[str, Any]) -> None:
    MCP_REG.write_text(json.dumps(d, indent=2))


@app.command("manifest")
def manifest():
    plugins = list_plugin_names()
    tools = []
    for n in plugins:
        tools.append(
            {
                "name": f"scout_{n}",
                "description": f"Scout {n} plugin",
                "type": "scout_internal",
            }
        )
    external = list_tools()
    for name, m in external.items():
        if m.get("type") == "mcp":
            tools.append(
                {
                    "name": name,
                    "description": m.get("description", "external mcp"),
                    "url": m.get("url"),
                }
            )
    data = {
        "name": "scout-cli",
        "version": "0.7.1",
        "description": "One CLI for agents to interact with the digital world — tools, MCP, auth, policy",
        "tools": tools,
        "security": "vault 0600, policy caps, audit",
        "aliases": {"bb_*": "legacy name for scout_* tools"},
    }
    emit(data, command="mcp manifest")


@app.command("serve")
def serve(
    sse: bool = typer.Option(
        False, "--sse", help="Serve over SSE/HTTP instead of stdio"
    ),
    port: int = typer.Option(8787, "--port", help="Port for --sse transport"),
):
    """Serve scout-cli plugins as a real MCP server (stdio by default)."""
    try:
        from bigbang.plugins.mcp.server import run_server
    except ImportError as e:
        emit(
            {"error": f"mcp SDK not installed ({e}). Run: pip install 'mcp>=1.28.1'"},
            command="mcp serve",
        )
        raise typer.Exit(1) from e
    # Blocks until the client disconnects (stdio) or the process is stopped (sse).
    run_server(transport="sse" if sse else "stdio", port=port)


@app.command(
    "add",
    epilog=examples_epilog(
        [
            "scout mcp add notion https://mcp.notion.com/sse",
            "scout mcp add notion https://mcp.notion.com/sse --dry-run",
            "scout --json mcp list-tools notion",
        ]
    ),
)
def add_server(
    name: str = typer.Argument(..., help="name for MCP server"),
    url: str = typer.Argument(..., help="sse url"),
    dry_run: bool = typer.Option(False, "--dry-run", help="preview without writing"),
):
    """Register an external MCP server in the World plane registry."""
    # Real check against the persisted user allowlist (default-deny), not a
    # manifest constructed to allow the exact URL being checked.
    enforce_user_url_or_raise(url, context="mcp add")
    dry = effective_dry_run(dry_run)
    if dry:
        emit(
            {
                "would_add": name,
                "url": url,
                "dry_run": True,
                "registry": str(MCP_REG),
            },
            command="mcp add",
        )
        return
    db = _load_mcp()
    existed = name in db
    db[name] = {"url": url, "type": "mcp", "added": True}
    _save_mcp(db)
    register_tool(
        name,
        {
            "type": "mcp",
            "url": url,
            "description": f"MCP server {name}",
            "tags": ["mcp", "external"],
            "capabilities": {"network": {"enabled": True, "domains": [url]}},
        },
    )
    emit(
        {
            "added": name,
            "url": url,
            "existed": existed,
            "registry": str(MCP_REG),
            "next": f"scout mcp list-tools {name}",
            "discover": "scout --json planes world",
        },
        command="mcp add",
    )


@app.command(
    "rm",
    epilog=examples_epilog(
        [
            "scout mcp rm notion --dry-run",
            "scout mcp rm notion --force",
            "SCOUT_YES=1 scout mcp rm notion",
        ]
    ),
)
def rm_server(
    name: str = typer.Argument(..., help="MCP server name to remove"),
    force: bool = typer.Option(False, "--force", "-f", help="skip confirmation"),
    dry_run: bool = typer.Option(False, "--dry-run", help="preview without deleting"),
):
    """Remove an MCP server from the World registry (idempotent with --force)."""
    db = _load_mcp()
    exists = name in db
    dry = effective_dry_run(dry_run)
    if dry:
        emit(
            {
                "would_delete": name,
                "exists": exists,
                "dry_run": True,
                "registry": str(MCP_REG),
            },
            command="mcp rm",
        )
        return
    if exists and not effective_force(force) and is_interactive():
        typer.confirm(f"Remove MCP server {name}?", abort=True)
    elif exists and not effective_force(force) and not is_interactive():
        fail_agent(
            "Refusing to remove MCP server without --force in non-interactive mode",
            command="mcp rm",
            example=f"scout mcp rm {name} --force",
            discover="scout --json mcp list",
        )
    if exists:
        del db[name]
        _save_mcp(db)
    unregistered = unregister_tool(name)
    emit(
        {
            "deleted": name,
            "ok": exists or unregistered,
            "existed": exists,
            "unregistered_tool": unregistered,
        },
        command="mcp rm",
    )


@app.command("list")
def list_servers():
    db = _load_mcp()
    emit({"mcp_servers": db, "count": len(db)}, command="mcp list")


@app.command("list-tools")
def list_tools_cmd(server: str = typer.Argument(..., help="server name")):
    db = _load_mcp()
    if server not in db:
        fail_agent(
            f"{server} not found",
            command="mcp list-tools",
            example=f"scout mcp add {server} <url>",
            discover="scout --json mcp list",
        )
    url = db[server]["url"]
    enforce_user_url_or_raise(url, context="mcp list-tools")
    sanitize_no_proxy_env()
    try:
        _check_sdk()
        tools = list_mcp_tools_sync(url) if _CORE_CLIENT else []
        emit(
            {"server": server, "url": url, "tools": tools, "count": len(tools)},
            command="mcp list-tools",
        )
    except Exception as e:
        emit(
            {
                "server": server,
                "url": url,
                "error": str(e),
                "hint": "Is the MCP server running? Try curl <url>",
                "example": f"scout mcp list-tools {server}",
            },
            command="mcp list-tools",
        )


@app.command("call")
def call_tool(
    server: str = typer.Argument(...),
    tool: str = typer.Argument(...),
    args: str = typer.Option("{}", help="json args"),
):
    db = _load_mcp()
    if server not in db:
        fail_agent(
            f"{server} not found",
            command="mcp call",
            example=f"scout mcp add {server} <url>",
            discover="scout --json mcp list",
        )
    url = db[server]["url"]
    enforce_user_url_or_raise(url, context="mcp call")
    try:
        parsed = json.loads(args)
    except Exception:
        parsed = {}
    sanitize_no_proxy_env()
    try:
        _check_sdk()
        result = call_mcp_tool_sync(url, tool, parsed) if _CORE_CLIENT else {}
        emit(
            {"server": server, "tool": tool, "args": parsed, "result": result},
            command="mcp call",
        )
    except Exception as e:
        emit(
            {
                "server": server,
                "tool": tool,
                "args": parsed,
                "error": str(e),
                "example": f'scout mcp call {server} {tool} --args \'{{"q":"x"}}\'',
            },
            command="mcp call",
        )


def register(root):
    root.add_typer(app, name="mcp")


# Solo personal project, no connection to employer, built with public/free-tier only
