# clawdog-calculator-api

**Calculator-Constellation REST API — Egress Interface for the LodgeiT calculator pool (Phase 3a).**

This repository implements the **REST surface** of the calculator constellation defined in [CLAWDOG/109 — Calculator Constellation](https://github.com/futureWA/clawdog-brain/blob/master/GLOBAL_NOTES/CLAWDOG/109_CALCULATOR_CONSTELLATION.md): a stateless HTTP wrapper over a deterministic SWI-Prolog substrate, projecting period-scoped statutory rate-tables, regression-anchored math, and content-addressable provenance through three coordinated surfaces (MCP, REST, direct Prolog HTTP). This repo is the **REST surface**; the MCP server (Phase 3b) and direct Prolog substrate (`lodgeit-labs/LodgeiT_FBT`, etc.) live elsewhere.

Authoring discipline is governed by [CLAWDOG/110 — Outsource Boundary Discipline](https://github.com/futureWA/clawdog-brain/blob/master/GLOBAL_NOTES/CLAWDOG/110_OUTSOURCE_BOUNDARY_DISCIPLINE.md), even for in-house work — the five non-negotiables (manifest-fidelity, advisory-boundary, atom-vs-bridge, OpenAPI drift, Standing Rule #1) are binary-failure gates wired into CI. Per Standing Rule #7, this repo is classified as an **Egress Interface** (transport buffer); statutory authoring lives in the calculator repos and the Brain.

## Quick start (Andrew's local box)

```bash
# One-time: install client-side mechanical enforcement of Standing Rule #1.
make install-hooks

# Install Python deps + dev extras.
pip install -e ".[dev]"

# Run the binary-failure gate test suite locally (CI runs the same).
make test

# Bring the local stack up (API + Prolog FBT engine via docker-compose).
# Adjust LODGEIT_FBT_REPO if your LodgeiT_FBT checkout lives elsewhere.
LODGEIT_FBT_REPO=../LodgeiT_FBT make run
```

Once `make run` is up, the canonical PR-D 5th case (Phase 2l-OC-integrate)
exercises the bridge end-to-end:

```bash
curl -sS -X POST \
  "http://localhost:8000/v1/calculators/urn%3Asbrm%3Acalculator%3Afbt%3Acar-operating-cost/urn%3Asbrm%3Aperiod%3Afbt%3Afy2026" \
  -H 'Content-Type: application/json' \
  -d '{
        "businessUsePercentage": 75,
        "employeeContribution": 200,
        "formOfFinance": "owned",
        "leasePayments": 0,
        "fuelRepairsServicing": 3000,
        "registrationInsurance": 1500,
        "noPrivateUseReduction": 0,
        "acquisitionDate": "2024-04-01",
        "openingDepreciatedValue": 55000,
        "daysHeldInFBTYear": 365
      }' | jq .
# →  taxable_value: 5547.75
#    trace.deemed_dispatch: "computed"
#    trace.deemed_total: 18491
#    manifest.rate_table_uris: [3 entries with live content_hashes]
#    advisory: <TAA 1953 + TASA 2009 disclaimer>
```

## Architectural surfaces

### REST endpoints (Phase 3a Cut A — minimum viable)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/calculators/{calc_uri}/{period_uri}` | Calculator invocation — pydantic-validated input → Prolog engine → `{taxable_value, trace, manifest, advisory}` envelope. URN path params are URL-encoded. |
| `GET`  | `/v1/calculators` | Discovery listing — Phase 3a hardcodes one entry (FBT car operating cost); Phase 3c onboards a second. |
| `GET`  | `/v1/rates/{period_uri}` | Rate-table snapshot for a period — every fact-node listed with its live content_hash. |
| `GET`  | `/v1/rates/{period_uri}/{rate_id}` | Single rate-table fact-node — parsed frontmatter + body + content_hash. |
| `GET`  | `/healthz` | Liveness probe (no upstream coupling). |

OpenAPI: see [`openapi.json`](./openapi.json) (regenerated from the live FastAPI
app via `make openapi`; CI fails on drift).

### The four binary-failure gates (CI-enforced)

CLAWDOG/110 §3 codifies five non-negotiables. Four of them have wired binary-failure tests in this repo; the fifth (Standing Rule #1 inheritance) is a pre-push hook installed by `make install-hooks`.

| # | Gate | Test file | Anchor lesson |
|---|---|---|---|
| 1 | **Manifest-Fidelity Contract** | `tests/test_manifest_fidelity.py` | Lesson #38 (file existence ≠ content fidelity) |
| 2 | **Advisory-Boundary Contract** | `tests/test_advisory_boundary.py` | Lesson #34 (reconcile-then-surface) |
| 3 | **PR-D Case 5 Production Surface** | `tests/test_phase3a_e2e.py` | Lesson #37 (production surface, not wind tunnel) |
| 4 | **OpenAPI Drift Gate** | `tests/test_openapi_drift.py` | Lesson #35 (binary-failure rules don't drift) |
| 5 | **Standing Rule #1 Inheritance** | `scripts/hooks/pre-push` (installed via `make install-hooks`) | Lesson #39 (canonical Lesson #35 vulnerability) |

All four pytest gates are wired into CI ([`.github/workflows/ci.yml`](./.github/workflows/ci.yml)) and run on every push to `clawdog/*` and every PR to `master` / `main`.

### What lives where (Phase 3a topology)

```
clawdog-calculator-api/                  ← THIS repo (Egress Interface)
├── api/                                 ← FastAPI bridge layer
│   ├── main.py                          ← app entrypoint
│   ├── manifest_fidelity.py             ← Lesson #38 byte-content discipline
│   ├── prolog_client.py                 ← async HTTP client to FBT_Engine.pl
│   ├── lib/advisory_boundary.py         ← TAA 1953 + TASA disclaimer
│   ├── routes/calculators.py            ← invocation + listing
│   ├── routes/rates.py                  ← rate-table provenance surface
│   └── schemas/                         ← pydantic input/output (atom-vs-bridge)
├── tests/                               ← four binary-failure gates + fixtures
│   ├── fixtures/sbrm_rate_table_fy2026/ ← vendored snapshot (10 fact-nodes)
│   └── fixtures/prolog_response_pr_d_case_5.json
├── deploy/                              ← Cloud Run service descriptor + runbook
├── scripts/hooks/pre-push               ← Standing Rule #1 mechanical enforcement
├── Dockerfile                           ← multi-stage; locale-gen en_AU.UTF-8
├── docker-compose.yml                   ← local-dev stack (Andrew runs)
└── .github/workflows/ci.yml             ← four binary-failure gates in CI
```

## MCP (Model Context Protocol) surface

**Added at `mut-2026-05-29-mc08` Option-A PR 2.** The calc-API now speaks MCP JSON-RPC 2.0 at `/mcp` so MCP-aware clients (Claude Desktop, OpenClaw webchat, the LodgeiT GL Playground host shell, partner integrations such as Streamace + Waqas's Office.js add-in) can invoke calculators as MCP **tools** and mount widget UIs as MCP **resources** without needing knowledge of the underlying REST shape.

**Protocol surface implemented** (subset of MCP spec 2025-06-18):

| Method | Purpose |
|---|---|
| `tools/list` | Enumerate calculators as MCP tools (one entry per row in `_CALCULATOR_REGISTRY`). |
| `tools/call` | Return a structured REST-redirect block pointing the client at `POST /v1/calculators/{calc_uri}/{period_uri}` (or the depreciation sibling route), plus the iframe-loadable widget URL when one is mapped. |
| `resources/list` | Enumerate standalone widgets (shipped: `gl-detail-csv-uploader`) plus calc-bound widget mappings. |
| `resources/read` | Return a `ui_resource` block with the widget URL on `https://lodgeit.org/clawdog-widget-renderer/widgets/<slug>/` (override via `CLAWDOG_WIDGET_RENDERER_URL` env var for staging). |

**Tool-name convention:** the URN's last two segments joined with a hyphen. So `urn:sbrm:calculator:fbt:car-operating-cost` → `fbt-car-operating-cost`; `urn:sbrm:calculator:depreciation:audit` → `depreciation-audit`.

**Resource-URI scheme** (custom, MCP spec allows any URI scheme):

- `urn:clawdog:widget:standalone:<slug>` — standalone widget (no calc binding)
- `urn:clawdog:widget:calc:<calc_uri>` — widget bound to a specific calc URI

### Curl examples

**List MCP tools:**

```bash
curl -sS -X POST https://fbt-calculator-api-8340695160.australia-southeast1.run.app/mcp \
     -H 'Content-Type: application/json' \
     -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

**List widget resources:**

```bash
curl -sS -X POST https://fbt-calculator-api-8340695160.australia-southeast1.run.app/mcp \
     -H 'Content-Type: application/json' \
     -d '{"jsonrpc":"2.0","method":"resources/list","id":2}'
```

**Read a widget resource** (returns `_ui_resource.widget_url` for iframe mounting):

```bash
curl -sS -X POST https://fbt-calculator-api-8340695160.australia-southeast1.run.app/mcp \
     -H 'Content-Type: application/json' \
     -d '{"jsonrpc":"2.0","method":"resources/read","id":3,"params":{"uri":"urn:clawdog:widget:standalone:gl-detail-csv-uploader"}}'
```

**Dispatch via tools/call** (returns a `_dispatch.url` for the REST POST + a `_dispatch.widget_url` for optional iframe rendering):

```bash
curl -sS -X POST https://fbt-calculator-api-8340695160.australia-southeast1.run.app/mcp \
     -H 'Content-Type: application/json' \
     -d '{"jsonrpc":"2.0","method":"tools/call","id":4,
          "params":{"name":"fbt-car-operating-cost",
                    "arguments":{"period_uri":"urn:sbrm:period:fbt:fy2026",
                                 "businessUsePercentage":75,
                                 "employeeContribution":200,
                                 "formOfFinance":"owned",
                                 "leasePayments":0,
                                 "fuelRepairsServicing":3000,
                                 "registrationInsurance":1500,
                                 "noPrivateUseReduction":0,
                                 "acquisitionDate":"2024-04-01",
                                 "openingDepreciatedValue":55000,
                                 "daysHeldInFBTYear":365}}}'
```

**JSON-RPC error codes:**

| Code | Meaning |
|---|---|
| -32700 | Parse error (malformed JSON) |
| -32600 | Invalid request envelope (missing `jsonrpc=2.0` or `method`) |
| -32601 | Method not found |
| -32602 | Invalid params |
| -32603 | Internal error |
| -32001 | MCP tool not found |
| -32002 | MCP resource not found |
| -32003 | MCP dispatch failed |

**Authentication:** inherits the REST surface's posture (CORS + IP allow-list); MCP-client auth + L402 gating land in later sprints per CLAWDOG/150.

## Standing Rules in scope

| Rule | How this repo honours it |
|---|---|
| **#1 ClawDog Git Protocol** | `scripts/hooks/pre-push` (installed via `make install-hooks`); branch protection visual layer is Andrew's responsibility. |
| **#4 Fano-Constraint API immutables** | Cloud Run target `australia-southeast1`; `locale-gen en_AU.UTF-8` in the runtime image; **no training inside Cloud Run** (this service is invocation-only). |
| **#6 Hoffman Temporal-Dimension Discipline** | No statutory constants in any Python source; the bridge is rate-table-blind, the upstream Prolog engine reads `SBRM_RATE_TABLE/<calc>/<taxonomy>/<period>/` (taxonomy axis added at `mut-2026-05-12-mc16` per clawdog-brain CLAWDOG/111). |
| **#7 Repository Topology Discipline** | This repo is an **Egress Interface**; provenance lives in the Brain and the calculator repos. |
| **#11 Verbatim-Claim Byte-Diff Discipline** | The advisory disclaimer is paraphrased + cites by section (TAA 1953 s284-15, TASA 2009 s50-5, FA 2008 Sch41). No verbatim transcription from statute or canon nodes; no `verbatim_claims:` declarations needed. |

## Cross-references

- **Architecture canon:** [CLAWDOG/109 — Calculator Constellation](https://github.com/futureWA/clawdog-brain/blob/master/GLOBAL_NOTES/CLAWDOG/109_CALCULATOR_CONSTELLATION.md) (§3 tri-surface model, §6 advisory-boundary framing, §7 manifest-fidelity contract, §8 phased runway).
- **Outsource-boundary canon:** [CLAWDOG/110 — Outsource Boundary Discipline](https://github.com/futureWA/clawdog-brain/blob/master/GLOBAL_NOTES/CLAWDOG/110_OUTSOURCE_BOUNDARY_DISCIPLINE.md) (the five non-negotiables governing every change here).
- **Empirical first instance:** `lodgeit-labs/LodgeiT_FBT` PR #12 (Phase 2l-OC-integrate) — the PR-D 5th case the Phase 3a E2E test pins against.
- **Manifest-fidelity Brain-side algorithm:** `clawdog-brain/scripts/audit_content_hashes.py` — `api/manifest_fidelity.py` is a byte-identical port verified by the test suite via in-process and (when `CLAWDOG_BRAIN_ROOT` is set) subprocess cross-check.

## License

MIT. See [Licence.txt](./Licence.txt).

*— ClawDog ∮*
