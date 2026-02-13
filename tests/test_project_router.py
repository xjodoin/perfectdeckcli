from __future__ import annotations

from pathlib import Path

import yaml

from perfectdeckcli.project_router import ProjectListingRouter
from perfectdeckcli.storage import InMemoryStorageBackend


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_router_writes_to_independent_projects(tmp_path: Path) -> None:
    router = ProjectListingRouter(root_folder=tmp_path)

    project_a = router.service_for("apps/a")
    project_b = router.service_for("apps/b")

    project_a.set_element("prod", "play", "title", "App A", locale="en-US")
    project_b.set_element("prod", "play", "title", "App B", locale="en-US")

    a_file = tmp_path / "apps" / "a" / "listings.yaml"
    b_file = tmp_path / "apps" / "b" / "listings.yaml"
    assert _read_yaml(a_file)["apps"]["prod"]["play"]["locales"]["en-US"]["title"] == "App A"
    assert _read_yaml(b_file)["apps"]["prod"]["play"]["locales"]["en-US"]["title"] == "App B"


def test_router_rejects_path_escape(tmp_path: Path) -> None:
    router = ProjectListingRouter(root_folder=tmp_path)
    try:
        router.service_for("../outside")
    except ValueError as exc:
        assert "escapes" in str(exc)
    else:
        raise AssertionError("Expected ValueError for path escape")


def test_router_with_custom_backend_factory(tmp_path: Path) -> None:
    """Router accepts a custom backend_factory that overrides default FileStorageBackend."""
    created_paths: list[Path] = []

    def factory(path: Path) -> InMemoryStorageBackend:
        created_paths.append(path)
        return InMemoryStorageBackend()

    router = ProjectListingRouter(root_folder=tmp_path, backend_factory=factory)
    service = router.service_for("proj")
    service.init_listing(app="prod")

    assert len(created_paths) == 1
    assert "proj" in str(created_paths[0])
    assert service.list_apps() == ["prod"]
