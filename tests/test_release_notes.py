"""Tests for the dedicated release notes system."""

from __future__ import annotations

import json

import pytest

from perfectdeckcli.service import ListingService
from perfectdeckcli import mcp_server
from perfectdeckcli.project_router import ProjectListingRouter
from perfectdeckcli.storage import InMemoryStorageBackend


# ======================================================================
# Helpers
# ======================================================================


def _svc() -> ListingService:
    return ListingService(InMemoryStorageBackend())


def _init(
    svc: ListingService,
    app: str = "myapp",
    store: str = "play",
    locales: list | None = None,
) -> None:
    svc.init_listing(app, stores=[store], locales=locales or ["en-US", "fr-FR"])


def _json(value: str) -> dict:
    return json.loads(value)


# ======================================================================
# TestReleaseNotesCRUD
# ======================================================================


class TestReleaseNotesCRUD:
    def test_set_and_get_single_locale(self):
        svc = _svc()
        _init(svc)

        svc.set_release_notes("myapp", "play", "2.1.0", "en-US", "Bug fixes")
        result = svc.get_release_notes("myapp", "play", "2.1.0", locale="en-US")
        assert result["text"] == "Bug fixes"
        assert result["locale"] == "en-US"
        assert result["app_version"] == "2.1.0"

    def test_set_and_get_all_locales(self):
        svc = _svc()
        _init(svc)

        svc.set_release_notes("myapp", "play", "2.1.0", "en-US", "Bug fixes")
        svc.set_release_notes("myapp", "play", "2.1.0", "fr-FR", "Corrections")
        result = svc.get_release_notes("myapp", "play", "2.1.0")
        assert result["notes"]["en-US"] == "Bug fixes"
        assert result["notes"]["fr-FR"] == "Corrections"

    def test_upsert_batch(self):
        svc = _svc()
        _init(svc)

        svc.upsert_release_notes("myapp", "play", "2.0.0", {
            "en-US": "Major redesign!",
            "fr-FR": "Refonte majeure!",
        })
        result = svc.get_release_notes("myapp", "play", "2.0.0")
        assert result["notes"]["en-US"] == "Major redesign!"
        assert result["notes"]["fr-FR"] == "Refonte majeure!"

    def test_upsert_merges(self):
        svc = _svc()
        _init(svc)

        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "First")
        svc.upsert_release_notes("myapp", "play", "2.0.0", {"fr-FR": "French"})

        result = svc.get_release_notes("myapp", "play", "2.0.0")
        assert result["notes"]["en-US"] == "First"
        assert result["notes"]["fr-FR"] == "French"

    def test_list_release_versions(self):
        svc = _svc()
        _init(svc)

        svc.set_release_notes("myapp", "play", "2.1.0", "en-US", "Notes")
        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "Old notes")
        svc.set_release_notes("myapp", "play", "1.0.0", "en-US", "Initial")

        versions = svc.list_release_versions("myapp", "play")
        assert versions == ["1.0.0", "2.0.0", "2.1.0"]

    def test_list_release_versions_empty(self):
        svc = _svc()
        _init(svc)

        versions = svc.list_release_versions("myapp", "play")
        assert versions == []

    def test_delete_release_notes(self):
        svc = _svc()
        _init(svc)

        svc.set_release_notes("myapp", "play", "2.1.0", "en-US", "Notes")
        result = svc.delete_release_notes("myapp", "play", "2.1.0")
        assert result["deleted"] is True

        versions = svc.list_release_versions("myapp", "play")
        assert "2.1.0" not in versions

    def test_delete_nonexistent_version(self):
        svc = _svc()
        _init(svc)

        result = svc.delete_release_notes("myapp", "play", "9.9.9")
        assert result["deleted"] is False

    def test_get_nonexistent_version_raises(self):
        svc = _svc()
        _init(svc)

        with pytest.raises(KeyError):
            svc.get_release_notes("myapp", "play", "9.9.9")

    def test_get_nonexistent_locale_raises(self):
        svc = _svc()
        _init(svc)

        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "Notes")
        with pytest.raises(KeyError):
            svc.get_release_notes("myapp", "play", "2.0.0", locale="ja")

    def test_persistence_to_yaml(self, tmp_path):
        from perfectdeckcli.storage import FileStorageBackend

        svc = ListingService(FileStorageBackend(tmp_path / "listings.yaml"))
        _init(svc)

        svc.set_release_notes("myapp", "play", "2.1.0", "en-US", "Persisted")

        # Create a new service instance pointing to same file
        svc2 = ListingService(FileStorageBackend(tmp_path / "listings.yaml"))
        result = svc2.get_release_notes("myapp", "play", "2.1.0", locale="en-US")
        assert result["text"] == "Persisted"

    def test_overwrite_existing_note(self):
        svc = _svc()
        _init(svc)

        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "Old text")
        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "New text")

        result = svc.get_release_notes("myapp", "play", "2.0.0", locale="en-US")
        assert result["text"] == "New text"

    def test_multiple_versions_independent(self):
        svc = _svc()
        _init(svc)

        svc.set_release_notes("myapp", "play", "1.0.0", "en-US", "V1")
        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "V2")

        r1 = svc.get_release_notes("myapp", "play", "1.0.0", locale="en-US")
        r2 = svc.get_release_notes("myapp", "play", "2.0.0", locale="en-US")
        assert r1["text"] == "V1"
        assert r2["text"] == "V2"


