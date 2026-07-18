"""Trust gate for `herd start` (FOUNDATION Wave F1).

`herd start` spawns arbitrary argv with full user privileges and, until now,
nothing looked at what it was about to run. Trust being paramount, this refuses
obviously-destructive commands unless the caller explicitly passes
``--allow-risky``, and the refusal is a telemetry event, not a silent pass.

It is a *safety rail*, not a sandbox — it catches catastrophic footguns
(recursive+forced deletes, disk wipes, fork bombs, piping a remote script into a
shell) while leaving ordinary agent/dev commands untouched. The `rm` check is
flag-aware rather than positional: it flags a recursive+force delete regardless
of short/long form or flag order (`-rf`, `-r -f`, `--recursive --force`, or a
`--long` flag placed before the destructive one), closing the bypass the review
found.
"""
from __future__ import annotations

import re
from typing import List, Sequence, Tuple

# Regex deny-list for non-`rm` footguns. Each: (pattern over joined command, reason).
_RISKY: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bmkfs\b|\bmke2fs\b"), "filesystem format"),
    (re.compile(r"\bdd\b.*\bof=/dev/"), "dd writing to a block device"),
    (re.compile(r">\s*/dev/(sd|nvme|hd|disk)"), "redirect over a block device"),
    (re.compile(r":\(\)\s*\{\s*:\|:&\s*\}\s*;\s*:"), "fork bomb"),
    # power-state: only at a command position (start, after ; & |, or after sudo)
    # so script/target names like reboot.py or `make reboot` don't trip it.
    (re.compile(r"(?:^|[;&|]\s*|\bsudo\s+)(shutdown|reboot|halt|poweroff)\b"),
     "power state change"),
    (re.compile(r"\bchmod\s+-R\s+0*00\s+/"), "chmod 000 of a root path"),
    (re.compile(r"\bchown\s+-R\b.*\s/\s*$"), "recursive chown of /"),
    (re.compile(r"(curl|wget)\b[^|]*\|\s*(sudo\s+)?(sh|bash|zsh)\b"),
     "piping a remote script into a shell"),
    # bare --force (destructive) but NOT the safe --force-with-lease.
    (re.compile(r"\bgit\b.*\bpush\b.*--force(?!-with-lease)"), "force push"),
]

# A flag token that implies recursive / force (short cluster or GNU long form).
_RECURSIVE = re.compile(r"(?<!\S)(?:-[a-zA-Z]*[rR][a-zA-Z]*|--recursive)(?!\S)")
_FORCE = re.compile(r"(?<!\S)(?:-[a-zA-Z]*f[a-zA-Z]*|--force)(?!\S)")
# A path argument that is a root / home / cwd target.
_SENSITIVE_TARGET = re.compile(r"(?:^|\s)(/|~|\$HOME|\.)\s*$")


def _rm_destructive(joined: str) -> Tuple[bool, str]:
    """Flag `rm` when the flags anywhere in the command include BOTH a recursive
    and a force form (any order/spelling), or a recursive delete of a root/home/
    cwd path. Scans the substring after the first `rm` word so it catches `rm`
    embedded in a `bash -c "…"` string too."""
    m = re.search(r"\brm\b", joined)
    if not m:
        return False, "ok"
    rest = joined[m.end():]
    recursive = bool(_RECURSIVE.search(rest))
    force = bool(_FORCE.search(rest))
    if recursive and force:
        return True, "rm recursive+force"
    if recursive and _SENSITIVE_TARGET.search(rest):
        return True, "recursive rm of a root/home/cwd path"
    return False, "ok"


def assess(argv: Sequence[str]) -> Tuple[bool, str]:
    """Return (risky, reason). ``risky`` True means the command matched a
    destructive pattern and should be refused unless explicitly allowed."""
    joined = " ".join(str(a) for a in argv)
    risky, reason = _rm_destructive(joined)
    if risky:
        return True, reason
    for pat, why in _RISKY:
        if pat.search(joined):
            return True, why
    return False, "ok"
