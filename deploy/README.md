# Deploy runbook — clawdog-calculator-api (Phase 3a)

> **Subagents do NOT execute these commands.** This runbook is written for
> Andrew to drive locally from PowerShell or `gcloud` in WSL. The Phase 3a
> brief constrains agent execution to author-only; deployment is human-driven.

## One-time GCP setup

```sh
# Create the project (Andrew has done this manually before first deploy).
gcloud projects create lodgeit-calc-constellation \
    --name="LodgeiT Calculator Constellation"

# Set the default project + region (Standing Rule #4: au-southeast1 matches Fano).
gcloud config set project lodgeit-calc-constellation
gcloud config set run/region australia-southeast1

# Enable APIs.
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com

# Create the Artifact Registry repository.
gcloud artifacts repositories create clawdog \
    --location=australia-southeast1 \
    --repository-format=docker \
    --description="ClawDog calculator-constellation containers"

# Create the runtime service account.
gcloud iam service-accounts create clawdog-calculator-api \
    --display-name="ClawDog Calculator API runtime"
```

## First deploy

```sh
# From the repo root.
make build

# Tag + push to Artifact Registry.
docker tag clawdog-calculator-api:dev \
    australia-southeast1-docker.pkg.dev/lodgeit-calc-constellation/clawdog/clawdog-calculator-api:latest
gcloud auth configure-docker australia-southeast1-docker.pkg.dev
docker push \
    australia-southeast1-docker.pkg.dev/lodgeit-calc-constellation/clawdog/clawdog-calculator-api:latest

# Deploy from source (alternatively: --image=... to use the pushed image).
make deploy
```

## Subsequent deploys (CRITICAL — read before running anything)

There are **two distinct deploy paths**. Mixing them up is the failure mode
that cost three deploy cycles on 2026-05-25 (mc14 → mc16 → mc17 → mc18).
Read this section before dispatching any deploy.

### Path A — `gcloud run services replace deploy/cloud-run.yaml`

**Updates Cloud Run service CONFIGURATION ONLY.** Env vars, scaling,
image-tag pointer, IAM, labels.

**Does NOT rebuild or push container images.** The `image:` field in
`cloud-run.yaml` points at `australia-southeast1-docker.pkg.dev/.../
clawdog-calculator-api:latest`. `services replace` makes the Cloud Run
service pull whatever `:latest` resolves to RIGHT NOW — which may be a
stale image from days ago if no fresh build has been pushed.

**Use Path A when the change is config-only.** Examples:

- env var values (e.g. `FBT_PROLOG_URL`, `LOG_LEVEL`)
- scaling parameters (min/max instances, concurrency, timeout)
- labels / annotations
- IAM service-account binding

**Path A symptom of misuse:** you change source code or a vendored
rate-table file, `services replace` reports SUCCESS, and the live API
still behaves as before. The image didn't change. `services replace` cannot
bake your new files into a container; it can only point at containers that
already exist.

### Path B — `make deploy` (or `gcloud run deploy --source .`)

**Rebuilds the container image from current source via Cloud Build, pushes
to Artifact Registry, then updates the Cloud Run service to use the new
image.** Full deploy chain in one command.

**Use Path B when the change is in image content.** Examples:

- source code in `api/`, `scripts/`, etc.
- vendored rate-table files under `rate_tables/SBRM_RATE_TABLE/`
- `pyproject.toml` dependency changes
- Dockerfile changes
- anything else under the build context

**The canonical Path B incantation (works from any clean `main` checkout):**

```sh
gcloud run deploy fbt-calculator-api \
    --source . \
    --region australia-southeast1 \
    --project lodgeit-calc-constellation \
    --platform managed \
    --allow-unauthenticated
```

or equivalently from the repo root:

```sh
make deploy
```

**Hybrid case — you changed BOTH image content AND `cloud-run.yaml`:**
run Path B first (gets the new image content into Cloud Run with the
CURRENT YAML config baked from `--source`), then Path A second (overwrites
the service config with the new YAML). Order matters: Path B first means
the new image is live BEFORE the new config switches traffic to it.

### Post-deploy smoke (mandatory — do NOT skip)

After EITHER path, fire the binary-failure smoke gate from the repo root:

```sh
make smoke-prod
```

This runs `scripts/smoke_prod.sh` which fires **5 wire-probes** against
the deployed Cloud Run service URL and exits per Standing Rule #8
tri-state:

| Exit | State | Meaning |
|------|-------|---------|
| 0 | \U0001f7e2 GREEN | All 5 checks pass; deploy is structurally complete |
| 1 | \U0001f534 LOGIC DRIFT | One or more checks failed; deploy is broken or production drifted |
| 2 | \U0001f7e1 INFRA BROKEN | curl/python3 missing or DNS fail; halt + alert |

The 5 checks are:

1. `/livez` returns 200 with `{status: 'ok', service: 'clawdog-calculator-api'}`
2. NTAA Row 3 FBT car operating-cost calc returns 200 with byte-exact `taxable_value`, `deemed_depreciation`, `deemed_interest`, `deemed_total` (regression on the canonical FBT result; sidecar at `tests/sidecars/ntaa_row_3_response.json`)
3. Depreciation route returns **structured JSON 502** with `error_code=engine_unreachable, engine=depreciation` (NEVER bare HTML 500; sidecar at `tests/sidecars/depreciation_engine_unavailable_response.json`)
4. FBT intentional-error returns 422 with `application/json` body + missing-field detail array
5. `openapi.json` registers all 7 expected paths

The gate also runs in CI via `.github/workflows/smoke-prod.yml` (post-deploy + hourly schedule + manual trigger).

Per Standing Rule #12 (production resolver shape assertions) + Lesson #40 (hermetic green is not production-bundle green) + Lesson #35 (binary-failure beats behavioural-recall — this gate replaces the previous inline-curl checklist which was a behavioural-recall pattern; the gate is mechanical).

Override the target URL via env var:

```sh
API_BASE_URL=https://my-other-cloud-run-url.run.app make smoke-prod
```

Introduced by `mut-2026-05-28-mc07` (Option-C PR β; Andrew direct-voice ratified 2026-05-28).

## Pre-deploy gates (must all be 🟢 before deploy)

1. `make openapi-check`  — committed `openapi.json` matches the live FastAPI app.
2. `make ruff`           — lint clean.
3. `make test`           — all four binary-failure gates pass (pytest).
4. CI on the merge commit is green (`audit-binary-failure-gates` workflow).

If any of the four are red, stop. The Phase 3a discipline is **binary-failure
gates first; deploy never goes out red** (CLAWDOG/110 §3).

## Roll back

Cloud Run keeps the previous revision live. Roll back via:

```sh
gcloud run services update-traffic fbt-calculator-api \
    --to-revisions=<previous-revision-name>=100
```

## Decommission / pause

Phase 3a is non-billable when at zero traffic. To force-stop:

```sh
gcloud run services delete fbt-calculator-api --quiet
```

## Cross-references

- **Architecture canon:** `GLOBAL_NOTES/CLAWDOG/109_CALCULATOR_CONSTELLATION.md`
- **Outsource discipline:** `GLOBAL_NOTES/CLAWDOG/110_OUTSOURCE_BOUNDARY_DISCIPLINE.md`
- **Standing Rule #4** (Fano immutables, australia-southeast1, no training in Cloud Run)
- **Standing Rule #1** (mechanical enforcement via `make install-hooks`)
