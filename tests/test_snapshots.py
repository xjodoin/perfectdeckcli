from __future__ import annotations

import json
from pathlib import Path

import pytest

from perfectdeckcli.repository import SnapshotRepository
from perfectdeckcli.service import ListingService
from perfectdeckcli.storage import InMemoryStorageBackend
from perfectdeckcli import mcp_server
from perfectdeckcli.project_router import ProjectListingRouter


# ======================================================================
# SnapshotRepository
# ======================================================================


class TestSnapshotRepository:
    def test_save_and_load_snapshot(self, tmp_path: Path) -> None:
        repo = SnapshotRepository(tmp_path / "listings.yaml")
        data = {
            "version": 1,
            "timestamp": "2026-01-01T00:00:00+00:00",
            "reason": "test",
            "global": {"key": "value"},
            "locales": {"en-US": {"title": "Hello"}},
        }
        repo.save_snapshot("myapp", "play", 1, data)
        loaded = repo.load_snapshot("myapp", "play", 1)
        assert loaded == data

    def test_load_missing_snapshot_raises(self, tmp_path: Path) -> None:
        repo = SnapshotRepository(tmp_path / "listings.yaml")
        with pytest.raises(FileNotFoundError, match="Snapshot not found"):
            repo.load_snapshot("myapp", "play", 99)

    def test_list_snapshots_empty(self, tmp_path: Path) -> None:
        repo = SnapshotRepository(tmp_path / "listings.yaml")
        assert repo.list_snapshots("myapp", "play") == []

    def test_list_snapshots_sorted(self, tmp_path: Path) -> None:
        repo = SnapshotRepository(tmp_path / "listings.yaml")
        for v in [3, 1, 2]:
            repo.save_snapshot("myapp", "play", v, {
                "version": v,
                "timestamp": f"2026-01-0{v}T00:00:00+00:00",
                "reason": f"v{v}",
                "global": {},
                "locales": {},
            })
        result = repo.list_snapshots("myapp", "play")
        assert len(result) == 3
        assert [s["version"] for s in result] == [1, 2, 3]

    def test_latest_snapshot_version(self, tmp_path: Path) -> None:
        repo = SnapshotRepository(tmp_path / "listings.yaml")
        assert repo.latest_snapshot_version("myapp", "play") is None
        for v in [1, 2, 5]:
            repo.save_snapshot("myapp", "play", v, {
                "version": v, "timestamp": "", "reason": "", "global": {}, "locales": {},
            })
        assert repo.latest_snapshot_version("myapp", "play") == 5

    def test_snapshots_dir_structure(self, tmp_path: Path) -> None:
        repo = SnapshotRepository(tmp_path / "listings.yaml")
        repo.save_snapshot("myapp", "app_store", 1, {
            "version": 1, "timestamp": "", "reason": "", "global": {}, "locales": {},
        })
        expected = tmp_path / ".listing_versions" / "myapp" / "app_store" / "v1.yaml"
        assert expected.exists()


# ======================================================================
# Auto-snapshot on bump_version
# ======================================================================


class TestSnapshotCreation:
    def test_bump_version_creates_snapshot(self) -> None:
        service = ListingService(InMemoryStorageBackend())
        service.init_listing(app="prod", stores=["play"], locales=["en-US"])
        # init auto-selects en-US as baseline; set on baseline bumps v1->v2
        service.set_element(app="prod", store="play", locale="en-US", key_path="title", value="Original")

        out = service.bump_version(app="prod", store="play", reason="release-1.0")
        assert out["ok"] is True

        # Snapshot should exist for v2 (pre-bump state)
        snapshots = service.list_snapshots(app="prod", store="play")
        assert len(snapshots) == 1
        assert snapshots[0]["version"] == 2
        assert snapshots[0]["reason"] == "release-1.0"

        # Snapshot data should contain the original title
        snap_data = service.storage.load_snapshot("prod", "play", 2)
        assert snap_data["locales"]["en-US"]["title"] == "Original"

    def test_import_play_store_creates_snapshot(self) -> None:
        service = ListingService(InMemoryStorageBackend())
        service.init_listing(app="prod", stores=["play"])
        service.import_from_play_store(
            app="prod",
            data={"en-US": {"title": "Remote Title", "shortDescription": "Short", "fullDescription": "Full"}},
        )

        snapshots = service.list_snapshots(app="prod", store="play")
        assert len(snapshots) == 1
        snap = service.storage.load_snapshot("prod", "play", snapshots[0]["version"])
        assert snap["locales"]["en-US"]["title"] == "Remote Title"
        assert snap["reason"] == "import-from-play-store"

    def test_import_app_store_creates_snapshot(self) -> None:
        service = ListingService(InMemoryStorageBackend())
        service.init_listing(app="prod", stores=["app_store"])
        service.import_from_app_store(
            app="prod",
            data={"en-US": {"app_name": "My App", "subtitle": "Great app"}},
        )

        snapshots = service.list_snapshots(app="prod", store="app_store")
        assert len(snapshots) == 1
        snap = service.storage.load_snapshot("prod", "app_store", snapshots[0]["version"])
        assert snap["locales"]["en-US"]["app_name"] == "My App"
        assert snap["reason"] == "import-from-app-store"

    def test_explicit_save_snapshot(self) -> None:
        service = ListingService(InMemoryStorageBackend())
        service.init_listing(app="prod", stores=["play"], locales=["en-US"])
        # baseline auto-selected; set on baseline bumps v1->v2
        service.set_element(app="prod", store="play", locale="en-US", key_path="title", value="V1 Title")

        out = service.save_snapshot(app="prod", store="play", reason="pre-translation")
        assert out["ok"] is True
        assert out["version"] == 2

        snapshots = service.list_snapshots(app="prod", store="play")
        assert len(snapshots) == 1
        assert snapshots[0]["reason"] == "pre-translation"


