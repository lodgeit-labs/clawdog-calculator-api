"""F2-\u03b1 + F2-\u03b2 gateway `AssetCreatedInput` extension binary-failure gates.

RATIFIED mc11-2026-08-31 per `memory/proposals/2026-08-31-depreciation-\
product-scope-RATIFIED.md` \u00a72 Ask 2 (revised at mc12 10:38 UTC to
unconditional per Andrew retraction of the `pool_type` case-6b gating).

The two fields (`dv_rate_factor` + `pool_type`) were previously excluded by
`AssetCreatedInput.model_config = ConfigDict(extra=\"forbid\")` at the
gateway. This exclusion produced two wire-observed defects on the rung 5
verification (2026-08-31 09:46 UTC per streamace-comms outbox):

  * Case 6a (DV WITH `dv_rate_factor`): HTTP 422 `extra_forbidden` on
    `dv_rate_factor`. Diminishing-value method unreachable through the
    gateway with a rate factor.
  * Case 6b (DV WITHOUT `dv_rate_factor`): HTTP 502 `engine_unavailable`
    with the engine's real 422 buried inside `detail.body` as a JSON
    string. Same buried-error class F2-\u03b3 targets.
  * Case 7 (pool_type='sbe_pool'): HTTP 422 `extra_forbidden` on
    `pool_type`. Rider 3 typed-refusal exclusion in the manifest is
    aspirational rather than demonstrable.

F2-\u03b1 lands `dv_rate_factor`; F2-\u03b2 lands `pool_type`. Conditional
validation (when required, when refused) stays at the engine per F13
UPHELD schema-authority; the gateway's job here is to stop forbidding
fields the engine requires.

Binary-failure assertions:

  1. `dv_rate_factor` is accepted by the gateway pydantic layer.
  2. `dv_rate_factor` may be omitted (Optional; engine enforces
     conditional requirement).
  3. `pool_type` is accepted by the gateway pydantic layer.
  4. `pool_type=None` (or field absent) is accepted (Optional).
  5. Any other unknown key is still rejected by extra=\"forbid\" (regression
     guard: the extension MUST NOT open the schema wholesale).
  6. `dv_rate_factor` obeys `gt=0` (positive floor: rate factor is a
     multiplier of 1/life, cannot be zero or negative).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from api.schemas.depreciation import AssetCreatedInput


class TestF2AlphaDvRateFactorAccepted:
    """F2-\u03b1: `dv_rate_factor` extends the gateway schema surface."""

    def test_dv_method_with_dv_rate_factor_accepted(self) -> None:
        """The rung 5 case 6a wire-observed defect (HTTP 422
        `extra_forbidden` on `dv_rate_factor`) is closed: the field is now
        declared and accepted."""
        asset = AssetCreatedInput(
            cost=Decimal("10000.00"),
            acquisition_date=date(2022, 7, 1),
            accounting_useful_life_years=10,
            accounting_method="diminishing_value",
            dv_rate_factor=Decimal("2.0"),
        )
        assert asset.dv_rate_factor == Decimal("2.0")

    def test_dv_rate_factor_optional_at_gateway(self) -> None:
        """Conditional validation (\"required when method='diminishing_value'\")
        stays at the engine per F13 UPHELD. Gateway does not enforce."""
        asset = AssetCreatedInput(
            cost=Decimal("10000.00"),
            acquisition_date=date(2022, 7, 1),
            accounting_useful_life_years=10,
            accounting_method="diminishing_value",
            # dv_rate_factor deliberately omitted; engine will refuse with
            # its own root_validator; gateway forwards verbatim.
        )
        assert asset.dv_rate_factor is None

    def test_dv_rate_factor_positive_floor(self) -> None:
        """SR #3 fail-loud: rate factor is a multiplier of 1/life; zero and
        negative values are meaningless and rejected at the pydantic
        boundary (gateway-side sanity check; the engine also enforces)."""
        with pytest.raises(ValidationError):
            AssetCreatedInput(
                cost=Decimal("10000.00"),
                acquisition_date=date(2022, 7, 1),
                accounting_useful_life_years=10,
                accounting_method="diminishing_value",
                dv_rate_factor=Decimal("0"),
            )
        with pytest.raises(ValidationError):
            AssetCreatedInput(
                cost=Decimal("10000.00"),
                acquisition_date=date(2022, 7, 1),
                accounting_useful_life_years=10,
                accounting_method="diminishing_value",
                dv_rate_factor=Decimal("-1"),
            )

    def test_pc_method_dv_rate_factor_ignored_at_gateway(self) -> None:
        """Under F13 UPHELD schema-authority split, the gateway does not
        enforce \"dv_rate_factor MUST be omitted for prime_cost\"; the engine
        does. Gateway just forwards. This test pins that the gateway
        pydantic layer accepts the field regardless of method; conditional
        rejection is the engine's job."""
        asset = AssetCreatedInput(
            cost=Decimal("10000.00"),
            acquisition_date=date(2022, 7, 1),
            accounting_useful_life_years=10,
            accounting_method="prime_cost",
            dv_rate_factor=Decimal("2.0"),  # gateway accepts; engine may refuse
        )
        assert asset.dv_rate_factor == Decimal("2.0")


class TestF2BetaPoolTypeAccepted:
    """F2-\u03b2: `pool_type` extends the gateway schema surface so the
    engine's rider-3 typed refusal can fire.

    RATIFIED \u00a72 Ask 2 (mc12 10:38 UTC unconditional revision): rider 3
    passthrough is wire-verified at source; the case 7 wire-observed HTTP
    422 `extra_forbidden` result blocks the typed refusal from firing. This
    field is now declared so any pool-typed asset reaches the engine's D2
    fold and returns the `pool_asset_out_of_t6_scope` refusal envelope.
    """

    def test_pool_type_absent_accepted(self) -> None:
        """Single-asset happy path: no `pool_type` in payload. T6 first-cut
        is single-asset by default; the field is Optional."""
        asset = AssetCreatedInput(
            cost=Decimal("5000.00"),
            acquisition_date=date(2022, 7, 1),
            accounting_useful_life_years=5,
            accounting_method="prime_cost",
        )
        assert asset.pool_type is None

    def test_pool_type_null_accepted(self) -> None:
        """Explicit `pool_type: null` is equivalent to absence. Gateway
        accepts."""
        asset = AssetCreatedInput(
            cost=Decimal("5000.00"),
            acquisition_date=date(2022, 7, 1),
            accounting_useful_life_years=5,
            accounting_method="prime_cost",
            pool_type=None,
        )
        assert asset.pool_type is None

    def test_pool_type_string_value_reaches_engine(self) -> None:
        """The whole F2-\u03b2 point: a non-null `pool_type` (e.g. 'sbe_pool',
        'sbe', 'lvp') is accepted by the gateway pydantic layer so the
        payload reaches the engine and the engine's typed refusal fires.
        The gateway does NOT enumerate pool-type values \u2014 F13 UPHELD.
        """
        asset = AssetCreatedInput(
            cost=Decimal("5000.00"),
            acquisition_date=date(2022, 7, 1),
            accounting_useful_life_years=5,
            accounting_method="prime_cost",
            pool_type="sbe_pool",
        )
        assert asset.pool_type == "sbe_pool"

        asset2 = AssetCreatedInput(
            cost=Decimal("5000.00"),
            acquisition_date=date(2022, 7, 1),
            accounting_useful_life_years=5,
            accounting_method="prime_cost",
            pool_type="sbe",
        )
        assert asset2.pool_type == "sbe"


class TestF2ExtraForbidRegression:
    """Regression guard: the F2 extension MUST NOT open the schema
    wholesale. `extra=\"forbid\"` still rejects arbitrary unknown keys.
    Only `dv_rate_factor` and `pool_type` are newly permitted."""

    def test_unknown_field_still_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AssetCreatedInput(
                cost=Decimal("5000.00"),
                acquisition_date=date(2022, 7, 1),
                accounting_useful_life_years=5,
                accounting_method="prime_cost",
                some_random_field="foo",  # extra="forbid" \u2192 error
            )

    def test_typo_of_dv_rate_factor_rejected(self) -> None:
        """Typo-guard: `dv_rate` (missing `_factor`) is still rejected. The
        F2-\u03b1 field name is exact; approximate matches remain in the
        `extra_forbidden` set."""
        with pytest.raises(ValidationError):
            AssetCreatedInput(
                cost=Decimal("5000.00"),
                acquisition_date=date(2022, 7, 1),
                accounting_useful_life_years=5,
                accounting_method="diminishing_value",
                dv_rate="2.0",  # not the declared field name
            )
