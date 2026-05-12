---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:depreciation:fy2026:instant-asset-write-off-threshold"
ontological_class: "StatutoryThreshold"
gist_equivalent: "gist:Magnitude"

# Calculator + period this rate belongs to
calculator: "depreciation"
applies_to_calculator_uri: "urn:lodgeit:calculator:depreciation"
applies_to_kit: "tax-au-ato"

# Hoffman temporal dimension — first-class
temporal_context:
  type: "Duration"
  period_uri: "urn:sbrm:period:depreciation:fy2026"
  period_start: "2025-07-01"
  period_end: "2026-06-30"
  period_label: "Depreciation FY2026 (AU income year ending 30 June 2026)"

# The threshold value itself
rate:
  name: Instant Asset Write-Off (IAWO) Threshold — Small Business Entities
  rate_id: "instant-asset-write-off-threshold"
  unit: "AUD"
  value: 20000.00

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "Income Tax Assessment Act 1997 (ITAA 1997)"
  source_clause: "ITAA 1997 s.328-180 (Small Business Entity simplified depreciation — instant asset write-off)"
  policy_type: "Federal statute (annually renewed)"
  reference_text: |
    The IAWO threshold for Small Business Entities (SBEs, aggregated turnover
    under $10 million) is the cost-cap below which a depreciating asset's
    full cost can be deducted in the year it is first used or installed
    ready for use.

    For FY2026 (income year ending 30 June 2026), the threshold is $20,000
    (per the Federal Government's announced extension of the temporary
    increased threshold). Threshold has cycled through $1,000 / $20,000 /
    $25,000 / $30,000 / $150,000 / unlimited / $1,000 / $20,000 across
    recent years — a textbook example of why this MUST be period-scoped.

    SBEs that have opted out of simplified depreciation in a prior year are
    excluded; lock-out rules under s.328-175 apply. This node captures the
    threshold value only; eligibility logic lives in the AU-tax kit.

    Authority: ATO website "Instant asset write-off for eligible businesses",
    Treasury Laws Amendment (instruments enacted annually since 2015).
  ato_locator: "https://www.ato.gov.au/Business/Depreciation-and-capital-expenses-and-allowances/Simpler-depreciation-for-small-business/Instant-asset-write-off/"
  as_of_date: "2026-04-27"

# Cryptographic anchor
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  content_hash: "f2892f62e5afa32dc4fe3b8066f03d821314c0b2e53880fd62e894b7c6c0c7da"

# Cybernetic state
cybernetic_state:
  status: "draft"  # value not yet confirmed against ATO 2026 final publication
  prolog_trace_id: null
  error_vector: "Threshold value of $20,000 is the announced FY2026 figure but ATO publications for the actual lodgement period (2025-07-01 to 2026-06-30) should be cross-checked before this node is promoted to 'canonical'."
  helm_trigger: "human_review_required_before_canonisation"
  human_override_required: true

# Semantic edges — links rate-tables together by calculator+period
semantic_edges:
  - rel: "sbrm:appliesIn"
    target: "urn:sbrm:period:depreciation:fy2026"
  - rel: "sbrm:partOfRateTableFor"
    target: "urn:lodgeit:calculator:depreciation"
  - rel: "sbrm:partOfKit"
    target: "urn:lodgeit:kit:tax-au-ato"
  - rel: "sbrm:eligibilityRule"
    target: "urn:sbrm:rule:au:sbe-aggregated-turnover-test"

