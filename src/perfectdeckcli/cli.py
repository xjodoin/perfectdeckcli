from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Any, Sequence, cast

from . import app_store as app_store_api
from . import play_store as play_store_api
from . import store_api_coverage
from .models import StoreName
from .service import ListingService
from .storage import FileStorageBackend


def _json_or_string(raw: str, parse_json: bool) -> Any:
    if not parse_json:
        return raw
    return json.loads(raw)


def _csv(raw: str | None) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def _json_object(raw: str | None, *, option: str) -> dict[str, Any] | None:
    if raw is None:
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"{option} must be a JSON object.")
    return parsed


def _require_write_confirmation(method: str, yes: bool, *, command: str) -> None:
    if method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return
    if not yes:
        raise ValueError(f"{command} with method {method.upper()} can mutate store state; pass --yes to confirm.")


def _resolve_app_store_cli_credentials(
    service: ListingService,
    app: str,
    app_id: str | None,
    key_id: str | None,
    issuer_id: str | None,
    private_key_path: str | None,
) -> tuple[str, str, str, str]:
    stored = service.get_credentials(app, "app_store")
    resolved_app_id = app_id or stored.get("app_id")
    resolved_key_id = key_id or stored.get("key_id")
    resolved_issuer_id = issuer_id or stored.get("issuer_id")
    resolved_private_key_path = private_key_path or stored.get("private_key_path")
    missing = [
        name for name, value in {
            "app_id": resolved_app_id,
            "key_id": resolved_key_id,
            "issuer_id": resolved_issuer_id,
            "private_key_path": resolved_private_key_path,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Missing App Store credentials: {', '.join(missing)}")
    return (
        str(resolved_app_id),
        str(resolved_key_id),
        str(resolved_issuer_id),
        str(resolved_private_key_path),
    )


def _resolve_play_cli_credentials(
    service: ListingService,
    app: str | None,
    package_name: str | None,
    credentials_path: str | None,
) -> tuple[str, str | None]:
    if not app:
        if not package_name:
            raise ValueError("--package-name is required when --app is omitted")
        return package_name, credentials_path
    stored = service.get_credentials(app, "play")
    resolved_package = package_name or stored.get("package_name")
    resolved_credentials = credentials_path if credentials_path is not None else stored.get("credentials_path")
    if not resolved_package:
        raise ValueError("Missing Play package_name. Pass --package-name or sync/store credentials first.")
    return str(resolved_package), resolved_credentials


def _add_app_store_auth_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--app-id", help="App Store app ID. Falls back to stored credentials.")
    parser.add_argument("--key-id", help="App Store Connect API key ID. Falls back to stored credentials.")
    parser.add_argument("--issuer-id", help="App Store Connect issuer ID. Falls back to stored credentials.")
    parser.add_argument("--private-key-path", help="Path to .p8 key. Falls back to stored credentials.")


def _add_play_auth_args(parser: argparse.ArgumentParser, *, app_required: bool = False) -> None:
    parser.add_argument("--app", required=app_required, help="Local app id for stored credential resolution.")
    parser.add_argument("--package-name", help="Android package name. Falls back to stored credentials when --app is set.")
    parser.add_argument("--credentials-path", help="Service account JSON path. Falls back to stored credentials or PLAY_SERVICE_ACCOUNT_JSON.")


def _parsed_gzip_result(content: bytes, *, max_rows: int, include_text: bool, include_base64: bool) -> dict[str, Any]:
    parsed = app_store_api.parse_gzip_tabular_report(content, max_rows=max_rows)
    result: dict[str, Any] = {
        "ok": True,
        "columns": parsed["columns"],
        "rows": parsed["rows"],
        "row_count": parsed["row_count"],
        "content_bytes": len(content),
    }
    if include_text:
        result["text"] = parsed["text"]
    if include_base64:
        result["content_base64"] = base64.b64encode(content).decode("ascii")
    return result


def _app_store_client_from_cli(
    service: ListingService,
    args: argparse.Namespace,
) -> tuple[str, app_store_api.AppStoreConnectClient]:
    app_id, key_id, issuer_id, private_key_path = _resolve_app_store_cli_credentials(
        service,
        args.app,
        args.app_id,
        args.key_id,
        args.issuer_id,
        args.private_key_path,
    )
    service.save_credentials(args.app, "app_store", {
        "app_id": app_id,
        "key_id": key_id,
        "issuer_id": issuer_id,
        "private_key_path": private_key_path,
    })
    return app_id, app_store_api.AppStoreConnectClient.from_key_file(key_id, issuer_id, private_key_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="perfectdeckcli: manage Play Store and App Store listing elements.",
    )
    parser.add_argument("--file", type=Path, default=Path("listings.yaml"), help="Listing data file path.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    get_parser = subparsers.add_parser("get", help="Read one key from global or locale section.")
    get_parser.add_argument("--app", required=True)
    get_parser.add_argument("--store", required=True, choices=["play", "app_store"])
    get_parser.add_argument("--key", required=True, help="Dotted key path, e.g. metadata.title")
    get_parser.add_argument("--locale", help="Locale key. If omitted, uses global section.")

    set_parser = subparsers.add_parser("set", help="Set one key on global or locale section.")
    set_parser.add_argument("--app", required=True)
    set_parser.add_argument("--store", required=True, choices=["play", "app_store"])
    set_parser.add_argument("--key", required=True)
    set_parser.add_argument("--value", required=True)
    set_parser.add_argument("--json-value", action="store_true", help="Parse --value as JSON.")
    set_parser.add_argument("--locale")

    delete_parser = subparsers.add_parser("delete", help="Delete one key from global or locale section.")
    delete_parser.add_argument("--app", required=True)
    delete_parser.add_argument("--store", required=True, choices=["play", "app_store"])
    delete_parser.add_argument("--key", required=True)
    delete_parser.add_argument("--locale")

    upsert_parser = subparsers.add_parser("upsert-locale", help="Merge or replace an entire locale payload.")
    upsert_parser.add_argument("--app", required=True)
    upsert_parser.add_argument("--store", required=True, choices=["play", "app_store"])
    upsert_parser.add_argument("--locale", required=True)
    upsert_parser.add_argument("--data", required=True, help='JSON object string, e.g. {"title":"..."}')
    upsert_parser.add_argument("--replace", action="store_true", help="Replace locale content instead of merge.")

    list_parser = subparsers.add_parser("list", help="List the whole store section or one locale payload.")
    list_parser.add_argument("--app", required=True)
    list_parser.add_argument("--store", required=True, choices=["play", "app_store"])
    list_parser.add_argument("--locale")

    init_parser = subparsers.add_parser("init", help="Initialize listing skeleton for an app.")
    init_parser.add_argument("--app", required=True)
    init_parser.add_argument("--stores", default="play,app_store", help="Comma-separated stores.")
    init_parser.add_argument("--locales", help="Comma-separated locale list.")
    init_parser.add_argument("--baseline-locale", help="Baseline/source locale for translation tracking.")
    init_parser.add_argument("--overwrite", action="store_true")

    baseline_parser = subparsers.add_parser("set-baseline-language", help="Set baseline language for one app/store.")
    baseline_parser.add_argument("--app", required=True)
    baseline_parser.add_argument("--store", required=True, choices=["play", "app_store"])
    baseline_parser.add_argument("--locale", required=True)

    bump_parser = subparsers.add_parser("bump-version", help="Manually bump listing version.")
    bump_parser.add_argument("--app", required=True)
    bump_parser.add_argument("--store", required=True, choices=["play", "app_store"])
    bump_parser.add_argument("--reason", default="manual-bump")
    bump_parser.add_argument("--source-locale")

    mark_parser = subparsers.add_parser("mark-language-updated", help="Mark one language updated at current version.")
    mark_parser.add_argument("--app", required=True)
    mark_parser.add_argument("--store", required=True, choices=["play", "app_store"])
    mark_parser.add_argument("--locale", required=True)

    status_parser = subparsers.add_parser("status", help="Show translation update status.")
    status_parser.add_argument("--app", required=True)
    status_parser.add_argument("--store", required=True, choices=["play", "app_store"])

    init_existing_parser = subparsers.add_parser(
        "init-from-existing",
        help="Bootstrap a target listing from an existing listing source.",
    )
    init_existing_parser.add_argument("--app", required=True, help="Target app")
    init_existing_parser.add_argument("--store", required=True, choices=["play", "app_store"], help="Target store")
    init_existing_parser.add_argument("--from-app", required=True)
    init_existing_parser.add_argument("--from-store", required=True, choices=["play", "app_store"])
    init_existing_parser.add_argument("--from-file", type=Path, help="Optional source listing file path.")
    init_existing_parser.add_argument("--locales", help="Comma-separated subset of locales to copy.")
    init_existing_parser.add_argument("--baseline-locale")
    init_existing_parser.add_argument("--overwrite", action="store_true")

    sales_parser = subparsers.add_parser("app-store-sales-report", help="Download and parse an App Store Sales and Trends report.")
    sales_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(sales_parser)
    sales_parser.add_argument("--vendor-number", required=True)
    sales_parser.add_argument("--report-type", default="SALES")
    sales_parser.add_argument("--report-sub-type", default="SUMMARY")
    sales_parser.add_argument("--frequency", default="DAILY")
    sales_parser.add_argument("--report-date")
    sales_parser.add_argument("--version")
    sales_parser.add_argument("--max-rows", type=int, default=100)
    sales_parser.add_argument("--include-text", action="store_true")
    sales_parser.add_argument("--include-base64", action="store_true")

    analytics_request_parser = subparsers.add_parser("app-store-analytics-request", help="Create an App Store Analytics Reports request.")
    analytics_request_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(analytics_request_parser)
    analytics_request_parser.add_argument("--access-type", default="ONGOING", choices=["ONGOING", "ONE_TIME_SNAPSHOT"])

    analytics_requests_parser = subparsers.add_parser("app-store-analytics-list-requests", help="List App Store Analytics report requests.")
    analytics_requests_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(analytics_requests_parser)
    analytics_requests_parser.add_argument("--access-type", choices=["ONGOING", "ONE_TIME_SNAPSHOT"])
    analytics_requests_parser.add_argument("--limit", type=int, default=50)

    analytics_reports_parser = subparsers.add_parser("app-store-analytics-list-reports", help="List Analytics reports for a request.")
    analytics_reports_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(analytics_reports_parser)
    analytics_reports_parser.add_argument("--request-id", required=True)
    analytics_reports_parser.add_argument("--limit", type=int, default=200)

    analytics_instances_parser = subparsers.add_parser("app-store-analytics-list-instances", help="List Analytics report instances.")
    analytics_instances_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(analytics_instances_parser)
    analytics_instances_parser.add_argument("--report-id", required=True)
    analytics_instances_parser.add_argument("--granularity", choices=["DAILY", "WEEKLY", "MONTHLY"])
    analytics_instances_parser.add_argument("--processing-date")
    analytics_instances_parser.add_argument("--limit", type=int, default=200)

    analytics_segments_parser = subparsers.add_parser("app-store-analytics-list-segments", help="List Analytics report segment files.")
    analytics_segments_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(analytics_segments_parser)
    analytics_segments_parser.add_argument("--instance-id", required=True)
    analytics_segments_parser.add_argument("--limit", type=int, default=200)

    analytics_download_parser = subparsers.add_parser("app-store-analytics-download-segment", help="Download and parse one Analytics segment.")
    analytics_download_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(analytics_download_parser)
    analytics_download_parser.add_argument("--segment-id", required=True)
    analytics_download_parser.add_argument("--max-rows", type=int, default=100)
    analytics_download_parser.add_argument("--include-text", action="store_true")
    analytics_download_parser.add_argument("--include-base64", action="store_true")

    play_apps_parser = subparsers.add_parser("play-reporting-apps", help="List apps visible to the Play Developer Reporting API.")
    play_apps_parser.add_argument("--credentials-path")
    play_apps_parser.add_argument("--page-size", type=int, default=100)
    play_apps_parser.add_argument("--page-token")

    play_vitals_parser = subparsers.add_parser("play-vitals", help="Query Android vitals via Play Developer Reporting API.")
    _add_play_auth_args(play_vitals_parser)
    play_vitals_parser.add_argument("--metric-set", default="crash_rate")
    play_vitals_parser.add_argument("--start-date", required=True)
    play_vitals_parser.add_argument("--end-date", required=True)
    play_vitals_parser.add_argument("--dimensions", help="Comma-separated dimensions, e.g. versionCode,countryCode.")
    play_vitals_parser.add_argument("--metrics", help="Comma-separated metrics, e.g. crashRate,distinctUsers.")
    play_vitals_parser.add_argument("--aggregation-period", default="DAILY")
    play_vitals_parser.add_argument("--timezone-id", default="America/Los_Angeles")
    play_vitals_parser.add_argument("--filter-expr")
    play_vitals_parser.add_argument("--user-cohort")
    play_vitals_parser.add_argument("--page-size", type=int, default=1000)
    play_vitals_parser.add_argument("--page-token")

    play_files_parser = subparsers.add_parser("play-report-files", help="List Play Console report files in Cloud Storage.")
    play_files_parser.add_argument("--credentials-path")
    play_files_parser.add_argument("--bucket", required=True)
    play_files_parser.add_argument("--prefix", default="")
    play_files_parser.add_argument("--page-size", type=int, default=1000)
    play_files_parser.add_argument("--page-token")

    play_download_parser = subparsers.add_parser("play-report-download", help="Download and parse a Play Console Cloud Storage CSV report.")
    play_download_parser.add_argument("--credentials-path")
    play_download_parser.add_argument("--bucket", required=True)
    play_download_parser.add_argument("--object-name", required=True)
    play_download_parser.add_argument("--max-rows", type=int, default=100)
    play_download_parser.add_argument("--encoding", default="utf-16")
    play_download_parser.add_argument("--include-text", action="store_true")
    play_download_parser.add_argument("--include-base64", action="store_true")

    coverage_parser = subparsers.add_parser("store-api-coverage", help="Show official store API coverage status.")
    coverage_parser.add_argument("--provider", choices=["app_store", "play_android_publisher", "play_reporting", "play_reports"])
    coverage_parser.add_argument("--no-rows", action="store_true", help="Return only summary and operation metadata.")
    coverage_parser.add_argument("--markdown", action="store_true", help="Include rendered Markdown coverage matrix.")

    app_store_request_parser = subparsers.add_parser("app-store-api-request", help="Call a generic App Store Connect API endpoint.")
    app_store_request_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(app_store_request_parser)
    app_store_request_parser.add_argument("--method", default="GET")
    app_store_request_parser.add_argument("--path", required=True, help="API path such as /v1/apps or /v2/appStoreVersionExperiments.")
    app_store_request_parser.add_argument("--params", help="JSON object of query parameters.")
    app_store_request_parser.add_argument("--body", help="JSON object request body.")
    app_store_request_parser.add_argument("--yes", action="store_true", help="Confirm non-read generic API request.")

    play_request_parser = subparsers.add_parser("play-api-request", help="Call a generic Android Publisher API endpoint.")
    _add_play_auth_args(play_request_parser)
    play_request_parser.add_argument("--method", default="GET")
    play_request_parser.add_argument("--path", required=True, help="Path under /androidpublisher/v3, or a full URL.")
    play_request_parser.add_argument("--params", help="JSON object of query parameters.")
    play_request_parser.add_argument("--body", help="JSON object request body.")
    play_request_parser.add_argument("--yes", action="store_true", help="Confirm non-read generic API request.")

    cpp_list_parser = subparsers.add_parser("app-store-custom-pages", help="List App Store custom product pages.")
    cpp_list_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(cpp_list_parser)
    cpp_list_parser.add_argument("--limit", type=int, default=200)

    cpp_create_parser = subparsers.add_parser("app-store-custom-page-create", help="Create an App Store custom product page.")
    cpp_create_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(cpp_create_parser)
    cpp_create_parser.add_argument("--name", required=True)
    cpp_create_parser.add_argument("--app-store-version-template-id")
    cpp_create_parser.add_argument("--custom-product-page-template-id")

    cpp_update_parser = subparsers.add_parser("app-store-custom-page-update", help="Update an App Store custom product page.")
    cpp_update_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(cpp_update_parser)
    cpp_update_parser.add_argument("--page-id", required=True)
    cpp_update_parser.add_argument("--name")
    cpp_update_parser.add_argument("--visible", choices=["true", "false"])

    cpp_delete_parser = subparsers.add_parser("app-store-custom-page-delete", help="Delete an App Store custom product page.")
    cpp_delete_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(cpp_delete_parser)
    cpp_delete_parser.add_argument("--page-id", required=True)

    keywords_parser = subparsers.add_parser("app-store-keywords", help="List App Store keyword resources.")
    keywords_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(keywords_parser)
    keywords_parser.add_argument("--locale", default="en-US")
    keywords_parser.add_argument("--platform", default="IOS")
    keywords_parser.add_argument("--limit", type=int, default=200)

    cpp_versions_parser = subparsers.add_parser("app-store-custom-page-versions", help="List custom product page versions.")
    cpp_versions_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(cpp_versions_parser)
    cpp_versions_parser.add_argument("--page-id", required=True)
    cpp_versions_parser.add_argument("--limit", type=int, default=200)

    cpp_version_create_parser = subparsers.add_parser("app-store-custom-page-version-create", help="Create a custom product page version.")
    cpp_version_create_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(cpp_version_create_parser)
    cpp_version_create_parser.add_argument("--page-id", required=True)
    cpp_version_create_parser.add_argument("--deep-link")

    cpp_version_update_parser = subparsers.add_parser("app-store-custom-page-version-update", help="Update a custom product page version.")
    cpp_version_update_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(cpp_version_update_parser)
    cpp_version_update_parser.add_argument("--version-id", required=True)
    cpp_version_update_parser.add_argument("--deep-link")

    cpp_locs_parser = subparsers.add_parser("app-store-custom-page-localizations", help="List custom product page localizations.")
    cpp_locs_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(cpp_locs_parser)
    cpp_locs_parser.add_argument("--version-id", required=True)
    cpp_locs_parser.add_argument("--limit", type=int, default=200)

    cpp_loc_create_parser = subparsers.add_parser("app-store-custom-page-localization-create", help="Create a custom product page localization.")
    cpp_loc_create_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(cpp_loc_create_parser)
    cpp_loc_create_parser.add_argument("--version-id", required=True)
    cpp_loc_create_parser.add_argument("--locale", required=True)
    cpp_loc_create_parser.add_argument("--promotional-text")

    cpp_loc_update_parser = subparsers.add_parser("app-store-custom-page-localization-update", help="Update a custom product page localization.")
    cpp_loc_update_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(cpp_loc_update_parser)
    cpp_loc_update_parser.add_argument("--localization-id", required=True)
    cpp_loc_update_parser.add_argument("--promotional-text")

    cpp_keywords_link_parser = subparsers.add_parser("app-store-custom-page-keywords-link", help="Link App Store keyword IDs to a custom product page localization.")
    cpp_keywords_link_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(cpp_keywords_link_parser)
    cpp_keywords_link_parser.add_argument("--localization-id", required=True)
    cpp_keywords_link_parser.add_argument("--keyword-ids", required=True, help="Comma-separated app keyword resource IDs.")

    cpp_keywords_unlink_parser = subparsers.add_parser("app-store-custom-page-keywords-unlink", help="Unlink App Store keyword IDs from a custom product page localization.")
    cpp_keywords_unlink_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(cpp_keywords_unlink_parser)
    cpp_keywords_unlink_parser.add_argument("--localization-id", required=True)
    cpp_keywords_unlink_parser.add_argument("--keyword-ids", required=True, help="Comma-separated app keyword resource IDs.")

    cpp_screens_parser = subparsers.add_parser("app-store-custom-page-screenshots", help="Upload custom product page screenshots.")
    cpp_screens_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(cpp_screens_parser)
    cpp_screens_parser.add_argument("--localization-id", required=True)
    cpp_screens_parser.add_argument("--display-type", required=True)
    cpp_screens_parser.add_argument("--file-paths", required=True, help="Comma-separated screenshot paths.")
    cpp_screens_parser.add_argument("--no-replace", action="store_true")

    cpp_previews_parser = subparsers.add_parser("app-store-custom-page-previews", help="Upload custom product page app preview videos.")
    cpp_previews_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(cpp_previews_parser)
    cpp_previews_parser.add_argument("--localization-id", required=True)
    cpp_previews_parser.add_argument("--preview-type", required=True, help="e.g. IPHONE_67, IPAD_PRO_3GEN_129")
    cpp_previews_parser.add_argument("--file-paths", required=True, help="Comma-separated app preview video paths.")
    cpp_previews_parser.add_argument("--mime-type")
    cpp_previews_parser.add_argument("--preview-frame-time-code")
    cpp_previews_parser.add_argument("--no-replace", action="store_true")

    exp_list_parser = subparsers.add_parser("app-store-experiments", help="List App Store product page optimization experiments.")
    exp_list_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(exp_list_parser)
    exp_list_parser.add_argument("--limit", type=int, default=200)

    exp_create_parser = subparsers.add_parser("app-store-experiment-create", help="Create an App Store product page optimization experiment.")
    exp_create_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(exp_create_parser)
    exp_create_parser.add_argument("--name", required=True)
    exp_create_parser.add_argument("--platform", default="IOS")
    exp_create_parser.add_argument("--traffic-proportion", type=int, default=50)

    exp_update_parser = subparsers.add_parser("app-store-experiment-update", help="Update or start an App Store experiment.")
    exp_update_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(exp_update_parser)
    exp_update_parser.add_argument("--experiment-id", required=True)
    exp_update_parser.add_argument("--name")
    exp_update_parser.add_argument("--traffic-proportion", type=int)
    exp_update_parser.add_argument("--started", choices=["true", "false"])

    exp_delete_parser = subparsers.add_parser("app-store-experiment-delete", help="Delete an App Store experiment before it starts.")
    exp_delete_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(exp_delete_parser)
    exp_delete_parser.add_argument("--experiment-id", required=True)

    treatments_parser = subparsers.add_parser("app-store-experiment-treatments", help="List App Store experiment treatments.")
    treatments_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(treatments_parser)
    treatments_parser.add_argument("--experiment-id", required=True)
    treatments_parser.add_argument("--limit", type=int, default=200)

    treatment_create_parser = subparsers.add_parser("app-store-experiment-treatment-create", help="Create an App Store experiment treatment.")
    treatment_create_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(treatment_create_parser)
    treatment_create_parser.add_argument("--experiment-id", required=True)
    treatment_create_parser.add_argument("--name", required=True)
    treatment_create_parser.add_argument("--app-icon-name")

    treatment_update_parser = subparsers.add_parser("app-store-experiment-treatment-update", help="Update an App Store experiment treatment.")
    treatment_update_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(treatment_update_parser)
    treatment_update_parser.add_argument("--treatment-id", required=True)
    treatment_update_parser.add_argument("--name")
    treatment_update_parser.add_argument("--app-icon-name")

    treatment_delete_parser = subparsers.add_parser("app-store-experiment-treatment-delete", help="Delete an App Store experiment treatment.")
    treatment_delete_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(treatment_delete_parser)
    treatment_delete_parser.add_argument("--treatment-id", required=True)

    treatment_locs_parser = subparsers.add_parser("app-store-experiment-treatment-localizations", help="List treatment localizations.")
    treatment_locs_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(treatment_locs_parser)
    treatment_locs_parser.add_argument("--treatment-id", required=True)
    treatment_locs_parser.add_argument("--limit", type=int, default=200)

    treatment_loc_create_parser = subparsers.add_parser("app-store-experiment-treatment-localization-create", help="Create treatment localization.")
    treatment_loc_create_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(treatment_loc_create_parser)
    treatment_loc_create_parser.add_argument("--treatment-id", required=True)
    treatment_loc_create_parser.add_argument("--locale", required=True)

    treatment_screens_parser = subparsers.add_parser("app-store-experiment-screenshots", help="Upload experiment treatment screenshots.")
    treatment_screens_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(treatment_screens_parser)
    treatment_screens_parser.add_argument("--localization-id", required=True)
    treatment_screens_parser.add_argument("--display-type", required=True)
    treatment_screens_parser.add_argument("--file-paths", required=True, help="Comma-separated screenshot paths.")
    treatment_screens_parser.add_argument("--no-replace", action="store_true")

    treatment_previews_parser = subparsers.add_parser("app-store-experiment-previews", help="Upload experiment treatment app preview videos.")
    treatment_previews_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(treatment_previews_parser)
    treatment_previews_parser.add_argument("--localization-id", required=True)
    treatment_previews_parser.add_argument("--preview-type", required=True, help="e.g. IPHONE_67, IPAD_PRO_3GEN_129")
    treatment_previews_parser.add_argument("--file-paths", required=True, help="Comma-separated app preview video paths.")
    treatment_previews_parser.add_argument("--mime-type")
    treatment_previews_parser.add_argument("--preview-frame-time-code")
    treatment_previews_parser.add_argument("--no-replace", action="store_true")

    review_create_parser = subparsers.add_parser("app-store-review-submission-create", help="Create App Store review submission.")
    review_create_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(review_create_parser)
    review_create_parser.add_argument("--platform")

    review_item_parser = subparsers.add_parser("app-store-review-submission-add-item", help="Add item to App Store review submission.")
    review_item_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(review_item_parser)
    review_item_parser.add_argument("--review-submission-id", required=True)
    review_item_parser.add_argument("--resource-type", required=True, choices=["appStoreVersions", "appCustomProductPageVersions", "appStoreVersionExperiments"])
    review_item_parser.add_argument("--resource-id", required=True)

    review_submit_parser = subparsers.add_parser("app-store-review-submission-submit", help="Submit App Store review submission.")
    review_submit_parser.add_argument("--app", required=True)
    _add_app_store_auth_args(review_submit_parser)
    review_submit_parser.add_argument("--review-submission-id", required=True)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    service = ListingService(FileStorageBackend(args.file))
    store = cast(StoreName, getattr(args, "store", "play"))

    if args.command == "get":
        result = service.get_element(app=args.app, store=store, key_path=args.key, locale=args.locale)
    elif args.command == "set":
        value = _json_or_string(args.value, parse_json=args.json_value)
        result = service.set_element(app=args.app, store=store, key_path=args.key, value=value, locale=args.locale)
    elif args.command == "delete":
        result = service.delete_element(app=args.app, store=store, key_path=args.key, locale=args.locale)
    elif args.command == "upsert-locale":
        payload = json.loads(args.data)
        if not isinstance(payload, dict):
            raise ValueError("--data must be a JSON object")
        result = service.upsert_locale(
            app=args.app,
            store=store,
            locale=args.locale,
            data=payload,
            replace=bool(args.replace),
        )
    elif args.command == "list":
        result = service.list_section(app=args.app, store=store, locale=args.locale)
    elif args.command == "init":
        parsed_stores = [part.strip() for part in args.stores.split(",") if part.strip()]
        parsed_locales = [part.strip() for part in (args.locales or "").split(",") if part.strip()] or None
        result = service.init_listing(
            app=args.app,
            stores=cast(list[StoreName], parsed_stores),
            locales=parsed_locales,
            baseline_locale=args.baseline_locale,
            overwrite=bool(args.overwrite),
        )
    elif args.command == "set-baseline-language":
        result = service.set_baseline_locale(app=args.app, store=store, locale=args.locale)
    elif args.command == "bump-version":
        result = service.bump_version(
            app=args.app,
            store=store,
            reason=args.reason,
            source_locale=args.source_locale,
        )
    elif args.command == "mark-language-updated":
        result = service.mark_language_updated(app=args.app, store=store, locale=args.locale)
    elif args.command == "status":
        result = service.get_update_status(app=args.app, store=store)
    elif args.command == "init-from-existing":
        source_service = ListingService(FileStorageBackend(args.from_file)) if args.from_file else service
        source_section = source_service.list_section(
            app=args.from_app,
            store=cast(StoreName, args.from_store),
            locale=None,
        )
        selected_locales = [part.strip() for part in (args.locales or "").split(",") if part.strip()] or None
        result = service.init_from_existing_section(
            target_app=args.app,
            target_store=store,
            source_section=source_section,
            overwrite=bool(args.overwrite),
            locales=selected_locales,
            baseline_locale=args.baseline_locale,
        )
    elif args.command == "app-store-sales-report":
        app_id, key_id, issuer_id, private_key_path = _resolve_app_store_cli_credentials(
            service, args.app, args.app_id, args.key_id, args.issuer_id, args.private_key_path,
        )
        client = app_store_api.AppStoreConnectClient.from_key_file(key_id, issuer_id, private_key_path)
        content = client.download_sales_report(
            vendor_number=args.vendor_number,
            report_type=args.report_type,
            report_sub_type=args.report_sub_type,
            frequency=args.frequency,
            report_date=args.report_date,
            version=args.version,
        )
        service.save_credentials(args.app, "app_store", {
            "app_id": app_id,
            "key_id": key_id,
            "issuer_id": issuer_id,
            "private_key_path": private_key_path,
        })
        result = _parsed_gzip_result(
            content,
            max_rows=args.max_rows,
            include_text=bool(args.include_text),
            include_base64=bool(args.include_base64),
        )
    elif args.command.startswith("app-store-analytics-"):
        app_id, key_id, issuer_id, private_key_path = _resolve_app_store_cli_credentials(
            service, args.app, args.app_id, args.key_id, args.issuer_id, args.private_key_path,
        )
        client = app_store_api.AppStoreConnectClient.from_key_file(key_id, issuer_id, private_key_path)
        service.save_credentials(args.app, "app_store", {
            "app_id": app_id,
            "key_id": key_id,
            "issuer_id": issuer_id,
            "private_key_path": private_key_path,
        })
        if args.command == "app-store-analytics-request":
            result = client.request_analytics_reports(app_id, access_type=args.access_type)
        elif args.command == "app-store-analytics-list-requests":
            result = client.list_analytics_report_requests(app_id, access_type=args.access_type, limit=args.limit)
        elif args.command == "app-store-analytics-list-reports":
            result = client.list_analytics_reports(args.request_id, limit=args.limit)
        elif args.command == "app-store-analytics-list-instances":
            result = client.list_analytics_report_instances(
                args.report_id,
                granularity=args.granularity,
                processing_date=args.processing_date,
                limit=args.limit,
            )
        elif args.command == "app-store-analytics-list-segments":
            result = client.list_analytics_report_segments(args.instance_id, limit=args.limit)
        elif args.command == "app-store-analytics-download-segment":
            content = client.download_analytics_report_segment(args.segment_id)
            result = _parsed_gzip_result(
                content,
                max_rows=args.max_rows,
                include_text=bool(args.include_text),
                include_base64=bool(args.include_base64),
            )
        else:
            parser.error(f"Unsupported command: {args.command}")
            return 2
    elif args.command == "play-reporting-apps":
        api = play_store_api.create_reporting_service(credentials_path=args.credentials_path)
        result = play_store_api.search_reporting_apps(
            api,
            page_size=args.page_size,
            page_token=args.page_token,
        )
    elif args.command == "play-vitals":
        package_name, credentials_path = _resolve_play_cli_credentials(
            service, args.app, args.package_name, args.credentials_path,
        )
        api = play_store_api.create_reporting_service(credentials_path=credentials_path)
        result = play_store_api.query_vitals_metric(
            api,
            package_name,
            args.metric_set,
            start_date=args.start_date,
            end_date=args.end_date,
            dimensions=_csv(args.dimensions),
            metrics=_csv(args.metrics),
            aggregation_period=args.aggregation_period,
            timezone_id=args.timezone_id,
            filter_expr=args.filter_expr,
            user_cohort=args.user_cohort,
            page_size=args.page_size,
            page_token=args.page_token,
        )
        if args.app:
            service.save_credentials(args.app, "play", {
                "package_name": package_name,
                **({"credentials_path": credentials_path} if credentials_path else {}),
            })
    elif args.command == "play-report-files":
        session = play_store_api.create_storage_session(credentials_path=args.credentials_path)
        result = play_store_api.list_play_report_objects(
            session,
            args.bucket,
            prefix=args.prefix,
            page_size=args.page_size,
            page_token=args.page_token,
        )
    elif args.command == "play-report-download":
        session = play_store_api.create_storage_session(credentials_path=args.credentials_path)
        content = play_store_api.download_play_report_object(session, args.bucket, args.object_name)
        parsed = play_store_api.parse_play_report_content(
            content,
            max_rows=args.max_rows,
            encoding=args.encoding,
        )
        result = {
            "ok": True,
            "bucket": args.bucket,
            "object_name": args.object_name,
            "columns": parsed["columns"],
            "rows": parsed["rows"],
            "row_count": parsed["row_count"],
            "content_bytes": len(content),
        }
        if args.include_text:
            result["text"] = parsed["text"]
        if args.include_base64:
            result["content_base64"] = base64.b64encode(content).decode("ascii")
    elif args.command == "store-api-coverage":
        result = store_api_coverage.coverage_payload(args.provider, include_rows=not args.no_rows)
        if args.markdown:
            result["markdown"] = store_api_coverage.render_coverage_markdown(args.provider)
    elif args.command == "app-store-api-request":
        _require_write_confirmation(args.method, args.yes, command=args.command)
        _, client = _app_store_client_from_cli(service, args)
        result = client.request(
            args.method,
            args.path,
            params=_json_object(args.params, option="--params"),
            json_body=_json_object(args.body, option="--body"),
        )
    elif args.command == "play-api-request":
        _require_write_confirmation(args.method, args.yes, command=args.command)
        package_name = args.package_name or ""
        credentials_path = args.credentials_path
        if args.app:
            stored = service.get_credentials(args.app, "play")
            package_name = package_name or str(stored.get("package_name") or "")
            credentials_path = credentials_path if credentials_path is not None else stored.get("credentials_path")
        session = play_store_api.create_android_publisher_session(credentials_path=credentials_path)
        result = play_store_api.android_publisher_request(
            session,
            args.method,
            args.path,
            params=_json_object(args.params, option="--params"),
            json_body=_json_object(args.body, option="--body"),
        )
        if args.app:
            credential_payload = {
                **({"package_name": package_name} if package_name else {}),
                **({"credentials_path": credentials_path} if credentials_path else {}),
            }
            if credential_payload:
                service.save_credentials(args.app, "play", credential_payload)
    elif args.command == "app-store-custom-pages":
        app_id, client = _app_store_client_from_cli(service, args)
        result = client.list_custom_product_pages(app_id, limit=args.limit)
    elif args.command == "app-store-custom-page-create":
        app_id, client = _app_store_client_from_cli(service, args)
        result = client.create_custom_product_page(
            app_id,
            args.name,
            app_store_version_template_id=args.app_store_version_template_id,
            custom_product_page_template_id=args.custom_product_page_template_id,
        )
    elif args.command == "app-store-custom-page-update":
        _, client = _app_store_client_from_cli(service, args)
        visible = None if args.visible is None else args.visible == "true"
        result = client.update_custom_product_page(args.page_id, name=args.name, visible=visible)
    elif args.command == "app-store-custom-page-delete":
        _, client = _app_store_client_from_cli(service, args)
        result = client.delete_custom_product_page(args.page_id)
    elif args.command == "app-store-keywords":
        app_id, client = _app_store_client_from_cli(service, args)
        result = client.list_app_keywords(
            app_id,
            locale=args.locale,
            platform=args.platform,
            limit=args.limit,
        )
    elif args.command == "app-store-custom-page-versions":
        _, client = _app_store_client_from_cli(service, args)
        result = client.list_custom_product_page_versions(args.page_id, limit=args.limit)
    elif args.command == "app-store-custom-page-version-create":
        _, client = _app_store_client_from_cli(service, args)
        result = client.create_custom_product_page_version(args.page_id, deep_link=args.deep_link)
    elif args.command == "app-store-custom-page-version-update":
        _, client = _app_store_client_from_cli(service, args)
        result = client.update_custom_product_page_version(args.version_id, deep_link=args.deep_link)
    elif args.command == "app-store-custom-page-localizations":
        _, client = _app_store_client_from_cli(service, args)
        result = client.list_custom_product_page_localizations(args.version_id, limit=args.limit)
    elif args.command == "app-store-custom-page-localization-create":
        _, client = _app_store_client_from_cli(service, args)
        result = client.create_custom_product_page_localization(
            args.version_id,
            args.locale,
            promotional_text=args.promotional_text,
        )
    elif args.command == "app-store-custom-page-localization-update":
        _, client = _app_store_client_from_cli(service, args)
        result = client.update_custom_product_page_localization(
            args.localization_id,
            promotional_text=args.promotional_text,
        )
    elif args.command == "app-store-custom-page-keywords-link":
        _, client = _app_store_client_from_cli(service, args)
        result = client.add_custom_product_page_search_keywords(
            args.localization_id,
            _csv(args.keyword_ids),
        )
    elif args.command == "app-store-custom-page-keywords-unlink":
        _, client = _app_store_client_from_cli(service, args)
        result = client.remove_custom_product_page_search_keywords(
            args.localization_id,
            _csv(args.keyword_ids),
        )
    elif args.command == "app-store-custom-page-screenshots":
        _, client = _app_store_client_from_cli(service, args)
        result = app_store_api.upload_screenshots(
            client,
            args.localization_id,
            args.display_type,
            _csv(args.file_paths),
            replace=not args.no_replace,
            target_type="appCustomProductPageLocalizations",
        )
    elif args.command == "app-store-custom-page-previews":
        _, client = _app_store_client_from_cli(service, args)
        result = app_store_api.upload_previews(
            client,
            args.localization_id,
            args.preview_type,
            _csv(args.file_paths),
            replace=not args.no_replace,
            target_type="appCustomProductPageLocalizations",
            mime_type=args.mime_type,
            preview_frame_time_code=args.preview_frame_time_code,
        )
    elif args.command == "app-store-experiments":
        app_id, client = _app_store_client_from_cli(service, args)
        result = client.list_app_store_experiments(app_id, limit=args.limit)
    elif args.command == "app-store-experiment-create":
        app_id, client = _app_store_client_from_cli(service, args)
        result = client.create_app_store_experiment(
            app_id,
            name=args.name,
            platform=args.platform,
            traffic_proportion=args.traffic_proportion,
        )
    elif args.command == "app-store-experiment-update":
        _, client = _app_store_client_from_cli(service, args)
        started = None if args.started is None else args.started == "true"
        result = client.update_app_store_experiment(
            args.experiment_id,
            name=args.name,
            traffic_proportion=args.traffic_proportion,
            started=started,
        )
    elif args.command == "app-store-experiment-delete":
        _, client = _app_store_client_from_cli(service, args)
        result = client.delete_app_store_experiment(args.experiment_id)
    elif args.command == "app-store-experiment-treatments":
        _, client = _app_store_client_from_cli(service, args)
        result = client.list_app_store_experiment_treatments(args.experiment_id, limit=args.limit)
    elif args.command == "app-store-experiment-treatment-create":
        _, client = _app_store_client_from_cli(service, args)
        result = client.create_app_store_experiment_treatment(
            args.experiment_id,
            name=args.name,
            app_icon_name=args.app_icon_name,
        )
    elif args.command == "app-store-experiment-treatment-update":
        _, client = _app_store_client_from_cli(service, args)
        result = client.update_app_store_experiment_treatment(
            args.treatment_id,
            name=args.name,
            app_icon_name=args.app_icon_name,
        )
    elif args.command == "app-store-experiment-treatment-delete":
        _, client = _app_store_client_from_cli(service, args)
        result = client.delete_app_store_experiment_treatment(args.treatment_id)
    elif args.command == "app-store-experiment-treatment-localizations":
        _, client = _app_store_client_from_cli(service, args)
        result = client.list_app_store_experiment_treatment_localizations(args.treatment_id, limit=args.limit)
    elif args.command == "app-store-experiment-treatment-localization-create":
        _, client = _app_store_client_from_cli(service, args)
        result = client.create_app_store_experiment_treatment_localization(args.treatment_id, args.locale)
    elif args.command == "app-store-experiment-screenshots":
        _, client = _app_store_client_from_cli(service, args)
        result = app_store_api.upload_screenshots(
            client,
            args.localization_id,
            args.display_type,
            _csv(args.file_paths),
            replace=not args.no_replace,
            target_type="appStoreVersionExperimentTreatmentLocalizations",
        )
    elif args.command == "app-store-experiment-previews":
        _, client = _app_store_client_from_cli(service, args)
        result = app_store_api.upload_previews(
            client,
            args.localization_id,
            args.preview_type,
            _csv(args.file_paths),
            replace=not args.no_replace,
            target_type="appStoreVersionExperimentTreatmentLocalizations",
            mime_type=args.mime_type,
            preview_frame_time_code=args.preview_frame_time_code,
        )
    elif args.command == "app-store-review-submission-create":
        app_id, client = _app_store_client_from_cli(service, args)
        result = client.create_review_submission(app_id, platform=args.platform)
    elif args.command == "app-store-review-submission-add-item":
        _, client = _app_store_client_from_cli(service, args)
        result = client.add_review_submission_item(
            args.review_submission_id,
            resource_type=args.resource_type,
            resource_id=args.resource_id,
        )
    elif args.command == "app-store-review-submission-submit":
        _, client = _app_store_client_from_cli(service, args)
        result = client.submit_review_submission(args.review_submission_id)
    else:
        parser.error(f"Unsupported command: {args.command}")
        return 2

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
