"""Central engine-error → gateway-HTTPException mapper.

**Fable post-matrix directive mc00-2026-09-04 (D8a + D8b) + Fable amendments
mc00 05:09 UTC (Amendments 1-4 + Flag-1 timeout correction).**

Rulings (verbatim), stated generally because per-route or basis-shaped fixes
would not hold as the engine grows new conditional rules:

    D8a  — "The gateway must never report a 4xx from the engine as a 5xx.
            5xx means our fault, retry. 4xx means the caller's request, don't."

    D8b  — "The error surface is part of the contract. Sanitise it — the
            gateway echoes back the caller's payload, never the engine's."

    Fable Amendment 1 (fault-based partition, not digit-based):
            Not every engine 4xx is about the caller. Some 4xx status codes
            (401/403 authorisation, 404/405 wrong path, 429 rate-limit)
            describe the *gateway-to-engine* relationship, and passing them
            through blames the caller for our misconfiguration. Partition on
            whose fault, not on the digit.

    Fable Flag-1 / Amendment 2 (timeout = 504, not 503):
            An unanswered request is a 5xx. But 503 is "engine never answered
            the connection" (refused / DNS / not running) and 504 is "request
            was sent, engine did not respond in time." A read-timeout is
            exactly the 504 case. FBT/depreciation historic 503 is corrected
            *up* to 504; Div7A original 504 was right.

    Fable Amendment 3 (defence-in-depth drift-detector log):
            Once gateway-side conditional validation exists, an engine 422
            should be unreachable for caller errors. If that path fires,
            it means the gateway's schema has drifted behind the engine's.
            Log a distinct line converting the silent divergence into an
            observable one.

    Fable Amendment 4 (arm-with-producer discipline):
            Grep before shipping a mapper arm. The `engine_bad_request` arm
            has a real producer: `depreciation-engine` routes.py:860 emits
            a bare 400 (no `refusal_class`) on `to_date < acquisition_date`
            at `/range/`. Arm kept, cited.

Mapping (canonical, post-amendments):

  Transport:
    engine_unreachable      → 502 engine_unavailable
    engine_timeout          → 504 engine_timeout              (Amendment 2)
    engine_transport_error  → 502 engine_unavailable

  Engine returned an HTTP status:
    engine 400 + refusal_class      → 400 (flat refusal envelope; §6 cosmetic)
    engine 400 bare                 → 400 engine_bad_request  (routes.py:860)
    engine 409 / 413 / 422          → same 4xx, caller's fault (Amendment 1)
        + 422 defence-in-depth log line (Amendment 3)
    engine 401 / 403                → 502 engine_unavailable  (Amendment 1;
                                       IAM/authorisation is OUR fault, not
                                       the caller's — Approach D readiness)
    engine 404 / 405                → 502 engine_unavailable  (Amendment 1;
                                       the gateway is calling a path the
                                       engine doesn't serve — mc11-2026-08-02
                                       `/depreciation/audit` shape, the
                                       incident that opened this arc)
    engine 429                      → 503 engine_rate_limited (Amendment 1;
                                       carries Retry-After when engine did)
    other engine 4xx (unmapped)     → 502 engine_unavailable  (conservative:
                                       unknown 4xx is more likely our fault
                                       than the caller's under Amendment 1)
    engine 5xx                      → 502 engine_unavailable

  Sanitisation (D8b): strip `numeric_mode` (Amendment 2 rider 2 server-side
  pin) and `events` (§A2.2 10 000-item affordance) from any dict echoed to
  the caller, at both the top level and nested `request` / `payload` sub-dicts.

  Cosmetic flatten (Fable §6): refusal envelopes previously surfaced as
  `{"detail": {"detail": {...}}}` at the public front door. Mapper hands
  FastAPI a flat dict; caller sees `{"detail": {...}}`.

This is the mapper Fable ruled *"the safety net and it ships first, because
the next conditional rule the engine grows would otherwise reintroduce this."*
Gateway-side conditional validation (defence-in-depth) lands alongside it,
but if either half is bypassed the other still holds the line.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, status

from api.prolog_client import PrologCalculationError, PrologEngineUnavailable

logger = logging.getLogger(__name__)

# Fields the gateway strips from any engine body echoed to a caller (D8b).
_INTERNAL_ENGINE_FIELDS = frozenset({"numeric_mode", "events"})

# --- Fault-based 4xx partition (Fable Amendment 1) --------------------------
# Set membership dispatch beats digit-range dispatch: extending the table when
# a new engine-emitted status code appears is a one-line edit, and the
# partition is explicit at read-time.
#
# CALLER_FAULT_4XX: the engine's own content validation refused the caller.
#                   Re-emit as the same 4xx with actionable detail.
# GATEWAY_FAULT_4XX_AS_502: the engine's answer describes OUR relationship
#                   to it (auth, wrong path). 502 covers `engine_unavailable`
#                   from the caller's viewpoint; the caller cannot fix it.
# RATE_LIMITED_4XX: engine is throttling us. 503 with Retry-After when the
#                   engine passes one through; the caller SHOULD retry.
_CALLER_FAULT_4XX = frozenset({400, 409, 413, 422})
_GATEWAY_FAULT_4XX_AS_502 = frozenset({401, 403, 404, 405})
_RATE_LIMITED_4XX = frozenset({429})


def _sanitise_engine_body(body: Any) -> Any:
    """Strip internal engine fields from any dict-shaped engine body.

    Recurses into nested `request` / `payload` sub-dicts (some engines echo
    the caller's request back verbatim under those keys). String bodies get
    a JSON round-trip attempted; if they parse to a dict, the scrubbed
    version is re-serialised. If they don't parse, they pass through
    verbatim — better to echo raw engine text than to lie about what the
    engine said.
    """
    if isinstance(body, str):
        try:
            parsed = json.loads(body)
        except (ValueError, TypeError):
            return body
        scrubbed = _sanitise_engine_body(parsed)
        # Only re-serialise if scrubbing actually changed the parsed shape.
        if scrubbed == parsed:
            return body
        return json.dumps(scrubbed)
    if isinstance(body, Mapping):
        scrubbed = {k: v for k, v in body.items() if k not in _INTERNAL_ENGINE_FIELDS}
        for nested_key in ("request", "payload"):
            if nested_key in scrubbed and isinstance(scrubbed[nested_key], Mapping):
                scrubbed[nested_key] = {
                    k: v
                    for k, v in scrubbed[nested_key].items()
                    if k not in _INTERNAL_ENGINE_FIELDS
                }
        return scrubbed
    if isinstance(body, list):
        return [_sanitise_engine_body(item) for item in body]
    return body


def _parse_engine_body(body_text: str | None) -> Any | None:
    """Best-effort JSON parse. None = missing / non-JSON; caller falls back
    to echoing raw text."""
    if not body_text:
        return None
    try:
        return json.loads(body_text)
    except (ValueError, TypeError):
        return None


def _extract_retry_after(exc: PrologEngineUnavailable) -> str | None:
    """Best-effort extraction of a Retry-After hint from the engine's echoed
    detail. Today `PrologClient.dispatch()` only captures `status_code` +
    `body[:500]`; response headers do not survive. Returned so a future
    extension of the client can slot Retry-After in without touching the
    mapper's signature.
    """
    if isinstance(exc.detail, Mapping):
        headers = exc.detail.get("headers")
        if isinstance(headers, Mapping):
            for key in ("Retry-After", "retry-after"):
                if key in headers:
                    return str(headers[key])
    return None


def map_engine_error_to_http(
    exc: PrologEngineUnavailable,
    *,
    engine_label: str | None = None,
) -> HTTPException:
    """Turn a ``PrologEngineUnavailable`` into a gateway ``HTTPException``.

    ``engine_label`` overrides the default ``"engine_unavailable"`` error
    slug for 5xx/transport paths; per-route handlers may pass e.g.
    ``"div7a_engine_unavailable"`` to preserve their historic label. 4xx
    paths do NOT use the label (their slugs are fault-partition-derived:
    `engine_validation_error`, `engine_bad_request`, `engine_client_error`,
    `engine_rate_limited`).

    The returned HTTPException is *not* raised here — callers do the
    ``raise ... from exc`` themselves so the traceback frame reflects the
    original call site.
    """
    # --- Path 1: engine returned an HTTP status ------------------------------
    if exc.error_code == "engine_http_error" and isinstance(exc.detail, Mapping):
        status_code = exc.detail.get("status_code")
        body_text = exc.detail.get("body")
        parsed_body = _parse_engine_body(body_text)

        # --- 1a: engine 400 + refusal_class → 400 refusal envelope, flat.
        # Cell 8 exercises this. The refusal body IS the contract.
        #
        # Fable mc01-2026-09-04 08:28 UTC (cell 20 wire-verified defect +
        # ruling): FastAPI wraps HTTPException(detail=X) unconditionally
        # in {"detail": X}. The engine's refusal body carries its own
        # `detail` key. Prior mapper handed FastAPI the engine's dict
        # verbatim; wire result was:
        #
        #   {"detail": {"detail": "pool_asset_out_of_t6_scope",
        #               "refusal_class": "pool_asset_out_of_t6_scope",
        #               "refusal_payload": {...}}}
        #
        # The inner `detail` string is character-for-character equal to
        # `refusal_class` on the pool-asset refusal path (engine emits
        # both as the constant `REFUSAL_POOL_ASSET_OUT_OF_T6_SCOPE ==
        # "pool_asset_out_of_t6_scope"` — wire-verified against
        # depreciation-engine/depreciation_core/refusal.py:94). Not
        # nesting; duplication. Fable ruled: drop the untyped one.
        #
        # Scoping (Fable's actual ruling was drop-when-duplicate, not
        # unconditional-drop, because the engine's OTHER refusal path
        # — unknown_basis at routes.py:548 — sets `detail` to a
        # meaningful string that is NOT a duplicate of `refusal_class`.
        # Unconditional pop would drop genuine content there):
        #
        # POP the inner `detail` key ONLY when it equals `refusal_class`.
        # Any other value stays: it's real explanatory content.
        if (
            status_code == 400
            and isinstance(parsed_body, Mapping)
            and parsed_body.get("refusal_class")
        ):
            sanitised = _sanitise_engine_body(parsed_body)
            if (
                isinstance(sanitised, Mapping)
                and sanitised.get("detail") == sanitised.get("refusal_class")
            ):
                sanitised = {
                    k: v for k, v in sanitised.items() if k != "detail"
                }
            return HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=sanitised,
            )

        # --- 1b: caller-fault 4xx (Fable Amendment 1: 400/409/413/422).
        # Includes bare 400 without refusal_class (real producer:
        # depreciation-engine routes.py:860 `to_date < acquisition_date`
        # on /range/).
        if status_code in _CALLER_FAULT_4XX:
            if status_code == 422:
                error_slug = "engine_validation_error"
                # Fable Amendment 3: once gateway-side conditional
                # validation exists, this branch should be unreachable for
                # caller errors. When it fires, it means the gateway's
                # schema has drifted behind the engine's. Convert the
                # silent divergence into an observable one.
                logger.warning(
                    "gateway_engine_schema_drift: engine=%s url=%s "
                    "returned 422 which gateway did not catch at pydantic "
                    "layer; caller received engine_validation_error. "
                    "This means the gateway's schema is behind the engine's.",
                    exc.engine,
                    getattr(exc, "url", "<unknown>"),
                )
            elif status_code == 400:
                error_slug = "engine_bad_request"
            elif status_code == 409:
                error_slug = "engine_conflict"
            else:  # 413
                error_slug = "engine_payload_too_large"

            engine_detail: Any
            if parsed_body is not None:
                engine_detail = _sanitise_engine_body(parsed_body)
            else:
                engine_detail = _sanitise_engine_body(body_text)

            return HTTPException(
                status_code=status_code,
                detail={
                    "error": error_slug,
                    "engine": engine_label or exc.engine,
                    "status_code": status_code,
                    "engine_detail": engine_detail,
                },
            )

        # --- 1c: gateway-fault 4xx (Fable Amendment 1: 401/403/404/405).
        # Never blame the caller for OUR configuration failure. 404 is the
        # incident that opened this arc — the gateway called
        # `/depreciation/audit` on the engine and the engine 404'd; under
        # a digit-based mapper that would have surfaced as "not found" to
        # the caller, sending them to look for a resource that was never
        # the problem. 401/403 is the Approach-D readiness path (engine
        # closed to IAM invoker binding; unbound gateway gets 403).
        if status_code in _GATEWAY_FAULT_4XX_AS_502:
            logger.error(
                "gateway_engine_misconfiguration: engine=%s url=%s "
                "returned %s; gateway surfaces as 502 rather than "
                "blaming caller. Class: %s.",
                exc.engine,
                getattr(exc, "url", "<unknown>"),
                status_code,
                (
                    "auth"
                    if status_code in (401, 403)
                    else "wrong_path"
                ),
            )
            return HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "error": engine_label or "engine_unavailable",
                    "error_code": exc.error_code,
                    "engine": exc.engine,
                    "detail": _sanitise_engine_body(dict(exc.detail)),
                },
            )

        # --- 1d: engine 429 → gateway 503 rate-limited (Fable Amendment 1).
        # The caller SHOULD retry; the engine's Retry-After is forwarded
        # verbatim when the engine sends one. Fable mc00 05:21 UTC sanity:
        # *never synthesise* a retry interval when the engine did not send
        # one — a fabricated interval is a claim about capacity we have no
        # basis for. When absent, `retry_after` is omitted from the response
        # entirely rather than emitted as null, and no Retry-After header
        # is set.
        if status_code in _RATE_LIMITED_4XX:
            retry_after = _extract_retry_after(exc)
            detail_body: dict[str, Any] = {
                "error": "engine_rate_limited",
                "engine": exc.engine,
                "status_code": 429,
                "engine_detail": (
                    _sanitise_engine_body(parsed_body)
                    if parsed_body is not None
                    else _sanitise_engine_body(body_text)
                ),
            }
            headers: dict[str, str] | None = None
            if retry_after is not None:
                detail_body["retry_after"] = retry_after
                headers = {"Retry-After": retry_after}
            return HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=detail_body,
                headers=headers,
            )

        # --- 1e: any other engine 4xx (Fable Amendment 1 conservative
        # default) → 502. Unknown 4xx is more likely our fault than the
        # caller's; the mapper defaults to charity toward the caller.
        if isinstance(status_code, int) and 400 <= status_code < 500:
            logger.warning(
                "gateway_engine_unmapped_4xx: engine=%s url=%s returned "
                "%s (not in caller-fault / gateway-fault / rate-limit "
                "partitions); defaulting to 502 per Amendment 1 "
                "conservative rule.",
                exc.engine,
                getattr(exc, "url", "<unknown>"),
                status_code,
            )
            return HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "error": engine_label or "engine_unavailable",
                    "error_code": exc.error_code,
                    "engine": exc.engine,
                    "detail": _sanitise_engine_body(dict(exc.detail)),
                },
            )

        # --- 1f: engine 5xx → 502. Sanitise before echoing.
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": engine_label or "engine_unavailable",
                "error_code": exc.error_code,
                "engine": exc.engine,
                "detail": _sanitise_engine_body(dict(exc.detail)),
            },
        )

    # --- Path 2: timeout → 504 (Fable Flag-1 / Amendment 2 correction) ------
    # Fable original 503 ruling was wrong; the request was sent, the engine
    # did not respond in time, that is exactly 504 Gateway Timeout. Historic
    # Div7A 504 was right; FBT + depreciation historic 503 is corrected up.
    if exc.error_code == "engine_timeout":
        return HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={
                "error": engine_label or "engine_timeout",
                "error_code": exc.error_code,
                "engine": exc.engine,
                "detail": exc.detail,
            },
        )

    # --- Path 3: transport failures (connect refused / protocol / catchall) →
    # 502 engine_unavailable (Fable Amendment 2: "engine never answered the
    # connection: refused, DNS, not running").
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={
            "error": engine_label or "engine_unavailable",
            "error_code": exc.error_code,
            "engine": exc.engine,
            "detail": exc.detail,
        },
    )


def map_calculation_error_to_http(
    exc: PrologCalculationError,
) -> HTTPException:
    """Turn a ``PrologCalculationError`` into a gateway ``HTTPException``.

    Structured engine-side errors that fall outside the transport-layer path;
    surfaced as 502 (the engine returned a 200 with an error-shaped body,
    which is the engine's contract violation from the caller's viewpoint).
    """
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={"error": exc.error, "detail": _sanitise_engine_body(exc.detail)},
    )


__all__ = [
    "map_engine_error_to_http",
    "map_calculation_error_to_http",
]
