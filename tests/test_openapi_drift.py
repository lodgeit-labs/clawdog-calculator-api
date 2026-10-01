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
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMITTED_SPEC = REPO_ROOT / "openapi.json"

# D64 (Fable [CALC] 2026-10-01): published text carries no internal references.
# D61 (B) stripped implementation names from descriptions by hand (63 -> 0) but
# added no content guard, so 13 references survived the D61 merge and more could
# be reintroduced silently. These four patterns are the content hygiene check;
# the drift gate above only proves committed == generated (byte-equality), which
# cannot catch a reference that exists identically in both the code and the
# spec. Scanned against every string value in openapi.json AND every MCP tool
# object (descriptions + inputSchema), which mirror the same source docstrings.
_INTERNAL_REF_PATTERNS = {
    "file_path": re.compile(r"api/[\w/]+\.(py|json)"),
    "private_id": re.compile(r"\b_[A-Z][A-Z0-9_]+\b"),
    "prolog": re.compile(r"Prolog"),
    "dot_py": re.compile(r"\.py\b"),
}

# The ONLY allowed exception: callers need this env-var name to authenticate, so
# it is a functional part of the contract, not a provenance leak (D61 rider).
_ALLOWED_TOKEN = "CLAWDOG_ENGINE_AUTH_PROBE_TOKEN"

# Structural invariant guarded alongside the text change: D64 is text-only, so
# the x-money field count must stay exactly where D65 left it.
_EXPECTED_X_MONEY_COUNT = 75


def _scan_string_for_internal_refs(value: str) -> list[tuple[str, str]]:
    """Return (pattern_name, match) for each internal reference in ``value``.

    The allowed env-var token is removed before scanning so that, and only
    that, is exempt from every pattern.
    """
    scrubbed = value.replace(_ALLOWED_TOKEN, "")
    hits: list[tuple[str, str]] = []
    for name, rx in _INTERNAL_REF_PATTERNS.items():
        for m in rx.finditer(scrubbed):
            hits.append((name, m.group(0)))
    return hits


def _walk_strings(node: object, path: str):
    """Yield (json_path, string_value) for every string leaf in ``node``."""
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, val in node.items():
            yield from _walk_strings(val, f"{path}.{key}")
    elif isinstance(node, list):
        for i, val in enumerate(node):
            yield from _walk_strings(val, f"{path}[{i}]")


def _count_x_money_fields(spec: dict) -> int:
    schemas = spec.get("components", {}).get("schemas", {})
    return sum(
        1
        for sch in schemas.values()
        for prop in (sch.get("properties") or {}).values()
        if isinstance(prop, dict) and prop.get("x-money") is True
    )


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


# --- D64 content hygiene: no internal implementation references ---------------


def test_openapi_has_no_internal_implementation_references() -> None:
    """Every string value in openapi.json is free of internal references.

    Scans file paths (``api/...py|json``), private identifiers
    (``_UPPER_SNAKE``), the engine implementation name (``Prolog``) and any
    ``.py`` filename. Only ``CLAWDOG_ENGINE_AUTH_PROBE_TOKEN`` is allowed,
    because callers need that env-var name to authenticate.
    """
    spec = json.loads(COMMITTED_SPEC.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for json_path, value in _walk_strings(spec, "$"):
        for pattern_name, match in _scan_string_for_internal_refs(value):
            offenders.append(
                f"{json_path}: pattern={pattern_name} match={match!r} "
                f"in {value[:120]!r}"
            )
    assert not offenders, (
        "internal implementation references leaked into openapi.json "
        f"(only {_ALLOWED_TOKEN} is allowed):\n" + "\n".join(offenders)
    )


def test_mcp_tool_descriptions_have_no_internal_references() -> None:
    """Every published MCP tool (description + inputSchema) is free of internal
    references, under the same four patterns and the same single allowance.

    The MCP tool objects embed the same source docstrings as openapi.json, so a
    reference stripped from one surface must be stripped from both.
    """
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert resp.status_code == 200, resp.text
    tools = resp.json()["result"]["tools"]
    assert len(tools) == 23, f"expected 23 MCP tools, got {len(tools)}"
    offenders: list[str] = []
    for tool in tools:
        name = tool.get("name", "<unnamed>")
        for json_path, value in _walk_strings(tool, "$"):
            for pattern_name, match in _scan_string_for_internal_refs(value):
                offenders.append(
                    f"tool={name} {json_path}: pattern={pattern_name} "
                    f"match={match!r} in {value[:120]!r}"
                )
    assert not offenders, (
        "internal implementation references leaked into MCP tool descriptions "
        f"(only {_ALLOWED_TOKEN} is allowed):\n" + "\n".join(offenders)
    )


def test_x_money_field_count_unchanged_by_d64() -> None:
    """D64 is text-only: the x-money field count must still be 75 (D65 baseline),
    proving no schema structure changed."""
    spec = json.loads(COMMITTED_SPEC.read_text(encoding="utf-8"))
    count = _count_x_money_fields(spec)
    assert count == _EXPECTED_X_MONEY_COUNT, (
        f"x-money field count={count}; expected {_EXPECTED_X_MONEY_COUNT}. "
        "D64 must not change schema structure."
    )
