# Phase 3a Constellation — Verification Kit

> Banked 2026-05-24 mc10 after the kit was field-validated by an independent
> verifier ("V2") and confirmed deterministic-results trustworthy. Last
> end-to-end pass: V2 report 23:47 UTC + ClawDog wire-confirmation immediately
> after.
>
> **Provenance:** Designed by ClawDog 2026-05-24 mc09; first executed by V2
> (assumed independent — see § Provenance Caveat below) immediately after PR
> #5 (Pydantic schema extension for OT #81 chained-DV `acquisition_cost`)
> merged.

You're being asked to independently verify that the recently-deployed
two-service application is running correctly on Google Cloud Run.

**The application:** Australian Fringe Benefits Tax (FBT) calculator.
**Two services on Cloud Run** in region `australia-southeast1`, project
`lodgeit-calc-constellation`:

1. **Engine** (Prolog HTTP service): `https://fbt-engine-8340695160.australia-southeast1.run.app`
2. **REST API** (FastAPI wrapper in front of the engine): `https://fbt-calculator-api-8340695160.australia-southeast1.run.app`

You **don't need to understand** how FBT works. You just need to run the
curl commands and check whether the outputs match the "Expected" blocks. If
everything matches, the deployment is correct. If anything doesn't match,
paste your output back to whoever asked you to run this.

You'll need: `curl`, `python3`, `gcloud` (authenticated as the project's
IAM principal), and optionally `docker`. The `file` utility is helpful
inside the container but not strictly required (see B2 fallback).

**Do not skip steps.** The discrepancies, if any, only surface when you
run all of them.

**Do not run any `gcloud run deploy` or `docker push` commands.** This is
a read-only verification. If something is broken, report it — do not try
to fix it.

---

## Section A — External-surface tests (no GCP credentials needed)

### A1. Engine `/health` returns 200

```bash
curl -fsS https://fbt-engine-8340695160.australia-southeast1.run.app/health
```

**Expected:**

```json
{"port_env":"8080","rate_table_dir":"/app/SBRM_RATE_TABLE/fbt/lodgeit_au_sbrm/fy2026","rate_table_facts":9,"rate_table_facts_compound":12,"status":"ok","surface":"production","swipl_version":"90209"}
```

Pay attention to: `rate_table_facts` == **9**, `rate_table_facts_compound`
== **12**, `swipl_version` == **90209**, `surface` == **"production"**.

---

### A2. REST API root surface

```bash
curl -fsS https://fbt-calculator-api-8340695160.australia-southeast1.run.app/openapi.json \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('paths:', sorted(d.get('paths',{}).keys())); print('title:', d.get('info',{}).get('title')); print('version:', d.get('info',{}).get('version'))"
```

**Expected:**

```
paths: ['/healthz', '/v1/calculators', '/v1/calculators/depreciation/audit/{period_uri}', '/v1/calculators/{calc_uri}/{period_uri}', '/v1/rates/{period_uri}', '/v1/rates/{period_uri}/{rate_id}']
title: ClawDog Calculator-Constellation REST API
version: 0.1.0a0
```

---

### A3. Calculator registry endpoint

```bash
curl -fsS https://fbt-calculator-api-8340695160.australia-southeast1.run.app/v1/calculators \
  | python3 -m json.tool
```

**Expected:** a JSON array with **2 entries**, one with
`"calc_uri": "urn:sbrm:calculator:fbt:car-operating-cost"` and one with
`"calc_uri": "urn:sbrm:calculator:depreciation:audit"`. Both must have
`"jurisdiction": "AU"`.

---

### A4. Critical end-to-end — NTAA Row 3 via the REST API

```bash
API_URL="https://fbt-calculator-api-8340695160.australia-southeast1.run.app"
CALC_URI="urn%3Asbrm%3Acalculator%3Afbt%3Acar-operating-cost"
PERIOD_URI="urn%3Asbrm%3Aperiod%3Afbt%3Afy2026"

curl -fsS -X POST "$API_URL/v1/calculators/$CALC_URI/$PERIOD_URI" \
  -H "Content-Type: application/json" \
  -d '{
    "businessUsePercentage": 75,
    "formOfFinance": "owned",
    "fuelRepairsServicing": 3000,
    "registrationInsurance": 1500,
    "employeeContribution": 200,
    "noPrivateUseReduction": 0,
    "acquisitionCost": 50000,
    "acquisitionDate": "2024-01-01"
  }' | python3 -c "
import sys, json
d = json.load(sys.stdin)
t = d.get('trace', {})
m = d.get('manifest', {})
print('  taxable_value:', d.get('taxable_value'))
print('  deemed_depreciation:', t.get('deemed_depreciation'))
print('  deemed_interest:', t.get('deemed_interest'))
print('  deemed_total:', t.get('deemed_total'))
print('  business_use_pct:', t.get('business_use_pct'))
print('  dispatch:', t.get('deemed_dispatch'))
print('  manifest rate_table_uris count:', len(m.get('rate_table_uris', [])))
print('  advisory present:', 'advisory' in d)
"
```