# ======================================================================
# TestReleaseNotesDoNotAffectVersioning
# ======================================================================


class TestReleaseNotesDoNotAffectVersioning:
    def test_set_does_not_bump_version(self):
        svc = _svc()
        _init(svc)

        status_before = svc.get_update_status("myapp", "play")
        ver_before = status_before["current_version"]

        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "Notes")

        status_after = svc.get_update_status("myapp", "play")
        assert status_after["current_version"] == ver_before

    def test_upsert_does_not_bump_version(self):
        svc = _svc()
        _init(svc)

        status_before = svc.get_update_status("myapp", "play")
        ver_before = status_before["current_version"]

        svc.upsert_release_notes("myapp", "play", "2.0.0", {"en-US": "Notes"})

        status_after = svc.get_update_status("myapp", "play")
        assert status_after["current_version"] == ver_before

    def test_delete_does_not_bump_version(self):
        svc = _svc()
        _init(svc)

        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "Notes")
        status_before = svc.get_update_status("myapp", "play")
        ver_before = status_before["current_version"]

        svc.delete_release_notes("myapp", "play", "2.0.0")

        status_after = svc.get_update_status("myapp", "play")
        assert status_after["current_version"] == ver_before

    def test_set_does_not_mark_locales_stale(self):
        svc = _svc()
        _init(svc, locales=["en-US", "fr-FR"])
        svc.set_baseline_locale("myapp", "play", "en-US")

        status_before = svc.get_update_status("myapp", "play")
        stale_before = status_before["stale_locales"]

        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "Notes")

        status_after = svc.get_update_status("myapp", "play")
        assert status_after["stale_locales"] == stale_before


# ======================================================================
# TestReleaseNotesValidation
# ======================================================================


