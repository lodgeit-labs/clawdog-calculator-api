"""clawdog-calculator-api — Phase 3a Egress Interface over the LodgeiT calculator pool.

Architectural canon: CLAWDOG/109 §3 (tri-surface exposure model) — this package
implements the **REST surface**. Authoring boundary: CLAWDOG/110 (the standalone
outsource-boundary discipline) governs every change here even when the change is
in-house — the binary-failure gates (manifest-fidelity, advisory-boundary,
atom-vs-bridge, OpenAPI drift, Standing Rule #1) are non-negotiable.

This package contains NO inlined statutory constants (Standing Rule #6 +
CLAWDOG/110 §5). Every period-varying number flows from the upstream
SBRM_RATE_TABLE/<calc>/<period>/ fact-nodes consumed by the Prolog engine.
"""

__version__ = "0.1.0a0"
