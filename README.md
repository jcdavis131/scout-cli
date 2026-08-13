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
uv sync --locked --extra dev   # the environment uv.lock pins; --locked so it cannot rewrite it
uv run pytest tests/
uv run ruff check .
```

`pytest tests/` is the suite. Bare `pytest` also picks up `scripts/test_goat_audit.py` (the
GOAT audit's own tests) — `testpaths` in `pyproject.toml` pins both roots, so the two
commands differ only in that one deliberate way.

**`uv.lock` is what pins this environment, so run the gates through `uv`.** `pip install -e
".[dev]"` also works and every command below is written to be runnable either way — but the
two do not produce the same environment, and only one of them is the one this repo
describes. `pyproject.toml` declares floors (`httpx>=0.27`, `mcp>=1.28.1`); `uv.lock` names
versions (httpx 0.28.1, mcp 1.28.1). pip re-resolves those floors against whatever the
machine and the index hand it that day, which is a *different* environment that happens to
be legal. That distinction is not pedantic here: with uv absent, the pinned suite does not
run at all, and a gate that could not run is not a gate that passed. If you have no uv,
say so when you report the result, and use the triage command below to establish which
environment you actually measured.

`--locked` is load-bearing rather than decorative: bare `uv sync` re-resolves and *rewrites*
`uv.lock` when `pyproject.toml` has drifted from it, so the setup step would quietly redefine
the pin the gate is supposed to be checking against. `--locked` fails instead and tells you
the lock is stale, which is a thing you want to find out deliberately.

`python scripts/goat_audit.py --check` is a second gate, run by hand rather than by CI: it
re-scores every plugin against the accepted `.goat_baseline.json` and exits **1** if one
regressed, or if the baseline covers a plugin a whole-tree run did not score — asking for a
subset with `--plugin` is exempt, since naming one plugin is not losing the other 62. It
exits **2**, never 0, when the comparison *could not run* — no baseline file, no plugins
found, a `--plugin` name that is not on disk — because each of those used to print "no
regressions vs baseline" after comparing against nothing. Exit 0 now names the two counts it
compared, so a green line cannot be read without seeing how much it covered.

**That gate is red in this tree right now, on one known regression — read this before you
assume you caused it.** Measured 2026-08-13:

```bash
python scripts/goat_audit.py --check
# REGRESSION: agents 6.83 -> 6.67     (exit 1; the file it compares against is unchanged —
#                                      --check never writes .goat_baseline.json)
```

It is one dimension on one plugin. `.goat_baseline.json` was recorded at `7c02e7a`, and
`bigbang/plugins/agents/cli.py` has changed exactly once since, in `14e878a` — the fix that
stopped the agents plugin writing checkpoints into the cwd. That fix added 13 lines to
`_triple_write()`, carrying it across the audit's 80-line D5 threshold — the run now reports
`D5: _triple_write() is 81 lines` and the score falls 41/6 to 40/6. The regression *is* the
cost of a real bug fix, correctly reported by a heuristic that does not know the difference.

Both honest resolutions are a maintainer call and neither is done here: split
`_triple_write()` so the plugin actually earns the point back, or re-run `--baseline` to
accept 6.67 as the new floor with that reasoning in the commit message. What is not
acceptable is re-accepting the baseline as routine hygiene, because a baseline refreshed
whenever it goes red is a gate that can only ever say what already happened. It is recorded
here rather than fixed so that the next red on this gate is distinguishable from this one —
an unexplained red retires a gate just as thoroughly as an unexplained green.

**On an environment that matches `pyproject.toml` the suite is fully green, so red means
one of exactly two things — and they are not interchangeable.** Either the code regressed,
or the environment does not match the manifest. Triage takes under a second:

```bash
python -m pytest tests/test_hard_deps.py -q
# exit 0 -> the environment matches the manifest, so a red suite is a real regression
# exit 1, failures naming dependencies -> each one names the dependency that does not
#           match. Fix the environment (`uv sync --locked --extra dev`, or `pip install
#           -e ".[dev]"`) before reading anything else in the run: the rest of it was
#           exercising dependencies the manifest says are not the ones it was written
#           against.
# exit 1, "No module named pytest" -> nothing ran. Not a dependency verdict.
```

Invoked as `python -m pytest`, not bare `pytest`, because the two are not
interchangeable here and the difference is the failure this whole section is about. Bare
`pytest` is a console script that need not be on `PATH` even where pytest is perfectly
importable; when it is not there a POSIX shell answers **127** and `command not found` — a
third outcome neither arm above covers, and the one you actually hit on a fresh checkout.
Measured in this tree on 2026-08-13: bare `pytest tests/test_hard_deps.py -q` exits 127
and measures nothing, while `python -m pytest tests/test_hard_deps.py -q` exits 1 and
reports `3 failed, 25 passed`. Naming the interpreter is what makes the 0-versus-1
distinction the block rests on reachable at all. That is also why the exit-1 arm is keyed
to the failures and not to the number: `python -m` returns 1 for a missing pytest module
too, and "no pytest" is not a statement about your dependencies. Where uv *is* installed,
triage through it the same way rather than mixing the two environments the section above
distinguishes.

**Read the exit code unpiped.** Every arm above is keyed to it, and a shell pipeline
reports the *last* stage's status, not pytest's. Measured in this tree on 2026-08-13:
`python -m pytest tests/test_hard_deps.py -q` exits **1**, while the same command with
`| tail -1` appended exits **0** — a broken environment landing in the arm that says the
environment matches and a red suite is therefore a real regression. That is the precise
inversion this block exists to prevent, and paging a long run through `tail`, `less` or
`tee` is the obvious way to run it rather than an exotic one. Redirecting to a log file
(`> log.txt`) is safe — it is interposing another *process* that swallows the status, not
the redirection. In bash, read
`${PIPESTATUS[0]}` instead of `$?` when you pipe.

In this checkout on 2026-08-13 the triage command reports `3 failed, 25 passed` in 0.45s
— no `mcp` installed at all, and httpx 0.24.1 against a declared `httpx>=0.27`. Those
failures are the guard working, not a regression, which is precisely why the claim opening
this section is conditional: a
permanently red gate teaches people to stop reading it just as effectively as a
permanently green one. The full run on that same environment is red for that reason and
no other — 7 failed, 0 errors, and all 7 are the environment: these 3 plus the 4 in
`tests/test_mcp_meta.py` that call `hard_deps.require_mcp()`. Nothing else in the suite
is red, which is the claim the triage command above exists to let you check in a second
instead of nine minutes.

Full green is a recent state. A handful of tests asserted the *developer's machine layout*
rather than the product — the plugin resolvers for `apps/scout-rtx` and `apps/ava-factory`,
which are companion trees that do not exist in this standalone mirror, so the resolvers
correctly fell through to a `$HOME` path that could not exist under the throwaway test
HOME. Those now build their own layout in `tmp_path` and pin resolution *order*. There is
no longer an "ignore those" list. `addopts = "-ra"` means every skip prints its reason, so
a check that declines to run cannot be mistaken for one that passed.

A full run takes roughly nine minutes. Rather than quote a pass count that goes stale on
every commit, here are both sides of the same three files that touch the MCP surface —
the two environments that used to look identical, told apart:

```bash
# on an environment that does not match pyproject.toml, this exits 1 -- not 0
python -m pytest tests/test_hard_deps.py tests/test_mcp_meta.py tests/test_mcp_serve.py
# 7 failed, 35 passed, 1 skipped   (measured 2026-08-13 on an env with no `mcp` and httpx 0.24.1)