class TestReleaseNotesValidation:
    def test_validate_no_versions_returns_ok(self):
        """validate_release_notes with no release notes at all returns ok=True."""
        svc = _svc()
        _init(svc)

        result = svc.validate_release_notes("myapp", "play")
        assert result["ok"] is True
        assert result["versions"] == {}

    def test_char_limit_and_missing_locales_combined(self):
        """Both char-limit errors and missing locales in the same version."""
        svc = _svc()
        _init(svc, locales=["en-US", "fr-FR"])

        # en-US over limit, fr-FR missing entirely
        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "X" * 501)
        result = svc.validate_release_notes("myapp", "play", "2.0.0")
        assert result["ok"] is False
        ver = result["versions"]["2.0.0"]
        assert ver["ok"] is False  # char limit error
        assert len(ver["errors"]) == 1
        assert "fr-FR" in ver["missing_locales"]

    def test_play_store_char_limit(self):
        svc = _svc()
        _init(svc)

        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "X" * 501)
        result = svc.validate_release_notes("myapp", "play", "2.0.0")
        assert result["ok"] is False
        errors = result["versions"]["2.0.0"]["errors"]
        assert len(errors) == 1
        assert errors[0]["limit"] == 500

    def test_play_store_within_limit(self):
        svc = _svc()
        _init(svc)

        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "X" * 500)
        svc.set_release_notes("myapp", "play", "2.0.0", "fr-FR", "Y" * 500)
        result = svc.validate_release_notes("myapp", "play", "2.0.0")
        assert result["versions"]["2.0.0"]["ok"] is True

    def test_app_store_char_limit(self):
        svc = _svc()
        _init(svc, store="app_store")

        svc.set_release_notes("myapp", "app_store", "2.0.0", "en-US", "X" * 4001)
        result = svc.validate_release_notes("myapp", "app_store", "2.0.0")
        assert result["ok"] is False
        errors = result["versions"]["2.0.0"]["errors"]
        assert errors[0]["limit"] == 4000

    def test_app_store_within_limit(self):
        svc = _svc()
        _init(svc, store="app_store")

        svc.set_release_notes("myapp", "app_store", "2.0.0", "en-US", "X" * 4000)
        svc.set_release_notes("myapp", "app_store", "2.0.0", "fr-FR", "Y" * 4000)
        result = svc.validate_release_notes("myapp", "app_store", "2.0.0")
        assert result["versions"]["2.0.0"]["ok"] is True

    def test_missing_locales_detected(self):
        svc = _svc()
        _init(svc, locales=["en-US", "fr-FR"])

        # Only set en-US, fr-FR is missing
        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "Bug fixes")
        result = svc.validate_release_notes("myapp", "play", "2.0.0")
        assert "fr-FR" in result["versions"]["2.0.0"]["missing_locales"]

    def test_extra_locales_detected(self):
        svc = _svc()
        _init(svc, locales=["en-US"])

        # Set note for locale not in listing
        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "Bug fixes")
        svc.set_release_notes("myapp", "play", "2.0.0", "ja", "Japanese notes")
        result = svc.validate_release_notes("myapp", "play", "2.0.0")
        assert "ja" in result["versions"]["2.0.0"]["extra_locales"]

    def test_validate_all_versions(self):
        svc = _svc()
        _init(svc)

        svc.set_release_notes("myapp", "play", "1.0.0", "en-US", "V1")
        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "V2")

        result = svc.validate_release_notes("myapp", "play")
        assert "1.0.0" in result["versions"]
        assert "2.0.0" in result["versions"]

    def test_validate_single_version(self):
        svc = _svc()
        _init(svc)

        svc.set_release_notes("myapp", "play", "1.0.0", "en-US", "V1")
        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "V2")

        result = svc.validate_release_notes("myapp", "play", "1.0.0")
        assert "1.0.0" in result["versions"]
        assert "2.0.0" not in result["versions"]

    def test_validate_nonexistent_version_raises(self):
        svc = _svc()
        _init(svc)

        with pytest.raises(KeyError):
            svc.validate_release_notes("myapp", "play", "9.9.9")

    def test_validate_clean_pass(self):
        svc = _svc()
        _init(svc, locales=["en-US", "fr-FR"])

        svc.upsert_release_notes("myapp", "play", "2.0.0", {
            "en-US": "Bug fixes",
            "fr-FR": "Corrections de bugs",
        })
        result = svc.validate_release_notes("myapp", "play", "2.0.0")
        assert result["ok"] is True
        ver = result["versions"]["2.0.0"]
        assert ver["ok"] is True
        assert ver["errors"] == []
        assert ver["missing_locales"] == []
        assert ver["extra_locales"] == []

    def test_ok_false_when_missing_locales(self):
        """Even without char limit errors, missing locales make overall ok=False."""
        svc = _svc()
        _init(svc, locales=["en-US", "fr-FR"])

        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "Notes")
        result = svc.validate_release_notes("myapp", "play")
        assert result["ok"] is False


# ======================================================================
# TestReleaseNotesPushIntegration
# ======================================================================


