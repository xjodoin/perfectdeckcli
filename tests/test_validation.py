"""Extensive tests for the validation module."""

from __future__ import annotations

import pytest

from perfectdeckcli.validation import (
    APP_STORE_LIMITS,
    PLAY_STORE_LIMITS,
    validate_app_store_listing,
    validate_listing,
    validate_play_listing,
)


# ======================================================================
# Play Store validation
# ======================================================================


class TestPlayStoreValidation:
    def test_valid_listing_passes(self):
        result = validate_play_listing({
            "en-US": {"title": "My App", "short_description": "Short", "full_description": "Full"},
        })
        assert result["ok"] is True
        assert result["errors"] == []

    def test_empty_locales_passes(self):
        result = validate_play_listing({})
        assert result["ok"] is True

    def test_empty_fields_passes(self):
        result = validate_play_listing({"en-US": {}})
        assert result["ok"] is True

    def test_title_at_exact_limit(self):
        result = validate_play_listing({"en-US": {"title": "A" * 30}})
        assert result["ok"] is True

    def test_title_one_over_limit(self):
        result = validate_play_listing({"en-US": {"title": "A" * 31}})
        assert result["ok"] is False
        assert len(result["errors"]) == 1
        err = result["errors"][0]
        assert err["locale"] == "en-US"
        assert err["field"] == "title"
        assert err["length"] == 31
        assert err["limit"] == 30
        assert err["over_by"] == 1

    def test_short_description_at_limit(self):
        result = validate_play_listing({"en-US": {"short_description": "X" * 80}})
        assert result["ok"] is True

    def test_short_description_over_limit(self):
        result = validate_play_listing({"en-US": {"short_description": "X" * 81}})
        assert result["ok"] is False
        assert result["errors"][0]["field"] == "short_description"

    def test_full_description_at_limit(self):
        result = validate_play_listing({"en-US": {"full_description": "D" * 4000}})
        assert result["ok"] is True

    def test_full_description_over_limit(self):
        result = validate_play_listing({"en-US": {"full_description": "D" * 4001}})
        assert result["ok"] is False
        assert result["errors"][0]["field"] == "full_description"

    def test_whats_new_not_validated_here(self):
        # whats_new is now validated via validate_release_notes, not listing validation
        result = validate_play_listing({"en-US": {"whats_new": "N" * 999}})
        assert result["ok"] is True

    def test_multiple_errors_same_locale(self):
        result = validate_play_listing({
            "en-US": {"title": "T" * 50, "short_description": "S" * 100},
        })
        assert result["ok"] is False
        assert len(result["errors"]) == 2
        fields = {e["field"] for e in result["errors"]}
        assert fields == {"title", "short_description"}

    def test_multiple_locales_multiple_errors(self):
        result = validate_play_listing({
            "en-US": {"title": "T" * 31},
            "fr-FR": {"title": "T" * 31},
            "ja": {"title": "OK"},
        })
        assert result["ok"] is False
        assert len(result["errors"]) == 2
        locales = {e["locale"] for e in result["errors"]}
        assert locales == {"en-US", "fr-FR"}

    def test_none_value_is_skipped(self):
        result = validate_play_listing({"en-US": {"title": None}})
        assert result["ok"] is True
        assert result["errors"] == []

    def test_non_dict_locale_is_skipped(self):
        result = validate_play_listing({"en-US": "not a dict"})
        assert result["ok"] is True

    def test_extra_fields_parameter(self):
        result = validate_play_listing(
            {"en-US": {"custom_field": "X" * 11}},
            extra_fields={"custom_field": 10},
        )
        assert result["ok"] is False
        assert result["errors"][0]["field"] == "custom_field"

    def test_unicode_characters_counted_by_len(self):
        # Unicode chars count as 1 each
        result = validate_play_listing({"ja": {"title": "日" * 30}})
        assert result["ok"] is True
        result = validate_play_listing({"ja": {"title": "日" * 31}})
        assert result["ok"] is False


# ======================================================================
# App Store validation
# ======================================================================


class TestAppStoreValidation:
    def test_valid_listing(self):
        result = validate_app_store_listing({
            "en-US": {
                "app_name": "My App",
                "subtitle": "Best app ever",
                "description": "A great app",
                "keywords": "app,great",
            },
        })
        assert result["ok"] is True

    def test_app_name_over_limit(self):
        result = validate_app_store_listing({"en-US": {"app_name": "A" * 31}})
        assert result["ok"] is False
        assert result["errors"][0]["field"] == "app_name"
        assert result["errors"][0]["limit"] == 30

    def test_subtitle_over_limit(self):
        result = validate_app_store_listing({"en-US": {"subtitle": "S" * 31}})
        assert result["ok"] is False
        assert result["errors"][0]["field"] == "subtitle"

    def test_promotional_text_at_limit(self):
        result = validate_app_store_listing({"en-US": {"promotional_text": "P" * 170}})
        assert result["ok"] is True

    def test_promotional_text_over_limit(self):
        result = validate_app_store_listing({"en-US": {"promotional_text": "P" * 171}})
        assert result["ok"] is False
        assert result["errors"][0]["field"] == "promotional_text"

    def test_description_over_limit(self):
        result = validate_app_store_listing({"en-US": {"description": "D" * 4001}})
        assert result["ok"] is False

    def test_keywords_at_limit(self):
        result = validate_app_store_listing({"en-US": {"keywords": "K" * 100}})
        assert result["ok"] is True

    def test_keywords_over_limit(self):
        result = validate_app_store_listing({"en-US": {"keywords": "K" * 101}})
        assert result["ok"] is False
        assert result["errors"][0]["field"] == "keywords"

    def test_whats_new_not_validated_here(self):
        # whats_new is now validated via validate_release_notes, not listing validation
        result = validate_app_store_listing({"en-US": {"whats_new": "W" * 9999}})
        assert result["ok"] is True

    def test_all_fields_over_limit(self):
        result = validate_app_store_listing({
            "en-US": {
                "app_name": "A" * 50,
                "subtitle": "S" * 50,
                "promotional_text": "P" * 200,
                "description": "D" * 5000,
                "keywords": "K" * 200,
            },
        })
        assert result["ok"] is False
        assert len(result["errors"]) == 5


# ======================================================================
# validate_listing() dispatch
# ======================================================================


class TestValidateListingDispatch:
    def test_play_store_dispatch(self):
        result = validate_listing("play", {"en-US": {"title": "T" * 31}})
        assert result["ok"] is False

    def test_app_store_dispatch(self):
        result = validate_listing("app_store", {"en-US": {"app_name": "A" * 31}})
        assert result["ok"] is False

    def test_unknown_store_raises(self):
        with pytest.raises(ValueError, match="Unknown store"):
            validate_listing("unknown_store", {})


# ======================================================================
# Verify limits match expected values
# ======================================================================


class TestLimitConstants:
    def test_play_store_limits(self):
        assert PLAY_STORE_LIMITS["title"] == 30
        assert PLAY_STORE_LIMITS["short_description"] == 80
        assert PLAY_STORE_LIMITS["full_description"] == 4000
        assert "whats_new" not in PLAY_STORE_LIMITS

    def test_app_store_limits(self):
        assert APP_STORE_LIMITS["app_name"] == 30
        assert APP_STORE_LIMITS["subtitle"] == 30
        assert APP_STORE_LIMITS["promotional_text"] == 170
        assert APP_STORE_LIMITS["description"] == 4000
        assert APP_STORE_LIMITS["keywords"] == 100
        assert "whats_new" not in APP_STORE_LIMITS
