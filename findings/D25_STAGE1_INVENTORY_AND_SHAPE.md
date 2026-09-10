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

---

# Stage 1 Addendum — Fable due-diligence (2026-09-10 04:51 UTC)

Fable's lean moved to **Option B (full pass-through)** on the parity finding, keeping the six A2-typed money fields declared on the model so a regressed float still 502s. Two due-diligence answers before Fable rules B. Both are **source-side** (L#96: engine `FBT_Engine.pl` + `emit_wire.pl` @ `LodgeiT_FBT@997f6d5`; gateway @ `8360d0b`) — not a deployed-wire probe (Cloud Run identity-token auth is Andrew's lane).

## Q1 — Does full pass-through expose any field that shouldn't be public? **No. B is clean; no denylist needed.**

### Complete top-level key enumeration (every FBT engine emission, depth-1 only)

Method: walked all 15 `DictBase`/`DictOut` emission blocks tracking brace depth, recording only keys at depth==1 (trace-nested keys excluded), then added the 3 keys `apply_dispatch_gross_up_to_dict/3` merges in (`FBT_Engine.pl:1305`).

**Money (string post-D12, `emit_wire.pl` MONEY class):** `taxable_value`, `gross_taxable_value`, `taxable_value_before_statutory`, `taxable_value_before_operating`, `taxable_value_net_operating_pre_clamp`, `operating_expenses_total`, `business_use_reduction`, `deemed_total`, `no_private_use_reduction`, `employee_contribution`, `reductions`, `in_house_benefit`, `grossed_up_value` (legacy v1, unexposed route), `grossed_up_taxable_value`, `fbt_payable`, `rfba_notional_taxable_value`, `rfba_notional_grossed_up_t2`.

**Rate/factor (string):** `gross_up_factor`.

**Percentage-echo (string):** `business_use_percentage_clamped`. **Input-echo mirrors:** `form_of_finance` (atom), `register_percentage`, `clamp_mode`, `method`, `pre_clamp_reductions_applied`.

**Structural / consumer-facing:** `fbt_type` (Literal), `trace` (dict), `rate_uris_consumed` (list; consumed by manifest builder), `s8a_inputs`, `advisory`, `applied_rate_table_uris`.

**Booleans / provenance:** `nil_cost_guard_triggered`, `counts_towards_fbt_cap`, `verification_required`, `exempt_under`, `exemption_provenance`, `deemed_dispatch`.

### Internal/debug audit — clean
1. **`numeric_mode` / `events`** — the gateway's existing internal-field set (`api/lib/engine_error_mapper.py:105` `_INTERNAL_ENGINE_FIELDS`). **Neither string appears anywhere in `FBT_Engine.pl` or `emit_wire.pl`.** They are fields from *other* engines that the error-path scrubber guards against; the FBT engine never emits them. (That scrubber runs only on the **error** path, not success — but since the FBT success dict never contains them, full pass-through cannot leak them.)
2. **Success-path envelope is calculator-only.** `handle_calculate_fbt/1` (`FBT_Engine.pl:666-681`) wraps exactly `DictOut` via `emit_wire:emit_wire_dict/2` → `reply_json_dict/1`. No diagnostic/debug envelope is injected on success. (The `/health` handler at `:656` emits `swipl_version`/`port_env`/`rate_table_facts` — but that's a **different endpoint** the gateway never proxies as a calc response.)
3. **`s8a_inputs`** is an **echo of validated s.8A electric-vehicle exemption inputs** (`exempt_electric`, `first_held_date`, `first_retail_sale_value`, `vehicle_type`, `phev_grandfathered`; def at `FBT_Engine.pl:1524`). Audit-legitimate — the caller's own exemption inputs reflected back for provenance; not internal.
4. **`advisory`** is a **Fable-ratified consumer advisory** (mut-2026-09-06-mc12, Fable ruling 2026-09-06 02:18 UTC) on meal-entertainment basket decomposition — explicitly consumer-facing.

**Conclusion:** every top-level FBT key is a money/echo/structural field the consumer should see, a provenance boolean, or a ratified advisory. **No internal/debug/diagnostic key exists on the FBT success surface.** Option B exposes nothing that shouldn't be public → **clean, no denylist**.

## Q2 — Do the sibling routes type their money fields, or pass them untyped? **Asymmetry named + justified.**

At the **gateway** layer, sibling money fields are **typed on the engines' own schemas**, not re-declared on the gateway's `CalculatorInvocationResponse` (source: gateway schema comment `api/schemas/invocation.py:1100-1120`, cross-checked against the sibling routes):

| Engine | Where money is typed | Shape | Gateway forwarding |
|---|---|---|---|
| depreciation-engine | its own `DepreciationAtResponse`, `depreciation_core/api/schemas.py:719+` (`Annotated[Decimal, Field(...)]`) | `wdv_at: "30265.03"` | `response_model=DepreciationAtResponse` pins it |
| Div7A_Engine | its own `CalculateResponse`, `div7a_core/../api/main.py:69` (every money field `str`) | `statutory_myr: "15497.53"` | forwarded via `{**engine_response, "manifest"}`; **untyped as extras at the gateway model** |
| **FBT (this PR)** | the **gateway** model `CalculatorInvocationResponse` (6 A2-typed money fields, regex-constrained) | `fbt_payable: "4392.06"` | `{**engine_response, ...}` + 6 fields keep gateway typing |

**The asymmetry, plainly:** after D25, FBT is the **only** engine whose money fields are typed *at the gateway boundary* (the six A2 fields). depreciation-engine types its money on its **own** Pydantic model (`Decimal`-serialised); Div7A types its money on its **own** model (`str`); the gateway re-validates neither — it trusts the engine model and forwards.

**Why this is deliberate, not sloppy:**
- **FBT is the only engine that went through D12's float scare.** D21 (2026-09-06) surfaced a 200-with-inconsistent-trio on the LAFHA path; D12 (2026-09-08) flipped FBT money from float to string engine-side *and* added the six gateway-boundary regex guards (A2) so a regression back to float 502s at the gateway, not silently at the consumer. That guard exists because FBT *earned* it empirically.
- **The siblings emit strings natively and never had the scare.** depreciation-engine has always serialised money as `Decimal`→string via its Pydantic model; Div7A declares `str` directly. Neither passed through a float-emission regression, so neither needed a gateway-boundary regex tourniquet. Their engine-model typing is the guard.
- **D25 keeps FBT's six A2 fields typed on the gateway model** (Fable's B-with-typed-six) precisely to preserve that hard-won gate, while the ~10 newly-exposed FBT workings ride as `extra="allow"` extras — the same untyped-passthrough posture the siblings already have for their non-headline fields. So B does **not** widen the asymmetry: it holds FBT's existing guard and matches the siblings' passthrough posture for the rest.

**Net:** the asymmetry is real, one-directional (FBT typed-at-gateway, siblings typed-at-engine), and justified by FBT's unique D12/D21 history. Named here so a future reader sees the six-typed-fields-on-FBT-only is intentional.

## A/B recommendation (updated)
Stage-1 recommended **A**; Fable's parity finding correctly moves the lean to **B**. I concur with **B**: uniformity across the four routes (`{**engine_response, "manifest"}`) *is* the contract, the six A2-typed money fields stay declared (float-regression gate preserved), and Q1 confirms nothing internal leaks. B with the six retained-typed fields is the clean end-state. **No serialisation code lands until Fable formally rules.**

`mut-2026-09-10-mc00-d25-stage1-ddq-addendum`
