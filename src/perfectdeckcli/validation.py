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

# ---------------------------------------------------------------------------
# IAP required fields per store
# ---------------------------------------------------------------------------

# localizations key used inside each product config dict
_IAP_LOC_KEY: Dict[str, str] = {
    "app_store": "localizations",
    "play": "listings",
}

_IAP_REQUIRED_FIELDS: Dict[str, List[str]] = {
    "app_store": ["name", "description"],
    "play": ["title", "description"],
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


def validate_products(
    store: str,
    products_data: Dict[str, Any],
    listing_locales: Sequence[str],
) -> Dict[str, Any]:
    """Validate IAP products against the listing's configured locales.

    Checks:
    - Every product has a localization entry for every listing locale.
    - Each localization has the required fields (name+description / title+description).
    - Each product has a default price configured.
    - Every entry in the ``pricing`` dict has ``currency`` and ``price`` fields.

    Returns ``{"ok": bool, "errors": [...]}``.
    """
    loc_key = _IAP_LOC_KEY.get(store, "localizations")
    required_fields = _IAP_REQUIRED_FIELDS.get(store, [])
    errors: List[Dict[str, Any]] = []

    for product_id, product_config in sorted(products_data.items()):
        if not isinstance(product_config, dict):
            continue

        # --- Default price ---
        if store == "play" and not product_config.get("default_price"):
            errors.append({"product_id": product_id, "issue": "missing_default_price"})
        elif store == "app_store":
            pricing = product_config.get("pricing", {})
            if not pricing:
                errors.append({"product_id": product_id, "issue": "missing_pricing"})

        # --- Regional pricing structure ---
        pricing = product_config.get("pricing", {})
        if isinstance(pricing, dict):
            for country, price_info in pricing.items():
                if not isinstance(price_info, dict):
                    errors.append({
                        "product_id": product_id,
                        "country": country,
                        "issue": "invalid_pricing_entry",
                    })
                    continue
                for field in ("currency", "price"):
                    if not price_info.get(field):
                        errors.append({
                            "product_id": product_id,
                            "country": country,
                            "field": field,
                            "issue": "missing_pricing_field",
                        })

        # --- Localizations ---
        localizations = product_config.get(loc_key, {})
        if not isinstance(localizations, dict):
            localizations = {}

        for locale in listing_locales:
            if locale not in localizations:
                errors.append({
                    "product_id": product_id,
                    "locale": locale,
                    "issue": "missing_localization",
                })
                continue
            loc_data = localizations[locale]
            if not isinstance(loc_data, dict):
                errors.append({
                    "product_id": product_id,
                    "locale": locale,
                    "issue": "invalid_localization",
                })
                continue
            for field in required_fields:
                if not loc_data.get(field):
                    errors.append({
                        "product_id": product_id,
                        "locale": locale,
                        "field": field,
                        "issue": "missing_field",
                    })

    return {"ok": len(errors) == 0, "errors": errors}
