"""Extensive tests for the Play Store API module (mocked)."""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from perfectdeckcli.play_store import (
    PLAY_LOCALE_MAP,
    VALID_IMAGE_TYPES,
    VALID_RELEASE_STATUSES,
    _compute_sha1,
    _execute_with_retry,
    _price_to_money,
    apply_regional_pricing,
    apply_subscription_regional_pricing,
    create_service,
    ensure_managed_products,
    fetch_listings,
    fetch_products,
    fetch_subscriptions,
    map_locale,
    publish_bundle,
    push_listings,
    update_release_notes,
    upload_screenshots,
)

try:
    from googleapiclient.errors import HttpError
except ImportError:
    HttpError = None


# ======================================================================
# Helpers
# ======================================================================


def _mock_service():
    """Build a deeply-nested mock that mimics the androidpublisher service."""
    svc = MagicMock()
    edits = svc.edits.return_value
    # insert / commit / delete
    edits.insert.return_value.execute.return_value = {"id": "edit-1"}
    edits.commit.return_value.execute.return_value = {}
    edits.delete.return_value.execute.return_value = {}
    # details sub-resource
    edits.details.return_value.get.return_value.execute.return_value = {
        "defaultLanguage": "en-US",
        "contactEmail": "test@example.com",
    }
    # listings sub-resource
    edits.listings.return_value.list.return_value.execute.return_value = {
        "listings": []
    }
    edits.listings.return_value.update.return_value.execute.return_value = {}
    # tracks sub-resource
    edits.tracks.return_value.get.return_value.execute.return_value = {
        "releases": []
    }
    edits.tracks.return_value.update.return_value.execute.return_value = {}
    # images sub-resource
    edits.images.return_value.list.return_value.execute.return_value = {
        "images": []
    }
    edits.images.return_value.deleteall.return_value.execute.return_value = {}
    edits.images.return_value.upload.return_value.execute.return_value = {}
    # bundles sub-resource
    edits.bundles.return_value.upload.return_value.execute.return_value = {
        "versionCode": 42
    }
    # deobfuscation sub-resource
    edits.deobfuscationfiles.return_value.upload.return_value.execute.return_value = {}
    # monetization sub-resource
    monetization = svc.monetization.return_value
    monetization.onetimeproducts.return_value.get.return_value.execute.return_value = {
        "sku": "sku1", "prices": {}
    }
    monetization.onetimeproducts.return_value.insert.return_value.execute.return_value = {}
    monetization.onetimeproducts.return_value.patch.return_value.execute.return_value = {}
    monetization.subscriptions.return_value.get.return_value.execute.return_value = {
        "basePlans": []
    }
    monetization.subscriptions.return_value.patch.return_value.execute.return_value = {}
    # list endpoints for fetch_products / fetch_subscriptions
    monetization.onetimeproducts.return_value.list.return_value.execute.return_value = {
        "oneTimeProducts": []
    }
    monetization.subscriptions.return_value.list.return_value.execute.return_value = {
        "subscriptions": []
    }
    return svc


def _make_http_error(status: int):
    """Create a mock HttpError-like exception."""
    resp = MagicMock()
    resp.status = status
    exc = Exception(f"HttpError {status}")
    exc.resp = resp
    exc.__class__.__name__ = "HttpError"
    return exc


# ======================================================================
# _execute_with_retry
# ======================================================================


