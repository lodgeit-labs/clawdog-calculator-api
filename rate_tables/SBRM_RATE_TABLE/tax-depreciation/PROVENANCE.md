# Tax-depreciation rate tables — deferred to the engine-conformance pass

**Status: intentionally empty at this PR.** No rate-table fact-nodes are
vendored here yet. This is the correct, honest state for the gateway-wiring PR
(SCOPE_tax_depreciation_v1.md v1.4), for two reasons:

1. **No acceptance fixture consumes a rate table.** The §6 acceptance rows
   (Dep1 Drill Press decline/balancing; Dep2 low-value pool 13 → 21; small
   business pool 18,505 → 43,179) use statutory *formula constants* (the DV
   200%/life rate, the 37.5%/18.75% low-value-pool rates, the 30%/15% SBE
   rates), not period rate tables. The engine returns `rate_uris_consumed: []`
   for every one of them, so the gateway manifest is an honest empty
   `rate_table_uris: []` (no fabricated anchor) — see
   `api/routes/calculators.py::invoke_tax_depreciation`.

2. **The only rate table the engine consumes is `car-limit`** (the `is_car`
   path, s 40-230), plus the SBE instant-asset-write-off / low-pool-balance
   threshold (s 328-210). SCOPE §9 is explicit that these must be **resolved
   against the statute for each year before the tables are written** — it flags
   a live `Depreciation_Transforms` conflict (a $1,000 Python constant vs
   $20,000 in `rates.pl`) that has to be reconciled first. Writing a
   primary-source-VERIFIED rate table (per the Zero-Hallucination Law) is
   engine-owner conformance work (§7 deliverable 1), not a value to finalise
   from a secondary source inside a gateway PR.

## When tables land

When the `is_car` / SBE-threshold paths are exercised, vendor the fact-nodes
under the canonical resolver path
`SBRM_RATE_TABLE/tax-depreciation/<taxonomy>/<fy>/<rate-id>.md`
(e.g. `.../lodgeit_au_sbrm/fy2025/car-limit.md`) with the same frontmatter +
`verification_status` shape as the div7a / fbt tables in sibling directories,
each carrying a primary-source ATO anchor. The gateway hashes them
automatically via `build_manifest`; no gateway code change is needed — the
resolver already points here.

Rate-table URN shape (SCOPE §3):
`urn:sbrm:rate:tax-depreciation:fy2025:car-limit`,
`urn:sbrm:rate:tax-depreciation:fy2025:sbe-instant-asset-write-off-threshold`.
