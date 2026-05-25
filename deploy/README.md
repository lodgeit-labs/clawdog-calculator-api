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

After EITHER path, smoke the actual calculator endpoints, not just
`/livez`. A 200 on `/livez` only proves the FastAPI process started; it
does NOT prove the engine path, rate-table bundle, or manifest builder
work. Per Standing Rule #12 (production resolver shape assertions) and
Lesson #40 (hermetic green is not production-bundle green):

```sh
curl -sS -X POST -H 'Content-Type: application/json' \
  -d '{"businessUsePercentage":80,"employeeContribution":1000,
       "formOfFinance":"owned","fuelRepairsServicing":4500,
       "registrationInsurance":1200,"acquisitionDate":"2024-04-01",
       "acquisitionCost":35000,"daysHeldInFBTYear":366}' \
  'https://fbt-calculator-api-8340695160.australia-southeast1.run.app/v1/calculators/urn%3Asbrm%3Acalculator%3Afbt%3Acar-operating-cost/urn%3Asbrm%3Aperiod%3Afbt%3Afy2026' \
  | python3 -m json.tool
```

**Expected:** HTTP 200 + JSON with `taxable_value` (a number), `trace`,
`manifest` (with `rate_table_uris` populated), `advisory`.

**Not expected:** any `"error": "manifest_rate_table_unavailable"`,
any HTTP 500, any bare HTML. If you see those, the deploy is broken even
though `services replace` reported success.

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
