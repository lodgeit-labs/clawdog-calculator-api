#!/usr/bin/env bash
# scripts/smoke_prod.sh — Post-deploy production smoke gate.
#
# Lifts the mc18-2026-05-25 README's behavioural-recall post-deploy
# checklist to a Lesson #35 binary-failure gate per the mc02-ratified
# Option-C PR β sprint design (Andrew direct-voice 2026-05-28 03:14 UTC
# + 10:34 UTC + 12:59 UTC).
#
# Fires 5 wire-probes against the deployed Cloud Run service URL.
# Each check captures a load-bearing assertion about the production
# surface contract. The aggregate exit code follows the Standing Rule #8
# tri-state contract:
#
#   exit 0  🟢 GREEN          — all 5 checks pass
#   exit 1  🔴 LOGIC DRIFT    — one or more checks fail (deploy is broken;
#                                revert or roll forward)
#   exit 2  🟡 INFRA BROKEN   — curl unreachable, jq/python3 missing, DNS
#                                fail, or other tooling failure. HALT.
#
# Usage:
#   ./scripts/smoke_prod.sh                     — fires against the default URL
#   API_BASE_URL=https://... ./smoke_prod.sh    — override the URL
#
# Invoked via `make smoke-prod` per Makefile addition. Also runs in CI via
# .github/workflows/smoke-prod.yml on push to main (post-deploy gate).
#
# Lesson honours:
#   #40 — production-bundle-shape assertion against the deployed URL,
#         not hermetic
#   #38 — byte-content comparison via tests/sidecars/ JSON fixtures
#         (sidecar IS the byte-content reference; the script asserts the
#         live response keys + values match the captured sidecar)
#   #35 — binary-failure gate; the README checklist had n=3+ drift
#         opportunities (deploy stale, deploy-no-redeploy, etc.); this
#         gate fires every time main moves
#
# Required tools: curl, python3, jq is NOT required (we use python3 stdlib
# for JSON parsing; matches the calc-api repo's no-runtime-deps posture).

set -u
set -o pipefail

# Default to the production Cloud Run URL; overridable via env var.
API_BASE_URL="${API_BASE_URL:-https://fbt-calculator-api-8340695160.australia-southeast1.run.app}"

# Path resolution: script lives at scripts/smoke_prod.sh; sidecars at
# tests/sidecars/. Resolve relative to script location so the script
# works from any cwd.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
SIDECARS_DIR="$REPO_ROOT/tests/sidecars"

# URL encoding for URN path params
FBT_CALC_URI="urn%3Asbrm%3Acalculator%3Afbt%3Acar-operating-cost"
FBT_PERIOD_URI="urn%3Asbrm%3Aperiod%3Afbt%3Afy2026"
DEP_PERIOD_URI="urn%3Asbrm%3Aperiod%3Adepreciation%3Afy2026"

# Tri-state result tracking
PASS_COUNT=0
FAIL_COUNT=0
INFRA_FAIL=0

# Pre-flight: confirm curl + python3 exist
command -v curl >/dev/null 2>&1 || { echo "🟡 INFRA BROKEN: curl not installed" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "🟡 INFRA BROKEN: python3 not installed" >&2; exit 2; }

# Pre-flight: confirm sidecar fixtures exist
[ -f "$SIDECARS_DIR/ntaa_row_3_response.json" ] || { echo "🟡 INFRA BROKEN: sidecar tests/sidecars/ntaa_row_3_response.json missing" >&2; exit 2; }
[ -f "$SIDECARS_DIR/depreciation_engine_unavailable_response.json" ] || { echo "🟡 INFRA BROKEN: sidecar tests/sidecars/depreciation_engine_unavailable_response.json missing" >&2; exit 2; }

echo "============================================================"
echo "smoke_prod — Option-C PR β binary-failure gate"
echo "Target: $API_BASE_URL"
echo "Sidecars: $SIDECARS_DIR"
echo "============================================================"

