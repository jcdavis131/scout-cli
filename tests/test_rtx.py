"""The release-asset download URL comes from the API response, so it must be gated.

`scout rtx releases sync --tag X` reads a release from api.github.com and then fetches
`asset["browser_download_url"]` — a URL taken out of the RESPONSE — with
follow_redirects=True, and writes the body to disk. That is "observed content decides the
next request", which is the shape the network allowlist exists to bound.

Smaller than forge's hole (be9890d), which took an arbitrary user `--url`: over TLS to
api.github.com the response is authentic unless GitHub itself is compromised. Same shape
though, and this one ends in a file write.

DELIBERATE ASYMMETRY, pinned here so it is not read as an oversight: the two other
httpx.get calls in that command target GITHUB_API, built from the hardcoded GITHUB_REPO.
They are fixed destinations, and gating them would make `scout rtx releases list` fail
until someone allowlists api.github.com — friction with no matching risk. Only the
response-derived URL is gated.
"""

from __future__ import annotations

from pathlib import Path

from bigbang.plugins.rtx import cli as rtx


def test_the_download_url_is_response_derived_not_a_constant():
    """Pins WHY this gate exists. If the code is ever changed to build the download URL
    from GITHUB_API instead, the risk disappears and this whole file can go."""
    src = Path(rtx.__file__).read_text(encoding="utf-8")
    assert 'asset["browser_download_url"]' in src, (
        "the download URL is no longer taken from the API response — re-evaluate whether "
        "this gate is still needed"
    )
    assert "check_user_url" in src, "the gate was removed"


def test_the_hardcoded_calls_are_still_hardcoded():
    """The asymmetry is only defensible while the other calls really are fixed.

    If GITHUB_API ever becomes user- or response-controlled, leaving those two ungated
    stops being a judgement and becomes a hole.
    """
    src = Path(rtx.__file__).read_text(encoding="utf-8")
    assert 'GITHUB_REPO = "jcdavis131/scout-rtx"' in src, (
        "GITHUB_REPO is no longer a constant; the ungated calls above it need re-checking"
    )
    assert "GITHUB_API = f\"https://api.github.com/repos/{GITHUB_REPO}\"" in src


class _Resp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status
        self.text = "irrelevant"

    def json(self):
        return self._payload


def _release_with_asset(url):
    return {"assets": [{"name": "results.tsv", "browser_download_url": url}]}


def test_denied_asset_url_is_never_fetched(monkeypatch, capsys):
    """The property that matters: policy is consulted BEFORE the download happens.

    Drives the real `releases sync` path rather than asserting on a stub. The first
    httpx.get (the release lookup, hardcoded host) is allowed through; the second — the
    response-derived asset URL — must not be reached at all.
    """
    fetched = []

    def fake_get(url, *a, **kw):
        fetched.append(url)
        if "releases/tags" in url:
            return _Resp(_release_with_asset("https://evil.example/results.tsv"))
        raise AssertionError(f"asset was downloaded despite the gate: {url}")

    monkeypatch.setattr(rtx.httpx, "get", fake_get)
    monkeypatch.setattr(
        "bigbang.core.policy.check_user_url",
        lambda url: (False, "user network allowlist is empty (default-deny)"),
    )

    # Returns rather than raising — see the comment at the gate: a typer.Exit here would
    # be swallowed by the branch's blanket `except Exception` and re-emitted as
    # {"error": "1"}. The contract is "does not download", not "raises".
    rtx.releases_cmd(action="sync", tag="v0.0.0-test")

    assert len(fetched) == 1, f"expected only the release lookup, got {fetched}"
    out = capsys.readouterr().out
    assert "denied by network policy" in out, out
    assert "scout reach allow evil.example" in out, out


def test_an_allowed_asset_url_still_downloads(monkeypatch, tmp_path):
    """Non-vacuity: the gate must be able to PASS.

    Without this, a `releases sync` that always exited would satisfy the test above.
    """
    monkeypatch.setattr(rtx, "CUSTOM_ROOT", tmp_path)
    monkeypatch.setattr(rtx, "BB_OFFLOAD", tmp_path / "bb-offload")
    monkeypatch.setattr(rtx, "RESULTS_TSV", tmp_path / "results.tsv")

    def fake_get(url, *a, **kw):
        if "releases/tags" in url:
            return _Resp(_release_with_asset("https://ok.example/results.tsv"))
        return _Resp({}, status=200)

    monkeypatch.setattr(rtx.httpx, "get", fake_get)
    monkeypatch.setattr("bigbang.core.policy.check_user_url", lambda url: (True, "ok"))
    rtx.releases_cmd(action="sync", tag="v0.0.0-test")


# --- scout-rtx root resolution (added 2026-08-02) ------------------------------------
#
# _resolve_custom_root() resolved to ~/workspace/autoresearch-rtx-custom, which does not
# exist on this box, while <repo>/apps/scout-rtx does and was never a candidate. CUSTOM_ROOT
# and the BB_OFFLOAD derived from it therefore pointed at a missing directory. Same omission
# as ava/cli.py (0c89edd); the correct version already existed in
# apps/scout-rtx/bigbang-bridge/cli.py, which checks the containing checkout second.


