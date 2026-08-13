"""Universal tool registry — the heart of 'one CLI to rule them all'"""

import time
from pathlib import Path

from bigbang.core import atomic_json

REG_DIR = Path.home() / ".local" / "share" / "bigbang"
REG_FILE = REG_DIR / "registry.json"
REG_DIR.mkdir(parents=True, exist_ok=True)


def _load():
    """Registry contents, or a fresh one when none exists.

    A CORRUPT registry raises rather than reading as empty -- same read-modify-write
    trap as the vault: silently returning a fresh registry would make the next
    register_tool() drop every previously registered tool. See atomic_json.

    The default above only fires when the FILE is absent. A file that parses fine
    but was written by something else -- `scout system doctor`'s test fixture
    (tests/test_system.py) seeds registry.json with a bare `{}` to exercise the
    file-exists check, and nothing restores it afterwards for the rest of the
    (session-scoped) throwaway HOME -- is not corruption, and every caller below
    does `db["tools"][...]`. Found by adding tests/test_tools.py: it is the first
    test file that touches the registry after test_system.py's fixture runs, and
    every one of its tests failed with `KeyError: 'tools'` reading a registry.json
    that was valid, empty JSON. Callers keep their bare `db["tools"]` access; this
    is the one place that needs to normalize the shape.
    """
    db = atomic_json.read_json(REG_FILE, {"version": "0.3.0", "tools": {}})
    if not isinstance(db.get("tools"), dict):
        db["tools"] = {}
    return db


def _save(data):
    atomic_json.write_json(REG_FILE, data)


def register_tool(name: str, manifest: dict):
    db = _load()
    manifest["registered_at"] = int(time.time())
    db["tools"][name] = manifest
    _save(db)


def get_tool(name: str) -> dict | None:
    db = _load()
    return db["tools"].get(name)


def list_tools() -> dict[str, dict]:
    db = _load()
    return db["tools"]


def unregister_tool(name: str) -> bool:
    db = _load()
    if name in db["tools"]:
        del db["tools"][name]
        _save(db)
        return True
    return False


def search_tools(query: str) -> list[dict]:
    db = _load()
    q = query.lower()
    results = []
    for name, m in db["tools"].items():
        hay = f"{name} {m.get('description', '')} {m.get('type', '')} {' '.join(m.get('tags', []))}".lower()
        if q in hay:
            results.append({"name": name, **m})
    return results
