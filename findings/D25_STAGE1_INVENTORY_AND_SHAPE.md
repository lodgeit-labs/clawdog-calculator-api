# D25 Stage 1 — gateway pass-through inventory + shape proposal (NO CODE)

**Authority:** Fable dispatch 2026-09-10 01:37 UTC. D25 greenlit, gateway-only, two stages. This is Stage 1 (inventory + shape; **no serialisation code until Fable rules A vs B**).

**Repo:** `lodgeit-labs/clawdog-calculator-api` (gateway). No engine change, no engine deploy.

**Evidence discipline (L#96):** this inventory is refreshed against the **source-side authoritative surfaces** — the FBT engine `FBT_Engine.pl` + `emit_wire.pl` at `lodgeit-labs/LodgeiT_FBT@997f6d5` (post-D12, PR #64+#65 merged) and the gateway route/schema at `lodgeit-labs/clawdog-calculator-api@8360d0b` (post-#42+#43). It is **not** a live deployed-wire probe: the deployed engine sits behind Cloud Run identity-token auth that this session does not hold (Andrew's lane per the D12 carryover). The two field-value anchors quoted (`gross_taxable_value "4000.00"`, `reductions "0.00"` on loan) are **Andrew's direct-engine curl from 2026-09-09**, cited by Fable in the dispatch. Stage 2 wire-proof re-confirms every value on the deployed wire (Andrew's token).

---

## 1 · The defect, precisely located

The FBT invoke route hand-builds a **fixed-shape** response dict and discards every engine top-level field outside its 4+6-key allowlist:

`api/routes/calculators.py:877-884` (current, `8360d0b`):

```python
response_payload = wrap_response(
    {
        "taxable_value": taxable_value,     # engine_response.get("taxable_value")
        "trace": trace,                     # engine_response.get("trace", {})
        "manifest": manifest,               # gateway-built
        **gross_up_passthrough,             # allowlist, built at :780-790
    },
    jurisdiction=meta["jurisdiction"],
)
return CalculatorInvocationResponse.model_validate(response_payload)
```

The allowlist (`api/routes/calculators.py:780-790`) admits exactly 6 keys:

```python
for key in ("fbt_type", "gross_up_factor", "grossed_up_taxable_value",
            "fbt_payable", "rfba_notional_taxable_value",
            "rfba_notional_grossed_up_t2"):
    if key in engine_response and engine_response[key] is not None:
        gross_up_passthrough[key] = engine_response[key]
```

**Every other top-level field the engine emits is dropped before the validator runs.** The drop is at **route construction**, not schema validation — the schema already permits extras (see §3).

## 2 · This is a parity gap, not a new pattern

The gateway's other three engine routes **already pass the full engine response through**:

| Route | File:line | Construction |
|---|---|---|
| Div7A-at | `api/routes/calculators.py:1066-1069` | `wrap_response({**engine_response, "manifest": manifest}, ...)` |
| depreciation-at | `api/routes/calculators.py:1200-1203` | `wrap_response({**engine_response, "manifest": manifest}, ...)` |
| depreciation-range | `api/routes/calculators.py:1347-1350` | `wrap_response({**engine_response, "manifest": manifest}, ...)` |
| **FBT invoke** | `api/routes/calculators.py:877-884` | **`{taxable_value, trace, manifest, **gross_up_passthrough}` ← the outlier** |

**D25 brings the FBT route to the same `{**engine_response, ...}` shape the other three already ship.** This is Andrew's ruling ("the workings are the product — pass everything through") expressed as: *make FBT match the constellation-standard route pattern that predates it.*

## 3 · How extras currently flow (Option-B mechanism, file:line)

`CalculatorInvocationResponse` at `api/schemas/invocation.py:1077` already declares:

```python
model_config = ConfigDict(extra="allow")   # api/schemas/invocation.py:1095
```

So unknown top-level keys already survive `model_validate` and serialise onto the wire **iff they are in the dict passed to it**. Today they are not, because the FBT route filters them out at :780-790 before validation. Option B therefore needs **only** the route-construction change (`**gross_up_passthrough` → `**engine_response`-derived), with the schema unchanged (`extra="allow"` already in place). Option A additionally enumerates each field as a typed, pattern-constrained model field.

## 4 · Dropped-field inventory (refreshed to post-D12 source)

Engine emission sites (`FBT_Engine.pl@997f6d5`, `grep -nE "DictBase = _\{|DictOut = _\{"` → 15 emissions). Post-D12, **every money field is string-serialised by `emit_wire.pl`** per its Fable-ratified classification table (MONEY → `^-?\d+\.\d{2}$`; RATE_OR_FACTOR → native-precision string; PERCENTAGE_ECHO → canonical string; NON_NUMERIC → unchanged). Class column below is taken directly from that ratified table.

| Predicate (engine line) | Dropped top-level field | Class | Engine emits (post-D12) |
|---|---|---|---|
| car-statutory-formula (1434) | `gross_taxable_value` | money | `str` `^-?\d+\.\d{2}$` |
| | `taxable_value_before_statutory` | money | `str` |
| | `employee_contribution` | money | `str` |
| | `reductions` | money | `str` |
| car-operating-cost (2094) | `operating_expenses_total` | money | `str` |
| | `business_use_reduction` | money | `str` |
| | `taxable_value_before_operating` | money | `str` |
| | `taxable_value_net_operating_pre_clamp` | money | `str` |
| | `deemed_total` | money | `str` |
| | `no_private_use_reduction` | money | `str` |
| | `employee_contribution` | money | `str` |
| | `business_use_percentage_clamped` | percentage_echo | `str` (canonical) |
| | `nil_cost_guard_triggered` | bool (non-numeric) | `bool` (excluded from money count) |
| loan (3578) | `gross_taxable_value` (= DifferenceBenchmarkInterest) | money | `str` — Andrew wire `"4000.00"` |
| | `employee_contribution` (= 0) | money | `str` |
| | `reductions` (= TotalOtherwiseDeductible) | money | `str` — Andrew wire `"0.00"` |
| debt-waiver (3743) | `gross_taxable_value`, `employee_contribution`, `reductions` | money | `str` |
| expense-payment std (4131) | `gross_taxable_value`, `employee_contribution`, `reductions` | money | `str` |
| expense-payment in-house (4256) | `gross_taxable_value`, `employee_contribution`, `reductions` | money | `str` |
| property std (4401) | `gross_taxable_value`, `employee_contribution`, `reductions` | money | `str` |
| property in-house (4470) | `gross_taxable_value`, `employee_contribution`, `reductions` | money | `str` |
| residual std (4546) | `gross_taxable_value`, `employee_contribution`, `reductions` | money | `str` |
| residual in-house (4605) | `gross_taxable_value`, `employee_contribution`, `reductions` | money | `str` |
| housing (4721) | `gross_taxable_value` (= GrossValue) | money | `str` |
| | `employee_contribution` | money | `str` |
| | `reductions` (= OdRule) | money | `str` |
| | `in_house_benefit` (= InHouseBenefit) | money | `str` |
| lafha (4882) | `gross_taxable_value`, `employee_contribution`, `reductions`, `in_house_benefit` | money | `str` |
| board (5009) | (needs sed inspection at Stage-2; classified with loan-shape trio pending) | money | `str` |
| statutory-formula legacy v1 (987) | `grossed_up_value`, `fbt_payable` (legacy naming; NOT exposed at calc-api per `api/schemas/invocation.py` Phase-3a docstring) | money | `str` — **out of D25 scope (unexposed route)** |

**Distinct dropped money fields:** `gross_taxable_value` (≈11 predicates), `employee_contribution` (≈13; often `"0.00"`), `reductions` (≈12; often `"0.00"`), `in_house_benefit` (2: housing + lafha), plus OC's 6 trace-adjacent money fields + SF's `taxable_value_before_statutory`. One percentage-echo (`business_use_percentage_clamped`). All in `emit_wire.pl`'s ratified table → all string post-D12. `rate_uris_consumed` is already consumed by the manifest builder (not a drop). `nil_cost_guard_triggered` is boolean, out of the money-field count.

## 5 · Shape proposal + Option A vs B recommendation

### Mechanism (both options share this route change)
Change `api/routes/calculators.py:877-884` from the fixed dict to the constellation-standard pass-through the other 3 routes already use:

```python
# additive: engine fields flow through; gateway-owned keys layered ON TOP so
# they always win (trace/manifest are gateway-authoritative, never engine-shadowed)
response_payload = wrap_response(
    {**engine_response, "taxable_value": taxable_value, "trace": trace, "manifest": manifest},
    jurisdiction=meta["jurisdiction"],
)
```

The D21 502 trio-consistency guard (`:820-875`) is untouched — it fires before construction and is orthogonal. The `gross_up_passthrough` allowlist loop (:780-790) becomes redundant and is deleted (its 6 keys now flow via `**engine_response`).

**Additive-only guarantee (Fable hard constraint):** `taxable_value`, `trace`, `manifest`, and the gross-up trio are written *after* `**engine_response`, so their gateway-computed values win any key collision → byte-identical to today. Only previously-dropped keys are net-new. `rate_uris_consumed` (engine-internal, consumed into manifest) should be popped so it does not leak — Stage-2 detail.

### Recommendation: **Option A (typed-per-field)** — with a B fallback

I recommend **Option A**: declare each dropped field on `CalculatorInvocationResponse` as `str | None` with the D12 A2 regex (`money = ^-?\d+\.\d{2}$`, percentage-echo canonical). Reasons:

1. **Same reasoning as A2 on this exact model.** A2 typed the gross-up 6 precisely so a regressed float shape fails validation at the gateway boundary. The dropped fields are the *same money class* from the *same engine*; leaving them `extra="allow"`-untyped means a future float regression on `gross_taxable_value` sails through silently — the exact hole A2 closed for the trio, re-opened for the workings.
2. **This is the consumer contract.** Daniyal's team (and later Coracle) read this schema as the wire contract. `extra="allow"` passes unknowns through **unvalidated and undocumented**; a typed field is both the validation gate and the published contract.
3. **Enumeration cost is bounded and already done.** The distinct set is ~9 money fields + 1 percentage-echo (§4), not 13×4. The union is small because the same trio (`gross_taxable_value`/`employee_contribution`/`reductions`) repeats across predicates.
4. **`extra="allow"` stays on** as defence-in-depth: any field I failed to enumerate still passes through (no data loss), it just isn't pattern-validated until enumerated — so Option A strictly dominates Option B on safety with no pass-through-completeness cost.

**Where Option B wins, if Fable prefers it:** lighter diff (route-only, zero schema change), and it cannot *under*-expose a field I missed in enumeration. The cost is no float-regression gate on the workings and no published contract for them. Given the workings are now a product surface (Andrew's ruling), an unvalidated product surface is the weaker end-state — hence A.

**Net:** Option A = route pass-through change **+** enumerate the ~10 distinct fields as typed `str|None` with A2 patterns, keeping `extra="allow"` as the catch-all. Awaiting Fable's ruling before writing serialisation/schema code.

## 6 · Stage 2 wire-proof plan (for after Fable rules)
- **Additive proof:** before/after gateway curl on a currently-exposed predicate (**car-operating-cost** or **lafha**) → `diff` shows only *added* keys; `taxable_value`/`trace`/`manifest`/trio byte-identical.
- **New-field proof:** gateway curl on **loan** → `gross_taxable_value == "4000.00"`, `reductions == "0.00"` (equal to Andrew's 2026-09-09 direct-engine values), present as strings.
- `jq '[paths(scalars)] | ...'` type walk asserting every money field is a JSON string, none numeric.

`mut-2026-09-10-mc00-d25-stage1-inventory`
