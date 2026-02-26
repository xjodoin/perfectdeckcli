"""Tests for the optional BEGIN/COMMIT/ROLLBACK transaction support."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from perfectdeckcli import mcp_server
from perfectdeckcli.project_router import ProjectListingRouter
from perfectdeckcli.service import ListingService
from perfectdeckcli.storage import FileStorageBackend, InMemoryStorageBackend


# ===========================================================================
# Service-level tests
# ===========================================================================


class TestTransactionService:
    def _svc(self) -> ListingService:
        return ListingService(InMemoryStorageBackend())

    # -- begin_transaction --------------------------------------------------

    def test_begin_sets_tx_doc(self):
        svc = self._svc()
        assert svc._tx_doc is None
        svc.begin_transaction()
        assert svc._tx_doc is not None

    def test_begin_loads_current_state(self):
        svc = self._svc()
        svc.set_element("app", "play", "title", "Before TX", locale="en-US")
        svc.begin_transaction()
        # _tx_doc should contain the state that was on disk before TX started
        assert svc._tx_doc is not None
        locales = svc._tx_doc["apps"]["app"]["play"]["locales"]
        assert locales["en-US"]["title"] == "Before TX"

    def test_double_begin_raises(self):
        svc = self._svc()
        svc.begin_transaction()
        with pytest.raises(RuntimeError, match="already active"):
            svc.begin_transaction()
        svc.rollback_transaction()

    # -- writes buffered, no disk I/O during TX ----------------------------

    def test_writes_not_persisted_to_disk_during_tx(self, tmp_path: Path):
        listing_file = tmp_path / "listings.yaml"
        svc = ListingService(FileStorageBackend(listing_file))

        svc.begin_transaction()
        svc.set_element("app", "play", "title", "In-TX Value", locale="en-US")

        # File should not exist (or not contain the in-TX value)
        if listing_file.exists():
            import yaml
            data = yaml.safe_load(listing_file.read_text())
            locales = data.get("apps", {}).get("app", {}).get("play", {}).get("locales", {})
            assert locales.get("en-US", {}).get("title") != "In-TX Value"

        svc.rollback_transaction()

    def test_multiple_writes_accumulate_in_buffer(self):
        svc = self._svc()
        svc.begin_transaction()
        svc.set_element("app", "play", "title", "Title", locale="en-US")
        svc.set_element("app", "play", "short_description", "Desc", locale="en-US")
        svc.set_element("app", "play", "title", "Title FR", locale="fr-FR")

        # All changes visible via _doc() (reads from buffer)
        assert svc.get_element("app", "play", "title", locale="en-US") == "Title"
        assert svc.get_element("app", "play", "short_description", locale="en-US") == "Desc"
        assert svc.get_element("app", "play", "title", locale="fr-FR") == "Title FR"

        svc.rollback_transaction()

    def test_doc_reads_from_buffer_not_disk(self, tmp_path: Path):
        listing_file = tmp_path / "listings.yaml"
        svc = ListingService(FileStorageBackend(listing_file))

        svc.set_element("app", "play", "title", "Disk Value", locale="en-US")
        svc.begin_transaction()
        svc.set_element("app", "play", "title", "Buffer Value", locale="en-US")

        # _doc() should return buffer value, not the on-disk value
        assert svc.get_element("app", "play", "title", locale="en-US") == "Buffer Value"

        svc.rollback_transaction()

        # After rollback, _doc() reads from disk again
        assert svc.get_element("app", "play", "title", locale="en-US") == "Disk Value"

    # -- rollback_transaction -----------------------------------------------

    def test_rollback_discards_changes(self):
        svc = self._svc()
        svc.set_element("app", "play", "title", "Original", locale="en-US")
        svc.begin_transaction()
        svc.set_element("app", "play", "title", "Changed", locale="en-US")
        svc.rollback_transaction()

        assert svc._tx_doc is None
        assert svc.get_element("app", "play", "title", locale="en-US") == "Original"

    def test_rollback_without_begin_raises(self):
        svc = self._svc()
        with pytest.raises(RuntimeError, match="No active transaction"):
            svc.rollback_transaction()

    def test_rollback_clears_tx_doc(self):
        svc = self._svc()
        svc.begin_transaction()
        svc.rollback_transaction()
        assert svc._tx_doc is None

    # -- commit_transaction -------------------------------------------------

    def test_commit_persists_changes(self):
        svc = self._svc()
        svc.begin_transaction()
        svc.set_element("app", "play", "title", "Committed", locale="en-US")
        svc.commit_transaction()

        assert svc._tx_doc is None
        assert svc.get_element("app", "play", "title", locale="en-US") == "Committed"

    def test_commit_persists_to_file(self, tmp_path: Path):
        import yaml
        listing_file = tmp_path / "listings.yaml"
        svc = ListingService(FileStorageBackend(listing_file))

        svc.begin_transaction()
        svc.set_element("app", "play", "title", "Committed", locale="en-US")
        svc.commit_transaction()

        data = yaml.safe_load(listing_file.read_text())
        assert data["apps"]["app"]["play"]["locales"]["en-US"]["title"] == "Committed"

    def test_commit_without_begin_raises(self):
        svc = self._svc()
        with pytest.raises(RuntimeError, match="No active transaction"):
            svc.commit_transaction()

    def test_commit_clears_tx_doc(self):
        svc = self._svc()
        svc.begin_transaction()
        svc.commit_transaction()
        assert svc._tx_doc is None

    def test_commit_multiple_writes_atomically(self, tmp_path: Path):
        import yaml
        listing_file = tmp_path / "listings.yaml"
        svc = ListingService(FileStorageBackend(listing_file))

        svc.begin_transaction()
        svc.set_element("app", "play", "title", "T1", locale="en-US")
        svc.set_element("app", "play", "short_description", "D1", locale="en-US")
        svc.set_element("app", "play", "title", "T2", locale="fr-FR")
        svc.commit_transaction()

        data = yaml.safe_load(listing_file.read_text())
        locales = data["apps"]["app"]["play"]["locales"]
        assert locales["en-US"]["title"] == "T1"
        assert locales["en-US"]["short_description"] == "D1"
        assert locales["fr-FR"]["title"] == "T2"

    # -- write-through when no TX ------------------------------------------

    def test_no_tx_writes_through_immediately(self, tmp_path: Path):
        import yaml
        listing_file = tmp_path / "listings.yaml"
        svc = ListingService(FileStorageBackend(listing_file))

        svc.set_element("app", "play", "title", "Immediate", locale="en-US")
        data = yaml.safe_load(listing_file.read_text())
        assert data["apps"]["app"]["play"]["locales"]["en-US"]["title"] == "Immediate"

    # -- reuse after commit/rollback ----------------------------------------

    def test_new_tx_after_commit(self):
        svc = self._svc()
        svc.begin_transaction()
        svc.set_element("app", "play", "title", "First TX", locale="en-US")
        svc.commit_transaction()

        svc.begin_transaction()
        svc.set_element("app", "play", "title", "Second TX", locale="en-US")
        svc.commit_transaction()

        assert svc.get_element("app", "play", "title", locale="en-US") == "Second TX"

    def test_new_tx_after_rollback(self):
        svc = self._svc()
        svc.begin_transaction()
        svc.set_element("app", "play", "title", "Discarded", locale="en-US")
        svc.rollback_transaction()

        svc.begin_transaction()
        svc.set_element("app", "play", "title", "Kept", locale="en-US")
        svc.commit_transaction()

        assert svc.get_element("app", "play", "title", locale="en-US") == "Kept"

    # -- snapshots bypass TX -----------------------------------------------

    def test_snapshots_bypass_transaction(self):
        """save_snapshot() writes to disk even during a TX (append-only, harmless)."""
        svc = self._svc()
        svc.init_listing("app", stores=["play"], locales=["en-US"])
        svc.begin_transaction()
        result = svc.save_snapshot("app", "play", reason="mid-tx")
        assert result["ok"] is True
        # Snapshot should be queryable (written to storage)
        snapshots = svc.list_snapshots("app", "play")
        assert len(snapshots) == 1
        svc.rollback_transaction()


# ===========================================================================
# MCP tool tests
# ===========================================================================


def _setup(tmp_path: Path, app: str = "myapp") -> None:
    mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
    mcp_server.perfectdeck_init_listing(
        mcp_server.InitListingInput(
            project_path="proj",
            app=app,
            stores=["play"],
            locales=["en-US"],
        )
    )


def _json(raw: str) -> dict:
    return json.loads(raw)


class TestTransactionMcpTools:
    # -- begin --------------------------------------------------------------

    def test_begin_returns_ok(self, tmp_path):
        _setup(tmp_path)
        result = _json(mcp_server.perfectdeck_begin_transaction(
            mcp_server.TransactionInput(project_path="proj")
        ))
        assert result["ok"] is True
        # cleanup
        mcp_server.perfectdeck_rollback_transaction(
            mcp_server.TransactionInput(project_path="proj")
        )

    def test_begin_hint_included(self, tmp_path):
        _setup(tmp_path)
        result = _json(mcp_server.perfectdeck_begin_transaction(
            mcp_server.TransactionInput(project_path="proj")
        ))
        assert "hint" in result
        assert "commit" in result["hint"].lower() or "rollback" in result["hint"].lower()
        mcp_server.perfectdeck_rollback_transaction(
            mcp_server.TransactionInput(project_path="proj")
        )

    def test_double_begin_raises(self, tmp_path):
        _setup(tmp_path)
        mcp_server.perfectdeck_begin_transaction(
            mcp_server.TransactionInput(project_path="proj")
        )
        with pytest.raises(RuntimeError, match="already active"):
            mcp_server.perfectdeck_begin_transaction(
                mcp_server.TransactionInput(project_path="proj")
            )
        mcp_server.perfectdeck_rollback_transaction(
            mcp_server.TransactionInput(project_path="proj")
        )

    # -- rollback -----------------------------------------------------------

    def test_rollback_discards_changes(self, tmp_path):
        _setup(tmp_path)
        mcp_server.perfectdeck_set_element(
            mcp_server.SetElementInput(
                project_path="proj", app="myapp", store="play",
                locale="en-US", key="title", value="Original",
            )
        )
        mcp_server.perfectdeck_begin_transaction(
            mcp_server.TransactionInput(project_path="proj")
        )
        mcp_server.perfectdeck_set_element(
            mcp_server.SetElementInput(
                project_path="proj", app="myapp", store="play",
                locale="en-US", key="title", value="Should Not Persist",
            )
        )
        result = _json(mcp_server.perfectdeck_rollback_transaction(
            mcp_server.TransactionInput(project_path="proj")
        ))
        assert result["ok"] is True

        value = _json(mcp_server.perfectdeck_get_element(
            mcp_server.GetElementInput(
                project_path="proj", app="myapp", store="play",
                locale="en-US", key="title",
            )
        ))
        assert value["value"] == "Original"

    def test_rollback_hint_included(self, tmp_path):
        _setup(tmp_path)
        mcp_server.perfectdeck_begin_transaction(
            mcp_server.TransactionInput(project_path="proj")
        )
        result = _json(mcp_server.perfectdeck_rollback_transaction(
            mcp_server.TransactionInput(project_path="proj")
        ))
        assert "hint" in result

    def test_rollback_without_begin_raises(self, tmp_path):
        _setup(tmp_path)
        with pytest.raises(RuntimeError, match="No active transaction"):
            mcp_server.perfectdeck_rollback_transaction(
                mcp_server.TransactionInput(project_path="proj")
            )

    # -- commit -------------------------------------------------------------

    def test_commit_persists_changes(self, tmp_path):
        _setup(tmp_path)
        mcp_server.perfectdeck_begin_transaction(
            mcp_server.TransactionInput(project_path="proj")
        )
        mcp_server.perfectdeck_set_element(
            mcp_server.SetElementInput(
                project_path="proj", app="myapp", store="play",
                locale="en-US", key="title", value="Committed Value",
            )
        )
        result = _json(mcp_server.perfectdeck_commit_transaction(
            mcp_server.TransactionInput(project_path="proj")
        ))
        assert result["ok"] is True

        value = _json(mcp_server.perfectdeck_get_element(
            mcp_server.GetElementInput(
                project_path="proj", app="myapp", store="play",
                locale="en-US", key="title",
            )
        ))
        assert value["value"] == "Committed Value"

    def test_commit_persists_multiple_writes(self, tmp_path):
        _setup(tmp_path)
        mcp_server.perfectdeck_begin_transaction(
            mcp_server.TransactionInput(project_path="proj")
        )
        for key, val in [("title", "My App"), ("short_description", "Great app")]:
            mcp_server.perfectdeck_set_element(
                mcp_server.SetElementInput(
                    project_path="proj", app="myapp", store="play",
                    locale="en-US", key=key, value=val,
                )
            )
        mcp_server.perfectdeck_commit_transaction(
            mcp_server.TransactionInput(project_path="proj")
        )

        for key, expected in [("title", "My App"), ("short_description", "Great app")]:
            value = _json(mcp_server.perfectdeck_get_element(
                mcp_server.GetElementInput(
                    project_path="proj", app="myapp", store="play",
                    locale="en-US", key=key,
                )
            ))
            assert value["value"] == expected

    def test_commit_hint_included(self, tmp_path):
        _setup(tmp_path)
        mcp_server.perfectdeck_begin_transaction(
            mcp_server.TransactionInput(project_path="proj")
        )
        result = _json(mcp_server.perfectdeck_commit_transaction(
            mcp_server.TransactionInput(project_path="proj")
        ))
        assert "hint" in result

    def test_commit_without_begin_raises(self, tmp_path):
        _setup(tmp_path)
        with pytest.raises(RuntimeError, match="No active transaction"):
            mcp_server.perfectdeck_commit_transaction(
                mcp_server.TransactionInput(project_path="proj")
            )

    # -- end-to-end: rollback leaves file unchanged -------------------------

    def test_e2e_rollback_file_unchanged(self, tmp_path):
        import yaml
        _setup(tmp_path)
        mcp_server.perfectdeck_set_element(
            mcp_server.SetElementInput(
                project_path="proj", app="myapp", store="play",
                locale="en-US", key="title", value="Stable",
            )
        )

        listing_file = tmp_path / "proj" / "listings.yaml"
        before = yaml.safe_load(listing_file.read_text())

        mcp_server.perfectdeck_begin_transaction(
            mcp_server.TransactionInput(project_path="proj")
        )
        mcp_server.perfectdeck_set_element(
            mcp_server.SetElementInput(
                project_path="proj", app="myapp", store="play",
                locale="en-US", key="title", value="Unstable",
            )
        )
        mcp_server.perfectdeck_rollback_transaction(
            mcp_server.TransactionInput(project_path="proj")
        )

        after = yaml.safe_load(listing_file.read_text())
        assert before == after