class TestReleaseNotesPushIntegration:
    def test_prepare_app_store_push_data_missing_version_graceful(self):
        """app_version that doesn't exist should just not inject whats_new."""
        svc = _svc()
        _init(svc, store="app_store")
        svc.upsert_locale("myapp", "app_store", "en-US", {"app_name": "My App"})

        result = svc.prepare_app_store_push_data("myapp", app_version="9.9.9")
        assert "en-US" in result
        assert "whats_new" not in result["en-US"]

    def test_prepare_app_store_whats_new_only_locale_with_notes(self):
        """Locale with release notes but no listing data still appears via whats_new."""
        svc = _svc()
        _init(svc, store="app_store", locales=["en-US", "fr-FR"])
        # en-US has listing data + notes, fr-FR has only notes (empty listing)
        svc.upsert_locale("myapp", "app_store", "en-US", {"app_name": "My App"})
        svc.set_release_notes("myapp", "app_store", "2.0.0", "en-US", "English notes")
        svc.set_release_notes("myapp", "app_store", "2.0.0", "fr-FR", "French notes")

        result = svc.prepare_app_store_push_data("myapp", app_version="2.0.0")
        assert result["en-US"]["whats_new"] == "English notes"
        # fr-FR has empty listing data but gets whats_new injected
        assert result["fr-FR"]["whats_new"] == "French notes"

    def test_prepare_play_release_notes_with_version(self):
        svc = _svc()
        _init(svc)

        svc.set_release_notes("myapp", "play", "2.1.0", "en-US", "Bug fixes")
        svc.set_release_notes("myapp", "play", "2.1.0", "fr-FR", "Corrections")

        result = svc.prepare_play_release_notes("myapp", app_version="2.1.0")
        assert result["en-US"] == "Bug fixes"
        assert result["fr-FR"] == "Corrections"

    def test_prepare_play_release_notes_locale_filter(self):
        svc = _svc()
        _init(svc)

        svc.set_release_notes("myapp", "play", "2.1.0", "en-US", "Bug fixes")
        svc.set_release_notes("myapp", "play", "2.1.0", "fr-FR", "Corrections")

        result = svc.prepare_play_release_notes(
            "myapp", app_version="2.1.0", locales=["en-US"],
        )
        assert "en-US" in result
        assert "fr-FR" not in result

    def test_prepare_play_release_notes_missing_version(self):
        svc = _svc()
        _init(svc)

        result = svc.prepare_play_release_notes("myapp", app_version="9.9.9")
        assert result == {}

    def test_prepare_play_release_notes_locale_mapping(self):
        svc = _svc()
        _init(svc, locales=["zh-Hans"])

        svc.set_release_notes("myapp", "play", "2.0.0", "zh-Hans", "Chinese notes")
        result = svc.prepare_play_release_notes("myapp", app_version="2.0.0")
        assert "zh-CN" in result
        assert result["zh-CN"] == "Chinese notes"

    def test_prepare_app_store_push_data_with_version(self):
        svc = _svc()
        _init(svc, store="app_store")
        svc.upsert_locale("myapp", "app_store", "en-US", {
            "app_name": "My App",
            "description": "Great app",
        })
        svc.set_release_notes("myapp", "app_store", "2.0.0", "en-US", "What's new text")

        result = svc.prepare_app_store_push_data("myapp", app_version="2.0.0")
        assert result["en-US"]["whats_new"] == "What's new text"
        assert result["en-US"]["app_name"] == "My App"

    def test_prepare_app_store_push_data_without_version(self):
        svc = _svc()
        _init(svc, store="app_store")
        svc.upsert_locale("myapp", "app_store", "en-US", {
            "app_name": "My App",
            "description": "Great app",
        })
        svc.set_release_notes("myapp", "app_store", "2.0.0", "en-US", "What's new text")

        result = svc.prepare_app_store_push_data("myapp")
        # Without app_version, whats_new should not be included
        assert "whats_new" not in result["en-US"]

    def test_prepare_app_store_push_data_locale_filter(self):
        svc = _svc()
        _init(svc, store="app_store")
        svc.upsert_locale("myapp", "app_store", "en-US", {"app_name": "English"})
        svc.upsert_locale("myapp", "app_store", "fr-FR", {"app_name": "French"})
        svc.set_release_notes("myapp", "app_store", "2.0.0", "en-US", "English notes")
        svc.set_release_notes("myapp", "app_store", "2.0.0", "fr-FR", "French notes")

        result = svc.prepare_app_store_push_data(
            "myapp", locales=["en-US"], app_version="2.0.0",
        )
        assert "en-US" in result
        assert "fr-FR" not in result
        assert result["en-US"]["whats_new"] == "English notes"


