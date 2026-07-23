#!/usr/bin/env bash
# Idempotent developer / Cursor Cloud bootstrap for standalone scout-cli.
set -euo pipefail

SCOUT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCOUT_ROOT"

log() { printf '[scout-dev-env] %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

export PATH="${HOME}/.local/bin:${PATH}"
# Prevent uv from attaching to a parent monorepo (e.g. /agent/repos/dottie).
unset UV_PROJECT UV_PROJECT_ENVIRONMENT VIRTUAL_ENV || true

if ! have uv; then
  log "installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${PATH}"
fi
log "uv $(uv --version)"

log "ensuring Python 3.11 via uv"
uv python install 3.11

log "syncing scout-cli (optional-dependencies via --all-extras)"
# scout-cli uses [project.optional-dependencies], not [dependency-groups].
# Always operate on THIS checkout's .venv.
if [[ ! -d .venv ]]; then
  uv venv --python 3.11 .venv
fi
# `uv sync` discovers pyproject in cwd; pin venv explicitly.
uv sync --all-extras --python "${SCOUT_ROOT}/.venv/bin/python" \
  || uv pip install --python "${SCOUT_ROOT}/.venv/bin/python" -e ".[dev,all]"

log "installing scout as uv tool from this checkout"
uv tool install -e "${SCOUT_ROOT}" --force >/dev/null 2>&1 \
  || uv pip install --python "${SCOUT_ROOT}/.venv/bin/python" -e ".[dev]"

BASHRC="${HOME}/.bashrc"
BLOCK_BEGIN="# >>> scout-dev-env >>>"
BLOCK_END="# <<< scout-dev-env <<<"
BLOCK_BODY=$(cat <<EOF
${BLOCK_BEGIN}
export PATH="\${HOME}/.local/bin:\${PATH}"
export SCOUT_CLI_ROOT="${SCOUT_ROOT}"
alias scout-root='cd "\$SCOUT_CLI_ROOT"'
alias scout-test='(cd "\$SCOUT_CLI_ROOT" && uv run pytest tests/ -q)'
${BLOCK_END}
EOF
)

if [[ -f "$BASHRC" ]] && grep -qF "$BLOCK_BEGIN" "$BASHRC"; then
  tmp="$(mktemp)"
  awk -v begin="$BLOCK_BEGIN" -v end="$BLOCK_END" '
    $0 == begin {skip=1; next}
    $0 == end {skip=0; next}
    !skip {print}
  ' "$BASHRC" >"$tmp"
  printf '\n%s\n' "$BLOCK_BODY" >>"$tmp"
  mv "$tmp" "$BASHRC"
  log "refreshed scout-dev-env block in ${BASHRC}"
else
  printf '\n%s\n' "$BLOCK_BODY" >>"$BASHRC"
  log "appended scout-dev-env block to ${BASHRC}"
fi

export SCOUT_CLI_ROOT="$SCOUT_ROOT"
log "SCOUT_CLI_ROOT=${SCOUT_CLI_ROOT}"
if have scout; then
  log "scout ready: $(command -v scout)"
else
  log "scout via: ${SCOUT_ROOT}/.venv/bin/scout"
fi
log "done. Next: source ~/.bashrc && scout --help && uv run pytest tests/ -q"
