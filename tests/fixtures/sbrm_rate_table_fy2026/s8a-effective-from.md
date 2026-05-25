---
"@context": "https://lodgeit-labs.org/sbrm/v1"
"@id": "urn:sbrm:rate:fbt:fy2026:s8a-effective-from"
ontological_class: "StatutoryDate"
gist_equivalent: "gist:Date"

# Calculator + period this fact belongs to
calculator: "fbt"
applies_to_calculator_uri: "urn:lodgeit:calculator:fbt"

# Hoffman temporal dimension — first-class
temporal_context:
  type: "Duration"
  period_uri: "urn:sbrm:period:fbt:fy2026"
  period_start: "2025-04-01"
  period_end: "2026-03-31"
  period_label: "FBT FY2026 (year ending 31 March 2026)"

# The statute fact itself
rate:
  name: FBTAA s.8A — electric-vehicle exemption effective-from date
  rate_id: "s8a-effective-from"
  unit: "iso-date"
  value: "2022-07-01"

# Statutory provenance
statutory_source:
  jurisdiction: "AU"
  primary_act: "Fringe Benefits Tax Assessment Act 1986 (FBTAA)"
  source_clause: FBTAA s.8A
  ato_toolkit_locator: "2026 FBT Toolkit, 'Exempt electric vehicles' section — 'first held on or after 1 July 2022'"
  reference_text: "Australian Taxation Office, *Fringe Benefits Tax — A Guide for Employers* (2026 edition). ATO 2026 FBT Toolkit available at LodgeiT_FBT/extracted_toolkit/2026_FBT_toolkit.txt (toolkit lines 211–213 + 4029–4042 + 5190–5201)."
  as_of_date: "2026-05-21"

# Cryptographic anchor
cryptographic_anchor:
  ipfs_cid: "PENDING_IPFS_BROADCAST"
  hash_domain: "pre_anchor_draft"
  content_hash: "1791455d068fa28fc518eb93f5acaefde3d391d0aff25948b4b6f686da7d60f3"

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
  - rel: "sbrm:statuteFact"
    target: "FBTAA_s8A"

# Mutation ledger (append-only)
helm_mutations: []
---

# FBTAA s.8A — electric-vehicle exemption effective-from date

> **Period:** FBT FY2026 (year ending 31 March 2026)
> **Statutory source:** FBTAA s.8A
> **Calculator:** FBT (Fringe Benefits Tax — Australia)

## Value

`2022-07-01` (ISO-8601 date)

## Statutory provenance

FBTAA s.8A introduces a full-FBT exemption for certain low/zero-emission cars (electric vehicles) provided as car benefits **on or after 1 July 2022**.

**ATO Toolkit verbatim (lines 4029–4032):**

> *"Broadly, certain low or no emission cars ('electric vehicles') are exempt from FBT if they are provided as car benefits on or after 1 July 2022. Refer to S.8A of the FBT Act. Amongst other requirements, for this exemption to apply, the electric vehicle needs to be first held on or after 1 July 2022…"*

This node is the first of the four conjunctive conditions for s.8A to fire (the others: `s8a-lct-low-emission-threshold` for the first-retail-sale-value condition; `s8a-phev-exclusion-effective-from` for the 2025-04-01 PHEV carve-out; vehicle-type tag from the input dict for the zero/low-emission condition).

## How the calculator consumes this

The s.8A predicate (introduced in PR-C of the OT #79 sprint ladder) looks this up at execution time via:

```prolog
rate_lookup_string('urn:sbrm:period:fbt:fy2026', 's8a-effective-from', DateStr).
```

The engine source carries algorithm only — never inlines `"2022-07-01"` as a magic string. This is the Standing-Rule-#6 (Hoffman Temporal-Dimension Discipline) shape, generalised to date-valued statute facts.

## Cross-references

- **Sibling rate-table nodes (s.8A constellation):**
  - `s8a-lct-low-emission-threshold.md` (AUD threshold, FY2026 = 91387)
  - `s8a-phev-exclusion-effective-from.md` (2025-04-01)
- **Engine-side consumer (forthcoming):** `s8a_exempt/3` predicate in `FBT_Engine.pl` (OT #79 sprint Rung 3).
- **Brain canon:** clawdog-brain OT #79 (statute-deviation finding) + sprint design `_drafts/fbt-s8a-sprint-design-2026-05-21-mc04.md`.

## Mutation ledger

This node was minted in `mut-2026-05-21-mc04-s8a-rate-table-mint` (LodgeiT_FBT PR-A; combined with `s8a-lct-low-emission-threshold.md` + `s8a-phev-exclusion-effective-from.md` as a three-node batch). Future amendments append to `helm_mutations[]` per the Zero-Hallucination Law.

*— ClawDog ∮*
