---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:fbt:fy2026:rfba-threshold"
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
  name: Reportable Fringe Benefits Amount (RFBA) Reporting Threshold
  rate_id: "rfba-threshold"
  unit: "AUD"
  value: 2000

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "Fringe Benefits Tax Assessment Act 1986 (FBTAA)"
  source_clause: ITAA 1997 s.135-A; FBTAA s.5E (Reportable fringe benefits total)
  ato_toolkit_locator: "Section 'Reportable fringe benefits' — '$2,000 threshold'"
  reference_text: "Australian Taxation Office, *Fringe Benefits Tax — A Guide for Employers* (2026 edition) and the *Fringe Benefits Tax Assessment Act 1986* (FBTAA). ATO 2026 FBT Toolkit available at LodgeiT_FBT/extracted_toolkit/2026_FBT_toolkit.txt."
  as_of_date: "2026-04-26"

# Cryptographic anchor
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  content_hash: "cdb571f2ddf584b02f7812da4baaf487800d473feabfb0c745a17a865af924c4"

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

# Reportable Fringe Benefits Amount (RFBA) Reporting Threshold

> **Period:** FBT FY2026 (year ending 31 March 2026)
> **Statutory source:** ITAA 1997 s.135-A; FBTAA s.5E (Reportable fringe benefits total)
> **Calculator:** FBT (Fringe Benefits Tax — Australia)

## Value

`2000` (AUD)

## Statutory provenance

Income Tax Assessment Act 1997 s.135-A reportable-fringe-benefits provisions — where total taxable value of reportable fringe benefits provided to an employee exceeds $2,000 in an FBT year, the grossed-up amount must be reported on the employee's income statement.

**ATO Toolkit locator:** Section 'Reportable fringe benefits' — '$2,000 threshold'

## Notes

Threshold is the per-employee aggregate taxable value floor; below it, no reporting requirement. Above it, the WHOLE grossed-up amount (Type 2 rate) is reportable, not just the excess.

## How the calculator consumes this

The FBT engine looks this up at execution time via:

```prolog
rate_lookup('urn:sbrm:period:fbt:fy2026', 'rfba-threshold', Value).
```

The engine source carries algorithm only — never inlines `2000` as a magic number. This is the Standing-Rule-#6 (Hoffman Temporal-Dimension Discipline) shape.

## Mutation ledger

This node was created in `mut-2026-04-26-010` (FBT FY2026 rate-table — first nodes ever; first instance of `SBRM_RATE_TABLE/` convention). Future amendments append to `helm_mutations[]` per the Zero-Hallucination Law.

*— ClawDog ∮*
