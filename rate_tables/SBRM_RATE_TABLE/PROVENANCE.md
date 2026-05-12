# SBRM Rate-Table Bundle — Production Snapshot

This tree is **byte-vendored** from the canonical engine source at
`lodgeit-labs/LodgeiT_FBT/SBRM_RATE_TABLE/` and shipped inside the
clawdog-calculator-api Docker image so the Phase 3a manifest-fidelity helper
(`api/manifest_fidelity.py::build_manifest`) can compute live content_hashes
at invocation time without reaching across a network boundary.

## Why bundle?

CLAWDOG/109 §7.1 (Manifest-Fidelity Contract) and Lesson #38 require that
every manifest entry carry the **live** content_hash of the rate-table
fact-node, not a deployment-time snapshot. The hash is recomputed from the
on-disk bytes inside the container at every request.

The Phase 3a engine (LodgeiT_FBT/FBT_Engine.pl) emits SBRM rate URIs in its
`rate_uris_consumed` / `trace.applied_rate_table_uris` block. The bridge
must be able to resolve each URI to a file on disk and SHA-256 the
placeholder-substituted bytes. Without this bundle, `read_text()` raises
`FileNotFoundError` and the bridge surfaces a bare 500 to the caller.

## Provenance

- Source: `lodgeit-labs/LodgeiT_FBT` repo, `SBRM_RATE_TABLE/` tree
- Vendoring rule: byte-identical copy. Do NOT edit these files in-place; if
  the engine-side rate-table is updated, re-vendor by running
  `cp -r LodgeiT_FBT/SBRM_RATE_TABLE/* clawdog-calculator-api/rate_tables/SBRM_RATE_TABLE/`
  and committing the result.
- Layout: `SBRM_RATE_TABLE/<calc>/<taxonomy>/<period_id>/<rate_id>.md`
  (taxonomy axis added at `mut-2026-05-12-mc16` per clawdog-brain CLAWDOG/111;
  Phase 3c.2 ratified set: `lodgeit_au_sbrm` populated, `hoffman_base` to populate at Phase 3c.3)
  - matches the canonical resolver at `api/lib/rate_table_resolver.py::rate_table_root_for(period_uri, taxonomy)`
  - in-route wrappers `_rate_table_root_for(period_uri, taxonomy=DEFAULT_TAXONOMY)` in `api/routes/calculators.py` and `api/routes/rates.py` delegate to the canonical resolver.

## Cloud Run wiring

The Dockerfile copies this tree into `/app/SBRM_RATE_TABLE/` inside the
runtime image. The Cloud Run service descriptor sets
`LODGEIT_FBT_REPO=/app` so the resolver picks up
`/app/SBRM_RATE_TABLE/<calc>/<taxonomy>/<period_id>/` (post-mc16 layout).

## Tests vs production

The hermetic test suite uses its own vendored snapshot at
`tests/fixtures/sbrm_rate_table_fy2026/` (re-anchored under the canonical
hash algorithm — see `tests/fixtures/sbrm_rate_table_fy2026/_FIXTURE_README.txt`).
Production uses **this** bundle, which mirrors the engine's runtime tree
verbatim so manifest hashes agree with the engine's view.

The new binary-failure gate `tests/test_production_bundle.py` cross-checks
this bundle to ensure the production manifest path actually works without
requiring `CLAWDOG_RATE_TABLE_ROOT`.
