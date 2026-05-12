---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:depreciation:fy2026:audit-variance-threshold"
ontological_class: "PolicyThreshold"
gist_equivalent: "gist:Magnitude"

# Calculator + period this rate belongs to
calculator: "depreciation"
applies_to_calculator_uri: "urn:lodgeit:calculator:depreciation"

# Hoffman temporal dimension — first-class
temporal_context:
  type: "Duration"
  period_uri: "urn:sbrm:period:depreciation:fy2026"
  period_start: "2025-07-01"
  period_end: "2026-06-30"
  period_label: "Depreciation FY2026 (AU income year ending 30 June 2026)"

# The threshold value itself
rate:
  name: Audit Variance Threshold (material variance flag for tax→accounting transition audit)
  rate_id: "audit-variance-threshold"
  unit: "AUD"
  value: 10.00

# Statutory / policy provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: null
  source_clause: null
  policy_type: "LodgeiT internal accounting policy (NOT statute)"
  reference_text: |
    Internal LodgeiT policy threshold for the depreciation transition audit.
    When the absolute difference between the legacy ledger's accumulated depreciation
    and the recomputed straight-line target accumulated depreciation exceeds this
    threshold, the audit endpoint flags the asset for human review.

    This is NOT a statutory threshold. It is a materiality cutoff for the
    `tax→accounting transition diagnostic` workflow only. Calculator engine
    behaviour does not depend on it for correctness — only for surfacing
    review-worthy assets in the audit report.

    Original source: `app/server/depreciation_server.pl/process_audit_asset/3`
    `(VarianceR > 10.00 -> VarFlag = 'Warning: Material variance...')`.

    Migrated to a rate-table node 2026-04-27 per Standing Rule #6
    (mut-2026-04-27-013).
  as_of_date: "2026-04-27"

# Cryptographic anchor
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  content_hash: "d6d32c88db759682d9208e8abb08ac8f57be98c28c162e60396acd6c5615ef91"

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
    target: "urn:sbrm:period:depreciation:fy2026"
  - rel: "sbrm:partOfRateTableFor"
    target: "urn:lodgeit:calculator:depreciation"
  - rel: "sbrm:policyKind"
    target: "urn:lodgeit:policy:internal-accounting-materiality"

# Mutation ledger (append-only)
helm_mutations:
  - mutation_id: "mut-2026-05-12-mc16"
    ledger_id: "mut-2026-05-12-mc16"
    timestamp: "2026-05-12T01:30:00Z"
    agent_id: "clawdog-agent"
    authority: "andrew (workspace owner, 2026-05-12 01:24 UTC, webchat control UI). PR #165 = mc15 Phase 3c ratifications including D3 = helm-roll the SBRM_RATE_TABLE/ reshape. Reply text Go a selects option (a) Brain-only-first cadence per the option ladder surfaced in PR #165 body."
    mutation_type: "factual_correction"
    content_hash_rolled: true
    previous_content_hash: "9c299e37237fcbbf5ec8c19a10a50bc6c7f8ef42598406957e3345fabafc5b01"
    justification: |
      Pre-mutation audit (python3 scripts/audit_content_hashes.py --check, 2026-05-12 01:25 UTC) flagged this node STALE: its declared content_hash (the value recorded in previous_content_hash above) was authored under a pre-canonical hashing pass at mut-2026-04-27-013 (depreciation canon initiation, PR #41 merged 2026-04-27 06:50 UTC) and never re-anchored via scripts/audit_content_hashes.py --write. This is the same defect class banked at GLOBAL_NOTES/CLAWDOG/110_OUTSOURCE_BOUNDARY_DISCIPLINE.md § Empirical evidence (PR-C deemed-depreciation-rates.md PR #11 f3fa3cee… drift caught by Phase 3a's manifest-fidelity gate, re-anchored under mut-2026-05-08-mc01). Lesson #38 (file existence ≠ content fidelity) applies. The file body is byte-identical to its mut-2026-04-27-013 commit; this factual_correction entry records the algorithm-version delta. The path_segment_addition entry that follows applies to the CORRECTED state. content_hash will be re-anchored at the end of the path-move via scripts/audit_content_hashes.py --write.
  - mutation_id: "mut-2026-05-12-mc16"
    ledger_id: "mut-2026-05-12-mc16"
    timestamp: "2026-05-12T01:30:00Z"
    agent_id: "clawdog-agent"
    authority: "andrew (workspace owner, 2026-05-12 01:24 UTC, webchat control UI). PR #165 = mc15 Phase 3c ratifications including D3 = helm-roll the SBRM_RATE_TABLE/ reshape. Reply text Go a selects option (a) Brain-only-first cadence per the option ladder surfaced in PR #165 body."
    mutation_type: "path_segment_addition"
    content_hash_rolled: true
    previous_content_hash: "9c299e37237fcbbf5ec8c19a10a50bc6c7f8ef42598406957e3345fabafc5b01"
    justification: |
      Phase 3c.2 path-segment-addition: taxonomy axis lift per GLOBAL_NOTES/CLAWDOG/111_TAXONOMY_AXIS.md (mut-2026-05-11-mc14). Path moved from SBRM_RATE_TABLE/{calc}/{period}/ to SBRM_RATE_TABLE/{calc}/lodgeit_au_sbrm/{period}/. The bare math of this fact-node is unchanged; only its filesystem-layer address is extended to make the taxonomy dimension explicit (NN#2 of CLAWDOG/111). Honours Lesson #36 (atom carries identity, bridge carries interpretation): the rate value 'value' / 'primary_value' is identity and unchanged; the path segment 'lodgeit_au_sbrm' is interpretation-metadata. content_hash will roll because the helm_mutations ledger grew; the body of the fact (rate, statutory_source, temporal_context) is byte-identical to pre-mutation state.
---

# Audit Variance Threshold — Depreciation FY2026

> **Period:** Depreciation FY2026 (AU income year ending 30 June 2026)
> **Policy source:** LodgeiT internal accounting policy (NOT statute)
> **Calculator:** Depreciation (Australia)

## Value

`10.00` (AUD)

## Policy provenance

LodgeiT internal materiality threshold for the `tax→accounting transition diagnostic`. When the absolute difference between the legacy ledger's accumulated depreciation and the recomputed straight-line target accumulated depreciation exceeds $10.00, the audit endpoint flags the asset for human review.

Not a statutory threshold. Engine behaviour does not depend on it for correctness — it only surfaces review-worthy assets in the audit report.

## How the calculator consumes this

```prolog
rate_lookup('urn:sbrm:period:depreciation:fy2026', 'audit-variance-threshold', T),
(VarianceR > T -> VarFlag = 'Warning: Material variance...' ; VarFlag = 'OK').
```

Replaces the hard-coded magic number `10.00` in `process_audit_asset/3`. This is the Standing-Rule-#6 (Hoffman Temporal-Dimension Discipline) shape applied to internal-policy thresholds (not just statute).

## Notes

- This is the FIRST internal-policy Duration node (vs. all FBT FY2026 nodes which are statute).
- LodgeiT may revise this threshold without a statutory trigger; revisions append to `helm_mutations[]` per the Zero-Hallucination Law.
- Future component-depreciation feature (AASB 116) may want a per-component variant; defer until that lands.

## Mutation ledger

Created in `mut-2026-04-27-013` (Depreciation calculator canon — first nodes ever in `SBRM_RATE_TABLE/depreciation/`). Future amendments append to `helm_mutations[]`.

*— ClawDog ∮*
