---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:fbt:fy2026:days-in-year"
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
  name: FBT Year — Days in Reporting Period
  rate_id: "days-in-year"
  unit: "days"
  value: 365

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "Fringe Benefits Tax Assessment Act 1986 (FBTAA)"
  source_clause: "FBTAA s.136 (definition of 'FBT year')"
  ato_toolkit_locator: All car-fringe-benefit days-available calculations use this denominator
  reference_text: "Australian Taxation Office, *Fringe Benefits Tax — A Guide for Employers* (2026 edition) and the *Fringe Benefits Tax Assessment Act 1986* (FBTAA). ATO 2026 FBT Toolkit available at LodgeiT_FBT/extracted_toolkit/2026_FBT_toolkit.txt."
  as_of_date: "2026-04-26"

# Cryptographic anchor
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  content_hash: "2f7fbfa306e3bfd4d008632c32ec176fab00f1deb8ece50ec346a9b3e5bc597b"

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

# FBT Year — Days in Reporting Period

> **Period:** FBT FY2026 (year ending 31 March 2026)
> **Statutory source:** FBTAA s.136 (definition of 'FBT year')
> **Calculator:** FBT (Fringe Benefits Tax — Australia)

## Value

`365` (days)

## Statutory provenance

FBTAA s.136 — FBT year is the 12-month period commencing 1 April; for FY2026 (1 April 2025 to 31 March 2026) total days = 365.

**ATO Toolkit locator:** All car-fringe-benefit days-available calculations use this denominator

## Notes

Becomes 366 in leap-FBT-years. FY2025 was 365 (year ending 31 March 2025), FY2026 = 365 (year ending 31 March 2026), FY2027 = 366 (year ending 31 March 2027 spans 29 February 2028 — wait, FY2028 = year ending 31 March 2028 spans 29 Feb 2028 = leap year). DOUBLE-CHECK on FY2027 rate-table creation.

## How the calculator consumes this

The FBT engine looks this up at execution time via:

```prolog
rate_lookup('urn:sbrm:period:fbt:fy2026', 'days-in-year', Value).
```

The engine source carries algorithm only — never inlines `365` as a magic number. This is the Standing-Rule-#6 (Hoffman Temporal-Dimension Discipline) shape.

## Mutation ledger

This node was created in `mut-2026-04-26-010` (FBT FY2026 rate-table — first nodes ever; first instance of `SBRM_RATE_TABLE/` convention). Future amendments append to `helm_mutations[]` per the Zero-Hallucination Law.

*— ClawDog ∮*
