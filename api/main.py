"""FastAPI application entrypoint — Phase 3a Cut A.

Mounts the calculator and rate routers and exposes a ``/healthz`` endpoint
for the Cloud Run / Docker HEALTHCHECK probe.
"""
from __future__ import annotations

from fastapi import FastAPI

from api import __version__
from api.routes import calculators as calculators_routes
from api.routes import rates as rates_routes

app = FastAPI(
    title="ClawDog Calculator-Constellation REST API",
    version=__version__,
    summary=(
        "Phase 3a Egress Interface over the LodgeiT calculator pool. Implements "
        "the REST surface of CLAWDOG/109's tri-surface exposure model. Governed "
        "by CLAWDOG/110's five non-negotiables (manifest-fidelity, advisory-"
        "boundary, atom-vs-bridge, OpenAPI drift, Standing Rule #1)."
    ),
    description=(
        "**Architectural canon:** [CLAWDOG/109]"
        "(https://github.com/futureWA/clawdog-brain/blob/master/GLOBAL_NOTES/CLAWDOG/109_CALCULATOR_CONSTELLATION.md)\n\n"
        "**Outsource-boundary canon:** [CLAWDOG/110]"
        "(https://github.com/futureWA/clawdog-brain/blob/master/GLOBAL_NOTES/CLAWDOG/110_OUTSOURCE_BOUNDARY_DISCIPLINE.md)\n\n"
        "Phase 3a wires a single calculator (FBT Car Operating Cost). Phase 3c "
        "is the second-instance test of whether the abstraction holds."
    ),
    contact={
        "name": "LodgeiT Labs",
        "url": "https://lodgeit.org",
    },
    license_info={"name": "MIT"},
    openapi_tags=[
        {
            "name": "calculators",
            "description": "Calculator invocation + discovery (CLAWDOG/109 §3, §4).",
        },
        {
            "name": "rates",
            "description": "Rate-table provenance surface (CLAWDOG/109 §7).",
        },
        {
            "name": "system",
            "description": "Liveness / readiness probes.",
        },
    ],
)

app.include_router(calculators_routes.router)
app.include_router(rates_routes.router)


@app.get("/healthz", tags=["system"], summary="Liveness probe.")
def healthz() -> dict[str, str]:
    """Return a minimal liveness response for the Cloud Run / Docker HEALTHCHECK.

    Does NOT call into the upstream Prolog engine — that would couple the
    REST liveness signal to the engine's readiness, which is a deliberately
    independent dimension.
    """
    return {"status": "ok", "service": "clawdog-calculator-api", "version": __version__}


__all__ = ["app"]
