"""App Store Connect API client for fetching and pushing store listings."""

from __future__ import annotations

import hashlib
import logging
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

import jwt
import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App Store screenshot display types
# ---------------------------------------------------------------------------

VALID_DISPLAY_TYPES = frozenset({
    "APP_IPHONE_67",
    "APP_IPHONE_61",
    "APP_IPHONE_65",
    "APP_IPHONE_58",
    "APP_IPHONE_55",
    "APP_IPHONE_47",
    "APP_IPHONE_40",
    "APP_IPHONE_35",
    "APP_IPAD_PRO_3GEN_129",
    "APP_IPAD_PRO_3GEN_11",
    "APP_IPAD_PRO_129",
    "APP_IPAD_105",
    "APP_IPAD_97",
    "APP_WATCH_ULTRA",
    "APP_WATCH_SERIES_7",
    "APP_WATCH_SERIES_4",
    "APP_WATCH_SERIES_3",
    "APP_DESKTOP",
    "APP_APPLE_TV",
    "APP_APPLE_VISION_PRO",
})


class AppStoreConnectClient:
    """JWT-authenticated client for the App Store Connect API v1."""

    def __init__(
        self,
        key_id: str,
        issuer_id: str,
        private_key: str,
        *,
        dry_run: bool = False,
    ) -> None:
        self.key_id = key_id
        self.issuer_id = issuer_id
        self.private_key = private_key
        self.dry_run = dry_run
        self.session = requests.Session()
        self.base_url = "https://api.appstoreconnect.apple.com/v1"
        self.logger = logging.getLogger(self.__class__.__name__)

    @classmethod
    def from_key_file(
        cls,
        key_id: str,
        issuer_id: str,
        private_key_path: str,
        *,
        dry_run: bool = False,
    ) -> "AppStoreConnectClient":
        """Create a client by reading the private key from a ``.p8`` file."""
        path = Path(private_key_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Private key file not found at {path}.")
        private_key = path.read_text(encoding="utf-8")
        return cls(key_id=key_id, issuer_id=issuer_id, private_key=private_key, dry_run=dry_run)

    # ------------------------------------------------------------------
    # Core HTTP
    # ------------------------------------------------------------------

    def _authorization_header(self) -> str:
        now = datetime.now(tz=timezone.utc)
        payload = {
            "iss": self.issuer_id,
            "exp": int((now + timedelta(minutes=20)).timestamp()),
            "aud": "appstoreconnect-v1",
        }
        token = jwt.encode(
            payload,
            self.private_key,
            algorithm="ES256",
            headers={"kid": self.key_id},
        )
        return f"Bearer {token}"

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Send an authenticated request with automatic retry for transient errors."""
        # Support paths with explicit API version (e.g. /v2/...)
        if path.startswith("/v2/") or path.startswith("/v3/"):
            base_domain = self.base_url.rsplit("/v", 1)[0]
            url = f"{base_domain}{path}"
        else:
            url = f"{self.base_url}{path}"
        method_upper = (method or "GET").upper()

        if self.dry_run and method_upper not in {"GET"}:
            self.logger.info("[dry-run] Would %s %s payload=%s", method_upper, url, json_body)
            return {}

        headers = {
            "Authorization": self._authorization_header(),
            "Accept": "application/json",
        }

        max_attempts = 4
        attempt = 0
        while True:
            attempt += 1
            self.logger.debug(
                "Requesting %s %s (attempt %s/%s)",
                method_upper, path, attempt, max_attempts,
            )
            response = self.session.request(
                method_upper, url, params=params, json=json_body,
                headers=headers, timeout=30,
            )
            status = response.status_code
            self.logger.debug("Received %s %s status=%s", method_upper, path, status)

            if status < 400:
                if status == 204:
                    return {}
                return response.json()

            transient = status in {429, 500, 502, 503, 504}
            safe_to_retry = method_upper in {"GET", "PATCH"}

            if transient and safe_to_retry and attempt < max_attempts:
                if status == 429:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        wait_seconds = float(retry_after) if retry_after is not None else None
                    except ValueError:
                        wait_seconds = None
                    if wait_seconds is None:
                        wait_seconds = 1.0 * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                else:
                    wait_seconds = 1.0 * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                self.logger.warning(
                    "Transient error %s for %s %s. Retrying in %.2fs (attempt %s/%s).",
                    status, method_upper, path, wait_seconds, attempt, max_attempts,
                )
                time.sleep(wait_seconds)
                continue

            self.logger.error(
                "App Store Connect API error %s for %s %s: %s",
                status, method_upper, path, response.text[:2000],
            )
            raise RuntimeError(f"App Store Connect API error {status}: {response.text}")

    # ------------------------------------------------------------------
    # App info ID resolution
    # ------------------------------------------------------------------

    def get_app_info_id(
        self,
        app_id: str,
        platform: str = "IOS",
        preferred_states: Sequence[str] | None = None,
    ) -> str:
        """Return the current appInfo ID, preferring editable states."""
        data = self.request(
            "GET",
            f"/apps/{app_id}/appInfos",
            params={"limit": "10"},
        )
        items = [
            item for item in data.get("data", [])
            if item.get("attributes", {}).get("platform", "IOS") == platform
        ]
        if not items:
            raise RuntimeError(f"No appInfo found for app_id={app_id} platform={platform}")

        if preferred_states:
            for state in preferred_states:
                for item in items:
                    if item.get("attributes", {}).get("appStoreState") == state:
                        return item["id"]

        return items[0]["id"]

    # ------------------------------------------------------------------
    # App Store version management
    # ------------------------------------------------------------------

    def get_app_store_version_id(
        self,
        app_id: str,
        platform: str,
        version_string: str,
    ) -> str:
        """Return the appStoreVersion ID for a specific version string."""
        data = self.request(
            "GET",
            f"/apps/{app_id}/appStoreVersions",
            params={
                "filter[versionString]": version_string,
                "limit": "5",
            },
        )
        items = [
            item for item in data.get("data", [])
            if item.get("attributes", {}).get("platform", "IOS") == platform
        ]
        if not items:
            raise RuntimeError(
                f"No appStoreVersion found for app_id={app_id} "
                f"platform={platform} version={version_string}"
            )
        return items[0]["id"]

    def get_app_store_version(self, version_id: str) -> Mapping[str, Any]:
        """Get full version resource."""
        data = self.request("GET", f"/appStoreVersions/{version_id}")
        return data.get("data", {})

    def create_app_store_version(
        self,
        app_id: str,
        platform: str,
        version_string: str,
        *,
        release_type: str = "MANUAL",
        earliest_release_date: str | None = None,
    ) -> Dict[str, Any]:
        """Create a new App Store version.

        *release_type*: ``MANUAL``, ``AFTER_APPROVAL``, or ``SCHEDULED``.
        """
        attributes: Dict[str, Any] = {
            "platform": platform,
            "versionString": version_string,
            "releaseType": release_type,
        }
        if earliest_release_date and release_type == "SCHEDULED":
            attributes["earliestReleaseDate"] = earliest_release_date

        data = self.request(
            "POST",
            "/appStoreVersions",
            json_body={
                "data": {
                    "type": "appStoreVersions",
                    "attributes": attributes,
                    "relationships": {
                        "app": {"data": {"type": "apps", "id": app_id}},
                    },
                }
            },
        )
        item = data.get("data", {})
        return {
            "id": item.get("id"),
            "version_string": item.get("attributes", {}).get("versionString"),
            "state": item.get("attributes", {}).get("appStoreState"),
        }

    # ------------------------------------------------------------------
    # App info localizations (name, subtitle, privacy URL)
    # ------------------------------------------------------------------

    def list_app_info_localizations(self, app_info_id: str) -> Dict[str, Dict[str, Any]]:
        """Fetch app-info level localizations."""
        data = self.request(
            "GET",
            f"/appInfos/{app_info_id}/appInfoLocalizations",
            params={"limit": "200"},
        )
        results: Dict[str, Dict[str, Any]] = {}
        for item in data.get("data", []):
            attributes = dict(item.get("attributes", {}) or {})
            locale = attributes.get("locale")
            if locale:
                attributes["id"] = item.get("id")
                results[locale] = attributes
        return results

    def find_app_info_localization(self, app_info_id: str, locale: str) -> str | None:
        """Find localization ID for a locale, or None."""
        localizations = self.list_app_info_localizations(app_info_id)
        loc = localizations.get(locale)
        return loc.get("id") if loc else None

    def create_app_info_localization(
        self,
        app_info_id: str,
        locale: str,
        *,
        name: str | None = None,
        subtitle: str | None = None,
        privacy_policy_url: str | None = None,
    ) -> str:
        """Create an app info localization. Returns localization ID."""
        attributes: Dict[str, Any] = {"locale": locale}
        if name is not None:
            attributes["name"] = name
        if subtitle is not None:
            attributes["subtitle"] = subtitle
        if privacy_policy_url is not None:
            attributes["privacyPolicyUrl"] = privacy_policy_url

        data = self.request(
            "POST",
            "/appInfoLocalizations",
            json_body={
                "data": {
                    "type": "appInfoLocalizations",
                    "attributes": attributes,
                    "relationships": {
                        "appInfo": {"data": {"type": "appInfos", "id": app_info_id}},
                    },
                }
            },
        )
        return data.get("data", {}).get("id", "")

    def update_app_info_localization(
        self,
        localization_id: str,
        *,
        name: str | None = None,
        subtitle: str | None = None,
        privacy_policy_url: str | None = None,
    ) -> None:
        """Update an app info localization (name, subtitle, privacy URL)."""
        attributes: Dict[str, Any] = {}
        if name is not None:
            attributes["name"] = name
        if subtitle is not None:
            attributes["subtitle"] = subtitle
        if privacy_policy_url is not None:
            attributes["privacyPolicyUrl"] = privacy_policy_url

        if not attributes:
            return

        try:
            self.request(
                "PATCH",
                f"/appInfoLocalizations/{localization_id}",
                json_body={
                    "data": {
                        "type": "appInfoLocalizations",
                        "id": localization_id,
                        "attributes": attributes,
                    }
                },
            )
        except RuntimeError:
            # Retry individual attributes on failure (some fields fail together)
            for key, value in attributes.items():
                self.request(
                    "PATCH",
                    f"/appInfoLocalizations/{localization_id}",
                    json_body={
                        "data": {
                            "type": "appInfoLocalizations",
                            "id": localization_id,
                            "attributes": {key: value},
                        }
                    },
                )

    # ------------------------------------------------------------------
    # App Store version localizations (description, keywords, promo, whatsNew)
    # ------------------------------------------------------------------

    def list_app_store_version_localizations(
        self, version_id: str,
    ) -> Dict[str, Dict[str, Any]]:
        """Fetch version-level localizations."""
        data = self.request(
            "GET",
            f"/appStoreVersions/{version_id}/appStoreVersionLocalizations",
            params={"limit": "200"},
        )
        results: Dict[str, Dict[str, Any]] = {}
        for item in data.get("data", []):
            attributes = dict(item.get("attributes", {}))
            locale = attributes.get("locale")
            if locale:
                attributes["id"] = item.get("id")
                results[locale] = attributes
        return results

    def find_app_store_version_localization(self, version_id: str, locale: str) -> str | None:
        """Find version localization ID for a locale, or None."""
        localizations = self.list_app_store_version_localizations(version_id)
        loc = localizations.get(locale)
        return loc.get("id") if loc else None

    def create_app_store_version_localization(
        self,
        version_id: str,
        locale: str,
        *,
        description: str | None = None,
        keywords: str | None = None,
        promotional_text: str | None = None,
        whats_new: str | None = None,
        support_url: str | None = None,
        marketing_url: str | None = None,
    ) -> str:
        """Create a version localization. Returns localization ID."""
        attributes: Dict[str, Any] = {"locale": locale}
        if description is not None:
            attributes["description"] = description
        if keywords is not None:
            attributes["keywords"] = keywords
        if promotional_text is not None:
            attributes["promotionalText"] = promotional_text
        if whats_new is not None:
            attributes["whatsNew"] = whats_new
        if support_url is not None:
            attributes["supportUrl"] = support_url
        if marketing_url is not None:
            attributes["marketingUrl"] = marketing_url

        data = self.request(
            "POST",
            "/appStoreVersionLocalizations",
            json_body={
                "data": {
                    "type": "appStoreVersionLocalizations",
                    "attributes": attributes,
                    "relationships": {
                        "appStoreVersion": {
                            "data": {"type": "appStoreVersions", "id": version_id}
                        },
                    },
                }
            },
        )
        return data.get("data", {}).get("id", "")

    def update_app_store_version_localization(
        self,
        localization_id: str,
        *,
        description: str | None = None,
        keywords: str | None = None,
        promotional_text: str | None = None,
        whats_new: str | None = None,
        support_url: str | None = None,
        marketing_url: str | None = None,
    ) -> None:
        """Update a version localization."""
        attributes: Dict[str, Any] = {}
        if description is not None:
            attributes["description"] = description
        if keywords is not None:
            attributes["keywords"] = keywords
        if promotional_text is not None:
            attributes["promotionalText"] = promotional_text
        if whats_new is not None:
            attributes["whatsNew"] = whats_new
        if support_url is not None:
            attributes["supportUrl"] = support_url
        if marketing_url is not None:
            attributes["marketingUrl"] = marketing_url

        if not attributes:
            return

        self.request(
            "PATCH",
            f"/appStoreVersionLocalizations/{localization_id}",
            json_body={
                "data": {
                    "type": "appStoreVersionLocalizations",
                    "id": localization_id,
                    "attributes": attributes,
                }
            },
        )

    def update_whats_new(self, localization_id: str, whats_new: str) -> None:
        """Update only the What's New field on a version localization."""
        self.update_app_store_version_localization(
            localization_id, whats_new=whats_new,
        )

    # ------------------------------------------------------------------
    # Screenshot management
    # ------------------------------------------------------------------

    def list_app_screenshot_sets(
        self, version_localization_id: str,
    ) -> List[Dict[str, Any]]:
        """List screenshot sets for a version localization."""
        data = self.request(
            "GET",
            f"/appStoreVersionLocalizations/{version_localization_id}/appScreenshotSets",
            params={"limit": "50"},
        )
        return list(data.get("data", []))

    def create_app_screenshot_set(
        self, version_localization_id: str, display_type: str,
    ) -> str:
        """Create a screenshot set. Returns set ID."""
        data = self.request(
            "POST",
            "/appScreenshotSets",
            json_body={
                "data": {
                    "type": "appScreenshotSets",
                    "attributes": {"screenshotDisplayType": display_type},
                    "relationships": {
                        "appStoreVersionLocalization": {
                            "data": {
                                "type": "appStoreVersionLocalizations",
                                "id": version_localization_id,
                            }
                        }
                    },
                }
            },
        )
        return data.get("data", {}).get("id", "")

    def list_app_screenshots(self, screenshot_set_id: str) -> List[Dict[str, Any]]:
        """List screenshots in a set."""
        data = self.request(
            "GET",
            f"/appScreenshotSets/{screenshot_set_id}/appScreenshots",
            params={"limit": "50"},
        )
        return list(data.get("data", []))

    def delete_app_screenshot(self, screenshot_id: str) -> None:
        """Delete a screenshot."""
        self.request("DELETE", f"/appScreenshots/{screenshot_id}")

    def create_app_screenshot(
        self, screenshot_set_id: str, file_name: str, file_size: int,
    ) -> Dict[str, Any]:
        """Reserve a screenshot upload slot. Returns resource with uploadOperations."""
        data = self.request(
            "POST",
            "/appScreenshots",
            json_body={
                "data": {
                    "type": "appScreenshots",
                    "attributes": {"fileName": file_name, "fileSize": file_size},
                    "relationships": {
                        "appScreenshotSet": {
                            "data": {"type": "appScreenshotSets", "id": screenshot_set_id}
                        }
                    },
                }
            },
        )
        return dict(data.get("data", {}))

    def perform_upload_operation(
        self, operation: Mapping[str, Any], chunk: bytes,
    ) -> None:
        """Execute a single upload operation (PUT to S3 presigned URL)."""
        url = operation["url"]
        method = operation.get("method", "PUT")
        req_headers = {
            h["name"]: h["value"]
            for h in operation.get("requestHeaders", [])
        }
        response = self.session.request(
            method, url, headers=req_headers, data=chunk, timeout=120,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Upload operation failed {response.status_code}: {response.text[:500]}"
            )

    def complete_app_screenshot_upload(
        self, screenshot_id: str, checksum: str,
    ) -> None:
        """Mark a screenshot upload as complete."""
        self.request(
            "PATCH",
            f"/appScreenshots/{screenshot_id}",
            json_body={
                "data": {
                    "type": "appScreenshots",
                    "id": screenshot_id,
                    "attributes": {
                        "uploaded": True,
                        "sourceFileChecksum": checksum,
                    },
                }
            },
        )

    # ------------------------------------------------------------------
    # In-app purchase enumeration (fetch all)
    # ------------------------------------------------------------------

    def list_all_in_app_purchases(self, app_id: str) -> List[Dict[str, Any]]:
        """Fetch all in-app purchases for an app, handling pagination."""
        results: List[Dict[str, Any]] = []
        path = f"/apps/{app_id}/inAppPurchasesV2"
        params = {"limit": "200"}
        while path:
            data = self.request("GET", path, params=params)
            results.extend(data.get("data", []))
            next_link = data.get("links", {}).get("next")
            if next_link and isinstance(next_link, str):
                # For paginated results, the next link is a full URL;
                # extract path after base_url
                if next_link.startswith(self.base_url):
                    path = next_link[len(self.base_url):]
                else:
                    break
                params = None  # params are embedded in the next URL path
            else:
                break
        return results

    def list_all_subscription_groups(self, app_id: str) -> List[Dict[str, Any]]:
        """Fetch all subscription groups for an app."""
        data = self.request(
            "GET",
            f"/apps/{app_id}/subscriptionGroups",
            params={"limit": "200"},
        )
        return list(data.get("data", []))

    def list_subscriptions_in_group(self, group_id: str) -> List[Dict[str, Any]]:
        """Fetch all subscriptions within a subscription group."""
        data = self.request(
            "GET",
            f"/subscriptionGroups/{group_id}/subscriptions",
            params={"limit": "200"},
        )
        return list(data.get("data", []))

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------

    def fetch_iap_pricing(self, iap_id: str) -> Dict[str, Dict]:
        """Fetch pricing for an in-app purchase across all territories."""
        # Step 1: Get the price schedule (v2 endpoint)
        schedule_data = self.request(
            "GET", f"/v2/inAppPurchases/{iap_id}/iapPriceSchedule",
        )
        schedule_id = schedule_data.get("data", {}).get("id")
        if not schedule_id:
            return {}

        # Step 2: Fetch manual prices with pagination
        all_data: List[Dict[str, Any]] = []
        all_included: List[Dict[str, Any]] = []
        path: str | None = (
            f"/inAppPurchasePriceSchedules/{schedule_id}/manualPrices"
        )
        params: Dict[str, str] | None = {
            "include": "inAppPurchasePricePoint,territory",
            "limit": "200",
        }
        while path:
            resp = self.request("GET", path, params=params)
            all_data.extend(resp.get("data", []))
            all_included.extend(resp.get("included", []))
            next_link = resp.get("links", {}).get("next")
            if (
                next_link
                and isinstance(next_link, str)
                and next_link.startswith(self.base_url)
            ):
                path = next_link[len(self.base_url):]
                params = None
            else:
                break

        return _parse_pricing_response(
            {"data": all_data, "included": all_included},
        )

    def fetch_subscription_pricing(
        self, subscription_id: str,
    ) -> Dict[str, Dict]:
        """Fetch pricing for a subscription across all territories."""
        all_data: List[Dict[str, Any]] = []
        all_included: List[Dict[str, Any]] = []
        path: str | None = f"/subscriptions/{subscription_id}/prices"
        params: Dict[str, str] | None = {
            "include": "subscriptionPricePoint,territory",
            "limit": "200",
        }
        while path:
            resp = self.request("GET", path, params=params)
            all_data.extend(resp.get("data", []))
            all_included.extend(resp.get("included", []))
            next_link = resp.get("links", {}).get("next")
            if (
                next_link
                and isinstance(next_link, str)
                and next_link.startswith(self.base_url)
            ):
                path = next_link[len(self.base_url):]
                params = None
            else:
                break

        return _parse_pricing_response(
            {"data": all_data, "included": all_included},
        )

    # ------------------------------------------------------------------
    # In-app purchase management
    # ------------------------------------------------------------------

    def find_in_app_purchase_id(self, app_id: str, product_id: str) -> str | None:
        """Find the IAP resource ID for a given product ID."""
        data = self.request(
            "GET",
            f"/apps/{app_id}/inAppPurchasesV2",
            params={"filter[productId]": product_id, "limit": "5"},
        )
        items = data.get("data", [])
        if items:
            return items[0]["id"]
        return None

    def list_in_app_purchase_localizations(
        self, iap_id: str,
    ) -> Dict[str, Dict[str, Any]]:
        """List localizations for an in-app purchase."""
        data = self.request(
            "GET",
            f"/inAppPurchases/{iap_id}/inAppPurchaseLocalizations",
            params={"limit": "200"},
        )
        results: Dict[str, Dict[str, Any]] = {}
        for item in data.get("data", []):
            attributes = dict(item.get("attributes", {}))
            locale = attributes.get("locale")
            if locale:
                attributes["id"] = item.get("id")
                results[locale] = attributes
        return results

    def create_in_app_purchase_localization(
        self,
        iap_id: str,
        locale: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> str:
        """Create an IAP localization. Returns localization ID."""
        attributes: Dict[str, Any] = {"locale": locale}
        if name is not None:
            attributes["name"] = name
        if description is not None:
            attributes["description"] = description

        data = self.request(
            "POST",
            "/inAppPurchaseLocalizations",
            json_body={
                "data": {
                    "type": "inAppPurchaseLocalizations",
                    "attributes": attributes,
                    "relationships": {
                        "inAppPurchaseV2": {
                            "data": {"type": "inAppPurchases", "id": iap_id}
                        },
                    },
                }
            },
        )
        return data.get("data", {}).get("id", "")

    def update_in_app_purchase_localization(
        self,
        localization_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        """Update an IAP localization."""
        attributes: Dict[str, Any] = {}
        if name is not None:
            attributes["name"] = name
        if description is not None:
            attributes["description"] = description
        if not attributes:
            return

        self.request(
            "PATCH",
            f"/inAppPurchaseLocalizations/{localization_id}",
            json_body={
                "data": {
                    "type": "inAppPurchaseLocalizations",
                    "id": localization_id,
                    "attributes": attributes,
                }
            },
        )

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def find_subscription_id(self, app_id: str, product_id: str) -> str | None:
        """Find the subscription resource ID for a product ID.

        Searches subscription groups then individual subscriptions.
        """
        groups_data = self.request(
            "GET",
            f"/apps/{app_id}/subscriptionGroups",
            params={"limit": "50"},
        )
        for group in groups_data.get("data", []):
            group_id = group["id"]
            subs_data = self.request(
                "GET",
                f"/subscriptionGroups/{group_id}/subscriptions",
                params={"limit": "50"},
            )
            for sub in subs_data.get("data", []):
                if sub.get("attributes", {}).get("productId") == product_id:
                    return sub["id"]
        return None

    def list_subscription_localizations(
        self, subscription_id: str,
    ) -> Dict[str, Dict[str, Any]]:
        """List localizations for a subscription."""
        data = self.request(
            "GET",
            f"/subscriptions/{subscription_id}/subscriptionLocalizations",
            params={"limit": "200"},
        )
        results: Dict[str, Dict[str, Any]] = {}
        for item in data.get("data", []):
            attributes = dict(item.get("attributes", {}))
            locale = attributes.get("locale")
            if locale:
                attributes["id"] = item.get("id")
                results[locale] = attributes
        return results

    def create_subscription_localization(
        self,
        subscription_id: str,
        locale: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> str:
        """Create a subscription localization. Returns localization ID."""
        attributes: Dict[str, Any] = {"locale": locale}
        if name is not None:
            attributes["name"] = name
        if description is not None:
            attributes["description"] = description

        data = self.request(
            "POST",
            "/subscriptionLocalizations",
            json_body={
                "data": {
                    "type": "subscriptionLocalizations",
                    "attributes": attributes,
                    "relationships": {
                        "subscription": {
                            "data": {"type": "subscriptions", "id": subscription_id}
                        },
                    },
                }
            },
        )
        return data.get("data", {}).get("id", "")

    def update_subscription_localization(
        self,
        localization_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        """Update a subscription localization."""
        attributes: Dict[str, Any] = {}
        if name is not None:
            attributes["name"] = name
        if description is not None:
            attributes["description"] = description
        if not attributes:
            return

        self.request(
            "PATCH",
            f"/subscriptionLocalizations/{localization_id}",
            json_body={
                "data": {
                    "type": "subscriptionLocalizations",
                    "id": localization_id,
                    "attributes": attributes,
                }
            },
        )


# ======================================================================
# Top-level orchestration functions
# ======================================================================

def fetch_listings(
    client: AppStoreConnectClient,
    app_id: str,
    platform: str = "IOS",
    version_string: str | None = None,
    locales: Sequence[str] | None = None,
) -> Dict[str, Any]:
    """Fetch App Store listings and return global data + merged dict per locale.

    Returns ``{"global": {...}, "locales": {locale: {app_name, subtitle, description, keywords, …}}}``.
    """
    # Fetch app-level info (primaryLocale, bundleId, etc.)
    global_data: Dict[str, str] = {}
    try:
        app_data = client.request("GET", f"/apps/{app_id}")
        app_attrs = app_data.get("data", {}).get("attributes", {})
        if app_attrs.get("primaryLocale"):
            global_data["primary_locale"] = app_attrs["primaryLocale"]
        if app_attrs.get("bundleId"):
            global_data["bundle_id"] = app_attrs["bundleId"]
        if app_attrs.get("sku"):
            global_data["sku"] = app_attrs["sku"]
    except Exception:
        logger.warning("Could not fetch app-level info for app_id=%s", app_id)

    app_info_id = client.get_app_info_id(app_id, platform)
    app_info_localizations = client.list_app_info_localizations(app_info_id)

    version_localizations: Dict[str, Dict[str, Any]] = {}
    if version_string:
        version_id = client.get_app_store_version_id(app_id, platform, version_string)
        version_localizations = client.list_app_store_version_localizations(version_id)

    if locales:
        requested = set(locales)
        app_info_localizations = {k: v for k, v in app_info_localizations.items() if k in requested}
        version_localizations = {k: v for k, v in version_localizations.items() if k in requested}

    all_locales = set(app_info_localizations.keys()) | set(version_localizations.keys())
    merged: Dict[str, Dict[str, Any]] = {}

    for locale in sorted(all_locales):
        entry: Dict[str, Any] = {}

        info = app_info_localizations.get(locale, {})
        if info.get("name"):
            entry["app_name"] = info["name"]
        if info.get("subtitle"):
            entry["subtitle"] = info["subtitle"]
        if info.get("privacyPolicyUrl"):
            entry["privacy_url"] = info["privacyPolicyUrl"]

        ver = version_localizations.get(locale, {})
        if ver.get("description"):
            entry["description"] = ver["description"]
        if ver.get("keywords"):
            entry["keywords"] = ver["keywords"]
        if ver.get("promotionalText"):
            entry["promotional_text"] = ver["promotionalText"]
        if ver.get("whatsNew"):
            entry["whats_new"] = ver["whatsNew"]
        if ver.get("supportUrl"):
            entry["support_url"] = ver["supportUrl"]
        if ver.get("marketingUrl"):
            entry["marketing_url"] = ver["marketingUrl"]

        if entry:
            merged[locale] = entry

    return {"global": global_data, "locales": merged}


def push_listings(
    client: AppStoreConnectClient,
    app_id: str,
    platform: str,
    version_string: str,
    locales_data: Dict[str, Dict[str, Any]],
    *,
    only_whats_new: bool = False,
) -> Dict[str, Any]:
    """Push local listing data to App Store Connect.

    *locales_data* maps ``{locale: {app_name, subtitle, description, …}}``.

    When *only_whats_new* is True, only the ``whats_new`` field is updated.

    Returns ``{"ok": True, "updated_locales": [...], "created_locales": [...]}``.
    """
    app_info_id = client.get_app_info_id(
        app_id, platform,
        preferred_states=["PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED"],
    )
    version_id = client.get_app_store_version_id(app_id, platform, version_string)

    existing_info = client.list_app_info_localizations(app_info_id)
    existing_version = client.list_app_store_version_localizations(version_id)

    updated_locales: List[str] = []
    created_locales: List[str] = []

    for locale, fields in sorted(locales_data.items()):
        # --- App Info localization (name, subtitle, privacy) ---
        if not only_whats_new:
            info_attrs: Dict[str, str | None] = {}
            if fields.get("app_name"):
                info_attrs["name"] = fields["app_name"]
            if fields.get("subtitle"):
                info_attrs["subtitle"] = fields["subtitle"]
            if fields.get("privacy_url"):
                info_attrs["privacy_policy_url"] = fields["privacy_url"]

            if info_attrs:
                existing = existing_info.get(locale)
                if existing and existing.get("id"):
                    client.update_app_info_localization(existing["id"], **info_attrs)
                else:
                    client.create_app_info_localization(app_info_id, locale, **info_attrs)

        # --- Version localization (description, keywords, promo, whatsNew) ---
        ver_attrs: Dict[str, str | None] = {}
        if only_whats_new:
            if fields.get("whats_new"):
                ver_attrs["whats_new"] = fields["whats_new"]
        else:
            if fields.get("description"):
                ver_attrs["description"] = fields["description"]
            if fields.get("keywords"):
                ver_attrs["keywords"] = fields["keywords"]
            if fields.get("promotional_text"):
                ver_attrs["promotional_text"] = fields["promotional_text"]
            if fields.get("whats_new"):
                ver_attrs["whats_new"] = fields["whats_new"]
            if fields.get("support_url"):
                ver_attrs["support_url"] = fields["support_url"]
            if fields.get("marketing_url"):
                ver_attrs["marketing_url"] = fields["marketing_url"]

        if ver_attrs:
            existing = existing_version.get(locale)
            if existing and existing.get("id"):
                client.update_app_store_version_localization(existing["id"], **ver_attrs)
                updated_locales.append(locale)
            else:
                client.create_app_store_version_localization(
                    version_id, locale, **ver_attrs,
                )
                created_locales.append(locale)

    return {"ok": True, "updated_locales": updated_locales, "created_locales": created_locales}


def upload_screenshots(
    client: AppStoreConnectClient,
    version_localization_id: str,
    display_type: str,
    file_paths: Sequence[str | Path],
    *,
    replace: bool = True,
) -> Dict[str, Any]:
    """Upload screenshots for one version localization + display type.

    Returns ``{"ok": True, "uploaded": int, "deleted": int}``.
    """
    paths = [Path(p) for p in file_paths]
    for p in paths:
        if not p.exists():
            raise FileNotFoundError(f"Screenshot file not found: {p}")

    # Find or create the screenshot set
    existing_sets = client.list_app_screenshot_sets(version_localization_id)
    set_id: str | None = None
    for s in existing_sets:
        if s.get("attributes", {}).get("screenshotDisplayType") == display_type:
            set_id = s["id"]
            break

    if set_id is None:
        set_id = client.create_app_screenshot_set(version_localization_id, display_type)

    deleted = 0
    if replace:
        existing = client.list_app_screenshots(set_id)
        for ss in existing:
            client.delete_app_screenshot(ss["id"])
            deleted += 1

    uploaded = 0
    for file_path in paths:
        file_bytes = file_path.read_bytes()
        file_size = len(file_bytes)
        md5_hash = hashlib.md5(file_bytes).hexdigest()

        ss_data = client.create_app_screenshot(set_id, file_path.name, file_size)
        ss_id = ss_data.get("id", "")
        upload_ops = ss_data.get("attributes", {}).get("uploadOperations", [])

        for op in upload_ops:
            offset = op.get("offset", 0)
            length = op.get("length", file_size)
            chunk = file_bytes[offset:offset + length]
            client.perform_upload_operation(op, chunk)

        client.complete_app_screenshot_upload(ss_id, md5_hash)
        uploaded += 1

    return {"ok": True, "uploaded": uploaded, "deleted": deleted}


def _parse_pricing_response(response_data: dict) -> Dict[str, Dict]:
    """Parse a JSON:API pricing response into ``{territory_id: {currency, price}}``.

    Filters out future-dated prices (``startDate`` is not ``null``).
    """
    data_items = response_data.get("data", [])
    included_items = response_data.get("included", [])

    # Build lookup: (type, id) → attributes
    included_lookup: Dict[tuple, Dict[str, Any]] = {}
    for item in included_items:
        key = (item.get("type", ""), item.get("id", ""))
        included_lookup[key] = item.get("attributes", {})

    pricing: Dict[str, Dict] = {}
    for price in data_items:
        attrs = price.get("attributes", {})
        # Skip future-dated prices
        if attrs.get("startDate") is not None:
            continue

        relationships = price.get("relationships", {})

        # Resolve territory
        territory_ref = relationships.get("territory", {}).get("data", {})
        territory_id = territory_ref.get("id", "")
        if not territory_id:
            continue

        territory_attrs = included_lookup.get(
            ("territories", territory_id), {},
        )
        currency = territory_attrs.get("currency", "")

        # Resolve price point (IAP or subscription)
        price_point_ref = (
            relationships.get("inAppPurchasePricePoint", {}).get("data")
            or relationships.get("subscriptionPricePoint", {}).get("data")
            or {}
        )
        price_point_type = price_point_ref.get("type", "")
        price_point_id = price_point_ref.get("id", "")
        if not price_point_id:
            continue

        price_point_attrs = included_lookup.get(
            (price_point_type, price_point_id), {},
        )
        customer_price_str = price_point_attrs.get("customerPrice", "")

        if not customer_price_str or not currency:
            continue

        try:
            customer_price = float(customer_price_str)
        except (ValueError, TypeError):
            continue

        pricing[territory_id] = {"currency": currency, "price": customer_price}

    return pricing


def fetch_iap_and_subscriptions(
    client: AppStoreConnectClient,
    app_id: str,
) -> Dict[str, Any]:
    """Fetch all IAPs and subscriptions with their localizations.

    Returns ``{"products": {product_id: {...}}, "subscriptions": {product_id: {...}}}``.
    """
    products: Dict[str, Any] = {}
    subscriptions: Dict[str, Any] = {}

    # --- In-app purchases ---
    try:
        iap_items = client.list_all_in_app_purchases(app_id)
        for item in iap_items:
            iap_id = item.get("id")
            attrs = item.get("attributes", {})
            product_id = attrs.get("productId")
            if not iap_id or not product_id:
                continue

            iap_type = attrs.get("inAppPurchaseType", "")
            type_label = "consumable" if iap_type == "CONSUMABLE" else (
                "non_consumable" if iap_type == "NON_CONSUMABLE" else iap_type.lower()
            )

            entry: Dict[str, Any] = {"type": type_label}

            # Fetch localizations
            try:
                localizations = client.list_in_app_purchase_localizations(iap_id)
                locs: Dict[str, Dict[str, str]] = {}
                for locale, loc_data in localizations.items():
                    loc_entry: Dict[str, str] = {}
                    if loc_data.get("name"):
                        loc_entry["name"] = loc_data["name"]
                    if loc_data.get("description"):
                        loc_entry["description"] = loc_data["description"]
                    if loc_entry:
                        locs[locale] = loc_entry
                if locs:
                    entry["localizations"] = locs
            except Exception:
                logger.warning("Could not fetch localizations for IAP %s", product_id)

            # Fetch pricing
            try:
                pricing = client.fetch_iap_pricing(iap_id)
                if pricing:
                    entry["pricing"] = pricing
            except Exception:
                logger.warning("Could not fetch pricing for IAP %s", product_id)

            products[product_id] = entry
    except Exception:
        logger.warning("Could not fetch in-app purchases for app_id=%s", app_id)

    # --- Subscriptions ---
    try:
        groups = client.list_all_subscription_groups(app_id)
        for group in groups:
            group_id = group.get("id")
            group_name = group.get("attributes", {}).get("referenceName", "")
            if not group_id:
                continue

            try:
                subs = client.list_subscriptions_in_group(group_id)
            except Exception:
                logger.warning("Could not fetch subscriptions for group %s", group_id)
                continue

            for sub in subs:
                sub_id = sub.get("id")
                sub_attrs = sub.get("attributes", {})
                sub_product_id = sub_attrs.get("productId")
                if not sub_id or not sub_product_id:
                    continue

                sub_entry: Dict[str, Any] = {}
                if group_name:
                    sub_entry["group_name"] = group_name

                # Fetch localizations
                try:
                    sub_locs = client.list_subscription_localizations(sub_id)
                    locs_map: Dict[str, Dict[str, str]] = {}
                    for locale, loc_data in sub_locs.items():
                        loc_entry_sub: Dict[str, str] = {}
                        if loc_data.get("name"):
                            loc_entry_sub["name"] = loc_data["name"]
                        if loc_data.get("description"):
                            loc_entry_sub["description"] = loc_data["description"]
                        if loc_entry_sub:
                            locs_map[locale] = loc_entry_sub
                    if locs_map:
                        sub_entry["localizations"] = locs_map
                except Exception:
                    logger.warning("Could not fetch localizations for subscription %s", sub_product_id)

                # Fetch pricing
                try:
                    pricing = client.fetch_subscription_pricing(sub_id)
                    if pricing:
                        sub_entry["pricing"] = pricing
                except Exception:
                    logger.warning("Could not fetch pricing for subscription %s", sub_product_id)

                subscriptions[sub_product_id] = sub_entry
    except Exception:
        logger.warning("Could not fetch subscription groups for app_id=%s", app_id)

    return {"products": products, "subscriptions": subscriptions}


def sync_iap_localizations(
    client: AppStoreConnectClient,
    app_id: str,
    products: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Sync in-app purchase localizations.

    Each item in *products*::

        {"product_id": "com.example.credits", "localizations": {
            "en-US": {"name": "3 Credits", "description": "Buy 3"},
            ...
        }}

    Returns ``{"ok": True, "created": int, "updated": int, "missing_products": [...]}``.
    """
    created_count = 0
    updated_count = 0
    missing: List[str] = []

    for product in products:
        product_id = product["product_id"]
        localizations = product.get("localizations", {})

        iap_id = client.find_in_app_purchase_id(app_id, product_id)
        if iap_id is None:
            missing.append(product_id)
            continue

        existing = client.list_in_app_purchase_localizations(iap_id)

        for locale, fields in sorted(localizations.items()):
            name = fields.get("name")
            description = fields.get("description")

            remote = existing.get(locale)
            if remote and remote.get("id"):
                client.update_in_app_purchase_localization(
                    remote["id"], name=name, description=description,
                )
                updated_count += 1
            else:
                client.create_in_app_purchase_localization(
                    iap_id, locale, name=name, description=description,
                )
                created_count += 1

    return {
        "ok": True,
        "created": created_count,
        "updated": updated_count,
        "missing_products": missing,
    }


def sync_subscription_localizations(
    client: AppStoreConnectClient,
    app_id: str,
    subscriptions: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Sync subscription localizations.

    Each item in *subscriptions*::

        {"product_id": "com.example.premium", "localizations": {
            "en-US": {"name": "Premium", "description": "Premium access"},
            ...
        }}

    Returns ``{"ok": True, "created": int, "updated": int, "missing_subscriptions": [...]}``.
    """
    created_count = 0
    updated_count = 0
    missing: List[str] = []

    for sub in subscriptions:
        product_id = sub["product_id"]
        localizations = sub.get("localizations", {})

        sub_id = client.find_subscription_id(app_id, product_id)
        if sub_id is None:
            missing.append(product_id)
            continue

        existing = client.list_subscription_localizations(sub_id)

        for locale, fields in sorted(localizations.items()):
            name = fields.get("name")
            description = fields.get("description")

            remote = existing.get(locale)
            if remote and remote.get("id"):
                client.update_subscription_localization(
                    remote["id"], name=name, description=description,
                )
                updated_count += 1
            else:
                client.create_subscription_localization(
                    sub_id, locale, name=name, description=description,
                )
                created_count += 1

    return {
        "ok": True,
        "created": created_count,
        "updated": updated_count,
        "missing_subscriptions": missing,
    }
