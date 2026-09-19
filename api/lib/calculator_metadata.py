"""Calculator module/registry metadata loader (mut-2026-09-19).

Loads ``api/data/calculator_metadata.json`` — the Fable-authored authoritative
source for the ``label``, ``module``, ``benefit_type``, ``statutes``,
``selection`` and ``description`` fields of ``_CALCULATOR_REGISTRY`` and for
the ``GET /v1/modules`` surface.

Strings are copied verbatim from the JSON; this module never paraphrases,
extends or corrects the tax content. The JSON is the single source of truth.

Import-time invariants (build fails on violation, per the dispatch):
    1. every registry URN is present in the metadata;
    2. every metadata calculator URN is present in the registry;
    3. for each calculator, ``module == "urn:sbrm:module:" + <second-last
       segment of the calc URN>``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_METADATA_PATH = Path(__file__).resolve().parent.parent / "data" / "calculator_metadata.json"

# Keys copied verbatim from each metadata calculator entry into the registry.
_MERGED_CALCULATOR_KEYS = (
    "label",
    "module",
    "benefit_type",
    "statutes",
    "selection",
    "description",
)


class CalculatorMetadataError(RuntimeError):
    """Raised at import time when metadata and registry disagree."""


def _module_uri_for(calc_uri: str) -> str:
    """Derive the module URN from a calculator URN's second-last segment.

    ``urn:sbrm:calculator:fbt:car-operating-cost`` -> ``urn:sbrm:module:fbt``.
    ``urn:sbrm:calculator:div7a:at`` -> ``urn:sbrm:module:div7a``.
    """
    segments = calc_uri.split(":")
    if len(segments) < 2:
        raise CalculatorMetadataError(
            f"calc_uri={calc_uri!r} has too few ':' segments to derive a module."
        )
    return "urn:sbrm:module:" + segments[-2]


def load_metadata() -> dict[str, Any]:
    """Load and return the parsed metadata document."""
    with _METADATA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def calculators_by_uri(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index the metadata ``calculators`` list by ``calc_uri``."""
    out: dict[str, dict[str, Any]] = {}
    for entry in metadata["calculators"]:
        out[entry["calc_uri"]] = entry
    return out


def modules(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the metadata ``modules`` list (verbatim)."""
    return metadata["modules"]


def merge_into_registry(
    registry: dict[str, dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Merge metadata fields into ``registry`` in place, enforcing the invariants.

    For each registry entry keyed by ``calc_uri`` the metadata ``label``
    replaces the registry ``label`` and ``module``, ``benefit_type``,
    ``statutes``, ``selection`` and ``description`` are added, all verbatim.

    Raises :class:`CalculatorMetadataError` if any invariant fails.
    """
    if metadata is None:
        metadata = load_metadata()

    meta_by_uri = calculators_by_uri(metadata)

    registry_uris = set(registry)
    metadata_uris = set(meta_by_uri)

    missing_from_metadata = registry_uris - metadata_uris
    if missing_from_metadata:
        raise CalculatorMetadataError(
            "registry URNs missing from calculator_metadata.json: "
            + ", ".join(sorted(missing_from_metadata))
        )

    missing_from_registry = metadata_uris - registry_uris
    if missing_from_registry:
        raise CalculatorMetadataError(
            "metadata URNs missing from _CALCULATOR_REGISTRY: "
            + ", ".join(sorted(missing_from_registry))
        )

    for calc_uri, meta in meta_by_uri.items():
        expected_module = _module_uri_for(calc_uri)
        if meta["module"] != expected_module:
            raise CalculatorMetadataError(
                f"metadata module {meta['module']!r} for {calc_uri!r} does not "
                f"equal the URN-derived module {expected_module!r}."
            )
        entry = registry[calc_uri]
        for key in _MERGED_CALCULATOR_KEYS:
            entry[key] = meta[key]

    return registry
