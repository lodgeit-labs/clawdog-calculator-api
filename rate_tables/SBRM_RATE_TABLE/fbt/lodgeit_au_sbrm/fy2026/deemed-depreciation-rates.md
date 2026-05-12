---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:fbt:fy2026:deemed-depreciation-rates"
ontological_class: "StatutoryRate"
gist_equivalent: "gist:Ratio"

# Calculator + period this rate belongs to
calculator: "fbt"
applies_to_calculator_uri: "urn:lodgeit:calculator:fbt"

# Hoffman temporal dimension — first-class
temporal_context:
  type: "Duration"
  period_uri: "urn:sbrm:period:fbt:fy2026"
  period_start: "2025-04-01"
  period_end: "2026-03-31"
  period_label: "FBT FY2026 (year ending 31 March 2026)"

# The rate value itself — COMPOUND (3 acquisition-date tiers)
rate:
  name: Deemed Depreciation Rates (Operating Cost Method, by Acquisition-Date Tier)
  rate_id: "deemed-depreciation-rates"
  unit: "decimal-fraction-per-annum-by-tier"
  shape: "compound"
  value:
    tier_modern: 0.25
    tier_middle: 0.1875
    tier_legacy: 0.225
  components:
    tier_modern:
      rate: 0.25
      acquisition_date_window: "on or after 2006-05-10"
      acquisition_date_window_iso: "[2006-05-10, +infinity)"
      label: "Modern tier — cars acquired on or after 10 May 2006"
    tier_middle:
      rate: 0.1875
      acquisition_date_window: "2002-07-01 to 2006-05-09 inclusive"
      acquisition_date_window_iso: "[2002-07-01, 2006-05-09]"
      label: "Middle tier — cars acquired between 1 July 2002 and 9 May 2006"
    tier_legacy:
      rate: 0.225
      acquisition_date_window: "before 2002-07-01"
      acquisition_date_window_iso: "(-infinity, 2002-06-30]"
      label: "Legacy tier — cars acquired before 1 July 2002"

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "Fringe Benefits Tax Assessment Act 1986 (FBTAA)"
  source_clause: "FBTAA s.11(1) — deemed depreciation for cars under the Operating Cost method; rates set by ATO in 2026 FBT Toolkit"
  ato_toolkit_locator: "Section 'Deemed depreciation and interest' (toolkit p.5314+); rate triplet at p.5318: '25% for cars acquired on or after 10 May 2006; 18.75% for cars acquired from 1 July 2002 to 9 May 2006; 22.5% for cars acquired prior to 1 July 2002.' Cross-reference p.5961 (no car-limit cap on owned-luxury) and p.5967 (leased cars: do NOT calculate deemed depreciation/interest — use actual lease charges)."
  reference_text: "Australian Taxation Office, *Fringe Benefits Tax — A Guide for Employers* (2026 edition) and the *Fringe Benefits Tax Assessment Act 1986* (FBTAA). ATO 2026 FBT Toolkit available at LodgeiT_FBT/extracted_toolkit/2026_FBT_toolkit.txt (lines 5314–5340 inclusive)."
  as_of_date: "2026-05-08"

# Cryptographic anchor (documentary; brain owns provenance per Standing Rule #7)
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  content_hash: "4d3a9e54d740de8df7961758d8f588cf76d3a37a638075b82b2811ddb3ad95df"

# Cybernetic state
cybernetic_state:
  status: "canonical"
  prolog_trace_id: null
  error_vector: null
  helm_trigger: null
  human_override_required: false

# Semantic edges — links rate-tables together by calculator+period
semantic_edges:
  - rel: "sbrm:appliesIn"
    target: "urn:sbrm:period:fbt:fy2026"
  - rel: "sbrm:partOfRateTableFor"
    target: "urn:lodgeit:calculator:fbt"
  - rel: "sbrm:companionTo"
    target: "urn:sbrm:rate:fbt:fy2026:benchmark-interest"

