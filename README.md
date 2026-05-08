# clawdog-calculator-api

**Calculator-Constellation REST API — Egress Interface for the LodgeiT calculator pool.**

This repository implements the **REST surface** of the calculator constellation defined in [CLAWDOG/109 — Calculator Constellation](https://github.com/futureWA/clawdog-brain/blob/master/GLOBAL_NOTES/CLAWDOG/109_CALCULATOR_CONSTELLATION.md): a stateless HTTP wrapper over a deterministic SWI-Prolog substrate, projecting period-scoped statutory rate-tables, regression-anchored math, and content-addressable provenance through three coordinated surfaces (MCP, REST, direct Prolog HTTP). This repo is the **REST surface**; the MCP server (Phase 3b) and direct Prolog substrate (`lodgeit-labs/LodgeiT_FBT`, `lodgeit-labs/Depreciation_Transforms`, etc.) live elsewhere.

Per Standing Rule #7 (Repository Topology Discipline), this repo is classified as an **Egress Interface** — a transport buffer over the Brain-owned canonical substrate. Statutory authoring lives in the calculator repos and the Brain (`futureWA/clawdog-brain`); this repo contains no inlined statutory constants.

## Quick start

```bash
# Local dev: API + Prolog FBT engine together
make run

# In another shell:
curl -sS -X POST http://localhost:8000/v1/calculators/urn%3Asbrm%3Acalculator%3Afbt%3Acar-operating-cost/urn%3Asbrm%3Aperiod%3Afbt%3Afy2026 \
  -H 'Content-Type: application/json' \
  -d '{"form_of_finance":"owned","lease_payments":0,"fuel_repairs_servicing":3000,"registration_insurance":1500,"no_private_use_reduction":0,"business_use_percentage":75,"employee_contribution":200,"acquisition_date":"2024-04-01","opening_depreciated_value":55000,"days_held_in_fbt_year":365}'
# → {"taxable_value": 5547.75, "trace": {...}, "manifest": {...}, "advisory": "..."}
```

## Status

**Phase 3a** (CLAWDOG/109 §8.1) — REST API in front of `LodgeiT_FBT/FBT_Engine.pl`.

## License

MIT — see [Licence.txt](./Licence.txt).
