from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict

from .service import ListingService
from .storage import FileStorageBackend, StorageBackend


class ProjectListingRouter:
    """Resolves caller-relative project paths to listing services."""

    def __init__(
        self,
        root_folder: Path,
        listing_file_name: str = "listings.yaml",
        backend_factory: Callable[[Path], StorageBackend] | None = None,
    ) -> None:
        if not listing_file_name.strip():
            raise ValueError("listing_file_name must not be empty")
        self.root_folder = root_folder.resolve()
        self.listing_file_name = listing_file_name
        self._backend_factory = backend_factory or FileStorageBackend
        self._services: Dict[str, ListingService] = {}

    def _resolve_project_folder(self, project_path: str | None) -> Path:
        rel = Path(project_path or ".")
        if rel.is_absolute():
            raise ValueError("project_path must be relative to the configured root folder.")
        target = (self.root_folder / rel).resolve()
        try:
            target.relative_to(self.root_folder)
        except ValueError as exc:
            raise ValueError("project_path escapes the configured root folder.") from exc
        return target

    def service_for(self, project_path: str | None) -> ListingService:
        project_folder = self._resolve_project_folder(project_path)
        key = str(project_folder)
        existing = self._services.get(key)
        if existing is not None:
            return existing
        listing_file = project_folder / self.listing_file_name
        backend = self._backend_factory(listing_file)
        created = ListingService(backend)
        self._services[key] = created
        return created
