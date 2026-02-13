from __future__ import annotations

import pytest

from perfectdeckcli.service import ListingService
from perfectdeckcli.storage import InMemoryStorageBackend


def test_init_from_existing_section_copies_subset_locales() -> None:
    source = ListingService(InMemoryStorageBackend())
    target = ListingService(InMemoryStorageBackend())

    source.init_listing(
        app="source-app",
        stores=["play"],
        locales=["en-US", "fr-FR", "es-ES"],
        baseline_locale="en-US",
    )
    source.set_element("source-app", "play", "title", "Source EN", locale="en-US")
    source.set_element("source-app", "play", "title", "Source FR", locale="fr-FR")
    source.set_element("source-app", "play", "global_field", "global-value")

    out = target.init_from_existing_section(
        target_app="target-app",
        target_store="app_store",
        source_section=source.list_section("source-app", "play"),
        locales=["en-US", "fr-FR"],
        baseline_locale="fr-FR",
        overwrite=False,
    )
    assert out["ok"] is True
    payload = target.list_section("target-app", "app_store")
    assert sorted(payload["locales"].keys()) == ["en-US", "fr-FR"]
    assert payload["global"]["global_field"] == "global-value"
    status = target.get_update_status("target-app", "app_store")
    assert status["current_version"] == 1
    assert status["baseline_locale"] == "fr-FR"


def test_init_from_existing_requires_overwrite_when_target_has_data() -> None:
    source = ListingService(InMemoryStorageBackend())
    target = ListingService(InMemoryStorageBackend())
    source.init_listing(app="a", stores=["play"], locales=["en-US"], baseline_locale="en-US")
    target.init_listing(app="b", stores=["app_store"], locales=["en-US"], baseline_locale="en-US")
    source_section = source.list_section("a", "play")

    with pytest.raises(ValueError):
        target.init_from_existing_section(
            target_app="b",
            target_store="app_store",
            source_section=source_section,
            overwrite=False,
        )
