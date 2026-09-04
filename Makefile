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
        run build deploy audit install-hooks clean gates

help:
	@echo "clawdog-calculator-api — Phase 3a Egress Interface"
	@echo ""
	@echo "Author-side (subagent-safe):"
	@echo "  make install-hooks   install scripts/hooks/pre-push (Standing Rule #1)"
	@echo "  make openapi         regenerate openapi.json"
	@echo "  make openapi-check   assert committed openapi.json matches the live app"
	@echo "  make ruff            lint"
	@echo "  make gates           run the FULL CI gate sequence locally"
	@echo "                       (Fable mc00-2026-09-04 05:34 UTC discipline)"
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

# `make gates` mirrors CI's binary-failure-gate job EXACTLY, in order, so a
# local green is a valid predictor of a CI green.
#
# **`make gates` is a feedback-loop shortener, NOT the enforcement.**
# The enforcement is CI + branch-protection required-status-checks on the
# target branch. This target closes the specific gap of author forgetting
# to run a CI step before push; it does not (and cannot) prevent a merge
# of a red PR. See scripts/hooks/pre-push Layer 3 for the scoping.
#
# Fable mc00-2026-09-04 05:34 UTC ruling (verbatim):
#   "A pre-push habit that depends on remembering is not a gate. Put the
#   lint + mechanical-gate job in a single make gates target and run it
#   before every push — or better, make the push itself run it."
#
# CI job source: .github/workflows/ci.yml `lint-and-test`. Steps 6-10 are
# what fails a CI run; steps 1-5 are runner setup. The five gates below
# are the wire-truth-equivalent locally:
#   1. ruff check api tests                     (CI step 6)
#   2. python scripts/check_deploy_placeholders (CI step 7)
#   3. make openapi-check                       (CI step 8)
#   4. pytest tests/                            (CI step 9)
#   5. collected-count floor >= FLOOR           (CI step 10)
#
# Wired into scripts/hooks/pre-push — running `git push` on a clawdog/*
# branch fires `make gates` first. Bypass via `git push --no-verify` for
# emergency pushes (auditable via shell history).
#
# GATES_FLOOR mirrors the CI floor; bump both together whenever the suite
# grows by >=15 tests.
GATES_FLOOR ?= 230

gates:
	@echo "===== gate 0/5: ruff version pin parity ====="
	@# Fable mc00-2026-09-04 05:41 UTC item 3: pin parity check. The
	@# pyproject.toml carries `ruff==X.Y.Z` (exact pin). This step reads
	@# the pin + verifies the invoked ruff binary reports the same
	@# version. If the binary drifts (venv stale; global-vs-venv confusion;
	@# ruff upgraded in one place not the other), `make gates` fails HERE
	@# rather than surfacing later as a green-hook / red-CI mismatch.
	@# CI mirrors this check via the same target when it runs `make gates`
	@# in future; today CI installs ruff via `pip install -e .[dev]` which
	@# honours the pin. Either surface flags a drift immediately.
	@PINNED=$$(grep -oE '"ruff==[0-9]+\.[0-9]+\.[0-9]+"' pyproject.toml | head -1 | tr -d '"' | sed 's/ruff==//'); \
	 if [ -z "$$PINNED" ]; then \
	   echo "FAIL: could not read ruff pin from pyproject.toml (expected \"ruff==X.Y.Z\")"; \
	   exit 1; \
	 fi; \
	 ACTUAL=$$($(RUFF) --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1); \
	 echo "pinned=$$PINNED  actual=$$ACTUAL"; \
	 if [ "$$PINNED" != "$$ACTUAL" ]; then \
	   echo "FAIL: ruff pin drift. pyproject.toml pins $$PINNED but $(RUFF) reports $$ACTUAL."; \
	   echo "      Fix: rm -rf .venv && make install"; \
	   exit 1; \
	 fi
	@echo "===== gate 1/5: ruff check api tests ====="
	$(RUFF) check api tests
	@echo "===== gate 2/5: scripts/check_deploy_placeholders ====="
	$(PY) scripts/check_deploy_placeholders.py
	@echo "===== gate 3/5: openapi-check (drift gate) ====="
	$(MAKE) openapi-check
	@echo "===== gate 4/5: pytest tests/ ====="
	$(PYTEST) tests/
	@echo "===== gate 5/5: collected-count floor (>= $(GATES_FLOOR)) ====="
	@COLLECTED=$$($(PYTEST) --collect-only 2>&1 | grep -oE '^[0-9]+ tests? collected' | grep -oE '^[0-9]+' | head -1); \
	 COLLECTED=$${COLLECTED:-0}; \
	 echo "collected=$$COLLECTED floor=$(GATES_FLOOR)"; \
	 if [ "$$COLLECTED" -lt "$(GATES_FLOOR)" ]; then \
	   echo "FAIL: pytest collected only $$COLLECTED tests; floor is $(GATES_FLOOR)."; \
	   echo "      Either the suite shrank or venv is stale. Fable mc19 gate."; \
	   exit 1; \
	 fi
	@echo "===== all 5 gates green ====="

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

# `make smoke-prod` — Option-C PR β binary-failure gate (mut-2026-05-28-mc07).
#
# Lifts the mc18-2026-05-25 README's behavioural-recall post-deploy checklist
# to a Lesson #35 mechanical gate. Fires 5 wire-probes against the deployed
# Cloud Run service URL; exits with Standing Rule #8 tri-state contract:
#
#   exit 0  \U0001f7e2 GREEN          — all 5 checks pass
#   exit 1  \U0001f534 LOGIC DRIFT    — deploy is broken or production drifted
#   exit 2  \U0001f7e1 INFRA BROKEN   — curl/python3 missing or DNS unreachable
#
# Subagents MAY run this target — it is pure read against the deployed URL,
# no mutation, no secrets required. CI runs it post-deploy via
# .github/workflows/smoke-prod.yml.
#
# Override the target URL via env var:
#   make smoke-prod API_BASE_URL=https://...
#
# Sidecar fixtures at tests/sidecars/ are the byte-content reference for
# the load-bearing assertions (Lesson #38 honour).
smoke-prod:
	@./scripts/smoke_prod.sh

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache **/__pycache__ \
	       *.egg-info build dist
