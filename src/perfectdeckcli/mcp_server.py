from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from .project_router import ProjectListingRouter
from .service import diff_objects
from . import play_store as play_store_api
from . import app_store as app_store_api
from . import regional_pricing

logger = logging.getLogger(__name__)


StoreName = Literal["play", "app_store"]
SyncMode = Literal["merge", "replace"]
router: ProjectListingRouter | None = None
mcp = FastMCP("perfectdeckcli_mcp")

# ---------------------------------------------------------------------------
# Store field reference & agent hints
# ---------------------------------------------------------------------------

_STORE_FIELD_LIMITS: dict[str, dict[str, int]] = {
    "play": {"title": 30, "short_description": 80, "full_description": 4000},
    "app_store": {"app_name": 30, "subtitle": 30, "description": 4000, "keywords": 100, "promotional_text": 170},
}

_TOOL_HINTS: dict[str, str] = {
    "perfectdeck_get_element": (
        "Use perfectdeck_set_element to update or perfectdeck_delete_element to remove."
    ),
    "perfectdeck_set_element": (
        "Run perfectdeck_validate_listing to check character limits."
    ),
    "perfectdeck_delete_element": (
        "Use perfectdeck_list_section to review remaining content."
    ),
    "perfectdeck_delete_locale": (
        "Locale removed. Use perfectdeck_list_languages to verify remaining locales."
    ),
    "perfectdeck_delete_product": (
        "Product removed. Use perfectdeck_list_section to verify remaining products."
    ),
    "perfectdeck_delete_release_notes_locale": (
        "Locale removed from release notes. Use perfectdeck_get_release_notes to verify."
    ),
    "perfectdeck_upsert_locale": (
        "Run perfectdeck_validate_listing to check limits. "
        "Call perfectdeck_mark_language_updated when translation is complete."
    ),
    "perfectdeck_list_section": (
        "Use perfectdeck_set_element or perfectdeck_upsert_locale to modify. "
        "Use perfectdeck_diff_listing to compare with another listing."
    ),
    "perfectdeck_list_apps": (
        "Use perfectdeck_list_stores to see stores, or perfectdeck_list_section to read content."
    ),
    "perfectdeck_list_stores": (
        "Use perfectdeck_list_languages for locales, or perfectdeck_list_section to read content."
    ),
    "perfectdeck_list_languages": (
        "Use perfectdeck_add_language to add a locale, or perfectdeck_list_section to read content."
    ),
    "perfectdeck_diff_listing": (
        "Use perfectdeck_sync_listing to copy from source to target."
    ),
    "perfectdeck_sync_listing": (
        "Use perfectdeck_diff_listing to verify, or perfectdeck_validate_listing to check limits."
    ),
    "perfectdeck_init_from_existing": (
        "Use perfectdeck_list_section to review cloned content. "
        "Customize with perfectdeck_set_element or perfectdeck_upsert_locale."
    ),
    "perfectdeck_set_baseline_language": (
        "Editing this locale now auto-bumps the version. "
        "Use perfectdeck_get_update_status to check translation freshness."
    ),
    "perfectdeck_bump_version": (
        "Non-baseline locales are now stale. Use perfectdeck_get_update_status to see which, "
        "then perfectdeck_mark_language_updated after translating each."
    ),
    "perfectdeck_mark_language_updated": (
        "Use perfectdeck_get_update_status to check remaining stale locales."
    ),
    "perfectdeck_get_update_status": (
        "For stale locales: update with perfectdeck_upsert_locale, "
        "then perfectdeck_mark_language_updated. To force a new version: perfectdeck_bump_version."
    ),
    "perfectdeck_save_snapshot": (
        "Use perfectdeck_list_snapshots to see all versions, or perfectdeck_diff_snapshot to compare."
    ),
    "perfectdeck_list_snapshots": (
        "Use perfectdeck_diff_snapshot to compare with current, or perfectdeck_restore_snapshot to roll back."
    ),
    "perfectdeck_restore_snapshot": (
        "Use perfectdeck_list_section to review restored data."
    ),
    "perfectdeck_diff_snapshot": (
        "Use perfectdeck_restore_snapshot to roll back if needed."
    ),
    "perfectdeck_set_release_notes": (
        "Run perfectdeck_validate_release_notes to check limits (Play: 500, App Store: 4000)."
    ),
    "perfectdeck_upsert_release_notes": (
        "Run perfectdeck_validate_release_notes to check limits."
    ),
    "perfectdeck_get_release_notes": (
        "Use perfectdeck_set_release_notes to update one locale, "
        "or perfectdeck_upsert_release_notes for batch updates."
    ),
    "perfectdeck_list_release_versions": (
        "Use perfectdeck_get_release_notes to read, or perfectdeck_set_release_notes to add."
    ),
    "perfectdeck_delete_release_notes": (
        "Use perfectdeck_list_release_versions to see remaining versions."
    ),
    "perfectdeck_validate_release_notes": (
        "Fix errors with perfectdeck_set_release_notes or perfectdeck_upsert_release_notes."
    ),
    "perfectdeck_validate_listing": (
        "Fix errors with perfectdeck_set_element or perfectdeck_upsert_locale."
    ),
    "perfectdeck_diff_play_listing": (
        "Use perfectdeck_sync_play_listing to import remote, "
        "or perfectdeck_push_play_listing to push local."
    ),
    "perfectdeck_diff_app_store_listing": (
        "Use perfectdeck_sync_app_store_listing to import remote, "
        "or perfectdeck_push_app_store_listing to push local."
    ),
    "perfectdeck_sync_play_listing": (
        "Use perfectdeck_diff_play_listing to verify, or perfectdeck_validate_listing to check content."
    ),
    "perfectdeck_sync_app_store_listing": (
        "Use perfectdeck_diff_app_store_listing to verify, or perfectdeck_validate_listing to check content."
    ),
    "perfectdeck_push_play_listing": (
        "Use perfectdeck_diff_play_listing to verify the push."
    ),
    "perfectdeck_push_app_store_listing": (
        "Use perfectdeck_diff_app_store_listing to verify the push."
    ),
    "perfectdeck_push_play_release_notes": (
        "Release notes pushed to Play Store track."
    ),
    "perfectdeck_push_play_screenshots": (
        "Screenshots uploaded to Google Play."
    ),
    "perfectdeck_publish_play_bundle": (
        "Bundle uploaded. Track release status in Google Play Console."
    ),
    "perfectdeck_create_app_store_version": (
        "Version created. Use perfectdeck_push_app_store_listing to upload content."
    ),
    "perfectdeck_push_app_store_screenshots": (
        "Screenshots uploaded to App Store Connect."
    ),
    "perfectdeck_configure_iap": (
        "IAP products saved locally. Use perfectdeck_sync_app_store_iap or perfectdeck_sync_play_products to push to stores."
    ),
    "perfectdeck_set_iap_pricing_tiers": (
        "Regional pricing applied locally. Use perfectdeck_sync_play_products or perfectdeck_sync_app_store_iap to push to stores."
    ),
    "perfectdeck_get_pricing_tiers": (
        "Shows built-in PPP tier config. Use perfectdeck_set_iap_pricing_tiers to apply pricing."
    ),
    "perfectdeck_get_app_store_app_id": (
        "Use the returned app_id with perfectdeck_sync_app_store_iap or other App Store tools."
    ),
    "perfectdeck_sync_app_store_iap": (
        "IAP localizations synced to App Store Connect and saved locally."
    ),
    "perfectdeck_sync_app_store_subscriptions": (
        "Subscription localizations synced to App Store Connect and saved locally."
    ),
    "perfectdeck_sync_play_products": (
        "Products synced to Google Play and saved locally."
    ),
    "perfectdeck_deactivate_play_product": (
        "Product deactivated on Google Play. Use perfectdeck_delete_product to also remove it locally."
    ),
    "perfectdeck_sync_play_pricing": (
        "Regional pricing applied on Google Play."
    ),
    "perfectdeck_sync_play_subscription_pricing": (
        "Subscription pricing applied on Google Play."
    ),
    "perfectdeck_begin_transaction": (
        "All mutations are buffered until commit. "
        "Use perfectdeck_commit_transaction to persist or perfectdeck_rollback_transaction to discard."
    ),
    "perfectdeck_commit_transaction": (
        "Changes flushed to disk. Use perfectdeck_validate_listing to verify."
    ),
    "perfectdeck_rollback_transaction": (
        "All changes since BEGIN discarded. Use perfectdeck_get_element to confirm revert."
    ),
}


def _result(data: dict[str, Any], tool_name: str = "") -> str:
    """Serialize result and attach a contextual hint for the calling agent."""
    hint = _TOOL_HINTS.get(tool_name)
    if hint and "hint" not in data:
        data["hint"] = hint
    return json.dumps(data, ensure_ascii=False)


def _router() -> ProjectListingRouter:
    if router is None:
        raise RuntimeError("Server not initialized. Start with perfectdeck-mcp --root-folder <path>.")
    return router


# ======================================================================
# Credential resolution helpers
# ======================================================================


def _resolve_play_credentials(
    project_path: str,
    app: str,
    package_name: str | None,
    credentials_path: str | None,
) -> tuple[str, str | None]:
    """Return (package_name, credentials_path) falling back to stored credentials."""
    if package_name and credentials_path is not None:
        return package_name, credentials_path
    stored = _router().service_for(project_path).get_credentials(app, "play")
    resolved_pkg = package_name or stored.get("package_name")
    resolved_creds = credentials_path if credentials_path is not None else stored.get("credentials_path")
    if not resolved_pkg:
        raise ValueError(
            "package_name is required. Provide it explicitly or run a sync first to store credentials."
        )
    return resolved_pkg, resolved_creds


def _resolve_app_store_credentials(
    project_path: str,
    app: str,
    app_id: str | None,
    key_id: str | None,
    issuer_id: str | None,
    private_key_path: str | None,
) -> tuple[str, str, str, str]:
    """Return (app_id, key_id, issuer_id, private_key_path) falling back to stored credentials."""
    if app_id and key_id and issuer_id and private_key_path:
        return app_id, key_id, issuer_id, private_key_path
    stored = _router().service_for(project_path).get_credentials(app, "app_store")
    resolved_app_id = app_id or stored.get("app_id")
    resolved_key_id = key_id or stored.get("key_id")
    resolved_issuer_id = issuer_id or stored.get("issuer_id")
    resolved_pk = private_key_path or stored.get("private_key_path")
    missing = []
    if not resolved_app_id:
        missing.append("app_id")
    if not resolved_key_id:
        missing.append("key_id")
    if not resolved_issuer_id:
        missing.append("issuer_id")
    if not resolved_pk:
        missing.append("private_key_path")
    if missing:
        raise ValueError(
            f"Missing App Store credentials: {', '.join(missing)}. "
            "Provide them explicitly or run a sync first to store credentials."
        )
    return resolved_app_id, resolved_key_id, resolved_issuer_id, resolved_pk  # type: ignore[return-value]


def _persist_play_credentials(
    project_path: str,
    app: str,
    package_name: str,
    credentials_path: str | None,
) -> None:
    """Save Play Store credentials for future use."""
    data: dict[str, Any] = {"package_name": package_name}
    if credentials_path is not None:
        data["credentials_path"] = credentials_path
    _router().service_for(project_path).save_credentials(app, "play", data)


