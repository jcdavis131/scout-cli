"""
Real MCP SDK client implementation — bigbang/plugins/mcp/cli.py
Uses mcp Python SDK 1.28.1 with SSE -> streamable HTTP fallback.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import typer

from bigbang.core.cli_ux import examples_epilog, fail_agent
from bigbang.core.contract import make_plugin_app, ok
from bigbang.core.http_utils import sanitize_no_proxy_env
from bigbang.core.output import emit
from bigbang.core.plugin_loader import list_plugin_names
from bigbang.core.policy import enforce_or_raise, enforce_user_url_or_raise, load_manifest
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


app = make_plugin_app(
    "mcp",
    "🌐 MCP — client for any MCP server + serve Scout as MCP",
    examples=[
        "scout mcp manifest",
        "scout mcp serve",
        "scout mcp add notion https://mcp.notion.com/sse",
        "scout --json mcp list",
        "scout mcp list-tools notion",
        "scout mcp rm notion --force",
    ],
)

MCP_REG = Path.home() / ".local" / "share" / "bigbang" / "mcp_servers.json"
MCP_REG.parent.mkdir(parents=True, exist_ok=True)


def _manifest():
    return load_manifest(Path(__file__).resolve().parent)


def _load_mcp() -> Dict[str, Any]:
    if MCP_REG.exists():
        try:
            return json.loads(MCP_REG.read_text())
        except Exception:
            return {}
    return {}


def _save_mcp(d: Dict[str, Any]) -> None:
    enforce_or_raise(_manifest(), "fs_write", str(MCP_REG))
    MCP_REG.write_text(json.dumps(d, indent=2))


@app.command(
    "manifest",
    epilog=examples_epilog(["scout --json mcp manifest", "scout mcp serve"]),
)
def manifest():
    plugins = list_plugin_names()
    tools = []
    for n in plugins:
        tools.append(
            {
                "name": f"scout_{n}",
                "legacy": f"bb_{n}",
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
    emit(
        ok(
            {
                "name": "scout-cli",
                "version": "0.7.0",
                "description": "Scout judgment plane — MCP tools for agents",
                "tools": tools,
                "security": "vault 0600, policy caps, audit",
            },
            command="mcp manifest",
            example="scout mcp serve",
        ),
        command="mcp manifest",
    )


@app.command(
    "serve",
    epilog=examples_epilog(
        [
            "scout mcp serve",
            "scout mcp serve --sse --port 8787",
        ]
    ),
)
def serve(
    sse: bool = typer.Option(False, "--sse", help="Serve over SSE/HTTP instead of stdio"),
    port: int = typer.Option(8787, "--port", help="Port for --sse transport"),
):
    """Serve scout-cli plugins as a real MCP server (stdio by default)."""
    try:
        from bigbang.plugins.mcp.server import run_server
    except ImportError as e:
        fail_agent(
            f"mcp SDK not installed ({e}). Run: pip install 'mcp>=1.28.1'",
            command="mcp serve",
            example="pip install 'mcp>=1.28.1' && scout mcp serve",
        )
    # Blocks until the client disconnects (stdio) or the process is stopped (sse).
    run_server(transport="sse" if sse else "stdio", port=port)


@app.command(
    "add",
    epilog=examples_epilog(
        [
            "scout mcp add notion https://mcp.notion.com/sse",
            "scout mcp add notion https://mcp.notion.com/sse --dry-run",
        ]
    ),
)
def add_server(
    name: str = typer.Argument(..., help="name for MCP server"),
    url: str = typer.Argument(..., help="sse url"),
    dry_run: bool = typer.Option(False, "--dry-run", help="preview without writing"),
):
    enforce_user_url_or_raise(url, context="mcp add")
    if dry_run:
        emit(
            ok(
                {"would_add": name, "url": url, "registry": str(MCP_REG), "dry_run": True},
                command="mcp add",
                example=f"scout mcp add {name} {url}",
            ),
            command="mcp add",
        )
        return
    db = _load_mcp()
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
        ok(
            {
                "added": name,
                "url": url,
                "registry": str(MCP_REG),
                "next": f"scout mcp list-tools {name}",
            },
            command="mcp add",
            example=f"scout mcp list-tools {name}",
        ),
        command="mcp add",
    )


@app.command(
    "list",
    epilog=examples_epilog(["scout --json mcp list"]),
)
def list_servers():
    db = _load_mcp()
    emit(
        ok(
            {"mcp_servers": db, "count": len(db)},
            command="mcp list",
            example="scout mcp list-tools <name>",
        ),
        command="mcp list",
    )


@app.command(
    "rm",
    epilog=examples_epilog(
        [
            "scout mcp rm notion --force",
            "scout mcp rm notion --dry-run",
        ]
    ),
)
def rm_server(
    name: str = typer.Argument(..., help="MCP server name"),
    force: bool = typer.Option(False, "--force", "-f", help="required to remove"),
    dry_run: bool = typer.Option(False, "--dry-run", help="preview only"),
):
    """Remove a registered MCP server (and tool registry entry)."""
    db = _load_mcp()
    exists = name in db
    if dry_run:
        emit(
            ok(
                {"would_remove": name, "exists": exists, "dry_run": True},
                command="mcp rm",
                example=f"scout mcp rm {name} --force",
            ),
            command="mcp rm",
        )
        return
    if exists and not force:
        fail_agent(
            "Pass --force to remove an MCP server",
            command="mcp rm",
            example=f"scout mcp rm {name} --force",
            discover="scout mcp list",
        )
    if exists:
        del db[name]
        _save_mcp(db)
    removed_tool = unregister_tool(name) if exists else False
    emit(
        ok(
            {"removed": name, "existed": exists, "tool_unregistered": removed_tool},
            command="mcp rm",
            example="scout --json mcp list",
        ),
        command="mcp rm",
    )


@app.command(
    "list-tools",
    epilog=examples_epilog(["scout --json mcp list-tools notion"]),
)
def list_tools_cmd(server: str = typer.Argument(..., help="server name")):
    db = _load_mcp()
    if server not in db:
        fail_agent(
            f"{server} not found",
            command="mcp list-tools",
            example=f"scout mcp add {server} <url>",
            discover="scout mcp list",
        )
    url = db[server]["url"]
    enforce_user_url_or_raise(url, context="mcp list-tools")
    sanitize_no_proxy_env()
    try:
        _check_sdk()
        tools = list_mcp_tools_sync(url) if _CORE_CLIENT else []
        emit(
            ok(
                {"server": server, "url": url, "tools": tools, "count": len(tools)},
                command="mcp list-tools",
                example=f'scout mcp call {server} <tool> --args \'{{}}\'',
            ),
            command="mcp list-tools",
        )
    except Exception as e:
        fail_agent(
            str(e),
            command="mcp list-tools",
            example=f"scout mcp list-tools {server}",
            discover="Is the MCP server running? Try curl <url>",
        )


@app.command(
    "call",
    epilog=examples_epilog(
        [
            'scout mcp call notion search --args \'{"query":"notes"}\'',
            "scout --json mcp call notion search",
        ]
    ),
)
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
            discover="scout mcp list",
        )
    url = db[server]["url"]
    enforce_user_url_or_raise(url, context="mcp call")
    try:
        parsed = json.loads(args)
    except Exception:
        fail_agent(
            "args must be valid JSON object",
            command="mcp call",
            example=f'scout mcp call {server} {tool} --args \'{{"key":"value"}}\'',
        )
    sanitize_no_proxy_env()
    try:
        _check_sdk()
        result = call_mcp_tool_sync(url, tool, parsed) if _CORE_CLIENT else {}
        emit(
            ok(
                {"server": server, "tool": tool, "args": parsed, "result": result},
                command="mcp call",
                example=f"scout mcp list-tools {server}",
            ),
            command="mcp call",
        )
    except Exception as e:
        fail_agent(
            str(e),
            command="mcp call",
            example=f'scout mcp call {server} {tool} --args \'{{}}\'',
        )


def register(root):
    root.add_typer(app, name="mcp")


# Solo personal project, no connection to employer, built with public/free-tier only