# These used to assert THE BOX, not the resolver: `_resolve_custom_root().exists()`,
# `BB_OFFLOAD.exists()`, and `parents[5]` as "the repo root". All three are wrong here.
# `apps/scout-rtx` is a companion tree that does not exist in this standalone mirror, so
# the resolver CORRECTLY falls through to ~/workspace/dottie/apps/scout-rtx — under the
# throwaway HOME from conftest.py, where nothing can exist. And parents[5] is only the
# root inside the dottie monorepo (apps/scout-cli/bigbang/plugins/<p>/cli.py); here it
# walks five levels PAST the checkout. The resolver was always fine; only the tests
# counted parents. Three permanently-red tests nobody could act on is how the 23 unrelated
# errors below them sat unremarked across four parked cycles of "pytest: fail".
#
# So build the layout instead of hoping for it, and pin what the resolver actually
# promises: the resolution ORDER, and that no candidate is returned unguarded.


def _isolate(monkeypatch, home, plugin_file):
    """Cut both machine dependencies the resolver has: $HOME and where this file lives.

    USERPROFILE is not belt-and-braces — `Path.home()` reads it on Windows and HOME on
    POSIX, so setting one of the two leaves the test passing on one platform only. The
    session HOME from conftest.py is SHARED and other modules mkdir into it
    (test_agents_langchain creates ~/workspace/dottie/apps/...), so a test that reads it
    is order-dependent — the exact disease these replacements cure.
    """
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("SCOUT_RTX_ROOT", raising=False)
    monkeypatch.delenv("DOTTIE_ROOT", raising=False)
    from bigbang.plugins.rtx import cli as rc

    monkeypatch.setattr(rc, "__file__", str(plugin_file))
    return rc


def _make(root):
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_the_containing_checkout_outranks_dottie_root_and_the_home_layout(
    tmp_path, monkeypatch
):
    """The defect, hermetically. All three candidates exist; the local one must win."""
    checkout = tmp_path / "checkout"
    home = tmp_path / "home"
    mine = _make(checkout / "apps" / "scout-rtx")
    _make(tmp_path / "dottie" / "apps" / "scout-rtx")
    _make(home / "workspace" / "dottie" / "apps" / "scout-rtx")

    rc = _isolate(monkeypatch, home, checkout / "bigbang" / "plugins" / "rtx" / "cli.py")
    monkeypatch.setenv("DOTTIE_ROOT", str(tmp_path / "dottie"))
    assert rc._resolve_custom_root() == mine


def test_dottie_root_outranks_the_home_layout(tmp_path, monkeypatch):
    """Non-vacuity for the ordering above: a resolver hardcoded to the checkout fails."""
    home = tmp_path / "home"
    override = _make(tmp_path / "dottie" / "apps" / "scout-rtx")
    _make(home / "workspace" / "dottie" / "apps" / "scout-rtx")

    # A checkout with no apps/scout-rtx in it, so the walk-up finds no candidate.
    rc = _isolate(monkeypatch, home, tmp_path / "bare" / "cli.py")
    monkeypatch.setenv("DOTTIE_ROOT", str(tmp_path / "dottie"))
    assert rc._resolve_custom_root() == override


def test_the_legacy_standalone_cannot_outrank_the_documented_layout(tmp_path, monkeypatch):
    """~/workspace/autoresearch-rtx-custom used to win. It is demoted, and guarded."""
    home = tmp_path / "home"
    documented = _make(home / "workspace" / "dottie" / "apps" / "scout-rtx")
    _make(home / "workspace" / "autoresearch-rtx-custom")

    rc = _isolate(monkeypatch, home, tmp_path / "bare" / "cli.py")
    assert rc._resolve_custom_root() == documented


def test_no_candidate_is_ever_returned_unguarded(tmp_path, monkeypatch):
    """The structural fix. Nothing exists, so the answer must NAME the canonical location.

    The original bug was an unguarded final `return` of a legacy path: the one candidate
    nobody existence-checked was the one that shipped. With an empty box the resolver may
    only point at where the checkout SHOULD be, so an error message is actionable.
    """
    home = tmp_path / "home"
    rc = _isolate(monkeypatch, home, tmp_path / "bare" / "cli.py")

    got = rc._resolve_custom_root()
    assert not got.exists(), got
    assert got == home / "workspace" / "dottie" / "apps" / "scout-rtx", got
    assert "autoresearch-rtx-custom" not in str(got), f"named the legacy path: {got}"


def test_bb_offload_derives_from_the_resolved_root():
    """Pins the DERIVATION, not existence.

    `BB_OFFLOAD.exists()` was an assertion about the developer's disk: these are bound at
    import time from whatever the machine happens to have. What the module owes its callers
    is that the offload dir hangs off the resolved root, and that is checkable anywhere.
    """
    from bigbang.plugins.rtx import cli as rc

    assert rc.BB_OFFLOAD == rc.CUSTOM_ROOT / "bb-offload"
    assert rc.QUEUE_FILE == rc.BB_OFFLOAD / "queue.json"


def test_scout_rtx_root_env_override_wins(tmp_path, monkeypatch):
    """Non-vacuity: a resolver hardcoded to the repo path would pass the tests above."""
    from bigbang.plugins.rtx import cli as rc

    monkeypatch.setenv("SCOUT_RTX_ROOT", str(tmp_path))
    assert rc._resolve_custom_root() == tmp_path
