# mc01-2026-09-04 investigation — FBT alias sweep + s10 statutory read + D13 promotion

**Triggered by:** Fable ruling mc01-2026-09-04 09:00 UTC after the control-fired probe on cell 21 revealed a wire-evident trace contradiction that outranked D17.

**Status:** investigation report only. No code changes shipped on the branch beyond PR #34's existing contents. Fable-authorised fixes queued to separate PRs after engine-side work in fresh-substrate sessions (D7-discipline sibling).

---

## Fable's ruling (verbatim, mc01-2026-09-04 09:00 UTC)

> "Control fired: `formOfFinance: "owned"` returns 200 with correct arithmetic. D17 is confined to the invalid value — the calculator is not broken outright. It is still an unhandled 500 with a non-JSON body and it still bypasses the mapper.
>
> But the control's trace contains a defect that outranks D17, and it is a silent wrong number on a headline calculator.
>
> `"acquisitionDate": "2024-04-01"` ← supplied in the request
> `"openingDepreciatedValue": 55000` ← supplied in the request
>
> `trace: "deemed_dispatch": "skipped_no_acquisition"` ← contradicts the input
> `"deemed_depreciation": null`
> `"deemed_interest": null`
> `"deemed_total": 0`
> `"total_after_npur": 4500.0` ← fuel 3000 + reg/ins 1500 only
>
> The engine says it skipped deemed amounts because there was no acquisition, and an acquisition date was supplied. That contradiction is wire-evident and requires no statutory reading to see."

**Revised priority Fable ordered:**

1. Alias sweep — every FBT field, gateway alias against the key the engine reads.
2. Deemed depreciation / deemed interest on COC — statutory read first, then whether the omission is the alias bug or a separate gap.
3. D13 nullability — promoted from OT; LAFHA either grosses up or declares that it cannot.
4. D17 — the unhandled 500.
5. PR #34's existing contents.

---

## 1. Alias sweep — result: no gateway↔engine key drift found

**Method:**

- Extracted every pydantic input-field name from `api/schemas/invocation.py` (only classes ending `Input`, only `AnnAssign` targets).
- Extracted every engine key read pattern from `lodgeit-labs/LodgeiT_FBT/FBT_Engine.pl`:
  - `get_dict(atom, DictIn, ...)`
  - `optional_number(DictIn, atom, ...)`
  - `optional_integer_or_number(DictIn, atom, ...)`
  - `optional_atom_or_string(DictIn, atom, ...)`
  - `DictIn.atom` dot-lookup pattern
- Compared the two sets.

**Result:** the two sets align. Every pydantic input-field name has a matching engine read key.

- **56 pydantic aliases** (camelCase, caller-facing) → resolve to **~54 python field names** (snake_case).
- **67 engine keys** across all engine read patterns.
- **Zero pydantic input fields declared by the gateway but not read by the engine.**

The sweep does not include response-model fields (those are engine-emit, gateway-declare — the flow direction is reversed). Nor does it include the D13 aggregate-level defect on `gross_up_factor` / `grossed_up_taxable_value` / `fbt_payable` / `rfba_*` — those are response-side fields and the D13 defect is about semantics (null vs zero vs absent), not about names.

**Wire-verification of the alias-mapping path** (payload direction, hermetic probe against TestClient):

```
POST /v1/calculators/{urn:...:car-operating-cost}/{urn:...:fy2026}
{
  "businessUsePercentage": 75,
  "formOfFinance": "owned",
  "employeeContribution": 200,
  "fuelRepairsServicing": 3000,
  "registrationInsurance": 1500,
  "noPrivateUseReduction": 0,
  "acquisitionDate": "2024-04-01",
  "openingDepreciatedValue": 55000
}
```

Captured engine-side payload:
```
{'acquisition_date', 'benefit_category', 'business_use_percentage',
 'employee_contribution', 'form_of_finance', 'fuel_repairs_servicing',
 'method', 'no_private_use_reduction', 'opening_depreciated_value',
 'registration_insurance'}
```

