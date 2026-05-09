---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:fbt:fy2026:statutory-fraction"
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
  name: FBT Statutory Fraction (Car Statutory Formula method)
  rate_id: "statutory-fraction"
  unit: "decimal-fraction"
  value: 0.2

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "Fringe Benefits Tax Assessment Act 1986 (FBTAA)"
  source_clause: FBTAA s.9(1)
  ato_toolkit_locator: "Section 'Statutory formula method (FBT calculation for cars)' — uniform 20% statutory percentage regardless of distance travelled"
  reference_text: "Australian Taxation Office, *Fringe Benefits Tax — A Guide for Employers* (2026 edition) and the *Fringe Benefits Tax Assessment Act 1986* (FBTAA). ATO 2026 FBT Toolkit available at LodgeiT_FBT/extracted_toolkit/2026_FBT_toolkit.txt."
  as_of_date: "2026-04-26"

# Cryptographic anchor
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  content_hash: "868b4661ed89d27c1e6f39854f57649c75460eacc29323d43fbaf515a70a6349"

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

# FBT Statutory Fraction (Car Statutory Formula method)

> **Period:** FBT FY2026 (year ending 31 March 2026)
> **Statutory source:** FBTAA s.9(1)
> **Calculator:** FBT (Fringe Benefits Tax — Australia)

## Value

`0.2` (decimal-fraction)

## Statutory provenance

FBTAA s.9(1) — single statutory percentage of 20% applies for all car fringe benefits where the Statutory Formula method is elected (post-1 April 2014).

**ATO Toolkit locator:** Section 'Statutory formula method (FBT calculation for cars)' — uniform 20% statutory percentage regardless of distance travelled

## Notes

Pre-2011 multi-tier statutory percentages (7%, 11%, 20%, 26%) are obsolete. Single 20% applies to all post-1 April 2014 elections. The FBT_Engine.pl prototype already encodes this value (caught the legacy LodgeITSmart C# bug where this was being misapplied).

## How the calculator consumes this

The FBT engine looks this up at execution time via:

```prolog
rate_lookup('urn:sbrm:period:fbt:fy2026', 'statutory-fraction', Value).
```

The engine source carries algorithm only — never inlines `0.2` as a magic number. This is the Standing-Rule-#6 (Hoffman Temporal-Dimension Discipline) shape.

## Mutation ledger

This node was created in `mut-2026-04-26-010` (FBT FY2026 rate-table — first nodes ever; first instance of `SBRM_RATE_TABLE/` convention). Future amendments append to `helm_mutations[]` per the Zero-Hallucination Law.

*— ClawDog ∮*
