# syntax=docker/dockerfile:1.6
#
# Multi-stage Dockerfile for clawdog-calculator-api (Phase 3a Egress Interface).
#
# Stage 1 (builder)  — install Python deps into a venv.
# Stage 2 (runtime)  — slim Python image + locale-gen en_AU.UTF-8 (Standing
#                      Rule #4 immutable) + the venv copied from the builder.
#
# Build:
#   docker build -t clawdog-calculator-api:dev .
# Run:
#   docker run --rm -p 8000:8000 \
#       -e FBT_PROLOG_URL=http://host.docker.internal:8081 \
#       clawdog-calculator-api:dev
#
# The `make build` and `make deploy` targets in the Makefile drive the
# canonical build path Andrew runs locally; subagents do NOT execute
# docker commands (Phase 3a brief constraint).

ARG PYTHON_VERSION=3.12

# -----------------------------------------------------------------------------
# Stage 1 — builder
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY api ./api

RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install .

# -----------------------------------------------------------------------------
# Stage 2 — runtime
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    LANG=en_AU.UTF-8 \
    LC_ALL=en_AU.UTF-8

# Standing Rule #4: locale-gen en_AU.UTF-8 in the runtime image. The Fano
# operational baseline that every LodgeiT-labs Cloud Run service inherits.
RUN apt-get update \
 && apt-get install -y --no-install-recommends locales tini ca-certificates \
 && sed -i -e 's/# *en_AU.UTF-8 UTF-8/en_AU.UTF-8 UTF-8/' /etc/locale.gen \
 && locale-gen en_AU.UTF-8 \
 && update-locale LANG=en_AU.UTF-8 LC_ALL=en_AU.UTF-8 \
 && rm -rf /var/lib/apt/lists/*

# Non-root runtime user.
RUN useradd --create-home --uid 1000 clawdog
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=clawdog:clawdog api ./api
COPY --chown=clawdog:clawdog openapi.json ./openapi.json
COPY --chown=clawdog:clawdog README.md Licence.txt ./

USER clawdog

EXPOSE 8000

# Liveness probe — does NOT call into the upstream Prolog engine deliberately
# (the REST liveness signal is decoupled from engine readiness).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status == 200 else 1)"

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
