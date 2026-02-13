from __future__ import annotations

from perfectdeckcli.service import diff_objects


def test_diff_objects_reports_added_removed_and_changed() -> None:
    left = {
        "global": {"category": "education", "priority": "high"},
        "locales": {"en-US": {"title": "A"}},
    }
    right = {
        "global": {"category": "productivity", "new": "yes"},
        "locales": {"fr-FR": {"title": "B"}},
    }
    diff = diff_objects(left, right)
    assert "global.new" in diff["added"]
    assert "global.priority" in diff["removed"]
    changed_paths = [item["path"] for item in diff["changed"]]
    assert "global.category" in changed_paths
    assert "locales.en-US" in diff["removed"]
    assert "locales.fr-FR" in diff["added"]


def test_diff_objects_same_values_have_no_changes() -> None:
    payload = {"a": {"b": 1}, "list": [1, 2, 3]}
    diff = diff_objects(payload, payload)
    assert diff == {"added": [], "removed": [], "changed": []}
