"""App Store Connect API client for fetching and pushing store listings."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import logging
import mimetypes
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
        if path.startswith("/v1/") or path.startswith("/v2/") or path.startswith("/v3/"):
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

    def request_raw(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        accept: str = "*/*",
    ) -> bytes:
        """Send an authenticated request and return the raw response bytes."""
        if path.startswith("http://") or path.startswith("https://"):
            url = path
        elif path.startswith("/v1/") or path.startswith("/v2/") or path.startswith("/v3/"):
            base_domain = self.base_url.rsplit("/v", 1)[0]
            url = f"{base_domain}{path}"
        else:
            url = f"{self.base_url}{path}"
        method_upper = (method or "GET").upper()
        headers = {
            "Authorization": self._authorization_header(),
            "Accept": accept,
        }

        max_attempts = 4
        attempt = 0
        while True:
            attempt += 1
            response = self.session.request(
                method_upper, url, params=params, headers=headers, timeout=60,
            )
            status = response.status_code
            if status < 400:
                return response.content

            transient = status in {429, 500, 502, 503, 504}
            if transient and method_upper == "GET" and attempt < max_attempts:
                retry_after = response.headers.get("Retry-After")
                try:
                    wait_seconds = float(retry_after) if retry_after is not None else None
                except ValueError:
                    wait_seconds = None
                if wait_seconds is None:
                    wait_seconds = 1.0 * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                time.sleep(wait_seconds)
                continue

            raise RuntimeError(f"App Store Connect API error {status}: {response.text}")

    # ------------------------------------------------------------------
    # App lookup
    # ------------------------------------------------------------------

    def find_app_id_by_bundle_id(self, bundle_id: str) -> str | None:
        """Return the numeric App Store app ID for the given bundle ID, or None if not found."""
        data = self.request(
            "GET",
            "/apps",
            params={"filter[bundleId]": bundle_id, "fields[apps]": "bundleId,name", "limit": "5"},
        )
        items = data.get("data", [])
        if not items:
            return None
        return items[0]["id"]

    # ------------------------------------------------------------------
    # Reporting and analytics
    # ------------------------------------------------------------------

    def download_sales_report(
        self,
        *,
        vendor_number: str,
        report_type: str = "SALES",
        report_sub_type: str = "SUMMARY",
        frequency: str = "DAILY",
        report_date: str | None = None,
        version: str | None = None,
    ) -> bytes:
        """Download a gzip Sales and Trends report from App Store Connect."""
        params = {
            "filter[vendorNumber]": vendor_number,
            "filter[reportType]": report_type,
            "filter[reportSubType]": report_sub_type,
            "filter[frequency]": frequency,
        }
        if report_date:
            params["filter[reportDate]"] = report_date
        if version:
            params["filter[version]"] = version
        return self.request_raw("GET", "/salesReports", params=params, accept="application/a-gzip")

    def request_analytics_reports(self, app_id: str, access_type: str = "ONGOING") -> Mapping[str, Any]:
        """Create an Analytics Reports request for an app."""
        return self.request(
            "POST",
            "/analyticsReportRequests",
            json_body={
                "data": {
                    "type": "analyticsReportRequests",
                    "attributes": {"accessType": access_type},
                    "relationships": {
                        "app": {"data": {"type": "apps", "id": app_id}},
                    },
                },
            },
        )

    def list_analytics_report_requests(
        self,
        app_id: str,
        *,
        access_type: str | None = None,
        limit: int = 50,
    ) -> Mapping[str, Any]:
        """List Analytics Reports requests already configured for an app."""
        params = {"limit": str(limit)}
        if access_type:
            params["filter[accessType]"] = access_type
        return self.request("GET", f"/apps/{app_id}/analyticsReportRequests", params=params)

    def list_analytics_reports(self, request_id: str, *, limit: int = 200) -> Mapping[str, Any]:
        """List report definitions generated for an Analytics Reports request."""
        return self.request("GET", f"/analyticsReportRequests/{request_id}/reports", params={"limit": str(limit)})

    def list_analytics_report_instances(
        self,
        report_id: str,
        *,
        granularity: str | None = None,
        processing_date: str | None = None,
        limit: int = 200,
    ) -> Mapping[str, Any]:
        """List downloadable instances for one Analytics report."""
        params = {"limit": str(limit)}
        if granularity:
            params["filter[granularity]"] = granularity
        if processing_date:
            params["filter[processingDate]"] = processing_date
        return self.request("GET", f"/analyticsReports/{report_id}/instances", params=params)

    def list_analytics_report_segments(self, instance_id: str, *, limit: int = 200) -> Mapping[str, Any]:
        """List downloadable file segments for one Analytics report instance."""
        return self.request("GET", f"/analyticsReportInstances/{instance_id}/segments", params={"limit": str(limit)})

    def get_analytics_report_segment(self, segment_id: str) -> Mapping[str, Any]:
        """Read segment metadata, including Apple's download URL when available."""
        return self.request("GET", f"/analyticsReportSegments/{segment_id}")

    def download_analytics_report_segment(self, segment_id: str) -> bytes:
        """Download one compressed Analytics report segment."""
        metadata = self.get_analytics_report_segment(segment_id)
        segment = metadata.get("data", {})
        attributes = segment.get("attributes", {}) if isinstance(segment, Mapping) else {}
        url = attributes.get("url")
        if not url:
            links = segment.get("links", {}) if isinstance(segment, Mapping) else {}
            url = links.get("self")
        if not url:
            raise RuntimeError(f"No download URL found for analytics report segment {segment_id}.")
        return self.request_raw("GET", str(url), accept="application/a-gzip")

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
        self,
        version_localization_id: str,
        *,
        target_type: str = "appStoreVersionLocalizations",
    ) -> List[Dict[str, Any]]:
        """List screenshot sets for a version, custom page, or experiment localization."""
        path_prefix = {
            "appStoreVersionLocalizations": "appStoreVersionLocalizations",
            "appCustomProductPageLocalizations": "appCustomProductPageLocalizations",
            "appStoreVersionExperimentTreatmentLocalizations": "appStoreVersionExperimentTreatmentLocalizations",
        }.get(target_type)
        if path_prefix is None:
            raise ValueError(f"Unsupported screenshot localization target_type: {target_type}")
        data = self.request(
            "GET",
            f"/{path_prefix}/{version_localization_id}/appScreenshotSets",
            params={"limit": "50"},
        )
        return list(data.get("data", []))

    def create_app_screenshot_set(
        self,
        version_localization_id: str,
        display_type: str,
        *,
        target_type: str = "appStoreVersionLocalizations",
    ) -> str:
        """Create a screenshot set for a version, custom page, or experiment localization."""
        relationship_name = {
            "appStoreVersionLocalizations": "appStoreVersionLocalization",
            "appCustomProductPageLocalizations": "appCustomProductPageLocalization",
            "appStoreVersionExperimentTreatmentLocalizations": "appStoreVersionExperimentTreatmentLocalization",
        }.get(target_type)
        if relationship_name is None:
            raise ValueError(f"Unsupported screenshot localization target_type: {target_type}")
        data = self.request(
            "POST",
            "/appScreenshotSets",
            json_body={
                "data": {
                    "type": "appScreenshotSets",
                    "attributes": {"screenshotDisplayType": display_type},
                    "relationships": {
                        relationship_name: {
                            "data": {
                                "type": target_type,
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
    # App preview management
    # ------------------------------------------------------------------

    def list_app_preview_sets(
        self,
        version_localization_id: str,
        *,
        target_type: str = "appStoreVersionLocalizations",
    ) -> List[Dict[str, Any]]:
        """List app preview sets for a version, custom page, or experiment localization."""
        path_prefix = {
            "appStoreVersionLocalizations": "appStoreVersionLocalizations",
            "appCustomProductPageLocalizations": "appCustomProductPageLocalizations",
            "appStoreVersionExperimentTreatmentLocalizations": "appStoreVersionExperimentTreatmentLocalizations",
        }.get(target_type)
        if path_prefix is None:
            raise ValueError(f"Unsupported app preview localization target_type: {target_type}")
        data = self.request(
            "GET",
            f"/{path_prefix}/{version_localization_id}/appPreviewSets",
            params={"limit": "50"},
        )
        return list(data.get("data", []))

    def create_app_preview_set(
        self,
        version_localization_id: str,
        preview_type: str,
        *,
        target_type: str = "appStoreVersionLocalizations",
    ) -> str:
        """Create an app preview set for a version, custom page, or experiment localization."""
        relationship_name = {
            "appStoreVersionLocalizations": "appStoreVersionLocalization",
            "appCustomProductPageLocalizations": "appCustomProductPageLocalization",
            "appStoreVersionExperimentTreatmentLocalizations": "appStoreVersionExperimentTreatmentLocalization",
        }.get(target_type)
        if relationship_name is None:
            raise ValueError(f"Unsupported app preview localization target_type: {target_type}")
        data = self.request(
            "POST",
            "/appPreviewSets",
            json_body={
                "data": {
                    "type": "appPreviewSets",
                    "attributes": {"previewType": preview_type},
                    "relationships": {
                        relationship_name: {
                            "data": {
                                "type": target_type,
                                "id": version_localization_id,
                            }
                        }
                    },
                }
            },
        )
        return data.get("data", {}).get("id", "")

    def list_app_previews(self, preview_set_id: str) -> List[Dict[str, Any]]:
        """List app previews in a preview set."""
        data = self.request(
            "GET",
            f"/appPreviewSets/{preview_set_id}/appPreviews",
            params={"limit": "50"},
        )
        return list(data.get("data", []))

    def delete_app_preview(self, preview_id: str) -> None:
        """Delete an app preview."""
        self.request("DELETE", f"/appPreviews/{preview_id}")

    def create_app_preview(
        self,
        preview_set_id: str,
        file_name: str,
        file_size: int,
        *,
        mime_type: str | None = None,
        preview_frame_time_code: str | None = None,
    ) -> Dict[str, Any]:
        """Reserve an app preview upload slot. Returns resource with uploadOperations."""
        attributes: Dict[str, Any] = {"fileName": file_name, "fileSize": file_size}
        if mime_type is not None:
            attributes["mimeType"] = mime_type
        if preview_frame_time_code is not None:
            attributes["previewFrameTimeCode"] = preview_frame_time_code
        data = self.request(
            "POST",
            "/appPreviews",
            json_body={
                "data": {
                    "type": "appPreviews",
                    "attributes": attributes,
                    "relationships": {
                        "appPreviewSet": {
                            "data": {"type": "appPreviewSets", "id": preview_set_id}
                        }
                    },
                }
            },
        )
        return dict(data.get("data", {}))

    def complete_app_preview_upload(
        self,
        preview_id: str,
        checksum: str,
        *,
        preview_frame_time_code: str | None = None,
    ) -> None:
        """Mark an app preview upload as complete."""
        attributes: Dict[str, Any] = {
            "uploaded": True,
            "sourceFileChecksum": checksum,
        }
        if preview_frame_time_code is not None:
            attributes["previewFrameTimeCode"] = preview_frame_time_code
        self.request(
            "PATCH",
            f"/appPreviews/{preview_id}",
            json_body={
                "data": {
                    "type": "appPreviews",
                    "id": preview_id,
                    "attributes": attributes,
                }
            },
        )

    # ------------------------------------------------------------------
    # Custom product pages
    # ------------------------------------------------------------------

    def list_custom_product_pages(self, app_id: str, *, limit: int = 200) -> Mapping[str, Any]:
        """List custom product pages for an app."""
        return self.request("GET", f"/apps/{app_id}/appCustomProductPages", params={"limit": str(limit)})

    def create_custom_product_page(
        self,
        app_id: str,
        name: str,
        *,
        app_store_version_template_id: str | None = None,
        custom_product_page_template_id: str | None = None,
    ) -> Mapping[str, Any]:
        """Create a custom product page."""
        relationships: Dict[str, Any] = {
            "app": {"data": {"type": "apps", "id": app_id}},
        }
        if app_store_version_template_id:
            relationships["appStoreVersionTemplate"] = {
                "data": {"type": "appStoreVersions", "id": app_store_version_template_id}
            }
        if custom_product_page_template_id:
            relationships["customProductPageTemplate"] = {
                "data": {"type": "appCustomProductPages", "id": custom_product_page_template_id}
            }
        return self.request(
            "POST",
            "/appCustomProductPages",
            json_body={
                "data": {
                    "type": "appCustomProductPages",
                    "attributes": {"name": name},
                    "relationships": relationships,
                }
            },
        )

    def update_custom_product_page(
        self,
        page_id: str,
        *,
        name: str | None = None,
        visible: bool | None = None,
    ) -> Mapping[str, Any]:
        """Update a custom product page name or visibility."""
        attributes: Dict[str, Any] = {}
        if name is not None:
            attributes["name"] = name
        if visible is not None:
            attributes["visible"] = visible
        return self.request(
            "PATCH",
            f"/appCustomProductPages/{page_id}",
            json_body={
                "data": {
                    "type": "appCustomProductPages",
                    "id": page_id,
                    "attributes": attributes,
                }
            },
        )

    def delete_custom_product_page(self, page_id: str) -> Mapping[str, Any]:
        """Delete a custom product page."""
        return self.request("DELETE", f"/appCustomProductPages/{page_id}")

    def list_custom_product_page_versions(self, page_id: str, *, limit: int = 200) -> Mapping[str, Any]:
        """List versions for a custom product page."""
        return self.request("GET", f"/appCustomProductPages/{page_id}/appCustomProductPageVersions", params={"limit": str(limit)})

    def create_custom_product_page_version(
        self,
        page_id: str,
        *,
        deep_link: str | None = None,
    ) -> Mapping[str, Any]:
        """Create a custom product page version."""
        attributes: Dict[str, Any] = {}
        if deep_link is not None:
            attributes["deepLink"] = deep_link
        return self.request(
            "POST",
            "/appCustomProductPageVersions",
            json_body={
                "data": {
                    "type": "appCustomProductPageVersions",
                    "attributes": attributes,
                    "relationships": {
                        "appCustomProductPage": {
                            "data": {"type": "appCustomProductPages", "id": page_id}
                        }
                    },
                }
            },
        )

    def update_custom_product_page_version(
        self,
        version_id: str,
        *,
        deep_link: str | None = None,
    ) -> Mapping[str, Any]:
        """Update a custom product page version."""
        attributes: Dict[str, Any] = {}
        if deep_link is not None:
            attributes["deepLink"] = deep_link
        return self.request(
            "PATCH",
            f"/appCustomProductPageVersions/{version_id}",
            json_body={
                "data": {
                    "type": "appCustomProductPageVersions",
                    "id": version_id,
                    "attributes": attributes,
                }
            },
        )

    def list_custom_product_page_localizations(self, version_id: str, *, limit: int = 200) -> Mapping[str, Any]:
        """List localizations for a custom product page version."""
        return self.request(
            "GET",
            f"/appCustomProductPageVersions/{version_id}/appCustomProductPageLocalizations",
            params={"limit": str(limit)},
        )

    def create_custom_product_page_localization(
        self,
        version_id: str,
        locale: str,
        *,
        promotional_text: str | None = None,
    ) -> Mapping[str, Any]:
        """Create a custom product page localization."""
        attributes: Dict[str, Any] = {"locale": locale}
        if promotional_text is not None:
            attributes["promotionalText"] = promotional_text
        return self.request(
            "POST",
            "/appCustomProductPageLocalizations",
            json_body={
                "data": {
                    "type": "appCustomProductPageLocalizations",
                    "attributes": attributes,
                    "relationships": {
                        "appCustomProductPageVersion": {
                            "data": {"type": "appCustomProductPageVersions", "id": version_id}
                        }
                    },
                }
            },
        )

    def update_custom_product_page_localization(
        self,
        localization_id: str,
        *,
        promotional_text: str | None = None,
    ) -> Mapping[str, Any]:
        """Update a custom product page localization."""
        attributes: Dict[str, Any] = {}
        if promotional_text is not None:
            attributes["promotionalText"] = promotional_text
        return self.request(
            "PATCH",
            f"/appCustomProductPageLocalizations/{localization_id}",
            json_body={
                "data": {
                    "type": "appCustomProductPageLocalizations",
                    "id": localization_id,
                    "attributes": attributes,
                }
            },
        )

    def list_app_keywords(
        self,
        app_id: str,
        *,
        locale: str,
        platform: str,
        limit: int = 200,
    ) -> Mapping[str, Any]:
        """List app keyword resources available for custom page search visibility."""
        return self.request(
            "GET",
            f"/apps/{app_id}/searchKeywords",
            params={
                "filter[locale]": locale,
                "filter[platform]": platform,
                "limit": str(limit),
            },
        )

    def add_custom_product_page_search_keywords(
        self,
        localization_id: str,
        keyword_ids: Sequence[str],
    ) -> Mapping[str, Any]:
        """Associate keyword IDs with a custom product page localization."""
        return self.request(
            "POST",
            f"/appCustomProductPageLocalizations/{localization_id}/relationships/searchKeywords",
            json_body={
                "data": [
                    {"type": "appKeywords", "id": keyword_id}
                    for keyword_id in keyword_ids
                ]
            },
        )

    def remove_custom_product_page_search_keywords(
        self,
        localization_id: str,
        keyword_ids: Sequence[str],
    ) -> Mapping[str, Any]:
        """Remove keyword associations from a custom product page localization."""
        return self.request(
            "DELETE",
            f"/appCustomProductPageLocalizations/{localization_id}/relationships/searchKeywords",
            json_body={
                "data": [
                    {"type": "appKeywords", "id": keyword_id}
                    for keyword_id in keyword_ids
                ]
            },
        )

    # ------------------------------------------------------------------
    # Product page optimization experiments
    # ------------------------------------------------------------------

    def list_app_store_experiments(self, app_id: str, *, limit: int = 200) -> Mapping[str, Any]:
        """List product page optimization experiments for an app."""
        return self.request("GET", f"/apps/{app_id}/appStoreVersionExperimentsV2", params={"limit": str(limit)})

    def create_app_store_experiment(
        self,
        app_id: str,
        *,
        name: str,
        platform: str = "IOS",
        traffic_proportion: int = 50,
    ) -> Mapping[str, Any]:
        """Create an App Store product page optimization experiment."""
        return self.request(
            "POST",
            "/v2/appStoreVersionExperiments",
            json_body={
                "data": {
                    "type": "appStoreVersionExperiments",
                    "attributes": {
                        "name": name,
                        "platform": platform,
                        "trafficProportion": traffic_proportion,
                    },
                    "relationships": {
                        "app": {"data": {"type": "apps", "id": app_id}},
                    },
                }
            },
        )

    def update_app_store_experiment(
        self,
        experiment_id: str,
        *,
        name: str | None = None,
        traffic_proportion: int | None = None,
        started: bool | None = None,
    ) -> Mapping[str, Any]:
        """Update an App Store product page optimization experiment."""
        attributes: Dict[str, Any] = {}
        if name is not None:
            attributes["name"] = name
        if traffic_proportion is not None:
            attributes["trafficProportion"] = traffic_proportion
        if started is not None:
            attributes["started"] = started
        return self.request(
            "PATCH",
            f"/v2/appStoreVersionExperiments/{experiment_id}",
            json_body={
                "data": {
                    "type": "appStoreVersionExperiments",
                    "id": experiment_id,
                    "attributes": attributes,
                }
            },
        )

    def delete_app_store_experiment(self, experiment_id: str) -> Mapping[str, Any]:
        """Delete a product page optimization experiment before it starts."""
        return self.request("DELETE", f"/v2/appStoreVersionExperiments/{experiment_id}")

    def list_app_store_experiment_treatments(self, experiment_id: str, *, limit: int = 200) -> Mapping[str, Any]:
        """List treatments for a product page optimization experiment."""
        return self.request("GET", f"/v2/appStoreVersionExperiments/{experiment_id}/appStoreVersionExperimentTreatments", params={"limit": str(limit)})

    def create_app_store_experiment_treatment(
        self,
        experiment_id: str,
        *,
        name: str,
        app_icon_name: str | None = None,
    ) -> Mapping[str, Any]:
        """Create an experiment treatment."""
        attributes: Dict[str, Any] = {"name": name}
        if app_icon_name is not None:
            attributes["appIconName"] = app_icon_name
        return self.request(
            "POST",
            "/appStoreVersionExperimentTreatments",
            json_body={
                "data": {
                    "type": "appStoreVersionExperimentTreatments",
                    "attributes": attributes,
                    "relationships": {
                        "appStoreVersionExperimentV2": {
                            "data": {"type": "appStoreVersionExperiments", "id": experiment_id}
                        }
                    },
                }
            },
        )

    def update_app_store_experiment_treatment(
        self,
        treatment_id: str,
        *,
        name: str | None = None,
        app_icon_name: str | None = None,
    ) -> Mapping[str, Any]:
        """Update an experiment treatment."""
        attributes: Dict[str, Any] = {}
        if name is not None:
            attributes["name"] = name
        if app_icon_name is not None:
            attributes["appIconName"] = app_icon_name
        return self.request(
            "PATCH",
            f"/appStoreVersionExperimentTreatments/{treatment_id}",
            json_body={
                "data": {
                    "type": "appStoreVersionExperimentTreatments",
                    "id": treatment_id,
                    "attributes": attributes,
                }
            },
        )

    def delete_app_store_experiment_treatment(self, treatment_id: str) -> Mapping[str, Any]:
        """Delete an experiment treatment."""
        return self.request("DELETE", f"/appStoreVersionExperimentTreatments/{treatment_id}")

    def list_app_store_experiment_treatment_localizations(self, treatment_id: str, *, limit: int = 200) -> Mapping[str, Any]:
        """List treatment localizations."""
        return self.request(
            "GET",
            f"/appStoreVersionExperimentTreatments/{treatment_id}/appStoreVersionExperimentTreatmentLocalizations",
            params={"limit": str(limit)},
        )

    def create_app_store_experiment_treatment_localization(
        self,
        treatment_id: str,
        locale: str,
    ) -> Mapping[str, Any]:
        """Create a treatment localization."""
        return self.request(
            "POST",
            "/appStoreVersionExperimentTreatmentLocalizations",
            json_body={
                "data": {
                    "type": "appStoreVersionExperimentTreatmentLocalizations",
                    "attributes": {"locale": locale},
                    "relationships": {
                        "appStoreVersionExperimentTreatment": {
                            "data": {"type": "appStoreVersionExperimentTreatments", "id": treatment_id}
                        }
                    },
                }
            },
        )

    # ------------------------------------------------------------------
    # Review submissions for custom pages and experiments
    # ------------------------------------------------------------------

    def create_review_submission(self, app_id: str, *, platform: str | None = None) -> Mapping[str, Any]:
        """Create a review submission container."""
        attributes: Dict[str, Any] = {}
        if platform is not None:
            attributes["platform"] = platform
        return self.request(
            "POST",
            "/reviewSubmissions",
            json_body={
                "data": {
                    "type": "reviewSubmissions",
                    "attributes": attributes,
                    "relationships": {
                        "app": {"data": {"type": "apps", "id": app_id}},
                    },
                }
            },
        )

    def add_review_submission_item(
        self,
        review_submission_id: str,
        *,
        resource_type: str,
        resource_id: str,
    ) -> Mapping[str, Any]:
        """Attach an App Store version, custom page version, or experiment to a review submission."""
        relationship_name_by_type = {
            "appStoreVersions": "appStoreVersion",
            "appCustomProductPageVersions": "appCustomProductPageVersion",
            "appStoreVersionExperiments": "appStoreVersionExperimentV2",
        }
        relationship_name = relationship_name_by_type.get(resource_type)
        if relationship_name is None:
            raise ValueError(f"Unsupported review submission resource_type: {resource_type}")
        return self.request(
            "POST",
            "/reviewSubmissionItems",
            json_body={
                "data": {
                    "type": "reviewSubmissionItems",
                    "relationships": {
                        "reviewSubmission": {
                            "data": {"type": "reviewSubmissions", "id": review_submission_id}
                        },
                        relationship_name: {
                            "data": {"type": resource_type, "id": resource_id}
                        },
                    },
                }
            },
        )

    def submit_review_submission(self, review_submission_id: str) -> Mapping[str, Any]:
        """Submit a review submission to App Review."""
        return self.request(
            "PATCH",
            f"/reviewSubmissions/{review_submission_id}",
            json_body={
                "data": {
                    "type": "reviewSubmissions",
                    "id": review_submission_id,
                    "attributes": {"submitted": True},
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
    # Pricing — price point lookup helpers
    # ------------------------------------------------------------------

    def _fetch_price_points_paginated(
        self, path: str, territories: List[str] | None = None,
    ) -> Dict[str, Dict[str, float]]:
        """Fetch all price points from a paginated endpoint.

        Returns ``{territory_id: {price_point_id: customer_price_float}}``.
        Works for both IAP (``inAppPurchasePricePoints``) and subscription
        (``subscriptionPricePoints``) endpoints.
        """
        base_domain = self.base_url.rsplit("/v", 1)[0]
        params: Dict[str, str] | None = {"include": "territory", "limit": "200"}
        if territories:
            params["filter[territory]"] = ",".join(territories)

        all_data: List[Dict[str, Any]] = []
        all_included: List[Dict[str, Any]] = []
        current_path: str | None = path
        while current_path:
            resp = self.request("GET", current_path, params=params)
            all_data.extend(resp.get("data", []))
            all_included.extend(resp.get("included", []))
            next_link = resp.get("links", {}).get("next")
            if next_link and isinstance(next_link, str) and next_link.startswith(base_domain):
                current_path = next_link[len(base_domain):]
                params = None
            else:
                break

        result: Dict[str, Dict[str, float]] = {}
        for pp in all_data:
            pp_id = pp.get("id")
            attrs = pp.get("attributes", {})
            customer_price_str = attrs.get("customerPrice", "")
            territory_id = pp.get("relationships", {}).get("territory", {}).get("data", {}).get("id", "")
            if not pp_id or not customer_price_str or not territory_id:
                continue
            try:
                customer_price = float(customer_price_str)
            except (ValueError, TypeError):
                continue
            result.setdefault(territory_id, {})[pp_id] = customer_price
        return result

    def set_iap_pricing(
        self,
        iap_id: str,
        pricing: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Set IAP pricing via a price schedule.

        *pricing* maps ``{territory_3letter: {currency, price}}``.

        Fetches available price points, snaps each requested price to the
        nearest valid point per territory, then POSTs a new price schedule
        (which replaces any existing one for this IAP).

        Returns ``{"territories_set": int, "territories_skipped": [...], "not_found": [...]}``.
        """
        territories = list(pricing.keys())
        price_points = self._fetch_price_points_paginated(
            f"/v2/inAppPurchases/{iap_id}/pricePoints",
            territories=territories,
        )

        included: List[Dict[str, Any]] = []
        manual_price_refs: List[Dict[str, str]] = []
        not_found: List[str] = []

        for i, (territory, price_info) in enumerate(pricing.items()):
            target_price = float(price_info.get("price", 0))
            territory_points = price_points.get(territory)
            if not territory_points:
                not_found.append(territory)
                continue
            best_pp_id = min(territory_points, key=lambda pp: abs(territory_points[pp] - target_price))
            client_id = f"${{{i}}}"  # format required by API: ${0}, ${1}, ...
            manual_price_refs.append({"type": "inAppPurchasePrices", "id": client_id})
            included.append({
                "id": client_id,
                "type": "inAppPurchasePrices",
                "attributes": {"startDate": None},
                "relationships": {
                    "inAppPurchasePricePoint": {
                        "data": {"type": "inAppPurchasePricePoints", "id": best_pp_id},
                    },
                },
            })

        if not included:
            return {"territories_set": 0, "territories_skipped": not_found}

        self.request(
            "POST",
            "/inAppPurchasePriceSchedules",
            json_body={
                "data": {
                    "type": "inAppPurchasePriceSchedules",
                    "relationships": {
                        "inAppPurchase": {
                            "data": {"type": "inAppPurchases", "id": iap_id},
                        },
                        "baseTerritory": {
                            "data": {"type": "territories", "id": "USA"},
                        },
                        "manualPrices": {"data": manual_price_refs},
                    },
                },
                "included": included,
            },
        )
        return {"territories_set": len(included), "territories_skipped": not_found}

    def set_subscription_pricing(
        self,
        subscription_id: str,
        pricing: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Set subscription pricing for specified territories.

        *pricing* maps ``{territory_3letter: {currency, price}}``.

        Fetches available price points, snaps each requested price, then
        creates or updates prices per territory.  For approved subscriptions
        the initial price cannot be re-created, so we skip territories that
        already have pricing and only add new ones.

        Returns ``{"territories_set": int, "territories_skipped": [...], "already_set": int}``.
        """
        territories = list(pricing.keys())

        # App Store Connect rejects price creation until the subscription has an
        # availability configured (409 ENTITY_ERROR.RELATIONSHIP.INVALID). Ensure
        # one exists, covering the territories we're about to price. Apple can
        # 500 when creating availability for very large territory sets (>~50);
        # don't let that abort pricing — proceed best-effort and report it.
        availability_error: str | None = None
        try:
            availability = self.ensure_subscription_availability(
                subscription_id, territories,
            )
            availability_created = availability["created"]
            available_territories = availability["available_territories"]
        except RuntimeError as exc:
            availability_created = False
            available_territories = set()
            availability_error = str(exc)[:300]

        price_points = self._fetch_price_points_paginated(
            f"/v1/subscriptions/{subscription_id}/pricePoints",
            territories=territories,
        )

        # Fetch existing prices to know which territories already have pricing
        existing_by_territory: Dict[str, str] = {}  # territory_id → price_point_id
        existing_price_ids: Dict[str, str] = {}  # territory_id → price resource id
        next_path: str | None = f"/v1/subscriptions/{subscription_id}/prices"
        next_params: Dict[str, str] | None = {
            "include": "subscriptionPricePoint,territory",
            "limit": "200",
        }
        base_domain = self.base_url.rsplit("/v", 1)[0]
        while next_path:
            existing_resp = self.request("GET", next_path, params=next_params)
            for item in existing_resp.get("data", []):
                price_id = item.get("id")
                territory_id = (
                    item.get("relationships", {})
                    .get("territory", {})
                    .get("data", {})
                    .get("id", "")
                )
                pp_id = (
                    item.get("relationships", {})
                    .get("subscriptionPricePoint", {})
                    .get("data", {})
                    .get("id", "")
                )
                if price_id and territory_id:
                    existing_price_ids[territory_id] = price_id
                    if pp_id:
                        existing_by_territory[territory_id] = pp_id
            next_link = existing_resp.get("links", {}).get("next")
            if next_link and isinstance(next_link, str) and next_link.startswith(base_domain):
                next_path = next_link[len(base_domain):]
                next_params = None
            else:
                break

        set_count = 0
        already_set = 0
        not_found: List[str] = []
        skipped_unavailable: List[str] = []
        failed: List[Dict[str, str]] = []

        for territory, price_info in pricing.items():
            target_price = float(price_info.get("price", 0))
            territory_points = price_points.get(territory)
            if not territory_points:
                not_found.append(territory)
                continue

            best_pp_id = min(territory_points, key=lambda pp: abs(territory_points[pp] - target_price))

            # Skip if territory already has this exact price point
            if territory in existing_by_territory and existing_by_territory[territory] == best_pp_id:
                already_set += 1
                continue

            # For territories that already have pricing, skip — can't change initial price
            if territory in existing_price_ids:
                already_set += 1
                continue

            # When availability pre-existed we can only price territories it
            # already covers; pricing an unavailable territory would 409.
            if (
                not availability_created
                and available_territories
                and territory not in available_territories
            ):
                skipped_unavailable.append(territory)
                continue

            try:
                self.request(
                    "POST",
                    "/v1/subscriptionPrices",
                    json_body={
                        "data": {
                            "type": "subscriptionPrices",
                            "attributes": {"startDate": None, "preserveCurrentPrice": False},
                            "relationships": {
                                "subscription": {
                                    "data": {"type": "subscriptions", "id": subscription_id},
                                },
                                "subscriptionPricePoint": {
                                    "data": {"type": "subscriptionPricePoints", "id": best_pp_id},
                                },
                            },
                        },
                    },
                )
                set_count += 1
            except RuntimeError as exc:
                # Don't let one bad territory abort the rest of the batch.
                failed.append({"territory": territory, "error": str(exc)[:300]})

        return {
            "territories_set": set_count,
            "territories_skipped": not_found,
            "already_set": already_set,
            "skipped_unavailable": skipped_unavailable,
            "availability_created": availability_created,
            "availability_error": availability_error,
            "failed": failed,
        }

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
            f"/v2/inAppPurchases/{iap_id}/inAppPurchaseLocalizations",
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

    def delete_in_app_purchase_localization(self, localization_id: str) -> None:
        """Delete an IAP localization by its resource ID."""
        self.request("DELETE", f"/inAppPurchaseLocalizations/{localization_id}")

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

    def find_subscription_group_id(
        self, app_id: str, group_name: str,
    ) -> str | None:
        """Find a subscription group resource ID by its reference name."""
        data = self.request(
            "GET",
            f"/apps/{app_id}/subscriptionGroups",
            params={"limit": "50"},
        )
        for group in data.get("data", []):
            if group.get("attributes", {}).get("referenceName") == group_name:
                return group["id"]
        return None

    def create_subscription_group(self, app_id: str, reference_name: str) -> str:
        """Create a subscription group. Returns the new group ID."""
        data = self.request(
            "POST",
            "/v1/subscriptionGroups",
            json_body={
                "data": {
                    "type": "subscriptionGroups",
                    "attributes": {"referenceName": reference_name},
                    "relationships": {
                        "app": {"data": {"type": "apps", "id": app_id}},
                    },
                }
            },
        )
        return data.get("data", {}).get("id", "")

    def create_subscription(
        self,
        group_id: str,
        product_id: str,
        name: str,
        subscription_period: str,
        *,
        group_level: int = 1,
        family_sharable: bool = False,
        review_note: str | None = None,
    ) -> str:
        """Create an auto-renewable subscription in a group. Returns its ID.

        *subscription_period* is an App Store Connect enum: ``ONE_WEEK``,
        ``ONE_MONTH``, ``TWO_MONTHS``, ``THREE_MONTHS``, ``SIX_MONTHS`` or
        ``ONE_YEAR``. The created subscription starts in ``MISSING_METADATA``
        until localizations, availability and pricing are added.
        """
        attributes: Dict[str, Any] = {
            "name": name,
            "productId": product_id,
            "subscriptionPeriod": subscription_period,
            "familySharable": family_sharable,
            "groupLevel": group_level,
        }
        if review_note is not None:
            attributes["reviewNote"] = review_note
        data = self.request(
            "POST",
            "/v1/subscriptions",
            json_body={
                "data": {
                    "type": "subscriptions",
                    "attributes": attributes,
                    "relationships": {
                        "group": {
                            "data": {"type": "subscriptionGroups", "id": group_id},
                        },
                    },
                }
            },
        )
        return data.get("data", {}).get("id", "")

    def get_subscription_availability(
        self, subscription_id: str,
    ) -> Dict[str, Any] | None:
        """Return availability info for a subscription, or None if unset.

        Result: ``{"available_in_new_territories": bool, "territories": set[str]}``.
        The territory list is paginated (App Store caps the page size at 50).
        """
        try:
            data = self.request(
                "GET",
                f"/v1/subscriptions/{subscription_id}/subscriptionAvailability",
            )
        except RuntimeError as exc:
            if "404" in str(exc):
                return None
            raise
        avail = data.get("data", {})
        avail_id = avail.get("id") or subscription_id
        in_new = avail.get("attributes", {}).get("availableInNewTerritories", True)

        territories: set[str] = set()
        base_domain = self.base_url.rsplit("/v", 1)[0]
        next_path: str | None = (
            f"/v1/subscriptionAvailabilities/{avail_id}/availableTerritories"
        )
        next_params: Dict[str, str] | None = {"limit": "50"}
        while next_path:
            resp = self.request("GET", next_path, params=next_params)
            for item in resp.get("data", []):
                tid = item.get("id")
                if tid:
                    territories.add(tid)
            nxt = resp.get("links", {}).get("next")
            if nxt and isinstance(nxt, str) and nxt.startswith(base_domain):
                next_path = nxt[len(base_domain):]
                next_params = None
            else:
                break

        return {
            "available_in_new_territories": in_new,
            "territories": territories,
        }

    def ensure_subscription_availability(
        self,
        subscription_id: str,
        territories: Sequence[str],
        *,
        available_in_new_territories: bool = True,
    ) -> Dict[str, Any]:
        """Ensure the subscription has an availability configured.

        App Store Connect rejects subscription price creation with HTTP 409
        ``ENTITY_ERROR.RELATIONSHIP.INVALID`` (pointer ``subscriptionPricePoint``)
        until the subscription has a ``subscriptionAvailability`` — so this MUST
        run before pricing a brand-new subscription. When none exists it is
        created covering *territories*; an existing availability is left intact
        (the ``subscriptionAvailabilities`` resource only allows CREATE/GET and
        its ``availableTerritories`` relationship is read-only, so it can't be
        expanded in place).

        Note: App Store Connect can return HTTP 500 when a single create lists a
        very large territory set (empirically >~50). For broader coverage set
        ``availableInNewTerritories`` and/or finish availability in the App Store
        Connect UI, which handles bulk territory selection server-side.

        Returns ``{"created": bool, "available_territories": set[str]}``.
        """
        existing = self.get_subscription_availability(subscription_id)
        if existing is not None:
            return {
                "created": False,
                "available_territories": existing["territories"],
            }

        wanted = [t for t in dict.fromkeys(territories) if t]
        self.request(
            "POST",
            "/v1/subscriptionAvailabilities",
            json_body={
                "data": {
                    "type": "subscriptionAvailabilities",
                    "attributes": {
                        "availableInNewTerritories": available_in_new_territories,
                    },
                    "relationships": {
                        "subscription": {
                            "data": {"type": "subscriptions", "id": subscription_id},
                        },
                        "availableTerritories": {
                            "data": [
                                {"type": "territories", "id": t} for t in wanted
                            ],
                        },
                    },
                }
            },
        )
        return {"created": True, "available_territories": set(wanted)}

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

    def delete_subscription_localization(self, localization_id: str) -> None:
        """Delete a subscription localization by its resource ID."""
        self.request("DELETE", f"/subscriptionLocalizations/{localization_id}")

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
    target_type: str = "appStoreVersionLocalizations",
) -> Dict[str, Any]:
    """Upload screenshots for one localization + display type.

    Returns ``{"ok": True, "uploaded": int, "deleted": int}``.
    """
    paths = [Path(p) for p in file_paths]
    for p in paths:
        if not p.exists():
            raise FileNotFoundError(f"Screenshot file not found: {p}")

    # Find or create the screenshot set
    existing_sets = client.list_app_screenshot_sets(
        version_localization_id,
        target_type=target_type,
    )
    set_id: str | None = None
    for s in existing_sets:
        if s.get("attributes", {}).get("screenshotDisplayType") == display_type:
            set_id = s["id"]
            break

    if set_id is None:
        set_id = client.create_app_screenshot_set(
            version_localization_id,
            display_type,
            target_type=target_type,
        )

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


def upload_previews(
    client: AppStoreConnectClient,
    version_localization_id: str,
    preview_type: str,
    file_paths: Sequence[str | Path],
    *,
    replace: bool = True,
    target_type: str = "appStoreVersionLocalizations",
    mime_type: str | None = None,
    preview_frame_time_code: str | None = None,
) -> Dict[str, Any]:
    """Upload app previews for one localization + preview type.

    Returns ``{"ok": True, "uploaded": int, "deleted": int}``.
    """
    paths = [Path(p) for p in file_paths]
    for p in paths:
        if not p.exists():
            raise FileNotFoundError(f"App preview file not found: {p}")

    existing_sets = client.list_app_preview_sets(
        version_localization_id,
        target_type=target_type,
    )
    set_id: str | None = None
    for preview_set in existing_sets:
        if preview_set.get("attributes", {}).get("previewType") == preview_type:
            set_id = preview_set["id"]
            break

    if set_id is None:
        set_id = client.create_app_preview_set(
            version_localization_id,
            preview_type,
            target_type=target_type,
        )

    deleted = 0
    if replace:
        existing = client.list_app_previews(set_id)
        for preview in existing:
            client.delete_app_preview(preview["id"])
            deleted += 1

    uploaded = 0
    for file_path in paths:
        file_bytes = file_path.read_bytes()
        file_size = len(file_bytes)
        md5_hash = hashlib.md5(file_bytes).hexdigest()
        detected_mime_type = mime_type or mimetypes.guess_type(file_path.name)[0] or "video/mp4"

        preview_data = client.create_app_preview(
            set_id,
            file_path.name,
            file_size,
            mime_type=detected_mime_type,
            preview_frame_time_code=preview_frame_time_code,
        )
        preview_id = preview_data.get("id", "")
        upload_ops = preview_data.get("attributes", {}).get("uploadOperations", [])

        for op in upload_ops:
            offset = op.get("offset", 0)
            length = op.get("length", file_size)
            chunk = file_bytes[offset:offset + length]
            client.perform_upload_operation(op, chunk)

        client.complete_app_preview_upload(
            preview_id,
            md5_hash,
            preview_frame_time_code=preview_frame_time_code,
        )
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
    delete_missing: bool = False,
) -> Dict[str, Any]:
    """Sync in-app purchase localizations.

    Each item in *products*::

        {"product_id": "com.example.credits", "localizations": {
            "en-US": {"name": "3 Credits", "description": "Buy 3"},
            ...
        }}

    When *delete_missing* is True, remote localizations not present in the
    local list are deleted from App Store Connect.

    Returns ``{"ok": True, "created": int, "updated": int, "deleted": int, "missing_products": [...]}``.
    """
    created_count = 0
    updated_count = 0
    deleted_count = 0
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

        if delete_missing:
            for locale, remote in existing.items():
                if locale not in localizations and remote.get("id"):
                    client.delete_in_app_purchase_localization(remote["id"])
                    deleted_count += 1

    return {
        "ok": True,
        "created": created_count,
        "updated": updated_count,
        "deleted": deleted_count,
        "missing_products": missing,
    }


def ensure_subscription_exists(
    client: AppStoreConnectClient,
    app_id: str,
    sub: Dict[str, Any],
) -> tuple[str | None, bool]:
    """Find a subscription by ``product_id``, creating it when absent.

    Creation requires ``subscription_period`` (App Store enum such as
    ``ONE_YEAR``) and a group. The group is resolved from ``group_name`` and
    created if it does not exist. The display ``name`` falls back to the en-US
    localization name, then the product-id tail. Optional ``group_level``
    (default 1) and ``family_sharable`` (default False) are honoured.

    Returns ``(subscription_id_or_None, created)``. When the subscription is
    missing and not enough info is provided to create it, returns ``(None, False)``.
    """
    product_id = sub.get("product_id", "")
    sub_id = client.find_subscription_id(app_id, product_id)
    if sub_id is not None:
        return sub_id, False

    period = sub.get("subscription_period")
    if not period:
        return None, False  # cannot create without a billing period

    group_name = sub.get("group_name")
    if not group_name:
        return None, False  # cannot create without a subscription group
    group_id = client.find_subscription_group_id(app_id, group_name)
    if group_id is None:
        group_id = client.create_subscription_group(app_id, group_name)

    name = sub.get("name")
    if not name:
        locs = sub.get("localizations", {}) or {}
        chosen = locs.get("en-US") or (next(iter(locs.values()), {}) if locs else {})
        name = (chosen or {}).get("name") or product_id.rsplit(".", 1)[-1]
    name = str(name)[:30]

    new_id = client.create_subscription(
        group_id,
        product_id,
        name,
        str(period),
        group_level=int(sub.get("group_level", 1)),
        family_sharable=bool(sub.get("family_sharable", False)),
    )
    return new_id, True


def sync_subscription_localizations(
    client: AppStoreConnectClient,
    app_id: str,
    subscriptions: Sequence[Dict[str, Any]],
    delete_missing: bool = False,
) -> Dict[str, Any]:
    """Sync subscription localizations, creating missing subscriptions.

    Each item in *subscriptions*::

        {"product_id": "com.example.premium",
         "group_name": "Premium",            # required to create
         "subscription_period": "ONE_YEAR",  # required to create
         "group_level": 1,                    # optional (default 1)
         "family_sharable": false,            # optional (default False)
         "localizations": {
            "en-US": {"name": "Premium", "description": "Premium access"},
            ...
        }}

    A subscription that doesn't exist yet is created when ``subscription_period``
    and ``group_name`` are present; otherwise its product id is reported under
    ``missing_subscriptions``. When *delete_missing* is True, remote
    localizations not present in the local list are deleted.

    Returns ``{"ok": True, "created": int, "updated": int, "deleted": int,
    "created_subscriptions": [...], "missing_subscriptions": [...]}``.
    """
    created_count = 0
    updated_count = 0
    deleted_count = 0
    skipped_count = 0
    missing: List[str] = []
    created_subscriptions: List[str] = []

    for sub in subscriptions:
        product_id = sub["product_id"]
        localizations = sub.get("localizations", {})

        sub_id, was_created = ensure_subscription_exists(client, app_id, sub)
        if sub_id is None:
            missing.append(product_id)
            continue
        if was_created:
            created_subscriptions.append(product_id)

        existing = client.list_subscription_localizations(sub_id)

        for locale, fields in sorted(localizations.items()):
            name = fields.get("name")
            description = fields.get("description")

            remote = existing.get(locale)
            if remote and remote.get("id"):
                try:
                    client.update_subscription_localization(
                        remote["id"], name=name, description=description,
                    )
                    updated_count += 1
                except RuntimeError as exc:
                    if "409" in str(exc) and "UNMODIFIABLE" in str(exc):
                        skipped_count += 1
                    else:
                        raise
            else:
                client.create_subscription_localization(
                    sub_id, locale, name=name, description=description,
                )
                created_count += 1

        if delete_missing:
            for locale, remote in existing.items():
                if locale not in localizations and remote.get("id"):
                    client.delete_subscription_localization(remote["id"])
                    deleted_count += 1

    return {
        "ok": True,
        "created": created_count,
        "updated": updated_count,
        "deleted": deleted_count,
        "skipped_active": skipped_count,
        "created_subscriptions": created_subscriptions,
        "missing_subscriptions": missing,
    }


def sync_iap_pricing(
    client: AppStoreConnectClient,
    app_id: str,
    products: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Sync IAP pricing to App Store Connect for all products that have a ``pricing`` field.

    Each item in *products*::

        {"product_id": "com.example.credits", "pricing": {"USA": {"currency": "USD", "price": 1.99}, ...}}

    Returns ``{"ok": True, "products_updated": int, "territories_set": int, "missing_products": [...]}``.
    """
    products_updated = 0
    total_territories = 0
    missing: List[str] = []

    for product in products:
        product_id = product.get("product_id", "")
        pricing = product.get("pricing")
        if not pricing:
            continue

        iap_id = client.find_in_app_purchase_id(app_id, product_id)
        if iap_id is None:
            missing.append(product_id)
            continue

        result = client.set_iap_pricing(iap_id, pricing)
        products_updated += 1
        total_territories += result.get("territories_set", 0)

    return {
        "ok": True,
        "products_updated": products_updated,
        "territories_set": total_territories,
        "missing_products": missing,
    }


def sync_subscription_pricing(
    client: AppStoreConnectClient,
    app_id: str,
    subscriptions: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Sync subscription pricing to App Store Connect for all subscriptions with a ``pricing`` field.

    Each item in *subscriptions*::

        {"product_id": "com.example.premium", "pricing": {"USA": {"currency": "USD", "price": 4.99}, ...}}

    Returns ``{"ok": True, "subscriptions_updated": int, "territories_set": int, "missing_subscriptions": [...]}``.
    """
    subscriptions_updated = 0
    total_territories = 0
    missing: List[str] = []
    failed: List[Dict[str, str]] = []

    for sub in subscriptions:
        product_id = sub.get("product_id", "")
        pricing = sub.get("pricing")
        if not pricing:
            continue

        sub_id, _ = ensure_subscription_exists(client, app_id, sub)
        if sub_id is None:
            missing.append(product_id)
            continue

        result = client.set_subscription_pricing(sub_id, pricing)
        subscriptions_updated += 1
        total_territories += result.get("territories_set", 0)
        for item in result.get("failed", []):
            failed.append({"product_id": product_id, **item})

    return {
        "ok": True,
        "subscriptions_updated": subscriptions_updated,
        "territories_set": total_territories,
        "missing_subscriptions": missing,
        "failed": failed,
    }


def parse_gzip_tabular_report(
    content: bytes,
    *,
    delimiter: str = "\t",
    max_rows: int | None = None,
    encoding: str = "utf-8",
) -> Dict[str, Any]:
    """Decompress a gzip tabular report into rows plus the raw text."""
    text = gzip.decompress(content).decode(encoding, errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows: List[Dict[str, str]] = []
    for idx, row in enumerate(reader):
        if max_rows is not None and idx >= max_rows:
            break
        rows.append(dict(row))
    return {"text": text, "rows": rows, "row_count": len(rows), "columns": reader.fieldnames or []}