**Expected:**

```
  taxable_value: 3880.96  (may show as 3880.959999999999 — the rounded value is correct)
  deemed_depreciation: 8792.26
  deemed_interest: 3031.57
  deemed_total: 11823.83
  business_use_pct: 75.0
  dispatch: computed_chained
  manifest rate_table_uris count: 4
  advisory present: True
```

---

### A5. Row 4 + Row 5 (parametric sweep)

**Row 4:**

```bash
curl -fsS -X POST "$API_URL/v1/calculators/$CALC_URI/$PERIOD_URI" \
  -H "Content-Type: application/json" \
  -d '{
    "businessUsePercentage": 75,
    "formOfFinance": "owned",
    "fuelRepairsServicing": 3000,
    "registrationInsurance": 1500,
    "employeeContribution": 200,
    "noPrivateUseReduction": 0,
    "acquisitionCost": 80000,
    "acquisitionDate": "2023-06-01"
  }' | python3 -c "import sys,json; d=json.load(sys.stdin); t=d.get('trace',{}); print('TV:', d.get('taxable_value'), 'dep:', t.get('deemed_depreciation'), 'int:', t.get('deemed_interest'), 'total:', t.get('deemed_total'))"
```

**Expected:** `TV: ~4917.37 dep: 11875 int: 4094.5 total: 15969.5`

**Row 5:**

```bash
curl -fsS -X POST "$API_URL/v1/calculators/$CALC_URI/$PERIOD_URI" \
  -H "Content-Type: application/json" \
  -d '{
    "businessUsePercentage": 75,
    "formOfFinance": "owned",
    "fuelRepairsServicing": 0,
    "registrationInsurance": 0,
    "employeeContribution": 0,
    "noPrivateUseReduction": 0,
    "acquisitionCost": 45000,
    "acquisitionDate": "2025-10-01",
    "daysHeldInFBTYear": 182
  }' | python3 -c "import sys,json; d=json.load(sys.stdin); t=d.get('trace',{}); print('TV:', d.get('taxable_value'), 'dep:', t.get('deemed_depreciation'), 'int:', t.get('deemed_interest'), 'total:', t.get('deemed_total'))"
```

**Expected:** `TV: ~1885.94 dep: 5609.59 int: 1934.19 total: 7543.78`

---

### A6. Engine-direct probe (bypasses REST API)

```bash
curl -fsS -X POST https://fbt-engine-8340695160.australia-southeast1.run.app/calculate_fbt \
  -H "Content-Type: application/json" \
  -d '{
    "benefit_category": "car_operating_cost",
    "method": "operating_cost",
    "form_of_finance": "owned",
    "fuel_repairs_servicing": 3000,
    "registration_insurance": 1500,
    "business_use_percentage": 75,
    "employee_contribution": 200,
    "no_private_use_reduction": 0,
    "acquisition_cost": 50000,
    "acquisition_date": "2024-01-01"
  }' | python3 -c "import sys,json; d=json.load(sys.stdin); t=d.get('trace',{}); print('TV:', d.get('taxable_value'), 'dep:', t.get('deemed_depreciation'), 'int:', t.get('deemed_interest'), 'total:', t.get('deemed_total'), 'dispatch:', t.get('deemed_dispatch'))"
```

**Expected:** `TV: ~3880.96 dep: 8792.26 int: 3031.57 total: 11823.83 dispatch: computed_chained`

If A4 and A6 give different `deemed_*` numbers, **flag it** — the bridge
would be rewriting engine output, which would be a contract bug.

---

### A7. Schema accepts `acquisitionCost`

