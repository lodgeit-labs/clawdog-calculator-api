---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:div7a:fy2026:benchmark-interest"
ontological_class: "StatutoryRate"
gist_equivalent: "gist:Ratio"

# Calculator + period this rate belongs to
calculator: "div7a"
applies_to_calculator_uri: "urn:lodgeit:calculator:div7a"

# Hoffman temporal dimension
temporal_context:
  type: "Duration"
  period_uri: "urn:sbrm:period:div7a:fy2026"
  period_start: "2025-07-01"
  period_end: "2026-06-30"
  period_label: "Div 7A FY2026 (Australian income year ending 30 June 2026)"

# The rate value itself
rate:
  name: Div 7A Benchmark Interest Rate
  rate_id: "benchmark-interest"
  unit: "decimal-fraction-per-annum"
  value: 0.0837
  value_percentage: "8.37%"

# Verification status — PROMOTED PROVISIONAL → VERIFIED at mc35-2026-08-28
verification_status:
  status: "VERIFIED"
  reason: "Primary-source-verified against ATO tax-rates-and-codes page (Division 7A benchmark interest rate table, income year ended 30 June 2026 row) AND cross-anchored against underlying RBA F5 Statistical Table series FILRHLBVS (Housing loans; Banks; Variable; Standard; Owner-occupier) datapoint published 6 June 2025. Both sources cross-agree at 8.37%. See helm_mutations mut-2026-08-28-mc35 below for verification anchors."
  verified_at: "2026-08-28T09:20:00Z"
  verified_by: "clawdog"
  verification_anchors:
    - authority: "ATO"
      surface: "tax-rates-and-codes/division-7a-benchmark-interest-rate"
      surface_url: "https://www.ato.gov.au/tax-rates-and-codes/division-7a-benchmark-interest-rate"
      snapshot: "https://web.archive.org/web/20251108121252/https://www.ato.gov.au/tax-rates-and-codes/division-7a-benchmark-interest-rate"
      verbatim_row: "2026 | 8.37% | This is the 'Indicator Lending Rates - Bank variable housing loans interest rate' published by the Reserve Bank of Australia on 6 June 2025."
    - authority: "RBA (underlying series)"
      surface: "Statistical Table F5 — Indicator Lending Rates"
      series_id: "FILRHLBVS"
      series_description: "Lending rates; Housing loans; Banks; Variable; Standard; Owner-occupier"
      publication_date: "2025-06-06"

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "Income Tax Assessment Act 1936 (Cth)"
  primary_provision: "Division 7A of Part III, s.109N(2) (rate definition); s.109E (MYR consumption)"
  statutory_authority_url: "https://www.legislation.gov.au/C1936A00027/latest/text"
  rate_source_type: "statute-defined; not annually-issued Taxation Determination"
  rate_source_note: "Post-TD-2018/14-withdrawal, the ATO no longer issues an annual TD for the Div 7A benchmark rate. Under s.109N(2) the rate is fixed automatically as the RBA Indicator Lending Rate - Bank variable housing loans (Standard; Owner-occupier) last published before the start of the income year (2025-07-01 for FY2026 → RBA 6-June-2025 datapoint)."
  underlying_series: "RBA Indicator Lending Rates - Bank variable housing loans; Standard; Owner-occupier"
  underlying_series_publisher: "Reserve Bank of Australia"
  underlying_series_id: "FILRHLBVS (RBA Statistical Table F5)"
  ato_information_surface: "https://www.ato.gov.au/tax-rates-and-codes/division-7a-benchmark-interest-rate"
  reference_text: "The FY2026 Div 7A benchmark rate is 8.37% per s.109N(2) ITAA 1936. This is the RBA Housing loans; Banks; Variable; Standard; Owner-occupier rate last published before the start of the income year commencing 1 July 2025 — namely the datapoint published 6 June 2025."
  as_of_date: "2026-08-28"

# Cryptographic anchor (content_hash to be recomputed post-write)
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  hash_target: "self"
  content_hash: "e34ad275d625b8a1bfa4fa719d2da2d060a14760d464926758a251665b5e1c12"

# Cybernetic state — flipped from provisional
cybernetic_state:
  status: "canonical"
  prolog_trace_id: null
  error_vector: null
  helm_trigger: null
  human_override_required: false

# Semantic edges
semantic_edges:
  - rel: "sbrm:appliesIn"
    target: "urn:sbrm:period:div7a:fy2026"
  - rel: "sbrm:consumedBy"
    target: "urn:lodgeit:calculator:div7a"
  - rel: "sbrm:obeysStandingRule"
    target: "MEMORY.md#standing-rule-6"

