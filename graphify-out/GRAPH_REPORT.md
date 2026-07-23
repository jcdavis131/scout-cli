# Personal Graphify Report

Solo personal project, no connection to employer, built with public/free-tier only.

**Nodes:** 1635 · **Edges:** 4613 · **Communities:** 55

Token estimate: ~556 tokens per scoped query vs ~321031 naive → **577.4× reduction** (measured: sum of indexed file bytes / 4).

## God Nodes (highest-degree concepts)

- **func:emit** (inferred_ref) — degree 118 — file `` — community 1
- **func:command** (inferred_ref) — degree 114 — file `` — community 1
- **Scout CLI** (tool) — degree 104 — file `` — community 0
- **func:str** (inferred_ref) — degree 93 — file `` — community 1
- **func:Option** (inferred_ref) — degree 71 — file `` — community 1
- **func:exists** (inferred_ref) — degree 70 — file `` — community 1
- **README.md** (doc) — degree 66 — file `/agent/repos/scout-cli/README.md` — community 2
- **cli.py** (file) — degree 66 — file `/agent/repos/scout-cli/bigbang/plugins/agent/cli.py` — community 3
- **func:len** (inferred_ref) — degree 64 — file `` — community 1
- **Ava AGI Factory v6.4** (ml_concept) — degree 63 — file `` — community 0
- **func:loads** (inferred_ref) — degree 59 — file `` — community 3
- **test_cli.py** (file) — degree 54 — file `/agent/repos/scout-cli/tests/test_cli.py` — community 0
- **func:Argument** (inferred_ref) — degree 53 — file `` — community 1
- **cli.py** (file) — degree 52 — file `/agent/repos/scout-cli/bigbang/plugins/auth/cli.py` — community 0
- **cli.py** (file) — degree 52 — file `/agent/repos/scout-cli/bigbang/plugins/ava/cli.py` — community 0

## Communities

