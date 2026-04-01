"""Extensive tests for service layer: prepare, validate, import, and diff methods."""

from __future__ import annotations

from pathlib import Path

import pytest

from perfectdeckcli.service import ListingService, diff_objects
from perfectdeckcli.storage import InMemoryStorageBackend


# ======================================================================
# Helpers
# ======================================================================


def _svc(tmp_path: Path | None = None) -> ListingService:
    """Create a ListingService with an in-memory backend."""
    return ListingService(InMemoryStorageBackend())


def _init_play(svc: ListingService, app: str = "myapp", locales: list | None = None) -> None:
    """Init a play store listing with given locales."""
    svc.init_listing(app, stores=["play"], locales=locales or ["en-US"])


def _init_app_store(svc: ListingService, app: str = "myapp", locales: list | None = None) -> None:
    """Init an app_store listing with given locales."""
    svc.init_listing(app, stores=["app_store"], locales=locales or ["en-US"])


def _populate_play(svc: ListingService, app: str = "myapp", locale: str = "en-US", data: dict | None = None) -> None:
    """Set up play store data for a locale."""
    default_data = {"title": "My App", "short_description": "Short", "full_description": "Full desc"}
    svc.upsert_locale(app, "play", locale, data or default_data)


def _populate_app_store(svc: ListingService, app: str = "myapp", locale: str = "en-US", data: dict | None = None) -> None:
    """Set up app_store data for a locale."""
    default_data = {
        "app_name": "My App",
        "subtitle": "Best app",
        "description": "Full description",
        "keywords": "app,tools",
    }
    svc.upsert_locale(app, "app_store", locale, data or default_data)


# ======================================================================
# _map_play_store_data
# ======================================================================


class TestMapPlayStoreData:
    def test_basic_mapping(self):
        data = {
            "en-US": {
                "title": "English Title",
                "shortDescription": "Short",
                "fullDescription": "Full",
            }
        }
        result = ListingService._map_play_store_data(data)
        assert result["en-US"]["title"] == "English Title"
        assert result["en-US"]["short_description"] == "Short"
        assert result["en-US"]["full_description"] == "Full"

    def test_skips_empty_fields(self):
        data = {
            "en-US": {"title": "Title", "shortDescription": "", "fullDescription": ""},
        }
        result = ListingService._map_play_store_data(data)
        assert result["en-US"] == {"title": "Title"}

    def test_skips_empty_locales(self):
        data = {
            "en-US": {"title": "", "shortDescription": "", "fullDescription": ""},
        }
        result = ListingService._map_play_store_data(data)
        assert result == {}

    def test_multiple_locales(self):
        data = {
            "en-US": {"title": "English", "shortDescription": "", "fullDescription": ""},
            "fr-FR": {"title": "French", "shortDescription": "Court", "fullDescription": ""},
        }
        result = ListingService._map_play_store_data(data)
        assert set(result.keys()) == {"en-US", "fr-FR"}

    def test_sorted_output(self):
        data = {
            "fr-FR": {"title": "French", "shortDescription": "", "fullDescription": ""},
            "en-US": {"title": "English", "shortDescription": "", "fullDescription": ""},
        }
        result = ListingService._map_play_store_data(data)
        assert list(result.keys()) == ["en-US", "fr-FR"]


# ======================================================================
# _map_app_store_data
# ======================================================================


class TestMapAppStoreData:
    def test_basic_mapping(self):
        data = {
            "en-US": {"app_name": "My App", "subtitle": "Best", "description": "Full"},
        }
        result = ListingService._map_app_store_data(data)
        assert result["en-US"]["app_name"] == "My App"

    def test_filters_empty_values(self):
        data = {
            "en-US": {"app_name": "My App", "subtitle": "", "description": None},
        }
        result = ListingService._map_app_store_data(data)
        assert result["en-US"] == {"app_name": "My App"}

    def test_skips_fully_empty_locale(self):
        data = {
            "en-US": {"app_name": "", "subtitle": ""},
        }
        result = ListingService._map_app_store_data(data)
        assert result == {}


# ======================================================================
# import_from_play_store
# ======================================================================


