# Vendored SBRM rate-table snapshot — FBT FY2026

This directory carries a **byte-snapshot** of the FBT FY2026 SBRM rate-table
fact-nodes from `lodgeit-labs/LodgeiT_FBT/SBRM_RATE_TABLE/fbt/fy2026/`,
re-anchored under the canonical Brain-side hash algorithm (per
`scripts/audit_content_hashes.py`) so every node's declared `content_hash:`
matches its canonical recompute on this snapshot.

## Why a vendored snapshot?

Tests run hermetically — they cannot reach into the LodgeiT_FBT working tree
or the Brain repository at runtime. Vendoring keeps `pytest tests/` reproducible
on any host (CI, Andrew's laptop, a future contributor's box) regardless of
which sibling repos happen to be checked out.

## Provenance + drift finding (Phase 3a snapshot rerun)

At vendor time, **9 of 10 fact-nodes** had a declared `content_hash` that
matched the canonical recompute under `scripts/audit_content_hashes.py`.

**`deemed-depreciation-rates.md`** carried a stale declared hash:

| field | value |
|---|---|
| upstream declared hash | `f3fa3ceebbac…` |
| canonical recompute | `db18119da690…` |
| upstream file | `LodgeiT_FBT/SBRM_RATE_TABLE/fbt/fy2026/deemed-depreciation-rates.md` |

The vendored copy in this directory has been re-anchored to the canonical
recompute so the binary-failure manifest-fidelity gate
(`test_manifest_fidelity_helper_matches_declared_hash`) is exercising the
**correct** invariant on the snapshot. The upstream drift is a real finding
that should be banked for follow-up:

- Open a separate PR against `lodgeit-labs/LodgeiT_FBT` re-anchoring the
  upstream `deemed-depreciation-rates.md` (or, equivalently, a Brain-side roll
  if the upstream copy is meant to mirror the Brain canon).
- Until that PR lands, the upstream copy will fail
  `python scripts/audit_content_hashes.py --check`.

This is **exactly what the manifest-fidelity gate is designed to surface**
(Lesson #38 — file existence is not content fidelity). The Phase 3a bridge
correctly produces a hash that does not match the upstream's declared value;
when the bridge sees this in production, it will surface the drift to its
caller via the manifest block, allowing audit-side byte-verification per
CLAWDOG/109 §7.3.

## Refresh procedure

When the upstream drift is fixed, re-vendor with:

```bash
cp /path/to/LodgeiT_FBT/SBRM_RATE_TABLE/fbt/fy2026/*.md \
   tests/fixtures/sbrm_rate_table_fy2026/
# (Optionally) re-anchor any nodes whose declared hash drifts:
python scripts/reanchor_fixtures.py   # not yet shipped; ad-hoc for now
pytest tests/test_manifest_fidelity.py
```
