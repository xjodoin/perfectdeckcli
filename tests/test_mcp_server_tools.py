from __future__ import annotations

import json
from pathlib import Path

from perfectdeckcli import mcp_server
from perfectdeckcli.project_router import ProjectListingRouter


def _json(value: str) -> dict:
    return json.loads(value)


def test_mcp_init_and_listing_discovery(tmp_path: Path) -> None:
    mcp_server.router = ProjectListingRouter(root_folder=tmp_path)

    out = _json(
        mcp_server.perfectdeck_init_listing(
            mcp_server.InitListingInput(
                project_path="proj-a",
                app="prod",
                stores=["play", "app_store"],
                locales=["en-US", "fr-FR"],
            )
        )
    )
    assert out["ok"] is True

    apps = _json(mcp_server.perfectdeck_list_apps(mcp_server.ProjectInput(project_path="proj-a")))
    assert apps["apps"] == ["prod"]

    stores = _json(
        mcp_server.perfectdeck_list_stores(
            mcp_server.ListStoresInput(project_path="proj-a", app="prod")
        )
    )
    assert stores["stores"] == ["app_store", "play"]

    langs = _json(
        mcp_server.perfectdeck_list_languages(
            mcp_server.ListLanguagesInput(project_path="proj-a", app="prod", store="play")
        )
    )
    assert langs["languages"] == ["en-US", "fr-FR"]


def test_mcp_add_language_set_get_and_delete(tmp_path: Path) -> None:
    mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
    mcp_server.perfectdeck_init_listing(
        mcp_server.InitListingInput(project_path="proj-a", app="prod", stores=["play"], locales=["en-US"])
    )
    mcp_server.perfectdeck_set_element(
        mcp_server.SetElementInput(
            project_path="proj-a",
            app="prod",
            store="play",
            locale="en-US",
            key="title",
            value="English Title",
        )
    )

    add_out = _json(
        mcp_server.perfectdeck_add_language(
            mcp_server.AddLanguageInput(
                project_path="proj-a",
                app="prod",
                store="play",
                locale="fr-FR",
                copy_from_locale="en-US",
            )
        )
    )
    assert add_out["created"] is True
    assert add_out["current_fields"] == ["title"]
    assert sorted(add_out["all_languages"]) == ["en-US", "fr-FR"]
    guide = add_out["guide"]
    assert "title" in guide["store_fields"]
    assert "short_description" in guide["store_fields"]
    assert "full_description" in guide["store_fields"]
    assert guide["store_fields"]["title"]["max_length"] == 30
    assert "short_description" in guide["missing_fields"]
    assert "full_description" in guide["missing_fields"]
    assert any("copied from" in s for s in guide["next_steps"])

    fr_title = _json(
        mcp_server.perfectdeck_get_element(
            mcp_server.GetElementInput(
                project_path="proj-a",
                app="prod",
                store="play",
                locale="fr-FR",
                key="title",
            )
        )
    )
    assert fr_title["value"] == "English Title"

    deleted = _json(
        mcp_server.perfectdeck_delete_element(
            mcp_server.DeleteElementInput(
                project_path="proj-a",
                app="prod",
                store="play",
                locale="fr-FR",
                key="title",
            )
        )
    )
    assert deleted["deleted"] is True


def test_mcp_sync_and_diff_between_projects(tmp_path: Path) -> None:
    mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
    mcp_server.perfectdeck_init_listing(
        mcp_server.InitListingInput(project_path="source", app="prod", stores=["play"], locales=["en-US"])
    )
    mcp_server.perfectdeck_init_listing(
        mcp_server.InitListingInput(project_path="target", app="prod", stores=["play"], locales=["en-US"])
    )

    mcp_server.perfectdeck_set_element(
        mcp_server.SetElementInput(
            project_path="source",
            app="prod",
            store="play",
            locale="en-US",
            key="title",
            value="From Source",
        )
    )

    diff_before = _json(
        mcp_server.perfectdeck_diff_listing(
            mcp_server.DiffListingInput(
                project_path="source",
                app="prod",
                store="play",
                compare_project_path="target",
            )
        )
    )
    assert diff_before["diff"]["same"] is False

    sync_out = _json(
        mcp_server.perfectdeck_sync_listing(
            mcp_server.SyncListingInput(
                source_project_path="source",
                target_project_path="target",
                app="prod",
                store="play",
                mode="replace",
            )
        )
    )
    assert sync_out["ok"] is True

    diff_after = _json(
        mcp_server.perfectdeck_diff_listing(
            mcp_server.DiffListingInput(
                project_path="source",
                app="prod",
                store="play",
                compare_project_path="target",
            )
        )
    )
    assert diff_after["diff"]["same"] is True


