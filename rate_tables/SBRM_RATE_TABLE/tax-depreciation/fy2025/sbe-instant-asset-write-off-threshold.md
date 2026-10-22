---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:tax-depreciation:fy2025:sbe-instant-asset-write-off-threshold"
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
  name: Small business instant asset write-off threshold — Subdiv 328-D (s.328-180)
  rate_id: "sbe-instant-asset-write-off-threshold"
  unit: "AUD"
  value: 20000.00

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "Income Tax Assessment Act 1997 (ITAA 1997)"
  source_clause: "ITAA 1997 s.328-180 (instant asset write-off), as modified for the 2024-25 income year by Income Tax (Transitional Provisions) Act 1997 s.328-180"
  amending_act: "Treasury Laws Amendment (Tax Incentives and Integrity) Act 2025 (Act No. 29 of 2025), Schedule 4"
  amending_act_register_id: "C2025A00029"
  policy_type: "Federal statute; permanent base $1,000 temporarily lifted to $20,000 for 2024-25 via the IT(TP) Act"
  reference_text: |
    ITAA 1997 s.328-180 lets a small business entity (aggregated turnover
    under $10 million) deduct in full the cost of a depreciating asset costing
    less than the threshold, where the asset is first used or installed ready
    for use in the income year.

    The PERMANENT threshold in ITAA 1997 s.328-180 is $1,000. For the 2024-25
    income year the threshold is temporarily $20,000: s.328-180 of the
    Income Tax (Transitional Provisions) Act 1997 modifies the operation of
    ITAA 1997 s.328-180 so references to "$1,000" are read as "$20,000" for
    assets first used or installed ready for use between 1 July 2024 and
    30 June 2025. That extension was enacted by the Treasury Laws Amendment
    (Tax Incentives and Integrity) Act 2025 (Act No. 29 of 2025), Schedule 4,
    which substitutes "30 June 2025" for "30 June 2024" in the IT(TP) Act
    s.328-180 provisions. The consolidated in-force ITAA 1997 (legislation.gov.au
    C2004A05138) accordingly titles s.328-180 "Assets costing less than $20,000".

    This settles the $1,000-vs-$20,000 conflict: $1,000 is the dormant
    permanent base; $20,000 is the operative FY2025 figure via the transitional
    measure.
  citation: "IT(TP) Act 1997 s.328-180 as amended by Act No. 29 of 2025 Sch 4; ATO Guide to depreciating assets 2025 (NAT 1996-06.2025)."
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
  status: "draft"  # mechanism primary-source-read (legislation.gov.au consolidated ITAA + Act 29/2025); $20,000 value corroborated, pending primary read of NAT 1996-06.2025 for the headline figure
  prolog_trace_id: null
  error_vector: "The $20,000 FY2025 threshold and its mechanism were read from legislation.gov.au (consolidated ITAA 1997 C2004A05138 s.328-180 heading 'Assets costing less than $20,000') and the amending Act C2025A00029 Sch 4. The headline dollar figure in the ATO Guide (NAT 1996-06.2025) was not re-read from a live ATO surface (ato.gov.au HTTP 403 to the fetcher 2026-10-22). Confirm the figure in NAT 1996-06.2025 before promotion to 'canonical'."
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
  - rel: "sbrm:eligibilityRule"
    target: "urn:sbrm:rule:au:sbe-aggregated-turnover-test"

# Mutation ledger (append-only)
helm_mutations:
  - mutation_id: "mut-2026-10-22-mc00-tax-depreciation-fy2025-sbe-iawo-mint"
    ledger_id: "mut-2026-10-22-mc00-tax-depreciation-fy2025-sbe-iawo-mint"
    timestamp: "2026-10-22T07:45:00Z"
    agent_id: "clawdog-agent"
    authority: "andrew (gateway owner, 2026-10-22 07:41 UTC, webchat): add the three FY2025 tax-depreciation rate-table files; cite IT(TP)A 1997 s.328-180 as amended by Act No. 29 of 2025 Sch 4, plus the ATO Guide to depreciating assets 2025 (NAT 1996-06.2025)."
    mutation_type: "statutory_node_mint"
    content_hash_rolled: false
    previous_content_hash: null
    justification: |
      FY2025 small-business instant asset write-off threshold fact-node for
      the tax-depreciation gateway module. Operative value $20,000 for the
      2024-25 income year via IT(TP) Act 1997 s.328-180 as amended by the
      Treasury Laws Amendment (Tax Incentives and Integrity) Act 2025 (Act
      No. 29 of 2025) Schedule 4; permanent base in ITAA 1997 s.328-180 is
      $1,000. Mechanism read from legislation.gov.au (consolidated ITAA
      C2004A05138 + Act C2025A00029). Minted at 'draft' /
      human_override_required pending a primary read of NAT 1996-06.2025 for
      the headline figure. content_hash is the canonical
      PLACEHOLDER_CONTENT_HASH; anchors on the next
      scripts/audit_content_hashes.py --write pass.
---

# Small business instant asset write-off threshold (s.328-180) — Tax depreciation FY2025

> **Period:** Tax depreciation FY2025 (AU income year ending 30 June 2025)
> **Statutory source:** ITAA 1997 s.328-180, modified for 2024-25 by IT(TP) Act 1997 s.328-180 (Act No. 29 of 2025 Sch 4)
> **Calculator:** Tax depreciation — small-business-pool (AU tax kit)
> **Status:** `draft` — pending primary-source confirmation of the headline figure

## Value

`20000.00` (AUD) — operative FY2025 figure.

## The $1,000-vs-$20,000 settlement

- **Permanent base (ITAA 1997 s.328-180):** $1,000.
- **Operative FY2025 (2024-25 income year):** $20,000, via **Income Tax
  (Transitional Provisions) Act 1997 s.328-180**, extended by the **Treasury
  Laws Amendment (Tax Incentives and Integrity) Act 2025 (Act No. 29 of 2025),
  Schedule 4** (substitutes "30 June 2025" for "30 June 2024"). The
  consolidated in-force ITAA 1997 (legislation.gov.au C2004A05138) titles
  s.328-180 "Assets costing less than $20,000".

So $1,000 is the dormant permanent base; **$20,000 is the correct FY2025 value**.

## How the calculator consumes this

Consumed by `small-business-pool` on every call: the engine reads this node for
the instant-asset-write-off eligibility test (an item at/over the threshold
belongs in additions, not instant write-off) and emits
`urn:sbrm:rate:tax-depreciation:fy2025:sbe-instant-asset-write-off-threshold`
in `rate_uris_consumed`. The gateway hashes this file into the manifest.

## Status: draft

Mechanism read from legislation.gov.au (consolidated ITAA C2004A05138 and
amending Act C2025A00029 Sch 4). The ATO Guide (NAT 1996-06.2025) headline
figure was not re-read from a live ATO surface this session (ato.gov.au HTTP
403). Confirm before promotion to `canonical`.

*— ClawDog ∮*
