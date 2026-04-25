"""Extensive tests for new MCP tools: validation, push, diff/sync remote, etc."""

from __future__ import annotations

import json
import gzip
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from perfectdeckcli import mcp_server
from perfectdeckcli.project_router import ProjectListingRouter


def _json(value: str) -> dict:
    return json.loads(value)


def _setup_project(tmp_path: Path, app: str = "prod", locales: list | None = None) -> None:
    """Initialize a project with play and app_store listings."""
    mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
    mcp_server.perfectdeck_init_listing(
        mcp_server.InitListingInput(
            project_path="proj",
            app=app,
            stores=["play", "app_store"],
            locales=locales or ["en-US", "fr-FR"],
        )
    )


def _set_play_data(app: str, locale: str, data: dict) -> None:
    for key, value in data.items():
        mcp_server.perfectdeck_set_element(
            mcp_server.SetElementInput(
                project_path="proj", app=app, store="play",
                locale=locale, key=key, value=value,
            )
        )


def _set_app_store_data(app: str, locale: str, data: dict) -> None:
    for key, value in data.items():
        mcp_server.perfectdeck_set_element(
            mcp_server.SetElementInput(
                project_path="proj", app=app, store="app_store",
                locale=locale, key=key, value=value,
            )
        )


def _app_store_auth_kwargs() -> dict:
    return {
        "app_id": "1234567890",
        "key_id": "KEY123",
        "issuer_id": "ISSUER456",
        "private_key_path": "/tmp/AuthKey_KEY123.p8",
    }


# ======================================================================
# Store analytics/reporting MCP tools
# ======================================================================


