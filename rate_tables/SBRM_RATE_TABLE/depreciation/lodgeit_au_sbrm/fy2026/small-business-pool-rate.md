---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:depreciation:fy2026:small-business-pool-rate"
ontological_class: "StatutoryRate"
gist_equivalent: "gist:Ratio"

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

# The rate values (compound — first year vs. subsequent years)
rate:
  name: Small Business Entity General Pool Depreciation Rate
  rate_id: "small-business-pool-rate"
  unit: "decimal-fraction"
  components:
    first_year_pct:
      value: 0.15
      label: "15% — applies to additions in the year of acquisition (regardless of when in the year the asset was acquired — half-year rule does NOT apply for SBE pool)"
    subsequent_year_pct:
      value: 0.30
      label: "30% diminishing-value style — applies to opening pool balance in subsequent years"
  primary_value: 0.30
  primary_value_note: "30% is the full-year rate; 15% is the first-year haircut. Engine should handle both branches via period-comparison."

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "Income Tax Assessment Act 1997 (ITAA 1997)"
  source_clause: "ITAA 1997 s.328-185 (general small business pool); s.328-190 (deductions from pool)"
  policy_type: "Federal statute"
  reference_text: |
    The Small Business Entity (SBE) general pool simplified depreciation rules
    apply to assets acquired by an SBE (aggregated turnover < $10M) that are
    above the IAWO threshold for the period and have a taxable purpose.

    Pool depreciation rates:
    - First year of allocation: 15% of cost (no part-year apportionment)
    - Subsequent years: 30% of opening pool balance (declining-balance shape)

    Pool balance is reduced when assets are disposed of (proceeds reduce pool;
    if pool goes negative, the negative amount is included in assessable income
    under s.328-215). If the pool's closing balance is below the IAWO threshold
    at year-end, the entire balance can be written off (s.328-210).

    Authority: ITAA 1997 Subdivision 328-D (Capital allowances for small
    business entities). ATO Toolkit reference: "Simpler depreciation for
    small business" — pool method.
  ato_locator: "https://www.ato.gov.au/Business/Depreciation-and-capital-expenses-and-allowances/Simpler-depreciation-for-small-business/"
  as_of_date: "2026-04-27"

# Cryptographic anchor
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  content_hash: "765d2f40309d47bed572e7c69575d4fd9b93987653da72edbf7ddca40cb7d99c"

