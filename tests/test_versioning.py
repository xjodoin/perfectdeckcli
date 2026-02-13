from __future__ import annotations

from perfectdeckcli.service import ListingService
from perfectdeckcli.storage import InMemoryStorageBackend


def test_versioning_stale_languages_after_baseline_change() -> None:
    service = ListingService(InMemoryStorageBackend())
    service.init_listing(
        app="prod",
        stores=["play"],
        locales=["en-US", "fr-FR", "es-ES"],
        baseline_locale="en-US",
    )

    # Baseline edit should bump listing version and make other locales stale.
    service.set_element(
        app="prod",
        store="play",
        locale="en-US",
        key_path="title",
        value="New baseline title",
    )
    status = service.get_update_status(app="prod", store="play")
    assert status["current_version"] > 1
    assert status["baseline_locale"] == "en-US"
    assert "fr-FR" in status["stale_locales"]
    assert "es-ES" in status["stale_locales"]
    assert "en-US" in status["up_to_date_locales"]

    service.mark_language_updated(app="prod", store="play", locale="fr-FR")
    status_after_fr = service.get_update_status(app="prod", store="play")
    assert "fr-FR" in status_after_fr["up_to_date_locales"]
    assert "es-ES" in status_after_fr["stale_locales"]


def test_manual_bump_version_records_changelog() -> None:
    service = ListingService(InMemoryStorageBackend())
    service.init_listing(app="prod", stores=["app_store"], locales=["en-US"], baseline_locale="en-US")
    out = service.bump_version(
        app="prod",
        store="app_store",
        reason="new feature requires translations",
        source_locale="en-US",
    )
    assert out["ok"] is True

    status = service.get_update_status(app="prod", store="app_store")
    assert status["current_version"] == out["current_version"]
    assert any(item["reason"] == "new feature requires translations" for item in status["changelog"])