# Mutation ledger (append-only)
helm_mutations:
  - mutation_id: "mut-2026-05-12-mc16"
    ledger_id: "mut-2026-05-12-mc16"
    timestamp: "2026-05-12T01:30:00Z"
    agent_id: "clawdog-agent"
    authority: "andrew (workspace owner, 2026-05-12 01:24 UTC, webchat control UI). PR #165 = mc15 Phase 3c ratifications including D3 = helm-roll the SBRM_RATE_TABLE/ reshape. Reply text Go a selects option (a) Brain-only-first cadence per the option ladder surfaced in PR #165 body."
    mutation_type: "factual_correction"
    content_hash_rolled: true
    previous_content_hash: "e6d58dcd9d38ba77279df74d630ea92f9488ebab70305f1811b555bb464f2129"
    justification: |
      Pre-mutation audit (python3 scripts/audit_content_hashes.py --check, 2026-05-12 01:25 UTC) flagged this node STALE: its declared content_hash (the value recorded in previous_content_hash above) was authored under a pre-canonical hashing pass at mut-2026-04-27-013 (depreciation canon initiation, PR #41 merged 2026-04-27 06:50 UTC) and never re-anchored via scripts/audit_content_hashes.py --write. This is the same defect class banked at GLOBAL_NOTES/CLAWDOG/110_OUTSOURCE_BOUNDARY_DISCIPLINE.md § Empirical evidence (PR-C deemed-depreciation-rates.md PR #11 f3fa3cee… drift caught by Phase 3a's manifest-fidelity gate, re-anchored under mut-2026-05-08-mc01). Lesson #38 (file existence ≠ content fidelity) applies. The file body is byte-identical to its mut-2026-04-27-013 commit; this factual_correction entry records the algorithm-version delta. The path_segment_addition entry that follows applies to the CORRECTED state. content_hash will be re-anchored at the end of the path-move via scripts/audit_content_hashes.py --write.
  - mutation_id: "mut-2026-05-12-mc16"
    ledger_id: "mut-2026-05-12-mc16"
    timestamp: "2026-05-12T01:30:00Z"
    agent_id: "clawdog-agent"
    authority: "andrew (workspace owner, 2026-05-12 01:24 UTC, webchat control UI). PR #165 = mc15 Phase 3c ratifications including D3 = helm-roll the SBRM_RATE_TABLE/ reshape. Reply text Go a selects option (a) Brain-only-first cadence per the option ladder surfaced in PR #165 body."
    mutation_type: "path_segment_addition"
    content_hash_rolled: true
    previous_content_hash: "e6d58dcd9d38ba77279df74d630ea92f9488ebab70305f1811b555bb464f2129"
    justification: |
      Phase 3c.2 path-segment-addition: taxonomy axis lift per GLOBAL_NOTES/CLAWDOG/111_TAXONOMY_AXIS.md (mut-2026-05-11-mc14). Path moved from SBRM_RATE_TABLE/{calc}/{period}/ to SBRM_RATE_TABLE/{calc}/lodgeit_au_sbrm/{period}/. The bare math of this fact-node is unchanged; only its filesystem-layer address is extended to make the taxonomy dimension explicit (NN#2 of CLAWDOG/111). Honours Lesson #36 (atom carries identity, bridge carries interpretation): the rate value 'value' / 'primary_value' is identity and unchanged; the path segment 'lodgeit_au_sbrm' is interpretation-metadata. content_hash will roll because the helm_mutations ledger grew; the body of the fact (rate, statutory_source, temporal_context) is byte-identical to pre-mutation state.
---

# Instant Asset Write-Off (IAWO) Threshold — Depreciation FY2026

> **Period:** Depreciation FY2026 (AU income year ending 30 June 2026)
> **Statutory source:** ITAA 1997 s.328-180
> **Calculator:** Depreciation (Australia) — AU tax kit
> **Status:** `draft` — value pending ATO 2026 publication confirmation

## Value

`20000.00` (AUD)

## Statutory provenance

Income Tax Assessment Act 1997 s.328-180 — Small Business Entity simplified depreciation. The instant asset write-off allows SBEs (aggregated turnover < $10M) to deduct the full cost of eligible depreciating assets first used or installed ready for use in the income year, where cost is below this threshold.

**Bracket creep history:** $1k → $20k → $25k → $30k → $150k → unlimited (COVID temp) → $1k → $20k. This is the canonical example of why depreciation thresholds **MUST** be period-scoped and never inlined in calculator source.

## How the calculator consumes this

```prolog
rate_lookup('urn:sbrm:period:depreciation:fy2026', 'instant-asset-write-off-threshold', T),
( Cost < T, sbe_eligible(Entity, Period)
-> deduction_method = immediate_writeoff
;  deduction_method = standard_depreciation
).
```

This logic is **not yet implemented** in `depreciation_server.pl`. The `poolsImmediate.csv` data file labels assets as `immediate write off` but the Prolog engine performs straight-line back-simulation regardless of whether the asset's cost is above or below the period's IAWO threshold. Implementation deferred to AU-tax-kit thread (post-Tuesday-Dep-drop, with parity oracle).

## Status: draft

The $20,000 value reflects the announced FY2026 threshold (Federal Government extension of the temporary higher threshold). **Before this node is promoted to `canonical`, the ATO's published 2026-edition guidance for income year 2025-07-01 to 2026-06-30 must be cross-checked.** Specifically:
- Confirm the threshold has not been retracted by 30 June 2026.
- Confirm the SBE aggregated-turnover test threshold ($10M as of last revision).
- Capture the lock-out rules (s.328-175) into a separate eligibility-rule node.

## Mutation ledger

Created in `mut-2026-04-27-013` (Depreciation calculator canon — first AU-tax-kit statutory node). Future amendments append to `helm_mutations[]` per the Zero-Hallucination Law.

*— ClawDog ∮*
