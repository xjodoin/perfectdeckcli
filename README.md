# perfectdeckcli

`perfectdeckcli` manages App Store Connect and Google Play listing data from a
single local source of truth.

It supports:
- Command-line operations through `perfectdeckcli`
- MCP server tools through `perfectdeck-mcp`
- Structured listing edits through dotted key paths
- Version tracking for language updates and release note workflows
- Regional pricing generation for one-time products
- Read-only App Store and Google Play analytics/reporting access
- App Store custom product pages and product page optimization experiments

Related docs:
- MCP client setup: `docs/mcp-client-setup.md`
- Authentication and credential storage: `docs/authentication.md`
- Store analytics and reporting: `docs/analytics-reporting.md`
- Regional pricing policy: `docs/pricing-policy.md`

## Installation

### With `uv`

```bash
uv tool install .
```

### In a local checkout

```bash
uv venv
uv pip install -e ".[dev]"
```

## Quick start

Initialize a project file:

```bash
perfectdeckcli init \
  --app prod \
  --stores play,app_store \
  --locales en-US,fr-FR \
  --baseline-locale en-US
```

Update a localized field:

```bash
perfectdeckcli set \
  --app prod \
  --store play \
  --locale fr-FR \
  --key title \
  --value "Docteur des plantes IA"
```

Inspect the current locale payload:

```bash
perfectdeckcli list --app prod --store play --locale fr-FR
```

Track translation status:

```bash
perfectdeckcli status --app prod --store play
perfectdeckcli mark-language-updated --app prod --store play --locale fr-FR
perfectdeckcli bump-version --app prod --store play --reason "new feature copy update" --source-locale en-US
```

## Data model

The default file is `listings.yaml` with this shape:

```yaml
apps:
  prod:
    play:
      global: {}
      locales: {}
      release_notes: {}
      products: {}
      subscriptions: {}
    app_store:
      global: {}
      locales: {}
      release_notes: {}
      products: {}
      subscriptions: {}
```

## Authentication

Store credentials are kept in a sibling `.listing_credentials.yaml` file, which
is intentionally gitignored. The tool can persist credentials per app and store
so you do not need to pass them on every command.

Play Store typically needs:
- `package_name`
- `credentials_path`

App Store Connect typically needs:
- `app_id`
- `key_id`
- `issuer_id`
- `private_key_path`

See `docs/authentication.md` for the exact fields and storage behavior.

## Analytics And Reporting

`perfectdeckcli` can read store analytics and report exports without changing
store metadata.

App Store Connect support:
- Sales and Trends gzip TSV reports through `app-store-sales-report`
- Analytics Reports request/list/instance/segment flow through
  `app-store-analytics-*` commands
- Custom product pages through `app-store-custom-page-*` commands
- Product page optimization experiments through `app-store-experiment-*`
  commands

Google Play support:
- Android vitals through `play-vitals`
- Play Console Cloud Storage CSV exports through `play-report-files` and
  `play-report-download`

Example Play vitals query:

```bash
perfectdeckcli --file ../myapp/listings.yaml play-vitals \
  --app prod \
  --metric-set crash_rate \
  --start-date 2026-04-15 \
  --end-date 2026-04-22 \
  --dimensions versionCode \
  --metrics crashRate,distinctUsers
```

See `docs/analytics-reporting.md` for API setup, permissions, MCP tool names,
and troubleshooting.

## App Store Conversion Experiments

Apple exposes official APIs for custom product pages and product page
optimization experiments. `perfectdeckcli` includes CLI and MCP tools to create
pages, versions, localizations, experiment treatments, keyword links,
screenshot and app-preview variants, delete draft resources, and submit review
items.

Example experiment skeleton:

```bash
perfectdeckcli --file ../myapp/listings.yaml app-store-experiment-create \
  --app prod \
  --name "Screenshot test - spring campaign" \
  --traffic-proportion 50
```

Example custom product page skeleton:

```bash
perfectdeckcli --file ../myapp/listings.yaml app-store-custom-page-create \
  --app prod \
  --name "Herb garden campaign"
```

Google Play does not currently expose equivalent public Android Publisher API
resources for creating Play Store Listing Experiments or Custom Store Listings.
Use Play Console for those setup steps, and use this tool for default listing
updates plus Play reporting export analysis.

## MCP usage

Run the server locally:

```bash
perfectdeck-mcp --root-folder .
```

For multi-project usage, pass `project_path` in each MCP tool call relative to
`--root-folder`.

Example:
- `project_path: "aiplantdoctor"`
- `project_path: "perfectdeck/mobile-app"`

Primary MCP tools:
- `perfectdeck_init_listing`
- `perfectdeck_sync_listing`
- `perfectdeck_diff_listing`
- `perfectdeck_init_from_existing`
- `perfectdeck_add_language`
- `perfectdeck_list_languages`
- `perfectdeck_get_element`
- `perfectdeck_set_element`
- `perfectdeck_delete_element`
- `perfectdeck_upsert_locale`
- `perfectdeck_list_section`
- `perfectdeck_list_apps`
- `perfectdeck_list_stores`
- `perfectdeck_set_baseline_language`
- `perfectdeck_bump_version`
- `perfectdeck_mark_language_updated`
- `perfectdeck_get_update_status`
- `perfectdeck_query_play_vitals`
- `perfectdeck_list_play_report_files`
- `perfectdeck_download_play_report_file`
- `perfectdeck_list_app_store_custom_product_pages`
- `perfectdeck_create_app_store_custom_product_page`
- `perfectdeck_update_app_store_custom_product_page`
- `perfectdeck_delete_app_store_custom_product_page`
- `perfectdeck_list_app_store_keywords`
- `perfectdeck_create_app_store_custom_product_page_version`
- `perfectdeck_update_app_store_custom_product_page_version`
- `perfectdeck_create_app_store_custom_product_page_localization`
- `perfectdeck_update_app_store_custom_product_page_localization`
- `perfectdeck_link_app_store_custom_product_page_keywords`
- `perfectdeck_unlink_app_store_custom_product_page_keywords`
- `perfectdeck_upload_app_store_custom_product_page_screenshots`
- `perfectdeck_upload_app_store_custom_product_page_previews`
- `perfectdeck_list_app_store_experiments`
- `perfectdeck_create_app_store_experiment`
- `perfectdeck_update_app_store_experiment`
- `perfectdeck_delete_app_store_experiment`
- `perfectdeck_create_app_store_experiment_treatment`
- `perfectdeck_update_app_store_experiment_treatment`
- `perfectdeck_delete_app_store_experiment_treatment`
- `perfectdeck_create_app_store_experiment_treatment_localization`
- `perfectdeck_upload_app_store_experiment_screenshots`
- `perfectdeck_upload_app_store_experiment_previews`
- `perfectdeck_create_app_store_review_submission`
- `perfectdeck_add_app_store_review_submission_item`
- `perfectdeck_submit_app_store_review_submission`
- `perfectdeck_get_app_store_sales_report`
- `perfectdeck_request_app_store_analytics_reports`
- `perfectdeck_list_app_store_analytics_requests`
- `perfectdeck_list_app_store_analytics_reports`
- `perfectdeck_list_app_store_analytics_instances`
- `perfectdeck_list_app_store_analytics_segments`
- `perfectdeck_download_app_store_analytics_segment`

## Development

Install dev dependencies and run the validation steps used in CI:

```bash
uv pip install -e ".[dev]"
pytest
python -m build
```

See `CONTRIBUTING.md` for the contribution workflow.