class TestAnalyticsReportingTools:
    def test_app_store_sales_report_tool(self, tmp_path):
        _setup_project(tmp_path)
        client = MagicMock()
        client.download_sales_report.return_value = gzip.compress(b"Date\tUnits\n2026-04-20\t9\n")
        with patch("perfectdeckcli.mcp_server.app_store_api.AppStoreConnectClient.from_key_file", return_value=client):
            out = _json(
                mcp_server.perfectdeck_get_app_store_sales_report(
                    mcp_server.AppStoreSalesReportInput(
                        project_path="proj",
                        app="prod",
                        vendor_number="123456",
                        max_rows=10,
                        **_app_store_auth_kwargs(),
                    )
                )
            )
        assert out["ok"] is True
        assert out["rows"][0]["Units"] == "9"
        assert out["report_type"] == "SALES"
        client.download_sales_report.assert_called_once()

    def test_app_store_analytics_list_instances_tool(self, tmp_path):
        _setup_project(tmp_path)
        client = MagicMock()
        client.list_analytics_report_instances.return_value = {"data": [{"id": "i1"}]}
        with patch("perfectdeckcli.mcp_server.app_store_api.AppStoreConnectClient.from_key_file", return_value=client):
            out = _json(
                mcp_server.perfectdeck_list_app_store_analytics_instances(
                    mcp_server.ListAppStoreAnalyticsInstancesInput(
                        project_path="proj",
                        app="prod",
                        report_id="r1",
                        granularity="DAILY",
                        processing_date="2026-04-20",
                        **_app_store_auth_kwargs(),
                    )
                )
            )
        assert out["ok"] is True
        assert out["response"]["data"][0]["id"] == "i1"
        client.list_analytics_report_instances.assert_called_once_with(
            "r1", granularity="DAILY", processing_date="2026-04-20", limit=200,
        )

    def test_play_vitals_tool(self, tmp_path):
        _setup_project(tmp_path)
        service = mcp_server._router().service_for("proj")
        service.save_credentials("prod", "play", {"package_name": "com.example.app"})
        with (
            patch("perfectdeckcli.mcp_server.play_store_api.create_reporting_service", return_value=MagicMock()) as create_reporting,
            patch("perfectdeckcli.mcp_server.play_store_api.query_vitals_metric", return_value={"rows": [{"metrics": []}]}) as query,
        ):
            out = _json(
                mcp_server.perfectdeck_query_play_vitals(
                    mcp_server.PlayVitalsQueryInput(
                        project_path="proj",
                        app="prod",
                        metric_set="crash_rate",
                        start_date="2026-04-20",
                        end_date="2026-04-22",
                        dimensions=["versionCode"],
                    )
                )
            )
        assert out["ok"] is True
        assert out["package_name"] == "com.example.app"
        create_reporting.assert_called_once()
        assert query.call_args.args[1] == "com.example.app"
        assert query.call_args.kwargs["dimensions"] == ["versionCode"]

    def test_play_report_download_tool(self, tmp_path):
        _setup_project(tmp_path)
        session = MagicMock()
        raw = "Date,Value\n2026-04-20,3\n".encode("utf-16")
        with (
            patch("perfectdeckcli.mcp_server.play_store_api.create_storage_session", return_value=session),
            patch("perfectdeckcli.mcp_server.play_store_api.download_play_report_object", return_value=raw),
        ):
            out = _json(
                mcp_server.perfectdeck_download_play_report_file(
                    mcp_server.DownloadPlayReportFileInput(
                        bucket="pubsite_prod_rev_123",
                        object_name="stats/installs/report.csv",
                        max_rows=10,
                    )
                )
            )
        assert out["ok"] is True
        assert out["rows"][0]["Value"] == "3"
        assert out["content_bytes"] == len(raw)

    def test_app_store_custom_product_page_tools(self, tmp_path):
        _setup_project(tmp_path)
        client = MagicMock()
        client.create_custom_product_page.return_value = {"data": {"id": "cpp-1"}}
        client.create_custom_product_page_version.return_value = {"data": {"id": "cppv-1"}}
        client.create_custom_product_page_localization.return_value = {"data": {"id": "cppl-1"}}
        client.list_app_keywords.return_value = {"data": [{"id": "kw-1"}]}
        client.add_custom_product_page_search_keywords.return_value = {}
        client.remove_custom_product_page_search_keywords.return_value = {}
        client.delete_custom_product_page.return_value = {}
        with patch("perfectdeckcli.mcp_server.app_store_api.AppStoreConnectClient.from_key_file", return_value=client):
            page = _json(mcp_server.perfectdeck_create_app_store_custom_product_page(
                mcp_server.CreateAppStoreCustomProductPageInput(
                    project_path="proj",
                    app="prod",
                    name="Campaign",
                    **_app_store_auth_kwargs(),
                )
            ))
            version = _json(mcp_server.perfectdeck_create_app_store_custom_product_page_version(
                mcp_server.CreateAppStoreCustomProductPageVersionInput(
                    project_path="proj",
                    app="prod",
                    page_id="cpp-1",
                    deep_link="myapp://campaign",
                    **_app_store_auth_kwargs(),
                )
            ))
            loc = _json(mcp_server.perfectdeck_create_app_store_custom_product_page_localization(
                mcp_server.CreateAppStoreCustomProductPageLocalizationInput(
                    project_path="proj",
                    app="prod",
                    version_id="cppv-1",
                    locale="en-US",
                    promotional_text="Try it",
                    **_app_store_auth_kwargs(),
                )
            ))
            keywords = _json(mcp_server.perfectdeck_list_app_store_keywords(
                mcp_server.ListAppStoreKeywordsInput(
                    project_path="proj",
                    app="prod",
                    **_app_store_auth_kwargs(),
                )
            ))
            link = _json(mcp_server.perfectdeck_link_app_store_custom_product_page_keywords(
                mcp_server.LinkAppStoreCustomProductPageKeywordsInput(
                    project_path="proj",
                    app="prod",
                    localization_id="cppl-1",
                    keyword_ids=["kw-1"],
                    **_app_store_auth_kwargs(),
                )
            ))
            unlink = _json(mcp_server.perfectdeck_unlink_app_store_custom_product_page_keywords(
                mcp_server.UnlinkAppStoreCustomProductPageKeywordsInput(
                    project_path="proj",
                    app="prod",
                    localization_id="cppl-1",
                    keyword_ids=["kw-1"],
                    **_app_store_auth_kwargs(),
                )
            ))
            deleted = _json(mcp_server.perfectdeck_delete_app_store_custom_product_page(
                mcp_server.DeleteAppStoreCustomProductPageInput(
                    project_path="proj",
                    app="prod",
                    page_id="cpp-1",
                    **_app_store_auth_kwargs(),
                )
            ))
        assert page["response"]["data"]["id"] == "cpp-1"
        assert version["response"]["data"]["id"] == "cppv-1"
        assert loc["response"]["data"]["id"] == "cppl-1"
        assert keywords["response"]["data"][0]["id"] == "kw-1"
        assert link["ok"] is True
        assert unlink["ok"] is True
        assert deleted["ok"] is True
        client.create_custom_product_page.assert_called_once()
        client.create_custom_product_page_version.assert_called_once_with("cpp-1", deep_link="myapp://campaign")
        client.list_app_keywords.assert_called_once_with("1234567890", locale="en-US", platform="IOS", limit=200)
        client.add_custom_product_page_search_keywords.assert_called_once_with("cppl-1", ["kw-1"])
        client.remove_custom_product_page_search_keywords.assert_called_once_with("cppl-1", ["kw-1"])

    def test_app_store_experiment_tools(self, tmp_path):
        _setup_project(tmp_path)
        client = MagicMock()
        client.create_app_store_experiment.return_value = {"data": {"id": "exp-1"}}
        client.create_app_store_experiment_treatment.return_value = {"data": {"id": "treat-1"}}
        client.create_app_store_experiment_treatment_localization.return_value = {"data": {"id": "tl-1"}}
        client.update_app_store_experiment_treatment.return_value = {"data": {"id": "treat-1"}}
        client.delete_app_store_experiment_treatment.return_value = {}
        client.delete_app_store_experiment.return_value = {}
        with patch("perfectdeckcli.mcp_server.app_store_api.AppStoreConnectClient.from_key_file", return_value=client):
            exp = _json(mcp_server.perfectdeck_create_app_store_experiment(
                mcp_server.CreateAppStoreExperimentInput(
                    project_path="proj",
                    app="prod",
                    name="Screenshot test",
                    traffic_proportion=60,
                    **_app_store_auth_kwargs(),
                )
            ))
            treatment = _json(mcp_server.perfectdeck_create_app_store_experiment_treatment(
                mcp_server.CreateAppStoreExperimentTreatmentInput(
                    project_path="proj",
                    app="prod",
                    experiment_id="exp-1",
                    name="Treatment A",
                    **_app_store_auth_kwargs(),
                )
            ))
            loc = _json(mcp_server.perfectdeck_create_app_store_experiment_treatment_localization(
                mcp_server.CreateAppStoreExperimentTreatmentLocalizationInput(
                    project_path="proj",
                    app="prod",
                    treatment_id="treat-1",
                    locale="en-US",
                    **_app_store_auth_kwargs(),
                )
            ))
            updated_treatment = _json(mcp_server.perfectdeck_update_app_store_experiment_treatment(
                mcp_server.UpdateAppStoreExperimentTreatmentInput(
                    project_path="proj",
                    app="prod",
                    treatment_id="treat-1",
                    name="Treatment B",
                    **_app_store_auth_kwargs(),
                )
            ))
            deleted_treatment = _json(mcp_server.perfectdeck_delete_app_store_experiment_treatment(
                mcp_server.DeleteAppStoreExperimentTreatmentInput(
                    project_path="proj",
                    app="prod",
                    treatment_id="treat-1",
                    **_app_store_auth_kwargs(),
                )
            ))
            deleted_exp = _json(mcp_server.perfectdeck_delete_app_store_experiment(
                mcp_server.DeleteAppStoreExperimentInput(
                    project_path="proj",
                    app="prod",
                    experiment_id="exp-1",
                    **_app_store_auth_kwargs(),
                )
            ))
        assert exp["response"]["data"]["id"] == "exp-1"
        assert treatment["response"]["data"]["id"] == "treat-1"
        assert loc["response"]["data"]["id"] == "tl-1"
        assert updated_treatment["response"]["data"]["id"] == "treat-1"
        assert deleted_treatment["ok"] is True
        assert deleted_exp["ok"] is True
        assert client.create_app_store_experiment.call_args.kwargs["traffic_proportion"] == 60
        client.update_app_store_experiment_treatment.assert_called_once_with("treat-1", name="Treatment B", app_icon_name=None)

    def test_app_store_preview_upload_tools(self, tmp_path):
        _setup_project(tmp_path)
        client = MagicMock()
        with (
            patch("perfectdeckcli.mcp_server.app_store_api.AppStoreConnectClient.from_key_file", return_value=client),
            patch("perfectdeckcli.mcp_server.app_store_api.upload_previews", return_value={"ok": True, "uploaded": 1}) as upload_previews,
        ):
            custom = _json(mcp_server.perfectdeck_upload_app_store_custom_product_page_previews(
                mcp_server.UploadAppStoreCustomProductPagePreviewsInput(
                    project_path="proj",
                    app="prod",
                    localization_id="cppl-1",
                    preview_type="IPHONE_67",
                    file_paths=["/tmp/preview.mp4"],
                    mime_type="video/mp4",
                    **_app_store_auth_kwargs(),
                )
            ))
            experiment = _json(mcp_server.perfectdeck_upload_app_store_experiment_previews(
                mcp_server.UploadAppStoreExperimentPreviewsInput(
                    project_path="proj",
                    app="prod",
                    localization_id="tl-1",
                    preview_type="IPHONE_67",
                    file_paths=["/tmp/preview.mp4"],
                    **_app_store_auth_kwargs(),
                )
            ))
        assert custom["ok"] is True
        assert experiment["ok"] is True
        assert upload_previews.call_args_list[0].kwargs["target_type"] == "appCustomProductPageLocalizations"
        assert upload_previews.call_args_list[1].kwargs["target_type"] == "appStoreVersionExperimentTreatmentLocalizations"


