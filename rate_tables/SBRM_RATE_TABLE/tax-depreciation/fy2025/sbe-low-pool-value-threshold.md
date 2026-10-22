---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:tax-depreciation:fy2025:sbe-low-pool-value-threshold"
ontological_class: "StatutoryThreshold"
gist_equivalent: "gist:Magnitude"

# Calculator + period this rate belongs to
calculator: "tax-depreciation"
applies_to_calculator_uri: "urn:sbrm:calculator:tax-depreciation:small-business-pool"
applies_to_kit: "tax-au-ato"

# Hoffman temporal dimension — first-class
temporal_context:
  type: "Duration"
  period_uri: "urn:sbrm:period:tax-depreciation:fy2025"
  period_start: "2024-07-01"
  period_end: "2025-06-30"
  period_label: "Tax depreciation FY2025 (AU income year ending 30 June 2025)"

# The threshold value itself
rate:
  name: Small business pool low-pool-value write-off threshold — Subdiv 328-D (s.328-210)
  rate_id: "sbe-low-pool-value-threshold"
  unit: "AUD"
  value: 20000.00

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "Income Tax Assessment Act 1997 (ITAA 1997)"
  source_clause: "ITAA 1997 s.328-210 (low pool value — write off the whole pool), as modified for the 2024-25 income year by Income Tax (Transitional Provisions) Act 1997 s.328-180"
  amending_act: "Treasury Laws Amendment (Tax Incentives and Integrity) Act 2025 (Act No. 29 of 2025), Schedule 4"
  amending_act_register_id: "C2025A00029"
  policy_type: "Federal statute; permanent base $1,000 temporarily lifted to $20,000 for 2024-25 via the IT(TP) Act"
  reference_text: |
    ITAA 1997 s.328-210 (low pool value): if a small business entity's general
    small business pool has a low pool value at the end of the income year —
    i.e. the pool balance before working out that year's decline is positive
    and below the threshold — the whole balance is deducted that year instead
    of the normal 30%/15% decline, and the closing pool balance is nil.

    The PERMANENT threshold in ITAA 1997 s.328-210 is $1,000. For the 2024-25
    income year it is temporarily $20,000: the Income Tax (Transitional
    Provisions) Act 1997 s.328-180 modifies the s.328-210 calculation so the
    threshold is read as "$20,000" for that year. That extension was enacted
    by the Treasury Laws Amendment (Tax Incentives and Integrity) Act 2025
    (Act No. 29 of 2025), Schedule 4.

    NOTE — distinct from s.328-180: the s.328-210 low-pool-value write-off and
    the s.328-180 instant asset write-off are legally separate thresholds that
    happen to coincide at $20,000 for FY2025 under the same transitional
    measure. They are modelled as separate nodes so a future year where they
    diverge does not silently mis-compute. The engine today keys both off a
    single `sbe-instant-asset-write-off-threshold` entry; this node records the
    s.328-210 figure independently for provenance and future-proofing.
  citation: "ITAA 1997 s.328-210; IT(TP) Act 1997 s.328-180 as amended by Act No. 29 of 2025 Sch 4; ATO Guide to depreciating assets 2025 (NAT 1996-06.2025)."
  legislation_url: "https://www.legislation.gov.au/C2025A00029/latest/text"
  ato_locator: "https://www.ato.gov.au/businesses-and-organisations/income-deductions-and-concessions/depreciation-and-capital-expenses-and-allowances/simplified-depreciation-rules"
  as_of_date: "2026-10-22"

# Cryptographic anchor
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  content_hash: "PLACEHOLDER_CONTENT_HASH"

# Cybernetic state
cybernetic_state:
  status: "draft"  # mechanism primary-source-read (legislation.gov.au consolidated ITAA + Act 29/2025); value corroborated, pending NAT 1996-06.2025 primary read. Also: engine does not yet emit this URN (keys s.328-210 off the s.328-180 entry).
  prolog_trace_id: null
  error_vector: "Two caveats. (1) The $20,000 figure/mechanism was read from legislation.gov.au (consolidated ITAA 1997 s.328-210 + Act C2025A00029 Sch 4 via IT(TP) Act s.328-180); the ATO Guide (NAT 1996-06.2025) headline was not re-read from a live ATO surface (ato.gov.au HTTP 403, 2026-10-22). (2) The engine (lodgeit-labs/tax-depreciation-calculator) currently keys the s.328-210 low-pool-value write-off off the single sbe-instant-asset-write-off-threshold entry and does NOT emit this urn:...:sbe-low-pool-value-threshold URN, so this node will not appear in rate_uris_consumed until the engine is updated to read it. Minted now for provenance + to future-proof the s.328-180/s.328-210 distinction."
  helm_trigger: "human_review_required_before_canonisation"
  human_override_required: true

