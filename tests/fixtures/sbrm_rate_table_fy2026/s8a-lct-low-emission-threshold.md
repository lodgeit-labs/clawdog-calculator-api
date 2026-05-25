---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:fbt:fy2026:s8a-lct-low-emission-threshold"
ontological_class: "StatutoryRate"
gist_equivalent: "gist:MonetaryAmount"

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

# The rate value itself
rate:
  name: LCT luxury car tax threshold for fuel-efficient cars (s.8A exemption ceiling, FY2026)
  rate_id: "s8a-lct-low-emission-threshold"
  unit: "aud-currency"
  value: 91387

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "A New Tax System (Luxury Car Tax) Act 1999; threshold indexation under ITAA 1997"
  source_clause: LCT Act 1999 — fuel-efficient car threshold; consumed by FBTAA s.8A
  ato_toolkit_locator: "2026 FBT Toolkit, 'Exempt electric vehicles' section — '$91,387 for the 2026 income year'"
  reference_text: "Australian Taxation Office, *Fringe Benefits Tax — A Guide for Employers* (2026 edition). ATO 2026 FBT Toolkit available at LodgeiT_FBT/extracted_toolkit/2026_FBT_toolkit.txt (toolkit line 4032 verbatim: '$91,387 for the 2026 income year'; mirrored at line 5193)."
  as_of_date: "2026-05-21"

# Cryptographic anchor
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  content_hash: "52a9c2ddf7848336b6543ca9a18aff66279abdbe3503604822f95ca0bfdca136"

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
  - rel: "sbrm:statuteFact"
    target: "FBTAA_s8A"
  - rel: "sbrm:derivedFromUpstreamStatute"
    target: "LCT_Act_1999_fuel_efficient_car_threshold"

# Mutation ledger (append-only)
helm_mutations: []
---

# LCT luxury car tax threshold for fuel-efficient cars (s.8A exemption ceiling, FY2026)

> **Period:** FBT FY2026 (year ending 31 March 2026)
> **Statutory source:** LCT Act 1999 (fuel-efficient car threshold), consumed by FBTAA s.8A
> **Calculator:** FBT (Fringe Benefits Tax — Australia)

## Value

`91387` (AUD)

## Statutory provenance

FBTAA s.8A requires that, for the electric-vehicle FBT exemption to fire, "the value of the car at its first retail sale must be less than the applicable luxury car tax threshold for fuel efficient cars in the relevant year."

For the 2026 income year, that threshold is **$91,387**, per the ATO 2026 FBT Toolkit (line 4032 + 5193).

**ATO Toolkit verbatim (line 4032, mirrored at 5193):**

> *"Amongst other requirements, for this exemption to apply, the electric vehicle needs to be first held on or after 1 July 2022, and the value of the car at its first retail sale must be less than the applicable luxury car tax threshold for fuel efficient cars in the relevant year (e.g., $91,387 for the 2026 income year)."*

This threshold is published annually by the ATO. The value here is FY2026-specific; future FY rotations will mint a new period-scoped node (`s8a-lct-low-emission-threshold` under `SBRM_RATE_TABLE/fbt/lodgeit_au_sbrm/fy2027/` etc.).

## How the calculator consumes this

The s.8A predicate (introduced in PR-C of the OT #79 sprint ladder) looks this up at execution time via:

```prolog
rate_lookup('urn:sbrm:period:fbt:fy2026', 's8a-lct-low-emission-threshold', Threshold).
```

The engine source carries algorithm only — never inlines `91387` as a magic number. This is the Standing-Rule-#6 (Hoffman Temporal-Dimension Discipline) shape.

## Notes

- The LCT threshold for fuel-efficient cars is **distinct** from the LCT threshold for non-fuel-efficient cars (which was $80,567 for FY2026 — not relevant to s.8A and not minted here).
- The threshold applies to **value at first retail sale**, not the current market value or the base value used for SF/OC method calculations.
- Below-threshold is **strictly less than** the threshold value (not ≤); confirm against ATO statutory text if a borderline case arises.

## Cross-references

- **Sibling rate-table nodes (s.8A constellation):**
  - `s8a-effective-from.md` (2022-07-01)
  - `s8a-phev-exclusion-effective-from.md` (2025-04-01)
- **Engine-side consumer (forthcoming):** `s8a_exempt/3` predicate in `FBT_Engine.pl` (OT #79 sprint Rung 3).
- **Brain canon:** clawdog-brain OT #79 (statute-deviation finding) + sprint design `_drafts/fbt-s8a-sprint-design-2026-05-21-mc04.md`.

## Mutation ledger

This node was minted in `mut-2026-05-21-mc04-s8a-rate-table-mint` (LodgeiT_FBT PR-A; combined with `s8a-effective-from.md` + `s8a-phev-exclusion-effective-from.md` as a three-node batch). Future amendments append to `helm_mutations[]` per the Zero-Hallucination Law.

*— ClawDog ∮*
