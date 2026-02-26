"""Google Play Store API client for fetching and pushing store listings."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Locale mapping  (project locale → Play Store locale)
# ---------------------------------------------------------------------------

PLAY_LOCALE_MAP: Mapping[str, str] = {
    "ar": "ar",
    "ar-SA": "ar",
    "cs": "cs-CZ",
    "da": "da-DK",
    "de-DE": "de-DE",
    "el": "el-GR",
    "en-US": "en-US",
    "es-ES": "es-ES",
    "es-419": "es-419",
    "es-MX": "es-419",
    "fi": "fi-FI",
    "fr-CA": "fr-CA",
    "fr-FR": "fr-FR",
    "fil": "fil",
    "fil-PH": "fil",
    "hi": "hi-IN",
    "hi-IN": "hi-IN",
    "hu": "hu-HU",
    "hu-HU": "hu-HU",
    "id": "id",
    "id-ID": "id",
    "it": "it-IT",
    "it-IT": "it-IT",
    "ja": "ja-JP",
    "ja-JP": "ja-JP",
    "ko": "ko-KR",
    "ko-KR": "ko-KR",
    "nl-NL": "nl-NL",
    "nb": "nb-NO",
    "nb-NO": "nb-NO",
    "no": "nb-NO",
    "no-NO": "nb-NO",
    "pl": "pl-PL",
    "pl-PL": "pl-PL",
    "pt-BR": "pt-BR",
    "pt-PT": "pt-PT",
    "ro": "ro",
    "ru": "ru-RU",
    "ru-RU": "ru-RU",
    "sv": "sv-SE",
    "sv-SE": "sv-SE",
    "th": "th",
    "th-TH": "th",
    "tr": "tr-TR",
    "tr-TR": "tr-TR",
    "vi": "vi",
    "vi-VN": "vi",
    "zh-Hans": "zh-CN",
    "zh-Hant": "zh-TW",
    "zh-CN": "zh-CN",
    "zh-TW": "zh-TW",
}

VALID_IMAGE_TYPES = frozenset({
    "phoneScreenshots",
    "sevenInchScreenshots",
    "tenInchScreenshots",
    "tvScreenshots",
    "wearScreenshots",
    "icon",
    "featureGraphic",
    "tvBanner",
})

VALID_RELEASE_STATUSES = frozenset({
    "draft",
    "inProgress",
    "halted",
    "completed",
})


def map_locale(locale: str) -> str:
    """Map a project locale to the canonical Google Play locale code."""
    if locale in PLAY_LOCALE_MAP:
        return PLAY_LOCALE_MAP[locale]
    if "-" in locale:
        language, region = locale.split("-", 1)
        return f"{language.lower()}-{region.upper()}"
    return locale


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def _execute_with_retry(request_obj: Any, *, max_attempts: int = 4) -> Any:
    """Execute a Google API request with retry on transient errors."""
    import time
    import random

    for attempt in range(1, max_attempts + 1):
        try:
            return request_obj.execute()
        except HttpError as exc:
            status = exc.resp.status if hasattr(exc, "resp") and exc.resp else 0
            if status in {429, 500, 502, 503, 504} and attempt < max_attempts:
                wait = 1.0 * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                logger.warning(
                    "Transient error %s (attempt %s/%s). Retrying in %.2fs.",
                    status, attempt, max_attempts, wait,
                )
                time.sleep(wait)
                continue
            raise


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def create_service(
    credentials_path: str | None = None,
    env_var: str = "PLAY_SERVICE_ACCOUNT_JSON",
) -> Any:
    """Build an ``androidpublisher`` v3 service from a service-account JSON file or env var.

    The *credentials_path* argument takes precedence.  When it is ``None`` the
    function falls back to the environment variable *env_var*, which can hold
    either inline JSON **or** a path to a JSON file on disk.
    """
    scopes = ["https://www.googleapis.com/auth/androidpublisher"]

    if credentials_path is not None:
        path = Path(credentials_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Service account JSON not found at {path}.")
        credentials = Credentials.from_service_account_file(str(path), scopes=scopes)
        return build("androidpublisher", "v3", credentials=credentials, cache_discovery=False)

    env_value = os.getenv(env_var)
    if not env_value:
        raise FileNotFoundError(
            f"Service account JSON not provided. Pass credentials_path or set the {env_var} environment variable."
        )

    env_value = env_value.strip()
    info_data: Mapping[str, str] | None = None
    json_error: json.JSONDecodeError | None = None

    try:
        info_data = json.loads(env_value)
    except json.JSONDecodeError as exc:
        json_error = exc

    if info_data is None:
        candidate_path: Path | None = None
        try:
            candidate_path = Path(env_value).expanduser()
        except (OSError, RuntimeError, ValueError):
            candidate_path = None

        if candidate_path and candidate_path.exists():
            info_text = candidate_path.read_text(encoding="utf-8")
            try:
                info_data = json.loads(info_text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Service account file referenced by {env_var} is not valid JSON: {candidate_path}."
                ) from exc
        elif candidate_path and not candidate_path.exists():
            raise FileNotFoundError(
                f"Service account file referenced by {env_var} not found: {candidate_path}."
            )

    if info_data is None:
        raise ValueError(
            f"Environment variable {env_var} must contain service account JSON or a path to a JSON file."
        ) from json_error

    credentials = Credentials.from_service_account_info(info_data, scopes=scopes)
    return build("androidpublisher", "v3", credentials=credentials, cache_discovery=False)


# ---------------------------------------------------------------------------
# Fetch (read-only)
# ---------------------------------------------------------------------------

def fetch_listings(
    service: Any,
    package_name: str,
    locales: Sequence[str] | None = None,
) -> Dict[str, Any]:
    """Fetch store listings from Google Play via an edit.

    Returns ``{"global": {...}, "locales": {locale: {title, shortDescription, fullDescription}}}``.
    The edit is always deleted in the ``finally`` block.
    """
    edits = service.edits()
    insert_response = edits.insert(packageName=package_name, body={}).execute()
    edit_id = insert_response["id"]

    try:
        # Fetch app-level details (defaultLanguage, contact info)
        global_data: Dict[str, str] = {}
        try:
            details = (
                edits.details()
                .get(packageName=package_name, editId=edit_id)
                .execute()
            )
            if details.get("defaultLanguage"):
                global_data["default_language"] = details["defaultLanguage"]
            if details.get("contactEmail"):
                global_data["contact_email"] = details["contactEmail"]
            if details.get("contactPhone"):
                global_data["contact_phone"] = details["contactPhone"]
            if details.get("contactWebsite"):
                global_data["contact_website"] = details["contactWebsite"]
        except HttpError:
            logger.warning("Could not fetch app details for %s", package_name)

        # Fetch per-locale listings
        listings_response = (
            edits.listings()
            .list(packageName=package_name, editId=edit_id)
            .execute()
        )
        remote_listings = listings_response.get("listings", []) or []

        listings_map: Dict[str, Dict[str, str]] = {}
        for entry in remote_listings:
            language = entry.get("language")
            if not language:
                continue
            listings_map[language] = {
                "title": entry.get("title", ""),
                "shortDescription": entry.get("shortDescription", ""),
                "fullDescription": entry.get("fullDescription", ""),
            }

        if locales:
            requested = set(locales)
            listings_map = {
                lang: data
                for lang, data in listings_map.items()
                if lang in requested
            }

        return {"global": global_data, "locales": listings_map}
    finally:
        try:
            edits.delete(packageName=package_name, editId=edit_id).execute()
        except HttpError:
            pass


# ---------------------------------------------------------------------------
# Fetch products and subscriptions (read-only)
# ---------------------------------------------------------------------------


def fetch_products(
    service: Any,
    package_name: str,
) -> Dict[str, Any]:
    """Fetch one-time in-app products from Google Play.

    Returns ``{product_id: {type, default_price, localizations, pricing}}``.
    """
    monetization = service.monetization()
    products: Dict[str, Any] = {}

    try:
        response = monetization.onetimeproducts().list(
            packageName=package_name,
        ).execute()

        # The monetization.onetimeproducts API returns "oneTimeProducts";
        # fall back to legacy keys for older API versions.
        items = (
            response.get("oneTimeProducts")
            or response.get("inappproduct")
            or response.get("inAppProducts")
            or []
        )
        for item in items:
            sku = item.get("productId") or item.get("sku")
            if not sku:
                continue

            entry: Dict[str, Any] = {"type": "consumable"}

            # Default price — legacy API uses "defaultPrice" with priceMicros
            default_price = item.get("defaultPrice", {})
            if default_price:
                currency = default_price.get("currency", "")
                price_micros = default_price.get("priceMicros", "0")
                try:
                    price_val = int(price_micros) / 1_000_000
                except (ValueError, TypeError):
                    price_val = 0.0
                if currency:
                    entry["default_price"] = {"currency": currency, "price": price_val}

            # Listings (localizations) — new API returns a list, legacy returns a dict
            listings = item.get("listings", [])
            if listings:
                locs: Dict[str, Dict[str, str]] = {}
                if isinstance(listings, list):
                    for listing in listings:
                        locale = listing.get("languageCode")
                        if not locale:
                            continue
                        loc_entry: Dict[str, str] = {}
                        if listing.get("title"):
                            loc_entry["title"] = listing["title"]
                        if listing.get("description"):
                            loc_entry["description"] = listing["description"]
                        if loc_entry:
                            locs[locale] = loc_entry
                elif isinstance(listings, dict):
                    for locale, fields in listings.items():
                        loc_entry_d: Dict[str, str] = {}
                        if fields.get("title"):
                            loc_entry_d["title"] = fields["title"]
                        if fields.get("description"):
                            loc_entry_d["description"] = fields["description"]
                        if loc_entry_d:
                            locs[locale] = loc_entry_d
                if locs:
                    entry["localizations"] = locs

            # Regional pricing — new API uses purchaseOptions[].regionalPricingAndAvailabilityConfigs
            purchase_options = item.get("purchaseOptions", [])
            if purchase_options and isinstance(purchase_options, list):
                pricing: Dict[str, Dict[str, Any]] = {}
                for po in purchase_options:
                    configs = po.get("regionalPricingAndAvailabilityConfigs", [])
                    for cfg in configs or []:
                        region = cfg.get("regionCode")
                        price_money = cfg.get("price", {})
                        if region and price_money:
                            currency = price_money.get("currencyCode", "")
                            # Money proto: units (string) + nanos (int)
                            try:
                                units = int(price_money.get("units", "0") or "0")
                                nanos = int(price_money.get("nanos", 0) or 0)
                                price_val = units + nanos / 1_000_000_000
                            except (ValueError, TypeError):
                                price_val = 0.0
                            if currency:
                                pricing[region] = {"currency": currency, "price": price_val}
                if pricing:
                    entry["pricing"] = pricing
                    # Derive default_price from US region if not already set
                    if "default_price" not in entry and "US" in pricing:
                        entry["default_price"] = pricing["US"].copy()

            # Legacy regional pricing — old API uses flat "prices" dict with priceMicros
            if "pricing" not in entry:
                prices = item.get("prices", {})
                if prices and isinstance(prices, dict):
                    pricing_legacy: Dict[str, Dict[str, Any]] = {}
                    for country, price_info in prices.items():
                        currency = price_info.get("currency", "")
                        price_micros = price_info.get("priceMicros", "0")
                        try:
                            price_val = int(price_micros) / 1_000_000
                        except (ValueError, TypeError):
                            price_val = 0.0
                        if currency:
                            pricing_legacy[country] = {"currency": currency, "price": price_val}
                    if pricing_legacy:
                        entry["pricing"] = pricing_legacy

            products[sku] = entry
    except Exception:
        logger.warning("Could not fetch one-time products for %s", package_name, exc_info=True)

    return products


def fetch_subscriptions(
    service: Any,
    package_name: str,
) -> Dict[str, Any]:
    """Fetch subscriptions from Google Play.

    Returns ``{subscription_id: {localizations, base_plans}}``.
    """
    monetization = service.monetization()
    subscriptions: Dict[str, Any] = {}

    try:
        response = monetization.subscriptions().list(
            packageName=package_name,
        ).execute()

        for item in response.get("subscriptions", []) or []:
            product_id = item.get("productId")
            if not product_id:
                continue

            entry: Dict[str, Any] = {}

            # Listings (localizations)
            listings = item.get("listings", [])
            if listings:
                locs: Dict[str, Dict[str, str]] = {}
                # listings can be a list of {languageCode, title, description, ...}
                if isinstance(listings, list):
                    for listing in listings:
                        locale = listing.get("languageCode")
                        if not locale:
                            continue
                        loc_entry: Dict[str, str] = {}
                        if listing.get("title"):
                            loc_entry["title"] = listing["title"]
                        if listing.get("description"):
                            loc_entry["description"] = listing["description"]
                        if loc_entry:
                            locs[locale] = loc_entry
                elif isinstance(listings, dict):
                    for locale, fields in listings.items():
                        loc_entry_d: Dict[str, str] = {}
                        if fields.get("title"):
                            loc_entry_d["title"] = fields["title"]
                        if fields.get("description"):
                            loc_entry_d["description"] = fields["description"]
                        if loc_entry_d:
                            locs[locale] = loc_entry_d
                if locs:
                    entry["localizations"] = locs

            # Base plans with pricing
            base_plans = item.get("basePlans", [])
            if base_plans:
                bp_map: Dict[str, Any] = {}
                for bp in base_plans:
                    bp_id = bp.get("basePlanId")
                    if not bp_id:
                        continue
                    bp_entry: Dict[str, Any] = {}
                    regional_configs = bp.get("regionalConfigs", [])
                    if regional_configs:
                        pricing: Dict[str, Dict[str, Any]] = {}
                        for rc in regional_configs:
                            region = rc.get("regionCode")
                            price_info = rc.get("price", {})
                            if region and price_info:
                                # Money proto: currencyCode + units/nanos
                                currency = price_info.get("currencyCode", "") or price_info.get("currency", "")
                                if "units" in price_info or "nanos" in price_info:
                                    try:
                                        units = int(price_info.get("units", "0") or "0")
                                        nanos = int(price_info.get("nanos", 0) or 0)
                                        price_val = units + nanos / 1_000_000_000
                                    except (ValueError, TypeError):
                                        price_val = 0.0
                                else:
                                    # Legacy priceMicros format
                                    price_micros = price_info.get("priceMicros", "0")
                                    try:
                                        price_val = int(price_micros) / 1_000_000
                                    except (ValueError, TypeError):
                                        price_val = 0.0
                                if currency:
                                    pricing[region] = {"currency": currency, "price": price_val}
                        if pricing:
                            bp_entry["pricing"] = pricing
                    if bp_entry:
                        bp_map[bp_id] = bp_entry
                if bp_map:
                    entry["base_plans"] = bp_map

            subscriptions[product_id] = entry
    except Exception:
        logger.warning("Could not fetch subscriptions for %s", package_name)

    return subscriptions


# ---------------------------------------------------------------------------
# Push listings
# ---------------------------------------------------------------------------

def push_listings(
    service: Any,
    package_name: str,
    locales_data: Dict[str, Dict[str, str]],
    *,
    release_notes: Dict[str, str] | None = None,
    track: str = "production",
    version_code: int | None = None,
) -> Dict[str, Any]:
    """Upload listing metadata (title, descriptions) and optionally release notes.

    *locales_data* maps ``{play_locale: {title, shortDescription, fullDescription}}``.
    *release_notes* maps ``{play_locale: text}`` and requires *version_code*.

    Returns ``{"ok": True, "updated_locales": [...], "committed": True}``.
    """
    edits = service.edits()
    insert_response = _execute_with_retry(
        edits.insert(packageName=package_name, body={})
    )
    edit_id = insert_response["id"]
    updated: List[str] = []

    try:
        for locale, fields in sorted(locales_data.items()):
            body: Dict[str, str] = {}
            if fields.get("title"):
                body["title"] = fields["title"]
            if fields.get("shortDescription"):
                body["shortDescription"] = fields["shortDescription"]
            if fields.get("fullDescription"):
                body["fullDescription"] = fields["fullDescription"]
            if not body:
                continue
            _execute_with_retry(
                edits.listings().update(
                    packageName=package_name,
                    editId=edit_id,
                    language=locale,
                    body=body,
                )
            )
            updated.append(locale)

        if release_notes and version_code is not None:
            _update_release_notes_in_edit(
                edits, package_name, edit_id, track, version_code, release_notes,
            )

        _execute_with_retry(edits.commit(packageName=package_name, editId=edit_id))
        return {"ok": True, "updated_locales": updated, "committed": True}
    except Exception:
        try:
            edits.delete(packageName=package_name, editId=edit_id).execute()
        except HttpError:
            pass
        raise


# ---------------------------------------------------------------------------
# Release notes
# ---------------------------------------------------------------------------

def _update_release_notes_in_edit(
    edits: Any,
    package_name: str,
    edit_id: str,
    track: str,
    version_code: int | None,
    release_notes: Dict[str, str],
) -> None:
    """Update release notes for a version code within an existing edit."""
    track_resource = _execute_with_retry(
        edits.tracks().get(packageName=package_name, editId=edit_id, track=track)
    )
    releases = track_resource.get("releases", []) or []
    if version_code is None:
        target_release = releases[0] if releases else None
    else:
        version_code_str = str(version_code)
        target_release = next(
            (
                r for r in releases
                if version_code_str in (r.get("versionCodes") or [])
            ),
            None,
        )
    if target_release is None:
        raise RuntimeError(
            f"No release found for version code {version_code} on track {track}."
        )

    notes_list = [
        {"language": lang, "text": text}
        for lang, text in sorted(release_notes.items())
        if text
    ]
    target_release["releaseNotes"] = notes_list

    _execute_with_retry(
        edits.tracks().update(
            packageName=package_name,
            editId=edit_id,
            track=track,
            body=track_resource,
        )
    )


def update_release_notes(
    service: Any,
    package_name: str,
    track: str,
    version_code: int | None,
    release_notes: Dict[str, str],
) -> Dict[str, Any]:
    """Standalone: update release notes for a version code on a track.

    *release_notes* maps ``{play_locale: text}``.
    If *version_code* is None, the latest release on the track is used.
    """
    edits = service.edits()
    insert_response = _execute_with_retry(
        edits.insert(packageName=package_name, body={})
    )
    edit_id = insert_response["id"]

    try:
        _update_release_notes_in_edit(
            edits, package_name, edit_id, track, version_code, release_notes,
        )
        _execute_with_retry(edits.commit(packageName=package_name, editId=edit_id))
        return {"ok": True, "track": track, "version_code": version_code}
    except Exception:
        try:
            edits.delete(packageName=package_name, editId=edit_id).execute()
        except HttpError:
            pass
        raise


# ---------------------------------------------------------------------------
# Screenshot upload
# ---------------------------------------------------------------------------

def _compute_sha1(file_path: Path) -> str:
    data = file_path.read_bytes()
    return hashlib.sha1(data).hexdigest()


def upload_screenshots(
    service: Any,
    package_name: str,
    locale: str,
    image_type: str,
    file_paths: Sequence[str | Path],
    *,
    replace: bool = True,
) -> Dict[str, Any]:
    """Upload screenshots for one locale + image type.

    *image_type* must be one of ``VALID_IMAGE_TYPES`` (e.g. ``phoneScreenshots``).
    When *replace* is True, existing screenshots are deleted before uploading.

    Returns ``{"ok": True, "uploaded": int, "skipped": int}``.
    """
    if image_type not in VALID_IMAGE_TYPES:
        raise ValueError(f"Invalid image_type {image_type!r}. Must be one of {sorted(VALID_IMAGE_TYPES)}.")

    paths = [Path(p) for p in file_paths]
    for p in paths:
        if not p.exists():
            raise FileNotFoundError(f"Screenshot file not found: {p}")

    edits = service.edits()
    insert_response = _execute_with_retry(
        edits.insert(packageName=package_name, body={})
    )
    edit_id = insert_response["id"]
    uploaded = 0
    skipped = 0

    try:
        if replace:
            # Check existing screenshots and compare hashes
            existing_response = _execute_with_retry(
                edits.images().list(
                    packageName=package_name,
                    editId=edit_id,
                    language=locale,
                    imageType=image_type,
                )
            )
            existing_images = existing_response.get("images", []) or []
            existing_hashes = {img.get("sha1") for img in existing_images if img.get("sha1")}
            new_hashes = {_compute_sha1(p) for p in paths}

            if existing_hashes == new_hashes and len(existing_images) == len(paths):
                # All screenshots match — nothing to do
                try:
                    edits.delete(packageName=package_name, editId=edit_id).execute()
                except HttpError:
                    pass
                return {"ok": True, "uploaded": 0, "skipped": len(paths)}

            _execute_with_retry(
                edits.images().deleteall(
                    packageName=package_name,
                    editId=edit_id,
                    language=locale,
                    imageType=image_type,
                )
            )

        for file_path in paths:
            media = MediaFileUpload(str(file_path), mimetype="image/png")
            _execute_with_retry(
                edits.images().upload(
                    packageName=package_name,
                    editId=edit_id,
                    language=locale,
                    imageType=image_type,
                    media_body=media,
                )
            )
            uploaded += 1

        _execute_with_retry(edits.commit(packageName=package_name, editId=edit_id))
        return {"ok": True, "uploaded": uploaded, "skipped": skipped}
    except Exception:
        try:
            edits.delete(packageName=package_name, editId=edit_id).execute()
        except HttpError:
            pass
        raise


# ---------------------------------------------------------------------------
# Bundle publishing
# ---------------------------------------------------------------------------

def publish_bundle(
    service: Any,
    package_name: str,
    bundle_path: str | Path,
    *,
    track: str = "internal",
    status: str = "draft",
    release_notes: Dict[str, str] | None = None,
    mapping_path: str | Path | None = None,
) -> Dict[str, Any]:
    """Upload an Android App Bundle (.aab) and assign it to a track.

    *status* must be one of ``VALID_RELEASE_STATUSES``.

    Returns ``{"ok": True, "version_code": int, "track": str}``.
    """
    if status not in VALID_RELEASE_STATUSES:
        raise ValueError(f"Invalid status {status!r}. Must be one of {sorted(VALID_RELEASE_STATUSES)}.")
    bundle = Path(bundle_path)
    if not bundle.exists():
        raise FileNotFoundError(f"Bundle file not found: {bundle}")

    edits = service.edits()
    insert_response = _execute_with_retry(
        edits.insert(packageName=package_name, body={})
    )
    edit_id = insert_response["id"]

    try:
        media = MediaFileUpload(str(bundle), mimetype="application/octet-stream")
        bundle_response = _execute_with_retry(
            edits.bundles().upload(
                packageName=package_name,
                editId=edit_id,
                media_body=media,
            )
        )
        version_code = bundle_response["versionCode"]

        if mapping_path is not None:
            mapping = Path(mapping_path)
            if mapping.exists():
                mapping_media = MediaFileUpload(str(mapping), mimetype="application/octet-stream")
                _execute_with_retry(
                    edits.deobfuscationfiles().upload(
                        packageName=package_name,
                        editId=edit_id,
                        apkVersionCode=version_code,
                        deobfuscationFileType="proguard",
                        media_body=mapping_media,
                    )
                )

        release_body: Dict[str, Any] = {
            "status": status,
            "versionCodes": [str(version_code)],
        }
        if release_notes:
            release_body["releaseNotes"] = [
                {"language": lang, "text": text}
                for lang, text in sorted(release_notes.items())
                if text
            ]

        _execute_with_retry(
            edits.tracks().update(
                packageName=package_name,
                editId=edit_id,
                track=track,
                body={"releases": [release_body]},
            )
        )

        _execute_with_retry(edits.commit(packageName=package_name, editId=edit_id))
        return {"ok": True, "version_code": version_code, "track": track}
    except Exception:
        try:
            edits.delete(packageName=package_name, editId=edit_id).execute()
        except HttpError:
            pass
        raise


# ---------------------------------------------------------------------------
# Managed products (one-time in-app purchases)
# ---------------------------------------------------------------------------

def _micro_price_to_money(currency: str, price_micros: int) -> Dict[str, str]:
    return {"currency": currency, "priceMicros": str(price_micros)}


def _price_to_money(currency: str, price: float) -> Dict[str, str]:
    return _micro_price_to_money(currency, int(round(price * 1_000_000)))


def _price_to_money_proto(currency: str, price: float) -> Dict[str, Any]:
    """Convert a price to the Money proto format used by the new monetization API."""
    units = int(price)
    nanos = int(round((price - units) * 1_000_000_000))
    return {"currencyCode": currency, "units": str(units), "nanos": nanos}


def ensure_managed_products(
    service: Any,
    package_name: str,
    products: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Create or update managed one-time in-app products.

    Each item in *products* must have::

        {
            "sku": "com.example.credits_3",
            "default_price": {"currency": "USD", "price": 2.99},
            "listings": {
                "en-US": {"title": "3 Credits", "description": "Buy 3 credits"},
                ...
            },
            # Optional: per-country pricing overrides
            "pricing": {
                "GB": {"currency": "GBP", "price": 1.79},
                "CA": {"currency": "CAD", "price": 2.49},
                ...
            }
        }

    Returns ``{"ok": True, "created": [...], "updated": [...], "pricing_applied": {...}}``.
    """
    monetization = service.monetization()
    created: List[str] = []
    updated: List[str] = []
    pricing_applied: Dict[str, int] = {}

    for product in products:
        sku = product["sku"]
        default_price = product.get("default_price", {})
        listings = product.get("listings", {})

        # New API uses a list of {languageCode, title, description}
        listing_entries: List[Dict[str, str]] = []
        for locale, fields in listings.items():
            entry: Dict[str, str] = {"languageCode": locale}
            if fields.get("title"):
                entry["title"] = fields["title"]
            if fields.get("description"):
                entry["description"] = fields["description"]
            if len(entry) > 1:
                listing_entries.append(entry)

        body: Dict[str, Any] = {
            "productId": sku,
            "packageName": package_name,
            "listings": listing_entries,
        }

        # Build regionalPricingAndAvailabilityConfigs from regional pricing dict.
        # Fall back to a single US entry from default_price if no regional map.
        regional_prices = product.get("pricing") or {}
        regional_configs: List[Dict[str, Any]] = [
            {
                "regionCode": country,
                "price": _price_to_money_proto(
                    info.get("currency", "USD"),
                    info.get("price", 0),
                ),
                "availability": "AVAILABLE",
            }
            for country, info in regional_prices.items()
        ]
        if not regional_configs and default_price:
            regional_configs = [{
                "regionCode": "US",
                "price": _price_to_money_proto(
                    default_price.get("currency", "USD"),
                    default_price.get("price", 0),
                ),
                "availability": "AVAILABLE",
            }]

        # Merge regional pricing into existing purchase options. Prefer
        # "legacy-base" (backwards compatible, used by existing apps) over
        # "default". Preserve all existing purchase options and newRegionsConfig.
        if regional_configs:
            new_by_region = {c["regionCode"]: c for c in regional_configs}
            target_po_id = "default"
            existing_pos: List[Dict[str, Any]] = []
            try:
                existing = _execute_with_retry(
                    monetization.onetimeproducts().get(
                        packageName=package_name, productId=sku,
                    )
                )
                existing_pos = existing.get("purchaseOptions", [])
                # Find the target purchase option: prefer legacy-base
                for po in existing_pos:
                    if po.get("purchaseOptionId") == "legacy-base":
                        target_po_id = "legacy-base"
                        break
            except Exception:
                pass  # Product doesn't exist yet

            # Build merged purchase options list
            updated_pos: List[Dict[str, Any]] = []
            target_found = False
            for po in existing_pos:
                if po.get("purchaseOptionId") == target_po_id:
                    target_found = True
                    # Merge existing regions not in our new pricing
                    for cfg in po.get("regionalPricingAndAvailabilityConfigs", []):
                        region = cfg.get("regionCode")
                        if region and region not in new_by_region:
                            new_by_region[region] = cfg
                    po["regionalPricingAndAvailabilityConfigs"] = list(new_by_region.values())
                    updated_pos.append(po)
                else:
                    updated_pos.append(po)

            if not target_found:
                # No existing product — create a new purchase option
                po_entry: Dict[str, Any] = {
                    "purchaseOptionId": target_po_id,
                    "buyOption": {"legacyCompatible": True},
                    "regionalPricingAndAvailabilityConfigs": list(new_by_region.values()),
                }
                updated_pos.append(po_entry)

            body["purchaseOptions"] = updated_pos

        # patch() with allowMissing=True is an upsert — creates or updates
        _execute_with_retry(
            monetization.onetimeproducts().patch(
                packageName=package_name, productId=sku, body=body,
                allowMissing=True, updateMask="listings,purchaseOptions",
                regionsVersion_version="2025/03",
            )
        )
        updated.append(sku)
        if regional_configs:
            pricing_applied[sku] = len(regional_configs)

    return {"ok": True, "created": created, "updated": updated, "pricing_applied": pricing_applied}


