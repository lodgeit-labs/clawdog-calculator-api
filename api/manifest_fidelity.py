"""Manifest-fidelity helper.

Implements CLAWDOG/110 §3.1 Non-Negotiable #1 (Manifest-Fidelity Contract).
``hash_rate_table`` is a **byte-identical port** of the canonical Brain-side
algorithm in ``scripts/audit_content_hashes.py`` (`_compute_hash` / classify).

The discipline (Lesson #38): file existence is not content fidelity. The bridge
reads each rate-table fact-node, substitutes its ``content_hash:`` line with
``"PLACEHOLDER_CONTENT_HASH"``, and SHA-256s the resulting bytes. The result
MUST match the live ``content_hash:`` field declared in the same node's
frontmatter. Mismatch is a binary-failure gate (test_manifest_fidelity).

This file is the canonical Phase 3a port. ``test_manifest_fidelity.py``
cross-checks it against ``scripts/audit_content_hashes.py`` via subprocess to
guarantee byte-identity (not just same-algorithm-by-spec).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

PLACEHOLDER: str = "PLACEHOLDER_CONTENT_HASH"
DRAFT_PLACEHOLDER: str = "PENDING_PRE_ANCHOR_DRAFT_HASH"

# Mirror of scripts/audit_content_hashes.py:
#   HASH_RE matches `content_hash: "<64-hex>"` ONLY at the top-level
#   (whitespace-only prefix). Helm-mutations' `previous_content_hash:` keys
#   include the `previous_` prefix and so do not match.
HASH_RE = re.compile(r'(?m)^\s*content_hash:\s*"([0-9a-f]{64})"')
PH_RE = re.compile(r'(?m)^\s*content_hash:\s*"PLACEHOLDER_CONTENT_HASH"')
DRAFT_PH_RE = re.compile(r'(?m)^\s*content_hash:\s*"PENDING_PRE_ANCHOR_DRAFT_HASH"')


@dataclass(frozen=True)
class RateTableHash:
    """Result of hashing a rate-table fact-node."""

    uri: str
    path: Path
    content_hash: str
    hash_algorithm: str = "sha256"

    def as_manifest_entry(self) -> dict:
        """Serialise as a manifest entry per CLAWDOG/109 §7.1."""
        return {
            "uri": self.uri,
            "content_hash": self.content_hash,
            "hash_algorithm": self.hash_algorithm,
        }


def _ph_substitute(content: str) -> str:
    """Replace ONLY the top-level ``content_hash:`` line with the placeholder.

    Byte-identical port of ``scripts/audit_content_hashes.py::_ph_substitute``.
    Preserves any historical ``previous_content_hash:`` entries (which carry the
    ``previous_`` prefix and so do not match HASH_RE).
    """

    def repl(m: re.Match[str]) -> str:
        return m.group(0).replace(m.group(1), PLACEHOLDER)

    return HASH_RE.sub(repl, content, count=1)


def _compute_canonical_hash(content: str) -> str:
    """Compute the canonical SHA-256 over the placeholder-substituted bytes.

    Byte-identical port of ``scripts/audit_content_hashes.py::compute_canonical_hash``
    (returns just the hash; the helper there returns ``(with_ph, recomputed)``).
    """
    with_ph = _ph_substitute(content)
    return hashlib.sha256(with_ph.encode("utf-8")).hexdigest()


def hash_rate_table(rate_table_path: Path) -> str:
    """Return the canonical content_hash of a rate-table fact-node.

    Byte-identical to the result of ``scripts/audit_content_hashes.py``'s
    canonical algorithm on the same file. The returned hash is the live
    invocation-time hash (Lesson #38) — NOT a deployment-time snapshot.

    Behaviour matches the Brain-side classify() OK / STALE branches:

    * If the file already carries a literal ``PLACEHOLDER_CONTENT_HASH`` line,
      hash the file as-is (the placeholder bytes ARE the canonical input).
    * If the file carries a draft placeholder, promote it to the canonical
      placeholder before hashing (matches the Brain-side reanchor() draft
      branch).
    * Otherwise, substitute the live ``content_hash:`` line with the canonical
      placeholder, then SHA-256.
    """
    content = rate_table_path.read_text(encoding="utf-8")

    if PH_RE.search(content):
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    if DRAFT_PH_RE.search(content):
        promoted = re.sub(
            r'(?m)^(\s*content_hash:\s*)"PENDING_PRE_ANCHOR_DRAFT_HASH"',
            rf'\1"{PLACEHOLDER}"',
            content,
            count=1,
        )
        return hashlib.sha256(promoted.encode("utf-8")).hexdigest()

    return _compute_canonical_hash(content)


def declared_content_hash(rate_table_path: Path) -> str | None:
    """Return the ``content_hash`` declared in the file's frontmatter, if any."""
    content = rate_table_path.read_text(encoding="utf-8")
    m = HASH_RE.search(content)
    return m.group(1) if m else None


def build_manifest(rate_table_uris: list[str], rate_table_root: Path) -> dict:
    """Build the ``manifest`` block per CLAWDOG/109 §7.1.

    Args:
        rate_table_uris: URIs as emitted by the calculator engine in
            ``trace.applied_rate_table_uris`` (e.g.
            ``urn:sbrm:rate:fbt:fy2026:deemed-depreciation-rates``).
        rate_table_root: filesystem root containing the rate-table fact-nodes.
            For Phase 3a, this is ``SBRM_RATE_TABLE/<calc>/<period>/``.

    URI shape mapping (Phase 3a):
        ``urn:sbrm:rate:<calc>:<period>:<rate_id>`` →
        ``<rate_table_root>/<rate_id>.md``

    Per Lesson #38, every entry carries the **live** content_hash computed
    here, not a baked-in deployment value.
    """
    entries: list[dict] = []
    for uri in rate_table_uris:
        rate_id = _rate_id_from_uri(uri)
        path = rate_table_root / f"{rate_id}.md"
        h = hash_rate_table(path)
        entries.append(
            RateTableHash(uri=uri, path=path, content_hash=h).as_manifest_entry()
        )
    return {"rate_table_uris": entries}


def _rate_id_from_uri(uri: str) -> str:
    """Map an SBRM rate URI back to its rate-table filename slug.

    ``urn:sbrm:rate:fbt:fy2026:deemed-depreciation-rates`` →
    ``deemed-depreciation-rates``
    """
    if ":" not in uri:
        raise ValueError(f"not a valid SBRM rate URI: {uri!r}")
    return uri.rsplit(":", 1)[-1]


__all__ = [
    "PLACEHOLDER",
    "DRAFT_PLACEHOLDER",
    "RateTableHash",
    "hash_rate_table",
    "declared_content_hash",
    "build_manifest",
]
