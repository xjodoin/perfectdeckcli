"""Tests for Play Store locale mapping."""

from __future__ import annotations

from perfectdeckcli.play_store import PLAY_LOCALE_MAP, map_locale


class TestMapLocale:
    def test_direct_match(self):
        assert map_locale("en-US") == "en-US"
        assert map_locale("fr-FR") == "fr-FR"
        assert map_locale("de-DE") == "de-DE"

    def test_chinese_simplified(self):
        assert map_locale("zh-Hans") == "zh-CN"
        assert map_locale("zh-CN") == "zh-CN"

    def test_chinese_traditional(self):
        assert map_locale("zh-Hant") == "zh-TW"
        assert map_locale("zh-TW") == "zh-TW"

    def test_norwegian_variants(self):
        assert map_locale("no") == "nb-NO"
        assert map_locale("no-NO") == "nb-NO"
        assert map_locale("nb") == "nb-NO"
        assert map_locale("nb-NO") == "nb-NO"

    def test_spanish_latin_america(self):
        assert map_locale("es-419") == "es-419"
        assert map_locale("es-MX") == "es-419"

    def test_arabic_variants(self):
        assert map_locale("ar") == "ar"
        assert map_locale("ar-SA") == "ar"

    def test_czech(self):
        assert map_locale("cs") == "cs-CZ"

    def test_danish(self):
        assert map_locale("da") == "da-DK"

    def test_filipino(self):
        assert map_locale("fil") == "fil"
        assert map_locale("fil-PH") == "fil"

    def test_hindi(self):
        assert map_locale("hi") == "hi-IN"
        assert map_locale("hi-IN") == "hi-IN"

    def test_thai_variants(self):
        assert map_locale("th") == "th"
        assert map_locale("th-TH") == "th"

    def test_vietnamese_variants(self):
        assert map_locale("vi") == "vi"
        assert map_locale("vi-VN") == "vi"

    def test_romanian(self):
        assert map_locale("ro") == "ro"

    def test_indonesian_variants(self):
        assert map_locale("id") == "id"
        assert map_locale("id-ID") == "id"

    def test_fallback_hyphenated_unknown(self):
        # Unknown locale with hyphen: lowercase language, uppercase region
        assert map_locale("xx-yy") == "xx-YY"
        assert map_locale("abc-def") == "abc-DEF"

    def test_fallback_no_hyphen(self):
        # Unknown locale without hyphen: passthrough
        assert map_locale("zz") == "zz"
        assert map_locale("unknown") == "unknown"

    def test_all_map_entries_are_consistent(self):
        for key, value in PLAY_LOCALE_MAP.items():
            assert isinstance(key, str)
            assert isinstance(value, str)
            assert len(value) > 0