# ---------------------------------------------------------------------------
# Deactivate / delete products
# ---------------------------------------------------------------------------

def deactivate_managed_product(
    service: Any,
    package_name: str,
    sku: str,
) -> Dict[str, Any]:
    """Set a managed one-time product to inactive on Google Play.

    Google Play does not allow permanent deletion of products via the API once
    they have been published. Setting status to ``inactive`` hides the product
    from new buyers while preserving purchase history.

    Returns ``{"ok": True, "sku": str, "status": "inactive"}``.
    """
    monetization = service.monetization()
    current = _execute_with_retry(
        monetization.onetimeproducts().get(packageName=package_name, productId=sku)
    )
    body = dict(current)
    body["status"] = "INACTIVE"
    _execute_with_retry(
        monetization.onetimeproducts().patch(packageName=package_name, productId=sku, body=body)
    )
    return {"ok": True, "sku": sku, "status": "inactive"}


# ---------------------------------------------------------------------------
# Regional pricing
# ---------------------------------------------------------------------------

def apply_regional_pricing(
    service: Any,
    package_name: str,
    sku: str,
    regional_prices: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Apply regional pricing to a one-time product.

    *regional_prices* maps ``{country_code: {currency, price}}``.

    Returns ``{"ok": True, "sku": str, "regions_applied": int}``.
    """
    monetization = service.monetization()

    current = _execute_with_retry(
        monetization.onetimeproducts().get(packageName=package_name, productId=sku)
    )

    # Find the active/legacy purchase option to update pricing on.
    # Prefer "legacy-base" (backwards compatible) over "default" since
    # existing apps use the legacy purchase flow.
    po_list: List[Dict[str, Any]] = current.get("purchaseOptions") or []
    if not po_list:
        po_list = [{"purchaseOptionId": "default", "buyOption": {}}]
    default_po = next(
        (po for po in po_list if po.get("purchaseOptionId") == "legacy-base"),
        next(
            (po for po in po_list if po.get("purchaseOptionId") == "default"),
            po_list[0],
        ),
    )
    existing_configs: Dict[str, Dict[str, Any]] = {
        cfg["regionCode"]: cfg
        for cfg in default_po.get("regionalPricingAndAvailabilityConfigs", [])
        if cfg.get("regionCode")
    }

    for country, price_info in regional_prices.items():
        existing_configs[country] = {
            "regionCode": country,
            "price": _price_to_money_proto(
                price_info.get("currency", "USD"),
                price_info.get("price", 0),
            ),
            "availability": "AVAILABLE",
        }

    default_po["regionalPricingAndAvailabilityConfigs"] = list(existing_configs.values())
    current["purchaseOptions"] = po_list

    _execute_with_retry(
        monetization.onetimeproducts().patch(
            packageName=package_name, productId=sku, body=current,
            updateMask="purchaseOptions", regionsVersion_version="2025/03",
        )
    )
    return {"ok": True, "sku": sku, "regions_applied": len(regional_prices)}


def apply_subscription_regional_pricing(
    service: Any,
    package_name: str,
    subscription_id: str,
    base_plan_id: str,
    regional_prices: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Apply regional pricing to a subscription base plan.

    *regional_prices* maps ``{region_code: {currency, price}}``.

    Returns ``{"ok": True, "subscription_id": str, "regions_applied": int}``.
    """
    monetization = service.monetization()

    current = _execute_with_retry(
        monetization.subscriptions().get(
            packageName=package_name, productId=subscription_id,
        )
    )

    base_plans = current.get("basePlans", [])
    target_plan = next(
        (bp for bp in base_plans if bp.get("basePlanId") == base_plan_id),
        None,
    )
    if target_plan is None:
        raise RuntimeError(
            f"Base plan {base_plan_id!r} not found in subscription {subscription_id!r}."
        )

    regional_configs = target_plan.setdefault("regionalConfigs", [])
    existing_regions = {rc.get("regionCode"): rc for rc in regional_configs}

    for region, price_info in regional_prices.items():
        money = _price_to_money_proto(
            price_info.get("currency", "USD"),
            price_info.get("price", 0),
        )
        if region in existing_regions:
            existing_regions[region]["price"] = money
        else:
            regional_configs.append({"regionCode": region, "price": money})

    _execute_with_retry(
        monetization.subscriptions().patch(
            packageName=package_name,
            productId=subscription_id,
            body=current,
            updateMask="basePlans",
            regionsVersion_version="2025/03",
        )
    )
    return {"ok": True, "subscription_id": subscription_id, "regions_applied": len(regional_prices)}
