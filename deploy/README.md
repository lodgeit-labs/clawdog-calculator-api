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