class TestImportFromPlayStore:
    def test_basic_import(self):
        svc = _svc()
        _init_play(svc)

        data = {
            "en-US": {"title": "Title", "shortDescription": "Short", "fullDescription": "Full"},
        }
        result = svc.import_from_play_store("myapp", data)
        assert result["ok"] is True
        assert result["imported_locales"] == ["en-US"]

        section = svc.list_section("myapp", "play", locale="en-US")
        assert section["title"] == "Title"
        assert section["short_description"] == "Short"

    def test_import_merges_with_existing(self):
        svc = _svc()
        _init_play(svc)
        svc.upsert_locale("myapp", "play", "en-US", {"custom_field": "keep me"})

        data = {"en-US": {"title": "New Title", "shortDescription": "", "fullDescription": ""}}
        svc.import_from_play_store("myapp", data)

        section = svc.list_section("myapp", "play", locale="en-US")
        assert section["title"] == "New Title"
        assert section["custom_field"] == "keep me"

    def test_import_creates_new_locale(self):
        svc = _svc()
        _init_play(svc)

        data = {"fr-FR": {"title": "French Title", "shortDescription": "Court", "fullDescription": "Complet"}}
        result = svc.import_from_play_store("myapp", data)
        assert "fr-FR" in result["imported_locales"]

        section = svc.list_section("myapp", "play", locale="fr-FR")
        assert section["title"] == "French Title"

    def test_import_skips_empty_data(self):
        svc = _svc()
        _init_play(svc)

        data = {"en-US": {"title": "", "shortDescription": "", "fullDescription": ""}}
        result = svc.import_from_play_store("myapp", data)
        assert result["imported_locales"] == []

    def test_import_multiple_locales(self):
        svc = _svc()
        _init_play(svc, locales=["en-US", "fr-FR", "de-DE"])

        data = {
            "en-US": {"title": "English", "shortDescription": "S", "fullDescription": "F"},
            "fr-FR": {"title": "French", "shortDescription": "C", "fullDescription": "C"},
            "de-DE": {"title": "German", "shortDescription": "K", "fullDescription": "V"},
        }
        result = svc.import_from_play_store("myapp", data)
        assert len(result["imported_locales"]) == 3


# ======================================================================
# import_from_app_store
# ======================================================================


class TestImportFromAppStore:
    def test_basic_import(self):
        svc = _svc()
        _init_app_store(svc)

        data = {
            "en-US": {
                "app_name": "My App",
                "subtitle": "Best",
                "description": "Full desc",
                "keywords": "app,tools",
            }
        }
        result = svc.import_from_app_store("myapp", data)
        assert result["ok"] is True
        assert result["imported_locales"] == ["en-US"]

    def test_import_skips_empty_locale(self):
        svc = _svc()
        _init_app_store(svc)

        data = {"en-US": {"app_name": "", "subtitle": ""}}
        result = svc.import_from_app_store("myapp", data)
        assert result["imported_locales"] == []


# ======================================================================
# diff_with_play_store_data
# ======================================================================


# ======================================================================
# import_from_play_store with products/subscriptions
# ======================================================================


class TestImportFromPlayStoreWithProducts:
    def test_import_with_products(self):
        svc = _svc()
        _init_play(svc)

        data = {
            "en-US": {"title": "Title", "shortDescription": "Short", "fullDescription": "Full"},
        }
        products = {
            "com.example.credits": {
                "type": "consumable",
                "default_price": {"currency": "USD", "price": 0.99},
                "localizations": {"en-US": {"title": "3 Credits", "description": "Buy 3"}},
            }
        }
        result = svc.import_from_play_store("myapp", data, products_data=products)
        assert result["ok"] is True

        # Check products were stored
        doc = svc.storage.load()
        section = doc["apps"]["myapp"]["play"]
        assert "com.example.credits" in section["products"]
        assert section["products"]["com.example.credits"]["type"] == "consumable"

    def test_import_with_subscriptions(self):
        svc = _svc()
        _init_play(svc)

        data = {"en-US": {"title": "Title", "shortDescription": "", "fullDescription": ""}}
        subs = {
            "com.example.premium": {
                "localizations": {"en-US": {"title": "Premium", "description": "Monthly sub"}},
                "base_plans": {"monthly": {"pricing": {"US": {"currency": "USD", "price": 7.99}}}},
            }
        }
        result = svc.import_from_play_store("myapp", data, subscriptions_data=subs)
        assert result["ok"] is True

        doc = svc.storage.load()
        section = doc["apps"]["myapp"]["play"]
        assert "com.example.premium" in section["subscriptions"]

    def test_import_without_products_leaves_existing(self):
        svc = _svc()
        _init_play(svc)

        # First import with products
        data = {"en-US": {"title": "T", "shortDescription": "", "fullDescription": ""}}
        svc.import_from_play_store("myapp", data, products_data={"sku1": {"type": "consumable"}})

        # Second import without products
        svc.import_from_play_store("myapp", data)

        doc = svc.storage.load()
        section = doc["apps"]["myapp"]["play"]
        # Products should still be there (not overwritten with empty)
        assert "sku1" in section["products"]


