# MCP Client Setup

This guide shows how to register `perfectdeckcli` as an MCP server in:
- Claude Code
- Codex
- Gemini CLI

The server is multi-project. You set one `--root-folder` at startup, then pass `project_path` per tool call.

## Prerequisites

1. `uv` installed.
2. This repository available locally.
3. Use this launch command pattern:

```bash
uv --directory /ABS/PATH/TO/perfectdeckcli run perfectdeck-mcp --root-folder /ABS/PATH/TO/WORKSPACE
```

## Claude Code

Add a stdio MCP server:

```bash
claude mcp add perfectdeckcli -- \
  uv --directory /ABS/PATH/TO/perfectdeckcli run perfectdeck-mcp --root-folder /ABS/PATH/TO/WORKSPACE
```

Useful commands:

```bash
claude mcp list
claude mcp get perfectdeckcli
claude mcp remove perfectdeckcli
```

## Codex

Add this to `~/.codex/config.toml`:

```toml
[mcp_servers.perfectdeckcli]
command = "uv"
args = [
  "--directory=/ABS/PATH/TO/perfectdeckcli",
  "run",
  "perfectdeck-mcp",
  "--root-folder",
  "/ABS/PATH/TO/WORKSPACE"
]
```

Then run:

```bash
codex mcp list
```

## Gemini CLI

Add this to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "perfectdeckcli": {
      "command": "uv",
      "args": [
        "--directory=/ABS/PATH/TO/perfectdeckcli",
        "run",
        "perfectdeck-mcp",
        "--root-folder",
        "/ABS/PATH/TO/WORKSPACE"
      ]
    }
  }
}
```

Then run:

```bash
gemini mcp list
```

## Example MCP call pattern

After server registration, include `project_path` in tool calls:

```json
{
  "project_path": "aiplantdoctor",
  "app": "prod",
  "store": "play",
  "locale": "en-US",
  "key": "title",
  "value": "AI Plant Doctor"
}
```

## Analytics MCP Tools

The analytics and reporting tools are read-only, but they call live Apple and
Google APIs and require the same credentials as the CLI.

Google Play:

- `perfectdeck_list_play_reporting_apps`
- `perfectdeck_query_play_vitals`
- `perfectdeck_list_play_report_files`
- `perfectdeck_download_play_report_file`

App Store Connect:

- `perfectdeck_get_app_store_sales_report`
- `perfectdeck_request_app_store_analytics_reports`
- `perfectdeck_list_app_store_analytics_requests`
- `perfectdeck_list_app_store_analytics_reports`
- `perfectdeck_list_app_store_analytics_instances`
- `perfectdeck_list_app_store_analytics_segments`
- `perfectdeck_download_app_store_analytics_segment`
- `perfectdeck_store_api_coverage`
- `perfectdeck_app_store_api_request`
- `perfectdeck_play_api_request`
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

Example Play vitals tool payload:

```json
{
  "project_path": "aiplantdoctor",
  "app": "aiplantdoctor",
  "metric_set": "crash_rate",
  "start_date": "2026-04-15",
  "end_date": "2026-04-22",
  "dimensions": ["versionCode"],
  "metrics": ["crashRate", "distinctUsers"],
  "page_size": 100
}
```

Example App Store Analytics Reports flow:

1. Call `perfectdeck_request_app_store_analytics_reports` once for the app if no
   request exists yet.
2. Call `perfectdeck_list_app_store_analytics_requests` to get the request ID.
3. Call `perfectdeck_list_app_store_analytics_reports` with the request ID.
4. Call `perfectdeck_list_app_store_analytics_instances` with a report ID and
   optional `granularity` or `processing_date`.
5. Call `perfectdeck_list_app_store_analytics_segments` with an instance ID.
6. Call `perfectdeck_download_app_store_analytics_segment` with a segment ID.

If App Store Analytics tools return `403 FORBIDDEN_ERROR`, the key may still be
valid for ordinary App Store Connect reads while lacking the Analytics Reports
role. See `docs/authentication.md`.

For custom product pages and product page optimization experiments, create or
update the metadata, keyword links, screenshots, and app previews first, attach the custom page version or
experiment to a review submission, then submit it for review. Start experiments
only after the required assets are approved.