# ======================================================================
# perfectdeck_list_section with jq filtering
# ======================================================================


class TestListSectionJqFiltering:
    def test_no_jq_returns_full_data(self, tmp_path):
        _setup_project(tmp_path)
        _set_play_data("prod", "en-US", {"title": "My App", "short_description": "Short"})
        _set_play_data("prod", "fr-FR", {"title": "Mon App"})

        out = _json(mcp_server.perfectdeck_list_section(
            mcp_server.ListSectionInput(
                project_path="proj", app="prod", store="play",
            )
        ))
        assert out["ok"] is True
        assert "global" in out["data"]
        assert "locales" in out["data"]
        assert "en-US" in out["data"]["locales"]
        assert "fr-FR" in out["data"]["locales"]

    def test_jq_select_global(self, tmp_path):
        _setup_project(tmp_path)
        _set_play_data("prod", "en-US", {"title": "My App"})

        out = _json(mcp_server.perfectdeck_list_section(
            mcp_server.ListSectionInput(
                project_path="proj", app="prod", store="play",
                jq=".global",
            )
        ))
        assert out["ok"] is True
        # .global returns the global dict (not the full envelope)
        assert isinstance(out["data"], dict)
        assert "locales" not in out["data"]

    def test_jq_map_values(self, tmp_path):
        _setup_project(tmp_path)
        _set_play_data("prod", "en-US", {"title": "English"})
        _set_play_data("prod", "fr-FR", {"title": "French"})

        out = _json(mcp_server.perfectdeck_list_section(
            mcp_server.ListSectionInput(
                project_path="proj", app="prod", store="play",
                jq=".locales | map_values(.title)",
            )
        ))
        assert out["ok"] is True
        assert out["data"]["en-US"] == "English"
        assert out["data"]["fr-FR"] == "French"

    def test_locales_filter(self, tmp_path):
        _setup_project(tmp_path)
        _set_play_data("prod", "en-US", {"title": "English"})
        _set_play_data("prod", "fr-FR", {"title": "French"})

        out = _json(mcp_server.perfectdeck_list_section(
            mcp_server.ListSectionInput(
                project_path="proj", app="prod", store="play",
                locales=["en-US"],
            )
        ))
        assert out["ok"] is True
        assert "en-US" in out["data"]["locales"]
        assert "fr-FR" not in out["data"]["locales"]

    def test_locales_filter_combined_with_jq(self, tmp_path):
        _setup_project(tmp_path)
        _set_play_data("prod", "en-US", {"title": "English"})
        _set_play_data("prod", "fr-FR", {"title": "French"})

        out = _json(mcp_server.perfectdeck_list_section(
            mcp_server.ListSectionInput(
                project_path="proj", app="prod", store="play",
                locales=["en-US"],
                jq=".locales | map_values(.title)",
            )
        ))
        assert out["ok"] is True
        assert out["data"] == {"en-US": "English"}

    def test_invalid_jq_expression(self, tmp_path):
        _setup_project(tmp_path)
        _set_play_data("prod", "en-US", {"title": "My App"})

        out = _json(mcp_server.perfectdeck_list_section(
            mcp_server.ListSectionInput(
                project_path="proj", app="prod", store="play",
                jq=".invalid[[[",
            )
        ))
        assert out["ok"] is False
        assert "error" in out
        assert "jq" in out["error"].lower()