class TestExecuteWithRetry:
    def test_success_first_attempt(self):
        req = MagicMock()
        req.execute.return_value = {"ok": True}
        assert _execute_with_retry(req) == {"ok": True}
        assert req.execute.call_count == 1

    @patch("time.sleep")
    @patch("random.uniform", return_value=0.1)
    def test_retries_on_transient_error(self, mock_rand, mock_sleep):
        if HttpError is None:
            pytest.skip("googleapiclient not available")
        resp = MagicMock()
        resp.status = 429
        req = MagicMock()
        error = HttpError(resp=resp, content=b"rate limited")
        req.execute.side_effect = [error, error, {"ok": True}]
        result = _execute_with_retry(req, max_attempts=4)
        assert result == {"ok": True}
        assert req.execute.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("time.sleep")
    @patch("random.uniform", return_value=0.1)
    def test_gives_up_after_max_attempts(self, mock_rand, mock_sleep):
        if HttpError is None:
            pytest.skip("googleapiclient not available")
        resp = MagicMock()
        resp.status = 500
        req = MagicMock()
        error = HttpError(resp=resp, content=b"server error")
        req.execute.side_effect = error
        with pytest.raises(HttpError):
            _execute_with_retry(req, max_attempts=3)
        assert req.execute.call_count == 3

    def test_non_transient_error_not_retried(self):
        if HttpError is None:
            pytest.skip("googleapiclient not available")
        resp = MagicMock()
        resp.status = 403
        req = MagicMock()
        error = HttpError(resp=resp, content=b"forbidden")
        req.execute.side_effect = error
        with pytest.raises(HttpError):
            _execute_with_retry(req, max_attempts=4)
        assert req.execute.call_count == 1


# ======================================================================
# create_service authentication
# ======================================================================


