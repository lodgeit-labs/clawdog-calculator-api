# Makefile for clawdog-calculator-api (Phase 3a Egress Interface).
#
# Targets that subagents MAY run (pure read / static-import operations):
#   make openapi          regenerate openapi.json from the live FastAPI app
#   make ruff             lint
#   make audit            run scripts/audit_content_hashes.py against vendored
#                         rate-table fixtures (read-only)
#   make install-hooks    symlink scripts/hooks/pre-push into .git/hooks/
#                         (DISCIPLINE FROM COMMIT ZERO — Lesson #39)
#
# Targets Andrew runs LOCALLY (subagents do NOT execute these — Phase 3a
# brief constraint; CI runs the test gates against the FastAPI app directly):
#   make test             pytest tests/  (also runs in CI)
#   make run              docker-compose up
#   make build            docker build
#   make deploy           gcloud run deploy ... (australia-southeast1)
#
# Standing Rule #4: Cloud Run lives in australia-southeast1; no training in Cloud Run.

# Environment-agnostic tool paths.
#
# Local-dev convenience: defaults assume a `.venv/` next to the Makefile,
# matching `make install` semantics.
#
# CI override: `actions/setup-python@v5` installs Python globally without
# creating `.venv/`. CI invokes targets with `PY=python PIP=pip PYTEST=pytest
# RUFF=ruff` (or via the env block) to point at the global binaries.
#
# `?=` makes each variable overridable from the environment / make CLI;
# `:=` would have hard-coded the venv path and broken portability.

PYTHON ?= python3
VENV   ?= .venv
PIP    ?= $(VENV)/bin/pip
PY     ?= $(VENV)/bin/python
PYTEST ?= $(VENV)/bin/pytest
RUFF   ?= $(VENV)/bin/ruff

# mc18-2026-05-25: project name corrected to match cloud-run.yaml + actual
# GCP project (the cloud-run.yaml was fixed in mc13/PR #8; this Makefile
# variable was missed in that pass). The wrong value caused `make deploy`
# to fail with a project-not-found error.
GCP_PROJECT ?= lodgeit-calc-constellation
GCP_REGION  ?= australia-southeast1
SERVICE     ?= fbt-calculator-api

.PHONY: help venv install test test-binary-gates ruff openapi openapi-check \
        run build deploy audit install-hooks clean

help:
	@echo "clawdog-calculator-api — Phase 3a Egress Interface"
	@echo ""
	@echo "Author-side (subagent-safe):"
	@echo "  make install-hooks   install scripts/hooks/pre-push (Standing Rule #1)"
	@echo "  make openapi         regenerate openapi.json"
	@echo "  make openapi-check   assert committed openapi.json matches the live app"
	@echo "  make ruff            lint"
	@echo "  make audit           audit vendored rate-table fixtures"
	@echo ""
	@echo "Andrew-side (local execution; subagents do NOT run these):"
	@echo "  make test            pytest tests/  (4 binary-failure gates)"
	@echo "  make run             docker-compose up"
	@echo "  make build           docker build"
	@echo "  make deploy          gcloud run deploy --region $(GCP_REGION)"

venv:
	@if [ ! -x "$(PY)" ]; then $(PYTHON) -m venv $(VENV); fi

install: venv
	$(PIP) install -e ".[dev]"

# `make test` runs the four binary-failure gates in CI (and locally for Andrew):
#   1. test_manifest_fidelity     — byte-content hash discipline (Lesson #38)
#   2. test_advisory_boundary     — every endpoint has the advisory block
#   3. test_phase3a_e2e           — PR-D Case 5 production-surface contract
#   4. test_openapi_drift         — committed spec vs live-generated
test:
	$(PYTEST) tests/

# Convenience target for "list which gates exist."
test-binary-gates:
	$(PYTEST) --collect-only -q tests/test_manifest_fidelity.py \
	                            tests/test_advisory_boundary.py \
	                            tests/test_phase3a_e2e.py \
	                            tests/test_openapi_drift.py \
	                            tests/test_production_bundle.py

ruff:
	$(RUFF) check api tests

# `make openapi` is a STATIC IMPORT operation — it imports the FastAPI app
# in-process and serialises app.openapi(). No server is started. Subagents
# MAY run this target; CI runs it as part of the drift-gate.
openapi:
	$(PY) -c "import json; from api.main import app; \
data = json.dumps(app.openapi(), indent=2, sort_keys=True) + '\n'; \
open('openapi.json', 'w').write(data)"
	@echo "openapi.json regenerated."

openapi-check:
	$(PY) -c "import json; from api.main import app; \
import sys, pathlib; \
generated = json.dumps(app.openapi(), indent=2, sort_keys=True) + '\n'; \
committed = pathlib.Path('openapi.json').read_text(); \
sys.exit(0 if generated == committed else (print('OpenAPI drift; run make openapi'), 1)[1])"

# `make audit` runs the Brain-side canonical hash audit against the vendored
# rate-table fixtures. Read-only; subagent-safe. Requires CLAWDOG_BRAIN_ROOT
# to point at a clawdog-brain checkout.
audit:
	@if [ -z "$$CLAWDOG_BRAIN_ROOT" ]; then \
		echo "CLAWDOG_BRAIN_ROOT not set; pointing at the workspace default."; \
		export CLAWDOG_BRAIN_ROOT=$$HOME/.openclaw/workspace; \
	fi; \
	$(PYTHON) "$$CLAWDOG_BRAIN_ROOT/scripts/audit_content_hashes.py" --check --quiet \
	    tests/fixtures/sbrm_rate_table_fy2026/*.md

# Andrew runs this. Subagents do NOT.
run:
	docker-compose up --build

# Andrew runs this. Subagents do NOT.
build:
	docker build -t clawdog-calculator-api:dev .

# Andrew runs this. Subagents do NOT.
deploy:
	gcloud run deploy $(SERVICE) \
	    --source . \
	    --region $(GCP_REGION) \
	    --project $(GCP_PROJECT) \
	    --platform managed \
	    --allow-unauthenticated

# Standing Rule #1 mechanical enforcement (Lesson #39 — DISCIPLINE FROM COMMIT
# ZERO). Symlink the pre-push hook into .git/hooks/ so any push to
# refs/heads/master or refs/heads/main halts with a loud, named violation.
install-hooks:
	@if [ ! -d .git ]; then \
		echo "not a git working tree; nothing to install."; exit 1; \
	fi
	@mkdir -p .git/hooks
	@ln -sf ../../scripts/hooks/pre-push .git/hooks/pre-push
	@chmod +x scripts/hooks/pre-push
	@echo "✓ pre-push hook installed."
	@echo "  Standing Rule #1 is now mechanically enforced: pushes to master/main"
	@echo "  will halt. Bypass with 'git push --no-verify' (deliberate-override only)."

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache **/__pycache__ \
	       *.egg-info build dist