# ----------------------------------------------------------------------
# Check 1: GET /livez returns 200 + expected body
# ----------------------------------------------------------------------
echo ""
echo "--- Check 1: GET /livez ---"
LIVEZ_TMP=$(mktemp)
HTTP_STATUS=$(curl -sS -o "$LIVEZ_TMP" -w "%{http_code}" "$API_BASE_URL/livez" 2>&1) || {
    echo "🟡 INFRA BROKEN: curl failed against $API_BASE_URL/livez"
    rm -f "$LIVEZ_TMP"
    exit 2
}
if [ "$HTTP_STATUS" != "200" ]; then
    echo "🔴 FAIL: expected HTTP 200, got $HTTP_STATUS"
    cat "$LIVEZ_TMP"
    FAIL_COUNT=$((FAIL_COUNT + 1))
else
    BODY_OK=$(python3 -c "
import json, sys
d = json.load(open('$LIVEZ_TMP'))
ok = d.get('status') == 'ok' and d.get('service') == 'clawdog-calculator-api'
print('OK' if ok else 'BAD')
")
    if [ "$BODY_OK" = "OK" ]; then
        echo "🟢 PASS: HTTP 200; body status=ok, service=clawdog-calculator-api"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "🔴 FAIL: HTTP 200 but body unexpected:"
        cat "$LIVEZ_TMP"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
fi
rm -f "$LIVEZ_TMP"

# ----------------------------------------------------------------------
# Check 2: NTAA Row 3 byte-exact regression against sidecar
# ----------------------------------------------------------------------
echo ""
echo "--- Check 2: NTAA Row 3 byte-exact regression (FBT) ---"
NTAA_TMP=$(mktemp)
HTTP_STATUS=$(curl -sS -o "$NTAA_TMP" -w "%{http_code}" -X POST \
    "$API_BASE_URL/v1/calculators/$FBT_CALC_URI/$FBT_PERIOD_URI" \
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
    }' 2>&1) || {
    echo "🟡 INFRA BROKEN: curl failed against FBT calc route"
    rm -f "$NTAA_TMP"
    exit 2
}
if [ "$HTTP_STATUS" != "200" ]; then
    echo "🔴 FAIL: expected HTTP 200, got $HTTP_STATUS"
    head -c 500 "$NTAA_TMP"
    FAIL_COUNT=$((FAIL_COUNT + 1))
else
    # Assert the 4 byte-exact values from sidecar against live response
    CHECK_RESULT=$(python3 -c "
import json
live = json.load(open('$NTAA_TMP'))
sidecar = json.load(open('$SIDECARS_DIR/ntaa_row_3_response.json'))
# Compare the 4 load-bearing values; ignore manifest content_hash which
# legitimately varies if Brain canon updates between sidecar capture and
# live deploy.
def trace(d): return d.get('trace', {})
mismatches = []
for k in ['taxable_value']:
    if live.get(k) != sidecar.get(k):
        mismatches.append(f'{k}: live={live.get(k)} sidecar={sidecar.get(k)}')
for k in ['deemed_depreciation', 'deemed_interest', 'deemed_total']:
    lv = trace(live).get(k)
    sv = trace(sidecar).get(k)
    if lv != sv:
        mismatches.append(f'trace.{k}: live={lv} sidecar={sv}')
if mismatches:
    print('FAIL:' + '|'.join(mismatches))
else:
    print('OK')
")
    if [ "$CHECK_RESULT" = "OK" ]; then
        echo "🟢 PASS: NTAA Row 3 byte-exact match (taxable_value, deemed_depreciation, deemed_interest, deemed_total)"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "🔴 FAIL: byte-exact mismatch:"
        echo "  $CHECK_RESULT"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
fi
rm -f "$NTAA_TMP"

# ----------------------------------------------------------------------
# Check 3: Depreciation route returns structured 502 with sidecar-matching body
# ----------------------------------------------------------------------
echo ""
echo "--- Check 3: Depreciation route structured 502 (OT #83 #1 closure) ---"
DEP_TMP=$(mktemp)
DEP_HEADERS_TMP=$(mktemp)
HTTP_STATUS=$(curl -sS -D "$DEP_HEADERS_TMP" -o "$DEP_TMP" -w "%{http_code}" -X POST \
    "$API_BASE_URL/v1/calculators/depreciation/audit/$DEP_PERIOD_URI" \
    -H "Content-Type: application/json" \
    -d '{
      "transitionDate": "2025-07-01",
      "method": "primecost",
      "assetsToAudit": [{
        "assetId": "test-1",
        "assetName": "Toyota Corolla",
        "purchaseDate": "2020-07-01",
        "originalCost": 30000,
        "taxMethod": "pc",
        "currentBookAccumDep": 15000
      }]
    }' 2>&1) || {
    echo "🟡 INFRA BROKEN: curl failed against depreciation route"
    rm -f "$DEP_TMP" "$DEP_HEADERS_TMP"
    exit 2
}
if [ "$HTTP_STATUS" != "502" ]; then
    echo "🔴 FAIL: expected HTTP 502 (engine unreachable), got $HTTP_STATUS"
    head -c 500 "$DEP_TMP"
    FAIL_COUNT=$((FAIL_COUNT + 1))