# Semantic edges — links rate-tables together by calculator+period
semantic_edges:
  - rel: "sbrm:appliesIn"
    target: "urn:sbrm:period:tax-depreciation:fy2025"
  - rel: "sbrm:partOfRateTableFor"
    target: "urn:sbrm:calculator:tax-depreciation:small-business-pool"
  - rel: "sbrm:partOfKit"
    target: "urn:lodgeit:kit:tax-au-ato"
  - rel: "sbrm:siblingThreshold"
    target: "urn:sbrm:rate:tax-depreciation:fy2025:sbe-instant-asset-write-off-threshold"

# Mutation ledger (append-only)
helm_mutations:
  - mutation_id: "mut-2026-10-22-mc00-tax-depreciation-fy2025-sbe-low-pool-mint"
    ledger_id: "mut-2026-10-22-mc00-tax-depreciation-fy2025-sbe-low-pool-mint"
    timestamp: "2026-10-22T07:45:00Z"
    agent_id: "clawdog-agent"
    authority: "andrew (gateway owner, 2026-10-22 07:41 UTC, webchat): add the three FY2025 tax-depreciation rate-table files; cite IT(TP)A 1997 s.328-180 as amended by Act No. 29 of 2025 Sch 4, plus the ATO Guide to depreciating assets 2025 (NAT 1996-06.2025) for both thresholds."
    mutation_type: "statutory_node_mint"
    content_hash_rolled: false
    previous_content_hash: null
    justification: |
      FY2025 small-business-pool low-pool-value write-off threshold (s.328-210)
      fact-node. Operative value $20,000 for 2024-25 via IT(TP) Act 1997
      s.328-180 as amended by Act No. 29 of 2025 Sch 4; permanent base in ITAA
      1997 s.328-210 is $1,000. Minted as a node distinct from
      sbe-instant-asset-write-off-threshold (s.328-180) because the two are
      legally separate thresholds that merely coincide at $20,000 for FY2025 —
      recorded separately so a future divergence cannot silently mis-compute.
      The engine does not yet emit this URN; it keys s.328-210 off the
      s.328-180 entry today. Minted at 'draft' / human_override_required
      pending (a) a primary read of NAT 1996-06.2025 and (b) an engine update
      to emit this URN. content_hash is the canonical PLACEHOLDER_CONTENT_HASH;
      anchors on the next scripts/audit_content_hashes.py --write pass.
---

# Low pool value write-off threshold (s.328-210) — Tax depreciation FY2025

> **Period:** Tax depreciation FY2025 (AU income year ending 30 June 2025)
> **Statutory source:** ITAA 1997 s.328-210, modified for 2024-25 by IT(TP) Act 1997 s.328-180 (Act No. 29 of 2025 Sch 4)
> **Calculator:** Tax depreciation — small-business-pool (AU tax kit)
> **Status:** `draft` — pending primary-source confirmation + engine URN emission

## Value

`20000.00` (AUD) — operative FY2025 figure.

## The $1,000-vs-$20,000 settlement

- **Permanent base (ITAA 1997 s.328-210):** $1,000.
- **Operative FY2025 (2024-25 income year):** $20,000, via **IT(TP) Act 1997
  s.328-180** (which modifies the s.328-210 calculation), extended by the
  **Treasury Laws Amendment (Tax Incentives and Integrity) Act 2025 (Act No. 29
  of 2025), Schedule 4**.

So $1,000 is the dormant permanent base; **$20,000 is the correct FY2025 value**.

## Distinct from s.328-180

s.328-210 (low pool value: write off the whole pool when its pre-decline balance
is below the threshold) and s.328-180 (instant asset write-off: deduct an asset
costing below the threshold) are **legally separate thresholds**. For FY2025
both are $20,000 under the same transitional measure, but they are modelled as
separate nodes so a year where they diverge cannot silently mis-compute.

## Engine note

The engine (`lodgeit-labs/tax-depreciation-calculator`) currently keys the
s.328-210 write-off off the single `sbe-instant-asset-write-off-threshold` entry
and does **not** emit this `...:sbe-low-pool-value-threshold` URN. This node is
minted now for provenance and to future-proof the distinction; it will only
appear in `rate_uris_consumed` once the engine reads it.

## Status: draft

Mechanism read from legislation.gov.au (consolidated ITAA C2004A05138 s.328-210
+ amending Act C2025A00029 Sch 4). The ATO Guide (NAT 1996-06.2025) headline was
not re-read from a live ATO surface this session (ato.gov.au HTTP 403). Confirm
before promotion to `canonical`.

*— ClawDog ∮*
