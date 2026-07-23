# Scout CLI × cli-for-agents — hyper-detail review

**Date:** 2026-07-23 (hillclimb: World plane agentability)  
**Scope:** `scout-cli` v0.7.1 (`bigbang/` package, primary binary `scout`)  
**Lens:** cli-for-agents skill — headless, layered help, examples, pipelines, actionable errors, idempotency, dry-run, confirmation bypass, consistent structure, machine-useful success output.

Solo personal project, no connection to employer, built with public/free-tier only.

---

## Executive scorecard

| Criterion | Score (pre → post World hillclimb) | Notes |
|---|---|---|
| Non-interactive first | **B → A−** | tasks delete / auth logout no longer hang; mcp rm/add dry-run; SCOUT_YES / root `--yes` |
| Discoverability (layered help) | **A− → A** | `scout --json planes world` is the digital-world entry |
| `--help` with Examples | **B → B+** | mcp add/rm, tasks delete, auth logout, system scaffold/doctor, root |
| stdin / pipelines | **B** | secrets/auth already solid |
| Fail-fast actionable errors | **B → B+** | mcp missing server → `fail_agent`; doctor emits `healthy`/`failed` |
| Idempotency | **B → B+** | mcp rm / tools rm / secrets rm with --force |
| Destructive dry-run / `--force` | **C+ → B+** | mcp/tasks/auth/scaffold + env `SCOUT_DRY_RUN` |
| Predictable structure | **B+** | `planes world` + scout-canonical agent plans |
| Success output for agents | **A−** | doctor envelope; world plane signals |

**Overall agentability:** ~**B+** — Scout is the headless World control plane for agents (tools · MCP · auth · policy), with judgment cockpit entry at `planes world`.

---

## World-plane hillclimb (this pass)

1. ✅ `tasks delete` non-interactive fail-fast + `--dry-run` + `rm` alias  
2. ✅ `mcp add --dry-run` + new `mcp rm --force/--dry-run`  
3. ✅ `auth logout --force/--dry-run`  
4. ✅ Root `--version` / `--yes` / `--dry-run` + `SCOUT_YES` / `SCOUT_DRY_RUN` in `cli_ux`  
5. ✅ `system doctor` → `{healthy, failed, checks}`; scaffold `--dry-run`  
6. ✅ `planes world` digital-world entry  
7. ✅ Agent planner emits `scout …` (aliases still accepted at execute time)  
8. ✅ Regression coverage in `tests/test_cli_for_agents.py`

## Remaining backlog

- Subcommand-ize `rtx releases {list,sync}`  
- Standard JSON envelope for all legacy `emit()` call sites  
- Wire fs/secret `enforce_or_raise` at more write sites  
- README quickstart still has historical `bb` examples (aliases still work)  
- `scout --help --plain` / emoji-light help for token-cheap agents  

## Verification

```bash
pytest tests/test_cli_for_agents.py -q
scout --json --version
scout --json planes world
scout --json system doctor
scout tasks delete x   # must exit fast with --force example
scout mcp rm missing --dry-run
```
