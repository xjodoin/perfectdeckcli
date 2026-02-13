"""Tests for credential persistence (CredentialsRepository, StorageBackend, MCP resolution)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from perfectdeckcli.repository import CredentialsRepository
from perfectdeckcli.storage import (
    FileStorageBackend,
    InMemoryStorageBackend,
    StorageBackend,
)
from perfectdeckcli import mcp_server
from perfectdeckcli.project_router import ProjectListingRouter


# ======================================================================
# CredentialsRepository unit tests
# ======================================================================


class TestCredentialsRepository:
    def test_load_empty(self, tmp_path: Path) -> None:
        repo = CredentialsRepository(tmp_path / "listings.yaml")
        assert repo.load("myapp", "play") == {}

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        repo = CredentialsRepository(tmp_path / "listings.yaml")
        repo.save("myapp", "play", {
            "package_name": "com.example.app",
            "credentials_path": "/path/to/sa.json",
        })
        loaded = repo.load("myapp", "play")
        assert loaded["package_name"] == "com.example.app"
        assert loaded["credentials_path"] == "/path/to/sa.json"

    def test_save_merges_into_existing(self, tmp_path: Path) -> None:
        repo = CredentialsRepository(tmp_path / "listings.yaml")
        repo.save("myapp", "play", {"package_name": "com.example.app"})
        repo.save("myapp", "play", {"credentials_path": "/path/to/sa.json"})
        loaded = repo.load("myapp", "play")
        assert loaded["package_name"] == "com.example.app"
        assert loaded["credentials_path"] == "/path/to/sa.json"

    def test_save_overwrites_existing_key(self, tmp_path: Path) -> None:
        repo = CredentialsRepository(tmp_path / "listings.yaml")
        repo.save("myapp", "play", {"package_name": "old"})
        repo.save("myapp", "play", {"package_name": "new"})
        assert repo.load("myapp", "play")["package_name"] == "new"

    def test_isolation_between_apps(self, tmp_path: Path) -> None:
        repo = CredentialsRepository(tmp_path / "listings.yaml")
        repo.save("app1", "play", {"package_name": "com.app1"})
        repo.save("app2", "play", {"package_name": "com.app2"})
        assert repo.load("app1", "play")["package_name"] == "com.app1"
        assert repo.load("app2", "play")["package_name"] == "com.app2"

    def test_isolation_between_stores(self, tmp_path: Path) -> None:
        repo = CredentialsRepository(tmp_path / "listings.yaml")
        repo.save("myapp", "play", {"package_name": "com.example"})
        repo.save("myapp", "app_store", {"app_id": "12345"})
        assert repo.load("myapp", "play") == {"package_name": "com.example"}
        assert repo.load("myapp", "app_store") == {"app_id": "12345"}

    def test_file_is_yaml(self, tmp_path: Path) -> None:
        repo = CredentialsRepository(tmp_path / "listings.yaml")
        repo.save("myapp", "play", {"package_name": "com.example"})
        cred_path = tmp_path / ".listing_credentials.yaml"
        assert cred_path.exists()
        data = yaml.safe_load(cred_path.read_text(encoding="utf-8"))
        assert data["apps"]["myapp"]["play"]["package_name"] == "com.example"

    def test_load_with_corrupt_file(self, tmp_path: Path) -> None:
        cred_path = tmp_path / ".listing_credentials.yaml"
        cred_path.write_text("not a dict", encoding="utf-8")
        repo = CredentialsRepository(tmp_path / "listings.yaml")
        assert repo.load("myapp", "play") == {}


# ======================================================================
# StorageBackend credential methods
# ======================================================================


@pytest.fixture(params=["file", "memory"])
def backend(request, tmp_path: Path) -> StorageBackend:
    if request.param == "file":
        return FileStorageBackend(tmp_path / "listings.yaml")
    return InMemoryStorageBackend()


class TestStorageCredentials:
    def test_load_empty(self, backend: StorageBackend) -> None:
        assert backend.load_credentials("myapp", "play") == {}

    def test_save_and_load(self, backend: StorageBackend) -> None:
        backend.save_credentials("myapp", "play", {"package_name": "com.example"})
        loaded = backend.load_credentials("myapp", "play")
        assert loaded["package_name"] == "com.example"

    def test_save_merges(self, backend: StorageBackend) -> None:
        backend.save_credentials("myapp", "play", {"package_name": "com.example"})
        backend.save_credentials("myapp", "play", {"credentials_path": "/sa.json"})
        loaded = backend.load_credentials("myapp", "play")
        assert loaded["package_name"] == "com.example"
        assert loaded["credentials_path"] == "/sa.json"

    def test_isolation(self, backend: StorageBackend) -> None:
        backend.save_credentials("app1", "play", {"package_name": "com.app1"})
        backend.save_credentials("app2", "app_store", {"app_id": "999"})
        assert backend.load_credentials("app1", "play")["package_name"] == "com.app1"
        assert backend.load_credentials("app2", "app_store")["app_id"] == "999"
        assert backend.load_credentials("app1", "app_store") == {}


# ======================================================================
# MCP credential resolution (using InMemoryStorageBackend)
# ======================================================================


def _json(value: str) -> dict:
    return json.loads(value)


class TestMcpCredentialResolution:
    """Test that credential resolution helpers work through the MCP layer."""

    def test_resolve_play_from_stored(self, tmp_path: Path) -> None:
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        # Init listing so the service exists
        mcp_server.perfectdeck_init_listing(
            mcp_server.InitListingInput(project_path="proj", app="prod", stores=["play"], locales=["en-US"])
        )
        # Save credentials directly
        service = mcp_server.router.service_for("proj")
        service.save_credentials("prod", "play", {
            "package_name": "com.stored.app",
            "credentials_path": "/stored/sa.json",
        })

        # Resolve without explicit values
        pkg, creds = mcp_server._resolve_play_credentials("proj", "prod", None, None)
        assert pkg == "com.stored.app"
        assert creds == "/stored/sa.json"

    def test_resolve_play_explicit_overrides_stored(self, tmp_path: Path) -> None:
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mcp_server.perfectdeck_init_listing(
            mcp_server.InitListingInput(project_path="proj", app="prod", stores=["play"], locales=["en-US"])
        )
        service = mcp_server.router.service_for("proj")
        service.save_credentials("prod", "play", {
            "package_name": "com.stored.app",
            "credentials_path": "/stored/sa.json",
        })

        pkg, creds = mcp_server._resolve_play_credentials("proj", "prod", "com.explicit.app", "/explicit/sa.json")
        assert pkg == "com.explicit.app"
        assert creds == "/explicit/sa.json"

    def test_resolve_play_raises_when_missing(self, tmp_path: Path) -> None:
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mcp_server.perfectdeck_init_listing(
            mcp_server.InitListingInput(project_path="proj", app="prod", stores=["play"], locales=["en-US"])
        )
        with pytest.raises(ValueError, match="package_name is required"):
            mcp_server._resolve_play_credentials("proj", "prod", None, None)

    def test_resolve_app_store_from_stored(self, tmp_path: Path) -> None:
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mcp_server.perfectdeck_init_listing(
            mcp_server.InitListingInput(project_path="proj", app="prod", stores=["app_store"], locales=["en-US"])
        )
        service = mcp_server.router.service_for("proj")
        service.save_credentials("prod", "app_store", {
            "app_id": "12345",
            "key_id": "KEY1",
            "issuer_id": "ISSUER1",
            "private_key_path": "/key.p8",
        })

        r_app_id, r_key_id, r_issuer_id, r_pk = mcp_server._resolve_app_store_credentials(
            "proj", "prod", None, None, None, None,
        )
        assert r_app_id == "12345"
        assert r_key_id == "KEY1"
        assert r_issuer_id == "ISSUER1"
        assert r_pk == "/key.p8"

    def test_resolve_app_store_raises_when_missing(self, tmp_path: Path) -> None:
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mcp_server.perfectdeck_init_listing(
            mcp_server.InitListingInput(project_path="proj", app="prod", stores=["app_store"], locales=["en-US"])
        )
        with pytest.raises(ValueError, match="Missing App Store credentials"):
            mcp_server._resolve_app_store_credentials("proj", "prod", None, None, None, None)

    def test_persist_play_credentials(self, tmp_path: Path) -> None:
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mcp_server.perfectdeck_init_listing(
            mcp_server.InitListingInput(project_path="proj", app="prod", stores=["play"], locales=["en-US"])
        )
        mcp_server._persist_play_credentials("proj", "prod", "com.test.app", "/test/sa.json")

        service = mcp_server.router.service_for("proj")
        loaded = service.get_credentials("prod", "play")
        assert loaded["package_name"] == "com.test.app"
        assert loaded["credentials_path"] == "/test/sa.json"

    def test_persist_app_store_credentials(self, tmp_path: Path) -> None:
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mcp_server.perfectdeck_init_listing(
            mcp_server.InitListingInput(project_path="proj", app="prod", stores=["app_store"], locales=["en-US"])
        )
        mcp_server._persist_app_store_credentials("proj", "prod", "999", "K1", "I1", "/k.p8")

        service = mcp_server.router.service_for("proj")
        loaded = service.get_credentials("prod", "app_store")
        assert loaded == {
            "app_id": "999",
            "key_id": "K1",
            "issuer_id": "I1",
            "private_key_path": "/k.p8",
        }