# ======================================================================
# Restore
# ======================================================================


class TestSnapshotRestore:
    def test_restore_specific_version(self) -> None:
        service = ListingService(InMemoryStorageBackend())
        service.init_listing(app="prod", stores=["play"], locales=["en-US"])
        # v1->v2 (baseline set)
        service.set_element(app="prod", store="play", locale="en-US", key_path="title", value="V1 Title")

        # Bump creates snapshot of v2, then bumps to v3
        service.bump_version(app="prod", store="play", reason="first-bump")

        # v3->v4 (baseline set)
        service.set_element(app="prod", store="play", locale="en-US", key_path="title", value="V2 Title")

        # Verify current is V2 Title
        current = service.get_element(app="prod", store="play", key_path="title", locale="en-US")
        assert current == "V2 Title"

        # Restore to v2 snapshot
        out = service.restore_snapshot(app="prod", store="play", version=2)
        assert out["ok"] is True
        assert out["restored_version"] == 2

        # Verify data is back to V1 Title
        restored = service.get_element(app="prod", store="play", key_path="title", locale="en-US")
        assert restored == "V1 Title"

    def test_restore_latest(self) -> None:
        service = ListingService(InMemoryStorageBackend())
        service.init_listing(app="prod", stores=["play"], locales=["en-US"])
        # v1->v2
        service.set_element(app="prod", store="play", locale="en-US", key_path="title", value="First")

        # bump: snapshot at v2 ("First"), bumps to v3
        service.bump_version(app="prod", store="play", reason="bump-1")

        # v3->v4
        service.set_element(app="prod", store="play", locale="en-US", key_path="title", value="Second")
        # bump: snapshot at v4 ("Second"), bumps to v5
        service.bump_version(app="prod", store="play", reason="bump-2")

        # v5->v6
        service.set_element(app="prod", store="play", locale="en-US", key_path="title", value="Third")

        # Restore latest (should be v4 snapshot with "Second")
        out = service.restore_snapshot(app="prod", store="play")
        assert out["ok"] is True
        assert out["restored_version"] == 4

        restored = service.get_element(app="prod", store="play", key_path="title", locale="en-US")
        assert restored == "Second"

    def test_restore_records_version_change(self) -> None:
        service = ListingService(InMemoryStorageBackend())
        service.init_listing(app="prod", stores=["play"], locales=["en-US"])
        # v1->v2
        service.set_element(app="prod", store="play", locale="en-US", key_path="title", value="Original")
        # bump: snapshot at v2, bumps to v3
        service.bump_version(app="prod", store="play", reason="bump")

        service.restore_snapshot(app="prod", store="play", version=2)

        status = service.get_update_status(app="prod", store="play")
        assert any(
            entry["reason"] == "restore-from-v2"
            for entry in status["changelog"]
        )

    def test_restore_no_snapshots_raises(self) -> None:
        service = ListingService(InMemoryStorageBackend())
        service.init_listing(app="prod", stores=["play"])
        with pytest.raises(FileNotFoundError, match="No snapshots found"):
            service.restore_snapshot(app="prod", store="play")

    def test_restore_missing_version_raises(self) -> None:
        service = ListingService(InMemoryStorageBackend())
        service.init_listing(app="prod", stores=["play"])
        with pytest.raises(FileNotFoundError, match="Snapshot not found"):
            service.restore_snapshot(app="prod", store="play", version=999)