# ======================================================================
# perfectdeck_validate_listing
# ======================================================================


class TestValidateListingTool:
    def test_valid_play_listing(self, tmp_path):
        _setup_project(tmp_path)
        _set_play_data("prod", "en-US", {"title": "My App"})

        out = _json(mcp_server.perfectdeck_validate_listing(
            mcp_server.ValidateListingInput(
                project_path="proj", app="prod", store="play",
            )
        ))
        assert out["ok"] is True
        assert out["errors"] == []

    def test_invalid_play_title(self, tmp_path):
        _setup_project(tmp_path)
        _set_play_data("prod", "en-US", {"title": "A" * 31})

        out = _json(mcp_server.perfectdeck_validate_listing(
            mcp_server.ValidateListingInput(
                project_path="proj", app="prod", store="play",
            )
        ))
        assert out["ok"] is False
        assert len(out["errors"]) == 1
        assert out["errors"][0]["field"] == "title"
        assert out["errors"][0]["limit"] == 30

    def test_valid_app_store_listing(self, tmp_path):
        _setup_project(tmp_path)
        _set_app_store_data("prod", "en-US", {"app_name": "My App"})

        out = _json(mcp_server.perfectdeck_validate_listing(
            mcp_server.ValidateListingInput(
                project_path="proj", app="prod", store="app_store",
            )
        ))
        assert out["ok"] is True

    def test_invalid_app_store_multiple_errors(self, tmp_path):
        _setup_project(tmp_path)
        _set_app_store_data("prod", "en-US", {
            "app_name": "A" * 31,
            "subtitle": "S" * 31,
        })

        out = _json(mcp_server.perfectdeck_validate_listing(
            mcp_server.ValidateListingInput(
                project_path="proj", app="prod", store="app_store",
            )
        ))
        assert out["ok"] is False
        assert len(out["errors"]) == 2

    def test_validate_with_locale_filter(self, tmp_path):
        _setup_project(tmp_path)
        _set_play_data("prod", "en-US", {"title": "A" * 31})  # over limit
        _set_play_data("prod", "fr-FR", {"title": "OK"})

        # Only validate fr-FR
        out = _json(mcp_server.perfectdeck_validate_listing(
            mcp_server.ValidateListingInput(
                project_path="proj", app="prod", store="play",
                locales=["fr-FR"],
            )
        ))
        assert out["ok"] is True

    def test_validate_empty_listing_passes(self, tmp_path):
        _setup_project(tmp_path)
        out = _json(mcp_server.perfectdeck_validate_listing(
            mcp_server.ValidateListingInput(
                project_path="proj", app="prod", store="play",
            )
        ))
        assert out["ok"] is True


# ======================================================================
# perfectdeck_diff_play_listing (mocked remote)
# ======================================================================


class TestDiffPlayListingTool:
    @patch("perfectdeckcli.mcp_server._fetch_play_remote")
    def test_diff_detects_changes(self, mock_fetch, tmp_path):
        _setup_project(tmp_path)
        _set_play_data("prod", "en-US", {"title": "Local Title"})

        mock_fetch.return_value = {
            "global": {"default_language": "en-US"},
            "locales": {
                "en-US": {"title": "Remote Title", "shortDescription": "", "fullDescription": ""},
            },
        }

        out = _json(mcp_server.perfectdeck_diff_play_listing(
            mcp_server.FetchPlayListingInput(
                project_path="proj", app="prod",
                package_name="com.example.app",
            )
        ))
        assert out["ok"] is True
        assert out["locales"]["en-US"]["same"] is False
        assert "en-US" in out["fetched_locales"]

    @patch("perfectdeckcli.mcp_server._fetch_play_remote")
    def test_diff_no_changes(self, mock_fetch, tmp_path):
        _setup_project(tmp_path)
        _set_play_data("prod", "en-US", {"title": "Same"})

        mock_fetch.return_value = {
            "global": {},
            "locales": {
                "en-US": {"title": "Same", "shortDescription": "", "fullDescription": ""},
            },
        }

        out = _json(mcp_server.perfectdeck_diff_play_listing(
            mcp_server.FetchPlayListingInput(
                project_path="proj", app="prod",
                package_name="com.example.app",
            )
        ))
        assert out["locales"]["en-US"]["same"] is True


# ======================================================================
# perfectdeck_sync_play_listing (mocked remote)
# ======================================================================


class TestSyncPlayListingTool:
    @patch("perfectdeckcli.mcp_server._fetch_play_remote")
    def test_sync_imports_data(self, mock_fetch, tmp_path):
        _setup_project(tmp_path)
        mock_fetch.return_value = {
            "global": {"default_language": "en-US"},
            "locales": {
                "en-US": {"title": "Synced", "shortDescription": "S", "fullDescription": "F"},
            },
        }

        out = _json(mcp_server.perfectdeck_sync_play_listing(
            mcp_server.FetchPlayListingInput(
                project_path="proj", app="prod",
                package_name="com.example.app",
            )
        ))
        assert out["ok"] is True
        assert "en-US" in out["imported_locales"]

        # Verify data was stored
        section = _json(mcp_server.perfectdeck_list_section(
            mcp_server.ListSectionInput(
                project_path="proj", app="prod", store="play", locale="en-US",
            )
        ))
        assert section["data"]["title"] == "Synced"

    @patch("perfectdeckcli.mcp_server._fetch_play_remote")
    def test_sync_imports_products_and_subscriptions(self, mock_fetch, tmp_path):
        _setup_project(tmp_path)
        mock_fetch.return_value = {
            "global": {"default_language": "en-US"},
            "locales": {
                "en-US": {"title": "App", "shortDescription": "S", "fullDescription": "F"},
            },
            "products": {
                "credits_3": {
                    "type": "consumable",
                    "default_price": {"currency": "USD", "price": 0.99},
                    "localizations": {"en-US": {"title": "3 Credits"}},
                }
            },
            "subscriptions": {
                "premium": {
                    "localizations": {"en-US": {"title": "Premium"}},
                    "base_plans": {"monthly": {"pricing": {"US": {"currency": "USD", "price": 7.99}}}},
                }
            },
        }

        out = _json(mcp_server.perfectdeck_sync_play_listing(
            mcp_server.FetchPlayListingInput(
                project_path="proj", app="prod",
                package_name="com.example.app",
            )
        ))
        assert out["ok"] is True
        assert out["products_count"] == 1
        assert out["subscriptions_count"] == 1

        # Verify products/subscriptions in list_section
        section = _json(mcp_server.perfectdeck_list_section(
            mcp_server.ListSectionInput(
                project_path="proj", app="prod", store="play",
            )
        ))
        assert "products" in section["data"]
        assert "credits_3" in section["data"]["products"]
        assert "subscriptions" in section["data"]
        assert "premium" in section["data"]["subscriptions"]


