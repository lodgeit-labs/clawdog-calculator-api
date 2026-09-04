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

## 4. D17 — unhandled 500 on invalid `formOfFinance`

Fable's cell 25 wire result: `formOfFinance: "sf_16"` returned an unhandled 500 with a non-JSON body, bypassing the mapper.

**Cause (hypothesised from FBT_Engine.pl reading; wire-verification pending):** the Prolog fold at `FBT_Engine.pl:1873` calls `member(FormOfFinance, [owned, hire_purchase])` in a decision chain. When `FormOfFinance = "sf_16"`, none of the arms match, and the fold falls through into a branch that either raises a Prolog exception or produces a non-dict response body. Because the exception isn't caught by the FastAPI wrapper's `reply_json_dict/1` layer, it surfaces as an HTTP 500 with a text/plain body — bypassing the mapper.

**Gateway-side fix:** narrow `form_of_finance` from `str` to `Literal["owned", "hire_purchase", "leased", "unspecified"]` at the pydantic layer. Same discipline as D8c narrowing on `GatewayBasisLiteral`. Would refuse `"sf_16"` at 422 before the engine is called.

**Engine-side fix:** the fold should refuse an unknown `form_of_finance` value with a typed refusal (`refusal_class: "unknown_form_of_finance"`) so the mapper's 400 branch fires and the caller sees a structured JSON response. Same defence-in-depth shape as D14.

Both fixes are appropriate; either alone closes the mapper-bypass. Both together close the "unknown-value passes gateway + reaches engine + engine dies weirdly" class of defect. Ship both.

**OT queued:** D17 — narrow `form_of_finance` Literal at gateway + refuse unknown form_of_finance at engine.

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