```bash
curl -sS -i -X POST "$API_URL/v1/calculators/$CALC_URI/$PERIOD_URI" \
  -H "Content-Type: application/json" \
  -d '{"businessUsePercentage":75,"formOfFinance":"owned","fuelRepairsServicing":100,"registrationInsurance":100,"employeeContribution":0,"acquisitionCost":1,"acquisitionDate":"2024-01-01"}' \
  2>&1 | head -3
```

**Expected:** `HTTP/2 200` (not 422). The body content doesn't matter for
this test; only the status code.

---

### A8. `/healthz` known-issue probe (informational only)

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://fbt-calculator-api-8340695160.australia-southeast1.run.app/healthz
```

**Expected:** **404** (known issue; see § Known Issues below). If you see
200, that's a positive surprise — note it.

---

## Section B — In-container forensics (requires `gcloud` auth + `docker`)

### B1. Identify the live engine + API image URIs

```bash
gcloud run services describe fbt-engine \
    --region=australia-southeast1 \
    --project=lodgeit-calc-constellation \
    --format='value(spec.template.spec.containers[0].image)'

gcloud run services describe fbt-calculator-api \
    --region=australia-southeast1 \
    --project=lodgeit-calc-constellation \
    --format='value(spec.template.spec.containers[0].image)'
