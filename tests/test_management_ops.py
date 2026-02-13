from __future__ import annotations

from perfectdeckcli.service import ListingService, diff_objects
from perfectdeckcli.storage import InMemoryStorageBackend


def test_init_and_language_ops() -> None:
    service = ListingService(InMemoryStorageBackend())

    init_out = service.init_listing(
        app="prod",
        stores=["play", "app_store"],
        locales=["en-US"],
    )
    assert init_out["ok"] is True
    assert set(init_out["stores"]) == {"play", "app_store"}

    langs = service.list_languages(app="prod", store="play")
    assert langs == ["en-US"]

    add_out = service.add_language(
        app="prod",
        store="play",
        locale="fr-FR",
        copy_from_locale="en-US",
    )
    assert add_out["ok"] is True
    assert sorted(service.list_languages(app="prod", store="play")) == ["en-US", "fr-FR"]


def test_replace_section_and_diff() -> None:
    service = ListingService(InMemoryStorageBackend())
    service.init_listing(app="prod")

    service.replace_section(
        app="prod",
        store="play",
        payload={
            "global": {"category": "education"},
            "locales": {"en-US": {"title": "A"}},
        },
        merge=False,
    )
    current = service.list_section(app="prod", store="play")
    assert current["global"]["category"] == "education"
    assert current["locales"]["en-US"]["title"] == "A"

    compared = {"global": {"category": "productivity"}, "locales": {"en-US": {"title": "A"}}}
    diff = diff_objects(current, compared)
    assert "global.category" in [item["path"] for item in diff["changed"]]


def test_cross_project_sync_pattern() -> None:
    source = ListingService(InMemoryStorageBackend())
    target = ListingService(InMemoryStorageBackend())

    source.init_listing(app="prod", locales=["en-US"])
    source.set_element(app="prod", store="play", key_path="title", value="Source Title", locale="en-US")

    payload = source.list_section(app="prod", store="play")
    target.replace_section(app="prod", store="play", payload=payload, merge=False)

    synced = target.list_section(app="prod", store="play")
    assert synced["locales"]["en-US"]["title"] == "Source Title"
