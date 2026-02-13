"""Tests for StorageBackend implementations."""

from __future__ import annotations

from pathlib import Path

import pytest

from perfectdeckcli.storage import (
    FileStorageBackend,
    InMemoryStorageBackend,
    StorageBackend,
)


# ======================================================================
# Protocol conformance
# ======================================================================


class TestProtocolConformance:
    def test_file_backend_implements_protocol(self, tmp_path: Path) -> None:
        backend = FileStorageBackend(tmp_path / "listings.yaml")
        assert isinstance(backend, StorageBackend)

    def test_in_memory_backend_implements_protocol(self) -> None:
        backend = InMemoryStorageBackend()
        assert isinstance(backend, StorageBackend)


# ======================================================================
# Shared interface tests (parametrised over both backends)
# ======================================================================


@pytest.fixture(params=["file", "memory"])
def backend(request, tmp_path: Path) -> StorageBackend:
    if request.param == "file":
        return FileStorageBackend(tmp_path / "listings.yaml")
    return InMemoryStorageBackend()


class TestLoadSave:
    def test_load_returns_default_doc(self, backend: StorageBackend) -> None:
        doc = backend.load()
        assert isinstance(doc, dict)
        assert "apps" in doc

    def test_save_and_load_roundtrip(self, backend: StorageBackend) -> None:
        doc = backend.load()
        doc["apps"]["myapp"] = {"play": {"global": {"key": "val"}, "locales": {}}}
        backend.save(doc)

        loaded = backend.load()
        assert loaded["apps"]["myapp"]["play"]["global"]["key"] == "val"

    def test_save_does_not_mutate_caller_data(self, backend: StorageBackend) -> None:
        doc = backend.load()
        doc["apps"]["test"] = {"data": "original"}
        backend.save(doc)

        # Mutate the dict after save — should not affect stored data
        doc["apps"]["test"]["data"] = "mutated"
        loaded = backend.load()
        assert loaded["apps"]["test"]["data"] == "original"


class TestSnapshots:
    def test_save_and_load_snapshot(self, backend: StorageBackend) -> None:
        data = {
            "version": 1,
            "timestamp": "2026-01-01T00:00:00+00:00",
            "reason": "test",
            "global": {"key": "value"},
            "locales": {"en-US": {"title": "Hello"}},
        }
        backend.save_snapshot("myapp", "play", 1, data)
        loaded = backend.load_snapshot("myapp", "play", 1)
        assert loaded == data

    def test_load_missing_snapshot_raises(self, backend: StorageBackend) -> None:
        with pytest.raises(FileNotFoundError, match="Snapshot not found"):
            backend.load_snapshot("myapp", "play", 99)

    def test_list_snapshots_empty(self, backend: StorageBackend) -> None:
        assert backend.list_snapshots("myapp", "play") == []

    def test_list_snapshots_sorted(self, backend: StorageBackend) -> None:
        for v in [3, 1, 2]:
            backend.save_snapshot("myapp", "play", v, {
                "version": v,
                "timestamp": f"2026-01-0{v}T00:00:00+00:00",
                "reason": f"v{v}",
                "global": {},
                "locales": {},
            })
        result = backend.list_snapshots("myapp", "play")
        assert len(result) == 3
        assert [s["version"] for s in result] == [1, 2, 3]

    def test_latest_snapshot_version(self, backend: StorageBackend) -> None:
        assert backend.latest_snapshot_version("myapp", "play") is None
        for v in [1, 2, 5]:
            backend.save_snapshot("myapp", "play", v, {
                "version": v, "timestamp": "", "reason": "", "global": {}, "locales": {},
            })
        assert backend.latest_snapshot_version("myapp", "play") == 5

    def test_snapshot_isolation_between_apps(self, backend: StorageBackend) -> None:
        backend.save_snapshot("app1", "play", 1, {
            "version": 1, "timestamp": "", "reason": "a1", "global": {}, "locales": {},
        })
        backend.save_snapshot("app2", "play", 1, {
            "version": 1, "timestamp": "", "reason": "a2", "global": {}, "locales": {},
        })
        a1 = backend.list_snapshots("app1", "play")
        a2 = backend.list_snapshots("app2", "play")
        assert len(a1) == 1
        assert len(a2) == 1
        assert a1[0]["reason"] == "a1"
        assert a2[0]["reason"] == "a2"

    def test_save_snapshot_does_not_mutate_caller_data(self, backend: StorageBackend) -> None:
        data = {"version": 1, "timestamp": "", "reason": "", "global": {"x": 1}, "locales": {}}
        backend.save_snapshot("myapp", "play", 1, data)
        data["global"]["x"] = 999
        loaded = backend.load_snapshot("myapp", "play", 1)
        assert loaded["global"]["x"] == 1


# ======================================================================
# InMemoryStorageBackend-specific tests
# ======================================================================


class TestInMemorySpecific:
    def test_initial_data(self) -> None:
        custom = {"apps": {"preset": {}}}
        backend = InMemoryStorageBackend(initial_data=custom)
        doc = backend.load()
        assert "preset" in doc["apps"]

    def test_default_initial_data(self) -> None:
        backend = InMemoryStorageBackend()
        doc = backend.load()
        assert doc == {"apps": {}}
