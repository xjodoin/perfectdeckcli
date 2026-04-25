from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from perfectdeckcli import mcp_server, play_store
from perfectdeckcli.cli import build_parser, main
from perfectdeckcli.project_router import ProjectListingRouter
from perfectdeckcli.store_api_coverage import coverage_payload, list_api_coverage
from perfectdeckcli.store_operations import STORE_OPERATIONS


def _cli_commands() -> set[str]:
    parser = build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def _mcp_tool_names() -> set[str]:
    mod = ast.parse(Path("src/perfectdeckcli/mcp_server.py").read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in mod.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            for kw in deco.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    names.add(str(kw.value.value))
    return names


def test_store_operation_registry_exposes_registered_cli_and_mcp_names() -> None:
    cli_commands = _cli_commands()
    mcp_tools = _mcp_tool_names()
    assert STORE_OPERATIONS
    for operation in STORE_OPERATIONS:
        assert operation.title
        assert operation.provider
        assert operation.status
        if operation.exposure in {"cli+mcp", "cli-only"}:
            assert operation.cli_name in cli_commands
        if operation.exposure in {"cli+mcp", "mcp-only"}:
            assert operation.mcp_name in mcp_tools


def test_destructive_or_write_generic_operations_require_confirmation_metadata() -> None:
    generic_ops = [op for op in STORE_OPERATIONS if "generic" in op.operation_id]
    assert generic_ops
    for operation in generic_ops:
        assert operation.mutability == "write"
        assert operation.confirmation_required is True


def test_coverage_matrix_classifies_official_and_console_only_categories() -> None:
    rows = list_api_coverage()
    assert rows
    statuses = {row["status"] for row in rows}
    assert "typed-supported" in statuses
    assert "generic-supported" in statuses
    assert "console-only" in statuses
    assert any(row["provider"] == "app_store" and row["category"] == "customerReviews" for row in rows)
    assert any(row["category"] == "storeListingExperiments" and row["status"] == "console-only" for row in rows)
    payload = coverage_payload(include_rows=False)
    assert payload["ok"] is True
    assert "rows" not in payload


def test_store_api_coverage_cli_outputs_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([
        "--file",
        str(tmp_path / "listings.yaml"),
        "store-api-coverage",
        "--provider",
        "app_store",
        "--no-rows",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["summary"]["by_provider"] == {"app_store": payload["summary"]["total"]}


def test_generic_app_store_mcp_request_requires_confirmation_for_writes() -> None:
    with pytest.raises(ValueError, match="confirm_destructive"):
        mcp_server.perfectdeck_app_store_api_request(
            mcp_server.AppStoreApiRequestInput(
                project_path="proj",
                app="prod",
                app_id="123",
                key_id="KEY",
                issuer_id="ISSUER",
                private_key_path="/tmp/key.p8",
                method="POST",
                path="/v1/apps",
            )
        )


def test_generic_app_store_mcp_request_calls_client_for_reads(tmp_path: Path) -> None:
    mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
    client = MagicMock()
    client.request.return_value = {"data": []}
    with patch("perfectdeckcli.mcp_server.app_store_api.AppStoreConnectClient.from_key_file", return_value=client):
        payload = json.loads(mcp_server.perfectdeck_app_store_api_request(
            mcp_server.AppStoreApiRequestInput(
                project_path="proj",
                app="prod",
                app_id="123",
                key_id="KEY",
                issuer_id="ISSUER",
                private_key_path="/tmp/key.p8",
                method="GET",
                path="/v1/apps",
                params={"limit": "1"},
            )
        ))
    assert payload["ok"] is True
    client.request.assert_called_once_with("GET", "/v1/apps", params={"limit": "1"}, json_body=None)


def test_android_publisher_request_builds_v3_url() -> None:
    response = MagicMock()
    response.status_code = 200
    response.content = b"{}"
    response.headers = {"content-type": "application/json"}
    response.json.return_value = {"ok": True}
    session = MagicMock()
    session.request.return_value = response

    result = play_store.android_publisher_request(
        session,
        "GET",
        "/applications/com.example",
        params={"fields": "packageName"},
    )

    assert result == {"ok": True}
    session.request.assert_called_once()
    assert session.request.call_args.args[1] == (
        "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/com.example?fields=packageName"
    )
