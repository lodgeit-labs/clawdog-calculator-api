#!/usr/bin/env python3
"""scripts/smoke_fbt_computed.py — FBT computed-value post-deploy smoke.

The "computed-value smoke" queued since the emit_wire 502 arc: smoke_prod.sh
asserts discovery + error-shape + one byte-exact FBT row, but never asserts
that EVERY FBT calculator returns a well-formed grossed-up trio as decimal
strings with no bare float anywhere in the body. This script does.

Origin: 2026-09-10 Stage-2a FBT-available sweep. That sweep caught
meal-entertainment-register-12wk leaking a top-level ``register_percentage``
as a bare JSON float (fixed in LodgeiT_FBT via the emit_wire percentage_echo
classification). This is that sweep, committed as a runnable gate so the leak
class cannot silently return.

What it does
------------
1. GET {base}/v1/calculators, enumerate every ``urn:sbrm:calculator:fbt:*``.
2. POST a minimal valid body to
   POST {base}/v1/calculators/{calc_uri}/urn:sbrm:period:fbt:fy2026
   for each.
3. Assert per calculator:
     - HTTP 200
     - gross_up_factor, grossed_up_taxable_value, fbt_payable present,
       non-null, and quoted decimal strings
     - a raw-text regex finds NO bare JSON float anywhere in the body
       (belt-and-braces alongside the parsed-tree float walk)
4. Call LAFHA twice and assert both (D21 first-call null-trio guard).
5. Print the sweep table.

Exit-code contract (Standing Rule #8 tri-state):
    0  GREEN         — every calculator passes
    1  LOGIC DRIFT   — one or more calculators fail (a trio gap or a bare float)
    2  INFRA BROKEN  — discovery unreachable / non-JSON / no FBT calculators

Usage:
    scripts/smoke_fbt_computed.py [BASE_URL]
    API_BASE_URL=https://... scripts/smoke_fbt_computed.py

No auth (the gateway is public). No third-party deps (stdlib only), matching
the repo's no-runtime-deps posture.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

# Default matches scripts/smoke_prod.sh so the deploy.yml post-deploy step
# fires both gates against the same freshly-deployed revision. Override via
# the API_BASE_URL env var or a CLI arg (the public gateway alias
# https://fbt-calculator-api-qkp3j5bjnq-ts.a.run.app resolves to the same
# service and is handy for ad-hoc runs).
DEFAULT_BASE = "https://fbt-calculator-api-8340695160.australia-southeast1.run.app"
PERIOD = "urn:sbrm:period:fbt:fy2026"
TRIO = ("gross_up_factor", "grossed_up_taxable_value", "fbt_payable")

# Minimal valid request bodies keyed by URN leaf. Required-field sets are
# taken from the deployed OpenAPI schemas; values are the smallest that
# produce a non-refusing 200 (loan needs originalLoanAmount so the engine can
# derive a benchmark amount rather than 400). New FBT calculators added to the
# registry without an entry here fail loudly as "no smoke body" — that is the
# intended floor-raise signal (mirror smoke_prod.sh check-6 discipline).
BODIES = {
    "board": {"membersOverTwelve": 2, "over12MealsPerChild": 20},
    "car-operating-cost": {
        "businessUsePercentage": 75, "formOfFinance": "owned",
        "acquisitionCost": 40000, "acquisitionDate": "2023-07-01",
        "daysHeldInFBTYear": 366, "fuelRepairsServicing": 3000,
        "registrationInsurance": 1500, "employeeContribution": 200,
    },
    "car-parking-actual": {"spacesProvided": 5, "valuationMethodRate": 20},
    "car-parking-register-12wk": {
        "benefitsInPeriod": 200, "valuationMethodRate": 20, "daysSpaceAvailable": 250},
    "car-parking-statutory-228": {"daysCarParkingAvailable": 228, "valuationMethodRate": 20},
    "car-statutory-formula": {"baseValue": 40000, "daysAvailable": 365},
    "debt-waiver": {"amountWaived": 5000},
    "expense-payment": {"expenseValue": 2000, "otherwiseDeductiblePercentage": 0, "fbtType": "Type 1"},
    "expense-payment-in-house": {"expenseValue": 2000, "otherwiseDeductiblePercentage": 0, "fbtType": "Type 1"},
    "housing": {"housingBenefitValue": 15000, "fbtType": "Type 1"},
    "lafha": {"weeksLivedAway": 10, "accommodationPerWeek": 400, "mealsPerWeek": 200},
    "loan": {"originalLoanAmount": 50000, "interestChargedByEmployer": 1000, "otherwiseDeductiblePercentage": 50},
    "meal-entertainment-50-50": {
        "employees": 10000, "employeesAssociates": 2000, "employeesNonassociates": 3000, "fbtType": "Type 1"},
    "meal-entertainment-register-12wk": {
        "employees": 10000, "employeesAssociates": 2000, "employeesNonassociates": 3000,
        "fbtType": "Type 1", "registerPercentage": 60},
    "property": {"gstInclusiveValue": 3000, "otherwiseDeductiblePercentage": 0, "fbtType": "Type 1"},
    "property-in-house": {"gstInclusiveValue": 3000, "otherwiseDeductiblePercentage": 0, "fbtType": "Type 1"},
    "residual": {"residualValue": 2500, "otherwiseDeductiblePercentage": 0, "fbtType": "Type 1"},
    "residual-in-house": {"residualValue": 2500, "otherwiseDeductiblePercentage": 0, "fbtType": "Type 1"},
    "tebe": {"salaryPackagedMealEfle": 5000, "recreation": 2000, "fbtType": "Type 1"},
}

# Regex that matches a JSON number token that is NOT quoted and carries a
# decimal point or exponent (i.e. a bare float). Integers are allowed (counts,
# days). A value inside quotes ("60.0") is a string and does not match.
BARE_FLOAT_RE = re.compile(r'(?<!")(?<![\d.])-?\d+\.\d+(?:[eE][+-]?\d+)?(?!")')


def http(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode() or "{}"


def is_decimal_string(v):
    if not isinstance(v, str):
        return False
    try:
        float(v)
        return True
    except ValueError:
        return False


def parsed_bare_floats(obj, path=""):
    """Paths where a JSON float (Python float after parse) appears."""
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            hits += parsed_bare_floats(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += parsed_bare_floats(v, f"{path}[{i}]")
    elif isinstance(obj, float):
        hits.append(path or ".")
    return hits


def raw_bare_floats(raw_text):
    """Bare-float substrings in the raw response text (regex belt-and-braces)."""
    return BARE_FLOAT_RE.findall(raw_text)


def evaluate(urn, status, raw, call=""):
    row = {"urn": urn, "call": call, "status": status,
           "gross_up_factor": None, "grossed_up_taxable_value": None,
           "fbt_payable": None, "pass": False, "detail": ""}
    if status != 200:
        try:
            b = json.loads(raw)
            row["detail"] = str(b.get("detail") or b.get("refusal_class") or b)[:160]
        except ValueError:
            row["detail"] = f"non-200, non-JSON body: {raw[:120]}"
        return row
    try:
        b = json.loads(raw)
    except ValueError:
        row["detail"] = "200 but body is not JSON"
        return row
    trio_ok = True
    for t in TRIO:
        row[t] = b.get(t)
        if b.get(t) is None or not is_decimal_string(b.get(t)):
            trio_ok = False
    parsed = parsed_bare_floats(b)
    raw_hits = raw_bare_floats(raw)
    if not trio_ok:
        row["detail"] = "trio missing/null/not-decimal-string"
    elif parsed:
        row["detail"] = f"bare float(s) at {parsed[:5]}"
    elif raw_hits:
        row["detail"] = f"raw-text bare float(s): {raw_hits[:5]}"
    row["pass"] = trio_ok and not parsed and not raw_hits
    return row


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("API_BASE_URL", DEFAULT_BASE)).rstrip("/")
    print("=" * 72)
    print(f"smoke_fbt_computed — FBT trio + no-bare-float gate")
    print(f"Target: {base}")
    print("=" * 72)

    status, raw = http("GET", f"{base}/v1/calculators")
    if status != 200:
        print(f"\U0001f7e1 INFRA BROKEN: GET /v1/calculators -> HTTP {status}")
        return 2
    try:
        disc = json.loads(raw)
    except ValueError:
        print("\U0001f7e1 INFRA BROKEN: /v1/calculators body is not JSON")
        return 2
    fbt = sorted(c["calc_uri"] for c in disc if "calculator:fbt:" in c.get("calc_uri", ""))
    if not fbt:
        print("\U0001f7e1 INFRA BROKEN: no urn:sbrm:calculator:fbt:* in discovery")
        return 2
    print(f"\nDiscovered {len(fbt)} FBT calculator(s).\n")

    results = []
    for urn in fbt:
        leaf = urn.split(":")[-1]
        body = BODIES.get(leaf)
        if body is None:
            results.append({"urn": urn, "call": "", "status": "-",
                            "gross_up_factor": None, "grossed_up_taxable_value": None,
                            "fbt_payable": None, "pass": False,
                            "detail": "no smoke body for this URN (registry grew; add one)"})
            continue
        if leaf == "lafha":  # D21 first-call null-trio guard: assert both calls
            for call in ("call#1", "call#2"):
                s, r = http("POST", f"{base}/v1/calculators/{urn}/{PERIOD}", body)
                results.append(evaluate(urn, s, r, call))
        else:
            s, r = http("POST", f"{base}/v1/calculators/{urn}/{PERIOD}", body)
            results.append(evaluate(urn, s, r))

    # Table
    npass = sum(1 for x in results if x["pass"])
    n = len(results)
    w = f"{'URN leaf':<34}{'call':<8}{'HTTP':<6}{'gross_up / grossed_up / fbt_payable':<44}{'verdict'}"
    print(w)
    print("-" * len(w))
    for x in results:
        leaf = x["urn"].split(":")[-1]
        trio = f"{x['gross_up_factor']} / {x['grossed_up_taxable_value']} / {x['fbt_payable']}"
        verdict = "PASS" if x["pass"] else f"FAIL — {x['detail']}"
        print(f"{leaf:<34}{x['call'] or '-':<8}{str(x['status']):<6}{trio:<44}{verdict}")

    print("\n" + "=" * 72)
    allpass = all(x["pass"] for x in results)
    print(f"Result: {npass}/{n} pass")
    if allpass:
        print("\U0001f7e2 GREEN — every FBT calculator returns a decimal-string trio, no bare float")
        return 0
    print("\U0001f534 LOGIC DRIFT — one or more FBT calculators failed the trio / bare-float gate")
    return 1


if __name__ == "__main__":
    sys.exit(main())
