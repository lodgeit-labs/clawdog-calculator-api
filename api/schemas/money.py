"""D56 (Fable [CALC] 2026-09-28): one Money type validated for cent scale at
parse time, before any engine call.

`Money` accepts a JSON number or a decimal string, converts a number via
``Decimal(str(v))``, and rejects anything with more than 2 decimal places,
NaN / inf, or a non-numeric string. A failure surfaces as a standard 422 with
``loc: [<alias>]``, ``type: "money_not_cent_quantised"`` and
``msg: "<alias> must be cent-quantised (at most 2 decimal places); got <value>"``.

Apply it to money fields ONLY (percentages, factors, rate multipliers, and
counts keep their native types). Existing ``minimum`` / ``exclusiveMinimum``
constraints are declared on the field as usual and are preserved.

OpenAPI: the accepted JSON schema is a ``oneOf`` of
  * a number carrying ``multipleOf: 0.01``; and
  * a string carrying ``pattern: ^[+-]?\\d+(\\.\\d{1,2})?$``;
plus ``x-money: true`` and a description suffix (added at the field via
``money_field(...)``).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import BeforeValidator, Field, PlainSerializer, WithJsonSchema
from pydantic_core import PydanticCustomError

_MONEY_DESC_SUFFIX = "Money: cent-quantised, JSON number or decimal string."


def _to_cent_quantised_decimal(v: Any) -> Decimal:
    """Coerce a JSON number / decimal string to a cent-scale Decimal, or raise
    a ``money_not_cent_quantised`` error the 422 layer renders with the alias."""
    if isinstance(v, Decimal):
        dec = v
    elif isinstance(v, bool):
        # bool is an int subclass; never a money value.
        raise PydanticCustomError(
            "money_not_cent_quantised",
            "{field} must be cent-quantised (at most 2 decimal places); got {value}",
            {"field": "value", "value": v},
        )
    elif isinstance(v, int):
        dec = Decimal(v)
    elif isinstance(v, float):
        # Convert via the shortest round-trippable string so 33.335 stays 33.335
        # (not the binary-float tail) for the scale check.
        dec = Decimal(str(v))
    elif isinstance(v, str):
        try:
            dec = Decimal(v.strip())
        except (InvalidOperation, ValueError):
            raise PydanticCustomError(
                "money_not_cent_quantised",
                "{field} must be cent-quantised (at most 2 decimal places); got {value}",
                {"field": "value", "value": v},
            ) from None
    else:
        raise PydanticCustomError(
            "money_not_cent_quantised",
            "{field} must be cent-quantised (at most 2 decimal places); got {value}",
            {"field": "value", "value": v},
        )

    if not dec.is_finite():  # NaN / inf
        raise PydanticCustomError(
            "money_not_cent_quantised",
            "{field} must be cent-quantised (at most 2 decimal places); got {value}",
            {"field": "value", "value": v},
        )

    # More than 2 decimal places → refuse. Decimal exponent counts trailing
    # zeros, so normalize first: 33.3300 is fine, 33.335 is not.
    exponent = dec.normalize().as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise PydanticCustomError(
            "money_not_cent_quantised",
            "{field} must be cent-quantised (at most 2 decimal places); got {value}",
            {"field": "value", "value": v},
        )
    return dec


# The OpenAPI schema the accepted input advertises (number OR decimal string).
_MONEY_JSON_SCHEMA: dict[str, Any] = {
    "oneOf": [
        {"type": "number", "multipleOf": 0.01},
        {"type": "string", "pattern": r"^[+-]?\d+(\.\d{1,2})?$"},
    ],
    "x-money": True,
}

def reject_sub_cent_string(v: str) -> str:
    """Scale-check a decimal-string money field IN PLACE (keeps the ``str``
    type, for engines that consume decimal strings, e.g. HP). Raises
    ``money_not_cent_quantised`` on > 2 dp / NaN / inf / non-numeric.
    """
    if not isinstance(v, str):
        # Delegate non-strings to the Decimal coercer's rejection path.
        _to_cent_quantised_decimal(v)
        return v
    try:
        dec = Decimal(v.strip())
    except (InvalidOperation, ValueError):
        raise PydanticCustomError(
            "money_not_cent_quantised",
            "{field} must be cent-quantised (at most 2 decimal places); got {value}",
            {"field": "value", "value": v},
        ) from None
    if not dec.is_finite():
        raise PydanticCustomError(
            "money_not_cent_quantised",
            "{field} must be cent-quantised (at most 2 decimal places); got {value}",
            {"field": "value", "value": v},
        )
    exponent = dec.normalize().as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise PydanticCustomError(
            "money_not_cent_quantised",
            "{field} must be cent-quantised (at most 2 decimal places); got {value}",
            {"field": "value", "value": v},
        )
    return v


Money = Annotated[
    Decimal,
    BeforeValidator(_to_cent_quantised_decimal),
    # Emit a JSON-native number on serialisation so engines that receive the
    # payload via json.dumps / httpx json= see a number (identical to the
    # pre-D56 float contract) rather than a Decimal (which is not JSON
    # serialisable) or a string (which would change the engine contract).
    PlainSerializer(lambda d: float(d), return_type=float, when_used="always"),
    WithJsonSchema(_MONEY_JSON_SCHEMA),
]
"""A cent-quantised money value (Decimal). Use in a model annotation and add
field constraints/metadata via :func:`money_field`."""


def money_field(*args: Any, description: str = "", **kwargs: Any):
    """A ``Field(...)`` for a money value: appends the Money description suffix
    and marks the OpenAPI schema ``x-money: true``. Pass ``ge`` / ``gt`` etc.
    exactly as before to preserve existing minimum / exclusiveMinimum.
    """
    desc = description.rstrip()
    if desc and not desc.endswith(_MONEY_DESC_SUFFIX):
        desc = f"{desc} {_MONEY_DESC_SUFFIX}"
    elif not desc:
        desc = _MONEY_DESC_SUFFIX
    extra = kwargs.pop("json_schema_extra", {}) or {}
    extra = {**extra, "x-money": True}
    return Field(*args, description=desc, json_schema_extra=extra, **kwargs)
