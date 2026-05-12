"""Rate-table filesystem resolver.

Phase 3c.2 (`mut-2026-05-12-mc16`) introduced the **taxonomy axis** between
`<calc>` and `<period>` in the SBRM_RATE_TABLE/ tree per
`clawdog-brain/GLOBAL_NOTES/CLAWDOG/111_TAXONOMY_AXIS.md`. The path now reads:

    SBRM_RATE_TABLE/<calc>/<taxonomy>/<period_id>/<rate_id>.md

This module is the canonical resolver shared by:
- `api.routes.calculators._rate_table_root_for`
- `api.routes.rates._rate_table_root_for`

Pre-mc16 the resolver took only `(period_uri,)` and resolved against
`SBRM_RATE_TABLE/<calc>/<period_id>/`. The new resolver accepts an optional
`taxonomy` argument; if omitted, it defaults to `lodgeit_au_sbrm` (the only
bundle populated at Phase 3c.2 — the ratified set is
`[lodgeit_au_sbrm, hoffman_base]` per CLAWDOG/111 §2, with `hoffman_base`
populating at Phase 3c.3 Depreciation_Transforms onboarding).

The default value is deliberate per Lesson #31 (minimal scope): at Phase 3c.2
only one bundle is populated, so the default is deterministic. When
`hoffman_base` populates at Phase 3c.3, the request-side discipline tightens
per CLAWDOG/111 NN#4 (no silent fallback at the discovery layer); but
existing FBT clients invoking against `lodgeit_au_sbrm` continue to work
without breaking the API contract.

Resolution precedence:
    1. If ``CLAWDOG_RATE_TABLE_ROOT`` env-var is set, return it directly
       (hermetic test-fixture override; the test fixture vendors a pinned
       snapshot AT the leaf path, so it already encodes taxonomy implicitly).
       This override is preserved for backward-compat with the hermetic test
       suite (test_phase3a_e2e.py); the production-bundle suite
       (test_production_bundle.py) deliberately does NOT use it.
    2. Otherwise, resolve relative to ``$LODGEIT_FBT_REPO`` /
       ``SBRM_RATE_TABLE/<calc>/<taxonomy>/<period_id>/``.

Per CLAWDOG/111 NN#1: the `taxonomy` parameter is a BARE ATOM (not a
compound URN); legal values are members of the ratified taxonomy set.
"""
from __future__ import annotations

import os
from pathlib import Path

# Ratified taxonomy set per CLAWDOG/111 §2 (PR #164 mut-2026-05-11-mc14).
# Adding a new entry is a Brain-canon mutation, not a runtime registration
# (Standing Rule #3 / closed-under-ratification).
RATIFIED_TAXONOMIES: frozenset[str] = frozenset({"lodgeit_au_sbrm", "hoffman_base"})

# Default at Phase 3c.2. Tightens at Phase 3c.3 when `hoffman_base` bundle
# actually populates and the strict-required-no-default rule fires.
DEFAULT_TAXONOMY: str = "lodgeit_au_sbrm"


def rate_table_root_for(period_uri: str, taxonomy: str = DEFAULT_TAXONOMY) -> Path:
    """Resolve the on-disk rate-table root for a (period, taxonomy) tuple.

    Args:
        period_uri: e.g. ``urn:sbrm:period:fbt:fy2026``. The 4th and 5th
            colon-separated segments are ``<calc>`` and ``<period_id>``.
        taxonomy: bare atom from the ratified set. Defaults to
            ``lodgeit_au_sbrm`` at Phase 3c.2.

    Returns:
        Filesystem path to ``<root>/SBRM_RATE_TABLE/<calc>/<taxonomy>/<period_id>``.

    Raises:
        ValueError: if ``taxonomy`` is not in the ratified set (CLAWDOG/111 NN#1).
    """
    if taxonomy not in RATIFIED_TAXONOMIES:
        raise ValueError(
            f"taxonomy={taxonomy!r} is not in the ratified set "
            f"{sorted(RATIFIED_TAXONOMIES)}. Adding a new taxonomy is a "
            f"Brain-canon mutation per CLAWDOG/111 §2, not a runtime registration."
        )

    override = os.environ.get("CLAWDOG_RATE_TABLE_ROOT")
    if override:
        # Hermetic test-fixture path: caller already knows the leaf layout.
        # The taxonomy parameter is accepted but does not affect path here.
        return Path(override)

    fbt_repo = os.environ.get("LODGEIT_FBT_REPO", "/srv/lodgeit_fbt")
    # period_uri shape: urn:sbrm:period:<calc>:<period_id>
    parts = period_uri.split(":")
    calc, period_id = parts[3], parts[4]
    return Path(fbt_repo) / "SBRM_RATE_TABLE" / calc / taxonomy / period_id


__all__ = [
    "DEFAULT_TAXONOMY",
    "RATIFIED_TAXONOMIES",
    "rate_table_root_for",
]