# ======================================================================
# perfectdeck_diff_app_store_listing (mocked remote)
# ======================================================================


class TestDiffAppStoreListingTool:
    @patch("perfectdeckcli.mcp_server._fetch_app_store_remote")
    def test_diff_new_locale(self, mock_fetch, tmp_path):
        _setup_project(tmp_path)
        mock_fetch.return_value = {
            "global": {"primary_locale": "en-US"},
            "locales": {
                "en-US": {"app_name": "My App"},
                "ja": {"app_name": "My App JP"},
            },
        }

        out = _json(mcp_server.perfectdeck_diff_app_store_listing(
            mcp_server.FetchAppStoreListingInput(
                project_path="proj", app="prod",
                app_id="12345", key_id="KEY", issuer_id="ISS",
                private_key_path="/fake/key.p8",
            )
        ))
        assert out["ok"] is True
        assert "ja" in out["summary"]["new_locales"]


# ======================================================================
# perfectdeck_sync_app_store_listing (mocked remote)
# ======================================================================


class TestSyncAppStoreListingTool:
    @patch("perfectdeckcli.mcp_server._fetch_app_store_remote")
    def test_sync_imports(self, mock_fetch, tmp_path):
        _setup_project(tmp_path)
        mock_fetch.return_value = {
            "global": {"primary_locale": "en-US", "bundle_id": "com.example.app"},
            "locales": {
                "en-US": {"app_name": "Imported", "description": "Full desc"},
            },
        }

        out = _json(mcp_server.perfectdeck_sync_app_store_listing(
            mcp_server.FetchAppStoreListingInput(
                project_path="proj", app="prod",
                app_id="12345", key_id="KEY", issuer_id="ISS",
                private_key_path="/fake/key.p8",
            )
        ))
        assert out["ok"] is True
        assert "en-US" in out["imported_locales"]

    @patch("perfectdeckcli.mcp_server._fetch_app_store_remote")
    def test_sync_imports_products_and_subscriptions(self, mock_fetch, tmp_path):
        _setup_project(tmp_path)
        mock_fetch.return_value = {
            "global": {"primary_locale": "en-US", "bundle_id": "com.example.app"},
            "locales": {
                "en-US": {"app_name": "App", "description": "Desc"},
            },
            "products": {
                "com.example.credits": {
                    "type": "consumable",
                    "localizations": {"en-US": {"name": "3 Credits"}},
                }
            },
            "subscriptions": {
                "com.example.premium": {
                    "group_name": "Premium",
                    "localizations": {"en-US": {"name": "Premium Monthly"}},
                }
            },
        }

        out = _json(mcp_server.perfectdeck_sync_app_store_listing(
            mcp_server.FetchAppStoreListingInput(
                project_path="proj", app="prod",
                app_id="12345", key_id="KEY", issuer_id="ISS",
                private_key_path="/fake/key.p8",
            )
        ))
        assert out["ok"] is True
        assert out["products_count"] == 1
        assert out["subscriptions_count"] == 1

        # Verify stored data
        section = _json(mcp_server.perfectdeck_list_section(
            mcp_server.ListSectionInput(
                project_path="proj", app="prod", store="app_store",
            )
        ))
        assert "products" in section["data"]
        assert "com.example.credits" in section["data"]["products"]
        assert "subscriptions" in section["data"]
        assert "com.example.premium" in section["data"]["subscriptions"]


# ======================================================================
# perfectdeck_push_play_listing (mocked API)
# ======================================================================


class TestPushPlayListingTool:
    @patch("perfectdeckcli.mcp_server.play_store_api.push_listings")
    @patch("perfectdeckcli.mcp_server.play_store_api.create_service")
    def test_push_basic(self, mock_create_service, mock_push, tmp_path):
        _setup_project(tmp_path)
        _set_play_data("prod", "en-US", {"title": "My App", "short_description": "Short"})

        mock_create_service.return_value = MagicMock()
        mock_push.return_value = {"ok": True, "updated_locales": ["en-US"], "committed": True}

        out = _json(mcp_server.perfectdeck_push_play_listing(
            mcp_server.PushPlayListingInput(
                project_path="proj", app="prod",
                package_name="com.example.app",
            )
        ))
        assert out["ok"] is True
        mock_push.assert_called_once()
        # Verify push was called with API-formatted data
        call_kwargs = mock_push.call_args
        locales_data = call_kwargs.kwargs.get("locales_data") or call_kwargs[1].get("locales_data") or call_kwargs[0][2]
        assert "en-US" in locales_data

    @patch("perfectdeckcli.mcp_server.play_store_api.push_listings")
    @patch("perfectdeckcli.mcp_server.play_store_api.create_service")
    def test_push_with_release_notes(self, mock_create_service, mock_push, tmp_path):
        _setup_project(tmp_path)
        _set_play_data("prod", "en-US", {"title": "My App"})
        # Store release notes in the dedicated system
        svc = mcp_server._router().service_for("proj")
        svc.set_release_notes("prod", "play", "2.0.0", "en-US", "Bug fixes")

        mock_create_service.return_value = MagicMock()
        mock_push.return_value = {"ok": True, "updated_locales": ["en-US"], "committed": True}

        out = _json(mcp_server.perfectdeck_push_play_listing(
            mcp_server.PushPlayListingInput(
                project_path="proj", app="prod",
                package_name="com.example.app",
                release_notes_version="2.0.0",
                version_code=42,
            )
        ))
        assert out["ok"] is True
        call_kwargs = mock_push.call_args
        # release_notes should have been passed
        release_notes = call_kwargs.kwargs.get("release_notes") or call_kwargs[1].get("release_notes")
        assert release_notes is not None