else
    # Assert content-type is application/json (NEVER text/plain bare HTML)
    CONTENT_TYPE=$(grep -i "^content-type:" "$DEP_HEADERS_TMP" | head -1 | tr -d '\r')
    case "$CONTENT_TYPE" in
        *application/json*)
            CHECK_RESULT=$(python3 -c "
import json
live = json.load(open('$DEP_TMP'))
sidecar = json.load(open('$SIDECARS_DIR/depreciation_engine_unavailable_response.json'))
ldetail = live.get('detail', {})
sdetail = sidecar.get('detail', {})
mismatches = []
for k in ['error', 'error_code', 'engine']:
    if ldetail.get(k) != sdetail.get(k):
        mismatches.append(f'detail.{k}: live={ldetail.get(k)!r} sidecar={sdetail.get(k)!r}')
if mismatches:
    print('FAIL:' + '|'.join(mismatches))
else:
    print('OK')
")
            if [ "$CHECK_RESULT" = "OK" ]; then
                echo "🟢 PASS: HTTP 502 application/json with error_code=engine_unreachable engine=depreciation (matches sidecar)"
                PASS_COUNT=$((PASS_COUNT + 1))
            else
                echo "🔴 FAIL: body shape mismatch against sidecar:"
                echo "  $CHECK_RESULT"
                FAIL_COUNT=$((FAIL_COUNT + 1))
            fi
            ;;
        *)
            echo "🔴 FAIL: content-type not application/json: $CONTENT_TYPE"
            echo "  (This means the bare-HTML 500 regression has reappeared; OT #83 #1 has NOT been closed)"
            head -c 200 "$DEP_TMP"
            FAIL_COUNT=$((FAIL_COUNT + 1))
            ;;
    esac
fi
rm -f "$DEP_TMP" "$DEP_HEADERS_TMP"

# ----------------------------------------------------------------------
# Check 4: FBT intentional-error returns 422 JSON (input validation regression)
# ----------------------------------------------------------------------
echo ""
echo "--- Check 4: FBT intentional-error returns 422 JSON ---"
ERR_TMP=$(mktemp)
ERR_HEADERS_TMP=$(mktemp)
HTTP_STATUS=$(curl -sS -D "$ERR_HEADERS_TMP" -o "$ERR_TMP" -w "%{http_code}" -X POST \
    "$API_BASE_URL/v1/calculators/$FBT_CALC_URI/$FBT_PERIOD_URI" \
    -H "Content-Type: application/json" \
    -d '{"businessUsePercentage": 75}' 2>&1) || {
    echo "🟡 INFRA BROKEN: curl failed"
    rm -f "$ERR_TMP" "$ERR_HEADERS_TMP"
    exit 2
}
if [ "$HTTP_STATUS" != "422" ]; then
    echo "🔴 FAIL: expected HTTP 422, got $HTTP_STATUS"
    head -c 500 "$ERR_TMP"
    FAIL_COUNT=$((FAIL_COUNT + 1))