def _persist_app_store_credentials(
    project_path: str,
    app: str,
    app_id: str,
    key_id: str,
    issuer_id: str,
    private_key_path: str,
) -> None:
    """Save App Store credentials for future use."""
    _router().service_for(project_path).save_credentials(app, "app_store", {
        "app_id": app_id,
        "key_id": key_id,
        "issuer_id": issuer_id,
        "private_key_path": private_key_path,
    })


class BaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(
        default=".",
        description="Project path relative to MCP server root folder.",
        min_length=1,
    )
    app: str = Field(
        ...,
        min_length=1,
        description="App identifier as defined in listings.yaml, e.g. 'myapp' or 'prod'.",
    )
    store: StoreName = Field(
        ...,
        description=(
            "Target store: 'play' (Google Play) or 'app_store' (Apple App Store). "
            "Play Store keys: title, short_description, full_description. "
            "App Store keys: app_name, subtitle, description, keywords, promotional_text. "
            "Release notes are managed separately via release notes tools."
        ),
    )
    locale: str | None = Field(
        default=None,
        description=(
            "BCP-47 locale code, e.g. 'en-US', 'fr-FR'. "
            "When set, operates on locale-specific content. "
            "When omitted, operates on the global (shared across locales) section."
        ),
    )


class ProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(
        default=".",
        description="Project path relative to MCP server root folder.",
        min_length=1,
    )


class TransactionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(default=".", min_length=1)


class GetElementInput(BaseInput):
    key: str = Field(
        ...,
        min_length=1,
        description=(
            "Dotted key path to read. "
            "Play Store locale keys: title, short_description, full_description, whats_new. "
            "App Store locale keys: app_name, subtitle, description, keywords, promotional_text, whats_new. "
            "Nested paths supported, e.g. 'metadata.category'."
        ),
    )


class SetElementInput(GetElementInput):
    value: Any = Field(
        ...,
        description="The value to set at the key path. Can be a string, number, list, or object.",
    )


class DeleteElementInput(GetElementInput):
    pass


class ListSectionInput(BaseInput):
    jq: str | None = Field(
        default=None,
        description=(
            "Optional JQ expression to filter/reshape the result. "
            "Applied to the full {global: ..., locales: {...}} object. "
            "Examples: '.locales[\"en-US\"]' (single locale), "
            "'.locales | map_values(.title)' (all titles), "
            "'.global' (global section only), "
            "'{global, titles: .locales | map_values(.title)}' (custom shape)."
        ),
    )
    locales: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of locale codes to include. "
            "When set, only these locales are returned in the locales dict. "
            "Applied before the jq expression."
        ),
    )


class UpsertLocaleInput(BaseInput):
    locale: str = Field(
        ...,
        min_length=1,
        description="BCP-47 locale code to upsert, e.g. 'en-US'.",
    )
    data: dict[str, Any] = Field(
        ...,
        description=(
            "Key-value pairs to set on the locale. "
            "Play Store example: {title: 'My App', short_description: 'A great app', full_description: '...'}. "
            "App Store example: {app_name: 'My App', subtitle: 'Tagline', description: '...', keywords: 'a,b,c'}."
        ),
    )
    replace: bool = Field(
        default=False,
        description="If true, replaces the entire locale payload. If false (default), merges keys into existing data.",
    )


class InitListingInput(ProjectInput):
    app: str = Field(..., min_length=1)
    stores: list[StoreName] = Field(default_factory=lambda: ["play", "app_store"])
    locales: list[str] = Field(default_factory=list)
    baseline_locale: str | None = None
    overwrite: bool = False


class ListStoresInput(ProjectInput):
    app: str = Field(..., min_length=1)


class ListLanguagesInput(ProjectInput):
    app: str = Field(..., min_length=1)
    store: StoreName


class AddLanguageInput(ListLanguagesInput):
    locale: str = Field(..., min_length=1)
    copy_from_locale: str | None = None
    overwrite: bool = False


class DiffListingInput(BaseInput):
    compare_project_path: str = Field(..., min_length=1)
    compare_app: str | None = None
    compare_store: StoreName | None = None
    compare_locale: str | None = None


class SyncListingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_project_path: str = Field(..., min_length=1)
    target_project_path: str = Field(..., min_length=1)
    app: str = Field(..., min_length=1)
    store: StoreName
    locale: str | None = None
    mode: SyncMode = "merge"


class InitFromExistingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_project_path: str = Field(..., min_length=1)
    source_app: str = Field(..., min_length=1)
    source_store: StoreName
    target_project_path: str = Field(..., min_length=1)
    target_app: str = Field(..., min_length=1)
    target_store: StoreName
    locales: list[str] | None = None
    baseline_locale: str | None = None
    overwrite: bool = False


class VersioningInput(ProjectInput):
    app: str = Field(..., min_length=1)
    store: StoreName


class SetBaselineLanguageInput(VersioningInput):
    locale: str = Field(..., min_length=1)


class BumpVersionInput(VersioningInput):
    reason: str = Field(default="manual-bump", min_length=1)
    source_locale: str | None = None


class MarkLanguageUpdatedInput(VersioningInput):
    locale: str = Field(..., min_length=1)


class SaveSnapshotInput(VersioningInput):
    reason: str | None = Field(
        default=None,
        description="Optional reason for the snapshot. Defaults to 'manual-snapshot'.",
    )


class SnapshotInput(VersioningInput):
    version: int | None = Field(
        default=None,
        description="Snapshot version number. If omitted, uses the latest snapshot.",
    )


class ValidateListingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(default=".", min_length=1)
    app: str = Field(..., min_length=1)
    store: StoreName
    locales: list[str] | None = Field(
        default=None, description="Optional locale filter. Validates all if omitted.",
    )


class ReleaseNotesBaseInput(VersioningInput):
    app_version: str = Field(
        ...,
        min_length=1,
        description="App version string, e.g. '2.1.0'.",
    )


class SetReleaseNotesInput(ReleaseNotesBaseInput):
    locale: str = Field(..., min_length=1, description="BCP-47 locale code, e.g. 'en-US'.")
    text: str = Field(..., description="Release notes text for this locale.")


class UpsertReleaseNotesInput(ReleaseNotesBaseInput):
    data: dict[str, str] = Field(
        ...,
        description="Map of {locale: text} to set for this app version.",
    )


class GetReleaseNotesInput(ReleaseNotesBaseInput):
    locale: str | None = Field(
        default=None,
        description="If set, returns notes for this locale only. Otherwise returns all locales.",
    )


class ListReleaseVersionsInput(VersioningInput):
    pass


class DeleteReleaseNotesInput(ReleaseNotesBaseInput):
    pass


class DeleteLocaleInput(BaseInput):
    locale: str = Field(..., min_length=1, description="BCP-47 locale code to remove, e.g. 'fr-FR'.")


class DeleteProductInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(default=".", min_length=1)
    app: str = Field(..., min_length=1, description="App identifier as defined in listings.yaml.")
    store: StoreName = Field(..., description="Target store: 'play' or 'app_store'.")
    product_id: str = Field(..., min_length=1, description="Product or subscription ID to remove.")
    is_subscription: bool = Field(
        default=False,
        description="Set to true if the ID refers to a subscription rather than a one-time product.",
    )


class DeleteReleaseNotesLocaleInput(ReleaseNotesBaseInput):
    locale: str = Field(..., min_length=1, description="BCP-47 locale code to remove from this version's release notes.")


class ValidateReleaseNotesInput(VersioningInput):
    app_version: str | None = Field(
        default=None,
        description="Validate a specific version. If omitted, validates all versions.",
    )


class FetchPlayListingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(
        default=".",
        description="Project path relative to MCP server root folder.",
        min_length=1,
    )
    app: str = Field(..., min_length=1)
    package_name: str | None = Field(
        default=None,
        description="Android package name, e.g. com.example.app. Resolved from stored credentials if omitted.",
    )
    credentials_path: str | None = Field(
        default=None,
        description="Path to service account JSON file. Falls back to stored credentials or PLAY_SERVICE_ACCOUNT_JSON env var.",
    )
    locales: list[str] | None = Field(
        default=None,
        description="Optional list of locale codes to fetch. Fetches all if omitted.",
    )


class FetchAppStoreListingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(
        default=".",
        description="Project path relative to MCP server root folder.",
        min_length=1,
    )
    app: str = Field(..., min_length=1)
    app_id: str | None = Field(default=None, description="App Store app ID (numeric string). Resolved from stored credentials if omitted.")
    key_id: str | None = Field(default=None, description="App Store Connect API key ID. Resolved from stored credentials if omitted.")
    issuer_id: str | None = Field(default=None, description="App Store Connect issuer ID. Resolved from stored credentials if omitted.")
    private_key_path: str | None = Field(default=None, description="Path to .p8 private key file. Resolved from stored credentials if omitted.")
    platform: str = Field(default="IOS", description="Platform: IOS or MAC_OS")
    version_string: str | None = Field(
        default=None,
        description="App version to fetch (e.g. '2.1.0'). Required for version-level fields like description and keywords.",
    )
    locales: list[str] | None = Field(
        default=None,
        description="Optional list of locale codes to fetch. Fetches all if omitted.",
    )


class PushPlayListingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(default=".", min_length=1)
    app: str = Field(..., min_length=1)
    package_name: str | None = Field(default=None, description="Android package name. Resolved from stored credentials if omitted.")
    credentials_path: str | None = Field(default=None)
    locales: list[str] | None = Field(default=None)
    track: str = Field(default="production", description="Release track for release notes")
    version_code: int | None = Field(default=None, description="Version code for release notes")
    release_notes_version: str | None = Field(
        default=None,
        description="App version string to pull release notes from (e.g. '2.1.0'). If set, includes release notes.",
    )


class PushAppStoreListingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(default=".", min_length=1)
    app: str = Field(..., min_length=1)
    app_id: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    key_id: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    issuer_id: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    private_key_path: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    platform: str = Field(default="IOS")
    version_string: str = Field(..., min_length=1, description="Target version string")
    locales: list[str] | None = Field(default=None)
    only_whats_new: bool = Field(default=False, description="Only update What's New text")
    dry_run: bool = Field(default=False)
    release_notes_version: str | None = Field(
        default=None,
        description="App version string to pull release notes from (e.g. '2.1.0').",
    )


class PushPlayReleaseNotesInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(default=".", min_length=1)
    app: str = Field(..., min_length=1)
    package_name: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    credentials_path: str | None = Field(default=None)
    track: str = Field(default="production")
    version_code: int | None = Field(default=None, description="Version code to update release notes for. If omitted, the latest release on the track is used.")
    locales: list[str] | None = Field(default=None)
    release_notes_version: str | None = Field(
        default=None,
        description="App version string to pull release notes from (e.g. '2.1.0').",
    )


class PushPlayScreenshotsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(default=".", min_length=1)
    app: str | None = Field(default=None, description="App identifier for credential resolution.")
    package_name: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    credentials_path: str | None = Field(default=None)
    locale: str = Field(..., min_length=1, description="Play Store locale code")
    image_type: str = Field(..., min_length=1, description="e.g. phoneScreenshots, sevenInchScreenshots")
    file_paths: list[str] = Field(..., description="Absolute paths to screenshot files")
    replace: bool = Field(default=True, description="Delete existing screenshots before uploading")


class PushAppStoreScreenshotsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(default=".", min_length=1)
    app: str | None = Field(default=None, description="App identifier for credential resolution.")
    app_id: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    key_id: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    issuer_id: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    private_key_path: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    platform: str = Field(default="IOS")
    version_string: str = Field(..., min_length=1)
    locale: str = Field(..., min_length=1)
    display_type: str = Field(..., min_length=1, description="e.g. APP_IPHONE_67, APP_IPAD_PRO_3GEN_129")
    file_paths: list[str] = Field(..., description="Absolute paths to screenshot files")
    replace: bool = Field(default=True)


class PublishPlayBundleInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(default=".", min_length=1)
    app: str = Field(..., min_length=1)
    package_name: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    credentials_path: str | None = Field(default=None)
    bundle_path: str = Field(..., min_length=1, description="Path to .aab file")
    track: str = Field(default="internal")
    status: str = Field(default="draft", description="draft, inProgress, halted, or completed")
    mapping_path: str | None = Field(default=None, description="Path to ProGuard mapping file")
    locales: list[str] | None = Field(default=None, description="Locales for release notes")
    release_notes_version: str | None = Field(
        default=None,
        description="App version string to pull release notes from (e.g. '2.1.0').",
    )


class CreateAppStoreVersionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(default=".", min_length=1)
    app: str | None = Field(default=None, description="App identifier for credential resolution.")
    app_id: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    key_id: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    issuer_id: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    private_key_path: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    platform: str = Field(default="IOS")
    version_string: str = Field(..., min_length=1, description="Version to create, e.g. '2.1.0'")
    release_type: str = Field(default="MANUAL", description="MANUAL, AFTER_APPROVAL, or SCHEDULED")
    earliest_release_date: str | None = Field(default=None, description="ISO8601 date for SCHEDULED releases")


class SyncAppStoreIapInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(default=".", min_length=1)
    app: str | None = Field(default=None, description="App identifier for credential resolution.")
    app_id: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    key_id: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    issuer_id: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    private_key_path: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    products: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "List of {product_id, localizations: {locale: {name, description}}}. "
            "When omitted and app is provided, products are auto-loaded from the local listing."
        ),
    )
    delete_missing: bool = Field(
        default=False,
        description="When true, remote localizations not present locally are deleted from App Store Connect.",
    )


class SyncAppStoreSubscriptionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(default=".", min_length=1)
    app: str | None = Field(default=None, description="App identifier for credential resolution.")
    app_id: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    key_id: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    issuer_id: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    private_key_path: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    subscriptions: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "List of {product_id, localizations: {locale: {name, description}}}. "
            "When omitted and app is provided, subscriptions are auto-loaded from the local listing."
        ),
    )
    delete_missing: bool = Field(
        default=False,
        description="When true, remote localizations not present locally are deleted from App Store Connect.",
    )


class SyncPlayProductsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(default=".", min_length=1)
    app: str | None = Field(default=None, description="App identifier for credential resolution.")
    package_name: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    credentials_path: str | None = Field(default=None)
    products: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "List of {sku, default_price: {currency, price}, listings: {locale: {title, description}}, "
            "pricing: {country_code: {currency, price}}}. "
            "The optional 'pricing' field sets per-country prices using 2-letter ISO country codes (US, GB, CA, AU, …). "
            "Regional prices are applied automatically after the product is created/updated. "
            "When omitted and app is provided, products are auto-loaded from the local listing."
        ),
    )


class DeactivatePlayProductInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(default=".", min_length=1)
    app: str | None = Field(default=None, description="App identifier for credential resolution.")
    package_name: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    credentials_path: str | None = Field(default=None)
    sku: str = Field(..., min_length=1, description="Product SKU to deactivate.")


class ConfigureIapInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(default=".", min_length=1)
    app: str = Field(..., min_length=1, description="App identifier as defined in listings.yaml.")
    store: StoreName = Field(..., description="Target store: 'play' or 'app_store'.")
    products: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Map of product_id → product config dict. "
            "App Store: {\"type\": \"consumable\", \"localizations\": {\"en-US\": {\"name\": \"10 Credits\", \"description\": \"...\"}}, "
            "\"pricing\": {\"USA\": {\"currency\": \"USD\", \"price\": 1.99}, \"GBR\": {\"currency\": \"GBP\", \"price\": 1.79}, \"CAN\": {\"currency\": \"CAD\", \"price\": 2.49}}}. "
            "Play Store: {\"default_price\": {\"currency\": \"USD\", \"price\": 1.99}, \"listings\": {\"en-US\": {\"title\": \"10 Credits\", \"description\": \"...\"}}, "
            "\"pricing\": {\"GB\": {\"currency\": \"GBP\", \"price\": 1.79}, \"CA\": {\"currency\": \"CAD\", \"price\": 2.49}}}. "
            "Shorthand: use \"pricing_tiers\": {\"base_usd\": 1.99} instead of a manual \"pricing\" dict to auto-generate "
            "regional prices for 100+ countries via PPP tiers. "
            "For bundle ladders, add \"units\" and optional \"value_group\" inside \"pricing_tiers\" so larger packs "
            "keep a non-increasing price per unit across markets. "
            "Supports optional keys: \"live_rates\" (bool, default true), \"exchange_rate_overrides\" ({currency: rate}), "
            "\"include_tier5\" (bool), \"currency_overrides\" ({country: currency}), \"tier_overrides\" ({tier: config}). "
            "Locales not provided are auto-filled from the baseline locale. "
            "Play Store uses 2-letter country codes (US, GB, CA); App Store uses 3-letter codes (USA, GBR, CAN)."
        ),
    )
    subscriptions: dict[str, Any] = Field(
        default_factory=dict,
        description="Map of subscription_id → subscription config dict.",
    )
    merge: bool = Field(
        default=True,
        description="If true (default), merge with existing products. If false, replace the entire products/subscriptions section.",
    )


class SetIapPricingTiersInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(default=".", min_length=1)
    app: str = Field(..., min_length=1, description="App identifier as defined in listings.yaml.")
    store: StoreName = Field(..., description="Target store: 'play' or 'app_store'.")
    products: dict[str, dict[str, Any]] = Field(
        ...,
        description=(
            "Map of product_id → pricing spec. "
            "Each spec requires {base_usd}. "
            "Optional {units, value_group} lets the solver preserve bundle value ladders, "
            "e.g. {'com.app.credits_10': {'base_usd': 1.99, 'units': 10, 'value_group': 'credits'}}."
        ),
    )
    tier_overrides: dict[str, Any] | None = Field(
        default=None,
        description="Optional override for tier multipliers or country lists.",
    )
    include_tier5: bool = Field(
        default=False,
        description="Include Tier 5 (Emerging Markets, 0.25× price). Off by default.",
    )
    currency_overrides: dict[str, str] | None = Field(
        default=None,
        description="Optional {country_2letter: currency_code} overrides.",
    )
    live_rates: bool = Field(
        default=True,
        description=(
            "Fetch current exchange rates from open.er-api.com before calculating. "
            "Falls back to hardcoded rates on network failure. Default: true."
        ),
    )
    exchange_rate_overrides: dict[str, float] | None = Field(
        default=None,
        description=(
            "Optional {currency_code: rate} overrides applied on top of live/hardcoded rates. "
            "e.g. {\"JPY\": 155.0, \"EUR\": 0.88}. Takes highest priority."
        ),
    )
    countries: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of 2-letter country codes to include. "
            "When set, only these countries are priced; all others are skipped. "
            "e.g. [\"US\", \"GB\", \"CA\", \"AU\", \"DE\"]. "
            "Play Store uses 2-letter codes; App Store territory codes are derived automatically."
        ),
    )


class GetAppStoreAppIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    bundle_id: str = Field(..., min_length=1, description="The app's bundle ID, e.g. 'me.jodoin.plantmatch'.")
    key_id: str = Field(..., min_length=1, description="App Store Connect API key ID.")
    issuer_id: str = Field(..., min_length=1, description="App Store Connect API issuer ID.")
    private_key_path: str = Field(..., min_length=1, description="Path to the .p8 private key file.")


class SyncPlayPricingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(default=".", min_length=1)
    app: str | None = Field(default=None, description="App identifier for credential resolution.")
    package_name: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    credentials_path: str | None = Field(default=None)
    sku: str = Field(..., min_length=1, description="Product SKU")
    regional_prices: dict[str, dict[str, Any]] = Field(
        ...,
        description='Map of {country_code: {currency, price}}',
    )


class SyncPlaySubscriptionPricingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str = Field(default=".", min_length=1)
    app: str | None = Field(default=None, description="App identifier for credential resolution.")
    package_name: str | None = Field(default=None, description="Resolved from stored credentials if omitted.")
    credentials_path: str | None = Field(default=None)
    subscription_id: str = Field(..., min_length=1)
    base_plan_id: str = Field(..., min_length=1)
    regional_prices: dict[str, dict[str, Any]] = Field(
        ...,
        description='Map of {region_code: {currency, price}}',
    )


