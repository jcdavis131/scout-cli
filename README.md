# Scout CLI

A personal, local-first control plane: one CLI (`scout`) that registers external tools (OpenAPI specs, MCP servers), calls them through a capability-policy layer, and writes an audit record for every invocation.

**Solo personal project, no connection to employer, built with public/free-tier only.**

Current version: 0.8.0 (Python 3.10+, MIT). The project started as "BigBang", so the internal package is still `bigbang/` and the aliases `bb`, `bigbang`, `dv`, and `kitty` are kept for compatibility. Canonical development happens in the [`dottie`](https://github.com/jcdavis131/dottie) monorepo at `apps/scout-cli`; this repo is the distribution mirror and receives snapshots of that tree.

## What it does

- **Tool registry** — `scout tools add <name> --type openapi|mcp --url ...` puts any HTTP API or MCP server in a local registry (`~/.local/share/bigbang/registry.json`), callable as `scout tools call` or via the agent planner.
- **Secrets vault** — `scout secrets set/get/list/rm`. File store at `~/.local/share/bigbang/secrets.json` (mode 0600), OS keyring read-fallback, `BB_SECRET_*` env override. Values are never printed or logged.
- **Capability policy** — every plugin declares `capabilities` (network domains, filesystem write, allowed secrets) in its `manifest.yaml`. Default deny on every axis, checked before execution. Network calls additionally go through a persisted user URL allowlist (`~/.config/bigbang/policy.yaml`) that is also default-deny: an empty allowlist grants nothing.
- **Audit trail** — every invocation is appended to `~/.local/share/bigbang/audit.jsonl` (timestamp, command, redacted args, status, duration). `scout system audit` tails it.
- **MCP, both directions** — `scout mcp serve` exposes each plugin as an MCP tool over stdio (or `--sse --port 8787`); `scout mcp add/call` acts as a client for external MCP servers.
- **Meta-MCP namespaces** — group registered MCP servers, disable individual downstream tools per namespace, and serve a whole namespace through one endpoint. See below.
- **Harness** — `scout harness run` is an end-to-end run loop (route, plan, execute, checkpoint/timeline, critic) with deterministic local executors and optional learned routing. See below.
- **Agent planner** — `scout agent run "..."` turns a natural-language request into a plan of registered tool calls, with the same policy checks applied.
- **`--json` everywhere** — every command has a machine-readable output mode, so agents can drive the CLI directly.

## Harness

The `harness` plugin carries the routing and execution loop that the dottie training pipeline builds on:

- `scout harness route "<goal>"` — heuristic intent/complexity classifier that assigns one of five tiers (`deterministic`, `llm`, `deep_research`, `action_operator`, `agentic_epic`) and a routed agent roster.
- `scout harness route --learned` — augments the heuristic result with a learned tier prediction when champion weights exported by the dottie training lane are present (`apps/ava-factory/reports/orchestrator/champion_weights.json`). The heuristic envelope stays authoritative; on any failure (weights missing, invalid, numpy unavailable) the output records the specific fallback reason rather than guessing.
- `scout harness run "<goal>"` — route → plan → execute → checkpoint/timeline → critic. Executors are deterministic and local: pure functions over the goal text and prior artifacts, no external model calls. Latencies are measured with `perf_counter`; provenance is labeled on every record.
- `mcp:<server>__<tool>` goals are disabled by default: `scout harness run "mcp:..."` requires `--mcp-namespace`, and the call still passes the fail-closed policy gates — including the default-deny user URL allowlist — before any network traffic.
- `scout harness checkpoint list|show` and `scout harness timeline append|stats` — disk-backed checkpoints and an append-only `timeline.jsonl` per run.

## Meta-MCP layer

The `mcp` plugin is both a client for external MCP servers and a server for Scout itself:

- **Client** — `scout mcp add <name> <url>` (the URL is checked against the default-deny user allowlist before registration), `scout mcp list-tools <server>`, `scout mcp call <server> <tool>`.
- **Server** — `scout mcp serve` exposes each plugin as a `scout_<plugin>` MCP tool over stdio by default, or SSE/HTTP with `--sse --port 8787`. `bb_<plugin>` aliases are kept for compatibility.
- **Namespaces** — `scout mcp ns create|list|delete|add-server|remove-server|disable-tool|enable-tool|tools|call` group registered servers, aggregate their tools under `<server>__<tool>` names, and honor per-namespace tool disables (`scout mcp ns disable-tool <ns> <server>__<tool>`).
- **Unified serve** — `scout mcp serve --namespace <ns>` serves the Scout plugin tools plus the namespace's enabled downstream tools from one endpoint.

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

# serve Scout itself as an MCP server
scout mcp serve
# {"mcpServers": {"scout": {"command": "scout", "args": ["mcp", "serve"]}}}

# meta-MCP: group servers, prune tools, serve unified
scout mcp ns create work
scout mcp ns add-server work github
scout mcp ns disable-tool work github__delete_repo
scout mcp serve --namespace work

# route and run a goal through the harness
scout --json harness route "compare two payment providers"
scout --json harness run "summarize repo status"

# audit and policy
scout system audit --n 20
scout system policy
```

## Plugins

Plugins are auto-discovered from `bigbang/plugins/<name>/` (a `manifest.yaml` plus a `cli.py`); dropping a folder in adds both a `scout <name>` command and a `scout_<name>` MCP tool. `scout system scaffold <name>` generates the skeleton. The current tree ships 63 plugins.

Core plugins: `secrets`, `auth`, `tools`, `mcp`, `agent`, `harness`, `system`, `skill`, `herd` (background-session ledger: start/wait/read). The rest (`ava`, `rtx`, `graphify`, `vector`, `write`, `lab`, `brain`, `tasks`, `tennis`, `family`, `planes`, `rft`, and others) integrate personal projects and depend on local infrastructure — they load fine but won't do much on a fresh machine.

## Development and releases

Development happens in the [`dottie`](https://github.com/jcdavis131/dottie) monorepo at `apps/scout-cli`; issues and changes land there. This repo receives snapshots of that tree and exists so the CLI can be cloned and installed standalone.

Snapshot: dottie@66886a7

```bash
pip install -e ".[dev]"
pytest tests/
ruff check .
```

`pytest tests/` is the suite. Bare `pytest` also picks up `scripts/test_goat_audit.py` (the
GOAT audit's own tests) — `testpaths` in `pyproject.toml` pins both roots, so the two
commands differ only in that one deliberate way.

**The suite is expected to be fully green, so treat any red as a real regression.** It was
not, for a while: a handful of tests asserted the *developer's machine layout* rather than
the product — the plugin resolvers for `apps/scout-rtx` and `apps/ava-factory`, which are
companion trees that do not exist in this standalone mirror, so the resolvers correctly
fell through to a `$HOME` path that could not exist under the throwaway test HOME. Those
now build their own layout in `tmp_path` and pin resolution *order*. There is no longer an
"ignore those" list. `addopts = "-ra"` means every skip prints its reason, so a check that
declines to run cannot be mistaken for one that passed.

A full run takes roughly nine minutes. Rather than quote a pass count that goes stale on
every commit, here is the thing worth checking, because it is the difference between two
environments that used to look identical:

```bash
# on an install missing `mcp`, this exits 1 -- not 0
pytest tests/test_hard_deps.py tests/test_mcp_meta.py tests/test_mcp_serve.py
# 5 failed, 16 passed, 1 skipped
```

`mcp>=1.28.1` is a *hard* dependency in `pyproject.toml`, but four cases in
`tests/test_mcp_meta.py` used to guard on `pytest.importorskip("mcp")`. A missing `mcp` and
a working `mcp` therefore produced the same exit code: the whole MCP server surface could
sit out behind a green summary line, and you only found out by reading the skip reasons.
Those four now call `hard_deps.require_mcp()`, which **fails** instead of skipping, and
`tests/test_hard_deps.py` checks every name in `[project].dependencies` directly — one
named failure per missing dependency, not a quieter summary. Those five failures are the
guard working; `pip install -e ".[dev]"` turns them into passes.

`tests/test_mcp_serve.py` keeps `importorskip` on purpose. It guards at *module* level, and
a `pytest.fail` during import is a collection error that aborts the whole session — a
missing `mcp` would run 0 of ~2650 tests instead of failing 5, which is the same
cannot-run-reads-as-green shape one level up. `test_hard_deps.py` is the loud guard; that
module-level skip is just how one file declines.

`tests/test_mcp_exit_codes.py` is deliberately not guarded either way — it monkeypatches
the SDK boundary instead of importing across it, so it is the one part of the mcp surface
still checked when `mcp` is absent. It was written after that gap hid a real bug: `mcp
list-tools`, `mcp call` and `mcp ns call` printed an `{"error": …}` object and exited
**0**, so `bb mcp call srv deploy && ship` ran `ship` against a tool that never executed.
All three now exit 1, matching `mcp serve`. `mcp ns tools` still exits 0 with a partial
listing — per-server failures come back in an `errors` map, which is that command's
contract, not a laundered exit code.

The remaining skips are environmental, and none is a check that *should* have run: the
`bundles/cli.sh` wrapper check (needs `SCOUT_BUNDLES_CLI_SH` pointed at a real wrapper;
that artifact is not part of this checkout), `acne.tools` and `skills.state_store`
(companion `dottie` workspace members, absent from this standalone mirror), and one
POSIX-only permission-bit test that cannot express `0600` on Windows.

CI runs a non-blocking `ruff check` (`.github/workflows/lint.yml`); lint findings are fixed in `dottie`, not here, since snapshots overwrite this tree. Docs: [architecture](docs/ARCHITECTURE.md), [security model](docs/SECURITY.md), [extending](docs/EXTENDING.md). The RTX offload companion repo is [`scout-rtx`](https://github.com/jcdavis131/scout-rtx), wired up as described in [INTEGRATION.md](INTEGRATION.md).

## Ecosystem

Scout CLI is the harness inside a larger closed loop (mapped in dottie's `docs/ECOSYSTEM.md`): harness runs leave measured traces, traces become router training labels, and the trained router is promotion-gated before it is served back — as `scout harness route --learned` locally and as `/api/route` on the live Validation Lab surface at [www.slasso.com](https://www.slasso.com) (dashboard plus `/api/health`).

## Status

Active personal project (as of 2026-08-09). The registry/vault/policy/audit core, the MCP server/client with namespaces, and the harness run loop are the stable parts; the personal-project plugins change frequently and track the `dottie` monorepo. Roadmap items (container isolation for tool execution, vault encryption at rest, plugin signing) are listed as roadmap, not shipped features.

## Disclaimer

Solo personal project, no connection to employer, built with public/free-tier only. Security first, local-first, free to host. MIT.