else
    CONTENT_TYPE=$(grep -i "^content-type:" "$ERR_HEADERS_TMP" | head -1 | tr -d '\r')
    case "$CONTENT_TYPE" in
        *application/json*)
            DETAIL_OK=$(python3 -c "
import json
d = json.load(open('$ERR_TMP'))
detail = d.get('detail', [])
ok = isinstance(detail, list) and len(detail) > 0 and 'missing' in (detail[0].get('type', '') if isinstance(detail[0], dict) else '')
print('OK' if ok else 'BAD')
")
            if [ "$DETAIL_OK" = "OK" ]; then
                echo "🟢 PASS: HTTP 422 application/json with missing-field detail array"
                PASS_COUNT=$((PASS_COUNT + 1))
            else
                echo "🔴 FAIL: 422 body shape unexpected:"
                head -c 300 "$ERR_TMP"
                FAIL_COUNT=$((FAIL_COUNT + 1))
            fi
            ;;
        *)
            echo "🔴 FAIL: content-type not application/json: $CONTENT_TYPE"
            FAIL_COUNT=$((FAIL_COUNT + 1))
            ;;
    esac
fi
rm -f "$ERR_TMP" "$ERR_HEADERS_TMP"

# ----------------------------------------------------------------------
# Check 5: OpenAPI surface has expected paths (regression on route registration)
# ----------------------------------------------------------------------
echo ""
echo "--- Check 5: openapi.json registers expected paths ---"
OPENAPI_TMP=$(mktemp)
HTTP_STATUS=$(curl -sS -o "$OPENAPI_TMP" -w "%{http_code}" "$API_BASE_URL/openapi.json" 2>&1) || {
    echo "🟡 INFRA BROKEN: curl failed against openapi.json"
    rm -f "$OPENAPI_TMP"
    exit 2
}
if [ "$HTTP_STATUS" != "200" ]; then
    echo "🔴 FAIL: expected HTTP 200, got $HTTP_STATUS"
    FAIL_COUNT=$((FAIL_COUNT + 1))