@mcp.tool(
    name="perfectdeck_begin_transaction",
    annotations={
        "title": "Begin Transaction",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def perfectdeck_begin_transaction(params: TransactionInput) -> str:
    """Start a transaction — all listing mutations are buffered in memory.

    Call perfectdeck_commit_transaction to persist or perfectdeck_rollback_transaction to discard.
    Raises if a transaction is already active.

    Returns: {"ok": true}
    """
    _router().service_for(params.project_path).begin_transaction()
    return _result({"ok": True}, "perfectdeck_begin_transaction")


@mcp.tool(
    name="perfectdeck_commit_transaction",
    annotations={
        "title": "Commit Transaction",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def perfectdeck_commit_transaction(params: TransactionInput) -> str:
    """Flush all buffered listing mutations to disk and end the transaction.

    Raises if no transaction is active.

    Returns: {"ok": true}
    """
    _router().service_for(params.project_path).commit_transaction()
    return _result({"ok": True}, "perfectdeck_commit_transaction")


@mcp.tool(
    name="perfectdeck_rollback_transaction",
    annotations={
        "title": "Rollback Transaction",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def perfectdeck_rollback_transaction(params: TransactionInput) -> str:
    """Discard all buffered listing mutations and end the transaction. The file on disk is unchanged.

    Raises if no transaction is active.

    Returns: {"ok": true}
    """
    _router().service_for(params.project_path).rollback_transaction()
    return _result({"ok": True}, "perfectdeck_rollback_transaction")


@mcp.tool(
    name="perfectdeck_get_element",
    annotations={
        "title": "Get Listing Element",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_get_element(params: GetElementInput) -> str:
    """Read a single value from the listing by dotted key path.

    Set `locale` to read locale-specific content (e.g. title, description),
    or omit it to read from the global section shared across locales.

    Returns: {"ok": true, "value": <the value>}
    """
    service = _router().service_for(params.project_path)
    result = service.get_element(
        app=params.app,
        store=params.store,
        key_path=params.key,
        locale=params.locale,
    )
    return _result({"ok": True, "value": result}, "perfectdeck_get_element")


@mcp.tool(
    name="perfectdeck_set_element",
    annotations={
        "title": "Set Listing Element",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_set_element(params: SetElementInput) -> str:
    """Create or update a single value in the listing by dotted key path.

    Set `locale` to write locale-specific content (e.g. title, description),
    or omit it to write to the global section. Intermediate keys are created
    automatically. This is the primary tool for adding and updating listing fields.

    Examples:
      - Set Play Store title for en-US: key="title", value="My App", locale="en-US", store="play"
      - Set App Store subtitle: key="subtitle", value="Best app ever", locale="en-US", store="app_store"
      - Set global metadata: key="metadata.category", value="productivity", locale=null

    Returns: {"ok": true}
    """
    service = _router().service_for(params.project_path)
    out = service.set_element(
        app=params.app,
        store=params.store,
        key_path=params.key,
        value=params.value,
        locale=params.locale,
    )
    return _result(out, "perfectdeck_set_element")


@mcp.tool(
    name="perfectdeck_delete_element",
    annotations={
        "title": "Delete Listing Element",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_delete_element(params: DeleteElementInput) -> str:
    """Remove a single key from the listing by dotted key path.

    Set `locale` to delete from locale-specific content, or omit it to
    delete from the global section.

    Returns: {"ok": true, "deleted": true/false}
    """
    service = _router().service_for(params.project_path)
    out = service.delete_element(
        app=params.app,
        store=params.store,
        key_path=params.key,
        locale=params.locale,
    )
    return _result(out, "perfectdeck_delete_element")


@mcp.tool(
    name="perfectdeck_delete_locale",
    annotations={
        "title": "Delete Locale",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_delete_locale(params: DeleteLocaleInput) -> str:
    """Remove an entire locale and all its content from an app/store listing.

    Also removes the locale from version tracking. This is irreversible locally
    (use perfectdeck_save_snapshot first if you want a rollback point).

    Returns: {"ok": true, "deleted": true/false, "locale": "..."}
    """
    service = _router().service_for(params.project_path)
    out = service.delete_locale(app=params.app, store=params.store, locale=params.locale)
    out["remaining_languages"] = service.list_languages(app=params.app, store=params.store)
    return _result(out, "perfectdeck_delete_locale")


@mcp.tool(
    name="perfectdeck_delete_product",
    annotations={
        "title": "Delete Product or Subscription",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_delete_product(params: DeleteProductInput) -> str:
    """Remove a single IAP product or subscription from the local listing by its ID.

    Set is_subscription=true to remove from the subscriptions section.
    Does not push to any store — use sync tools after to propagate changes.

    Returns: {"ok": true, "deleted": true/false, "product_id": "..."}
    """
    service = _router().service_for(params.project_path)
    out = service.delete_product(
        app=params.app,
        store=params.store,
        product_id=params.product_id,
        is_subscription=params.is_subscription,
    )
    return _result(out, "perfectdeck_delete_product")


@mcp.tool(
    name="perfectdeck_upsert_locale",
    annotations={
        "title": "Upsert Locale Payload",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_upsert_locale(params: UpsertLocaleInput) -> str:
    """Set multiple keys on a locale in one operation (batch update).

    Use this instead of multiple set_element calls when writing several
    fields at once. With replace=false (default), only the provided keys
    are updated; with replace=true, the entire locale payload is replaced.

    Example data for Play Store: {"title": "My App", "short_description": "Great app", "full_description": "..."}
    Example data for App Store: {"app_name": "My App", "subtitle": "Tagline", "description": "...", "keywords": "a,b,c"}

    Returns: {"ok": true}
    """
    service = _router().service_for(params.project_path)
    out = service.upsert_locale(
        app=params.app,
        store=params.store,
        locale=params.locale,
        data=params.data,
        replace=params.replace,
    )
    return _result(out, "perfectdeck_upsert_locale")


@mcp.tool(
    name="perfectdeck_list_section",
    annotations={
        "title": "List Section",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_list_section(params: ListSectionInput) -> str:
    """Read listing content for one app/store, with optional filtering.

    If `locale` is set, returns only that locale's key-value data.
    If `locale` is omitted, returns both `global` and all `locales` data.

    Use `locales` to limit which locales are included (e.g. ["en-US", "fr-FR"]).
    Use `jq` to filter/reshape the result with a JQ expression:
      jq='.locales["en-US"]'              → single locale
      jq='.locales | map_values(.title)'  → all titles only
      jq='.global'                        → just global settings
      jq='{global, titles: .locales | map_values(.title)}'  → custom shape

    Returns: {"ok": true, "data": <result>}
    """
    service = _router().service_for(params.project_path)
    out = service.list_section(app=params.app, store=params.store, locale=params.locale)

    # Apply locales filter (narrow locale dict before jq)
    if params.locales is not None and isinstance(out, dict) and "locales" in out:
        allowed = set(params.locales)
        out["locales"] = {k: v for k, v in out["locales"].items() if k in allowed}

    # Apply jq expression
    if params.jq is not None:
        import jq

        try:
            result = jq.first(params.jq, out)
        except ValueError as exc:
            return json.dumps(
                {"ok": False, "error": f"Invalid jq expression: {exc}"},
                ensure_ascii=False,
            )
        return _result({"ok": True, "data": result}, "perfectdeck_list_section")

    return _result({"ok": True, "data": out}, "perfectdeck_list_section")


@mcp.tool(
    name="perfectdeck_init_listing",
    annotations={
        "title": "Initialize Listing",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_init_listing(params: InitListingInput) -> str:
    """Create a new app listing structure in the project's listings.yaml file.

    This is the first step: it creates empty store sections for the given app
    with optional locales and a baseline language for translation tracking.
    After init, use set_element or upsert_locale to populate content.

    Returns: {"ok": true, "initialized_stores": [...], "stores": [...]}
    """
    service = _router().service_for(params.project_path)
    out = service.init_listing(
        app=params.app,
        stores=params.stores,
        locales=params.locales,
        baseline_locale=params.baseline_locale,
        overwrite=params.overwrite,
    )
    initialized = out.get("initialized_stores", [])
    out["store_fields"] = {s: _STORE_FIELD_LIMITS[s] for s in initialized if s in _STORE_FIELD_LIMITS}
    parts = []
    for s in initialized:
        lim = _STORE_FIELD_LIMITS.get(s)
        if lim:
            label = "Play Store" if s == "play" else "App Store"
            parts.append(f"{label}: {', '.join(f'{k} ({v})' for k, v in lim.items())}")
    out["hint"] = (
        "Listing created. Populate with perfectdeck_upsert_locale (batch) or "
        "perfectdeck_set_element (single field). " + " | ".join(parts)
    )
    return _result(out, "perfectdeck_init_listing")


@mcp.tool(
    name="perfectdeck_list_apps",
    annotations={
        "title": "List Apps",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_list_apps(params: ProjectInput) -> str:
    """List all app identifiers defined in the project's listings.yaml.

    Returns: {"ok": true, "apps": ["myapp", "prod", ...]}
    """
    service = _router().service_for(params.project_path)
    return _result({"ok": True, "apps": service.list_apps()}, "perfectdeck_list_apps")


@mcp.tool(
    name="perfectdeck_list_stores",
    annotations={
        "title": "List Stores",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_list_stores(params: ListStoresInput) -> str:
    """List which stores (play, app_store) are configured for a given app.

    Returns: {"ok": true, "stores": ["app_store", "play"]}
    """
    service = _router().service_for(params.project_path)
    return _result({"ok": True, "stores": service.list_stores(params.app)}, "perfectdeck_list_stores")


@mcp.tool(
    name="perfectdeck_list_languages",
    annotations={
        "title": "List Languages",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_list_languages(params: ListLanguagesInput) -> str:
    """List all locale codes configured for an app/store (e.g. en-US, fr-FR, ja).

    Returns: {"ok": true, "languages": ["en-US", "fr-FR", ...]}
    """
    service = _router().service_for(params.project_path)
    return _result(
        {"ok": True, "languages": service.list_languages(app=params.app, store=params.store)},
        "perfectdeck_list_languages",
    )


@mcp.tool(
    name="perfectdeck_add_language",
    annotations={
        "title": "Add Language",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_add_language(params: AddLanguageInput) -> str:
    """Add a new locale to an app/store listing.

    Optionally copy initial content from an existing locale using copy_from_locale.
    After adding, use set_element or upsert_locale to customize the content.

    Returns: {"ok": true, "created": true/false, "locale": "...", "store_fields": {...}, "missing_fields": [...]}
    """
    service = _router().service_for(params.project_path)
    out = service.add_language(
        app=params.app,
        store=params.store,
        locale=params.locale,
        copy_from_locale=params.copy_from_locale,
        overwrite=params.overwrite,
    )

    # Contextual info for the agent
    locale_data = service.list_section(app=params.app, store=params.store, locale=params.locale)
    current_fields = sorted(locale_data.keys()) if isinstance(locale_data, dict) else []
    limits = _STORE_FIELD_LIMITS.get(params.store, {})

    out["current_fields"] = current_fields
    out["all_languages"] = service.list_languages(app=params.app, store=params.store)
    out["store_fields"] = limits
    out["missing_fields"] = [f for f in limits if f not in current_fields]

    if params.copy_from_locale:
        out["hint"] = (
            f"Content copied from '{params.copy_from_locale}'. Translate each field, "
            "then perfectdeck_mark_language_updated. Validate with perfectdeck_validate_listing."
        )
    else:
        out["hint"] = (
            "Locale is empty. Use perfectdeck_upsert_locale (batch) or perfectdeck_set_element "
            "(single field). Validate with perfectdeck_validate_listing."
        )

    return _result(out, "perfectdeck_add_language")


@mcp.tool(
    name="perfectdeck_diff_listing",
    annotations={
        "title": "Diff Listing",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_diff_listing(params: DiffListingInput) -> str:
    """Compare two listing sections across projects, apps, or stores (read-only).

    Shows added, removed, and changed keys between the source and comparison listing.

    Returns: {"ok": true, "diff": {added, removed, changed, same}}
    """
    source_service = _router().service_for(params.project_path)
    compare_service = _router().service_for(params.compare_project_path)

    left = source_service.list_section(
        app=params.app,
        store=params.store,
        locale=params.locale,
    )
    right = compare_service.list_section(
        app=params.compare_app or params.app,
        store=params.compare_store or params.store,
        locale=params.compare_locale if params.compare_locale is not None else params.locale,
    )
    diff = diff_objects(left, right)
    diff["same"] = not diff["added"] and not diff["removed"] and not diff["changed"]
    return _result({"ok": True, "diff": diff}, "perfectdeck_diff_listing")


@mcp.tool(
    name="perfectdeck_sync_listing",
    annotations={
        "title": "Sync Listing",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_sync_listing(params: SyncListingInput) -> str:
    """Copy listing data from one project to another (merge or replace).

    Use mode='merge' to add/overwrite keys without removing existing ones,
    or mode='replace' to fully replace the target section.

    Returns: {"ok": true, "source_project_path": "...", "target_project_path": "...", "mode": "merge"}
    """
    source_service = _router().service_for(params.source_project_path)
    target_service = _router().service_for(params.target_project_path)
    payload = source_service.list_section(
        app=params.app,
        store=params.store,
        locale=params.locale,
    )
    out = target_service.replace_section(
        app=params.app,
        store=params.store,
        payload=payload,
        locale=params.locale,
        merge=(params.mode == "merge"),
    )
    return _result(
        {
            "ok": bool(out.get("ok")),
            "source_project_path": params.source_project_path,
            "target_project_path": params.target_project_path,
            "mode": params.mode,
        },
        "perfectdeck_sync_listing",
    )


@mcp.tool(
    name="perfectdeck_init_from_existing",
    annotations={
        "title": "Init From Existing Listing",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_init_from_existing(params: InitFromExistingInput) -> str:
    """Create a new listing by cloning data from an existing source listing.

    Copies global data and selected locales, sets version to 1, and optionally
    sets a baseline locale. Use this to bootstrap a new app/store from existing content.

    Returns: {"ok": true, "target_app": "...", "locales_copied": [...], "baseline_locale": "..."}
    """
    source_service = _router().service_for(params.source_project_path)
    target_service = _router().service_for(params.target_project_path)
    source_section = source_service.list_section(
        app=params.source_app,
        store=params.source_store,
        locale=None,
    )
    out = target_service.init_from_existing_section(
        target_app=params.target_app,
        target_store=params.target_store,
        source_section=source_section,
        overwrite=params.overwrite,
        locales=params.locales,
        baseline_locale=params.baseline_locale,
    )
    return _result(out, "perfectdeck_init_from_existing")


@mcp.tool(
    name="perfectdeck_set_baseline_language",
    annotations={
        "title": "Set Baseline Language",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_set_baseline_language(params: SetBaselineLanguageInput) -> str:
    """Set the baseline (source) language for translation tracking.

    When the baseline locale is edited, the version is bumped automatically
    and all other locales become 'stale' until marked as updated.

    Returns: {"ok": true, "baseline_locale": "en-US"}
    """
    service = _router().service_for(params.project_path)
    out = service.set_baseline_locale(app=params.app, store=params.store, locale=params.locale)
    return _result(out, "perfectdeck_set_baseline_language")


@mcp.tool(
    name="perfectdeck_bump_version",
    annotations={
        "title": "Bump Listing Version",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def perfectdeck_bump_version(params: BumpVersionInput) -> str:
    """Manually bump the listing version and record a change reason.

    This also creates a snapshot of the current state before bumping.
    All non-baseline locales become stale after a bump. Use this when
    content has changed and translations need updating.

    Returns: {"ok": true, "current_version": 3}
    """
    service = _router().service_for(params.project_path)
    out = service.bump_version(
        app=params.app,
        store=params.store,
        reason=params.reason,
        source_locale=params.source_locale,
    )
    return _result(out, "perfectdeck_bump_version")


@mcp.tool(
    name="perfectdeck_mark_language_updated",
    annotations={
        "title": "Mark Language Updated",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_mark_language_updated(params: MarkLanguageUpdatedInput) -> str:
    """Mark a locale's translation as up-to-date with the current version.

    Call this after translating a locale to clear its 'stale' status.

    Returns: {"ok": true, "locale": "fr-FR", "version": 3}
    """
    service = _router().service_for(params.project_path)
    out = service.mark_language_updated(app=params.app, store=params.store, locale=params.locale)
    return _result(out, "perfectdeck_mark_language_updated")


@mcp.tool(
    name="perfectdeck_get_update_status",
    annotations={
        "title": "Get Update Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_get_update_status(params: VersioningInput) -> str:
    """Check which locales are stale (need translation) vs up-to-date.

    Shows current version, baseline locale, stale/up-to-date/missing locales,
    and recent changelog entries.

    Returns: {"ok": true, "status": {current_version, baseline_locale, stale_locales, up_to_date_locales, ...}}
    """
    service = _router().service_for(params.project_path)
    out = service.get_update_status(app=params.app, store=params.store)
    return _result({"ok": True, "status": out}, "perfectdeck_get_update_status")


@mcp.tool(
    name="perfectdeck_save_snapshot",
    annotations={
        "title": "Save Listing Snapshot",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_save_snapshot(params: SaveSnapshotInput) -> str:
    """Save the current listing state as a versioned snapshot.

    Creates an immutable copy of global + locales data at the current version.
    Snapshots are also created automatically on bump_version and remote sync.
    Use this for explicit checkpoints (e.g. before large edits).

    Returns: {"ok": true, "version": 2}
    """
    service = _router().service_for(params.project_path)
    out = service.save_snapshot(app=params.app, store=params.store, reason=params.reason)
    return _result(out, "perfectdeck_save_snapshot")


@mcp.tool(
    name="perfectdeck_list_snapshots",
    annotations={
        "title": "List Snapshots",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_list_snapshots(params: VersioningInput) -> str:
    """List all available version snapshots for an app/store.

    Returns: {"ok": true, "snapshots": [{version, timestamp, reason}, ...]}
    """
    service = _router().service_for(params.project_path)
    snapshots = service.list_snapshots(app=params.app, store=params.store)
    return _result({"ok": True, "snapshots": snapshots}, "perfectdeck_list_snapshots")


@mcp.tool(
    name="perfectdeck_restore_snapshot",
    annotations={
        "title": "Restore Snapshot",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
def perfectdeck_restore_snapshot(params: SnapshotInput) -> str:
    """Restore listing data from a version snapshot, replacing current global + locales.

    If version is omitted, restores from the latest snapshot. Bumps the version
    and records 'restore-from-v{N}' in the changelog. Snapshot files are never modified.

    Returns: {"ok": true, "restored_version": 2, "current_version": 5}
    """
    service = _router().service_for(params.project_path)
    out = service.restore_snapshot(app=params.app, store=params.store, version=params.version)
    return _result(out, "perfectdeck_restore_snapshot")


@mcp.tool(
    name="perfectdeck_diff_snapshot",
    annotations={
        "title": "Diff Against Snapshot",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_diff_snapshot(params: SnapshotInput) -> str:
    """Compare current listing data against a version snapshot (read-only).

    If version is omitted, diffs against the latest snapshot. Shows added keys,
    removed keys, and changed values between the snapshot and current state.

    Returns: {"ok": true, "snapshot_version": 2, "diff": {added, removed, changed, same}}
    """
    service = _router().service_for(params.project_path)
    out = service.diff_with_snapshot(app=params.app, store=params.store, version=params.version)
    return _result({"ok": True, **out}, "perfectdeck_diff_snapshot")


def _fetch_play_remote(
    package_name: str,
    credentials_path: str | None,
    locales: list[str] | None = None,
) -> dict:
    """Shared helper: authenticate and fetch remote Play Store listings."""
    service_api = play_store_api.create_service(
        credentials_path=credentials_path,
    )
    result = play_store_api.fetch_listings(
        service=service_api,
        package_name=package_name,
        locales=locales,
    )
    # Fetch products and subscriptions (failures are non-fatal)
    try:
        result["products"] = play_store_api.fetch_products(
            service=service_api, package_name=package_name,
        )
    except Exception:
        logger.warning("Failed to fetch Play products", exc_info=True)
    try:
        result["subscriptions"] = play_store_api.fetch_subscriptions(
            service=service_api, package_name=package_name,
        )
    except Exception:
        logger.warning("Failed to fetch Play subscriptions", exc_info=True)
    return result


def _fetch_app_store_remote(
    app_id: str,
    key_id: str,
    issuer_id: str,
    private_key_path: str,
    platform: str = "IOS",
    version_string: str | None = None,
    locales: list[str] | None = None,
) -> dict:
    """Shared helper: authenticate and fetch remote App Store listings."""
    client = app_store_api.AppStoreConnectClient.from_key_file(
        key_id=key_id,
        issuer_id=issuer_id,
        private_key_path=private_key_path,
    )
    result = app_store_api.fetch_listings(
        client=client,
        app_id=app_id,
        platform=platform,
        version_string=version_string,
        locales=locales,
    )
    # Fetch IAP and subscriptions (failures are non-fatal)
    try:
        iap_data = app_store_api.fetch_iap_and_subscriptions(
            client=client, app_id=app_id,
        )
        result["products"] = iap_data.get("products", {})
        result["subscriptions"] = iap_data.get("subscriptions", {})
    except Exception:
        pass
    return result


@mcp.tool(
    name="perfectdeck_diff_play_listing",
    annotations={
        "title": "Diff Play Store Listing",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def perfectdeck_diff_play_listing(params: FetchPlayListingInput) -> str:
    """Fetch current listings from Google Play and diff against local listing (read-only preview)."""
    pkg, creds = _resolve_play_credentials(params.project_path, params.app, params.package_name, params.credentials_path)
    remote_data = _fetch_play_remote(pkg, creds, params.locales)
    locales_data = remote_data.get("locales", {})
    service = _router().service_for(params.project_path)
    out = service.diff_with_play_store_data(app=params.app, data=locales_data)
    out["fetched_locales"] = sorted(locales_data.keys())
    _persist_play_credentials(params.project_path, params.app, pkg, creds)
    return _result({"ok": True, **out}, "perfectdeck_diff_play_listing")


@mcp.tool(
    name="perfectdeck_diff_app_store_listing",
    annotations={
        "title": "Diff App Store Listing",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def perfectdeck_diff_app_store_listing(params: FetchAppStoreListingInput) -> str:
    """Fetch current listings from App Store Connect and diff against local listing (read-only preview)."""
    r_app_id, r_key_id, r_issuer_id, r_pk = _resolve_app_store_credentials(
        params.project_path, params.app, params.app_id, params.key_id, params.issuer_id, params.private_key_path,
    )
    remote_data = _fetch_app_store_remote(r_app_id, r_key_id, r_issuer_id, r_pk, params.platform, params.version_string, params.locales)
    locales_data = remote_data.get("locales", {})
    service = _router().service_for(params.project_path)
    out = service.diff_with_app_store_data(app=params.app, data=locales_data)
    out["fetched_locales"] = sorted(locales_data.keys())
    _persist_app_store_credentials(params.project_path, params.app, r_app_id, r_key_id, r_issuer_id, r_pk)
    return _result({"ok": True, **out}, "perfectdeck_diff_app_store_listing")


@mcp.tool(
    name="perfectdeck_sync_play_listing",
    annotations={
        "title": "Sync Play Store Listing",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def perfectdeck_sync_play_listing(params: FetchPlayListingInput) -> str:
    """Fetch current listings from Google Play and import them into the local listing."""
    pkg, creds = _resolve_play_credentials(params.project_path, params.app, params.package_name, params.credentials_path)
    remote_data = _fetch_play_remote(pkg, creds, params.locales)
    service = _router().service_for(params.project_path)
    global_data = remote_data.get("global", {})
    locales_data = remote_data.get("locales", {})
    products_data = remote_data.get("products")
    subscriptions_data = remote_data.get("subscriptions")
    out = service.import_from_play_store(
        app=params.app,
        data=locales_data,
        global_data=global_data,
        products_data=products_data if products_data else None,
        subscriptions_data=subscriptions_data if subscriptions_data else None,
    )
    out["fetched_locales"] = sorted(locales_data.keys())
    if products_data:
        out["products_count"] = len(products_data)
    if subscriptions_data:
        out["subscriptions_count"] = len(subscriptions_data)
    _persist_play_credentials(params.project_path, params.app, pkg, creds)
    return _result(out, "perfectdeck_sync_play_listing")


@mcp.tool(
    name="perfectdeck_sync_app_store_listing",
    annotations={
        "title": "Sync App Store Listing",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def perfectdeck_sync_app_store_listing(params: FetchAppStoreListingInput) -> str:
    """Fetch current listings from App Store Connect and import them into the local listing."""
    r_app_id, r_key_id, r_issuer_id, r_pk = _resolve_app_store_credentials(
        params.project_path, params.app, params.app_id, params.key_id, params.issuer_id, params.private_key_path,
    )
    remote_data = _fetch_app_store_remote(r_app_id, r_key_id, r_issuer_id, r_pk, params.platform, params.version_string, params.locales)
    service = _router().service_for(params.project_path)
    global_data = remote_data.get("global", {})
    locales_data = remote_data.get("locales", {})
    products_data = remote_data.get("products")
    subscriptions_data = remote_data.get("subscriptions")
    out = service.import_from_app_store(
        app=params.app,
        data=locales_data,
        global_data=global_data,
        products_data=products_data if products_data else None,
        subscriptions_data=subscriptions_data if subscriptions_data else None,
    )
    out["fetched_locales"] = sorted(locales_data.keys())
    if products_data:
        out["products_count"] = len(products_data)
    if subscriptions_data:
        out["subscriptions_count"] = len(subscriptions_data)
    _persist_app_store_credentials(params.project_path, params.app, r_app_id, r_key_id, r_issuer_id, r_pk)
    return _result(out, "perfectdeck_sync_app_store_listing")


# ======================================================================
# Release Notes
# ======================================================================


@mcp.tool(
    name="perfectdeck_set_release_notes",
    annotations={
        "title": "Set Release Notes",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_set_release_notes(params: SetReleaseNotesInput) -> str:
    """Set release notes text for one app version and locale.

    Release notes are stored independently from listing data and never
    affect listing versioning or translation tracking.

    Returns: {"ok": true}
    """
    service = _router().service_for(params.project_path)
    out = service.set_release_notes(
        app=params.app,
        store=params.store,
        app_version=params.app_version,
        locale=params.locale,
        text=params.text,
    )
    return _result(out, "perfectdeck_set_release_notes")


@mcp.tool(
    name="perfectdeck_upsert_release_notes",
    annotations={
        "title": "Upsert Release Notes",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_upsert_release_notes(params: UpsertReleaseNotesInput) -> str:
    """Batch set release notes for one app version across multiple locales.

    Merges the provided {locale: text} map into existing notes for this version.
    Does not affect listing versioning.

    Returns: {"ok": true}
    """
    service = _router().service_for(params.project_path)
    out = service.upsert_release_notes(
        app=params.app,
        store=params.store,
        app_version=params.app_version,
        data=params.data,
    )
    return _result(out, "perfectdeck_upsert_release_notes")


@mcp.tool(
    name="perfectdeck_get_release_notes",
    annotations={
        "title": "Get Release Notes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_get_release_notes(params: GetReleaseNotesInput) -> str:
    """Read release notes for a specific app version.

    If locale is set, returns the text for that locale only.
    If locale is omitted, returns all locales for the version.

    Returns: {"ok": true, ...} with app_version, locale/text or notes map.
    """
    service = _router().service_for(params.project_path)
    out = service.get_release_notes(
        app=params.app,
        store=params.store,
        app_version=params.app_version,
        locale=params.locale,
    )
    return _result({"ok": True, **out}, "perfectdeck_get_release_notes")


@mcp.tool(
    name="perfectdeck_list_release_versions",
    annotations={
        "title": "List Release Versions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_list_release_versions(params: ListReleaseVersionsInput) -> str:
    """List all app versions that have release notes stored.

    Returns: {"ok": true, "versions": ["2.0.0", "2.1.0"]}
    """
    service = _router().service_for(params.project_path)
    versions = service.list_release_versions(app=params.app, store=params.store)
    return _result({"ok": True, "versions": versions}, "perfectdeck_list_release_versions")


@mcp.tool(
    name="perfectdeck_delete_release_notes",
    annotations={
        "title": "Delete Release Notes",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_delete_release_notes(params: DeleteReleaseNotesInput) -> str:
    """Delete all release notes for a specific app version.

    Does not affect listing versioning.

    Returns: {"ok": true, "deleted": true/false}
    """
    service = _router().service_for(params.project_path)
    out = service.delete_release_notes(
        app=params.app,
        store=params.store,
        app_version=params.app_version,
    )
    return _result(out, "perfectdeck_delete_release_notes")


@mcp.tool(
    name="perfectdeck_delete_release_notes_locale",
    annotations={
        "title": "Delete Release Notes for One Locale",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_delete_release_notes_locale(params: DeleteReleaseNotesLocaleInput) -> str:
    """Remove release notes for a single locale from a specific app version.

    Use this to drop one language's notes without affecting the other locales
    in the same version.

    Returns: {"ok": true, "deleted": true/false, "app_version": "...", "locale": "..."}
    """
    service = _router().service_for(params.project_path)
    out = service.delete_release_notes_locale(
        app=params.app,
        store=params.store,
        app_version=params.app_version,
        locale=params.locale,
    )
    return _result(out, "perfectdeck_delete_release_notes_locale")


@mcp.tool(
    name="perfectdeck_validate_release_notes",
    annotations={
        "title": "Validate Release Notes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_validate_release_notes(params: ValidateReleaseNotesInput) -> str:
    """Validate release notes against character limits and locale sync.

    Checks: Play Store max 500 chars, App Store max 4000 chars.
    Reports locales in release notes missing from listing (extra_locales)
    and listing locales missing from release notes (missing_locales).

    Returns: {"ok": true/false, "versions": {"2.1.0": {ok, errors, missing_locales, extra_locales}}}
    """
    service = _router().service_for(params.project_path)
    out = service.validate_release_notes(
        app=params.app,
        store=params.store,
        app_version=params.app_version,
    )
    return _result(out, "perfectdeck_validate_release_notes")


# ======================================================================
# Validation
# ======================================================================


@mcp.tool(
    name="perfectdeck_validate_listing",
    annotations={
        "title": "Validate Listing",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_validate_listing(params: ValidateListingInput) -> str:
    """Check listing fields against store character limits.

    Play Store limits: title (30), short_description (80), full_description (4000).
    App Store limits: app_name (30), subtitle (30), description (4000), keywords (100),
    promotional_text (170).

    Release notes (whats_new) are validated separately via perfectdeck_validate_release_notes.

    Returns: {"ok": true/false, "errors": [{locale, field, length, limit, message}, ...]}
    """
    service = _router().service_for(params.project_path)
    out = service.validate_listing(
        app=params.app, store=params.store, locales=params.locales,
    )
    return _result(out, "perfectdeck_validate_listing")


# ======================================================================
# Push to Play Store
# ======================================================================


@mcp.tool(
    name="perfectdeck_push_play_listing",
    annotations={
        "title": "Push Play Store Listing",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def perfectdeck_push_play_listing(params: PushPlayListingInput) -> str:
    """Push local listing metadata to Google Play Store."""
    pkg, creds = _resolve_play_credentials(params.project_path, params.app, params.package_name, params.credentials_path)
    service = _router().service_for(params.project_path)
    push_data = service.prepare_play_push_data(app=params.app, locales=params.locales)

    release_notes = None
    if params.release_notes_version:
        release_notes = service.prepare_play_release_notes(
            app=params.app,
            app_version=params.release_notes_version,
            locales=params.locales,
        )

    api = play_store_api.create_service(credentials_path=creds)
    out = play_store_api.push_listings(
        service=api,
        package_name=pkg,
        locales_data=push_data,
        release_notes=release_notes,
        track=params.track,
        version_code=params.version_code,
    )
    _persist_play_credentials(params.project_path, params.app, pkg, creds)
    return _result(out, "perfectdeck_push_play_listing")


@mcp.tool(
    name="perfectdeck_push_play_release_notes",
    annotations={
        "title": "Push Play Release Notes",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def perfectdeck_push_play_release_notes(params: PushPlayReleaseNotesInput) -> str:
    """Push release notes from local listing to a Play Store track."""
    if not params.release_notes_version:
        return json.dumps({"ok": False, "error": "release_notes_version is required"}, ensure_ascii=False)
    pkg, creds = _resolve_play_credentials(params.project_path, params.app, params.package_name, params.credentials_path)
    service = _router().service_for(params.project_path)
    release_notes = service.prepare_play_release_notes(
        app=params.app,
        app_version=params.release_notes_version,
        locales=params.locales,
    )
    api = play_store_api.create_service(credentials_path=creds)
    out = play_store_api.update_release_notes(
        service=api,
        package_name=pkg,
        track=params.track,
        version_code=params.version_code,
        release_notes=release_notes,
    )
    _persist_play_credentials(params.project_path, params.app, pkg, creds)
    return _result(out, "perfectdeck_push_play_release_notes")


@mcp.tool(
    name="perfectdeck_push_play_screenshots",
    annotations={
        "title": "Push Play Screenshots",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def perfectdeck_push_play_screenshots(params: PushPlayScreenshotsInput) -> str:
    """Upload screenshots to Google Play for one locale and image type."""
    if params.app:
        pkg, creds = _resolve_play_credentials(params.project_path, params.app, params.package_name, params.credentials_path)
    else:
        if not params.package_name:
            raise ValueError("package_name is required when app is not set for credential resolution.")
        pkg, creds = params.package_name, params.credentials_path
    api = play_store_api.create_service(credentials_path=creds)
    out = play_store_api.upload_screenshots(
        service=api,
        package_name=pkg,
        locale=params.locale,
        image_type=params.image_type,
        file_paths=params.file_paths,
        replace=params.replace,
    )
    if params.app:
        _persist_play_credentials(params.project_path, params.app, pkg, creds)
    return _result(out, "perfectdeck_push_play_screenshots")


@mcp.tool(
    name="perfectdeck_publish_play_bundle",
    annotations={
        "title": "Publish Play Bundle",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
def perfectdeck_publish_play_bundle(params: PublishPlayBundleInput) -> str:
    """Upload an Android App Bundle (.aab) to a Play Store track."""
    pkg, creds = _resolve_play_credentials(params.project_path, params.app, params.package_name, params.credentials_path)
    service = _router().service_for(params.project_path)
    release_notes = None
    if params.release_notes_version:
        release_notes = service.prepare_play_release_notes(
            app=params.app,
            app_version=params.release_notes_version,
            locales=params.locales,
        )

    api = play_store_api.create_service(credentials_path=creds)
    out = play_store_api.publish_bundle(
        service=api,
        package_name=pkg,
        bundle_path=params.bundle_path,
        track=params.track,
        status=params.status,
        release_notes=release_notes,
        mapping_path=params.mapping_path,
    )
    _persist_play_credentials(params.project_path, params.app, pkg, creds)
    return _result(out, "perfectdeck_publish_play_bundle")


@mcp.tool(
    name="perfectdeck_sync_play_products",
    annotations={
        "title": "Sync Play Managed Products",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def perfectdeck_sync_play_products(params: SyncPlayProductsInput) -> str:
    """Create or update managed one-time in-app products on Google Play.

    When products is omitted, all products from the local listing are synced automatically.
    Regional pricing from the local listing pricing field is applied per-product.
    """
    if params.app:
        pkg, creds = _resolve_play_credentials(params.project_path, params.app, params.package_name, params.credentials_path)
    else:
        if not params.package_name:
            raise ValueError("package_name is required when app is not set for credential resolution.")
        pkg, creds = params.package_name, params.credentials_path

    products = params.products
    if not products and params.app:
        local = _router().service_for(params.project_path).list_section(params.app, "play")
        products = _local_products_to_play_list(local.get("products", {}))
    if not products:
        raise ValueError("No products to sync. Provide products or configure them locally with perfectdeck_configure_iap.")

    api = play_store_api.create_service(credentials_path=creds)
    out = play_store_api.ensure_managed_products(
        service=api,
        package_name=pkg,
        products=products,
    )
    if params.app:
        _persist_play_credentials(params.project_path, params.app, pkg, creds)
        products_dict = {}
        for p in products:
            if not p.get("sku"):
                continue
            entry = {k: v for k, v in p.items() if k != "sku"}
            # Normalize Play API "listings" back to local "localizations" key
            if "listings" in entry:
                entry["localizations"] = entry.pop("listings")
            products_dict[p["sku"]] = entry
        if products_dict:
            _router().service_for(params.project_path).set_products(params.app, "play", products_dict)
    return _result(out, "perfectdeck_sync_play_products")


@mcp.tool(
    name="perfectdeck_deactivate_play_product",
    annotations={
        "title": "Deactivate Play Managed Product",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def perfectdeck_deactivate_play_product(params: DeactivatePlayProductInput) -> str:
    """Set a managed one-time product to inactive on Google Play.

    Google Play does not support permanent deletion of published products via the API.
    Setting a product inactive hides it from new buyers while preserving purchase history.

    Use perfectdeck_delete_product (without credentials) to also remove it from the local listing.

    Returns: {"ok": true, "sku": "...", "status": "inactive"}
    """
    if params.app:
        pkg, creds = _resolve_play_credentials(params.project_path, params.app, params.package_name, params.credentials_path)
    else:
        if not params.package_name:
            raise ValueError("package_name is required when app is not set for credential resolution.")
        pkg, creds = params.package_name, params.credentials_path
    api = play_store_api.create_service(credentials_path=creds)
    out = play_store_api.deactivate_managed_product(
        service=api,
        package_name=pkg,
        sku=params.sku,
    )
    if params.app:
        _persist_play_credentials(params.project_path, params.app, pkg, creds)
    return _result(out, "perfectdeck_deactivate_play_product")


@mcp.tool(
    name="perfectdeck_sync_play_pricing",
    annotations={
        "title": "Sync Play Regional Pricing",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def perfectdeck_sync_play_pricing(params: SyncPlayPricingInput) -> str:
    """Apply regional pricing to a one-time product on Google Play."""
    if params.app:
        pkg, creds = _resolve_play_credentials(params.project_path, params.app, params.package_name, params.credentials_path)
    else:
        if not params.package_name:
            raise ValueError("package_name is required when app is not set for credential resolution.")
        pkg, creds = params.package_name, params.credentials_path
    api = play_store_api.create_service(credentials_path=creds)
    out = play_store_api.apply_regional_pricing(
        service=api,
        package_name=pkg,
        sku=params.sku,
        regional_prices=params.regional_prices,
    )
    if params.app:
        _persist_play_credentials(params.project_path, params.app, pkg, creds)
    return _result(out, "perfectdeck_sync_play_pricing")


@mcp.tool(
    name="perfectdeck_sync_play_subscription_pricing",
    annotations={
        "title": "Sync Play Subscription Pricing",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def perfectdeck_sync_play_subscription_pricing(params: SyncPlaySubscriptionPricingInput) -> str:
    """Apply regional pricing to a subscription base plan on Google Play."""
    if params.app:
        pkg, creds = _resolve_play_credentials(params.project_path, params.app, params.package_name, params.credentials_path)
    else:
        if not params.package_name:
            raise ValueError("package_name is required when app is not set for credential resolution.")
        pkg, creds = params.package_name, params.credentials_path
    api = play_store_api.create_service(credentials_path=creds)
    out = play_store_api.apply_subscription_regional_pricing(
        service=api,
        package_name=pkg,
        subscription_id=params.subscription_id,
        base_plan_id=params.base_plan_id,
        regional_prices=params.regional_prices,
    )
    if params.app:
        _persist_play_credentials(params.project_path, params.app, pkg, creds)
    return _result(out, "perfectdeck_sync_play_subscription_pricing")


# ======================================================================
# Push to App Store
# ======================================================================


@mcp.tool(
    name="perfectdeck_push_app_store_listing",
    annotations={
        "title": "Push App Store Listing",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def perfectdeck_push_app_store_listing(params: PushAppStoreListingInput) -> str:
    """Push local listing metadata to App Store Connect."""
    r_app_id, r_key_id, r_issuer_id, r_pk = _resolve_app_store_credentials(
        params.project_path, params.app, params.app_id, params.key_id, params.issuer_id, params.private_key_path,
    )
    service = _router().service_for(params.project_path)
    push_data = service.prepare_app_store_push_data(
        app=params.app,
        locales=params.locales,
        app_version=params.release_notes_version,
    )
    client = app_store_api.AppStoreConnectClient.from_key_file(
        key_id=r_key_id,
        issuer_id=r_issuer_id,
        private_key_path=r_pk,
        dry_run=params.dry_run,
    )
    out = app_store_api.push_listings(
        client=client,
        app_id=r_app_id,
        platform=params.platform,
        version_string=params.version_string,
        locales_data=push_data,
        only_whats_new=params.only_whats_new,
    )
    _persist_app_store_credentials(params.project_path, params.app, r_app_id, r_key_id, r_issuer_id, r_pk)
    return _result(out, "perfectdeck_push_app_store_listing")


@mcp.tool(
    name="perfectdeck_create_app_store_version",
    annotations={
        "title": "Create App Store Version",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
def perfectdeck_create_app_store_version(params: CreateAppStoreVersionInput) -> str:
    """Create a new App Store version."""
    if params.app:
        r_app_id, r_key_id, r_issuer_id, r_pk = _resolve_app_store_credentials(
            params.project_path, params.app, params.app_id, params.key_id, params.issuer_id, params.private_key_path,
        )
    else:
        if not (params.app_id and params.key_id and params.issuer_id and params.private_key_path):
            raise ValueError("All App Store credentials are required when app is not set for credential resolution.")
        r_app_id, r_key_id, r_issuer_id, r_pk = params.app_id, params.key_id, params.issuer_id, params.private_key_path
    client = app_store_api.AppStoreConnectClient.from_key_file(
        key_id=r_key_id,
        issuer_id=r_issuer_id,
        private_key_path=r_pk,
    )
    out = client.create_app_store_version(
        app_id=r_app_id,
        platform=params.platform,
        version_string=params.version_string,
        release_type=params.release_type,
        earliest_release_date=params.earliest_release_date,
    )
    out["ok"] = True
    if params.app:
        _persist_app_store_credentials(params.project_path, params.app, r_app_id, r_key_id, r_issuer_id, r_pk)
    return _result(out, "perfectdeck_create_app_store_version")


@mcp.tool(
    name="perfectdeck_push_app_store_screenshots",
    annotations={
        "title": "Push App Store Screenshots",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def perfectdeck_push_app_store_screenshots(params: PushAppStoreScreenshotsInput) -> str:
    """Upload screenshots to App Store Connect for one locale and display type."""
    if params.app:
        r_app_id, r_key_id, r_issuer_id, r_pk = _resolve_app_store_credentials(
            params.project_path, params.app, params.app_id, params.key_id, params.issuer_id, params.private_key_path,
        )
    else:
        if not (params.app_id and params.key_id and params.issuer_id and params.private_key_path):
            raise ValueError("All App Store credentials are required when app is not set for credential resolution.")
        r_app_id, r_key_id, r_issuer_id, r_pk = params.app_id, params.key_id, params.issuer_id, params.private_key_path
    client = app_store_api.AppStoreConnectClient.from_key_file(
        key_id=r_key_id,
        issuer_id=r_issuer_id,
        private_key_path=r_pk,
    )
    version_id = client.get_app_store_version_id(
        r_app_id, params.platform, params.version_string,
    )
    loc_id = client.find_app_store_version_localization(version_id, params.locale)
    if loc_id is None:
        loc_id = client.create_app_store_version_localization(
            version_id, params.locale,
        )

    out = app_store_api.upload_screenshots(
        client=client,
        version_localization_id=loc_id,
        display_type=params.display_type,
        file_paths=params.file_paths,
        replace=params.replace,
    )
    if params.app:
        _persist_app_store_credentials(params.project_path, params.app, r_app_id, r_key_id, r_issuer_id, r_pk)
    return _result(out, "perfectdeck_push_app_store_screenshots")


@mcp.tool(
    name="perfectdeck_get_app_store_app_id",
    annotations={
        "title": "Look Up App Store App ID",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def perfectdeck_get_app_store_app_id(params: GetAppStoreAppIdInput) -> str:
    """Look up the numeric App Store Connect app ID for a given bundle ID.

    Use this when you have API credentials but don't know the numeric app_id
    required by other App Store tools.
    """
    client = app_store_api.AppStoreConnectClient.from_key_file(
        key_id=params.key_id,
        issuer_id=params.issuer_id,
        private_key_path=params.private_key_path,
    )
    app_id = client.find_app_id_by_bundle_id(params.bundle_id)
    if not app_id:
        raise ValueError(f"No app found with bundle ID: {params.bundle_id}")
    return _result({"ok": True, "bundle_id": params.bundle_id, "app_id": app_id}, "perfectdeck_get_app_store_app_id")


@mcp.tool(
    name="perfectdeck_configure_iap",
    annotations={
        "title": "Configure IAP Products Locally",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def _local_products_to_play_list(products: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert local listing products dict → sync_play_products list format."""
    result = []
    for sku, cfg in products.items():
        if not isinstance(cfg, dict):
            continue
        entry: dict[str, Any] = {"sku": sku}
        if "default_price" in cfg:
            entry["default_price"] = cfg["default_price"]
        # Local listing uses "localizations"; Play API expects "listings"
        if "localizations" in cfg:
            entry["listings"] = cfg["localizations"]
        if "pricing" in cfg:
            entry["pricing"] = cfg["pricing"]
        result.append(entry)
    return result


def _local_products_to_app_store_list(products: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert local listing products dict → sync_app_store_iap list format."""
    result = []
    for product_id, cfg in products.items():
        if not isinstance(cfg, dict):
            continue
        entry: dict[str, Any] = {"product_id": product_id}
        if "localizations" in cfg:
            entry["localizations"] = cfg["localizations"]
        if "pricing" in cfg:
            entry["pricing"] = cfg["pricing"]
        result.append(entry)
    return result


def _expand_pricing_tiers(products: dict[str, Any], store: str) -> dict[str, Any]:
    """Replace pricing_tiers shorthand with a fully calculated pricing dict."""
    expanded: dict[str, Any] = {}
    pricing_runs: dict[str, dict[str, Any]] = {}
    for pid, cfg in products.items():
        if not isinstance(cfg, dict) or "pricing_tiers" not in cfg:
            expanded[pid] = cfg
            continue
        cfg = dict(cfg)
        tier_cfg = cfg.pop("pricing_tiers")
        if not isinstance(tier_cfg, dict):
            tier_cfg = {}
        base_usd: float = float(tier_cfg.get("base_usd", 0.0))
        include_tier5: bool = bool(tier_cfg.get("include_tier5", False))
        currency_overrides: dict | None = tier_cfg.get("currency_overrides")
        tier_overrides: dict | None = tier_cfg.get("tier_overrides")
        live_rates: bool = bool(tier_cfg.get("live_rates", True))
        exchange_rate_overrides: dict | None = tier_cfg.get("exchange_rate_overrides")
        countries: list | None = tier_cfg.get("countries")
        expanded[pid] = cfg
        pricing_options = {
            "tiers": tier_overrides,
            "include_tier5": include_tier5,
            "currency_overrides": currency_overrides,
            "live_rates": live_rates,
            "exchange_rate_overrides": exchange_rate_overrides,
            "countries": countries,
        }
        run_key = json.dumps(pricing_options, sort_keys=True, ensure_ascii=False)
        run = pricing_runs.setdefault(
            run_key,
            {"options": pricing_options, "products": {}},
        )
        run["products"][pid] = {
            "base_usd": base_usd,
            "units": tier_cfg.get("units"),
            "value_group": tier_cfg.get("value_group"),
        }

    for run in pricing_runs.values():
        calculated = regional_pricing.calculate_regional_prices_for_products(
            products=run["products"],
            store=store,
            **run["options"],
        )
        for pid, pricing in calculated.items():
            expanded[pid]["pricing"] = pricing
    return expanded


def perfectdeck_configure_iap(params: ConfigureIapInput) -> str:
    """Configure IAP products and subscriptions in the local listing file without pushing to any store.

    Use this to define product IDs, pricing, and localizations locally before syncing.
    Does not require store credentials. Safe to call at any time.

    Supports a ``pricing_tiers`` shorthand per product: instead of manually specifying
    regional prices, provide ``{"pricing_tiers": {"base_usd": 1.99}}`` and the tool
    auto-generates prices for 100+ countries using PPP tiers.
    """
    products = _expand_pricing_tiers(dict(params.products), params.store)
    svc = _router().service_for(params.project_path)
    out = svc.set_products(
        params.app,
        params.store,
        products,
        params.subscriptions or None,
        merge=params.merge,
    )
    return _result(out, "perfectdeck_configure_iap")


@mcp.tool(
    name="perfectdeck_set_iap_pricing_tiers",
    annotations={
        "title": "Set IAP Pricing via PPP Tiers",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_set_iap_pricing_tiers(params: SetIapPricingTiersInput) -> str:
    """Auto-configure regional pricing for IAP products using PPP tiers.

    Provide a base USD price per product; the tool calculates prices for 100+
    countries across 5 income tiers with currency-aware price point snapping.

    Products may optionally declare ``units`` and ``value_group`` so bundle
    ladders are solved together and larger packs never end up with a worse
    price per unit than smaller packs.

    Tiers (multipliers):
      tier1 (1.0×): US, CA, AU, GB, DE, FR, NL, Nordic, Gulf...
      tier2 (0.75×): ES, IT, PT, KR, JP, TW, Baltic...
      tier3 (0.5×):  PL, BR, MX, TH, TR, ZA, RU...
      tier4 (0.35×): IN, ID, PH, VN, NG, EG...
      tier5 (0.25×): ET, MW, RW, HT... (opt-in via include_tier5)

    Currencies: EUR for Eurozone, GBP for GB, INR for IN, BRL for BR,
    JPY for JP, KRW for KR, CAD for CA, AUD for AU, and local currencies for
    25+ additional markets. USD fallback for the rest.

    Play Store uses 2-letter codes; App Store uses 3-letter territory codes.
    Merges into existing product config, preserving localizations.
    """
    svc = _router().service_for(params.project_path)
    calculated = regional_pricing.calculate_regional_prices_for_products(
        products=params.products,
        store=params.store,
        tiers=params.tier_overrides,
        include_tier5=params.include_tier5,
        currency_overrides=params.currency_overrides,
        live_rates=params.live_rates,
        exchange_rate_overrides=params.exchange_rate_overrides,
        countries=params.countries,
    )
    pricing_data: dict[str, Any] = {
        product_id: {"pricing": pricing}
        for product_id, pricing in calculated.items()
    }

    # Split pricing between products and subscriptions based on existing listing
    section = svc.list_section(params.app, params.store)
    existing_subs = section.get("subscriptions", {})
    sub_pricing: dict[str, Any] = {}
    prod_pricing: dict[str, Any] = {}
    for pid, pdata in pricing_data.items():
        if pid in existing_subs:
            sub_pricing[pid] = pdata
        else:
            prod_pricing[pid] = pdata
    if prod_pricing:
        svc.set_products(params.app, params.store, prod_pricing, merge=True)
    if sub_pricing:
        svc.set_products(params.app, params.store, {}, subscriptions=sub_pricing, merge=True)

    country_count = len(next(iter(pricing_data.values()))["pricing"]) if pricing_data else 0
    return _result(
        {
            "ok": True,
            "products_configured": len(params.products),
            "countries_configured": country_count,
            "store": params.store,
        },
        "perfectdeck_set_iap_pricing_tiers",
    )


@mcp.tool(
    name="perfectdeck_get_pricing_tiers",
    annotations={
        "title": "Get Built-in PPP Pricing Tiers",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def perfectdeck_get_pricing_tiers() -> str:
    """Return the built-in PPP pricing tier configuration.

    Shows all tiers, their multipliers, and which countries are included.
    Useful for understanding what regional pricing will be applied before
    calling perfectdeck_set_iap_pricing_tiers.
    """
    return _result(
        {"ok": True, "tiers": regional_pricing.PRICING_TIERS},
        "perfectdeck_get_pricing_tiers",
    )


@mcp.tool(
    name="perfectdeck_sync_app_store_iap",
    annotations={
        "title": "Sync App Store IAP Localizations",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def perfectdeck_sync_app_store_iap(params: SyncAppStoreIapInput) -> str:
    """Sync in-app purchase localizations and pricing to App Store Connect.

    When products is omitted, all products from the local listing are synced automatically.
    Set delete_missing=true to remove remote localizations not present in the local listing.
    Products that have a ``pricing`` field will have their regional pricing pushed automatically.
    """
    if params.app:
        r_app_id, r_key_id, r_issuer_id, r_pk = _resolve_app_store_credentials(
            params.project_path, params.app, params.app_id, params.key_id, params.issuer_id, params.private_key_path,
        )
    else:
        if not (params.app_id and params.key_id and params.issuer_id and params.private_key_path):
            raise ValueError("All App Store credentials are required when app is not set for credential resolution.")
        r_app_id, r_key_id, r_issuer_id, r_pk = params.app_id, params.key_id, params.issuer_id, params.private_key_path

    products = params.products
    if not products and params.app:
        local = _router().service_for(params.project_path).list_section(params.app, "app_store")
        products = _local_products_to_app_store_list(local.get("products", {}))
    if not products:
        raise ValueError("No products to sync. Provide products or configure them locally with perfectdeck_configure_iap.")

    client = app_store_api.AppStoreConnectClient.from_key_file(
        key_id=r_key_id,
        issuer_id=r_issuer_id,
        private_key_path=r_pk,
    )
    out = app_store_api.sync_iap_localizations(
        client=client,
        app_id=r_app_id,
        products=products,
        delete_missing=params.delete_missing,
    )

    # Sync pricing for products that have a pricing field
    products_with_pricing = [p for p in products if p.get("pricing")]
    if products_with_pricing:
        pricing_out = app_store_api.sync_iap_pricing(
            client=client,
            app_id=r_app_id,
            products=products_with_pricing,
        )
        out["pricing"] = pricing_out

    if params.app:
        _persist_app_store_credentials(params.project_path, params.app, r_app_id, r_key_id, r_issuer_id, r_pk)
        products_dict = {
            p["product_id"]: {k: v for k, v in p.items() if k != "product_id"}
            for p in products
            if p.get("product_id")
        }
        if products_dict:
            _router().service_for(params.project_path).set_products(params.app, "app_store", products_dict)
    return _result(out, "perfectdeck_sync_app_store_iap")


@mcp.tool(
    name="perfectdeck_sync_app_store_subscriptions",
    annotations={
        "title": "Sync App Store Subscription Localizations",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def perfectdeck_sync_app_store_subscriptions(params: SyncAppStoreSubscriptionsInput) -> str:
    """Sync subscription localizations and pricing to App Store Connect.

    When subscriptions is omitted, all subscriptions from the local listing are synced automatically.
    Set delete_missing=true to remove remote localizations not present in the local listing.
    Subscriptions that have a ``pricing`` field will have their regional pricing pushed automatically.
    """
    if params.app:
        r_app_id, r_key_id, r_issuer_id, r_pk = _resolve_app_store_credentials(
            params.project_path, params.app, params.app_id, params.key_id, params.issuer_id, params.private_key_path,
        )
    else:
        if not (params.app_id and params.key_id and params.issuer_id and params.private_key_path):
            raise ValueError("All App Store credentials are required when app is not set for credential resolution.")
        r_app_id, r_key_id, r_issuer_id, r_pk = params.app_id, params.key_id, params.issuer_id, params.private_key_path

    subscriptions = params.subscriptions
    if not subscriptions and params.app:
        local = _router().service_for(params.project_path).list_section(params.app, "app_store")
        subscriptions = _local_products_to_app_store_list(local.get("subscriptions", {}))
    if not subscriptions:
        raise ValueError("No subscriptions to sync. Provide subscriptions or configure them locally with perfectdeck_configure_iap.")

    client = app_store_api.AppStoreConnectClient.from_key_file(
        key_id=r_key_id,
        issuer_id=r_issuer_id,
        private_key_path=r_pk,
    )
    out = app_store_api.sync_subscription_localizations(
        client=client,
        app_id=r_app_id,
        subscriptions=subscriptions,
        delete_missing=params.delete_missing,
    )

    # Sync pricing for subscriptions that have a pricing field
    subs_with_pricing = [s for s in subscriptions if s.get("pricing")]
    if subs_with_pricing:
        pricing_out = app_store_api.sync_subscription_pricing(
            client=client,
            app_id=r_app_id,
            subscriptions=subs_with_pricing,
        )
        out["pricing"] = pricing_out

    if params.app:
        _persist_app_store_credentials(params.project_path, params.app, r_app_id, r_key_id, r_issuer_id, r_pk)
        subscriptions_dict = {
            s["product_id"]: {k: v for k, v in s.items() if k != "product_id"}
            for s in subscriptions
            if s.get("product_id")
        }
        if subscriptions_dict:
            _router().service_for(params.project_path).set_products(params.app, "app_store", {}, subscriptions_dict)
    return _result(out, "perfectdeck_sync_app_store_subscriptions")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run perfectdeckcli MCP server.")
    parser.add_argument(
        "--root-folder",
        type=Path,
        default=Path("."),
        help="Workspace root; tool project_path values resolve relative to this folder.",
    )
    parser.add_argument(
        "--listing-file-name",
        default="listings.yaml",
        help="Listing filename to use inside each project folder.",
    )
    args = parser.parse_args()

    global router
    router = ProjectListingRouter(
        root_folder=args.root_folder,
        listing_file_name=args.listing_file_name,
    )
    mcp.run()


if __name__ == "__main__":
    main()