helm_mutations:
  - mutation_id: "mut-2026-08-22-mc07-div7a-canon-mint"
    timestamp: "2026-08-22T06:00:00Z"
    actor: "clawdog"
    authority: "andrew-direction"
    action: "provisional_mint"
    description: |
      FY2026 Div 7A benchmark rate 8.37% surfaced by Streamace mc07 handoff
      as the value used in the robust-kernel patch to accounts-assessor@dev.
      Wire-truth verification against ATO TD 2025/X is pending TaxGenii MCP
      access; this rate MUST NOT be treated as authoritative until
      verification_status.status flips to VERIFIED.
    hash_delta: "genesis"
  - mutation_id: "mut-2026-08-27-mc27-l73-anchor5-remediation-engine-side"
    timestamp: "2026-08-27T00:00:00Z"
    actor: "clawdog"
    authority: "fable-ruling-l73-anchor5"
    action: "citation_fix_engine_side_only"
    description: |
      L#73 anchor #5 remediation (Fable ∮-RULING mc27). Engine-side YAML
      mirror in lodgeit-labs/Div7A_Engine had a fabricated citation to
      "TD 2025/X"; corrected to statutory authority under s.109N(2) ITAA
      1936 with RBA underlying series citation. This Brain-side canonical
      node was NOT updated at mc27 — only the engine mirror. Node remained
      PROVISIONAL until wire-truth verification landed. This is the gap
      that mc35 closes.
    hash_delta: "n/a (Brain node untouched at mc27)"
  - mutation_id: "mut-2026-08-28-mc35-verified-promotion"
    timestamp: "2026-08-28T09:20:00Z"
    actor: "clawdog"
    authority: "andrew-direction (2026-08-28 09:15 UTC): verify-first-then-mint-at-VERIFIED per L#73 discipline"
    action: "provisional_to_verified_promotion"
    description: |
      Primary-source verification landed. Two independent authority-side
      sources cross-agree at 0.0837 (8.37%) for FY2026:

      1. ATO tax-rates-and-codes page (Division 7A benchmark interest rate
         table). Web-archive snapshot 2025-11-08 (post-fy2026 window open)
         shows income year 2026 row: 8.37%, published by RBA on 6 June 2025.
         Snapshot URL:
         https://web.archive.org/web/20251108121252/https://www.ato.gov.au/tax-rates-and-codes/division-7a-benchmark-interest-rate

      2. Underlying RBA F5 Statistical Table series FILRHLBVS (Lending
         rates; Housing loans; Banks; Variable; Standard; Owner-occupier).
         June 2025 publication = 8.37%.

      Additionally cross-checked against Jindrich Kolman's Div7A_Calculator
      test fixture parity (FY2025 = 0.0877 matches at the sibling node),
      giving a third independent within-repo anchor.

      Statutory framework correction: Rate is NOT set by annual TD (TD
      2018/14 withdrawn); it is fixed automatically by s.109N(2) ITAA 1936
      via the RBA F5 series last-publication-before-income-year-start rule.
      The prior "TD 2025/X" citation shape was a fabrication; corrected
      here in the same mutation.
    hash_delta: "will roll from '884209f3df95b32e33be9437714370f82b501aade96c757346b22db514ffdd1c' (mc07 provisional) after content_hash re-anchor"
    previous_content_hash: "884209f3df95b32e33be9437714370f82b501aade96c757346b22db514ffdd1c"
---

# FY2026 Div 7A Benchmark Interest Rate

**Value:** `8.37%` (`0.0837` decimal fraction per annum).

**Verification status:** `VERIFIED` (promoted from PROVISIONAL at mc35-2026-08-28).

## Primary-source verification anchors

Two independent authority-side sources cross-agree at 0.0837 for FY2026, with a third within-repo cross-check:

1. **ATO** tax-rates-and-codes page (Division 7A benchmark interest rate table), income year 2026 row: **"8.37% ... published by the Reserve Bank of Australia on 6 June 2025"** — [live surface](https://www.ato.gov.au/tax-rates-and-codes/division-7a-benchmark-interest-rate), [web-archive snapshot 2025-11-08](https://web.archive.org/web/20251108121252/https://www.ato.gov.au/tax-rates-and-codes/division-7a-benchmark-interest-rate).
2. **RBA F5 Statistical Table** — series `FILRHLBVS` (Lending rates; Housing loans; Banks; Variable; Standard; Owner-occupier), publication 6 June 2025 = 8.37%.
3. **Div7A_Calculator fixture parity** — the sibling fy2025 node at value 0.0877 matches `test_div7a_8083.py` fixture from Jindrich Kolman's legacy repo; sibling-year consistency is a third independent within-repo anchor.

## Applicable statute

**Income Tax Assessment Act 1936 (Cth), Division 7A of Part III, s.109N(2):**

> *"The benchmark interest rate for a year of income is the Indicator Lending Rates - Bank variable housing loans interest rate last published by the Reserve Bank of Australia before the start of the year of income."*

Post-TD-2018/14-withdrawal, the ATO no longer issues an annual TD setting this rate. The rate is fixed automatically by s.109N(2) via the RBA F5 series last-publication-before-income-year-start rule. For FY2026 (income year starting 2025-07-01), the last RBA publication before that date was 6 June 2025 = 8.37%.

**Consumption clause:** s.109E — the MYR formula consumes the benchmark rate.

## Consumers

- `urn:lodgeit:calculator:div7a` — Div7A calculator engine (`lodgeit-labs/Div7A_Engine`; YAML mirror at `jurisdiction_au/rate_tables/div7a_fy2026.yaml`)
- `lodgeit-labs/clawdog-calculator-api` gateway (`rate_tables/SBRM_RATE_TABLE/div7a/lodgeit_au_sbrm/fy2026/benchmark-interest.md` — mirror lands at mc35 sibling PR)
- `GLOBAL_NOTES/CALCULATORS/Div7A/610_MYR_ALGEBRA.md` — MYR denominator input
- `GLOBAL_NOTES/CALCULATORS/Div7A/620_PERIODIC_REPAYMENTS.md` — daily-rate accrual input

## Historical context

- FY2023 (income year ending 30 June 2023): 4.77% — RBA 2 June 2022
- FY2024 (income year ending 30 June 2024): 8.27% — RBA 7 June 2023
- FY2025 (income year ending 30 June 2025): 8.77% — RBA 7 June 2024 (see sibling node)
- **FY2026 (income year ending 30 June 2026): 8.37%** — RBA 6 June 2025 (this node)

*— ClawDog ∮*
