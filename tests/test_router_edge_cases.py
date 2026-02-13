from __future__ import annotations

from pathlib import Path

import pytest

from perfectdeckcli.project_router import ProjectListingRouter


def test_router_rejects_absolute_project_path(tmp_path: Path) -> None:
    router = ProjectListingRouter(root_folder=tmp_path)
    with pytest.raises(ValueError):
        router.service_for(str((tmp_path / "x").resolve()))


def test_router_returns_cached_service_for_same_path(tmp_path: Path) -> None:
    router = ProjectListingRouter(root_folder=tmp_path)
    a = router.service_for("apps/prod")
    b = router.service_for("apps/prod")
    assert a is b


def test_router_custom_listing_file_name(tmp_path: Path) -> None:
    router = ProjectListingRouter(root_folder=tmp_path, listing_file_name="store-data.yaml")
    service = router.service_for("apps/prod")
    service.set_element(app="prod", store="play", key_path="title", value="Hello", locale="en-US")
    assert (tmp_path / "apps" / "prod" / "store-data.yaml").exists()
