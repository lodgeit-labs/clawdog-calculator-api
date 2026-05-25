---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:fbt:fy2026:days-in-year-by-fy"
ontological_class: "StatutoryRate"
gist_equivalent: "gist:Magnitude"

# Calculator + period this rate belongs to
calculator: "fbt"
applies_to_calculator_uri: "urn:lodgeit:calculator:fbt"

# Hoffman temporal dimension — this node is the FY2026 cohort's lookup table
# for days-in-year-by-FY, used by the chained DV walk that touches every
# FBT year from acquisition through FY2026. The node is authored under the
# FY2026 cohort URN; future FY rotations (FY2027+) will either mint a
# parallel cohort node or helm-roll this one to extend the components.
temporal_context:
  type: "Duration"
  period_uri: "urn:sbrm:period:fbt:fy2026"
  period_start: "2025-04-01"
  period_end: "2026-03-31"
  period_label: "FBT FY2026 (year ending 31 March 2026) — cohort lookup table"

# The rate value itself — COMPOUND (days-in-year per FBT year, FY2022 through FY2030)
rate:
  name: Days-in-FBT-Year by FY (chained-DV-walk lookup table; covers FY2022 through FY2030)
  rate_id: "days-in-year-by-fy"
  unit: "days"
  shape: "compound"
  value:
    fy2022: 365
    fy2023: 365
    fy2024: 366
    fy2025: 365
    fy2026: 365
    fy2027: 365
    fy2028: 366
    fy2029: 365
    fy2030: 365
  components:
    fy2022:
      days: 365
      fbt_year_start: "2021-04-01"
      fbt_year_end:   "2022-03-31"
      contains_29_feb: false
      label: "FBT FY2022 (1 Apr 2021 – 31 Mar 2022)"
    fy2023:
      days: 365
      fbt_year_start: "2022-04-01"
      fbt_year_end:   "2023-03-31"
      contains_29_feb: false
      label: "FBT FY2023 (1 Apr 2022 – 31 Mar 2023)"
    fy2024:
      days: 366
      fbt_year_start: "2023-04-01"
      fbt_year_end:   "2024-03-31"
      contains_29_feb: true
      contains_29_feb_date: "2024-02-29"
      label: "FBT FY2024 (1 Apr 2023 – 31 Mar 2024) — leap-containing"
    fy2025:
      days: 365
      fbt_year_start: "2024-04-01"
      fbt_year_end:   "2025-03-31"
      contains_29_feb: false
      label: "FBT FY2025 (1 Apr 2024 – 31 Mar 2025)"
    fy2026:
      days: 365
      fbt_year_start: "2025-04-01"
      fbt_year_end:   "2026-03-31"
      contains_29_feb: false
      label: "FBT FY2026 (1 Apr 2025 – 31 Mar 2026) — current FBT year"
    fy2027:
      days: 365
      fbt_year_start: "2026-04-01"
      fbt_year_end:   "2027-03-31"
      contains_29_feb: false
      label: "FBT FY2027 (1 Apr 2026 – 31 Mar 2027) — forward-looking"
    fy2028:
      days: 366
      fbt_year_start: "2027-04-01"
      fbt_year_end:   "2028-03-31"
      contains_29_feb: true
      contains_29_feb_date: "2028-02-29"
      label: "FBT FY2028 (1 Apr 2027 – 31 Mar 2028) — forward-looking, leap-containing"
    fy2029:
      days: 365
      fbt_year_start: "2028-04-01"
      fbt_year_end:   "2029-03-31"
      contains_29_feb: false
      label: "FBT FY2029 (1 Apr 2028 – 31 Mar 2029) — forward-looking"
    fy2030:
      days: 365
      fbt_year_start: "2029-04-01"
      fbt_year_end:   "2030-03-31"
      contains_29_feb: false
      label: "FBT FY2030 (1 Apr 2029 – 31 Mar 2030) — forward-looking"

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "Fringe Benefits Tax Assessment Act 1986 (FBTAA), s.136 (definition: FBT year)"
  source_clause: "FBTAA s.136 — defines the FBT year as 1 April to 31 March; days-in-year derived from this definition + the Gregorian leap-year rule"
  reference_text: |
    FBT year FY<N> spans 1 April (N-1) to 31 March N inclusive. The year
    contains 29 February if and only if N is a leap year (divisible by 4
    and not by 100, OR divisible by 400). This compound rate-table fact-node
    enumerates days-in-year for each FBT year potentially traversed by the
    chained deemed-depreciation walk (OT #81 sprint Rung 1, mut-2026-05-22-mc05).

    The chained walk consumes per-FY days-in-year via rate_lookup/4:
        rate_lookup('urn:sbrm:period:fbt:fy2026',
                    'days-in-year-by-fy', fy2024, Days).
        % Days = 366.

    Leap-containing FBT years in the cohort: FY2024, FY2028.

    The pre-existing scalar 'urn:sbrm:rate:fbt:fy2026:days-in-year' (= 365)
    remains canonical for single-FY callers; the new compound is a sibling
    for the chained-DV consumer per Standing Rule #6 (Hoffman temporal-
    dimension discipline).
  as_of_date: "2026-05-22"