All snake_case, all fields expected. **No silent-drop, no key rename, no missing field on the engine-side.**

### Why Fable's earlier probe reported `skipped_no_acquisition`

Fable's cell 21 payload was missing `daysHeldInFBTYear`. The engine's `fbt_oc_deemed_dispatch/8` at `FBT_Engine.pl:1899-1908` requires ALL THREE of `opening_depreciated_value`, `days_held_in_fbt_year`, and `acquisition_date` to enter the compute-deemed-amounts branch. Missing any one → falls to `skipped_no_acquisition`.

**The trace label is misleading, not wrong.** `deemed_dispatch: "skipped_no_acquisition"` should read `"skipped_missing_days_held"` when the trigger was `daysHeldInFBTYear` being absent (rather than `acquisitionDate`). But the label defect does not by itself explain the silent wrong number — that is a separate substantive defect (see §2).

**Alias-sweep verdict:** the "silent-default class Fable named 4 prior instances of" is NOT present as a NAME-DRIFT class on the current substrate. What IS present is a **missing-required-input silent-fallback** class: the engine has fields it consumes only when all-of-triad is present, and silently defaults when the triad is broken. That is a different class of defect from the schema-drift class Fable predicted, and it needs to be named separately.

---

## 2. Deemed depreciation + deemed interest on operating cost method — statutory read

**Read discipline:** Fable ruled *"I am flagging this as a strong hypothesis requiring verification, not a ruling, because I have not read the section: under the operating cost method, an owned car's operating costs include deemed depreciation and deemed interest. If that is right, this response has omitted both, and taxable_value: 925.00 is understated by a material amount on a $55,000 car."*

Statutory reading performed 2026-09-04 09:03 UTC via two independent secondary sources on FBTAA 1986 s10 and s11.

### Confirmed reading

Under **FBTAA s10 operating cost method** (the alternative to the s9 statutory formula method), taxable value is:

$$\text{Taxable Value} = [C \times (100\% - BP)] - R$$

where:
- $C$ = total operating cost of the car during the holding period
- $BP$ = business use percentage (from logbook)
- $R$ = recipient / employee contributions

For an **owned** car (or hire-purchase held car), s10 requires that $C$ include:

1. **Actual running costs** — fuel, repairs, servicing, registration, insurance.
2. **Deemed depreciation** under s11 —
   $\text{Depreciated Value} \times \text{Deemed Depreciation Rate} \times \frac{\text{Days Held}}{365}$
   - Rate for cars acquired on/after 10 May 2006: **25% diminishing value**.
3. **Deemed interest** under s11 —
   $\text{Depreciated Value} \times \text{Statutory Benchmark Rate} \times \frac{\text{Days Held}}{365}$
   - Benchmark for FBT year 2026: **8.77%** (secondary source).
   - Applied regardless of whether the car was cash-purchased or financed.

### Application to Fable's cell 21 control payload

Payload: `openingDepreciatedValue: 55000`, `formOfFinance: "owned"`, `acquisitionDate: "2024-04-01"`, `daysHeldInFBTYear: (missing)`.

If we assume `days_held_in_fbt_year = 365` (full FBT-year holding, which the caller almost certainly intended for a car acquired 2024-04-01 held through FY2026):

- Deemed depreciation = $55,000 × 25% × 365/365 = **$13,750**
- Deemed interest = $55,000 × 8.77% × 365/365 = **$4,823.50**
- Operating cost $C$ = 3,000 (fuel) + 1,500 (reg/ins) + 13,750 + 4,823.50 = **$23,073.50**
- Taxable value = $23,073.50 × (100% − 75%) − 200 = **$5,568.38**

**The wire response returned $925.00.** Understated by ~$4,643 on this assumed-full-year-holding shape.