- **Community 0** — 371 nodes — types [('function', 107), ('inferred_ref', 79), ('symbol', 70), ('file', 55), ('module', 53)] — sample: Ava AGI Factory v6.4, Scout CLI, generate_llm_wiki.py, re, pathlib
- **Community 1** — 355 nodes — types [('function', 195), ('inferred_ref', 153), ('file', 5), ('module', 1), ('symbol', 1)] — sample: load_manifest, doctor_cmd, _normalize_plan_cmd, run, bus
- **Community 2** — 217 nodes — types [('concept', 160), ('file', 16), ('doc', 10), ('ml_concept', 7), ('product', 6)] — sample: README.md, Scout CLI 🐾 — One CLI to Rule , What's New in v0.7.0 — Judgmen, Differentiator cockpit, Teach Dottie-claw
- **Community 3** — 161 nodes — types [('function', 68), ('inferred_ref', 46), ('symbol', 18), ('module', 12), ('class', 9)] — sample: json, bigbang.core.output, set_json_mode, _version_callback, main
- **Community 4** — 58 nodes — types [('inferred_ref', 35), ('function', 23)] — sample: parse_commands, _is_resolvable_fast, _httpx_client, _do, _httpx_client_fallback
- **Community 5** — 58 nodes — types [('function', 22), ('symbol', 13), ('inferred_ref', 13), ('class', 7), ('module', 2)] — sample: RFT_SCHEMA_VERSION, export_dataset, iter_records, validate_record, to_rft_record
- **Community 6** — 43 nodes — types [('function', 14), ('inferred_ref', 13), ('module', 8), ('symbol', 6), ('file', 2)] — sample: _dispatch, run_server, _check_sdk, mcp_client.py, asyncio
- **Community 7** — 40 nodes — types [('concept', 33), ('doc', 3), ('reference', 2), ('metadata', 2)] — sample: https://herdr.dev/, scout-herd.md, name: scout-herd, description: Orchestrate Scout, Scout Herd — agent skill
- **Community 8** — 35 nodes — types [('inferred_ref', 17), ('function', 15), ('module', 2), ('file', 1)] — sample: refresh_session, list_sessions, get_session, create_session, report_status
- **Community 9** — 34 nodes — types [('function', 17), ('inferred_ref', 17)] — sample: _policy_check_step, herdr_available, run_doctor, policy_cmd, _file_check
- **Community 10** — 25 nodes — types [('function', 24), ('file', 1)] — sample: app.js, esc, num, fetchJson, loadBaked
- **Community 11** — 22 nodes — types [('function', 17), ('inferred_ref', 4), ('file', 1)] — sample: register, register, register, register, register
- **Community 12** — 22 nodes — types [('concept', 19), ('metadata', 2), ('doc', 1)] — sample: SKILL.md, name: scout, description: Drive Scout CLI —, Scout — Dottie-claw curriculum, Positioning (do not confuse wi
- **Community 13** — 20 nodes — types [('concept', 19), ('doc', 1)] — sample: tasks-plugin.md, Tasks Plugin — LLM Wiki (Wired, Why Tasks Matters, Implementation File, Core Function
- **Community 14** — 18 nodes — types [('concept', 16), ('doc', 1), ('reference', 1)] — sample: FOUNDATION.md, Scout Foundation Plan, 1. What Scout is (and is not), 2. Design principles (non-nego, 3. Execution waves

## Surprising Connections (cross-community, cross-file)

- `cli.py` [imports] → `os` — [EXTRACTED] — files differ? True — communities (3, 0)
- `cli.py` [imports] → `re` — [EXTRACTED] — files differ? True — communities (3, 0)
- `cli.py` [imports] → `subprocess` — [EXTRACTED] — files differ? True — communities (3, 0)
- `cli.py` [imports] → `sys` — [EXTRACTED] — files differ? True — communities (3, 0)
- `cli.py` [imports] → `Path` — [EXTRACTED] — files differ? True — communities (3, 0)
- `cli.py` [imports] → `typer` — [EXTRACTED] — files differ? True — communities (3, 0)
- `cli.py` [imports] → `emit` — [EXTRACTED] — files differ? True — communities (3, 0)
- `store.py` [imports] → `json` — [EXTRACTED] — files differ? True — communities (0, 3)
- `cli.py` [imports] → `annotations` — [EXTRACTED] — files differ? True — communities (1, 0)
- `cli.py` [imports] → `shlex` — [EXTRACTED] — files differ? True — communities (1, 3)
- `cli.py` [imports] → `Path` — [EXTRACTED] — files differ? True — communities (1, 0)
- `cli.py` [imports] → `typer` — [EXTRACTED] — files differ? True — communities (1, 0)

## Suggested Questions (ask via `pgraphify query`)

- `pgraphify query "what connects auth to database?"`
- `pgraphify query "where is turnover retention logic?"`
- `pgraphify query "how does Ava J-space Planner interact with Critic?"`
- `pgraphify query "how does Scout connect to Ava?"`
- `pgraphify query "trace Stripe webhook to Paid Users MRR"`
- `pgraphify query "show MTNN heads 48→64→k"`

## Rationale & Why

- No # NOTE / # WHY comments found. Consider adding them — they become first-class graph nodes linked to code.

## Personal Ecosystem Overlay

- **Family Brain**: Joint accounts, Betterment buckets, Plaid 5 institutions, Emergency $136.5k
- **Passive Lab**: Turnover Shield $79-$149/mo, 7-13 customers → $1k MRR, Stripe → Supabase → Workers free-tier
- **Ava AGI**: multi_jspace_module.py 4 workspaces S1 hl=8 S2 hl=300 Critic hl=30 Planner hl=150, Router/veto
- **Vector Hoops**: 12,966 player-seasons, MTNN v5_concat_b2_h160_t32_d48_mlp128, CQS 85.87, leakfree 0.7937 composite

> Use `pgraphify path "A" "B"` to trace any two concepts.