# Mutation ledger (append-only)
helm_mutations:
  - ledger_id: "mut-2026-05-08-mc01"
    timestamp: "2026-05-08T05:37:47Z"
    agent_id: "clawdog-agent"
    authority: "andrew (workspace owner, 2026-05-08 05:34 UTC, webchat control UI: I'd go 1 - small upstream next)"
    mutation_type: "factual_correction"
    content_hash_rolled: true
    previous_content_hash: "f3fa3ceebbac515f4d02c39e8715a6acc0061852f64b3f0f27c7a2e9034d1ab5"
    justification: |
      Re-anchor content_hash to match canonical Brain-side audit_content_hashes.py output.

      The original hash f3fa3ceebbac... was authored at PR #11 merge time (2026-05-08 01:28 UTC,
      commit 134110e) when the PR-C subagent computed the hash inline rather than via the canonical
      script. The file body is byte-identical to its original commit; this is purely an
      algorithm-version mismatch at authoring time, not a content drift.

      The drift was caught on first contact by Phase 3a's manifest-fidelity binary-failure gate
      (CLAWDOG/110 §3 non-negotiable #1; clawdog-calculator-api PR #1, 2026-05-08 04:54 UTC).
      Lesson #38 (file existence ≠ content fidelity) paid out exactly as designed.

      Forward discipline: future calculator rate-table authoring must invoke
      scripts/audit_content_hashes.py --write to anchor the hash, never compute inline.
      Banked as a finding for Phase 3b/3c discipline.
  - ledger_id: "mut-2026-05-12-mc16"
    timestamp: "2026-05-12T02:10:00Z"
    agent_id: "clawdog-agent"
    authority: "andrew (workspace owner, 2026-05-12 01:59 UTC, webchat control UI). PR #166 = mc16 Brain-side reshape merged at 7a143a8 (Phase 3c.2 Brain-only-first). Reply text 'proceed' green-lit Phase 3c.2.b sibling PR in LodgeiT_FBT."
    mutation_type: "path_segment_addition"
    content_hash_rolled: true
    previous_content_hash: "837740cf9f62c53c508af561fccdd94ac8e4e066cba7b7c1e9f1399a18dfe597"
    justification: |
      Phase 3c.2.b path-segment-addition: taxonomy axis lift per GLOBAL_NOTES/CLAWDOG/111_TAXONOMY_AXIS.md (mut-2026-05-11-mc14, ratified PR #164). Path moved from SBRM_RATE_TABLE/fbt/fy2026/ to SBRM_RATE_TABLE/fbt/lodgeit_au_sbrm/fy2026/. The bare math of this fact-node is unchanged; only its filesystem-layer address is extended to make the taxonomy dimension explicit (NN#2 of CLAWDOG/111). This is the Egress-Interface side (LodgeiT_FBT) of Phase 3c.2; the Brain-side reshape banked at mut-2026-05-12-mc16 (clawdog-brain PR #166 merged 2026-05-12 01:59 UTC at 7a143a8). The compound deemed-depreciation node is locally-authored in LodgeiT_FBT (not in Brain); the 9 atomic FBT FY2026 nodes are byte-vendored from Brain's post-mc16 state. URN identity (urn:sbrm:rate:fbt:fy2026:deemed-depreciation-rates) is unchanged — Lesson #36 (atom carries identity, bridge carries interpretation): URN is identity, path segment is interpretation-metadata.
---

# Deemed Depreciation Rates — Operating Cost Method (FY2026)

> **Period:** FBT FY2026 (year ending 31 March 2026)
> **Statutory source:** FBTAA s.11(1); ATO 2026 FBT Toolkit p.5318
> **Calculator:** FBT (Fringe Benefits Tax — Australia)
> **Shape:** COMPOUND — three acquisition-date tiers

## Values

| Tier        | Rate     | Acquisition-date window           |
|-------------|----------|-----------------------------------|
| `tier_modern` | `0.25`   | on or after **2006-05-10**          |
| `tier_middle` | `0.1875` | **2002-07-01** to **2006-05-09** inclusive |
| `tier_legacy` | `0.225`  | before **2002-07-01**               |

## Statutory provenance

FBTAA s.11(1) establishes the deemed-depreciation framework for cars under the Operating Cost method. The specific rate triplet for the FBT 2026 year is published in the ATO 2026 FBT Toolkit, Section "Deemed depreciation and interest" (p.5318):

> "Deemed depreciation for the 2026 FBT year is calculated by multiplying the depreciated value of a car (at the start of the FBT year) by:
>  – 25% for cars acquired on or after 10 May 2006;
>  – 18.75% for cars acquired from 1 July 2002 to 9 May 2006; and
>  – 22.5% for cars acquired prior to 1 July 2002."

**Toolkit cross-references:**
- **p.5961** — no car-limit cap: "If the car is a luxury car owned by employer, ensure deemed depreciation and interest is based on a depreciated value that reflects the full 'cost price' of the car, and not capped at the car limit (i.e., \$69,674 for the 2026 income year)."
- **p.5967** — leased path: "If the car is a luxury car leased by the employer, ensure that the lease charges are included, and do not calculate deemed depreciation and interest." This is the toolkit basis for the `form_of_finance == 'leased'` branch in `fbt_car_oc_deemed_amounts/9` throwing `use_actual_lease_charges`.

## Notes

**Boundary semantics (deterministic per Lesson #14):**
- `tier_modern` is **inclusive** of 2006-05-10. A car acquired exactly on 2006-05-10 is `tier_modern`.
- `tier_middle` ends inclusive at 2006-05-09 and begins inclusive at 2002-07-01.
- `tier_legacy` is **exclusive** of 2002-07-01. A car acquired exactly on 2002-07-01 is `tier_middle`, NOT `tier_legacy`.

**Why three tiers and not income-year-aligned diminishing-value:** the FBT Operating Cost method computes its OWN deemed-depreciation amount per FBTAA s.11(1) — it does NOT defer to the generic income-tax depreciation engine (Prime Cost / Diminishing Value). The acquisition-date tiers are FBT-specific and reflect historical statutory rate adjustments (Costello-era 18.75% reduction, then the 2006 reform back to 25%). See `_ephemeral_LIS_extracts/depr_engine/PROVENANCE.txt` for the rationale (extract-time-only) explaining why the canonical income-tax engine is the wrong jurisdictional fit.

**Companion rate (load together):** `benchmark-interest` (0.0862) — required for the deemed-interest leg of the same calculation. Both consumed by `fbt_car_oc_deemed_amounts/9`.

## How the calculator consumes this

The FBT engine looks up the per-tier rate at execution time via the **4-arg `rate_lookup/4`** (compound-rate variant; the 3-arg `rate_lookup/3` continues to serve scalar rates):

```prolog
rate_lookup('urn:sbrm:period:fbt:fy2026', 'deemed-depreciation-rates', tier_modern, Rate).
% Rate = 0.25
```

The acquisition-date → tier dispatch is **bridge-side interpretation** (per Lesson #36): the engine layer parses the ISO acquisition date, determines the tier atom (`tier_modern` | `tier_middle` | `tier_legacy`), then invokes `rate_lookup/4`. The rate-table node itself does NOT encode the date-arithmetic — it only carries the (Tier → Rate) mapping plus the human-readable window strings for documentation.

Standing Rule #6 compliance: no calculator source inlines `0.25` / `0.1875` / `0.225` — all three flow through `rate_lookup/4`.

## Mutation ledger

This node was created in the Phase 2l-OC-deemed PR (PR-C of the Phase 2l-OC ladder; lodgeit-labs/LodgeiT_FBT, branch `clawdog/fbt-cars-2l-oc-deemed`). First compound rate-table node in the FBT FY2026 set. Future amendments append to `helm_mutations[]` per the Zero-Hallucination Law.

*— ClawDog ∮*