else
    PATHS_OK=$(python3 -c "
import json
d = json.load(open('$OPENAPI_TMP'))
paths = d.get('paths', {})
required = [
    '/livez',
    '/healthz',
    '/v1/calculators',
    '/v1/calculators/{calc_uri}/{period_uri}',
    '/v1/calculators/depreciation/audit/{period_uri}',
    '/v1/rates/{period_uri}',
    '/v1/rates/{period_uri}/{rate_id}',
]
missing = [p for p in required if p not in paths]
if missing:
    print('MISSING:' + ','.join(missing))
else:
    print('OK')
")
    if [ "$PATHS_OK" = "OK" ]; then
        echo "🟢 PASS: all 7 expected paths registered"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "🔴 FAIL: $PATHS_OK"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
fi
rm -f "$OPENAPI_TMP"

# ----------------------------------------------------------------------
# Check 6: GET /v1/calculators lists Wave A FBT methods
# (mut-2026-05-31-mc15 — production-resolver-shape assertion at the
# calculator-discovery boundary; per-URN POST byte-content assertions
# deferred until canonical engine-response sidecars land.)
# ----------------------------------------------------------------------
echo ""
echo "--- Check 6: GET /v1/calculators lists Wave A FBT methods ---"
CALCS_TMP=$(mktemp)
HTTP_STATUS=$(curl -sS -o "$CALCS_TMP" -w "%{http_code}" "$API_BASE_URL/v1/calculators" 2>&1) || {
    echo "🟡 INFRA BROKEN: curl failed against /v1/calculators"
    rm -f "$CALCS_TMP"
    exit 2
}
if [ "$HTTP_STATUS" != "200" ]; then
    echo "🔴 FAIL: expected HTTP 200, got $HTTP_STATUS"
    head -c 300 "$CALCS_TMP"
    FAIL_COUNT=$((FAIL_COUNT + 1))
else
    CALCS_OK=$(python3 -c "
import json
d = json.load(open('$CALCS_TMP'))
uris = {c.get('calc_uri') for c in d}
required = {
    'urn:sbrm:calculator:fbt:car-operating-cost',
    'urn:sbrm:calculator:fbt:loan',
    'urn:sbrm:calculator:fbt:debt-waiver',
    'urn:sbrm:calculator:fbt:expense-payment',
    'urn:sbrm:calculator:fbt:expense-payment-in-house',
    'urn:sbrm:calculator:fbt:property',
    'urn:sbrm:calculator:fbt:property-in-house',
    'urn:sbrm:calculator:fbt:residual',
    'urn:sbrm:calculator:fbt:residual-in-house',
    'urn:sbrm:calculator:fbt:housing',
    'urn:sbrm:calculator:fbt:lafha',
    'urn:sbrm:calculator:fbt:board',
    'urn:sbrm:calculator:fbt:tebe',
    'urn:sbrm:calculator:fbt:car-parking-actual',
    'urn:sbrm:calculator:fbt:car-parking-statutory-228',
    'urn:sbrm:calculator:fbt:car-parking-register-12wk',
    'urn:sbrm:calculator:fbt:meal-entertainment-50-50',
    'urn:sbrm:calculator:fbt:meal-entertainment-register-12wk',
    'urn:sbrm:calculator:fbt:car-statutory-formula',
    'urn:sbrm:calculator:depreciation:audit',
}
missing = required - uris
if missing:
    print('MISSING:' + ','.join(sorted(missing)))
else:
    print('OK')
")
    if [ "$CALCS_OK" = "OK" ]; then
        echo "🟢 PASS: all 20 expected calculator URNs registered (2 existing + 8 Wave A + 4 Wave B + 6 Wave C)"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "🔴 FAIL: $CALCS_OK"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
fi
rm -f "$CALCS_TMP"

# ----------------------------------------------------------------------
# Check 7: MCP tools/list returns at least 10 tools post Wave A
# (mut-2026-05-31-mc15)
# ----------------------------------------------------------------------
echo ""
echo "--- Check 7: MCP tools/list returns at least 10 tools post Wave A ---"
MCP_TMP=$(mktemp)
HTTP_STATUS=$(curl -sS -o "$MCP_TMP" -w "%{http_code}" -X POST \
    "$API_BASE_URL/mcp" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' 2>&1) || {
    echo "🟡 INFRA BROKEN: curl failed against /mcp"
    rm -f "$MCP_TMP"
    exit 2
}
if [ "$HTTP_STATUS" != "200" ]; then
    echo "🔴 FAIL: expected HTTP 200, got $HTTP_STATUS"
    head -c 300 "$MCP_TMP"
    FAIL_COUNT=$((FAIL_COUNT + 1))
else
    MCP_OK=$(python3 -c "
import json
d = json.load(open('$MCP_TMP'))
tools = d.get('result', {}).get('tools', [])
names = {t.get('name') for t in tools}
required = {
    'fbt-car-operating-cost',
    'fbt-loan',
    'fbt-debt-waiver',
    'fbt-expense-payment',
    'fbt-expense-payment-in-house',
    'fbt-property',
    'fbt-property-in-house',
    'fbt-residual',
    'fbt-residual-in-house',
    'fbt-housing',
    'fbt-lafha',
    'fbt-board',
    'fbt-tebe',
    'fbt-car-parking-actual',
    'fbt-car-parking-statutory-228',
    'fbt-car-parking-register-12wk',
    'fbt-meal-entertainment-50-50',
    'fbt-meal-entertainment-register-12wk',
    'fbt-car-statutory-formula',
    'depreciation-audit',
}
missing = required - names
if missing:
    print('MISSING:' + ','.join(sorted(missing)))
else:
    print('OK')
")
    if [ "$MCP_OK" = "OK" ]; then
        echo "🟢 PASS: MCP tools/list advertises all 20 expected tools"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "🔴 FAIL: $MCP_OK"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
fi
rm -f "$MCP_TMP"

# ----------------------------------------------------------------------
# Aggregate verdict
# ----------------------------------------------------------------------
echo ""
echo "============================================================"
echo "Result: PASS=$PASS_COUNT FAIL=$FAIL_COUNT (of 7)"
echo "============================================================"

if [ "$FAIL_COUNT" -eq 0 ]; then
    echo "🟢 GREEN — production-bundle gate clean"
    exit 0
else
    echo "🔴 LOGIC DRIFT — $FAIL_COUNT of 7 checks failed; deploy is broken or production drifted"
    exit 1
fi
