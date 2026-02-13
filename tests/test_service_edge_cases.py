from __future__ import annotations

import pytest

from perfectdeckcli.service import ListingService
from perfectdeckcli.storage import InMemoryStorageBackend


def test_get_missing_key_raises_key_error() -> None:
    service = ListingService(InMemoryStorageBackend())
    service.init_listing(app="prod", locales=["en-US"])
    with pytest.raises(KeyError):
        service.get_element(app="prod", store="play", key_path="missing", locale="en-US")


def test_delete_missing_key_returns_false() -> None:
    service = ListingService(InMemoryStorageBackend())
    service.init_listing(app="prod", locales=["en-US"])
    out = service.delete_element(app="prod", store="play", key_path="missing", locale="en-US")
    assert out == {"ok": True, "deleted": False}


def test_set_nested_conflict_raises_value_error() -> None:
    service = ListingService(InMemoryStorageBackend())
    service.set_element(app="prod", store="play", key_path="metadata", value="not-an-object")
    with pytest.raises(ValueError):
        service.set_element(app="prod", store="play", key_path="metadata.title", value="new")


def test_init_overwrite_resets_store_section() -> None:
    service = ListingService(InMemoryStorageBackend())
    service.set_element(app="prod", store="play", key_path="title", value="Old", locale="en-US")
    service.init_listing(app="prod", stores=["play"], overwrite=True)
    payload = service.list_section(app="prod", store="play")
    assert payload == {"global": {}, "locales": {}}


def test_add_language_copy_from_missing_source_raises() -> None:
    service = ListingService(InMemoryStorageBackend())
    service.init_listing(app="prod", stores=["play"], locales=["en-US"])
    with pytest.raises(KeyError):
        service.add_language(
            app="prod",
            store="play",
            locale="fr-FR",
            copy_from_locale="es-ES",
        )


def test_list_apps_and_stores_empty_states() -> None:
    service = ListingService(InMemoryStorageBackend())
    assert service.list_apps() == []
    assert service.list_stores("prod") == []
