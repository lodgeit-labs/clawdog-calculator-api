"""Hermetic guard tying scripts/smoke_prod.sh Check 5 to the committed spec.

Deploy run #56 failed in the canary smoke, not in CI, because Check 5 of
``scripts/smoke_prod.sh`` still required ``/healthz`` in ``/openapi.json`` after
D70 (PR #71) hid it. A spec change that breaks the canary smoke must fail HERE
(hermetically, before deploy), not at deploy time.

This test extracts Check 5's required-paths list straight from the shell script
(one regex over the ``required = [ ... ]`` block) and asserts:

  * every listed path exists in the committed ``openapi.json`` ``paths``; and
  * ``/healthz`` is NOT in the list (it is hidden from the spec by D70, so a
    smoke check that required it would fail the canary again).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "smoke_prod.sh"
COMMITTED_SPEC = REPO_ROOT / "openapi.json"

# Check 5 builds ``required = [ '<path>', '<path>', ... ]`` inside a python3
# heredoc. Capture that list's body, then pull each single-quoted entry.
_REQUIRED_BLOCK_RE = re.compile(r"required\s*=\s*\[(.*?)\]", re.DOTALL)
_QUOTED_PATH_RE = re.compile(r"'([^']+)'")


def _check5_required_paths() -> list[str]:
    """Extract Check 5's required-paths list from scripts/smoke_prod.sh.

    Check 5 is the OpenAPI-paths check; it is the FIRST ``required = [...]`` in
    the script whose entries are URL paths (they start with '/'). Later checks
    (6, 7) also use ``required = {...}`` sets, but those are URN/tool-name sets
    that do not start with '/'.
    """
    text = SMOKE_SCRIPT.read_text(encoding="utf-8")
    for block in _REQUIRED_BLOCK_RE.findall(text):
        paths = _QUOTED_PATH_RE.findall(block)
        if paths and all(p.startswith("/") for p in paths):
            return paths
    raise AssertionError(
        "could not locate Check 5's required-paths list (required = [ '/...' ]) "
        "in scripts/smoke_prod.sh"
    )


def test_check5_required_paths_all_present_in_committed_openapi() -> None:
    required = _check5_required_paths()
    assert required, "Check 5 required-paths list is empty"
    spec = json.loads(COMMITTED_SPEC.read_text(encoding="utf-8"))
    paths = spec.get("paths", {})
    missing = [p for p in required if p not in paths]
    assert not missing, (
        "scripts/smoke_prod.sh Check 5 requires paths absent from the committed "
        f"openapi.json: {missing}. A spec change broke the canary smoke contract "
        "— update Check 5's required list (and openapi.json) together."
    )


def test_check5_does_not_require_healthz() -> None:
    required = _check5_required_paths()
    assert "/healthz" not in required, (
        "/healthz is hidden from openapi.json by D70 (include_in_schema=False); "
        "Check 5 must NOT require it or the canary smoke fails again (deploy #56)."
    )
    # The internal probe is likewise hidden; guard it too.
    assert "/_internal/probe/engine-auth" not in required, (
        "/_internal/probe/engine-auth is hidden from openapi.json by D70; "
        "Check 5 must not require it."
    )
