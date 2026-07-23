# AGENTS — scout-cli bootstrap

Solo personal project. Primary monorepo home is `jcdavis131/dottie` (`apps/scout-cli`); this repo is the standalone twin.

## Environment

```bash
bash scripts/dev-env-setup.sh
source ~/.bashrc
export SCOUT_CLI_ROOT=/agent/repos/scout-cli   # or your checkout
export PATH="$HOME/.local/bin:$PATH"
```

If developing inside dottie instead:

```bash
export DOTTIE_ROOT=/agent/repos/dottie
bash "$DOTTIE_ROOT/scripts/dev-env-setup.sh"
```

## Verify

```bash
scout --help
scout --json forge list
scout --json system doctor
uv run pytest tests/ -q
ruff check .
```

Durable Cursor Cloud config: `.cursor/environment.json`.