# ======================================================================
# TestMcpReleaseNotesTools
# ======================================================================


class TestMcpReleaseNotesTools:
    def _setup(self, tmp_path):
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mcp_server.perfectdeck_init_listing(
            mcp_server.InitListingInput(
                project_path="proj",
                app="myapp",
                stores=["play"],
                locales=["en-US", "fr-FR"],
            )
        )

    def test_set_and_get(self, tmp_path):
        self._setup(tmp_path)

        out = _json(mcp_server.perfectdeck_set_release_notes(
            mcp_server.SetReleaseNotesInput(
                project_path="proj", app="myapp", store="play",
                app_version="2.0.0", locale="en-US", text="Bug fixes",
            )
        ))
        assert out["ok"] is True

        out = _json(mcp_server.perfectdeck_get_release_notes(
            mcp_server.GetReleaseNotesInput(
                project_path="proj", app="myapp", store="play",
                app_version="2.0.0", locale="en-US",
            )
        ))
        assert out["ok"] is True
        assert out["text"] == "Bug fixes"

    def test_upsert(self, tmp_path):
        self._setup(tmp_path)

        out = _json(mcp_server.perfectdeck_upsert_release_notes(
            mcp_server.UpsertReleaseNotesInput(
                project_path="proj", app="myapp", store="play",
                app_version="2.0.0",
                data={"en-US": "English notes", "fr-FR": "French notes"},
            )
        ))
        assert out["ok"] is True

        out = _json(mcp_server.perfectdeck_get_release_notes(
            mcp_server.GetReleaseNotesInput(
                project_path="proj", app="myapp", store="play",
                app_version="2.0.0",
            )
        ))
        assert out["notes"]["en-US"] == "English notes"
        assert out["notes"]["fr-FR"] == "French notes"

    def test_list_versions(self, tmp_path):
        self._setup(tmp_path)

        mcp_server.perfectdeck_set_release_notes(
            mcp_server.SetReleaseNotesInput(
                project_path="proj", app="myapp", store="play",
                app_version="1.0.0", locale="en-US", text="V1",
            )
        )
        mcp_server.perfectdeck_set_release_notes(
            mcp_server.SetReleaseNotesInput(
                project_path="proj", app="myapp", store="play",
                app_version="2.0.0", locale="en-US", text="V2",
            )
        )

        out = _json(mcp_server.perfectdeck_list_release_versions(
            mcp_server.ListReleaseVersionsInput(
                project_path="proj", app="myapp", store="play",
            )
        ))
        assert out["ok"] is True
        assert out["versions"] == ["1.0.0", "2.0.0"]

    def test_delete(self, tmp_path):
        self._setup(tmp_path)

        mcp_server.perfectdeck_set_release_notes(
            mcp_server.SetReleaseNotesInput(
                project_path="proj", app="myapp", store="play",
                app_version="2.0.0", locale="en-US", text="Notes",
            )
        )

        out = _json(mcp_server.perfectdeck_delete_release_notes(
            mcp_server.DeleteReleaseNotesInput(
                project_path="proj", app="myapp", store="play",
                app_version="2.0.0",
            )
        ))
        assert out["ok"] is True
        assert out["deleted"] is True

        # Verify deleted
        versions = _json(mcp_server.perfectdeck_list_release_versions(
            mcp_server.ListReleaseVersionsInput(
                project_path="proj", app="myapp", store="play",
            )
        ))
        assert "2.0.0" not in versions["versions"]

    def test_validate(self, tmp_path):
        self._setup(tmp_path)

        # Set only en-US → fr-FR missing
        mcp_server.perfectdeck_set_release_notes(
            mcp_server.SetReleaseNotesInput(
                project_path="proj", app="myapp", store="play",
                app_version="2.0.0", locale="en-US", text="Bug fixes",
            )
        )

        out = _json(mcp_server.perfectdeck_validate_release_notes(
            mcp_server.ValidateReleaseNotesInput(
                project_path="proj", app="myapp", store="play",
                app_version="2.0.0",
            )
        ))
        assert out["ok"] is False
        assert "fr-FR" in out["versions"]["2.0.0"]["missing_locales"]

    def test_validate_all(self, tmp_path):
        self._setup(tmp_path)

        mcp_server.perfectdeck_upsert_release_notes(
            mcp_server.UpsertReleaseNotesInput(
                project_path="proj", app="myapp", store="play",
                app_version="1.0.0",
                data={"en-US": "V1", "fr-FR": "V1 FR"},
            )
        )
        mcp_server.perfectdeck_upsert_release_notes(
            mcp_server.UpsertReleaseNotesInput(
                project_path="proj", app="myapp", store="play",
                app_version="2.0.0",
                data={"en-US": "V2", "fr-FR": "V2 FR"},
            )
        )

        out = _json(mcp_server.perfectdeck_validate_release_notes(
            mcp_server.ValidateReleaseNotesInput(
                project_path="proj", app="myapp", store="play",
            )
        ))
        assert out["ok"] is True
        assert "1.0.0" in out["versions"]
        assert "2.0.0" in out["versions"]