### Root cause (as far as this investigation goes)

The engine's `fbt_oc_deemed_dispatch/8` at `FBT_Engine.pl:1899-1908` currently:

- Requires `days_held_in_fbt_year` to be explicitly supplied when all-of-triad guards the deemed-amounts branch.
- Falls silently to `skipped_no_acquisition` when it isn't.
- Sums operating cost from actual-running-costs fields only, with `deemed_total = 0`.
- Returns 200 with a taxable_value that is mathematically consistent under s10 IF deemed_total were legitimately zero — which it is NOT for an owned car.

**Verdict:** this is NOT the alias schema-drift class. It is a separate defect: the engine's operating-cost aggregator does not enforce the s10-mandated inclusion of deemed depreciation + deemed interest when the fold is owned/hire-purchase. Three ways to close, and they are for the engine-PR to rule between:

1. **Default `days_held_in_fbt_year` to the full FBT-year length** when `acquisition_date` + `opening_depreciated_value` are present. Business-rule inference; matches the common case; retains backward compatibility with callers who never sent the field.
2. **Refuse the payload** with a clear "days_held_in_fbt_year required for deemed-amounts computation" error when the fold is owned/hire_purchase and `days_held_in_fbt_year` is absent. Fail-loud discipline; forces the caller to supply the field.
3. **Compute using the `chained_dv_walk` path** when `acquisition_cost` is available, and require `chained_dv_walk` mode for owned COC. Complex; requires the caller to declare which path they want.

Option 2 is the strongest defence against silent wrong numbers. Option 1 accepts the risk that a partial-year holding is silently mis-computed.

**Gateway-side defence-in-depth** (independent of the engine PR): require `daysHeldInFBTYear` on the pydantic layer when `formOfFinance in ("owned", "hire_purchase")` and BOTH `acquisitionDate` and `openingDepreciatedValue` are supplied. Same mechanism as D8a defence-in-depth on the depreciation basis-conditional rules. Documented here; not shipped in PR #34.

**OT queued:** D18 — FBTAA s10 deemed-amounts silent-omission when `days_held_in_fbt_year` is absent on owned/hire-purchase COC. Requires engine PR + gateway defence-in-depth PR.

---

## 3. D13 promoted from OT to first-tier defect

**Fable ruling verbatim:**

> "LAFHA returned `gross_up_factor`, `grossed_up_taxable_value` and `fbt_payable` all null; car-operating-cost returns 1.8868, 1745.29, 820.29. Two benefit types on one API, one grosses up and one does not. An integrator summing `fbt_payable` across benefit types silently gets nothing from LAFHA and a correct figure from COC — a wrong total with no error anywhere. D13 is not a documentation gap; it is an aggregate-level silent wrong number. Promote it."

### Wire-observed shapes

- COC 200 body: `gross_up_factor: 1.8868, grossed_up_taxable_value: 1745.29, fbt_payable: 820.29`.
- LAFHA 200 body: `gross_up_factor: null, grossed_up_taxable_value: null, fbt_payable: null`.

Any integrator writing `sum(fbt_payable for _ in benefits)` gets a plausible number that is undercounted by whatever the LAFHA benefit's gross-up-value would have been if computed.

### Correct behaviour

Two options for LAFHA:

1. **Gross up at the engine.** LAFHA is Type 2 (per ATO TR 96/9) so `gross_up_factor = 1.8868`. Compute `grossed_up_taxable_value` and `fbt_payable` from the LAFHA taxable value the way COC does. Emit non-null values. Same fields, same semantics across benefit types.
2. **Explicitly declare the omission** by returning an error / a typed sentinel that says "LAFHA does not participate in cross-benefit gross-up aggregation," and require the integrator to handle it. This is unusual and generally worse than option 1.

Fable's ruling supports option 1: *"LAFHA either grosses up or declares that it cannot."* Silent nulls are not "declaring it cannot" — they are the wrong-number-with-no-error shape the D8a/D8b/D11 discipline exists to eliminate.

