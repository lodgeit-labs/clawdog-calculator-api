"""Manifest-fidelity binary-failure gate (CLAWDOG/110 §3.1 Non-Negotiable #1).

Verifies that ``api.manifest_fidelity.hash_rate_table`` produces a
**byte-identical** SHA-256 to the canonical Brain-side algorithm
(``scripts/audit_content_hashes.py``).

The cross-check is run in two ways:

1. **In-process algorithmic comparison** — re-implements the placeholder-
   substitute + SHA-256 in this test module (a literal mirror of the Brain-side
   algorithm, kept under 20 lines so any drift between the canonical algorithm
   and the helper is loud), and asserts the helper agrees.

2. **Out-of-process subprocess cross-check** — when
   ``CLAWDOG_BRAIN_ROOT`` is set (and points at a checkout of
   ``futureWA/clawdog-brain``), invoke that repo's actual
   ``scripts/audit_content_hashes.py`` against the vendored fixtures and
   assert the audit reports OK (i.e. the recorded ``content_hash:`` declared
   in the rate-table frontmatter matches the canonical recompute). This is
   the binding that prevents silent algorithm drift between the Brain-side
   tool and our port.

Lesson #38 anchor — file existence is not content fidelity. The discipline
this test enforces is *byte-content* discipline; it is the binary-failure gate
that converts the rule from "remember to keep them in sync" into "the build
fails if they drift."
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from api.manifest_fidelity import (
    HASH_RE,
    PLACEHOLDER,
    declared_content_hash,
    hash_rate_table,
)

# ---------------------------------------------------------------------------
# In-process literal mirror of scripts/audit_content_hashes.py canonical algo.
# This is INTENTIONALLY duplicated rather than imported so the cross-check
# catches any silent edit of api/manifest_fidelity.py.
# ---------------------------------------------------------------------------
_HASH_RE_LITERAL = re.compile(r'(?m)^\s*content_hash:\s*"([0-9a-f]{64})"')


def _canonical_recompute(content: str) -> str:
    def repl(m: re.Match[str]) -> str:
        return m.group(0).replace(m.group(1), PLACEHOLDER)

    with_ph = _HASH_RE_LITERAL.sub(repl, content, count=1)
    return hashlib.sha256(with_ph.encode("utf-8")).hexdigest()


@pytest.fixture
def fixture_files(rate_table_fixture: Path) -> list[Path]:
    files = sorted(rate_table_fixture.glob("*.md"))
    assert files, f"no rate-table fixtures found at {rate_table_fixture}"
    return files


def test_manifest_fidelity_helper_matches_inline_algorithm(
    fixture_files: list[Path],
) -> None:
    """The helper produces the same hash as the literal in-test algorithm."""
    for path in fixture_files:
        content = path.read_text(encoding="utf-8")
        expected = _canonical_recompute(content)
        actual = hash_rate_table(path)
        assert actual == expected, (
            f"hash_rate_table drift on {path.name}: "
            f"expected {expected[:12]}…, got {actual[:12]}…"
        )


def test_manifest_fidelity_helper_matches_declared_hash(
    fixture_files: list[Path],
) -> None:
    """Each fixture's declared content_hash matches the canonical recompute.

    This is the load-bearing assertion: if it fails on a vendored snapshot
    that was OK at vendor time, the helper has drifted from the canonical
    algorithm. (If it fails on a fresh re-vendor, the upstream fact-node has
    drifted — surface that finding to the human.)
    """
    drift = []
    for path in fixture_files:
        declared = declared_content_hash(path)
        recomputed = hash_rate_table(path)
        if declared is None:
            # Some legacy nodes ship without a declared content_hash; the
            # canonical algorithm still applies but there is no anchor to
            # compare against. Skip with a record.
            continue
        if declared != recomputed:
            drift.append((path.name, declared, recomputed))
    assert not drift, (
        "Manifest-fidelity drift detected — vendored rate-tables have a "
        "declared content_hash that no longer matches the canonical recompute. "
        f"Mismatched files: {drift}"
    )


def test_manifest_fidelity_brain_side_audit_subprocess(
    fixture_files: list[Path], tmp_path: Path
) -> None:
    """Cross-check against the actual Brain-side script when available.

    Skips gracefully when the Brain repo is not on disk (e.g. external CI
    runners), but executes whenever ``CLAWDOG_BRAIN_ROOT`` resolves to a path
    containing ``scripts/audit_content_hashes.py``. The skip path keeps CI
    green on environments where the Brain isn't checked out; the binding
    fires whenever it IS — including on Andrew's local box and any internal
    runner mounting the Brain repo.
    """
    brain_root_env = os.environ.get("CLAWDOG_BRAIN_ROOT")
    if not brain_root_env:
        pytest.skip(
            "CLAWDOG_BRAIN_ROOT not set; the Brain-side cross-check is opt-in "
            "and runs whenever a clawdog-brain checkout is mounted."
        )
    audit_script = Path(brain_root_env) / "scripts" / "audit_content_hashes.py"
    if not audit_script.exists():
        pytest.skip(f"audit script not found at {audit_script}; skipping cross-check.")

    # The Brain-side script audits files under GLOBAL_NOTES/ via a fixed root.
    # For a per-file cross-check we invoke it with explicit paths and parse
    # the report; we run in --check mode on each fixture and assert exit 0
    # (which means the declared hash matches the canonical recompute under
    # the Brain-side algorithm — i.e. byte-identity with our port).
    failures = []
    for path in fixture_files:
        result = subprocess.run(
            [sys.executable, str(audit_script), "--check", "--quiet", str(path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            failures.append((path.name, result.stdout.strip(), result.stderr.strip()))

    assert not failures, (
        "Brain-side audit reports drift on vendored fixtures — our port may "
        f"have drifted from the canonical algorithm. Failures: {failures}"
    )


def test_manifest_fidelity_helper_handles_placeholder_files(tmp_path: Path) -> None:
    """A node still carrying the literal PLACEHOLDER string hashes its own bytes."""
    body = (
        "---\n"
        "content_hash: \"PLACEHOLDER_CONTENT_HASH\"\n"
        "---\n\n"
        "# placeholder-only node\n"
    )
    p = tmp_path / "placeholder.md"
    p.write_text(body, encoding="utf-8")
    assert hash_rate_table(p) == hashlib.sha256(body.encode("utf-8")).hexdigest()


def test_manifest_fidelity_hash_re_does_not_match_previous_content_hash() -> None:
    """The top-level HASH_RE must not match `previous_content_hash:` lines.

    Helm-mutations carry historical hash values; collapsing them into the
    canonical-hash substitution would break the byte-identity guarantee.
    """
    body = (
        "---\n"
        "content_hash: \"" + ("a" * 64) + "\"\n"
        "helm_mutations:\n"
        "  - previous_content_hash: \"" + ("b" * 64) + "\"\n"
        "---\n"
    )
    matches = HASH_RE.findall(body)
    assert matches == ["a" * 64], (
        f"HASH_RE matched a previous_content_hash: line; got {matches!r}"
    )
