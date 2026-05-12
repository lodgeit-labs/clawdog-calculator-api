---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:fbt:fy2026:benchmark-interest"
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
  name: FBT Benchmark Interest Rate (for Loan Fringe Benefits)
  rate_id: "benchmark-interest"
  unit: "decimal-fraction-per-annum"
  value: 0.0862

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "Fringe Benefits Tax Assessment Act 1986 (FBTAA)"
  source_clause: FBTAA s.18; ATO Taxation Determination TD 2025/X (FBT benchmark rate for FBT year ending 31 March 2026)
  ato_toolkit_locator: "Section 'Loan fringe benefits — calculating taxable value'; sheet header column literally reads 'FBT Benchmark interest (refer to 2026 FBT year @ 8.62%)'"
  reference_text: "Australian Taxation Office, *Fringe Benefits Tax — A Guide for Employers* (2026 edition) and the *Fringe Benefits Tax Assessment Act 1986* (FBTAA). ATO 2026 FBT Toolkit available at LodgeiT_FBT/extracted_toolkit/2026_FBT_toolkit.txt."
  as_of_date: "2026-04-26"

# Cryptographic anchor
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  content_hash: "1f9b83a89e9dd8a2b0c5484063818f9a8f1380be231d073c412382b99896580c"

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
helm_mutations:
  - mutation_id: "mut-2026-05-12-mc16"
    ledger_id: "mut-2026-05-12-mc16"
    timestamp: "2026-05-12T01:30:00Z"
    agent_id: "clawdog-agent"
    authority: "andrew (workspace owner, 2026-05-12 01:24 UTC, webchat control UI). PR #165 = mc15 Phase 3c ratifications including D3 = helm-roll the SBRM_RATE_TABLE/ reshape. Reply text Go a selects option (a) Brain-only-first cadence per the option ladder surfaced in PR #165 body."
    mutation_type: "path_segment_addition"
    content_hash_rolled: true
    previous_content_hash: "dcd145e425a5ae6d2c2254e8b463a9b2fa2fa622b81d872ea70f7ccaac14fd4d"
    justification: |
      Phase 3c.2 path-segment-addition: taxonomy axis lift per GLOBAL_NOTES/CLAWDOG/111_TAXONOMY_AXIS.md (mut-2026-05-11-mc14). Path moved from SBRM_RATE_TABLE/{calc}/{period}/ to SBRM_RATE_TABLE/{calc}/lodgeit_au_sbrm/{period}/. The bare math of this fact-node is unchanged; only its filesystem-layer address is extended to make the taxonomy dimension explicit (NN#2 of CLAWDOG/111). Honours Lesson #36 (atom carries identity, bridge carries interpretation): the rate value 'value' / 'primary_value' is identity and unchanged; the path segment 'lodgeit_au_sbrm' is interpretation-metadata. content_hash will roll because the helm_mutations ledger grew; the body of the fact (rate, statutory_source, temporal_context) is byte-identical to pre-mutation state.
---

# FBT Benchmark Interest Rate (for Loan Fringe Benefits)

> **Period:** FBT FY2026 (year ending 31 March 2026)
> **Statutory source:** FBTAA s.18; ATO Taxation Determination TD 2025/X (FBT benchmark rate for FBT year ending 31 March 2026)
> **Calculator:** FBT (Fringe Benefits Tax — Australia)

## Value

`0.0862` (decimal-fraction-per-annum)

## Statutory provenance

FBTAA s.18 — for the FBT year ended 31 March 2026, the statutory benchmark interest rate published by the ATO is 8.62% p.a.

**ATO Toolkit locator:** Section 'Loan fringe benefits — calculating taxable value'; sheet header column literally reads 'FBT Benchmark interest (refer to 2026 FBT year @ 8.62%)'

## Notes

Year-on-year volatility. FY2025 was 8.77%. FY2027 will be different again. THE archetypal Hoffman-temporal value: hard-coding it would produce silent drift errors when the season turns.

## How the calculator consumes this

The FBT engine looks this up at execution time via:

```prolog
rate_lookup('urn:sbrm:period:fbt:fy2026', 'benchmark-interest', Value).
```

The engine source carries algorithm only — never inlines `0.0862` as a magic number. This is the Standing-Rule-#6 (Hoffman Temporal-Dimension Discipline) shape.

## Mutation ledger

This node was created in `mut-2026-04-26-010` (FBT FY2026 rate-table — first nodes ever; first instance of `SBRM_RATE_TABLE/` convention). Future amendments append to `helm_mutations[]` per the Zero-Hallucination Law.

*— ClawDog ∮*