class TestImportFromAppStoreWithProducts:
    def test_import_with_products_and_subscriptions(self):
        svc = _svc()
        _init_app_store(svc)

        data = {
            "en-US": {"app_name": "My App", "description": "Full desc"},
        }
        products = {
            "com.example.credits": {
                "type": "consumable",
                "localizations": {"en-US": {"name": "3 Credits", "description": "Buy 3"}},
            }
        }
        subs = {
            "com.example.premium": {
                "group_name": "Premium",
                "localizations": {"en-US": {"name": "Premium", "description": "Monthly"}},
            }
        }
        result = svc.import_from_app_store(
            "myapp", data, products_data=products, subscriptions_data=subs,
        )
        assert result["ok"] is True

        doc = svc.storage.load()
        section = doc["apps"]["myapp"]["app_store"]
        assert "com.example.credits" in section["products"]
        assert "com.example.premium" in section["subscriptions"]
        assert section["subscriptions"]["com.example.premium"]["group_name"] == "Premium"


# ======================================================================
# list_section includes products/subscriptions
# ======================================================================


class TestListSectionWithProducts:
    def test_list_section_includes_products(self):
        svc = _svc()
        _init_play(svc)

        data = {"en-US": {"title": "T", "shortDescription": "", "fullDescription": ""}}
        svc.import_from_play_store(
            "myapp", data,
            products_data={"sku1": {"type": "consumable"}},
            subscriptions_data={"sub1": {"localizations": {}}},
        )

        section = svc.list_section("myapp", "play")
        assert "products" in section
        assert section["products"]["sku1"]["type"] == "consumable"
        assert "subscriptions" in section
        assert "sub1" in section["subscriptions"]

    def test_list_section_omits_empty_products(self):
        svc = _svc()
        _init_play(svc)

        section = svc.list_section("myapp", "play")
        assert "products" not in section
        assert "subscriptions" not in section


class TestDiffWithPlayStoreData:
    def test_diff_detects_changes(self):
        svc = _svc()
        _init_play(svc)
        _populate_play(svc, data={"title": "Old Title"})

        remote = {"en-US": {"title": "New Title", "shortDescription": "", "fullDescription": ""}}
        result = svc.diff_with_play_store_data("myapp", remote)
        assert result["locales"]["en-US"]["same"] is False
        assert "en-US" in result["summary"]["changed_locales"]

    def test_diff_no_changes(self):
        svc = _svc()
        _init_play(svc)
        _populate_play(svc, data={"title": "Same"})

        remote = {"en-US": {"title": "Same", "shortDescription": "", "fullDescription": ""}}
        result = svc.diff_with_play_store_data("myapp", remote)
        assert result["locales"]["en-US"]["same"] is True

    def test_diff_new_locale(self):
        svc = _svc()
        _init_play(svc)

        remote = {
            "en-US": {"title": "X", "shortDescription": "", "fullDescription": ""},
            "fr-FR": {"title": "French", "shortDescription": "", "fullDescription": ""},
        }
        result = svc.diff_with_play_store_data("myapp", remote)
        assert "fr-FR" in result["summary"]["new_locales"]

    def test_diff_nonexistent_app(self):
        svc = _svc()
        remote = {"en-US": {"title": "X", "shortDescription": "", "fullDescription": ""}}
        result = svc.diff_with_play_store_data("nonexistent", remote)
        assert result["summary"]["total_remote"] == 1
        assert "en-US" in result["summary"]["new_locales"]

    def test_diff_empty_remote(self):
        svc = _svc()
        _init_play(svc)
        _populate_play(svc)

        result = svc.diff_with_play_store_data("myapp", {})
        assert result["summary"]["total_remote"] == 0
        assert result["locales"] == {}


# ======================================================================
# diff_with_app_store_data
# ======================================================================