# ======================================================================
# perfectdeck_push_play_release_notes (mocked API)
# ======================================================================


class TestPushPlayReleaseNotesTool:
    @patch("perfectdeckcli.mcp_server.play_store_api.update_release_notes")
    @patch("perfectdeckcli.mcp_server.play_store_api.create_service")
    def test_push_release_notes(self, mock_create_service, mock_update, tmp_path):
        _setup_project(tmp_path)
        svc = mcp_server._router().service_for("proj")
        svc.set_release_notes("prod", "play", "2.0.0", "en-US", "New features")

        mock_create_service.return_value = MagicMock()
        mock_update.return_value = {"ok": True, "track": "production", "version_code": 42}

        out = _json(mcp_server.perfectdeck_push_play_release_notes(
            mcp_server.PushPlayReleaseNotesInput(
                project_path="proj", app="prod",
                package_name="com.example.app",
                version_code=42,
                release_notes_version="2.0.0",
            )
        ))
        assert out["ok"] is True


# ======================================================================
# perfectdeck_push_play_screenshots (mocked API)
# ======================================================================


class TestPushPlayScreenshotsTool:
    @patch("perfectdeckcli.mcp_server.play_store_api.upload_screenshots")
    @patch("perfectdeckcli.mcp_server.play_store_api.create_service")
    def test_push_screenshots(self, mock_create_service, mock_upload, tmp_path):
        mock_create_service.return_value = MagicMock()
        mock_upload.return_value = {"ok": True, "uploaded": 2, "skipped": 0}

        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        out = _json(mcp_server.perfectdeck_push_play_screenshots(
            mcp_server.PushPlayScreenshotsInput(
                package_name="com.example.app",
                locale="en-US",
                image_type="phoneScreenshots",
                file_paths=["/fake/screen1.png", "/fake/screen2.png"],
            )
        ))
        assert out["ok"] is True
        assert out["uploaded"] == 2


# ======================================================================
# perfectdeck_publish_play_bundle (mocked API)
# ======================================================================


class TestPublishPlayBundleTool:
    @patch("perfectdeckcli.mcp_server.play_store_api.publish_bundle")
    @patch("perfectdeckcli.mcp_server.play_store_api.create_service")
    def test_publish_basic(self, mock_create_service, mock_publish, tmp_path):
        _setup_project(tmp_path)
        mock_create_service.return_value = MagicMock()
        mock_publish.return_value = {"ok": True, "version_code": 42, "track": "internal"}

        out = _json(mcp_server.perfectdeck_publish_play_bundle(
            mcp_server.PublishPlayBundleInput(
                project_path="proj", app="prod",
                package_name="com.example.app",
                bundle_path="/fake/app.aab",
            )
        ))
        assert out["ok"] is True
        assert out["version_code"] == 42

    @patch("perfectdeckcli.mcp_server.play_store_api.publish_bundle")
    @patch("perfectdeckcli.mcp_server.play_store_api.create_service")
    def test_publish_with_release_notes(self, mock_create_service, mock_publish, tmp_path):
        _setup_project(tmp_path)
        svc = mcp_server._router().service_for("proj")
        svc.set_release_notes("prod", "play", "2.0.0", "en-US", "Bug fixes")

        mock_create_service.return_value = MagicMock()
        mock_publish.return_value = {"ok": True, "version_code": 43, "track": "internal"}

        out = _json(mcp_server.perfectdeck_publish_play_bundle(
            mcp_server.PublishPlayBundleInput(
                project_path="proj", app="prod",
                package_name="com.example.app",
                bundle_path="/fake/app.aab",
                release_notes_version="2.0.0",
                locales=["en-US"],
            )
        ))
        assert out["ok"] is True
        # Verify release_notes were passed
        call_kwargs = mock_publish.call_args
        rn = call_kwargs.kwargs.get("release_notes") or call_kwargs[1].get("release_notes")
        assert rn is not None


# ======================================================================
# perfectdeck_sync_play_products (mocked API)
# ======================================================================


class TestSyncPlayProductsTool:
    @patch("perfectdeckcli.mcp_server.play_store_api.ensure_managed_products")
    @patch("perfectdeckcli.mcp_server.play_store_api.create_service")
    def test_sync_products(self, mock_create_service, mock_ensure, tmp_path):
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mock_create_service.return_value = MagicMock()
        mock_ensure.return_value = {"ok": True, "created": ["sku1"], "updated": []}

        out = _json(mcp_server.perfectdeck_sync_play_products(
            mcp_server.SyncPlayProductsInput(
                package_name="com.example.app",
                products=[{"sku": "sku1", "listings": {}}],
            )
        ))
        assert out["ok"] is True
        assert out["created"] == ["sku1"]