# ======================================================================
# TestMcpPushWithReleaseNotesVersion
# ======================================================================


class TestMcpPushWithReleaseNotesVersion:
    def test_push_play_listing_input_has_release_notes_version(self):
        """PushPlayListingInput should accept release_notes_version."""
        params = mcp_server.PushPlayListingInput(
            app="myapp",
            package_name="com.example.app",
            release_notes_version="2.0.0",
        )
        assert params.release_notes_version == "2.0.0"

    def test_push_play_listing_input_no_include_release_notes(self):
        """include_release_notes field should no longer exist."""
        assert not hasattr(mcp_server.PushPlayListingInput.model_fields, "include_release_notes")

    def test_push_play_release_notes_input_has_version(self):
        params = mcp_server.PushPlayReleaseNotesInput(
            app="myapp",
            package_name="com.example.app",
            version_code=42,
            release_notes_version="2.0.0",
        )
        assert params.release_notes_version == "2.0.0"

    def test_publish_play_bundle_input_has_version(self):
        params = mcp_server.PublishPlayBundleInput(
            app="myapp",
            package_name="com.example.app",
            bundle_path="/path/to/app.aab",
            release_notes_version="2.0.0",
        )
        assert params.release_notes_version == "2.0.0"

    def test_push_app_store_listing_input_has_version(self):
        params = mcp_server.PushAppStoreListingInput(
            app="myapp",
            app_id="123",
            key_id="KEY",
            issuer_id="ISS",
            private_key_path="/path/to/key.p8",
            version_string="2.0.0",
            release_notes_version="2.0.0",
        )
        assert params.release_notes_version == "2.0.0"


# ======================================================================
# TestReleaseNotesNotInSnapshots
# ======================================================================


class TestReleaseNotesNotInSnapshots:
    def test_snapshot_does_not_contain_release_notes(self):
        svc = _svc()
        _init(svc)

        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "Notes")
        svc.save_snapshot("myapp", "play", reason="test")

        snapshots = svc.list_snapshots("myapp", "play")
        assert len(snapshots) >= 1

        # Load the snapshot and verify release_notes is NOT in it
        latest = svc.storage.load_snapshot("myapp", "play", snapshots[-1]["version"])
        assert "release_notes" not in latest

    def test_restore_snapshot_preserves_release_notes(self):
        """Restoring a snapshot must not wipe release notes."""
        svc = _svc()
        _init(svc)
        svc.upsert_locale("myapp", "play", "en-US", {"title": "Original"})
        svc.save_snapshot("myapp", "play", reason="before-edit")

        # Mutate listing and add release notes
        svc.set_element("myapp", "play", "title", "Changed", locale="en-US")
        svc.set_release_notes("myapp", "play", "3.0.0", "en-US", "New release")

        # Restore the snapshot — listing should revert, release notes should stay
        svc.restore_snapshot("myapp", "play")

        section = svc.list_section("myapp", "play", locale="en-US")
        assert section["title"] == "Original"

        rn = svc.get_release_notes("myapp", "play", "3.0.0", locale="en-US")
        assert rn["text"] == "New release"


