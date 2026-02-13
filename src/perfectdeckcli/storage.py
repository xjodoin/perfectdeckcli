from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Protocol, runtime_checkable

from pathlib import Path

from .models import DEFAULT_LISTING_DOC
from .repository import CredentialsRepository, ListingRepository, SnapshotRepository


@runtime_checkable
class StorageBackend(Protocol):
    """Unified storage interface for listing data and snapshots."""

    def load(self) -> Dict[str, Any]: ...
    def save(self, data: Dict[str, Any]) -> None: ...
    def save_snapshot(self, app: str, store: str, version: int, data: Dict[str, Any]) -> None: ...
    def load_snapshot(self, app: str, store: str, version: int) -> Dict[str, Any]: ...
    def list_snapshots(self, app: str, store: str) -> List[Dict[str, Any]]: ...
    def latest_snapshot_version(self, app: str, store: str) -> int | None: ...
    def load_credentials(self, app: str, store: str) -> Dict[str, Any]: ...
    def save_credentials(self, app: str, store: str, data: Dict[str, Any]) -> None: ...


class FileStorageBackend:
    """File-based storage backend wrapping ListingRepository + SnapshotRepository."""

    def __init__(self, listing_path: Path) -> None:
        self._repo = ListingRepository(listing_path)
        self._snapshots = SnapshotRepository(listing_path)
        self._credentials = CredentialsRepository(listing_path)

    def load(self) -> Dict[str, Any]:
        return self._repo.load()

    def save(self, data: Dict[str, Any]) -> None:
        self._repo.save(data)

    def save_snapshot(self, app: str, store: str, version: int, data: Dict[str, Any]) -> None:
        self._snapshots.save_snapshot(app, store, version, data)

    def load_snapshot(self, app: str, store: str, version: int) -> Dict[str, Any]:
        return self._snapshots.load_snapshot(app, store, version)

    def list_snapshots(self, app: str, store: str) -> List[Dict[str, Any]]:
        return self._snapshots.list_snapshots(app, store)

    def latest_snapshot_version(self, app: str, store: str) -> int | None:
        return self._snapshots.latest_snapshot_version(app, store)

    def load_credentials(self, app: str, store: str) -> Dict[str, Any]:
        return self._credentials.load(app, store)

    def save_credentials(self, app: str, store: str, data: Dict[str, Any]) -> None:
        self._credentials.save(app, store, data)


class InMemoryStorageBackend:
    """In-memory storage backend for tests. No disk I/O."""

    def __init__(self, initial_data: Dict[str, Any] | None = None) -> None:
        self._data: Dict[str, Any] = initial_data if initial_data is not None else deepcopy(DEFAULT_LISTING_DOC)
        self._snapshots: Dict[tuple[str, str, int], Dict[str, Any]] = {}
        self._credentials: Dict[tuple[str, str], Dict[str, Any]] = {}

    def load(self) -> Dict[str, Any]:
        return deepcopy(self._data)

    def save(self, data: Dict[str, Any]) -> None:
        self._data = deepcopy(data)

    def save_snapshot(self, app: str, store: str, version: int, data: Dict[str, Any]) -> None:
        self._snapshots[(app, store, version)] = deepcopy(data)

    def load_snapshot(self, app: str, store: str, version: int) -> Dict[str, Any]:
        key = (app, store, version)
        if key not in self._snapshots:
            raise FileNotFoundError(f"Snapshot not found: {app}/{store}/v{version}")
        return deepcopy(self._snapshots[key])

    def list_snapshots(self, app: str, store: str) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for (s_app, s_store, s_version), data in self._snapshots.items():
            if s_app == app and s_store == store:
                results.append({
                    "version": data.get("version", s_version),
                    "timestamp": data.get("timestamp", ""),
                    "reason": data.get("reason", ""),
                })
        results.sort(key=lambda s: s["version"])
        return results

    def latest_snapshot_version(self, app: str, store: str) -> int | None:
        snapshots = self.list_snapshots(app, store)
        if not snapshots:
            return None
        return snapshots[-1]["version"]

    def load_credentials(self, app: str, store: str) -> Dict[str, Any]:
        return deepcopy(self._credentials.get((app, store), {}))

    def save_credentials(self, app: str, store: str, data: Dict[str, Any]) -> None:
        existing = self._credentials.get((app, store), {})
        existing.update(deepcopy(data))
        self._credentials[(app, store)] = existing