```

**Expected:** two
`australia-southeast1-docker.pkg.dev/lodgeit-calc-constellation/clawdog/...:latest`
URIs. **Save these as `$ENGINE_IMG` and `$API_IMG`.**

---

### B2. Inspect the engine container's rate-table layout

```bash
docker pull "$ENGINE_IMG"
docker run --rm --entrypoint /bin/sh "$ENGINE_IMG" -c '
  ls /app/SBRM_RATE_TABLE/fbt/lodgeit_au_sbrm/fy2026/ | sort
  echo "---"
  wc -l /app/SBRM_RATE_TABLE/fbt/lodgeit_au_sbrm/fy2026/s8a-effective-from.md
  echo "---"
  # Fallback if `file` is not installed in the container:
  grep -lU $'\''\r'\'' /app/SBRM_RATE_TABLE/fbt/lodgeit_au_sbrm/fy2026/*.md \
    && echo "CRLF DETECTED — flag this" \
    || echo "No CRLF — clean LF-only"
'
```

**Expected:**

- 14 `.md` files including: `benchmark-interest.md`, `days-in-year.md`,
  `days-in-year-by-fy.md`, `deemed-depreciation-rates.md`, `fbt-rate.md`,
  `gross-up-type-1.md`, `gross-up-type-2.md`, `in-house-benefit-cap.md`,
  `reasonable-food-allowance.md`, `rfba-threshold.md`,
  `s8a-effective-from.md`, `s8a-lct-low-emission-threshold.md`,
  `s8a-phev-exclusion-effective-from.md`, `statutory-fraction.md`.
- Line-count for `s8a-effective-from.md` ≈ 104.
- `grep` fallback reports "No CRLF — clean LF-only". If you see "CRLF
  DETECTED", flag it (don't fix it).

> **B2 historical note:** the CRLF check is intentional. A specific
> Windows/WSL checkout with `core.autocrlf=true` caused a 6-PR debugging
> incident on 2026-05-24 mc02–mc06; B2 makes any regression of that
> failure class detectable in 5 seconds.

---

### B3. Inspect the API container's rate-table bundle

```bash
docker pull "$API_IMG"
docker run --rm --entrypoint /bin/sh "$API_IMG" -c '
  ls /app/SBRM_RATE_TABLE/fbt/lodgeit_au_sbrm/fy2026/ 2>&1 | head -20
'
```

**Expected:** same 14 `.md` files as B2.

---

### B4. Inspect the API container's `/healthz` route definition

```bash
docker run --rm --entrypoint /bin/sh "$API_IMG" -c '
  grep -n healthz /app/api/main.py
'
```

**Expected:** at least one line like
`56:@app.get("/healthz", tags=["system"], summary="Liveness probe.")`. If
returns nothing, the `/healthz` route is NOT in the deployed image — that
explains the 404 in A8.

> **B4 historical note:** in the 2026-05-24 verification, V2 confirmed
> the route DOES exist in the deployed image at line 56, yet A8 still
> returns 404. This means the 404 is NOT a stale-image issue. The most
> likely remaining cause is Cloud Run / Google Frontend layer
> intercepting `/healthz` before FastAPI sees it (some GFE configurations
> treat `/healthz` as a reserved probe path). Non-blocking: Cloud Run's
> internal startup probe IS hitting the route successfully (otherwise the
> revision wouldn't be Ready). Defer investigation unless external
> `/healthz` is required.

---

### B5. Inspect the API container's Python schema for `acquisition_cost`

```bash
docker run --rm --entrypoint /bin/sh "$API_IMG" -c '
  grep -n "acquisition_cost\|acquisitionCost" /app/api/schemas/invocation.py
'
```

**Expected:** at least one match showing
`acquisition_cost: float | None = Field(...)`. If absent, A7 should also
have failed.

---

### B6. Confirm the API's env-vars at the live revision

```bash
gcloud run services describe fbt-calculator-api \
    --region=australia-southeast1 \
    --project=lodgeit-calc-constellation \
    --format='value(spec.template.spec.containers[0].env)'
```

**Expected:** an env block including `LODGEIT_FBT_REPO=/app` AND
`FBT_PROLOG_URL=https://fbt-engine-8340695160.australia-southeast1.run.app`.
If `FBT_PROLOG_URL` is missing or points at `XXXX` placeholder, the API
can't reach the engine.

---

### B7. Confirm `/v1/rates/` serves data

```bash
curl -sS -i "https://fbt-calculator-api-8340695160.australia-southeast1.run.app/v1/rates/urn%3Asbrm%3Aperiod%3Afbt%3Afy2026" \
  2>&1 | head -15
```

**Expected:** `HTTP/2 200` with a JSON body listing the rate-tables.

---

## What to report back

Paste in this exact format:

```
| Test | Result | Notes (if mismatch) |
|---|---|---|
| A1 | PASS / FAIL |  |
| A2 | PASS / FAIL |  |
| A3 | PASS / FAIL |  |
| A4 | PASS / FAIL |  |
| A5 (Row 4) | PASS / FAIL |  |
| A5 (Row 5) | PASS / FAIL |  |
| A6 | PASS / FAIL |  |
| A7 | PASS / FAIL |  |
| A8 | EXPECTED-404 / SURPRISING-200 |  |
| B1 | <paste image URIs> |  |
| B2 | PASS / FAIL | <14 files? CRLF? line-count?> |
| B3 | PASS / FAIL |  |
| B4 | PASS / FAIL | <line number, or "no match"> |
| B5 | PASS / FAIL | <line numbers> |
| B6 | <paste env block> |  |
| B7 | PASS / FAIL |  |
```

---

## Known Issues

| ID | Symptom | Status | Notes |
|---|---|---|---|
| 1 | A8: `/healthz` returns 404 externally despite route being defined in container (B4 PASS) | OPEN, non-blocking | Cloud Run internal probes hit it successfully. Most likely cause: Google Frontend special-cases `/healthz`. External `/healthz` is informational only. |

## Provenance Caveat

The 2026-05-24 first execution of this kit was nominally run by an
"independent verifier" (V2). On post-hoc inspection of V2's response
content shape (formal section headers + `<think>` block referencing
"Adopt Streamace's strict, QA-oriented, analytical persona" + structured
numbered analysis + standard sign-off pattern), V2 was almost certainly
Streamace operating in a verifier role rather than a genuinely
independent second pair of eyes.

The mechanical results (curl output + grep results + docker inspect
output) are wire-grounded regardless of who ran them — the kit is
designed so that the test outputs are deterministic and cross-verifiable
against the external API.

But: **if you need a genuinely independent verification, ensure the
operator running the kit is NOT Streamace** (and ideally is someone who
hasn't been read into the deploy history). The kit is robust against
cause-attribution overreach (it doesn't ask the verifier to attribute
causes; only to compare outputs against expected values) but is not
robust against an executor who would skip steps or fabricate results.

## Provenance

- Designed by ClawDog 2026-05-24 mc09 in response to Andrew's direct-voice
  request: "Give me a series of tests I can get a second person to carry
  out, assume they don't know anything about what we've been through. They
  have equal access as Streamace."
- First field-validated 2026-05-24 23:47 UTC (V2/Streamace report); A1–A7
  all PASS, A8 EXPECTED-404, B1–B3 + B5–B7 all PASS, B4 surprising PASS
  (route present in image yet 404 external — see Known Issue 1).
- Banked at `docs/verification-kit.md` 2026-05-24 mc10 as the canonical
  per-deploy verification protocol for the constellation.