**Wire scope note:** the engine at `FBT_Engine.pl:3719-3765` (LAFHA's `calculate_fbt_lafha/2`) returns a `DictOut` with `taxable_value`, `gross_taxable_value`, and `reductions` — it does NOT emit `gross_up_factor` / `grossed_up_taxable_value` / `fbt_payable`. The nulls arrive at the gateway response because the gateway's response schema declares those fields as `float | None` with `None` default, and pydantic's `model_dump` emits them as `null` when the engine omitted them.

This is the D13 promotion: the OMISSION is the defect, and it lives at the engine layer (LAFHA fold does not gross up). Gateway-side fix: nothing on this PR; a schema change that omits the fields entirely on LAFHA responses would be a shape change the engine PR would ratify.

**OT promoted:** D13 — LAFHA (and every other non-grossing FBT calculator) must either gross up + emit non-null `fbt_payable` OR the response envelope must OMIT those fields entirely rather than nulling them. Engine PR authoring in a fresh session.

---

## 4. D17 — unhandled 500 on invalid `formOfFinance` (SHIPPED gateway half + ROOT CAUSE CORRECTED)

Fable's cell 25 wire result: `formOfFinance: "sf_16"` returned an unhandled 500 with a non-JSON body, bypassing the mapper.

**Root cause (WIRE-VERIFIED HERMETICALLY 2026-09-04 09:15 UTC; my earlier speculation was wrong):**

The defect was NOT engine-side. Reproduced against `TestClient(app)`:

1. Payload with `formOfFinance: "sf_16"` reached the pydantic layer.
2. The pre-D17 `@field_validator("form_of_finance")` at `api/schemas/invocation.py` raised `ValueError` on unknown values.
3. FastAPI caught the `ValidationError` (which wraps the ValueError) in the generic route at `api/routes/calculators.py:645`.
4. `exc.errors()` returned the error list — which INCLUDED the raw `ValueError` object under `ctx.error` per pydantic v2's default output.
5. FastAPI's `JSONResponse` failed to serialise the `ValueError` object, raising `TypeError: Object of type ValueError is not JSON serializable`.
6. That TypeError bubbled to FastAPI's exception handler which produced an HTTP 500 with a text/plain body — bypassing the D8a mapper.

My earlier hypothesis — that the engine's `member(FormOfFinance, [owned, hire_purchase])` raised uncaught — was wrong. Bare `member/2` fails silently in Prolog; it does not raise. The engine fold has a fall-through branch at `FBT_Engine.pl:1944` that would have returned 200 with `skipped_no_acquisition` for a `"sf_16"` value if the payload had ever reached it. Wire evidence: the engine's typed refusal (`throw(error(invalid_form_of_finance(...), ...))`) fires INSIDE the deemed-amounts compute path only, not from the top-level decision chain.

**Fix shipped (gateway half; wire-verified):**

1. `api/schemas/invocation.py`: narrow `form_of_finance` from `str` to `Literal["owned", "hire_purchase", "leased", "unspecified"]` at the pydantic layer. Removes the `@field_validator` (redundant + was the exception-raising site). The pre-D17 field_validator also silently accepted an orphaned `"other"` value not declared in the description — also removed.

2. `api/routes/calculators.py`: the generic route now calls `exc.errors(include_context=False, include_input=False, include_url=False)` instead of `exc.errors()`. This strips the non-JSON-serialisable `ValueError` object from the response body before it hits `JSONResponse`. This fix is separately load-bearing for ANY model_validator that raises ValueError — including D18's conjunction-guard shipped in the same commit.

**Wire-verified hermetically post-fix:**

```
POST .../urn:...:car-operating-cost/urn:...:fy2026
Content-Type: application/json
{ "formOfFinance": "sf_16", ... }

HTTP 422
Content-Type: application/json
{"detail":[{"type":"literal_error", "loc":["formOfFinance"],
            "msg":"Input should be 'owned', 'hire_purchase', 'leased' or 'unspecified'"}]}
```

**Engine-side fix (queued as OT):** the fold should refuse an unknown `form_of_finance` value with a typed refusal (`refusal_class: "unknown_form_of_finance"`). This closes the defence-in-truth requirement for callers who bypass the gateway (e.g. direct engine tests). Not shipped this arc; requires fresh-substrate FBT engine PR.

**Anchor banked:** the ValidationError-serialisation defect is a class of its own. Any pydantic `model_validator(mode="after")` or `field_validator` that raises `ValueError` produces a non-JSON-serialisable error object under pydantic v2's default `errors()` output. Every FastAPI route that catches `ValidationError` and passes `exc.errors()` to `HTTPException(detail=...)` MUST use `include_context=False` (or an equivalent scrubber) or it will surface as a 500 text/plain body on the wire. Discipline banked in the route's comment; applies to any future FastAPI-catching-ValidationError site.

## 4a. D18 gateway half — conjunction-guard on FBT COC (SHIPPED)

Sibling to D17 gateway half. Same class of defect (fail-open-on-unsatisfied-conjunction-guard). Shipped in the same commit because both use the same pydantic-validation-error surface.

**What ships:**

`api/schemas/invocation.py::FBTCarOperatingCostInput._validate_deemed_amounts_input_triad` — a `@model_validator(mode="after")` that fires when `form_of_finance ∈ {owned, hire_purchase}` and requires ONE of three paths (mirroring the engine's `fbt_oc_deemed_dispatch/8` dispatch at `FBT_Engine.pl:1873-1946`):

- **(a) single-year-primitive triad**: `openingDepreciatedValue + daysHeldInFBTYear + acquisitionDate`
- **(b) chained-DV walk triad**: `acquisitionCost + acquisitionDate` (+ optional `daysHeldInFBTYear`)
- **(c) explicit override**: `deemedTotal`

If none satisfied → `ValueError` → pydantic ValidationError → gateway 422 with the missing keys enumerated per path. Fable's diagnostic-label discipline mc01 09:11 UTC: *"A diagnostic label names the condition that was actually unsatisfied, or it names none of them."* The refusal message lists what's missing for EACH attempted path so the caller sees the full set of legitimate payloads.

**IMPORTANT SCOPE**: this changes WHICH PAYLOADS reach the fold, NOT what the fold computes. The D18 arithmetic itself remains BLOCKED pending Waqas oracle concordance per Fable 09:11 UTC ruling. Whether the engine's operating cost `C` should include deemed depreciation + deemed interest is NOT decided by this validator; the validator only ensures a payload without the required inputs cannot reach the fold's silent-default branch.

**Engine-side sibling half** (queued as OT for fresh-substrate FBT engine PR):
- Typed refusal instead of falling through: `refusal_class: "skipped_incomplete_deemed_inputs"` with `missing_keys: ["days_held_in_fbt_year"]` enumeration.
- Truthful trace label per Fable's diagnostic-label discipline; supersedes the current misleading `skipped_no_acquisition`.
- SAME COMMIT: label fix + typed refusal.

**8 wire-response-level tests** at `tests/test_d18_gateway_half_conjunction_guard.py` covering cell 21 replay + all three legitimate paths + leased/unspecified no-op + mapper-envelope-absent assertion (mc00 08:28 UTC design covenant).

---

## 4b. Corrections + Fable rulings 09:11 UTC

**Fable rulings mc01-2026-09-04 09:11 UTC (verbatim):**

On D18 arithmetic: *"You used 8.77% for deemed interest and labelled it 'FY2026 benchmark'. 0.0877 is the rate the Div7A engine returns for FY2025, from urn:sbrm:rate:div7a:fy2025:benchmark-interest. The FBT statutory interest rate is a separate published rate for the FBT year. They may coincide; you may have used a Div7A rate in an FBT computation."*

**Verified: I did.** Wire-verified against
`LodgeiT_FBT/SBRM_RATE_TABLE/fbt/lodgeit_au_sbrm/fy2026/benchmark-interest.md`:
the FBT FY2026 benchmark interest rate is **0.0862** (8.62%), NOT 0.0877.
The rate-table's own statutory-source clause reads *"FBTAA s.18; ATO
Taxation Determination TD 2025/X (FBT benchmark rate for FBT year
ending 31 March 2026)"* and the ATO-toolkit-locator says *"Loan fringe
benefits — calculating taxable value; sheet header column literally
reads 'FBT Benchmark interest (refer to 2026 FBT year @ 8.62%)'"*.

Two separable errors in my earlier arithmetic:

1. **Wrong-year, wrong-calculator rate.** Used 0.0877 (Div7A FY2025)
   in an FBT FY2026 computation.
2. **Rate-scope unverified.** Even 0.0862 is scoped by the rate-table
   name to *"Loan Fringe Benefits"* (FBTAA s.18). Whether the SAME
   rate applies to car-OC deemed-interest (FBTAA s.10 + s.11) is not
   confirmed by primary source; my earlier arithmetic report treated
   them as identical without checking.

Applying the FBT-declared 0.0862 (still assuming the rate-scope is
correct, which is now flagged as unverified):

- Deemed interest = $55,000 × 8.62% × 365/365 = $4,741
- Deemed depreciation unchanged at $13,750
- Operating cost C = 3,000 + 1,500 + 13,750 + 4,741 = $23,001
- Taxable value = $23,001 × 25% − $200 = **$5,550.13**

Direction of the correction stands (~$4,625 understated). Numeric
detail is corrected. The direction Fable named — mediated substrate —
is exactly why this arithmetic still cannot close D18.

**Fable's manifest wire-observation** (verbatim ratified):
> *"Corroborating evidence that you have: the COC response's manifest
> cites gross-up-type-2 and fbt-rate — and no interest rate table at
> all. If deemed interest were computed, a third rate table would be
> consumed and cited. Its absence from the manifest is independent
> confirmation that deemed amounts are not being calculated, and it
> tells you the rate table may not exist yet."*

The FBT engine's manifest emission for COC responses does NOT cite
`urn:sbrm:rate:fbt:fy2026:benchmark-interest` (the rate table exists
as a file but is not consumed by the OC deemed-amounts fold). This is
the wire-verifiable proof that deemed amounts are not fired: the
table is not consumed, the URI is not cited, and the caller can see
this at the manifest layer independently of the arithmetic itself.

**Standing rule ratified from tri-surface work (Fable 09:11 UTC):**

> *"You have two secondary sources and no primary, on a headline
> calculator, for a $4,643 correction. That is the mediated-substrate
> shape — and we have an oracle built for exactly this case. Send the
> cell-21 control payload to Waqas. His C# replica and the NTAA sheet
> are two independent implementations; if they return 5,568.38 the
> read is confirmed by concordance rather than by citation, which is
> stronger than a primary reading by one party. If they disagree, we
> learn something more interesting than the statute."*

**D18 IS BLOCKED pending Waqas oracle concordance.** Do NOT touch the
arithmetic on the engine before the C# replica and NTAA sheet return
their independent figures for the cell-21 control payload. Standing
rule from the tri-surface ruling: where they disagree, the burden
sits with our engine; where they agree, our engine changes to match.

**Diagnostic-label discipline (Fable-minted 09:11 UTC, standing rule):**

> *"A diagnostic label names the condition that was actually
> unsatisfied, or it names none of them. `skipped_incomplete_deemed_
> inputs`, with the missing keys enumerated, would have taken ten
> seconds instead of an hour."*

Applies to trace labels generally; `skipped_no_acquisition` is the
first instance we've caught. Engine PR authoring the fix ships the
truthful label + missing-key enumeration in the same commit as the
conjunction-guard remedy.

**Schema-drift attribution withdrawn (Fable 09:11 UTC):**

> *"I called it 'the fourth instance of schema drift' and swept 56
> aliases on that premise. Zero drift. The class is real but the
> mechanism is different: fail-open on an unsatisfied conjunction
> guard. Same wire signature, different cause, different remedy.
> Pattern-matching a symptom to a known class is how you get a clean
> sweep that proves nothing — I did that, and the sweep is worth
> keeping precisely because it now rules the class out."*

Banked in this doc's audit trail; the class Fable was tracking is
now named **fail-open-on-unsatisfied-conjunction-guard**, distinct
from schema-drift.

**D13 rate-table-fed ruling (Fable 09:11 UTC verbatim):**

> *"On D13's fix — read the gross-up factor from the rate table, do
> not hardcode 1.8868. urn:sbrm:rate:fbt:fy2026:gross-up-type-2
> already exists and COC already consumes it. A hardcoded 1.8868 in
> LAFHA is a rate literal in source, which your own mechanical gate
> forbids, and it would drift the day the factor changes."*

When LAFHA engine PR is authored: `calculate_fbt_lafha/2` calls
`rate_lookup(Period, 'gross-up-type-2', GrossUpFactor)` — same
pattern COC already uses. NO hardcoded 1.8868.

**Sequencing ruled** (Fable 09:11 UTC verbatim):

1. Div7A engine refusal on `amalgamated_base ≤ 0` — smallest, and it
   is the only thing between Div7A and shareable.
2. D17 gateway half now — `form_of_finance` narrowed to the Literal
   its own description already declares. Engine typed refusal follows
   in the FBT engine PR.
3. The conjunction-guard remedy — gateway conditional requirement plus
   engine typed refusal, with the trace label fixed in the same commit.
4. D13 LAFHA gross-up, rate-table-fed.
5. D18 — blocked pending Waqas. Do not touch the arithmetic.

**PR #34 batching decision:** items 2 and 3-gateway-half batched onto
PR #34 before ready-flip. Everything else lands on separate PRs (engine
repos + fresh sessions per Option-C discipline).

---

## 5. Sharing gate — per-calculator readiness state

Fable ruled: *"FBT does not go to testers. Depreciation's gate is met and stands; Div7A needs D14 deployed; FBT now has an unswept silent-default class and a possible understated headline figure. Say so plainly in the verification kit rather than letting the three calculators be treated as one readiness state."*

The verification-kit at `docs/verification-kit.md` § Known Issues currently carries only D7 known-limitation on depreciation `/range/`. It needs three additional entries per Fable's per-calculator readiness ruling:

| Calc | Sharing state | Blockers |
|---|---|---|
| Depreciation | ✅ shareable | D7 known-limitation banked; D8a + D10 gate met |
| Div7A | ⏳ conditional on deploy | D14 gt=0 pydantic constraint in PR #34 must reach production; engine-side amalgamated_base refusal PR queued |
| FBT | ❌ NOT shareable | D18 (s10 deemed-amounts silent omission — HEADLINE understated) + D13 (LAFHA cross-benefit aggregation silent-wrong-total) both live on the wire; D17 (unhandled 500 on invalid form_of_finance) tolerable but ugly |

Verification-kit update queued for next PR alongside the D13/D18 engine work.

---

## PR #34 status

Contents unchanged. Ready-flip held per Fable ruling. Fixes for D13 + D17 + D18 authorised as separate PRs — engine-side authoring in fresh sessions per the D7 Option-C discipline sibling. Gateway-side defence-in-depth constraints on `form_of_finance` Literal + `daysHeldInFBTYear`-required-when-owned may be batched into a follow-up gateway PR when the engine PRs land.
