---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:fbt:fy2026:in-house-benefit-cap"
ontological_class: "StatutoryRate"
gist_equivalent: "gist:Magnitude"

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
  name: In-House Fringe Benefit Annual Reduction Cap
  rate_id: "in-house-benefit-cap"
  unit: "AUD"
  value: 1000

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "Fringe Benefits Tax Assessment Act 1986 (FBTAA)"
  source_clause: FBTAA s.62(1)
  ato_toolkit_locator: "Section 'In-house benefits' — '$1,000 in-house benefit reduction'"
  reference_text: "Australian Taxation Office, *Fringe Benefits Tax — A Guide for Employers* (2026 edition) and the *Fringe Benefits Tax Assessment Act 1986* (FBTAA). ATO 2026 FBT Toolkit available at LodgeiT_FBT/extracted_toolkit/2026_FBT_toolkit.txt."
  as_of_date: "2026-04-26"

# Cryptographic anchor
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  content_hash: "5c35804fe451a93877db717a3506f3c893dad190343343dd7d1f6ce6a16490b6"

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

# Mutation ledger (append-only)
helm_mutations: []
---

# In-House Fringe Benefit Annual Reduction Cap

> **Period:** FBT FY2026 (year ending 31 March 2026)
> **Statutory source:** FBTAA s.62(1)
> **Calculator:** FBT (Fringe Benefits Tax — Australia)

## Value

`1000` (AUD)

## Statutory provenance

FBTAA s.62 — annual reduction of $1,000 in aggregate taxable value of in-house fringe benefits provided to each employee (in-house expense payment, in-house property, in-house residual).

**ATO Toolkit locator:** Section 'In-house benefits' — '$1,000 in-house benefit reduction'

## Notes

Applies per-employee-per-FBT-year aggregated across in-house expense, property, and residual benefits. Sheet preserves this in 'In-house benefit (max. $1000)' column header. Statutory cap is stable across recent years but Hoffman-disciplined regardless.

## How the calculator consumes this

The FBT engine looks this up at execution time via:

```prolog
rate_lookup('urn:sbrm:period:fbt:fy2026', 'in-house-benefit-cap', Value).
```

The engine source carries algorithm only — never inlines `1000` as a magic number. This is the Standing-Rule-#6 (Hoffman Temporal-Dimension Discipline) shape.

## Mutation ledger

This node was created in `mut-2026-04-26-010` (FBT FY2026 rate-table — first nodes ever; first instance of `SBRM_RATE_TABLE/` convention). Future amendments append to `helm_mutations[]` per the Zero-Hallucination Law.

*— ClawDog ∮*
