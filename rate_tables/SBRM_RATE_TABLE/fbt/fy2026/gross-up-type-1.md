---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:fbt:fy2026:gross-up-type-1"
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
  name: FBT Gross-Up Rate — Type 1 (GST-credit-eligible benefits)
  rate_id: "gross-up-type-1"
  unit: "decimal-multiplier"
  value: 2.0802

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "Fringe Benefits Tax Assessment Act 1986 (FBTAA)"
  source_clause: FBTAA s.5B(1B)
  ato_toolkit_locator: "Section 'Gross-up factors' — Type 1 = 2.0802 for FBT year ending 31 March 2026"
  reference_text: "Australian Taxation Office, *Fringe Benefits Tax — A Guide for Employers* (2026 edition) and the *Fringe Benefits Tax Assessment Act 1986* (FBTAA). ATO 2026 FBT Toolkit available at LodgeiT_FBT/extracted_toolkit/2026_FBT_toolkit.txt."
  as_of_date: "2026-04-26"

# Cryptographic anchor
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  content_hash: "c4f2880277e817e9ffb260b73a29f22e3ecdad06903be34701568413502a19fd"

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

# FBT Gross-Up Rate — Type 1 (GST-credit-eligible benefits)

> **Period:** FBT FY2026 (year ending 31 March 2026)
> **Statutory source:** FBTAA s.5B(1B)
> **Calculator:** FBT (Fringe Benefits Tax — Australia)

## Value

`2.0802` (decimal-multiplier)

## Statutory provenance

FBTAA s.5B(1B) — Type 1 gross-up rate accounts for FBT being non-deductible AND for GST input-tax-credits being available to the employer on the underlying benefit acquisition.

**ATO Toolkit locator:** Section 'Gross-up factors' — Type 1 = 2.0802 for FBT year ending 31 March 2026

## Notes

Type 1 applies to fringe benefits where the employer is entitled to an input tax credit for GST on the acquisition. Higher than Type 2 because the gross-up reverses the GST credit claim.

## How the calculator consumes this

The FBT engine looks this up at execution time via:

```prolog
rate_lookup('urn:sbrm:period:fbt:fy2026', 'gross-up-type-1', Value).
```

The engine source carries algorithm only — never inlines `2.0802` as a magic number. This is the Standing-Rule-#6 (Hoffman Temporal-Dimension Discipline) shape.

## Mutation ledger

This node was created in `mut-2026-04-26-010` (FBT FY2026 rate-table — first nodes ever; first instance of `SBRM_RATE_TABLE/` convention). Future amendments append to `helm_mutations[]` per the Zero-Hallucination Law.

*— ClawDog ∮*
