---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:fbt:fy2026:s8a-phev-exclusion-effective-from"
ontological_class: "StatutoryDate"
gist_equivalent: "gist:Date"

# Calculator + period this fact belongs to
calculator: "fbt"
applies_to_calculator_uri: "urn:lodgeit:calculator:fbt"

# Hoffman temporal dimension — first-class
temporal_context:
  type: "Duration"
  period_uri: "urn:sbrm:period:fbt:fy2026"
  period_start: "2025-04-01"
  period_end: "2026-03-31"
  period_label: "FBT FY2026 (year ending 31 March 2026)"

# The statute fact itself
rate:
  name: FBTAA s.8A — PHEV exclusion effective-from date (2024 amendment)
  rate_id: "s8a-phev-exclusion-effective-from"
  unit: "iso-date"
  value: "2025-04-01"

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "Fringe Benefits Tax Assessment Act 1986 (FBTAA), s.8A as amended 2024"
  source_clause: FBTAA s.8A (2024 amendment — PHEV carve-out)
  ato_toolkit_locator: "2026 FBT Toolkit, 'Exempt electric vehicles' section — 'since 1 April 2025, plug-in hybrid electric vehicles (PHEVs) are no longer considered eligible electric vehicles'"
  reference_text: "Australian Taxation Office, *Fringe Benefits Tax — A Guide for Employers* (2026 edition). ATO 2026 FBT Toolkit available at LodgeiT_FBT/extracted_toolkit/2026_FBT_toolkit.txt (toolkit lines 4038–4042 + 5199–5201)."
  as_of_date: "2026-05-21"

# Cryptographic anchor
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  content_hash: "b3f2b4183bbe778b3277220e7adb108fd4b6ca2f8ce83c0abfcddd14de9c5360"

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

# Mutation ledger (append-only)
helm_mutations: []
---

# FBTAA s.8A — PHEV exclusion effective-from date (2024 amendment)

> **Period:** FBT FY2026 (year ending 31 March 2026)
> **Statutory source:** FBTAA s.8A (as amended 2024)
> **Calculator:** FBT (Fringe Benefits Tax — Australia)

## Value

`2025-04-01` (ISO-8601 date)

## Statutory provenance

From **1 April 2025**, plug-in hybrid electric vehicles (PHEVs) are no longer considered eligible electric vehicles for the FBTAA s.8A exemption. The exemption survives ONLY where a pre-existing arrangement was already FBT-exempt and a financially binding commitment continues the arrangement past 2025-04-01.

**ATO Toolkit verbatim (lines 4038–4042, mirrored at 5199–5201):**

> *"In addition, since 1 April 2025, plug-in hybrid electric vehicles ('PHEVs') are no longer considered eligible electric vehicles for FBT purposes and so they are no longer eligible for the exemption. However, an employer can continue to apply the electric vehicle exemption if:*
> *• the use of the PHEV was exempt from FBT before 1 April 2025; and*
> *• there is a financially binding commitment to continue providing the vehicle to an employee or their associate for their private use on or after 1 April 2025 (although any optional extension of the agreement is not considered binding)."*

This node is consumed by the `phev_grandfathered` branch of the s.8A predicate (introduced in PR-C of the OT #79 sprint ladder). The grandfather check is **honour-system** at the engine layer — the engine cannot verify the financially-binding-commitment condition from input data alone; it surfaces a `verification_required: "phev_grandfather_attestation"` flag on the output dict when the grandfather branch fires.

## How the calculator consumes this

The s.8A predicate looks this up at execution time via:

```prolog
rate_lookup_string('urn:sbrm:period:fbt:fy2026', 's8a-phev-exclusion-effective-from', DateStr).
```

The engine source carries algorithm only — never inlines `"2025-04-01"` as a magic string. This is the Standing-Rule-#6 (Hoffman Temporal-Dimension Discipline) shape, generalised to date-valued statute facts.

## Notes

- BEV and FCEV vehicles are unaffected by this amendment — they remain eligible under s.8A regardless of when first held (provided the other three conditions of s.8A are satisfied).
- The grandfather provision is narrow: an "optional extension" of the agreement does NOT count as a financially binding commitment. The engine cannot enforce this distinction; surfaced as an operator attestation.

## Cross-references

- **Sibling rate-table nodes (s.8A constellation):**
  - `s8a-effective-from.md` (2022-07-01)
  - `s8a-lct-low-emission-threshold.md` (91387 AUD)
- **Engine-side consumer (forthcoming):** `s8a_exempt/3` predicate in `FBT_Engine.pl` (OT #79 sprint Rung 3).
- **Brain canon:** clawdog-brain OT #79 (statute-deviation finding) + sprint design `_drafts/fbt-s8a-sprint-design-2026-05-21-mc04.md`.

## Mutation ledger

This node was minted in `mut-2026-05-21-mc04-s8a-rate-table-mint` (LodgeiT_FBT PR-A; combined with `s8a-effective-from.md` + `s8a-lct-low-emission-threshold.md` as a three-node batch). Future amendments append to `helm_mutations[]` per the Zero-Hallucination Law.

*— ClawDog ∮*
