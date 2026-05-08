"""OpenAPI drift binary-failure gate (CLAWDOG/110 §3.4 Non-Negotiable #4).

The committed ``openapi.json`` MUST be byte-identical to the spec the FastAPI
app generates from the live implementation.

Lesson #35 anchor — recall rules drift; binary-failure rules don't. This test
makes spec-vs-code drift mechanical: the build fails on any divergence.

Regenerate with ``make openapi`` and commit the result whenever the API
surface changes.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMITTED_SPEC = REPO_ROOT / "openapi.json"


def _normalise(spec: dict) -> str:
    """Produce a stable JSON string for byte-diff comparison.

    ``sort_keys=True`` + 2-space indent + a trailing newline matches the
    ``make openapi`` target convention. Both sides go through the same path
    so a key-ordering wobble (which has bitten openapi-drift tests in the
    past) cannot produce a false positive.
    """
    return json.dumps(spec, indent=2, sort_keys=True) + "\n"


def test_openapi_committed_matches_generated() -> None:
    from api.main import app  # noqa: WPS433

    generated = _normalise(app.openapi())
    if not COMMITTED_SPEC.exists():
        raise AssertionError(
            f"openapi.json missing at {COMMITTED_SPEC}. "
            "Run `make openapi` and commit the result."
        )
    committed = COMMITTED_SPEC.read_text(encoding="utf-8")
    if generated != committed:
        # Surface the first divergence line for fast triage.
        gen_lines = generated.splitlines()
        com_lines = committed.splitlines()
        first_diff = next(
            (
                f"line {i + 1}: committed={c!r} generated={g!r}"
                for i, (c, g) in enumerate(zip(com_lines, gen_lines, strict=False))
                if c != g
            ),
            f"committed has {len(com_lines)} lines; generated has {len(gen_lines)} lines",
        )
        raise AssertionError(
            "OpenAPI spec drift detected. Run `make openapi` and commit the "
            f"regenerated openapi.json. First divergence: {first_diff}"
        )


def test_openapi_committed_is_well_formed_json() -> None:
    """Sanity: the committed artefact must parse as JSON."""
    if not COMMITTED_SPEC.exists():
        raise AssertionError("openapi.json missing; run `make openapi`.")
    json.loads(COMMITTED_SPEC.read_text(encoding="utf-8"))
