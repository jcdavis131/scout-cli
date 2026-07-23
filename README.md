# Scout CLI

A personal, local-first control plane: one CLI (`scout`) that registers external tools (OpenAPI specs, MCP servers), calls them through a capability-policy layer, and writes an audit record for every invocation.

**Solo personal project, no connection to employer, built with public/free-tier only.**

Current version: 0.7.1 (Python 3.11+, MIT). The project started as "BigBang", so the internal package is still `bigbang/` and the aliases `bb`, `bigbang`, `dv`, and `kitty` are kept for compatibility. The primary home for this code is the [`dottie`](https://github.com/jcdavis131/dottie) monorepo (`apps/scout-cli`); this repo is the standalone twin.

## What it does

- **Tool registry** — `scout tools add <name> --type openapi|mcp --url ...` puts any HTTP API or MCP server in a local registry (`~/.local/share/bigbang/registry.json`), callable as `scout tools call` or via the agent planner.
- **Secrets vault** — `scout secrets set/get/list/rm`. File store at `~/.local/share/bigbang/secrets.json` (mode 0600), OS keyring read-fallback, `BB_SECRET_*` env override. Values are never printed or logged.
- **Capability policy** — every plugin declares `capabilities` (network domains, filesystem write, allowed secrets) in its `manifest.yaml`. Default deny, checked before execution; network calls go through a domain allowlist persisted at `~/.config/bigbang/policy.yaml`.
- **Audit trail** — every invocation is appended to `~/.local/share/bigbang/audit.jsonl` (timestamp, command, args hash, duration). `scout system audit` tails it.
- **MCP, both directions** — `scout mcp serve` exposes each plugin as an MCP tool over stdio (or `--sse --port 8787`); `scout mcp add/call` acts as a client for external MCP servers.
- **Agent planner** — `scout agent run "..."` turns a natural-language request into a plan of registered tool calls, with the same policy checks applied.
- **`--json` everywhere** — every command has a machine-readable output mode, so agents can drive the CLI directly.

## Install

```bash
git clone https://github.com/jcdavis131/scout-cli
cd scout-cli
pip install -e ".[all]"
scout --help
scout system doctor
```

## Quickstart

```bash
# secrets stay out of the repo
scout secrets set GITHUB_TOKEN ghp_xxx

# register and use tools
scout tools add github --type openapi --url https://api.github.com/openapi.json
scout tools list
scout --json tools search github

# serve Scout itself as an MCP server (Claude Desktop / Cursor)
scout mcp serve
# {"mcpServers": {"scout": {"command": "scout", "args": ["mcp", "serve"]}}}

# audit and policy
scout system audit --n 20
scout system policy
```

## Plugins

Plugins are auto-discovered from `bigbang/plugins/<name>/` (a `manifest.yaml` plus a `cli.py`); dropping a folder in adds both a `scout <name>` command and a `scout_<name>` MCP tool. `scout system scaffold <name>` generates the skeleton.

Core plugins: `secrets`, `auth`, `tools`, `mcp`, `agent`, `system`, `skill`, `herd` (background-session ledger: start/wait/read). The rest (`ava`, `rtx`, `graphify`, `vector`, `write`, `lab`, `brain`, `tasks`, `tennis`, `family`, `planes`, `rft`) integrate personal projects and depend on local infrastructure — they load fine but won't do much on a fresh machine.

## Development

```bash
pip install -e ".[dev]"
pytest tests/
ruff check .
```

CI runs the ruff lint (`.github/workflows/lint.yml`). Docs: [architecture](docs/ARCHITECTURE.md), [security model](docs/SECURITY.md), [extending](docs/EXTENDING.md). The RTX offload companion repo is [`scout-rtx`](https://github.com/jcdavis131/scout-rtx), wired up as described in [INTEGRATION.md](INTEGRATION.md).

## Status

Active personal project. The registry/vault/policy/audit core and the MCP server/client are the stable parts; the personal-project plugins change frequently and track the `dottie` monorepo. Roadmap items (container isolation for tool execution, vault encryption at rest, plugin signing) are listed as roadmap, not shipped features.

## Disclaimer

Solo personal project, no connection to employer, built with public/free-tier only. Security first, local-first, free to host. MIT.