class TestDiffWithAppStoreData:
    def test_diff_detects_changes(self):
        svc = _svc()
        _init_app_store(svc)
        _populate_app_store(svc, data={"app_name": "Old Name"})

        remote = {"en-US": {"app_name": "New Name"}}
        result = svc.diff_with_app_store_data("myapp", remote)
        assert result["locales"]["en-US"]["same"] is False

    def test_diff_unchanged(self):
        svc = _svc()
        _init_app_store(svc)
        _populate_app_store(svc, data={"app_name": "Same"})

        remote = {"en-US": {"app_name": "Same"}}
        result = svc.diff_with_app_store_data("myapp", remote)
        assert result["locales"]["en-US"]["same"] is True


# ======================================================================
# validate_listing
# ======================================================================


class TestValidateListing:
    def test_valid_play_listing(self):
        svc = _svc()
        _init_play(svc)
        _populate_play(svc, data={"title": "Short"})

        result = svc.validate_listing("myapp", "play")
        assert result["ok"] is True

    def test_invalid_play_title(self):
        svc = _svc()
        _init_play(svc)
        _populate_play(svc, data={"title": "A" * 31})

        result = svc.validate_listing("myapp", "play")
        assert result["ok"] is False
        assert result["errors"][0]["field"] == "title"

    def test_valid_app_store_listing(self):
        svc = _svc()
        _init_app_store(svc)
        _populate_app_store(svc, data={"app_name": "My App"})

        result = svc.validate_listing("myapp", "app_store")
        assert result["ok"] is True

    def test_invalid_app_store_keywords(self):
        svc = _svc()
        _init_app_store(svc)
        _populate_app_store(svc, data={"keywords": "K" * 101})

        result = svc.validate_listing("myapp", "app_store")
        assert result["ok"] is False
        assert result["errors"][0]["field"] == "keywords"

    def test_validate_with_locale_filter(self):
        svc = _svc()
        _init_play(svc, locales=["en-US", "fr-FR"])
        _populate_play(svc, locale="en-US", data={"title": "A" * 31})
        _populate_play(svc, locale="fr-FR", data={"title": "OK"})

        # Only validate en-US → should fail
        result = svc.validate_listing("myapp", "play", locales=["en-US"])
        assert result["ok"] is False

        # Only validate fr-FR → should pass
        result = svc.validate_listing("myapp", "play", locales=["fr-FR"])
        assert result["ok"] is True

    def test_validate_nonexistent_app_raises(self):
        svc = _svc()
        with pytest.raises(KeyError):
            svc.validate_listing("nonexistent", "play")


# ======================================================================
# prepare_play_push_data
# ======================================================================


class TestPreparePlayPushData:
    def test_basic_preparation(self):
        svc = _svc()
        _init_play(svc)
        _populate_play(svc, data={
            "title": "My App",
            "short_description": "Short",
            "full_description": "Full description",
        })

        result = svc.prepare_play_push_data("myapp")
        assert "en-US" in result
        assert result["en-US"]["title"] == "My App"
        assert result["en-US"]["shortDescription"] == "Short"
        assert result["en-US"]["fullDescription"] == "Full description"

    def test_locale_mapping_applied(self):
        svc = _svc()
        _init_play(svc, locales=["zh-Hans"])
        _populate_play(svc, locale="zh-Hans", data={"title": "Chinese Title"})

        result = svc.prepare_play_push_data("myapp")
        # zh-Hans should map to zh-CN
        assert "zh-CN" in result
        assert result["zh-CN"]["title"] == "Chinese Title"

    def test_skips_empty_fields(self):
        svc = _svc()
        _init_play(svc)
        _populate_play(svc, data={"title": "", "short_description": "", "full_description": ""})

        result = svc.prepare_play_push_data("myapp")
        assert result == {}

    def test_locale_filter(self):
        svc = _svc()
        _init_play(svc, locales=["en-US", "fr-FR"])
        _populate_play(svc, locale="en-US", data={"title": "English"})
        _populate_play(svc, locale="fr-FR", data={"title": "French"})

        result = svc.prepare_play_push_data("myapp", locales=["en-US"])
        assert "en-US" in result
        assert len(result) == 1

    def test_non_dict_locale_skipped(self):
        svc = _svc()
        _init_play(svc)
        # Manually set a non-dict locale value
        doc = svc.storage.load()
        doc["apps"]["myapp"]["play"]["locales"]["bad"] = "not a dict"
        svc.storage.save(doc)

        result = svc.prepare_play_push_data("myapp")
        assert "bad" not in result