# Cryptographic anchor
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  content_hash: "8f63d3bd1685acca00717d88cc262c79c731286cfc98a19bdb6c1b2648c8baca"

# Cybernetic state
cybernetic_state:
  status: "canonical"
  prolog_trace_id: null
  error_vector: null
  helm_trigger: null
  human_override_required: false

# Semantic edges — links rate-tables together by calculator + cohort
semantic_edges:
  - rel: "sbrm:appliesIn"
    target: "urn:sbrm:period:fbt:fy2026"
  - rel: "sbrm:partOfRateTableFor"
    target: "urn:lodgeit:calculator:fbt"
  - rel: "sbrm:companionTo"
    target: "urn:sbrm:rate:fbt:fy2026:deemed-depreciation-rates"
  - rel: "sbrm:companionTo"
    target: "urn:sbrm:rate:fbt:fy2026:benchmark-interest"
  - rel: "sbrm:siblingScalarOf"
    target: "urn:sbrm:rate:fbt:fy2026:days-in-year"

# Mutation ledger (append-only)
helm_mutations:
  - ledger_id: "mut-2026-05-22-mc05-ot81-rung1-days-in-year-by-fy-mint"
    timestamp: "2026-05-22T02:50:00Z"
    agent_id: "clawdog-agent"
    authority: "andrew (workspace owner, 2026-05-22 02:41 UTC, webchat control UI: 'Proceed. We need to be able to match NTAA.')"
    mutation_type: "node_creation"
    previous_path: null
    new_path: "SBRM_RATE_TABLE/fbt/lodgeit_au_sbrm/fy2026/days-in-year-by-fy.md"
    content_hash_rolled: false
    previous_content_hash: null
    justification: |
      First-mint of the chained-DV lookup-table fact-node under OT #81 sprint
      Rung 1. The node enumerates days-in-FBT-year for FY2022 through FY2030
      (initial cohort; extends annually). Consumed by the chained
      fbt_car_oc_deemed_amounts_chained/N predicate (landing in Rung 3) via
      rate_lookup/4 with Component = fy<N>.

      The values are derived from the FBT year definition (FBTAA s.136: 1 April
      to 31 March) plus the Gregorian leap-year rule. Leap-containing FBT
      years in this cohort: FY2024 (contains 29 Feb 2024) and FY2028 (contains
      29 Feb 2028).

      Standing Rule #6 first-class fact-node addition: no calculator source
      inlines 365 or 366 in the chained walk; all per-year prorate looks up
      via rate_lookup/4 against this compound.

      Standing Rule #7 (Bilateral Graph owns provenance): Brain canonical;
      LodgeiT_FBT will vendor byte-identical in a follow-up Egress PR
      (mirroring the OT #80 + OT #79 cross-org sync pattern).
---

# Days-in-FBT-Year by FY — Chained-DV-Walk Lookup Table (FY2022 through FY2030)

> **Period (canonical-authoring cohort):** FBT FY2026 (year ending 31 March 2026)
> **Statutory source:** FBTAA s.136 (FBT year definition) + Gregorian leap-year rule
> **Calculator:** FBT (Fringe Benefits Tax — Australia)
> **Shape:** COMPOUND — one component per FBT year in the cohort

## Values

| FBT Year | Start         | End           | Days | Contains 29 Feb? |
|----------|---------------|---------------|------|------------------|
| FY2022   | 2021-04-01    | 2022-03-31    | 365  | No               |
| FY2023   | 2022-04-01    | 2023-03-31    | 365  | No               |
| FY2024   | 2023-04-01    | 2024-03-31    | 366  | **Yes** (29 Feb 2024) |
| FY2025   | 2024-04-01    | 2025-03-31    | 365  | No               |
| FY2026   | 2025-04-01    | 2026-03-31    | 365  | No (current FBT year) |
| FY2027   | 2026-04-01    | 2027-03-31    | 365  | No               |
| FY2028   | 2027-04-01    | 2028-03-31    | 366  | **Yes** (29 Feb 2028) |
| FY2029   | 2028-04-01    | 2029-03-31    | 365  | No               |
| FY2030   | 2029-04-01    | 2030-03-31    | 365  | No               |

## Statutory derivation

FBTAA s.136 defines the FBT year as 1 April to 31 March. The days-in-year value is then the standard Gregorian calendar count for the range, which equals 366 when 29 February falls inside the range. By construction, an FBT year FY<N> contains 29 February if and only if **N is a leap year** (divisible by 4 and not by 100, OR divisible by 400). For the cohort enumerated above:

- **FY2024** contains 29 Feb 2024 → 366 days. (2024: divisible by 4 ✓, not by 100 ✓.)
- **FY2028** contains 29 Feb 2028 → 366 days. (2028: divisible by 4 ✓, not by 100 ✓.)
- All other listed FYs: 365 days.

## How the calculator consumes this

The chained DV-walk predicate (landing in OT #81 Rung 3) walks each FBT year from FY-of-acquisition to the current FBT year, applying the diminishing-value step:

```
DV_start_of_FY<N+1> = DV_start_of_FY<N> − (DV_start_of_FY<N> × DepRate × DaysHeld<N> / DaysInYear<N>)
```

Each per-year `DaysInYear<N>` looks up via:

```prolog
rate_lookup('urn:sbrm:period:fbt:fy2026', 'days-in-year-by-fy', fy2024, Days).
% Days = 366
rate_lookup('urn:sbrm:period:fbt:fy2026', 'days-in-year-by-fy', fy2025, Days).
% Days = 365
```

The bridge-side dispatch (acquisition-date → FY-of-acquisition → enumerate FYs through current → look up each year's days-in-year) is computed in `fbt_car_oc_deemed_amounts_chained/N`; the per-year primitive `fbt_car_oc_deemed_amounts/9` is invoked once per FY with the resolved `OpeningDV` + `DaysHeld` + `DaysInYear`.

## Notes

**Cohort extension policy:** if a chained walk needs an FBT year outside this cohort (FY2021 or earlier; FY2031 or later), the engine should throw `error(fbt_year_outside_cohort(FY, available_range:[fy2022, fy2030]), _)` rather than silently defaulting. Future FY rotations extend this node via helm-roll (`mutation_type: "audit_driven_first_anchor"` or similar) — never silent fallback to a default day count.

**Why a compound (and not 9 per-FY scalar nodes):** the chained walk needs all per-year values resolved together at runtime; a compound node is one disk + one resolver round-trip vs nine. Mirrors the existing `deemed-depreciation-rates.md` compound shape (which has 3 tier components per Lesson #36 bridge-side dispatch pattern).

**Pre-existing scalar sibling:** `urn:sbrm:rate:fbt:fy2026:days-in-year` (= 365) remains canonical for single-FY callers (the `fbt_car_oc_deemed_compute/8` primitive uses it). This compound is a sibling for the chained-DV consumer. Standing Rule #3 append-only preserves both surfaces; no helm-roll on the scalar.

**Cross-references:**
- **Engine consumer (forthcoming):** `fbt_car_oc_deemed_amounts_chained/N` in `FBT_Engine.pl` (OT #81 Rung 3).
- **Brain canon:** clawdog-brain OT #81 (statute-deviation finding) + sprint design `_drafts/fbt-chained-dv-sprint-design-2026-05-22-mc05.md`.
- **Companion compound:** `deemed-depreciation-rates.md` (the 3-tier rate compound; same shape and consumer).

## Mutation ledger

This node was minted in `mut-2026-05-22-mc05-ot81-rung1-days-in-year-by-fy-mint` (Brain PR #252; bundled with OT #81 banking per OT #79 mc04 precedent). LodgeiT_FBT re-vendor PR follows post-merge. Future amendments append to `helm_mutations[]` per the Zero-Hallucination Law.

*— ClawDog ∮*