# ======================================================================
# perfectdeck_sync_play_pricing (mocked API)
# ======================================================================


class TestSyncPlayPricingTool:
    @patch("perfectdeckcli.mcp_server.play_store_api.apply_regional_pricing")
    @patch("perfectdeckcli.mcp_server.play_store_api.create_service")
    def test_sync_pricing(self, mock_create_service, mock_pricing, tmp_path):
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mock_create_service.return_value = MagicMock()
        mock_pricing.return_value = {"ok": True, "sku": "sku1", "regions_applied": 2}

        out = _json(mcp_server.perfectdeck_sync_play_pricing(
            mcp_server.SyncPlayPricingInput(
                package_name="com.example.app",
                sku="sku1",
                regional_prices={
                    "US": {"currency": "USD", "price": 2.99},
                    "CA": {"currency": "CAD", "price": 3.99},
                },
            )
        ))
        assert out["ok"] is True
        assert out["regions_applied"] == 2


# ======================================================================
# perfectdeck_sync_play_subscription_pricing (mocked API)
# ======================================================================


class TestSyncPlaySubscriptionPricingTool:
    @patch("perfectdeckcli.mcp_server.play_store_api.apply_subscription_regional_pricing")
    @patch("perfectdeckcli.mcp_server.play_store_api.create_service")
    def test_sync_sub_pricing(self, mock_create_service, mock_pricing, tmp_path):
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mock_create_service.return_value = MagicMock()
        mock_pricing.return_value = {"ok": True, "subscription_id": "premium", "regions_applied": 1}

        out = _json(mcp_server.perfectdeck_sync_play_subscription_pricing(
            mcp_server.SyncPlaySubscriptionPricingInput(
                package_name="com.example.app",
                subscription_id="premium",
                base_plan_id="monthly",
                regional_prices={"US": {"currency": "USD", "price": 9.99}},
            )
        ))
        assert out["ok"] is True
        assert out["subscription_id"] == "premium"


# ======================================================================
# perfectdeck_push_app_store_listing (mocked API)
# ======================================================================


class TestPushAppStoreListingTool:
    @patch("perfectdeckcli.mcp_server.app_store_api.push_listings")
    @patch("perfectdeckcli.mcp_server.app_store_api.AppStoreConnectClient.from_key_file")
    def test_push_basic(self, mock_from_key, mock_push, tmp_path):
        _setup_project(tmp_path)
        _set_app_store_data("prod", "en-US", {"app_name": "My App", "description": "Full"})

        mock_from_key.return_value = MagicMock()
        mock_push.return_value = {"ok": True, "updated_locales": ["en-US"], "created_locales": []}

        out = _json(mcp_server.perfectdeck_push_app_store_listing(
            mcp_server.PushAppStoreListingInput(
                project_path="proj", app="prod",
                app_id="12345", key_id="KEY", issuer_id="ISS",
                private_key_path="/fake/key.p8",
                version_string="2.0.0",
            )
        ))
        assert out["ok"] is True

    @patch("perfectdeckcli.mcp_server.app_store_api.push_listings")
    @patch("perfectdeckcli.mcp_server.app_store_api.AppStoreConnectClient.from_key_file")
    def test_push_dry_run(self, mock_from_key, mock_push, tmp_path):
        _setup_project(tmp_path)
        _set_app_store_data("prod", "en-US", {"app_name": "My App"})

        mock_client = MagicMock()
        mock_from_key.return_value = mock_client
        mock_push.return_value = {"ok": True, "updated_locales": [], "created_locales": []}

        out = _json(mcp_server.perfectdeck_push_app_store_listing(
            mcp_server.PushAppStoreListingInput(
                project_path="proj", app="prod",
                app_id="12345", key_id="KEY", issuer_id="ISS",
                private_key_path="/fake/key.p8",
                version_string="2.0.0",
                dry_run=True,
            )
        ))
        assert out["ok"] is True
        mock_from_key.assert_called_once_with(
            key_id="KEY", issuer_id="ISS",
            private_key_path="/fake/key.p8",
            dry_run=True,
        )


# ======================================================================
# perfectdeck_create_app_store_version (mocked API)
# ======================================================================


class TestCreateAppStoreVersionTool:
    @patch("perfectdeckcli.mcp_server.app_store_api.AppStoreConnectClient.from_key_file")
    def test_create_version(self, mock_from_key, tmp_path):
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mock_client = MagicMock()
        mock_client.create_app_store_version.return_value = {
            "id": "ver-new", "version_string": "3.0.0", "state": "PREPARE_FOR_SUBMISSION",
        }
        mock_from_key.return_value = mock_client

        out = _json(mcp_server.perfectdeck_create_app_store_version(
            mcp_server.CreateAppStoreVersionInput(
                app_id="12345", key_id="KEY", issuer_id="ISS",
                private_key_path="/fake/key.p8",
                version_string="3.0.0",
            )
        ))
        assert out["ok"] is True
        assert out["version_string"] == "3.0.0"


# ======================================================================
# perfectdeck_push_app_store_screenshots (mocked API)
# ======================================================================


