"""Registry ↔ module-metadata parity + /v1/modules + ?module= filter + label hygiene.

Covers mut-2026-09-19 (registry module metadata, /v1/modules, label clean).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.lib.calculator_metadata import (
    CalculatorMetadataError,
    _module_uri_for,
    calculators_by_uri,
    load_metadata,
    merge_into_registry,
)
from api.main import app
from api.routes.calculators import _CALCULATOR_METADATA, _CALCULATOR_REGISTRY

client = TestClient(app)

_METADATA = load_metadata()
_META_BY_URI = calculators_by_uri(_METADATA)
_MERGED_KEYS = ("label", "module", "benefit_type", "statutes", "selection", "description")
_LABEL_BANNED = ("OT #", "row", "sheet", "thesis")


# --- metadata ↔ registry parity ---------------------------------------------

def test_every_registry_urn_present_in_metadata():
    missing = set(_CALCULATOR_REGISTRY) - set(_META_BY_URI)
    assert not missing, f"registry URNs missing from metadata: {sorted(missing)}"


def test_every_metadata_urn_present_in_registry():
    missing = set(_META_BY_URI) - set(_CALCULATOR_REGISTRY)
    assert not missing, f"metadata URNs missing from registry: {sorted(missing)}"


def test_module_equals_second_last_segment_derivation():
    for calc_uri, meta in _META_BY_URI.items():
        assert meta["module"] == _module_uri_for(calc_uri), (
            f"{calc_uri}: module {meta['module']!r} != derived "
            f"{_module_uri_for(calc_uri)!r}"
        )


def test_registry_entries_carry_merged_fields_verbatim():
    for calc_uri, entry in _CALCULATOR_REGISTRY.items():
        meta = _META_BY_URI[calc_uri]
        for key in _MERGED_KEYS:
            assert entry[key] == meta[key], f"{calc_uri}.{key} not verbatim from metadata"


def test_merge_fails_on_registry_urn_missing_from_metadata():
    registry = {"urn:sbrm:calculator:fbt:phantom": {"label": "x"}}
    with pytest.raises(CalculatorMetadataError, match="registry URNs missing"):
        merge_into_registry(registry, _METADATA)


def test_merge_fails_on_metadata_urn_missing_from_registry():
    # A registry with only ONE real entry; every other metadata URN is missing.
    one = next(iter(_META_BY_URI))
    registry = {one: {}}
    with pytest.raises(CalculatorMetadataError, match="metadata URNs missing"):
        merge_into_registry(registry, _METADATA)


def test_merge_fails_on_module_mismatch():
    calc_uri = "urn:sbrm:calculator:fbt:debt-waiver"
    bad_meta = {
        "_meta": _METADATA["_meta"],
        "modules": _METADATA["modules"],
        "calculators": [
            {**c, "module": "urn:sbrm:module:WRONG"} if c["calc_uri"] == calc_uri else c
            for c in _METADATA["calculators"]
        ],
    }
    registry = {c: {} for c in _META_BY_URI}
    with pytest.raises(CalculatorMetadataError, match="does not"):
        merge_into_registry(registry, bad_meta)


# --- GET /v1/modules shape ---------------------------------------------------

def test_modules_listing_shape():
    r = client.get("/v1/modules")
    assert r.status_code == 200
    body = r.json()
    meta_modules = {m["module_uri"] for m in _CALCULATOR_METADATA["modules"]}
    assert {m["module_uri"] for m in body} == meta_modules
    for m in body:
        for field in (
            "module_uri", "label", "jurisdiction", "statutes", "period_family",
            "description", "resolution_order", "election_groups", "calculators",
        ):
            assert field in m, f"module {m.get('module_uri')} missing {field}"


def test_modules_calculators_in_registry_order():
    r = client.get("/v1/modules")
    body = {m["module_uri"]: m for m in r.json()}
    # Registry-order projection per module.
    expected: dict[str, list[str]] = {}
    for calc_uri, meta in _CALCULATOR_REGISTRY.items():
        expected.setdefault(meta["module"], []).append(calc_uri)
    for module_uri, calcs in expected.items():
        assert body[module_uri]["calculators"] == calcs


def test_modules_fields_verbatim_from_metadata():
    r = client.get("/v1/modules")
    body = {m["module_uri"]: m for m in r.json()}
    for meta_module in _CALCULATOR_METADATA["modules"]:
        got = body[meta_module["module_uri"]]
        for field in (
            "label", "jurisdiction", "statutes", "period_family",
            "description", "resolution_order", "election_groups",
        ):
            assert got[field] == meta_module[field], f"{field} not verbatim"


# --- ?module= filter + 404 ---------------------------------------------------

def test_calculators_module_filter():
    r = client.get("/v1/calculators", params={"module": "urn:sbrm:module:div7a"})
    assert r.status_code == 200
    body = r.json()
    assert body, "filter returned no calculators"
    assert all(c["module"] == "urn:sbrm:module:div7a" for c in body)


def test_calculators_module_filter_all_modules_partition():
    r_all = client.get("/v1/calculators")
    total = len(r_all.json())
    seen = 0
    for m in _CALCULATOR_METADATA["modules"]:
        r = client.get("/v1/calculators", params={"module": m["module_uri"]})
        assert r.status_code == 200
        seen += len(r.json())
    assert seen == total, "module filters do not partition the full listing"


def test_calculators_unknown_module_404_names_known():
    r = client.get("/v1/calculators", params={"module": "urn:sbrm:module:bogus"})
    assert r.status_code == 404
    detail = r.json()["detail"]
    for m in _CALCULATOR_METADATA["modules"]:
        assert m["module_uri"] in detail, f"{m['module_uri']} not named in 404 detail"


# --- label hygiene -----------------------------------------------------------

def test_every_label_free_of_banned_tokens():
    for calc_uri, entry in _CALCULATOR_REGISTRY.items():
        label = entry["label"]
        for banned in _LABEL_BANNED:
            assert banned not in label, (
                f"{calc_uri} label {label!r} contains banned token {banned!r}"
            )


def test_module_labels_free_of_banned_tokens():
    for m in _CALCULATOR_METADATA["modules"]:
        for banned in _LABEL_BANNED:
            assert banned not in m["label"], (
                f"module {m['module_uri']} label contains {banned!r}"
            )


# --- MCP tools/list carries the new fields ----------------------------------

def test_mcp_tools_list_carries_module_metadata():
    from api.services.mcp_tool_registry import list_tools

    tools = list_tools()
    by_uri = {t["_calc_uri"]: t for t in tools}
    for calc_uri, meta in _CALCULATOR_REGISTRY.items():
        tool = by_uri[calc_uri]
        assert tool["_module"] == meta["module"]
        assert tool["_benefit_type"] == meta["benefit_type"]
        assert tool["_statutes"] == meta["statutes"]
        assert tool["_selection"] == meta["selection"]
        assert tool["_description"] == meta["description"]