# ======================================================================
# prepare_play_release_notes
# ======================================================================


class TestPreparePlayReleaseNotes:
    def test_basic(self):
        svc = _svc()
        _init_play(svc)
        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "Bug fixes")

        result = svc.prepare_play_release_notes("myapp", app_version="2.0.0")
        assert result["en-US"] == "Bug fixes"

    def test_locale_mapping(self):
        svc = _svc()
        _init_play(svc, locales=["no"])
        svc.set_release_notes("myapp", "play", "2.0.0", "no", "Feilrettinger")

        result = svc.prepare_play_release_notes("myapp", app_version="2.0.0")
        assert "nb-NO" in result

    def test_empty_version_returns_empty(self):
        svc = _svc()
        _init_play(svc)

        result = svc.prepare_play_release_notes("myapp", app_version="9.9.9")
        assert result == {}

    def test_locale_filter(self):
        svc = _svc()
        _init_play(svc, locales=["en-US", "fr-FR"])
        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "English")
        svc.set_release_notes("myapp", "play", "2.0.0", "fr-FR", "French")

        result = svc.prepare_play_release_notes("myapp", app_version="2.0.0", locales=["fr-FR"])
        assert len(result) == 1
        assert "fr-FR" in result


# ======================================================================
# prepare_app_store_push_data
# ======================================================================


class TestPrepareAppStorePushData:
    def test_basic(self):
        svc = _svc()
        _init_app_store(svc)
        _populate_app_store(svc, data={
            "app_name": "My App",
            "description": "Full desc",
            "keywords": "app,tools",
        })

        result = svc.prepare_app_store_push_data("myapp")
        assert result["en-US"]["app_name"] == "My App"
        assert result["en-US"]["description"] == "Full desc"

    def test_filters_empty_values(self):
        svc = _svc()
        _init_app_store(svc)
        _populate_app_store(svc, data={"app_name": "My App", "subtitle": "", "description": ""})

        result = svc.prepare_app_store_push_data("myapp")
        assert result["en-US"] == {"app_name": "My App"}

    def test_locale_filter(self):
        svc = _svc()
        _init_app_store(svc, locales=["en-US", "ja"])
        _populate_app_store(svc, locale="en-US", data={"app_name": "English"})
        _populate_app_store(svc, locale="ja", data={"app_name": "Japanese"})

        result = svc.prepare_app_store_push_data("myapp", locales=["ja"])
        assert "ja" in result
        assert len(result) == 1

    def test_fully_empty_locale_skipped(self):
        svc = _svc()
        _init_app_store(svc)
        _populate_app_store(svc, data={"app_name": "", "subtitle": ""})

        result = svc.prepare_app_store_push_data("myapp")
        assert result == {}


# ======================================================================
# diff_objects utility
# ======================================================================


class TestDiffObjects:
    def test_identical(self):
        result = diff_objects({"a": 1}, {"a": 1})
        assert result == {"added": [], "removed": [], "changed": []}

    def test_added_key(self):
        result = diff_objects({"a": 1}, {"a": 1, "b": 2})
        assert result["added"] == ["b"]

    def test_removed_key(self):
        result = diff_objects({"a": 1, "b": 2}, {"a": 1})
        assert result["removed"] == ["b"]

    def test_changed_value(self):
        result = diff_objects({"a": 1}, {"a": 2})
        assert len(result["changed"]) == 1
        assert result["changed"][0]["before"] == 1
        assert result["changed"][0]["after"] == 2

    def test_nested_diff(self):
        left = {"a": {"b": 1, "c": 2}}
        right = {"a": {"b": 1, "c": 3}}
        result = diff_objects(left, right)
        assert len(result["changed"]) == 1
        assert result["changed"][0]["path"] == "a.c"

    def test_scalar_values(self):
        result = diff_objects("hello", "world")
        assert len(result["changed"]) == 1
        assert result["changed"][0]["before"] == "hello"
        assert result["changed"][0]["after"] == "world"

    def test_equal_scalars(self):
        result = diff_objects(42, 42)
        assert result == {"added": [], "removed": [], "changed": []}
