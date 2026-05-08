---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:fbt:fy2026:fbt-rate"
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

# The rate value itself
rate:
  name: FBT Rate (statutory tax rate on grossed-up taxable value)
  rate_id: "fbt-rate"
  unit: "decimal-fraction"
  value: 0.47

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "Fringe Benefits Tax Assessment Act 1986 (FBTAA)"
  source_clause: FBTAA s.6 (rate of tax)
  ato_toolkit_locator: "Section 'Calculating FBT' — flat 47% rate applied to total grossed-up taxable value"
  reference_text: "Australian Taxation Office, *Fringe Benefits Tax — A Guide for Employers* (2026 edition) and the *Fringe Benefits Tax Assessment Act 1986* (FBTAA). ATO 2026 FBT Toolkit available at LodgeiT_FBT/extracted_toolkit/2026_FBT_toolkit.txt."
  as_of_date: "2026-04-26"

# Cryptographic anchor
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  content_hash: "c7cab39cc6afaeb48466d1bda1835c29b1f98cb1e903b0c18c4d9d5ca01d3c02"

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

# FBT Rate (statutory tax rate on grossed-up taxable value)

> **Period:** FBT FY2026 (year ending 31 March 2026)
> **Statutory source:** FBTAA s.6 (rate of tax)
> **Calculator:** FBT (Fringe Benefits Tax — Australia)

## Value

`0.47` (decimal-fraction)

## Statutory provenance

Fringe Benefits Tax Act 1986 s.6 — FBT rate aligned to top marginal income-tax rate (45%) plus 2% Medicare Levy = 47%.

**ATO Toolkit locator:** Section 'Calculating FBT' — flat 47% rate applied to total grossed-up taxable value

## Notes

Has been 47% since FY2018 (was 49% during temporary Budget Repair Levy period FY2015-FY2017). Stability across multiple FBT years; does not necessarily change annually but is still period-scoped per Hoffman discipline.

## How the calculator consumes this

The FBT engine looks this up at execution time via:

```prolog
rate_lookup('urn:sbrm:period:fbt:fy2026', 'fbt-rate', Value).
```

The engine source carries algorithm only — never inlines `0.47` as a magic number. This is the Standing-Rule-#6 (Hoffman Temporal-Dimension Discipline) shape.

## Mutation ledger

This node was created in `mut-2026-04-26-010` (FBT FY2026 rate-table — first nodes ever; first instance of `SBRM_RATE_TABLE/` convention). Future amendments append to `helm_mutations[]` per the Zero-Hallucination Law.

*— ClawDog ∮*
