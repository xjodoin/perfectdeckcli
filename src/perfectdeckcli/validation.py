"""Character-limit validation for Play Store and App Store listings."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence


# ---------------------------------------------------------------------------
# Google Play Store limits
# ---------------------------------------------------------------------------

PLAY_STORE_LIMITS: Dict[str, int] = {
    "title": 30,
    "short_description": 80,
    "full_description": 4000,
}

# ---------------------------------------------------------------------------
# Apple App Store limits
# ---------------------------------------------------------------------------

APP_STORE_LIMITS: Dict[str, int] = {
    "app_name": 30,
    "subtitle": 30,
    "promotional_text": 170,
    "description": 4000,
    "keywords": 100,
}


def _check_field(
    errors: List[Dict[str, Any]],
    locale: str,
    field: str,
    value: Any,
    limit: int,
) -> None:
    if value is None:
        return
    text = str(value)
    length = len(text)
    if length > limit:
        errors.append(
            {
                "locale": locale,
                "field": field,
                "length": length,
                "limit": limit,
                "over_by": length - limit,
            }
        )


def validate_play_listing(
    locales_data: Dict[str, Dict[str, Any]],
    extra_fields: Dict[str, int] | None = None,
) -> Dict[str, Any]:
    """Validate Play Store locale data against character limits.

    *locales_data* maps ``{locale: {title, short_description, …}}``.

    Returns ``{"ok": bool, "errors": [...]}``.
    """
    limits = {**PLAY_STORE_LIMITS, **(extra_fields or {})}
    errors: List[Dict[str, Any]] = []

    for locale, fields in sorted(locales_data.items()):
        if not isinstance(fields, dict):
            continue
        for field_name, max_len in limits.items():
            _check_field(errors, locale, field_name, fields.get(field_name), max_len)

    return {"ok": len(errors) == 0, "errors": errors}


def validate_app_store_listing(
    locales_data: Dict[str, Dict[str, Any]],
    extra_fields: Dict[str, int] | None = None,
) -> Dict[str, Any]:
    """Validate App Store locale data against character limits.

    *locales_data* maps ``{locale: {app_name, subtitle, description, …}}``.

    Returns ``{"ok": bool, "errors": [...]}``.
    """
    limits = {**APP_STORE_LIMITS, **(extra_fields or {})}
    errors: List[Dict[str, Any]] = []

    for locale, fields in sorted(locales_data.items()):
        if not isinstance(fields, dict):
            continue
        for field_name, max_len in limits.items():
            _check_field(errors, locale, field_name, fields.get(field_name), max_len)

    return {"ok": len(errors) == 0, "errors": errors}


def validate_listing(
    store: str,
    locales_data: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Validate locale data for the given store (``"play"`` or ``"app_store"``)."""
    if store == "play":
        return validate_play_listing(locales_data)
    if store == "app_store":
        return validate_app_store_listing(locales_data)
    raise ValueError(f"Unknown store: {store}")
