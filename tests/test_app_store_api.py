"""Extensive tests for the App Store Connect API module (mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from perfectdeckcli.app_store import (
    VALID_DISPLAY_TYPES,
    AppStoreConnectClient,
    _parse_pricing_response,
    fetch_iap_and_subscriptions,
    fetch_listings,
    push_listings,
    sync_iap_localizations,
    sync_subscription_localizations,
    upload_screenshots,
)


# ======================================================================
# Helpers
# ======================================================================


def _mock_client(**kwargs) -> AppStoreConnectClient:
    """Create a client with mocked session and mocked JWT auth."""
    client = AppStoreConnectClient(
        key_id="KEY123",
        issuer_id="ISSUER456",
        private_key="fake-key",
        **kwargs,
    )
    client.session = MagicMock()
    # Bypass real JWT encoding in tests
    client._authorization_header = lambda: "Bearer fake-token"
    return client


def _mock_response(status_code: int = 200, json_data: dict | None = None, text: str = ""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    resp.headers = {}
    return resp


# ======================================================================
# AppStoreConnectClient - constructor and factory
# ======================================================================


class TestAppStoreConnectClientInit:
    def test_basic_init(self):
        client = AppStoreConnectClient(
            key_id="KEY", issuer_id="ISS", private_key="PK",
        )
        assert client.key_id == "KEY"
        assert client.issuer_id == "ISS"
        assert client.dry_run is False

    def test_dry_run_mode(self):
        client = AppStoreConnectClient(
            key_id="KEY", issuer_id="ISS", private_key="PK", dry_run=True,
        )
        assert client.dry_run is True

    def test_from_key_file(self, tmp_path):
        key_file = tmp_path / "key.p8"
        key_file.write_text("-----BEGIN EC PRIVATE KEY-----\nfake\n-----END EC PRIVATE KEY-----")
        client = AppStoreConnectClient.from_key_file(
            key_id="KEY", issuer_id="ISS", private_key_path=str(key_file),
        )
        assert client.private_key.startswith("-----BEGIN")

    def test_from_key_file_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="not found"):
            AppStoreConnectClient.from_key_file(
                key_id="KEY", issuer_id="ISS",
                private_key_path=str(tmp_path / "missing.p8"),
            )


# ======================================================================
# AppStoreConnectClient.request
# ======================================================================


class TestClientRequest:
    def test_get_success(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {"data": []})
        result = client.request("GET", "/apps")
        assert result == {"data": []}

    def test_204_returns_empty_dict(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(204)
        result = client.request("DELETE", "/something")
        assert result == {}

    def test_dry_run_skips_post(self):
        client = _mock_client(dry_run=True)
        result = client.request("POST", "/create", json_body={"data": {}})
        assert result == {}
        client.session.request.assert_not_called()

    def test_dry_run_allows_get(self):
        client = _mock_client(dry_run=True)
        client.session.request.return_value = _mock_response(200, {"data": [{"id": "1"}]})
        result = client.request("GET", "/read")
        assert result == {"data": [{"id": "1"}]}
        client.session.request.assert_called_once()

    def test_non_transient_error_raises(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(403, text="Forbidden")
        with pytest.raises(RuntimeError, match="403"):
            client.request("GET", "/forbidden")

    @patch("time.sleep")
    @patch("random.uniform", return_value=0.1)
    def test_retries_on_transient_get(self, mock_rand, mock_sleep):
        client = _mock_client()
        fail = _mock_response(500, text="Server Error")
        success = _mock_response(200, {"data": "ok"})
        client.session.request.side_effect = [fail, fail, success]
        result = client.request("GET", "/flaky")
        assert result == {"data": "ok"}
        assert client.session.request.call_count == 3

    @patch("time.sleep")
    def test_does_not_retry_post_on_transient_error(self, mock_sleep):
        client = _mock_client()
        client.session.request.return_value = _mock_response(500, text="Server Error")
        with pytest.raises(RuntimeError, match="500"):
            client.request("POST", "/create")
        assert client.session.request.call_count == 1

    @patch("time.sleep")
    @patch("random.uniform", return_value=0.1)
    def test_retries_patch_on_transient_error(self, mock_rand, mock_sleep):
        client = _mock_client()
        fail = _mock_response(502, text="Bad Gateway")
        success = _mock_response(200, {"data": "ok"})
        client.session.request.side_effect = [fail, success]
        result = client.request("PATCH", "/update")
        assert result == {"data": "ok"}
        assert client.session.request.call_count == 2

    @patch("time.sleep")
    def test_429_retry_after_header(self, mock_sleep):
        client = _mock_client()
        fail = _mock_response(429, text="Rate limit")
        fail.headers = {"Retry-After": "5"}
        success = _mock_response(200, {"data": "ok"})
        client.session.request.side_effect = [fail, success]
        result = client.request("GET", "/rate-limited")
        assert result == {"data": "ok"}
        mock_sleep.assert_called_once_with(5.0)


# ======================================================================
# get_app_info_id
# ======================================================================


class TestGetAppInfoId:
    def test_basic(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": [{"id": "info-1", "attributes": {"appStoreState": "READY_FOR_SALE"}}]
        })
        result = client.get_app_info_id("app123")
        assert result == "info-1"

    def test_no_app_info_raises(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {"data": []})
        with pytest.raises(RuntimeError, match="No appInfo"):
            client.get_app_info_id("app123")

    def test_preferred_states(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": [
                {"id": "info-1", "attributes": {"appStoreState": "READY_FOR_SALE"}},
                {"id": "info-2", "attributes": {"appStoreState": "PREPARE_FOR_SUBMISSION"}},
            ]
        })
        result = client.get_app_info_id(
            "app123", preferred_states=["PREPARE_FOR_SUBMISSION"],
        )
        assert result == "info-2"

    def test_preferred_states_fallback(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": [{"id": "info-1", "attributes": {"appStoreState": "READY_FOR_SALE"}}]
        })
        result = client.get_app_info_id(
            "app123", preferred_states=["PREPARE_FOR_SUBMISSION"],
        )
        assert result == "info-1"  # falls back to first


# ======================================================================
# App Store version management
# ======================================================================


class TestVersionManagement:
    def test_get_version_id(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": [{"id": "ver-1", "attributes": {"versionString": "2.0.0"}}]
        })
        result = client.get_app_store_version_id("app123", "IOS", "2.0.0")
        assert result == "ver-1"

    def test_get_version_id_not_found(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {"data": []})
        with pytest.raises(RuntimeError, match="No appStoreVersion"):
            client.get_app_store_version_id("app123", "IOS", "99.0.0")

    def test_create_version(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": {
                "id": "ver-new",
                "attributes": {"versionString": "3.0.0", "appStoreState": "PREPARE_FOR_SUBMISSION"},
            }
        })
        result = client.create_app_store_version("app123", "IOS", "3.0.0")
        assert result["id"] == "ver-new"
        assert result["version_string"] == "3.0.0"
        assert result["state"] == "PREPARE_FOR_SUBMISSION"

    def test_create_version_scheduled(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {"data": {"id": "ver-s"}})
        client.create_app_store_version(
            "app123", "IOS", "3.0.0",
            release_type="SCHEDULED",
            earliest_release_date="2026-03-01T00:00:00Z",
        )
        # Verify the POST was made
        client.session.request.assert_called_once()


# ======================================================================
# App info localizations
# ======================================================================


class TestAppInfoLocalizations:
    def test_list(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": [
                {"id": "loc-1", "attributes": {"locale": "en-US", "name": "My App"}},
                {"id": "loc-2", "attributes": {"locale": "fr-FR", "name": "Mon App"}},
            ]
        })
        result = client.list_app_info_localizations("info-1")
        assert len(result) == 2
        assert result["en-US"]["name"] == "My App"
        assert result["en-US"]["id"] == "loc-1"

    def test_find_existing(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": [{"id": "loc-1", "attributes": {"locale": "en-US", "name": "My App"}}]
        })
        result = client.find_app_info_localization("info-1", "en-US")
        assert result == "loc-1"

    def test_find_missing(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {"data": []})
        result = client.find_app_info_localization("info-1", "xx-XX")
        assert result is None

    def test_create(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": {"id": "new-loc"}
        })
        result = client.create_app_info_localization(
            "info-1", "ja", name="App Name", subtitle="Subtitle",
        )
        assert result == "new-loc"

    def test_update_no_attributes_skips(self):
        client = _mock_client()
        client.update_app_info_localization("loc-1")
        client.session.request.assert_not_called()

    def test_update_with_attributes(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {})
        client.update_app_info_localization("loc-1", name="New Name")
        client.session.request.assert_called_once()

    def test_update_retries_on_failure(self):
        client = _mock_client()
        # First call raises RuntimeError, then individual calls succeed
        error_resp = _mock_response(409, text="Conflict")
        success_resp = _mock_response(200, {})
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return error_resp
            return success_resp

        client.session.request.side_effect = side_effect
        client.update_app_info_localization(
            "loc-1", name="Name", subtitle="Sub",
        )


# ======================================================================
# Version localizations
# ======================================================================


class TestVersionLocalizations:
    def test_list(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": [
                {"id": "vloc-1", "attributes": {"locale": "en-US", "description": "An app"}},
            ]
        })
        result = client.list_app_store_version_localizations("ver-1")
        assert "en-US" in result
        assert result["en-US"]["description"] == "An app"

    def test_create(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": {"id": "vloc-new"}
        })
        result = client.create_app_store_version_localization(
            "ver-1", "ja", description="Japanese desc", keywords="app,tools",
        )
        assert result == "vloc-new"

    def test_update_empty_attributes_skips(self):
        client = _mock_client()
        client.update_app_store_version_localization("vloc-1")
        client.session.request.assert_not_called()

    def test_update_whats_new(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {})
        client.update_whats_new("vloc-1", "Bug fixes and improvements")
        client.session.request.assert_called_once()


# ======================================================================
# Screenshot management
# ======================================================================


class TestScreenshotManagement:
    def test_list_screenshot_sets(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": [
                {"id": "set-1", "attributes": {"screenshotDisplayType": "APP_IPHONE_67"}},
            ]
        })
        result = client.list_app_screenshot_sets("vloc-1")
        assert len(result) == 1

    def test_create_screenshot_set(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": {"id": "set-new"}
        })
        result = client.create_app_screenshot_set("vloc-1", "APP_IPHONE_67")
        assert result == "set-new"

    def test_create_screenshot(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": {
                "id": "ss-1",
                "attributes": {
                    "uploadOperations": [
                        {"url": "https://s3.example.com/upload", "method": "PUT", "offset": 0, "length": 1024},
                    ],
                },
            }
        })
        result = client.create_app_screenshot("set-1", "screen.png", 1024)
        assert result["id"] == "ss-1"

    def test_perform_upload_operation(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200)
        op = {
            "url": "https://s3.example.com/upload",
            "method": "PUT",
            "requestHeaders": [
                {"name": "Content-Type", "value": "application/octet-stream"},
            ],
        }
        client.perform_upload_operation(op, b"chunk-data")
        client.session.request.assert_called_once()

    def test_perform_upload_failure_raises(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(403, text="Forbidden")
        op = {"url": "https://s3.example.com/upload", "method": "PUT", "requestHeaders": []}
        with pytest.raises(RuntimeError, match="Upload operation failed"):
            client.perform_upload_operation(op, b"data")

    def test_complete_upload(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {})
        client.complete_app_screenshot_upload("ss-1", "abc123md5hash")
        client.session.request.assert_called_once()


# ======================================================================
# IAP management
# ======================================================================


class TestIAPManagement:
    def test_find_iap_id(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": [{"id": "iap-1"}]
        })
        result = client.find_in_app_purchase_id("app123", "com.example.credits")
        assert result == "iap-1"

    def test_find_iap_id_missing(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {"data": []})
        result = client.find_in_app_purchase_id("app123", "com.example.missing")
        assert result is None

    def test_list_iap_localizations(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": [
                {"id": "loc-1", "attributes": {"locale": "en-US", "name": "Credits"}},
            ]
        })
        result = client.list_in_app_purchase_localizations("iap-1")
        assert "en-US" in result
        assert result["en-US"]["name"] == "Credits"

    def test_create_iap_localization(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": {"id": "iap-loc-new"}
        })
        result = client.create_in_app_purchase_localization(
            "iap-1", "ja", name="Credits", description="Buy credits",
        )
        assert result == "iap-loc-new"

    def test_update_iap_localization_no_attrs_skips(self):
        client = _mock_client()
        client.update_in_app_purchase_localization("iap-loc-1")
        client.session.request.assert_not_called()

    def test_update_iap_localization(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {})
        client.update_in_app_purchase_localization("iap-loc-1", name="New Name")
        client.session.request.assert_called_once()


# ======================================================================
# Subscription management
# ======================================================================


class TestSubscriptionManagement:
    def test_find_subscription_id(self):
        client = _mock_client()
        # groups call
        groups_resp = _mock_response(200, {
            "data": [{"id": "group-1"}]
        })
        # subscriptions call
        subs_resp = _mock_response(200, {
            "data": [{"id": "sub-1", "attributes": {"productId": "com.example.premium"}}]
        })
        client.session.request.side_effect = [groups_resp, subs_resp]
        result = client.find_subscription_id("app123", "com.example.premium")
        assert result == "sub-1"

    def test_find_subscription_not_found(self):
        client = _mock_client()
        groups_resp = _mock_response(200, {"data": [{"id": "group-1"}]})
        subs_resp = _mock_response(200, {"data": []})
        client.session.request.side_effect = [groups_resp, subs_resp]
        result = client.find_subscription_id("app123", "com.example.missing")
        assert result is None

    def test_find_subscription_no_groups(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {"data": []})
        result = client.find_subscription_id("app123", "com.example.premium")
        assert result is None

    def test_list_subscription_localizations(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": [
                {"id": "sloc-1", "attributes": {"locale": "en-US", "name": "Premium"}},
            ]
        })
        result = client.list_subscription_localizations("sub-1")
        assert "en-US" in result

    def test_update_subscription_localization_no_attrs_skips(self):
        client = _mock_client()
        client.update_subscription_localization("sloc-1")
        client.session.request.assert_not_called()


# ======================================================================
# Top-level: fetch_listings
# ======================================================================


class TestFetchListings:
    def _app_resp(self):
        """Mock response for GET /apps/{app_id} (app-level info)."""
        return _mock_response(200, {
            "data": {"id": "app123", "attributes": {
                "primaryLocale": "en-US",
                "bundleId": "com.example.app",
                "sku": "APP123",
            }}
        })

    def test_fetch_info_only(self):
        client = _mock_client()
        # GET /apps/{app_id}
        app_resp = self._app_resp()
        # get_app_info_id
        info_resp = _mock_response(200, {
            "data": [{"id": "info-1", "attributes": {"appStoreState": "READY_FOR_SALE"}}]
        })
        # list_app_info_localizations
        info_locs_resp = _mock_response(200, {
            "data": [
                {"id": "loc-1", "attributes": {"locale": "en-US", "name": "My App", "subtitle": "Sub"}},
            ]
        })
        client.session.request.side_effect = [app_resp, info_resp, info_locs_resp]
        result = fetch_listings(client, "app123")
        assert result["global"]["primary_locale"] == "en-US"
        assert result["global"]["bundle_id"] == "com.example.app"
        locales = result["locales"]
        assert "en-US" in locales
        assert locales["en-US"]["app_name"] == "My App"
        assert locales["en-US"]["subtitle"] == "Sub"

    def test_fetch_with_version(self):
        client = _mock_client()
        app_resp = self._app_resp()
        # get_app_info_id
        info_resp = _mock_response(200, {
            "data": [{"id": "info-1", "attributes": {"appStoreState": "READY_FOR_SALE"}}]
        })
        # list_app_info_localizations
        info_locs_resp = _mock_response(200, {
            "data": [
                {"id": "loc-1", "attributes": {"locale": "en-US", "name": "My App"}},
            ]
        })
        # get_app_store_version_id
        ver_resp = _mock_response(200, {
            "data": [{"id": "ver-1", "attributes": {"versionString": "2.0.0"}}]
        })
        # list_app_store_version_localizations
        ver_locs_resp = _mock_response(200, {
            "data": [
                {"id": "vloc-1", "attributes": {
                    "locale": "en-US",
                    "description": "A great app",
                    "keywords": "app,great",
                    "whatsNew": "Bug fixes",
                }},
            ]
        })
        client.session.request.side_effect = [app_resp, info_resp, info_locs_resp, ver_resp, ver_locs_resp]
        result = fetch_listings(client, "app123", version_string="2.0.0")
        locales = result["locales"]
        assert locales["en-US"]["description"] == "A great app"
        assert locales["en-US"]["keywords"] == "app,great"
        assert locales["en-US"]["whats_new"] == "Bug fixes"

    def test_fetch_with_locale_filter(self):
        client = _mock_client()
        app_resp = self._app_resp()
        info_resp = _mock_response(200, {
            "data": [{"id": "info-1", "attributes": {"appStoreState": "READY_FOR_SALE"}}]
        })
        info_locs_resp = _mock_response(200, {
            "data": [
                {"id": "loc-1", "attributes": {"locale": "en-US", "name": "En"}},
                {"id": "loc-2", "attributes": {"locale": "fr-FR", "name": "Fr"}},
                {"id": "loc-3", "attributes": {"locale": "de-DE", "name": "De"}},
            ]
        })
        client.session.request.side_effect = [app_resp, info_resp, info_locs_resp]
        result = fetch_listings(client, "app123", locales=["en-US", "de-DE"])
        assert set(result["locales"].keys()) == {"en-US", "de-DE"}

    def test_fetch_empty_results(self):
        client = _mock_client()
        app_resp = self._app_resp()
        info_resp = _mock_response(200, {
            "data": [{"id": "info-1", "attributes": {"appStoreState": "READY_FOR_SALE"}}]
        })
        info_locs_resp = _mock_response(200, {"data": []})
        client.session.request.side_effect = [app_resp, info_resp, info_locs_resp]
        result = fetch_listings(client, "app123")
        assert result["locales"] == {}

    def test_fetch_skips_empty_entries(self):
        client = _mock_client()
        app_resp = self._app_resp()
        info_resp = _mock_response(200, {
            "data": [{"id": "info-1", "attributes": {"appStoreState": "READY_FOR_SALE"}}]
        })
        # locale with no meaningful data
        info_locs_resp = _mock_response(200, {
            "data": [
                {"id": "loc-1", "attributes": {"locale": "en-US"}},
            ]
        })
        client.session.request.side_effect = [app_resp, info_resp, info_locs_resp]
        result = fetch_listings(client, "app123")
        # en-US has no name/subtitle/privacy, so nothing to include
        assert result["locales"] == {}


# ======================================================================
# Top-level: push_listings
# ======================================================================


class TestPushListings:
    def _setup_push_mocks(self, client):
        """Set up the sequence of API responses needed for push_listings."""
        responses = [
            # get_app_info_id
            _mock_response(200, {
                "data": [{"id": "info-1", "attributes": {"appStoreState": "PREPARE_FOR_SUBMISSION"}}]
            }),
            # get_app_store_version_id
            _mock_response(200, {
                "data": [{"id": "ver-1"}]
            }),
            # list_app_info_localizations
            _mock_response(200, {"data": []}),
            # list_app_store_version_localizations
            _mock_response(200, {"data": []}),
        ]
        return responses

    def test_push_creates_new_localizations(self):
        client = _mock_client()
        base_responses = self._setup_push_mocks(client)
        # create_app_info_localization
        create_info = _mock_response(200, {"data": {"id": "new-info-loc"}})
        # create_app_store_version_localization
        create_ver = _mock_response(200, {"data": {"id": "new-ver-loc"}})
        client.session.request.side_effect = base_responses + [create_info, create_ver]

        result = push_listings(
            client, "app123", "IOS", "2.0.0",
            {"en-US": {"app_name": "My App", "description": "Great app"}},
        )
        assert result["ok"] is True
        assert "en-US" in result["created_locales"]

    def test_push_updates_existing_localizations(self):
        client = _mock_client()
        responses = [
            # get_app_info_id
            _mock_response(200, {
                "data": [{"id": "info-1", "attributes": {"appStoreState": "PREPARE_FOR_SUBMISSION"}}]
            }),
            # get_app_store_version_id
            _mock_response(200, {"data": [{"id": "ver-1"}]}),
            # list_app_info_localizations
            _mock_response(200, {
                "data": [{"id": "info-loc-1", "attributes": {"locale": "en-US", "name": "Old"}}]
            }),
            # list_app_store_version_localizations
            _mock_response(200, {
                "data": [{"id": "ver-loc-1", "attributes": {"locale": "en-US", "description": "Old desc"}}]
            }),
            # update_app_info_localization
            _mock_response(200, {}),
            # update_app_store_version_localization
            _mock_response(200, {}),
        ]
        client.session.request.side_effect = responses

        result = push_listings(
            client, "app123", "IOS", "2.0.0",
            {"en-US": {"app_name": "New App", "description": "New desc"}},
        )
        assert result["ok"] is True
        assert "en-US" in result["updated_locales"]

    def test_push_only_whats_new(self):
        client = _mock_client()
        responses = [
            _mock_response(200, {
                "data": [{"id": "info-1", "attributes": {"appStoreState": "PREPARE_FOR_SUBMISSION"}}]
            }),
            _mock_response(200, {"data": [{"id": "ver-1"}]}),
            _mock_response(200, {"data": []}),
            _mock_response(200, {
                "data": [{"id": "ver-loc-1", "attributes": {"locale": "en-US", "description": "Desc"}}]
            }),
            # update_app_store_version_localization
            _mock_response(200, {}),
        ]
        client.session.request.side_effect = responses

        result = push_listings(
            client, "app123", "IOS", "2.0.0",
            {"en-US": {"whats_new": "Bug fixes", "app_name": "Should be ignored"}},
            only_whats_new=True,
        )
        assert result["ok"] is True


# ======================================================================
# Top-level: upload_screenshots
# ======================================================================


class TestUploadScreenshots:
    def test_upload_basic(self, tmp_path):
        client = _mock_client()
        img = tmp_path / "screen1.png"
        img.write_bytes(b"fake-png-data")

        # list_app_screenshot_sets (none exist)
        sets_resp = _mock_response(200, {"data": []})
        # create_app_screenshot_set
        create_set_resp = _mock_response(200, {"data": {"id": "set-1"}})
        # list_app_screenshots (replace=True, empty set)
        list_ss_resp = _mock_response(200, {"data": []})
        # create_app_screenshot
        create_ss_resp = _mock_response(200, {
            "data": {
                "id": "ss-1",
                "attributes": {
                    "uploadOperations": [
                        {"url": "https://s3.example.com/upload", "method": "PUT",
                         "offset": 0, "length": 13, "requestHeaders": []},
                    ]
                },
            }
        })
        # perform_upload_operation
        upload_resp = _mock_response(200)
        # complete_app_screenshot_upload
        complete_resp = _mock_response(200, {})

        client.session.request.side_effect = [
            sets_resp, create_set_resp, list_ss_resp,
            create_ss_resp, upload_resp, complete_resp,
        ]
        result = upload_screenshots(client, "vloc-1", "APP_IPHONE_67", [str(img)])
        assert result["ok"] is True
        assert result["uploaded"] == 1
        assert result["deleted"] == 0

    def test_upload_with_replace(self, tmp_path):
        client = _mock_client()
        img = tmp_path / "screen1.png"
        img.write_bytes(b"data")

        # list_app_screenshot_sets (existing set)
        sets_resp = _mock_response(200, {
            "data": [{"id": "set-1", "attributes": {"screenshotDisplayType": "APP_IPHONE_67"}}]
        })
        # list_app_screenshots (existing screenshot)
        list_ss_resp = _mock_response(200, {"data": [{"id": "old-ss-1"}]})
        # delete old screenshot
        del_resp = _mock_response(204)
        # create_app_screenshot
        create_ss_resp = _mock_response(200, {
            "data": {"id": "ss-new", "attributes": {"uploadOperations": []}}
        })
        # complete
        complete_resp = _mock_response(200, {})

        client.session.request.side_effect = [
            sets_resp, list_ss_resp, del_resp, create_ss_resp, complete_resp,
        ]
        result = upload_screenshots(client, "vloc-1", "APP_IPHONE_67", [str(img)])
        assert result["deleted"] == 1
        assert result["uploaded"] == 1

    def test_missing_file_raises(self):
        client = _mock_client()
        with pytest.raises(FileNotFoundError, match="not found"):
            upload_screenshots(client, "vloc-1", "APP_IPHONE_67", ["/no/such/file.png"])


# ======================================================================
# Top-level: sync_iap_localizations
# ======================================================================


class TestSyncIapLocalizations:
    def test_create_new(self):
        client = _mock_client()
        # find_in_app_purchase_id
        find_resp = _mock_response(200, {"data": [{"id": "iap-1"}]})
        # list localizations
        list_resp = _mock_response(200, {"data": []})
        # create localization
        create_resp = _mock_response(200, {"data": {"id": "loc-new"}})

        client.session.request.side_effect = [find_resp, list_resp, create_resp]
        result = sync_iap_localizations(client, "app123", [
            {"product_id": "credits", "localizations": {"en-US": {"name": "Credits"}}},
        ])
        assert result["ok"] is True
        assert result["created"] == 1
        assert result["updated"] == 0

    def test_update_existing(self):
        client = _mock_client()
        find_resp = _mock_response(200, {"data": [{"id": "iap-1"}]})
        list_resp = _mock_response(200, {
            "data": [{"id": "loc-1", "attributes": {"locale": "en-US", "name": "Old"}}]
        })
        update_resp = _mock_response(200, {})

        client.session.request.side_effect = [find_resp, list_resp, update_resp]
        result = sync_iap_localizations(client, "app123", [
            {"product_id": "credits", "localizations": {"en-US": {"name": "New"}}},
        ])
        assert result["updated"] == 1
        assert result["created"] == 0

    def test_missing_product(self):
        client = _mock_client()
        find_resp = _mock_response(200, {"data": []})

        client.session.request.side_effect = [find_resp]
        result = sync_iap_localizations(client, "app123", [
            {"product_id": "missing", "localizations": {"en-US": {"name": "X"}}},
        ])
        assert result["missing_products"] == ["missing"]


# ======================================================================
# Top-level: sync_subscription_localizations
# ======================================================================


class TestSyncSubscriptionLocalizations:
    def test_create_new(self):
        client = _mock_client()
        # find_subscription_id (groups + subscriptions)
        groups_resp = _mock_response(200, {"data": [{"id": "g-1"}]})
        subs_resp = _mock_response(200, {
            "data": [{"id": "sub-1", "attributes": {"productId": "premium"}}]
        })
        # list localizations
        list_resp = _mock_response(200, {"data": []})
        # create localization
        create_resp = _mock_response(200, {"data": {"id": "sloc-new"}})

        client.session.request.side_effect = [groups_resp, subs_resp, list_resp, create_resp]
        result = sync_subscription_localizations(client, "app123", [
            {"product_id": "premium", "localizations": {"en-US": {"name": "Premium"}}},
        ])
        assert result["ok"] is True
        assert result["created"] == 1

    def test_missing_subscription(self):
        client = _mock_client()
        groups_resp = _mock_response(200, {"data": []})

        client.session.request.side_effect = [groups_resp]
        result = sync_subscription_localizations(client, "app123", [
            {"product_id": "missing", "localizations": {}},
        ])
        assert result["missing_subscriptions"] == ["missing"]


# ======================================================================
# list_all_in_app_purchases
# ======================================================================


class TestListAllInAppPurchases:
    def test_basic(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": [
                {"id": "iap-1", "attributes": {"productId": "com.example.credits", "inAppPurchaseType": "CONSUMABLE"}},
                {"id": "iap-2", "attributes": {"productId": "com.example.unlock", "inAppPurchaseType": "NON_CONSUMABLE"}},
            ],
            "links": {},
        })
        result = client.list_all_in_app_purchases("app123")
        assert len(result) == 2
        assert result[0]["id"] == "iap-1"

    def test_empty(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {"data": [], "links": {}})
        result = client.list_all_in_app_purchases("app123")
        assert result == []

    def test_pagination(self):
        client = _mock_client()
        page1 = _mock_response(200, {
            "data": [{"id": "iap-1", "attributes": {"productId": "p1"}}],
            "links": {"next": "https://api.appstoreconnect.apple.com/v1/apps/app123/inAppPurchasesV2?cursor=abc"},
        })
        page2 = _mock_response(200, {
            "data": [{"id": "iap-2", "attributes": {"productId": "p2"}}],
            "links": {},
        })
        client.session.request.side_effect = [page1, page2]
        result = client.list_all_in_app_purchases("app123")
        assert len(result) == 2


# ======================================================================
# list_all_subscription_groups
# ======================================================================


class TestListAllSubscriptionGroups:
    def test_basic(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": [
                {"id": "grp-1", "attributes": {"referenceName": "Premium"}},
            ]
        })
        result = client.list_all_subscription_groups("app123")
        assert len(result) == 1
        assert result[0]["id"] == "grp-1"

    def test_empty(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {"data": []})
        result = client.list_all_subscription_groups("app123")
        assert result == []


class TestListSubscriptionsInGroup:
    def test_basic(self):
        client = _mock_client()
        client.session.request.return_value = _mock_response(200, {
            "data": [
                {"id": "sub-1", "attributes": {"productId": "com.example.premium"}},
            ]
        })
        result = client.list_subscriptions_in_group("grp-1")
        assert len(result) == 1


# ======================================================================
# _parse_pricing_response
# ======================================================================


class TestParsePricingResponse:
    def test_basic_two_territories(self):
        response = {
            "data": [
                {
                    "type": "inAppPurchasePrices", "id": "p1",
                    "attributes": {"startDate": None},
                    "relationships": {
                        "inAppPurchasePricePoint": {"data": {"type": "inAppPurchasePricePoints", "id": "pp-1"}},
                        "territory": {"data": {"type": "territories", "id": "USA"}},
                    },
                },
                {
                    "type": "inAppPurchasePrices", "id": "p2",
                    "attributes": {"startDate": None},
                    "relationships": {
                        "inAppPurchasePricePoint": {"data": {"type": "inAppPurchasePricePoints", "id": "pp-2"}},
                        "territory": {"data": {"type": "territories", "id": "CAN"}},
                    },
                },
            ],
            "included": [
                {"type": "inAppPurchasePricePoints", "id": "pp-1", "attributes": {"customerPrice": "4.99", "proceeds": "3.49"}},
                {"type": "inAppPurchasePricePoints", "id": "pp-2", "attributes": {"customerPrice": "5.99", "proceeds": "4.19"}},
                {"type": "territories", "id": "USA", "attributes": {"currency": "USD"}},
                {"type": "territories", "id": "CAN", "attributes": {"currency": "CAD"}},
            ],
        }
        result = _parse_pricing_response(response)
        assert result == {
            "USA": {"currency": "USD", "price": 4.99},
            "CAN": {"currency": "CAD", "price": 5.99},
        }

    def test_filters_future_dated_prices(self):
        response = {
            "data": [
                {
                    "type": "inAppPurchasePrices", "id": "p1",
                    "attributes": {"startDate": None},
                    "relationships": {
                        "inAppPurchasePricePoint": {"data": {"type": "inAppPurchasePricePoints", "id": "pp-1"}},
                        "territory": {"data": {"type": "territories", "id": "USA"}},
                    },
                },
                {
                    "type": "inAppPurchasePrices", "id": "p2",
                    "attributes": {"startDate": "2027-01-01"},
                    "relationships": {
                        "inAppPurchasePricePoint": {"data": {"type": "inAppPurchasePricePoints", "id": "pp-2"}},
                        "territory": {"data": {"type": "territories", "id": "CAN"}},
                    },
                },
            ],
            "included": [
                {"type": "inAppPurchasePricePoints", "id": "pp-1", "attributes": {"customerPrice": "4.99"}},
                {"type": "inAppPurchasePricePoints", "id": "pp-2", "attributes": {"customerPrice": "5.99"}},
                {"type": "territories", "id": "USA", "attributes": {"currency": "USD"}},
                {"type": "territories", "id": "CAN", "attributes": {"currency": "CAD"}},
            ],
        }
        result = _parse_pricing_response(response)
        assert "USA" in result
        assert "CAN" not in result  # future-dated, filtered out

    def test_empty_data(self):
        result = _parse_pricing_response({"data": [], "included": []})
        assert result == {}

    def test_missing_included_data_skips_gracefully(self):
        response = {
            "data": [
                {
                    "type": "inAppPurchasePrices", "id": "p1",
                    "attributes": {"startDate": None},
                    "relationships": {
                        "inAppPurchasePricePoint": {"data": {"type": "inAppPurchasePricePoints", "id": "pp-missing"}},
                        "territory": {"data": {"type": "territories", "id": "USA"}},
                    },
                },
            ],
            "included": [
                {"type": "territories", "id": "USA", "attributes": {"currency": "USD"}},
                # price point pp-missing is not in included
            ],
        }
        result = _parse_pricing_response(response)
        assert result == {}  # skipped because customerPrice is empty

    def test_subscription_price_point_type(self):
        """Subscription pricing uses subscriptionPricePoint relationship."""
        response = {
            "data": [
                {
                    "type": "subscriptionPrices", "id": "sp1",
                    "attributes": {"startDate": None},
                    "relationships": {
                        "subscriptionPricePoint": {"data": {"type": "subscriptionPricePoints", "id": "spp-1"}},
                        "territory": {"data": {"type": "territories", "id": "USA"}},
                    },
                },
            ],
            "included": [
                {"type": "subscriptionPricePoints", "id": "spp-1", "attributes": {"customerPrice": "9.99"}},
                {"type": "territories", "id": "USA", "attributes": {"currency": "USD"}},
            ],
        }
        result = _parse_pricing_response(response)
        assert result == {"USA": {"currency": "USD", "price": 9.99}}


# ======================================================================
# fetch_iap_pricing
# ======================================================================


class TestFetchIapPricing:
    def test_basic(self):
        client = _mock_client()
        # GET /v2/inAppPurchases/{id}/iapPriceSchedule
        schedule_resp = _mock_response(200, {
            "data": {"id": "schedule-1", "type": "inAppPurchasePriceSchedules"},
        })
        # GET /v1/inAppPurchasePriceSchedules/{id}/manualPrices
        prices_resp = _mock_response(200, {
            "data": [
                {
                    "type": "inAppPurchasePrices", "id": "price-1",
                    "attributes": {"startDate": None},
                    "relationships": {
                        "inAppPurchasePricePoint": {"data": {"type": "inAppPurchasePricePoints", "id": "pp-1"}},
                        "territory": {"data": {"type": "territories", "id": "USA"}},
                    },
                },
            ],
            "included": [
                {"type": "inAppPurchasePricePoints", "id": "pp-1", "attributes": {"customerPrice": "4.99"}},
                {"type": "territories", "id": "USA", "attributes": {"currency": "USD"}},
            ],
            "links": {},
        })
        client.session.request.side_effect = [schedule_resp, prices_resp]
        result = client.fetch_iap_pricing("iap-1")
        assert result == {"USA": {"currency": "USD", "price": 4.99}}

    def test_no_schedule(self):
        client = _mock_client()
        schedule_resp = _mock_response(200, {"data": {}})
        client.session.request.side_effect = [schedule_resp]
        result = client.fetch_iap_pricing("iap-1")
        assert result == {}

    def test_pagination(self):
        client = _mock_client()
        schedule_resp = _mock_response(200, {
            "data": {"id": "schedule-1"},
        })
        page1 = _mock_response(200, {
            "data": [
                {
                    "type": "inAppPurchasePrices", "id": "p1",
                    "attributes": {"startDate": None},
                    "relationships": {
                        "inAppPurchasePricePoint": {"data": {"type": "inAppPurchasePricePoints", "id": "pp-1"}},
                        "territory": {"data": {"type": "territories", "id": "USA"}},
                    },
                },
            ],
            "included": [
                {"type": "inAppPurchasePricePoints", "id": "pp-1", "attributes": {"customerPrice": "4.99"}},
                {"type": "territories", "id": "USA", "attributes": {"currency": "USD"}},
            ],
            "links": {"next": "https://api.appstoreconnect.apple.com/v1/inAppPurchasePriceSchedules/schedule-1/manualPrices?cursor=abc"},
        })
        page2 = _mock_response(200, {
            "data": [
                {
                    "type": "inAppPurchasePrices", "id": "p2",
                    "attributes": {"startDate": None},
                    "relationships": {
                        "inAppPurchasePricePoint": {"data": {"type": "inAppPurchasePricePoints", "id": "pp-2"}},
                        "territory": {"data": {"type": "territories", "id": "CAN"}},
                    },
                },
            ],
            "included": [
                {"type": "inAppPurchasePricePoints", "id": "pp-2", "attributes": {"customerPrice": "5.99"}},
                {"type": "territories", "id": "CAN", "attributes": {"currency": "CAD"}},
            ],
            "links": {},
        })
        client.session.request.side_effect = [schedule_resp, page1, page2]
        result = client.fetch_iap_pricing("iap-1")
        assert len(result) == 2
        assert result["USA"] == {"currency": "USD", "price": 4.99}
        assert result["CAN"] == {"currency": "CAD", "price": 5.99}


# ======================================================================
# fetch_subscription_pricing
# ======================================================================


class TestFetchSubscriptionPricing:
    def test_basic(self):
        client = _mock_client()
        prices_resp = _mock_response(200, {
            "data": [
                {
                    "type": "subscriptionPrices", "id": "sp1",
                    "attributes": {"startDate": None},
                    "relationships": {
                        "subscriptionPricePoint": {"data": {"type": "subscriptionPricePoints", "id": "spp-1"}},
                        "territory": {"data": {"type": "territories", "id": "USA"}},
                    },
                },
            ],
            "included": [
                {"type": "subscriptionPricePoints", "id": "spp-1", "attributes": {"customerPrice": "9.99"}},
                {"type": "territories", "id": "USA", "attributes": {"currency": "USD"}},
            ],
            "links": {},
        })
        client.session.request.side_effect = [prices_resp]
        result = client.fetch_subscription_pricing("sub-1")
        assert result == {"USA": {"currency": "USD", "price": 9.99}}

    def test_pagination(self):
        client = _mock_client()
        page1 = _mock_response(200, {
            "data": [
                {
                    "type": "subscriptionPrices", "id": "sp1",
                    "attributes": {"startDate": None},
                    "relationships": {
                        "subscriptionPricePoint": {"data": {"type": "subscriptionPricePoints", "id": "spp-1"}},
                        "territory": {"data": {"type": "territories", "id": "USA"}},
                    },
                },
            ],
            "included": [
                {"type": "subscriptionPricePoints", "id": "spp-1", "attributes": {"customerPrice": "9.99"}},
                {"type": "territories", "id": "USA", "attributes": {"currency": "USD"}},
            ],
            "links": {"next": "https://api.appstoreconnect.apple.com/v1/subscriptions/sub-1/prices?cursor=abc"},
        })
        page2 = _mock_response(200, {
            "data": [
                {
                    "type": "subscriptionPrices", "id": "sp2",
                    "attributes": {"startDate": None},
                    "relationships": {
                        "subscriptionPricePoint": {"data": {"type": "subscriptionPricePoints", "id": "spp-2"}},
                        "territory": {"data": {"type": "territories", "id": "GBR"}},
                    },
                },
            ],
            "included": [
                {"type": "subscriptionPricePoints", "id": "spp-2", "attributes": {"customerPrice": "7.99"}},
                {"type": "territories", "id": "GBR", "attributes": {"currency": "GBP"}},
            ],
            "links": {},
        })
        client.session.request.side_effect = [page1, page2]
        result = client.fetch_subscription_pricing("sub-1")
        assert len(result) == 2
        assert result["USA"] == {"currency": "USD", "price": 9.99}
        assert result["GBR"] == {"currency": "GBP", "price": 7.99}


# ======================================================================
# fetch_iap_and_subscriptions
# ======================================================================


class TestFetchIapAndSubscriptions:
    def test_fetches_products_and_subscriptions(self):
        client = _mock_client()
        # list_all_in_app_purchases
        iap_resp = _mock_response(200, {
            "data": [
                {"id": "iap-1", "attributes": {"productId": "com.example.credits", "inAppPurchaseType": "CONSUMABLE"}},
            ],
            "links": {},
        })
        # list_in_app_purchase_localizations
        iap_locs_resp = _mock_response(200, {
            "data": [
                {"id": "iloc-1", "attributes": {"locale": "en-US", "name": "3 Credits", "description": "Buy 3"}},
            ]
        })
        # fetch_iap_pricing: schedule
        iap_schedule_resp = _mock_response(200, {
            "data": {"id": "schedule-1", "type": "inAppPurchasePriceSchedules"},
        })
        # fetch_iap_pricing: manual prices
        iap_prices_resp = _mock_response(200, {
            "data": [
                {
                    "type": "inAppPurchasePrices", "id": "price-1",
                    "attributes": {"startDate": None},
                    "relationships": {
                        "inAppPurchasePricePoint": {"data": {"type": "inAppPurchasePricePoints", "id": "pp-1"}},
                        "territory": {"data": {"type": "territories", "id": "USA"}},
                    },
                },
            ],
            "included": [
                {"type": "inAppPurchasePricePoints", "id": "pp-1", "attributes": {"customerPrice": "4.99"}},
                {"type": "territories", "id": "USA", "attributes": {"currency": "USD"}},
            ],
            "links": {},
        })
        # list_all_subscription_groups
        groups_resp = _mock_response(200, {
            "data": [{"id": "grp-1", "attributes": {"referenceName": "Premium"}}]
        })
        # list_subscriptions_in_group
        subs_resp = _mock_response(200, {
            "data": [{"id": "sub-1", "attributes": {"productId": "com.example.monthly"}}]
        })
        # list_subscription_localizations
        sub_locs_resp = _mock_response(200, {
            "data": [
                {"id": "sloc-1", "attributes": {"locale": "en-US", "name": "Monthly", "description": "Monthly sub"}},
            ]
        })
        # fetch_subscription_pricing
        sub_prices_resp = _mock_response(200, {
            "data": [
                {
                    "type": "subscriptionPrices", "id": "sprice-1",
                    "attributes": {"startDate": None},
                    "relationships": {
                        "subscriptionPricePoint": {"data": {"type": "subscriptionPricePoints", "id": "spp-1"}},
                        "territory": {"data": {"type": "territories", "id": "USA"}},
                    },
                },
            ],
            "included": [
                {"type": "subscriptionPricePoints", "id": "spp-1", "attributes": {"customerPrice": "9.99"}},
                {"type": "territories", "id": "USA", "attributes": {"currency": "USD"}},
            ],
            "links": {},
        })

        client.session.request.side_effect = [
            iap_resp, iap_locs_resp, iap_schedule_resp, iap_prices_resp,
            groups_resp, subs_resp, sub_locs_resp, sub_prices_resp,
        ]
        result = fetch_iap_and_subscriptions(client, "app123")

        assert "com.example.credits" in result["products"]
        prod = result["products"]["com.example.credits"]
        assert prod["type"] == "consumable"
        assert prod["localizations"]["en-US"]["name"] == "3 Credits"
        assert prod["pricing"]["USA"] == {"currency": "USD", "price": 4.99}

        assert "com.example.monthly" in result["subscriptions"]
        sub = result["subscriptions"]["com.example.monthly"]
        assert sub["group_name"] == "Premium"
        assert sub["localizations"]["en-US"]["name"] == "Monthly"
        assert sub["pricing"]["USA"] == {"currency": "USD", "price": 9.99}

    def test_empty_results(self):
        client = _mock_client()
        # list_all_in_app_purchases (empty)
        iap_resp = _mock_response(200, {"data": [], "links": {}})
        # list_all_subscription_groups (empty)
        groups_resp = _mock_response(200, {"data": []})

        client.session.request.side_effect = [iap_resp, groups_resp]
        result = fetch_iap_and_subscriptions(client, "app123")
        assert result["products"] == {}
        assert result["subscriptions"] == {}

    def test_iap_failure_still_returns_subscriptions(self):
        client = _mock_client()
        # list_all_in_app_purchases fails
        iap_resp = _mock_response(500, text="Server Error")
        # list_all_subscription_groups (empty)
        groups_resp = _mock_response(200, {"data": []})

        client.session.request.side_effect = [iap_resp, groups_resp]
        # The IAP fetch will raise RuntimeError which is caught
        result = fetch_iap_and_subscriptions(client, "app123")
        assert result["products"] == {}
        assert result["subscriptions"] == {}

    def test_non_consumable_type(self):
        client = _mock_client()
        iap_resp = _mock_response(200, {
            "data": [
                {"id": "iap-1", "attributes": {"productId": "com.example.unlock", "inAppPurchaseType": "NON_CONSUMABLE"}},
            ],
            "links": {},
        })
        iap_locs_resp = _mock_response(200, {"data": []})
        # No price schedule for this product
        no_schedule_resp = _mock_response(200, {"data": {}})
        groups_resp = _mock_response(200, {"data": []})

        client.session.request.side_effect = [iap_resp, iap_locs_resp, no_schedule_resp, groups_resp]
        result = fetch_iap_and_subscriptions(client, "app123")
        assert result["products"]["com.example.unlock"]["type"] == "non_consumable"

    def test_pricing_failure_does_not_break_fetch(self):
        client = _mock_client()
        iap_resp = _mock_response(200, {
            "data": [
                {"id": "iap-1", "attributes": {"productId": "com.example.credits", "inAppPurchaseType": "CONSUMABLE"}},
            ],
            "links": {},
        })
        iap_locs_resp = _mock_response(200, {
            "data": [{"id": "iloc-1", "attributes": {"locale": "en-US", "name": "Credits"}}]
        })
        # Pricing schedule call fails (404 = non-transient, no retry)
        pricing_fail_resp = _mock_response(404, text="Not Found")
        groups_resp = _mock_response(200, {"data": []})

        client.session.request.side_effect = [iap_resp, iap_locs_resp, pricing_fail_resp, groups_resp]
        result = fetch_iap_and_subscriptions(client, "app123")

        prod = result["products"]["com.example.credits"]
        assert prod["type"] == "consumable"
        assert prod["localizations"]["en-US"]["name"] == "Credits"
        assert "pricing" not in prod  # pricing failed but product is still present


# ======================================================================
# VALID_DISPLAY_TYPES
# ======================================================================


class TestConstants:
    def test_valid_display_types(self):
        assert "APP_IPHONE_67" in VALID_DISPLAY_TYPES
        assert "APP_IPAD_PRO_3GEN_129" in VALID_DISPLAY_TYPES
        assert "APP_APPLE_VISION_PRO" in VALID_DISPLAY_TYPES
        assert "INVALID" not in VALID_DISPLAY_TYPES