# Cybernetic state
cybernetic_state:
  status: "draft"  # rates are stable but eligibility/edge-case rules need encoding before promotion
  prolog_trace_id: null
  error_vector: "Rates of 15%/30% have been stable since FY2013 simplified depreciation reforms. Promotion to 'canonical' deferred until accompanying eligibility-rule node and pool-mechanics rule node are encoded (separate thread, post-Tuesday-Dep-drop)."
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
  - rel: "sbrm:relatedThreshold"
    target: "urn:sbrm:rate:depreciation:fy2026:instant-asset-write-off-threshold"
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
    previous_content_hash: "fb8f9711e3fe37ff0699a6d32aa7656fff768acc62e70c6978e6fd3f8a0d08ce"
    justification: |
      Pre-mutation audit (python3 scripts/audit_content_hashes.py --check, 2026-05-12 01:25 UTC) flagged this node STALE: its declared content_hash (the value recorded in previous_content_hash above) was authored under a pre-canonical hashing pass at mut-2026-04-27-013 (depreciation canon initiation, PR #41 merged 2026-04-27 06:50 UTC) and never re-anchored via scripts/audit_content_hashes.py --write. This is the same defect class banked at GLOBAL_NOTES/CLAWDOG/110_OUTSOURCE_BOUNDARY_DISCIPLINE.md § Empirical evidence (PR-C deemed-depreciation-rates.md PR #11 f3fa3cee… drift caught by Phase 3a's manifest-fidelity gate, re-anchored under mut-2026-05-08-mc01). Lesson #38 (file existence ≠ content fidelity) applies. The file body is byte-identical to its mut-2026-04-27-013 commit; this factual_correction entry records the algorithm-version delta. The path_segment_addition entry that follows applies to the CORRECTED state. content_hash will be re-anchored at the end of the path-move via scripts/audit_content_hashes.py --write.
  - mutation_id: "mut-2026-05-12-mc16"
    ledger_id: "mut-2026-05-12-mc16"
    timestamp: "2026-05-12T01:30:00Z"
    agent_id: "clawdog-agent"
    authority: "andrew (workspace owner, 2026-05-12 01:24 UTC, webchat control UI). PR #165 = mc15 Phase 3c ratifications including D3 = helm-roll the SBRM_RATE_TABLE/ reshape. Reply text Go a selects option (a) Brain-only-first cadence per the option ladder surfaced in PR #165 body."
    mutation_type: "path_segment_addition"
    content_hash_rolled: true
    previous_content_hash: "fb8f9711e3fe37ff0699a6d32aa7656fff768acc62e70c6978e6fd3f8a0d08ce"
    justification: |
      Phase 3c.2 path-segment-addition: taxonomy axis lift per GLOBAL_NOTES/CLAWDOG/111_TAXONOMY_AXIS.md (mut-2026-05-11-mc14). Path moved from SBRM_RATE_TABLE/{calc}/{period}/ to SBRM_RATE_TABLE/{calc}/lodgeit_au_sbrm/{period}/. The bare math of this fact-node is unchanged; only its filesystem-layer address is extended to make the taxonomy dimension explicit (NN#2 of CLAWDOG/111). Honours Lesson #36 (atom carries identity, bridge carries interpretation): the rate value 'value' / 'primary_value' is identity and unchanged; the path segment 'lodgeit_au_sbrm' is interpretation-metadata. content_hash will roll because the helm_mutations ledger grew; the body of the fact (rate, statutory_source, temporal_context) is byte-identical to pre-mutation state.
---

# Small Business Pool Rate — Depreciation FY2026

> **Period:** Depreciation FY2026 (AU income year ending 30 June 2026)
> **Statutory source:** ITAA 1997 s.328-185, s.328-190
> **Calculator:** Depreciation (Australia) — AU tax kit
> **Status:** `draft` — accompanying eligibility/mechanics rules required before promotion

## Values

| Component | Rate | When applied |
|---|---|---|
| First-year rate | `0.15` (15%) | Additions in their year of acquisition (no part-year apportionment) |
| Subsequent-year rate | `0.30` (30%) | Opening pool balance, every year after |

## Statutory provenance

Income Tax Assessment Act 1997 ss. 328-185, 328-190 — Small Business Entity simplified depreciation pool rules. SBEs (aggregated turnover < $10M) that have not opted out of simplified depreciation may pool depreciable assets above the IAWO threshold and depreciate the pool at a flat 30% (15% in year of acquisition).

Pool mechanics:
- First year: 15% × cost (no proportional half-year rule).
- Each subsequent year: 30% × opening pool balance.
- Disposals: proceeds reduce pool; net negative pool balance → assessable income (s.328-215).
- Year-end clear-out: if closing pool balance < IAWO threshold, entire balance deductible (s.328-210).

## How the calculator consumes this

```prolog
% First-year addition:
rate_lookup(Period, 'small-business-pool-rate', RateNode),
FirstYearPct = RateNode.components.first_year_pct.value,    % 0.15
PoolAdd is Cost * FirstYearPct.

% Subsequent-year depreciation:
SubsequentPct = RateNode.components.subsequent_year_pct.value,  % 0.30
PoolDep is OpeningPoolBalance * SubsequentPct.
```

**Not yet implemented** in `depreciation_server.pl`. Pool-balance state (an Instant snapshot at each period boundary) is itself a separate fact-node class; this rate-table only captures the arithmetic constants.

## Status: draft

Rates have been stable since the FY2013 simplified-depreciation reforms (no annual rotation expected). Promotion to `canonical` deferred until:
- Eligibility rule node encoded (`urn:sbrm:rule:au:sbe-aggregated-turnover-test`).
- Pool-mechanics rule node encoded (proceeds-on-disposal, year-end clear-out, opt-out lock-out).
- Parity oracle exists (post-Tuesday-Dep-drop).

## Mutation ledger

Created in `mut-2026-04-27-013` (Depreciation calculator canon — second AU-tax-kit statutory node). Future amendments append to `helm_mutations[]`.

*— ClawDog ∮*