# ======================================================================
# TestReleaseNotesCrossStore
# ======================================================================


class TestReleaseNotesCrossStore:
    def test_play_and_app_store_independent(self):
        """Release notes for play and app_store on the same app are independent."""
        svc = _svc()
        svc.init_listing("myapp", stores=["play", "app_store"], locales=["en-US"])

        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "Play notes")
        svc.set_release_notes("myapp", "app_store", "2.0.0", "en-US", "App Store notes")

        play_rn = svc.get_release_notes("myapp", "play", "2.0.0", locale="en-US")
        as_rn = svc.get_release_notes("myapp", "app_store", "2.0.0", locale="en-US")
        assert play_rn["text"] == "Play notes"
        assert as_rn["text"] == "App Store notes"

    def test_delete_play_does_not_affect_app_store(self):
        svc = _svc()
        svc.init_listing("myapp", stores=["play", "app_store"], locales=["en-US"])

        svc.set_release_notes("myapp", "play", "2.0.0", "en-US", "Play")
        svc.set_release_notes("myapp", "app_store", "2.0.0", "en-US", "AppStore")

        svc.delete_release_notes("myapp", "play", "2.0.0")

        # play gone
        with pytest.raises(KeyError):
            svc.get_release_notes("myapp", "play", "2.0.0")
        # app_store untouched
        rn = svc.get_release_notes("myapp", "app_store", "2.0.0", locale="en-US")
        assert rn["text"] == "AppStore"


# ======================================================================
# TestInitIncludesReleaseNotes
# ======================================================================


class TestInitIncludesReleaseNotes:
    def test_init_creates_empty_release_notes(self):
        svc = _svc()
        _init(svc)

        doc = svc.storage.load()
        section = doc["apps"]["myapp"]["play"]
        assert "release_notes" in section
        assert section["release_notes"] == {}


# ======================================================================
# TestMcpPushReleaseNotesWithoutVersion
# ======================================================================


class TestMcpPushReleaseNotesWithoutVersion:
    def test_push_play_release_notes_without_version_returns_error(self, tmp_path):
        """push_play_release_notes should fail gracefully when no version provided."""
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mcp_server.perfectdeck_init_listing(
            mcp_server.InitListingInput(
                project_path="proj", app="myapp",
                stores=["play"], locales=["en-US"],
            )
        )

        out = _json(mcp_server.perfectdeck_push_play_release_notes(
            mcp_server.PushPlayReleaseNotesInput(
                project_path="proj", app="myapp",
                package_name="com.example.app",
                version_code=42,
                # release_notes_version intentionally omitted (None)
            )
        ))
        assert out["ok"] is False
        assert "release_notes_version" in out["error"]


# ======================================================================
# TestMcpInputValidation
# ======================================================================


class TestMcpReleaseNotesInputValidation:
    def test_set_rejects_empty_app_version(self):
        with pytest.raises(Exception):
            mcp_server.SetReleaseNotesInput(
                project_path="proj", app="myapp", store="play",
                app_version="", locale="en-US", text="Notes",
            )

    def test_set_rejects_empty_locale(self):
        with pytest.raises(Exception):
            mcp_server.SetReleaseNotesInput(
                project_path="proj", app="myapp", store="play",
                app_version="2.0.0", locale="", text="Notes",
            )

    def test_delete_rejects_empty_app_version(self):
        with pytest.raises(Exception):
            mcp_server.DeleteReleaseNotesInput(
                project_path="proj", app="myapp", store="play",
                app_version="",
            )

    def test_set_rejects_extra_fields(self):
        with pytest.raises(Exception):
            mcp_server.SetReleaseNotesInput(
                project_path="proj", app="myapp", store="play",
                app_version="2.0.0", locale="en-US", text="Notes",
                bogus="bad",
            )