# same three files, environment uv.lock pins; --no-sync measures rather than repairs
uv run --no-sync python -m pytest tests/test_hard_deps.py tests/test_mcp_meta.py tests/test_mcp_serve.py -q
# 43 passed                        (exit 0; measured 2026-08-13 in this tree)
```

Same 43 cases either way. The skip is worth as much attention as the failures: it is the
module-level `importorskip` in `tests/test_mcp_serve.py`, and it disappears here not
because anything was fixed but because `mcp` is present. Under the broken environment that
one line is the real-SDK server round-trip declining to run, and only the seven named
failures beside it say so out loud — which is the arrangement this section is describing.

`mcp>=1.28.1` is a *hard* dependency in `pyproject.toml`, but four cases in
`tests/test_mcp_meta.py` used to guard on `pytest.importorskip("mcp")`. A missing `mcp` and
a working `mcp` therefore produced the same exit code: the whole MCP server surface could
sit out behind a green summary line, and you only found out by reading the skip reasons.
Those four now call `hard_deps.require_mcp()`, which **fails** instead of skipping, and
`tests/test_hard_deps.py` checks every name in `[project].dependencies` directly — one
named failure per missing dependency, not a quieter summary. Those failures are the guard
working; `pip install -e ".[dev]"` turns them into passes.

`test_hard_deps.py` checks the declared *version* separately from the import, because
"it imports" and "it matches the manifest" are two different claims and only the first was
being made. The environment above carries httpx 0.24.1 against a declared `httpx>=0.27`:
`import httpx` succeeds, so an import-only guard called that environment clean. It is not
clean — it is one where every httpx-dependent path, including the MCP client, is exercised
against a version the manifest says is unsupported. That mismatch is now its own named
failure (`test_declared_dependency_satisfies_specifier[httpx->=0.27]`) rather than silence.
Whether the right fix is upgrading httpx or relaxing the pin is a maintainer decision; the
guard's job is only to stop the two states from looking identical. A dependency whose
distribution metadata is missing entirely fails the same way, since a constraint that could
not be checked must not report as one that was.

A guard against checks that cannot run must not become one, and this one nearly was. Both
of those per-dependency tests are parametrized over the parsed manifest, and pytest builds
a parameter list during *collection*, where an exception is not a reported failure but
`Interrupted: 1 error during collection` — exit 2, zero tests run, sibling modules never
loaded. Reformatting `dependencies = [` to `dependencies=[`, which is a thing TOML
formatters do, took the entire suite to nothing while naming only `StopIteration`. Reading
the manifest is now total: any parse failure yields a single sentinel requirement that
fails by name and reports the cause, so the run stays red, stays readable, and stays a
run. Single, not zero — pytest reports an empty parameter set as *skipped*, so returning
no parameters would have laundered an unreadable manifest into green.

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