# ======================================================================
# Diff
# ======================================================================


class TestSnapshotDiff:
    def test_diff_current_vs_snapshot(self) -> None:
        service = ListingService(InMemoryStorageBackend())
        service.init_listing(app="prod", stores=["play"], locales=["en-US"])
        # v1->v2
        service.set_element(app="prod", store="play", locale="en-US", key_path="title", value="Original")

        # bump: snapshot at v2, bumps to v3
        service.bump_version(app="prod", store="play", reason="test")

        # v3->v4
        service.set_element(app="prod", store="play", locale="en-US", key_path="title", value="Changed")

        out = service.diff_with_snapshot(app="prod", store="play", version=2)
        assert out["snapshot_version"] == 2
        assert out["diff"]["same"] is False
        assert len(out["diff"]["changed"]) > 0
        # Find the title change
        title_changes = [c for c in out["diff"]["changed"] if "title" in c["path"]]
        assert len(title_changes) > 0
        assert title_changes[0]["before"] == "Original"
        assert title_changes[0]["after"] == "Changed"

    def test_diff_shows_added_removed(self) -> None:
        service = ListingService(InMemoryStorageBackend())
        service.init_listing(app="prod", stores=["play"], locales=["en-US"])
        # v1->v2
        service.set_element(app="prod", store="play", locale="en-US", key_path="title", value="Title")
        # v2->v3
        service.set_element(app="prod", store="play", locale="en-US", key_path="old_field", value="old")

        # bump: snapshot at v3, bumps to v4
        service.bump_version(app="prod", store="play", reason="test")

        # Remove old_field and add new_field (both bump version since baseline)
        service.delete_element(app="prod", store="play", locale="en-US", key_path="old_field")
        service.set_element(app="prod", store="play", locale="en-US", key_path="new_field", value="new")

        out = service.diff_with_snapshot(app="prod", store="play", version=3)
        assert out["diff"]["same"] is False
        # new_field was not in snapshot, now in current → "added"
        assert any("new_field" in a for a in out["diff"]["added"])
        # old_field was in snapshot, removed from current → "removed"
        assert any("old_field" in r for r in out["diff"]["removed"])

    def test_diff_same_data(self) -> None:
        service = ListingService(InMemoryStorageBackend())
        service.init_listing(app="prod", stores=["play"], locales=["en-US"])
        # v1->v2
        service.set_element(app="prod", store="play", locale="en-US", key_path="title", value="Same")

        out_save = service.save_snapshot(app="prod", store="play")
        version = out_save["version"]

        out = service.diff_with_snapshot(app="prod", store="play", version=version)
        assert out["diff"]["same"] is True

    def test_diff_latest_defaults(self) -> None:
        service = ListingService(InMemoryStorageBackend())
        service.init_listing(app="prod", stores=["play"], locales=["en-US"])
        # v1->v2
        service.set_element(app="prod", store="play", locale="en-US", key_path="title", value="V1")
        # bump: snapshot at v2, bumps to v3
        service.bump_version(app="prod", store="play", reason="bump")

        out = service.diff_with_snapshot(app="prod", store="play")
        assert out["snapshot_version"] == 2

    def test_diff_no_snapshots_raises(self) -> None:
        service = ListingService(InMemoryStorageBackend())
        service.init_listing(app="prod", stores=["play"])
        with pytest.raises(FileNotFoundError, match="No snapshots found"):
            service.diff_with_snapshot(app="prod", store="play")


# ======================================================================
# MCP tools
# ======================================================================


def _json(value: str) -> dict:
    return json.loads(value)


