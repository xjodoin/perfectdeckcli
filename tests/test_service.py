from __future__ import annotations

from pathlib import Path

import yaml

from perfectdeckcli.service import ListingService
from perfectdeckcli.storage import FileStorageBackend, InMemoryStorageBackend


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_set_get_delete_global() -> None:
    service = ListingService(InMemoryStorageBackend())

    service.set_element(
        app="prod",
        store="play",
        key_path="metadata.title",
        value="AI Plant Doctor",
    )
    value = service.get_element(
        app="prod",
        store="play",
        key_path="metadata.title",
    )
    assert value == "AI Plant Doctor"

    result = service.delete_element(
        app="prod",
        store="play",
        key_path="metadata.title",
    )
    assert result["deleted"] is True

    data = service.storage.load()
    assert "title" not in data["apps"]["prod"]["play"]["global"]["metadata"]


def test_set_get_delete_global_file_persistence(tmp_path: Path) -> None:
    listing_file = tmp_path / "listings.yaml"
    service = ListingService(FileStorageBackend(listing_file))

    service.set_element(
        app="prod",
        store="play",
        key_path="metadata.title",
        value="AI Plant Doctor",
    )
    result = service.delete_element(
        app="prod",
        store="play",
        key_path="metadata.title",
    )
    assert result["deleted"] is True

    data = _read_yaml(listing_file)
    assert "title" not in data["apps"]["prod"]["play"]["global"]["metadata"]


def test_upsert_locale_merge_and_replace() -> None:
    service = ListingService(InMemoryStorageBackend())

    service.upsert_locale(
        app="prod",
        store="app_store",
        locale="en-US",
        data={"title": "Title", "subtitle": "Sub"},
    )
    service.upsert_locale(
        app="prod",
        store="app_store",
        locale="en-US",
        data={"subtitle": "New Sub"},
    )
    merged = service.list_section(app="prod", store="app_store", locale="en-US")
    assert merged == {"title": "Title", "subtitle": "New Sub"}

    service.upsert_locale(
        app="prod",
        store="app_store",
        locale="en-US",
        data={"description": "New"},
        replace=True,
    )
    replaced = service.list_section(app="prod", store="app_store", locale="en-US")
    assert replaced == {"description": "New"}
