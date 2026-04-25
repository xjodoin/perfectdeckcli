"""Shared store API operation metadata for CLI, MCP, docs, and tests."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


Provider = Literal["app_store", "play_android_publisher", "play_reporting", "play_reports", "coverage"]
Mutability = Literal["read", "write", "destructive"]
Exposure = Literal["cli+mcp", "mcp-only", "cli-only"]
CoverageStatus = Literal[
    "typed-supported",
    "generic-supported",
    "planned",
    "console-only",
    "not-public",
    "not-applicable",
]


@dataclass(frozen=True)
class StoreOperation:
    """A public store operation exposed by perfectdeckcli."""

    operation_id: str
    title: str
    provider: Provider
    status: CoverageStatus
    mutability: Mutability = "read"
    exposure: Exposure = "cli+mcp"
    cli_name: str | None = None
    mcp_name: str | None = None
    credential: str = ""
    role_hint: str = ""
    dry_run: bool = False
    confirmation_required: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


STORE_OPERATIONS: tuple[StoreOperation, ...] = (
    StoreOperation(
        "store.api_coverage",
        "Store API coverage matrix",
        "coverage",
        "typed-supported",
        cli_name="store-api-coverage",
        mcp_name="perfectdeck_store_api_coverage",
        notes="Generated from the shared operation registry and official API category inventory.",
    ),
    StoreOperation(
        "app_store.generic_request",
        "Generic App Store Connect API request",
        "app_store",
        "generic-supported",
        mutability="write",
        cli_name="app-store-api-request",
        mcp_name="perfectdeck_app_store_api_request",
        credential="App Store Connect API key",
        role_hint="Depends on endpoint; Admin/App Manager/Developer/Marketing/Finance/Sales roles may be required.",
        confirmation_required=True,
        notes="Provides official-public-API reach for App Store Connect categories without typed wrappers yet.",
    ),
    StoreOperation(
        "play.generic_android_publisher_request",
        "Generic Android Publisher API request",
        "play_android_publisher",
        "generic-supported",
        mutability="write",
        cli_name="play-api-request",
        mcp_name="perfectdeck_play_api_request",
        credential="Google Play service account",
        role_hint="Depends on endpoint; Play Console app permissions and androidpublisher scope required.",
        confirmation_required=True,
        notes="Provides official-public-API reach for Android Publisher categories without typed wrappers yet.",
    ),
    StoreOperation(
        "app_store.sales_report",
        "App Store Sales and Trends report",
        "app_store",
        "typed-supported",
        cli_name="app-store-sales-report",
        mcp_name="perfectdeck_get_app_store_sales_report",
        credential="App Store Connect API key",
        role_hint="Sales and Reports or Finance.",
    ),
    StoreOperation(
        "app_store.analytics_reports",
        "App Store Analytics Reports flow",
        "app_store",
        "typed-supported",
        mutability="write",
        cli_name="app-store-analytics-request",
        mcp_name="perfectdeck_request_app_store_analytics_reports",
        credential="App Store Connect API key",
        role_hint="Role with Analytics Reports access.",
        notes="List/download operations are read-only; request creation is a non-destructive write.",
    ),
    StoreOperation(
        "app_store.custom_product_pages",
        "App Store custom product pages",
        "app_store",
        "typed-supported",
        mutability="write",
        cli_name="app-store-custom-pages",
        mcp_name="perfectdeck_list_app_store_custom_product_pages",
        credential="App Store Connect API key",
        role_hint="Admin, App Manager, or Marketing.",
        confirmation_required=True,
    ),
    StoreOperation(
        "app_store.product_page_experiments",
        "App Store product page optimization experiments",
        "app_store",
        "typed-supported",
        mutability="write",
        cli_name="app-store-experiments",
        mcp_name="perfectdeck_list_app_store_experiments",
        credential="App Store Connect API key",
        role_hint="Admin, App Manager, or Marketing.",
        confirmation_required=True,
    ),
    StoreOperation(
        "app_store.review_submissions",
        "App Store review submissions",
        "app_store",
        "typed-supported",
        mutability="write",
        cli_name="app-store-review-submission-create",
        mcp_name="perfectdeck_create_app_store_review_submission",
        credential="App Store Connect API key",
        role_hint="Admin or App Manager.",
        confirmation_required=True,
    ),
    StoreOperation(
        "app_store.listing_push",
        "App Store listing sync and push",
        "app_store",
        "typed-supported",
        mutability="write",
        exposure="mcp-only",
        mcp_name="perfectdeck_push_app_store_listing",
        credential="App Store Connect API key",
        role_hint="Admin, App Manager, or Marketing.",
        dry_run=True,
        confirmation_required=True,
    ),
    StoreOperation(
        "app_store.iap_subscriptions",
        "App Store IAP and subscription sync",
        "app_store",
        "typed-supported",
        mutability="write",
        exposure="mcp-only",
        mcp_name="perfectdeck_sync_app_store_iap",
        credential="App Store Connect API key",
        role_hint="Admin, App Manager, or Finance depending on field.",
        confirmation_required=True,
    ),
    StoreOperation(
        "play.reporting_apps",
        "Play Developer Reporting apps",
        "play_reporting",
        "typed-supported",
        cli_name="play-reporting-apps",
        mcp_name="perfectdeck_list_play_reporting_apps",
        credential="Google Play service account",
        role_hint="Play Developer Reporting API access.",
    ),
    StoreOperation(
        "play.vitals",
        "Play Android vitals query",
        "play_reporting",
        "typed-supported",
        cli_name="play-vitals",
        mcp_name="perfectdeck_query_play_vitals",
        credential="Google Play service account",
        role_hint="Play Developer Reporting API access.",
    ),
    StoreOperation(
        "play.report_exports",
        "Play Console Cloud Storage report exports",
        "play_reports",
        "typed-supported",
        cli_name="play-report-files",
        mcp_name="perfectdeck_list_play_report_files",
        credential="Google Play service account",
        role_hint="Storage object viewer on the Play reports bucket.",
    ),
    StoreOperation(
        "play.listing_push",
        "Google Play listing sync and push",
        "play_android_publisher",
        "typed-supported",
        mutability="write",
        exposure="mcp-only",
        mcp_name="perfectdeck_push_play_listing",
        credential="Google Play service account",
        role_hint="Manage store presence.",
        dry_run=True,
        confirmation_required=True,
    ),
    StoreOperation(
        "play.release_bundle",
        "Google Play bundle upload and track release",
        "play_android_publisher",
        "typed-supported",
        mutability="write",
        exposure="mcp-only",
        mcp_name="perfectdeck_publish_play_bundle",
        credential="Google Play service account",
        role_hint="Release to testing/production tracks.",
        confirmation_required=True,
    ),
    StoreOperation(
        "play.products_pricing",
        "Google Play product and pricing sync",
        "play_android_publisher",
        "typed-supported",
        mutability="write",
        exposure="mcp-only",
        mcp_name="perfectdeck_sync_play_products",
        credential="Google Play service account",
        role_hint="Manage monetization.",
        confirmation_required=True,
    ),
)


def list_store_operations() -> list[dict[str, object]]:
    """Return store operation metadata as JSON-serializable dictionaries."""
    return [operation.to_dict() for operation in STORE_OPERATIONS]


def operation_by_cli_name(cli_name: str) -> StoreOperation | None:
    for operation in STORE_OPERATIONS:
        if operation.cli_name == cli_name:
            return operation
    return None


def operation_by_mcp_name(mcp_name: str) -> StoreOperation | None:
    for operation in STORE_OPERATIONS:
        if operation.mcp_name == mcp_name:
            return operation
    return None