class TestMcpSnapshotTools:
    def test_save_and_list_snapshots(self, tmp_path: Path) -> None:
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mcp_server.perfectdeck_init_listing(
            mcp_server.InitListingInput(project_path="proj", app="prod", stores=["play"], locales=["en-US"])
        )
        mcp_server.perfectdeck_set_element(
            mcp_server.SetElementInput(
                project_path="proj", app="prod", store="play", locale="en-US", key="title", value="Hello",
            )
        )

        save_out = _json(
            mcp_server.perfectdeck_save_snapshot(
                mcp_server.SaveSnapshotInput(project_path="proj", app="prod", store="play", reason="checkpoint")
            )
        )
        assert save_out["ok"] is True
        assert isinstance(save_out["version"], int)

        list_out = _json(
            mcp_server.perfectdeck_list_snapshots(
                mcp_server.VersioningInput(project_path="proj", app="prod", store="play")
            )
        )
        assert list_out["ok"] is True
        assert len(list_out["snapshots"]) == 1
        assert list_out["snapshots"][0]["reason"] == "checkpoint"

    def test_restore_snapshot_tool(self, tmp_path: Path) -> None:
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mcp_server.perfectdeck_init_listing(
            mcp_server.InitListingInput(project_path="proj", app="prod", stores=["play"], locales=["en-US"])
        )
        mcp_server.perfectdeck_set_element(
            mcp_server.SetElementInput(
                project_path="proj", app="prod", store="play", locale="en-US", key="title", value="Original",
            )
        )

        # Bump creates snapshot of pre-bump state
        _json(
            mcp_server.perfectdeck_bump_version(
                mcp_server.BumpVersionInput(project_path="proj", app="prod", store="play", reason="bump")
            )
        )

        # Find the snapshot version
        snaps = _json(
            mcp_server.perfectdeck_list_snapshots(
                mcp_server.VersioningInput(project_path="proj", app="prod", store="play")
            )
        )
        snap_version = snaps["snapshots"][0]["version"]

        # Change data
        mcp_server.perfectdeck_set_element(
            mcp_server.SetElementInput(
                project_path="proj", app="prod", store="play", locale="en-US", key="title", value="Changed",
            )
        )

        # Restore to snapshot
        restore_out = _json(
            mcp_server.perfectdeck_restore_snapshot(
                mcp_server.SnapshotInput(project_path="proj", app="prod", store="play", version=snap_version)
            )
        )
        assert restore_out["ok"] is True
        assert restore_out["restored_version"] == snap_version

        # Verify restored
        get_out = _json(
            mcp_server.perfectdeck_get_element(
                mcp_server.GetElementInput(
                    project_path="proj", app="prod", store="play", locale="en-US", key="title",
                )
            )
        )
        assert get_out["value"] == "Original"

    def test_diff_snapshot_tool(self, tmp_path: Path) -> None:
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mcp_server.perfectdeck_init_listing(
            mcp_server.InitListingInput(project_path="proj", app="prod", stores=["play"], locales=["en-US"])
        )
        mcp_server.perfectdeck_set_element(
            mcp_server.SetElementInput(
                project_path="proj", app="prod", store="play", locale="en-US", key="title", value="V1",
            )
        )
        mcp_server.perfectdeck_bump_version(
            mcp_server.BumpVersionInput(project_path="proj", app="prod", store="play", reason="bump")
        )

        # Get snapshot version
        snaps = _json(
            mcp_server.perfectdeck_list_snapshots(
                mcp_server.VersioningInput(project_path="proj", app="prod", store="play")
            )
        )
        snap_version = snaps["snapshots"][0]["version"]

        mcp_server.perfectdeck_set_element(
            mcp_server.SetElementInput(
                project_path="proj", app="prod", store="play", locale="en-US", key="title", value="V2",
            )
        )

        diff_out = _json(
            mcp_server.perfectdeck_diff_snapshot(
                mcp_server.SnapshotInput(project_path="proj", app="prod", store="play", version=snap_version)
            )
        )
        assert diff_out["ok"] is True
        assert diff_out["snapshot_version"] == snap_version
        assert diff_out["diff"]["same"] is False

    def test_restore_latest_snapshot_tool(self, tmp_path: Path) -> None:
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mcp_server.perfectdeck_init_listing(
            mcp_server.InitListingInput(project_path="proj", app="prod", stores=["play"], locales=["en-US"])
        )
        mcp_server.perfectdeck_set_element(
            mcp_server.SetElementInput(
                project_path="proj", app="prod", store="play", locale="en-US", key="title", value="A",
            )
        )
        mcp_server.perfectdeck_bump_version(
            mcp_server.BumpVersionInput(project_path="proj", app="prod", store="play", reason="bump")
        )

        # Get snapshot version for assertion
        snaps = _json(
            mcp_server.perfectdeck_list_snapshots(
                mcp_server.VersioningInput(project_path="proj", app="prod", store="play")
            )
        )
        snap_version = snaps["snapshots"][-1]["version"]

        # Restore without specifying version (latest)
        restore_out = _json(
            mcp_server.perfectdeck_restore_snapshot(
                mcp_server.SnapshotInput(project_path="proj", app="prod", store="play")
            )
        )
        assert restore_out["ok"] is True
        assert restore_out["restored_version"] == snap_version