def test_mcp_versioning_workflow(tmp_path: Path) -> None:
    mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
    mcp_server.perfectdeck_init_listing(
        mcp_server.InitListingInput(
            project_path="proj-v",
            app="prod",
            stores=["play"],
            locales=["en-US", "fr-FR"],
            baseline_locale="en-US",
        )
    )
    mcp_server.perfectdeck_set_element(
        mcp_server.SetElementInput(
            project_path="proj-v",
            app="prod",
            store="play",
            locale="en-US",
            key="title",
            value="v2 title",
        )
    )

    status_before = _json(
        mcp_server.perfectdeck_get_update_status(
            mcp_server.VersioningInput(project_path="proj-v", app="prod", store="play")
        )
    )["status"]
    assert "fr-FR" in status_before["stale_locales"]

    _json(
        mcp_server.perfectdeck_mark_language_updated(
            mcp_server.MarkLanguageUpdatedInput(
                project_path="proj-v",
                app="prod",
                store="play",
                locale="fr-FR",
            )
        )
    )
    status_after = _json(
        mcp_server.perfectdeck_get_update_status(
            mcp_server.VersioningInput(project_path="proj-v", app="prod", store="play")
        )
    )["status"]
    assert "fr-FR" in status_after["up_to_date_locales"]

    bumped = _json(
        mcp_server.perfectdeck_bump_version(
            mcp_server.BumpVersionInput(
                project_path="proj-v",
                app="prod",
                store="play",
                reason="big copy refresh",
                source_locale="en-US",
            )
        )
    )
    assert bumped["current_version"] >= status_after["current_version"] + 1


def test_mcp_init_from_existing_between_projects(tmp_path) -> None:
    mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
    mcp_server.perfectdeck_init_listing(
        mcp_server.InitListingInput(
            project_path="source",
            app="prod",
            stores=["play"],
            locales=["en-US", "fr-FR"],
            baseline_locale="en-US",
        )
    )
    mcp_server.perfectdeck_set_element(
        mcp_server.SetElementInput(
            project_path="source",
            app="prod",
            store="play",
            locale="fr-FR",
            key="title",
            value="Bonjour",
        )
    )
    out = _json(
        mcp_server.perfectdeck_init_from_existing(
            mcp_server.InitFromExistingInput(
                source_project_path="source",
                source_app="prod",
                source_store="play",
                target_project_path="target",
                target_app="new-prod",
                target_store="app_store",
                locales=["fr-FR"],
                baseline_locale="fr-FR",
                overwrite=False,
            )
        )
    )
    assert out["ok"] is True
    payload = _json(
        mcp_server.perfectdeck_list_section(
            mcp_server.ListSectionInput(
                project_path="target",
                app="new-prod",
                store="app_store",
            )
        )
    )["data"]
    assert list(payload["locales"].keys()) == ["fr-FR"]


def test_mcp_add_language_guide_for_app_store(tmp_path: Path) -> None:
    mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
    mcp_server.perfectdeck_init_listing(
        mcp_server.InitListingInput(
            project_path="proj-guide", app="prod", stores=["app_store"], locales=["en-US"]
        )
    )

    add_out = _json(
        mcp_server.perfectdeck_add_language(
            mcp_server.AddLanguageInput(
                project_path="proj-guide",
                app="prod",
                store="app_store",
                locale="ja",
            )
        )
    )
    assert add_out["created"] is True
    guide = add_out["guide"]
    # App Store fields
    assert "app_name" in guide["store_fields"]
    assert "subtitle" in guide["store_fields"]
    assert "description" in guide["store_fields"]
    assert "keywords" in guide["store_fields"]
    assert "promotional_text" in guide["store_fields"]
    assert guide["store_fields"]["keywords"]["max_length"] == 100
    # Locale is empty — all fields should be missing
    assert sorted(guide["missing_fields"]) == sorted(guide["store_fields"].keys())
    # Next steps should mention empty locale
    assert any("empty" in s.lower() for s in guide["next_steps"])
    assert any("validate" in s.lower() for s in guide["next_steps"])
    assert any("mark" in s.lower() for s in guide["next_steps"])
