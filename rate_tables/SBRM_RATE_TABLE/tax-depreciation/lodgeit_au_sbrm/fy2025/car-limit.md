---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:tax-depreciation:fy2025:car-limit"
ontological_class: "StatutoryThreshold"
gist_equivalent: "gist:Magnitude"

# Calculator + period this rate belongs to
calculator: "tax-depreciation"
applies_to_calculator_uri: "urn:sbrm:calculator:tax-depreciation:decline-in-value"
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
  name: Car limit (first element of cost cap) — Division 40
  rate_id: "car-limit"
  unit: "AUD"
  value: 69674.00

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "Income Tax Assessment Act 1997 (ITAA 1997)"
  source_clause: "ITAA 1997 s.40-230 (car limit; first element of cost cap), indexed under Subdivision 960-M"
  policy_type: "Federal statute; dollar figure published annually by the Commissioner (CPI-indexed)"
  reference_text: |
    ITAA 1997 s.40-230 caps the first element of the cost of a car for
    decline-in-value purposes at the car limit for the financial year in
    which the taxpayer first uses it (or has it installed ready for use) for
    any purpose. Any excess above the car limit cannot be depreciated. The
    car limit is a motor vehicle designed to carry a load of less than 1
    tonne and fewer than 9 passengers; it is applied before any taxable-use
    reduction.

    For the 2024-25 income year the car limit is $69,674 (ATO Guide to
    depreciating assets 2025, NAT 1996-06.2025: "The car limit for 2024-25
    is $69,674."). The figure is CPI-indexed each year under Subdiv 960-M;
    where the indexation factor is 1 or less the limit is held unchanged.
  citation: "ATO Guide to depreciating assets 2025 (NAT 1996-06.2025): \"The car limit for 2024-25 is $69,674.\""
  ato_locator: "https://www.ato.gov.au/tax-rates-and-codes/car-cost-limit-for-depreciation"
  as_of_date: "2026-10-22"

# Cryptographic anchor
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  content_hash: "dc789ee199f7a420cc63e356ad5d1c35267c5f0599055f967d37069a2080da35"

# Cybernetic state
cybernetic_state:
  status: "draft"  # value cited to the ATO Guide (NAT 1996-06.2025) but not re-read from a live ATO/primary surface this session
  prolog_trace_id: null
  error_vector: "Value $69,674 is cited to the ATO Guide to depreciating assets 2025 (NAT 1996-06.2025) per operator direction and corroborated against secondary professional sources; it was NOT re-read from a live ato.gov.au page this session (ato.gov.au returned HTTP 403 Akamai block to the fetcher 2026-10-22). Confirm against the NAT 1996-06.2025 PDF or the ATO car-cost-limit page before promotion to 'canonical'."
  helm_trigger: "human_review_required_before_canonisation"
  human_override_required: true

# Semantic edges — links rate-tables together by calculator+period
semantic_edges:
  - rel: "sbrm:appliesIn"
    target: "urn:sbrm:period:tax-depreciation:fy2025"
  - rel: "sbrm:partOfRateTableFor"
    target: "urn:sbrm:calculator:tax-depreciation:decline-in-value"
  - rel: "sbrm:partOfKit"
    target: "urn:lodgeit:kit:tax-au-ato"

# Mutation ledger (append-only)
helm_mutations:
  - mutation_id: "mut-2026-10-22-mc00-tax-depreciation-fy2025-car-limit-mint"
    ledger_id: "mut-2026-10-22-mc00-tax-depreciation-fy2025-car-limit-mint"
    timestamp: "2026-10-22T07:45:00Z"
    agent_id: "clawdog-agent"
    authority: "andrew (gateway owner, 2026-10-22 07:41 UTC, webchat): add the three FY2025 tax-depreciation rate-table files, replacing the empty PROVENANCE note; cite the ATO Guide to depreciating assets 2025 (NAT 1996-06.2025) for the car limit."
    mutation_type: "statutory_node_mint"
    content_hash_rolled: false
    previous_content_hash: null
    justification: |
      FY2025 car limit fact-node for the tax-depreciation gateway module.
      Value $69,674 for the 2024-25 income year, cited to the ATO Guide to
      depreciating assets 2025 (NAT 1996-06.2025). Minted at 'draft' /
      human_override_required because ato.gov.au was Akamai-blocked (HTTP
      403) to the fetcher this session; the value is cited per operator
      direction and secondary-corroborated, pending a primary-source read of
      NAT 1996-06.2025 before promotion. content_hash anchored via
      scripts/audit_content_hashes.py --write at mint time.
---

# Car limit (s.40-230) — Tax depreciation FY2025

> **Period:** Tax depreciation FY2025 (AU income year ending 30 June 2025)
> **Statutory source:** ITAA 1997 s.40-230 (indexed under Subdivision 960-M)
> **Calculator:** Tax depreciation — decline-in-value (AU tax kit)
> **Status:** `draft` — value cited to NAT 1996-06.2025, pending primary-source confirmation

## Value

`69674.00` (AUD)

## Statutory provenance

ITAA 1997 s.40-230 caps the first element of a car's cost for decline-in-value
purposes at the car limit for the year it is first used or installed ready for
use. Excess above the limit is not depreciable. CPI-indexed under Subdiv 960-M.

**Citation (operator-directed):** ATO Guide to depreciating assets 2025
(NAT 1996-06.2025): *"The car limit for 2024-25 is $69,674."*

## How the calculator consumes this

Consumed by `decline-in-value` only when `is_car: true`: the engine reads this
node, caps `cost_base = min(cost, car_limit)`, and emits
`urn:sbrm:rate:tax-depreciation:fy2025:car-limit` in `rate_uris_consumed`. The
gateway then hashes this file into the response manifest.

## Status: draft

ato.gov.au returned HTTP 403 (Akamai edge block) to the fetcher on 2026-10-22,
so the value was cited to NAT 1996-06.2025 per operator direction and
corroborated against secondary professional sources, not re-read from a live
ATO/primary surface this session. Confirm against the NAT 1996-06.2025 PDF (or
the ATO car-cost-limit page) before promotion to `canonical`.

*— ClawDog ∮*
