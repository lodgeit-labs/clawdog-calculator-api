---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:fbt:fy2026:reasonable-food-allowance"
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
  name: Reasonable Food and Drink Allowance (LAFHA) — Australian Components
  rate_id: "reasonable-food-allowance"
  unit: "structured-table"
  value:
    applies_to: Australian destinations
    per_week_AUD:
      single_no_children: 320
      two_adults_no_children: 481
      two_adults_one_child: 541
      two_adults_two_children: 601
      three_adults: 642
      additional_adult: 161
      additional_child: 60
    note: "Sheet's LAFHA test case uses scalar 100 as 'exempt component of reasonable food allowance' — implying the calculator-side computation per TD 2025/2 produces a scalar deduction for the specific employee composition. The sheet does not test multi-composition variants. Flagged for FBT calculator design discussion."

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "Fringe Benefits Tax Assessment Act 1986 (FBTAA)"
  source_clause: FBTAA s.31; TD 2025/2
  ato_toolkit_locator: "Section 'Living-away-from-home allowance' — 'reasonable food allowance per TD 2025/2'"
  reference_text: "Australian Taxation Office, *Fringe Benefits Tax — A Guide for Employers* (2026 edition) and the *Fringe Benefits Tax Assessment Act 1986* (FBTAA). ATO 2026 FBT Toolkit available at LodgeiT_FBT/extracted_toolkit/2026_FBT_toolkit.txt."
  as_of_date: "2026-04-26"

# Cryptographic anchor
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  content_hash: "ab66aedf828b454fe4af5376d29ea503ef9da6932d8824c23aab38c7f0876c02"

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
    previous_content_hash: "8303d06f8cce28ee9ca45caff38b363ed6df11aa010f94eef617e115b5bbead0"
    justification: |
      Phase 3c.2 path-segment-addition: taxonomy axis lift per GLOBAL_NOTES/CLAWDOG/111_TAXONOMY_AXIS.md (mut-2026-05-11-mc14). Path moved from SBRM_RATE_TABLE/{calc}/{period}/ to SBRM_RATE_TABLE/{calc}/lodgeit_au_sbrm/{period}/. The bare math of this fact-node is unchanged; only its filesystem-layer address is extended to make the taxonomy dimension explicit (NN#2 of CLAWDOG/111). Honours Lesson #36 (atom carries identity, bridge carries interpretation): the rate value 'value' / 'primary_value' is identity and unchanged; the path segment 'lodgeit_au_sbrm' is interpretation-metadata. content_hash will roll because the helm_mutations ledger grew; the body of the fact (rate, statutory_source, temporal_context) is byte-identical to pre-mutation state.
---

# Reasonable Food and Drink Allowance (LAFHA) — Australian Components

> **Period:** FBT FY2026 (year ending 31 March 2026)
> **Statutory source:** FBTAA s.31; TD 2025/2
> **Calculator:** FBT (Fringe Benefits Tax — Australia)

## Value

Structured table — see frontmatter `rate.value` (structured-table).

## Statutory provenance

ATO Taxation Determination TD 2025/2 — reasonable amounts of food/drink for LAFHA fringe benefits during the FBT year ending 31 March 2026. Compound rate-table indexed by employee composition (single, couple, +children) and location (Australian, overseas).

**ATO Toolkit locator:** Section 'Living-away-from-home allowance' — 'reasonable food allowance per TD 2025/2'

## Notes

STRUCTURED rate (table, not scalar). Modelling decision: this node carries the full TD 2025/2 table; calculator engine performs the per-employee-composition lookup. Sheet's regression cases assume a derived scalar; the calculator's `rate_lookup` for this URI returns the structured object, the FBT engine then derives the scalar. This is the first SBRM rate-table node demonstrating that statutory rates can be NESTED structured values, not just scalars.

## How the calculator consumes this

The FBT engine looks this up at execution time via:

```prolog
rate_lookup('urn:sbrm:period:fbt:fy2026', 'reasonable-food-allowance', Value).
```

The engine source carries algorithm only — never inlines `<structured-value>` as a magic number. This is the Standing-Rule-#6 (Hoffman Temporal-Dimension Discipline) shape.

## Mutation ledger

This node was created in `mut-2026-04-26-010` (FBT FY2026 rate-table — first nodes ever; first instance of `SBRM_RATE_TABLE/` convention). Future amendments append to `helm_mutations[]` per the Zero-Hallucination Law.

*— ClawDog ∮*
