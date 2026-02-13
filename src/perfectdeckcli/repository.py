from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .models import DEFAULT_LISTING_DOC


class SnapshotRepository:
    """Manages versioned snapshot files stored alongside the listing file."""

    def __init__(self, listing_path: Path) -> None:
        self.listing_path = listing_path

    def snapshots_dir(self, app: str, store: str) -> Path:
        return self.listing_path.parent / ".listing_versions" / app / store

    def save_snapshot(
        self,
        app: str,
        store: str,
        version: int,
        data: Dict[str, Any],
    ) -> Path:
        directory = self.snapshots_dir(app, store)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"v{version}.yaml"
        payload = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        path.write_text(payload + ("" if payload.endswith("\n") else "\n"), encoding="utf-8")
        return path

    def load_snapshot(self, app: str, store: str, version: int) -> Dict[str, Any]:
        path = self.snapshots_dir(app, store) / f"v{version}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Snapshot not found: {app}/{store}/v{version}")
        text = path.read_text(encoding="utf-8").strip()
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError(f"Invalid snapshot file: {path}")
        return data

    def list_snapshots(self, app: str, store: str) -> List[Dict[str, Any]]:
        directory = self.snapshots_dir(app, store)
        if not directory.exists():
            return []
        results: List[Dict[str, Any]] = []
        for path in sorted(directory.glob("v*.yaml")):
            stem = path.stem  # e.g. "v2"
            if not stem[1:].isdigit():
                continue
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8").strip())
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            results.append({
                "version": data.get("version", int(stem[1:])),
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


class CredentialsRepository:
    """Manages a `.listing_credentials.yaml` file alongside the listing file.

    Stores per-app, per-store credentials (e.g. Play Store service account
    paths, App Store Connect API keys) so users only need to provide them once.
    """

    def __init__(self, listing_path: Path) -> None:
        self.path = listing_path.parent / ".listing_credentials.yaml"

    def _load_doc(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"apps": {}}
        text = self.path.read_text(encoding="utf-8").strip()
        if not text:
            return {"apps": {}}
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            return {"apps": {}}
        data.setdefault("apps", {})
        return data

    def _save_doc(self, doc: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
        self.path.write_text(payload + ("" if payload.endswith("\n") else "\n"), encoding="utf-8")

    def load(self, app: str, store: str) -> Dict[str, Any]:
        doc = self._load_doc()
        apps = doc.get("apps", {})
        if not isinstance(apps, dict):
            return {}
        app_section = apps.get(app, {})
        if not isinstance(app_section, dict):
            return {}
        store_section = app_section.get(store, {})
        if not isinstance(store_section, dict):
            return {}
        return dict(store_section)

    def save(self, app: str, store: str, data: Dict[str, Any]) -> None:
        doc = self._load_doc()
        apps = doc.setdefault("apps", {})
        app_section = apps.get(app)
        if not isinstance(app_section, dict):
            app_section = {}
            apps[app] = app_section
        existing = app_section.get(store)
        if not isinstance(existing, dict):
            existing = {}
            app_section[store] = existing
        existing.update(data)
        self._save_doc(doc)


class ListingRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return deepcopy(DEFAULT_LISTING_DOC)

        text = self.path.read_text(encoding="utf-8").strip()
        if not text:
            return deepcopy(DEFAULT_LISTING_DOC)

        if self.path.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(text)
        else:
            data = json.loads(text)

        if not isinstance(data, dict):
            raise ValueError(f"Listing file must contain an object: {self.path}")

        data.setdefault("apps", {})
        if not isinstance(data["apps"], dict):
            raise ValueError("Top-level 'apps' must be an object.")
        return data

    def save(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.suffix.lower() in {".yaml", ".yml"}:
            payload = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        else:
            payload = json.dumps(data, indent=2, ensure_ascii=False)
        self.path.write_text(payload + ("" if payload.endswith("\n") else "\n"), encoding="utf-8")