class TestCreateService:
    def test_missing_credentials_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(FileNotFoundError, match="not provided"):
                create_service(credentials_path=None, env_var="PLAY_SERVICE_ACCOUNT_JSON")

    def test_credentials_path_not_found(self, tmp_path):
        bad_path = str(tmp_path / "nonexistent.json")
        with pytest.raises(FileNotFoundError, match="not found"):
            create_service(credentials_path=bad_path)

    def test_env_var_with_bad_json_and_no_file(self, tmp_path):
        # Value is not valid JSON, so it's treated as a path → FileNotFoundError
        with patch.dict(os.environ, {"TEST_CREDS": "not-json-and-not-a-path!!!"}, clear=False):
            with pytest.raises(FileNotFoundError, match="not found"):
                create_service(credentials_path=None, env_var="TEST_CREDS")

    def test_env_var_pointing_to_nonexistent_file(self, tmp_path):
        fake_path = str(tmp_path / "missing.json")
        with patch.dict(os.environ, {"TEST_CREDS": fake_path}, clear=False):
            with pytest.raises(FileNotFoundError, match="not found"):
                create_service(credentials_path=None, env_var="TEST_CREDS")

    def test_env_var_pointing_to_invalid_json_file(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json", encoding="utf-8")
        with patch.dict(os.environ, {"TEST_CREDS": str(bad_file)}, clear=False):
            with pytest.raises(ValueError, match="not valid JSON"):
                create_service(credentials_path=None, env_var="TEST_CREDS")


# ======================================================================
# fetch_listings
# ======================================================================


class TestFetchListings:
    def test_fetch_all_locales(self):
        svc = _mock_service()
        edits = svc.edits.return_value
        edits.listings.return_value.list.return_value.execute.return_value = {
            "listings": [
                {"language": "en-US", "title": "My App", "shortDescription": "Short", "fullDescription": "Full"},
                {"language": "fr-FR", "title": "Mon App", "shortDescription": "Court", "fullDescription": "Complet"},
            ]
        }
        result = fetch_listings(svc, "com.example.app")
        assert result["global"]["default_language"] == "en-US"
        assert result["global"]["contact_email"] == "test@example.com"
        locales = result["locales"]
        assert len(locales) == 2
        assert locales["en-US"]["title"] == "My App"
        assert locales["fr-FR"]["fullDescription"] == "Complet"
        # Edit should be deleted
        edits.delete.return_value.execute.assert_called_once()

    def test_fetch_with_locale_filter(self):
        svc = _mock_service()
        edits = svc.edits.return_value
        edits.listings.return_value.list.return_value.execute.return_value = {
            "listings": [
                {"language": "en-US", "title": "My App", "shortDescription": "", "fullDescription": ""},
                {"language": "fr-FR", "title": "Mon App", "shortDescription": "", "fullDescription": ""},
                {"language": "de-DE", "title": "Meine App", "shortDescription": "", "fullDescription": ""},
            ]
        }
        result = fetch_listings(svc, "com.example.app", locales=["en-US", "de-DE"])
        assert set(result["locales"].keys()) == {"en-US", "de-DE"}

    def test_fetch_empty_listings(self):
        svc = _mock_service()
        result = fetch_listings(svc, "com.example.app")
        assert result["locales"] == {}

    def test_fetch_skips_entries_without_language(self):
        svc = _mock_service()
        edits = svc.edits.return_value
        edits.listings.return_value.list.return_value.execute.return_value = {
            "listings": [
                {"title": "No Language"},
                {"language": "en-US", "title": "Good"},
            ]
        }
        result = fetch_listings(svc, "com.example.app")
        assert len(result["locales"]) == 1
        assert "en-US" in result["locales"]

    def test_fetch_none_listings_value(self):
        svc = _mock_service()
        edits = svc.edits.return_value
        edits.listings.return_value.list.return_value.execute.return_value = {
            "listings": None
        }
        result = fetch_listings(svc, "com.example.app")
        assert result["locales"] == {}


# ======================================================================
# push_listings
# ======================================================================


class TestPushListings:
    def test_push_basic(self):
        svc = _mock_service()
        result = push_listings(
            svc, "com.example.app",
            {"en-US": {"title": "My App", "shortDescription": "Short", "fullDescription": "Full"}},
        )
        assert result["ok"] is True
        assert result["updated_locales"] == ["en-US"]
        assert result["committed"] is True

    def test_push_skips_empty_bodies(self):
        svc = _mock_service()
        result = push_listings(
            svc, "com.example.app",
            {"en-US": {}},  # no fields
        )
        assert result["ok"] is True
        assert result["updated_locales"] == []

    def test_push_skips_falsy_fields(self):
        svc = _mock_service()
        result = push_listings(
            svc, "com.example.app",
            {"en-US": {"title": "", "shortDescription": None, "fullDescription": ""}},
        )
        assert result["updated_locales"] == []

    def test_push_multiple_locales(self):
        svc = _mock_service()
        data = {
            "en-US": {"title": "English"},
            "fr-FR": {"title": "French"},
            "de-DE": {"title": "German"},
        }
        result = push_listings(svc, "com.example.app", data)
        assert result["updated_locales"] == ["de-DE", "en-US", "fr-FR"]  # sorted

    def test_push_with_release_notes(self):
        svc = _mock_service()
        edits = svc.edits.return_value
        edits.tracks.return_value.get.return_value.execute.return_value = {
            "releases": [
                {"versionCodes": ["42"], "releaseNotes": []}
            ]
        }
        result = push_listings(
            svc, "com.example.app",
            {"en-US": {"title": "Title"}},
            release_notes={"en-US": "What's new"},
            track="production",
            version_code=42,
        )
        assert result["ok"] is True

    def test_push_release_notes_without_version_code_skips(self):
        svc = _mock_service()
        # version_code is None, so release notes should be skipped
        result = push_listings(
            svc, "com.example.app",
            {"en-US": {"title": "Title"}},
            release_notes={"en-US": "What's new"},
            track="production",
            version_code=None,
        )
        assert result["ok"] is True
        # tracks().get should NOT have been called
        svc.edits.return_value.tracks.return_value.get.return_value.execute.assert_not_called()


# ======================================================================
# update_release_notes
# ======================================================================


class TestUpdateReleaseNotes:
    def test_update_success(self):
        svc = _mock_service()
        edits = svc.edits.return_value
        edits.tracks.return_value.get.return_value.execute.return_value = {
            "releases": [
                {"versionCodes": ["100"], "status": "completed", "releaseNotes": []}
            ]
        }
        result = update_release_notes(
            svc, "com.example.app", "production", 100,
            {"en-US": "Bug fixes", "fr-FR": "Corrections"},
        )
        assert result["ok"] is True
        assert result["version_code"] == 100

    def test_version_code_not_found_raises(self):
        svc = _mock_service()
        edits = svc.edits.return_value
        edits.tracks.return_value.get.return_value.execute.return_value = {
            "releases": [
                {"versionCodes": ["100"], "status": "completed"}
            ]
        }
        with pytest.raises(RuntimeError, match="No release found"):
            update_release_notes(
                svc, "com.example.app", "production", 999,
                {"en-US": "Bug fixes"},
            )

    def test_empty_text_is_filtered(self):
        svc = _mock_service()
        edits = svc.edits.return_value
        edits.tracks.return_value.get.return_value.execute.return_value = {
            "releases": [
                {"versionCodes": ["100"], "releaseNotes": []}
            ]
        }
        result = update_release_notes(
            svc, "com.example.app", "production", 100,
            {"en-US": "Good", "fr-FR": "", "de-DE": ""},
        )
        assert result["ok"] is True


# ======================================================================
# upload_screenshots
# ======================================================================


class TestUploadScreenshots:
    def test_upload_basic(self, tmp_path):
        svc = _mock_service()
        img = tmp_path / "screen1.png"
        img.write_bytes(b"fake-png-data")

        result = upload_screenshots(
            svc, "com.example.app", "en-US", "phoneScreenshots",
            [str(img)], replace=True,
        )
        assert result["ok"] is True
        assert result["uploaded"] == 1

    def test_invalid_image_type_raises(self, tmp_path):
        svc = _mock_service()
        img = tmp_path / "screen1.png"
        img.write_bytes(b"data")
        with pytest.raises(ValueError, match="Invalid image_type"):
            upload_screenshots(svc, "com.example.app", "en-US", "invalidType", [str(img)])

    def test_missing_file_raises(self):
        svc = _mock_service()
        with pytest.raises(FileNotFoundError, match="not found"):
            upload_screenshots(svc, "com.example.app", "en-US", "phoneScreenshots", ["/no/such/file.png"])

    def test_skip_when_hashes_match(self, tmp_path):
        svc = _mock_service()
        img = tmp_path / "screen1.png"
        img.write_bytes(b"exact-content")
        sha = hashlib.sha1(b"exact-content").hexdigest()

        edits = svc.edits.return_value
        edits.images.return_value.list.return_value.execute.return_value = {
            "images": [{"sha1": sha}]
        }

        result = upload_screenshots(
            svc, "com.example.app", "en-US", "phoneScreenshots",
            [str(img)], replace=True,
        )
        assert result["ok"] is True
        assert result["uploaded"] == 0
        assert result["skipped"] == 1

    def test_hashes_differ_triggers_replace(self, tmp_path):
        svc = _mock_service()
        img = tmp_path / "screen1.png"
        img.write_bytes(b"new-content")

        edits = svc.edits.return_value
        edits.images.return_value.list.return_value.execute.return_value = {
            "images": [{"sha1": "oldhash123"}]
        }

        result = upload_screenshots(
            svc, "com.example.app", "en-US", "phoneScreenshots",
            [str(img)], replace=True,
        )
        assert result["ok"] is True
        assert result["uploaded"] == 1
        # deleteall should have been called
        edits.images.return_value.deleteall.return_value.execute.assert_called_once()

    def test_no_replace_mode(self, tmp_path):
        svc = _mock_service()
        img = tmp_path / "screen1.png"
        img.write_bytes(b"data")

        result = upload_screenshots(
            svc, "com.example.app", "en-US", "phoneScreenshots",
            [str(img)], replace=False,
        )
        assert result["ok"] is True
        assert result["uploaded"] == 1
        # deleteall should NOT have been called
        svc.edits.return_value.images.return_value.deleteall.return_value.execute.assert_not_called()

    def test_multiple_files(self, tmp_path):
        svc = _mock_service()
        imgs = []
        for i in range(3):
            img = tmp_path / f"screen{i}.png"
            img.write_bytes(f"data-{i}".encode())
            imgs.append(str(img))

        result = upload_screenshots(
            svc, "com.example.app", "en-US", "phoneScreenshots",
            imgs, replace=True,
        )
        assert result["ok"] is True
        assert result["uploaded"] == 3


# ======================================================================
# publish_bundle
# ======================================================================


class TestPublishBundle:
    def test_publish_basic(self, tmp_path):
        svc = _mock_service()
        bundle = tmp_path / "app.aab"
        bundle.write_bytes(b"fake-bundle")

        result = publish_bundle(svc, "com.example.app", str(bundle))
        assert result["ok"] is True
        assert result["version_code"] == 42
        assert result["track"] == "internal"

    def test_invalid_status_raises(self, tmp_path):
        svc = _mock_service()
        bundle = tmp_path / "app.aab"
        bundle.write_bytes(b"data")
        with pytest.raises(ValueError, match="Invalid status"):
            publish_bundle(svc, "com.example.app", str(bundle), status="badstatus")

    def test_missing_bundle_raises(self):
        svc = _mock_service()
        with pytest.raises(FileNotFoundError, match="not found"):
            publish_bundle(svc, "com.example.app", "/no/such/file.aab")

    def test_publish_with_mapping(self, tmp_path):
        svc = _mock_service()
        bundle = tmp_path / "app.aab"
        bundle.write_bytes(b"bundle-data")
        mapping = tmp_path / "mapping.txt"
        mapping.write_text("some proguard mapping")

        result = publish_bundle(
            svc, "com.example.app", str(bundle),
            mapping_path=str(mapping),
        )
        assert result["ok"] is True
        # deobfuscation upload should have been called
        svc.edits.return_value.deobfuscationfiles.return_value.upload.return_value.execute.assert_called_once()

    def test_publish_with_nonexistent_mapping_skips(self, tmp_path):
        svc = _mock_service()
        bundle = tmp_path / "app.aab"
        bundle.write_bytes(b"bundle-data")

        result = publish_bundle(
            svc, "com.example.app", str(bundle),
            mapping_path=str(tmp_path / "nonexistent.txt"),
        )
        assert result["ok"] is True
        # deobfuscation upload should NOT have been called
        svc.edits.return_value.deobfuscationfiles.return_value.upload.return_value.execute.assert_not_called()

    def test_publish_with_release_notes(self, tmp_path):
        svc = _mock_service()
        bundle = tmp_path / "app.aab"
        bundle.write_bytes(b"bundle-data")

        result = publish_bundle(
            svc, "com.example.app", str(bundle),
            release_notes={"en-US": "What's new", "fr-FR": "Quoi de neuf"},
        )
        assert result["ok"] is True

    def test_all_valid_statuses(self, tmp_path):
        for status in VALID_RELEASE_STATUSES:
            svc = _mock_service()
            bundle = tmp_path / "app.aab"
            bundle.write_bytes(b"data")
            result = publish_bundle(svc, "com.example.app", str(bundle), status=status)
            assert result["ok"] is True

    def test_all_valid_tracks(self, tmp_path):
        for track in ("internal", "alpha", "beta", "production"):
            svc = _mock_service()
            bundle = tmp_path / "app.aab"
            bundle.write_bytes(b"data")
            result = publish_bundle(svc, "com.example.app", str(bundle), track=track)
            assert result["track"] == track


# ======================================================================
# ensure_managed_products
# ======================================================================


class TestEnsureManagedProducts:
    def test_create_new_product(self):
        if HttpError is None:
            pytest.skip("googleapiclient not available")
        svc = _mock_service()
        monetization = svc.monetization.return_value
        resp = MagicMock()
        resp.status = 404
        monetization.onetimeproducts.return_value.get.return_value.execute.side_effect = (
            HttpError(resp=resp, content=b"not found")
        )

        result = ensure_managed_products(svc, "com.example.app", [
            {
                "sku": "credits_3",
                "default_price": {"currency": "USD", "price": 2.99},
                "listings": {"en-US": {"title": "3 Credits", "description": "Buy 3 credits"}},
            }
        ])
        assert result["ok"] is True
        assert result["created"] == ["credits_3"]
        assert result["updated"] == []

    def test_update_existing_product(self):
        svc = _mock_service()
        result = ensure_managed_products(svc, "com.example.app", [
            {
                "sku": "credits_3",
                "default_price": {"currency": "USD", "price": 2.99},
                "listings": {"en-US": {"title": "3 Credits"}},
            }
        ])
        assert result["ok"] is True
        assert result["updated"] == ["credits_3"]
        assert result["created"] == []

    def test_multiple_products(self):
        svc = _mock_service()
        result = ensure_managed_products(svc, "com.example.app", [
            {"sku": "a", "listings": {}},
            {"sku": "b", "listings": {}},
        ])
        assert result["ok"] is True
        assert len(result["updated"]) == 2

    def test_empty_listings_skipped(self):
        svc = _mock_service()
        result = ensure_managed_products(svc, "com.example.app", [
            {"sku": "a", "listings": {"en-US": {"title": "", "description": ""}}},
        ])
        assert result["ok"] is True

    def test_no_default_price(self):
        svc = _mock_service()
        result = ensure_managed_products(svc, "com.example.app", [
            {"sku": "a", "listings": {}},
        ])
        assert result["ok"] is True


# ======================================================================
# apply_regional_pricing
# ======================================================================


class TestApplyRegionalPricing:
    def test_basic_pricing(self):
        svc = _mock_service()
        result = apply_regional_pricing(
            svc, "com.example.app", "credits_3",
            {"US": {"currency": "USD", "price": 2.99}, "CA": {"currency": "CAD", "price": 3.99}},
        )
        assert result["ok"] is True
        assert result["sku"] == "credits_3"
        assert result["regions_applied"] == 2

    def test_empty_regions(self):
        svc = _mock_service()
        result = apply_regional_pricing(svc, "com.example.app", "credits_3", {})
        assert result["regions_applied"] == 0


# ======================================================================
# apply_subscription_regional_pricing
# ======================================================================


class TestApplySubscriptionRegionalPricing:
    def test_basic(self):
        svc = _mock_service()
        monetization = svc.monetization.return_value
        monetization.subscriptions.return_value.get.return_value.execute.return_value = {
            "basePlans": [
                {"basePlanId": "monthly", "regionalConfigs": []}
            ]
        }
        result = apply_subscription_regional_pricing(
            svc, "com.example.app", "premium", "monthly",
            {"US": {"currency": "USD", "price": 9.99}},
        )
        assert result["ok"] is True
        assert result["subscription_id"] == "premium"
        assert result["regions_applied"] == 1

    def test_base_plan_not_found(self):
        svc = _mock_service()
        monetization = svc.monetization.return_value
        monetization.subscriptions.return_value.get.return_value.execute.return_value = {
            "basePlans": [{"basePlanId": "yearly"}]
        }
        with pytest.raises(RuntimeError, match="Base plan"):
            apply_subscription_regional_pricing(
                svc, "com.example.app", "premium", "monthly",
                {"US": {"currency": "USD", "price": 9.99}},
            )

    def test_updates_existing_region(self):
        svc = _mock_service()
        monetization = svc.monetization.return_value
        monetization.subscriptions.return_value.get.return_value.execute.return_value = {
            "basePlans": [
                {
                    "basePlanId": "monthly",
                    "regionalConfigs": [
                        {"regionCode": "US", "price": {"currency": "USD", "priceMicros": "4990000"}},
                    ],
                }
            ]
        }
        result = apply_subscription_regional_pricing(
            svc, "com.example.app", "premium", "monthly",
            {"US": {"currency": "USD", "price": 9.99}},
        )
        assert result["ok"] is True


# ======================================================================
# Helper functions
# ======================================================================


# ======================================================================
# fetch_products
# ======================================================================


class TestFetchProducts:
    def test_fetch_empty(self):
        svc = _mock_service()
        result = fetch_products(svc, "com.example.app")
        assert result == {}

    def test_fetch_with_products_new_api(self):
        """New monetization.onetimeproducts API returns 'oneTimeProducts' key with purchaseOptions pricing."""
        svc = _mock_service()
        monetization = svc.monetization.return_value
        monetization.onetimeproducts.return_value.list.return_value.execute.return_value = {
            "oneTimeProducts": [
                {
                    "productId": "credits_3",
                    "listings": [
                        {"languageCode": "en-US", "title": "3 Credits", "description": "Buy 3 credits"},
                    ],
                    "purchaseOptions": [
                        {
                            "purchaseOptionId": "legacy-base",
                            "regionalPricingAndAvailabilityConfigs": [
                                {
                                    "regionCode": "US",
                                    "price": {"currencyCode": "USD", "units": "0", "nanos": 990000000},
                                    "availability": "AVAILABLE",
                                },
                                {
                                    "regionCode": "IN",
                                    "price": {"currencyCode": "INR", "units": "29", "nanos": 0},
                                    "availability": "AVAILABLE",
                                },
                            ],
                        },
                    ],
                },
            ]
        }
        result = fetch_products(svc, "com.example.app")
        assert "credits_3" in result
        prod = result["credits_3"]
        assert prod["type"] == "consumable"
        assert prod["default_price"]["currency"] == "USD"
        assert prod["default_price"]["price"] == 0.99
        assert prod["localizations"]["en-US"]["title"] == "3 Credits"
        assert prod["pricing"]["US"]["price"] == 0.99
        assert prod["pricing"]["IN"]["currency"] == "INR"
        assert prod["pricing"]["IN"]["price"] == 29.0

    def test_fetch_with_products_legacy_api(self):
        """Legacy API returns 'inappproduct' key with dict-style listings."""
        svc = _mock_service()
        monetization = svc.monetization.return_value
        monetization.onetimeproducts.return_value.list.return_value.execute.return_value = {
            "inappproduct": [
                {
                    "sku": "credits_3",
                    "defaultPrice": {"currency": "USD", "priceMicros": "990000"},
                    "listings": {
                        "en-US": {"title": "3 Credits", "description": "Buy 3 credits"},
                    },
                    "prices": {
                        "US": {"currency": "USD", "priceMicros": "990000"},
                    },
                },
            ]
        }
        result = fetch_products(svc, "com.example.app")
        assert "credits_3" in result
        prod = result["credits_3"]
        assert prod["type"] == "consumable"
        assert prod["default_price"]["price"] == 0.99
        assert prod["localizations"]["en-US"]["title"] == "3 Credits"

    def test_fetch_no_price(self):
        svc = _mock_service()
        monetization = svc.monetization.return_value
        monetization.onetimeproducts.return_value.list.return_value.execute.return_value = {
            "oneTimeProducts": [
                {"productId": "test_sku", "listings": []},
            ]
        }
        result = fetch_products(svc, "com.example.app")
        assert "test_sku" in result
        assert "default_price" not in result["test_sku"]


# ======================================================================
# fetch_subscriptions
# ======================================================================


class TestFetchSubscriptions:
    def test_fetch_empty(self):
        svc = _mock_service()
        result = fetch_subscriptions(svc, "com.example.app")
        assert result == {}

    def test_fetch_with_subscriptions(self):
        """Subscriptions API returns Money proto (currencyCode/units/nanos) in regionalConfigs."""
        svc = _mock_service()
        monetization = svc.monetization.return_value
        monetization.subscriptions.return_value.list.return_value.execute.return_value = {
            "subscriptions": [
                {
                    "productId": "premium_monthly",
                    "listings": [
                        {"languageCode": "en-US", "title": "Premium Monthly", "description": "Monthly sub"},
                    ],
                    "basePlans": [
                        {
                            "basePlanId": "monthly",
                            "regionalConfigs": [
                                {"regionCode": "US", "price": {"currencyCode": "USD", "units": "7", "nanos": 990000000}},
                            ],
                        },
                    ],
                },
            ]
        }
        result = fetch_subscriptions(svc, "com.example.app")
        assert "premium_monthly" in result
        sub = result["premium_monthly"]
        assert sub["localizations"]["en-US"]["title"] == "Premium Monthly"
        assert sub["base_plans"]["monthly"]["pricing"]["US"]["price"] == 7.99
        assert sub["base_plans"]["monthly"]["pricing"]["US"]["currency"] == "USD"

    def test_fetch_with_subscriptions_legacy_pricing(self):
        """Legacy format uses currency/priceMicros."""
        svc = _mock_service()
        monetization = svc.monetization.return_value
        monetization.subscriptions.return_value.list.return_value.execute.return_value = {
            "subscriptions": [
                {
                    "productId": "premium_monthly",
                    "listings": [
                        {"languageCode": "en-US", "title": "Premium Monthly", "description": "Monthly sub"},
                    ],
                    "basePlans": [
                        {
                            "basePlanId": "monthly",
                            "regionalConfigs": [
                                {"regionCode": "US", "price": {"currency": "USD", "priceMicros": "7990000"}},
                            ],
                        },
                    ],
                },
            ]
        }
        result = fetch_subscriptions(svc, "com.example.app")
        assert result["premium_monthly"]["base_plans"]["monthly"]["pricing"]["US"]["price"] == 7.99

    def test_fetch_dict_listings(self):
        """Subscriptions may have listings as dict instead of list."""
        svc = _mock_service()
        monetization = svc.monetization.return_value
        monetization.subscriptions.return_value.list.return_value.execute.return_value = {
            "subscriptions": [
                {
                    "productId": "sub_1",
                    "listings": {
                        "en-US": {"title": "Sub", "description": "A subscription"},
                    },
                    "basePlans": [],
                },
            ]
        }
        result = fetch_subscriptions(svc, "com.example.app")
        assert "sub_1" in result
        assert result["sub_1"]["localizations"]["en-US"]["title"] == "Sub"

    def test_fetch_no_base_plans(self):
        svc = _mock_service()
        monetization = svc.monetization.return_value
        monetization.subscriptions.return_value.list.return_value.execute.return_value = {
            "subscriptions": [
                {"productId": "basic", "listings": [], "basePlans": []},
            ]
        }
        result = fetch_subscriptions(svc, "com.example.app")
        assert "basic" in result
        assert "base_plans" not in result["basic"]


# ======================================================================
# Helper functions
# ======================================================================


class TestHelperFunctions:
    def test_price_to_money(self):
        result = _price_to_money("USD", 2.99)
        assert result["currency"] == "USD"
        assert result["priceMicros"] == "2990000"

    def test_price_to_money_zero(self):
        result = _price_to_money("EUR", 0)
        assert result["priceMicros"] == "0"

    def test_price_to_money_round(self):
        result = _price_to_money("USD", 1.005)
        assert result["priceMicros"] == "1005000"

    def test_compute_sha1(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        expected = hashlib.sha1(b"hello world").hexdigest()
        assert _compute_sha1(f) == expected

    def test_valid_image_types_set(self):
        assert "phoneScreenshots" in VALID_IMAGE_TYPES
        assert "featureGraphic" in VALID_IMAGE_TYPES
        assert "invalid" not in VALID_IMAGE_TYPES

    def test_valid_release_statuses_set(self):
        assert "draft" in VALID_RELEASE_STATUSES
        assert "completed" in VALID_RELEASE_STATUSES
        assert "invalid" not in VALID_RELEASE_STATUSES