class TestPushAppStoreScreenshotsTool:
    @patch("perfectdeckcli.mcp_server.app_store_api.upload_screenshots")
    @patch("perfectdeckcli.mcp_server.app_store_api.AppStoreConnectClient.from_key_file")
    def test_push_screenshots(self, mock_from_key, mock_upload, tmp_path):
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mock_client = MagicMock()
        mock_client.get_app_store_version_id.return_value = "ver-1"
        mock_client.find_app_store_version_localization.return_value = "vloc-1"
        mock_from_key.return_value = mock_client
        mock_upload.return_value = {"ok": True, "uploaded": 1, "deleted": 0}

        out = _json(mcp_server.perfectdeck_push_app_store_screenshots(
            mcp_server.PushAppStoreScreenshotsInput(
                app_id="12345", key_id="KEY", issuer_id="ISS",
                private_key_path="/fake/key.p8",
                version_string="2.0.0",
                locale="en-US",
                display_type="APP_IPHONE_67",
                file_paths=["/fake/screen.png"],
            )
        ))
        assert out["ok"] is True

    @patch("perfectdeckcli.mcp_server.app_store_api.upload_screenshots")
    @patch("perfectdeckcli.mcp_server.app_store_api.AppStoreConnectClient.from_key_file")
    def test_push_screenshots_creates_localization(self, mock_from_key, mock_upload, tmp_path):
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mock_client = MagicMock()
        mock_client.get_app_store_version_id.return_value = "ver-1"
        mock_client.find_app_store_version_localization.return_value = None  # not found
        mock_client.create_app_store_version_localization.return_value = "vloc-new"
        mock_from_key.return_value = mock_client
        mock_upload.return_value = {"ok": True, "uploaded": 1, "deleted": 0}

        out = _json(mcp_server.perfectdeck_push_app_store_screenshots(
            mcp_server.PushAppStoreScreenshotsInput(
                app_id="12345", key_id="KEY", issuer_id="ISS",
                private_key_path="/fake/key.p8",
                version_string="2.0.0",
                locale="ja",
                display_type="APP_IPHONE_67",
                file_paths=["/fake/screen.png"],
            )
        ))
        assert out["ok"] is True
        mock_client.create_app_store_version_localization.assert_called_once()


# ======================================================================
# perfectdeck_sync_app_store_iap (mocked API)
# ======================================================================


class TestSyncAppStoreIapTool:
    @patch("perfectdeckcli.mcp_server.app_store_api.sync_iap_localizations")
    @patch("perfectdeckcli.mcp_server.app_store_api.AppStoreConnectClient.from_key_file")
    def test_sync_iap(self, mock_from_key, mock_sync, tmp_path):
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mock_from_key.return_value = MagicMock()
        mock_sync.return_value = {"ok": True, "created": 1, "updated": 0, "missing_products": []}

        out = _json(mcp_server.perfectdeck_sync_app_store_iap(
            mcp_server.SyncAppStoreIapInput(
                app_id="12345", key_id="KEY", issuer_id="ISS",
                private_key_path="/fake/key.p8",
                products=[{
                    "product_id": "credits",
                    "localizations": {"en-US": {"name": "Credits", "description": "Buy"}},
                }],
            )
        ))
        assert out["ok"] is True
        assert out["created"] == 1


# ======================================================================
# perfectdeck_sync_app_store_subscriptions (mocked API)
# ======================================================================


class TestSyncAppStoreSubscriptionsTool:
    @patch("perfectdeckcli.mcp_server.app_store_api.sync_subscription_localizations")
    @patch("perfectdeckcli.mcp_server.app_store_api.AppStoreConnectClient.from_key_file")
    def test_sync_subscriptions(self, mock_from_key, mock_sync, tmp_path):
        mcp_server.router = ProjectListingRouter(root_folder=tmp_path)
        mock_from_key.return_value = MagicMock()
        mock_sync.return_value = {"ok": True, "created": 2, "updated": 0, "missing_subscriptions": []}

        out = _json(mcp_server.perfectdeck_sync_app_store_subscriptions(
            mcp_server.SyncAppStoreSubscriptionsInput(
                app_id="12345", key_id="KEY", issuer_id="ISS",
                private_key_path="/fake/key.p8",
                subscriptions=[{
                    "product_id": "premium",
                    "localizations": {
                        "en-US": {"name": "Premium", "description": "Access all"},
                        "fr-FR": {"name": "Premium", "description": "Acc\u00e9dez \u00e0 tout"},
                    },
                }],
            )
        ))
        assert out["ok"] is True
        assert out["created"] == 2


# ======================================================================
# Pydantic input validation
# ======================================================================


class TestInputValidation:
    def test_validate_listing_input_rejects_extra_fields(self):
        with pytest.raises(Exception):
            mcp_server.ValidateListingInput(
                project_path="proj", app="prod", store="play",
                extra_field="bad",
            )

    def test_validate_listing_input_requires_app(self):
        with pytest.raises(Exception):
            mcp_server.ValidateListingInput(project_path="proj", store="play")

    def test_push_play_input_strips_whitespace(self):
        inp = mcp_server.PushPlayListingInput(
            project_path="  proj  ", app="  prod  ",
            package_name="  com.example.app  ",
        )
        assert inp.project_path == "proj"
        assert inp.app == "prod"
        assert inp.package_name == "com.example.app"

    def test_store_name_must_be_valid(self):
        with pytest.raises(Exception):
            mcp_server.ValidateListingInput(
                project_path="proj", app="prod", store="unknown_store",
            )

    def test_fetch_play_input_defaults(self):
        inp = mcp_server.FetchPlayListingInput(
            app="prod", package_name="com.example.app",
        )
        assert inp.project_path == "."
        assert inp.credentials_path is None
        assert inp.locales is None

    def test_push_app_store_input_defaults(self):
        inp = mcp_server.PushAppStoreListingInput(
            app="prod", app_id="12345", key_id="KEY",
            issuer_id="ISS", private_key_path="/key.p8",
            version_string="2.0.0",
        )
        assert inp.platform == "IOS"
        assert inp.only_whats_new is False
        assert inp.dry_run is False

    def test_publish_bundle_input_defaults(self):
        inp = mcp_server.PublishPlayBundleInput(
            app="prod", package_name="com.example.app",
            bundle_path="/app.aab",
        )
        assert inp.track == "internal"
        assert inp.status == "draft"
        assert inp.mapping_path is None
