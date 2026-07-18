"""Shared subprocess CLI launcher — always use the active interpreter."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
CLI: List[str] = [sys.executable, "-m", "bigbang.cli"]


def _base_env(extra: Optional[dict] = None) -> Dict[str, str]:
    env = dict(os.environ)
    # Windows consoles often default to charmap; emoji in --help needs UTF-8.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    if extra:
        env.update({str(k): str(v) for k, v in extra.items()})
    return env


def run_cli(
    args: Sequence[str],
    *,
    input_text: Optional[str] = None,
    timeout: float = 20,
    env: Optional[dict] = None,
    cwd: Optional[Path] = None,
):
    return subprocess.run(
        CLI + list(args),
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=str(cwd or ROOT),
        env=_base_env(env),
    )
