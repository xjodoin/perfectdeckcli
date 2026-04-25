# Authentication

`perfectdeckcli` stores per-app, per-store credentials in a sibling
`.listing_credentials.yaml` file next to your `listings.yaml`.

That file is intentionally gitignored and should never be committed.

## Storage model

Credentials are stored under:

```yaml
apps:
  myapp:
    play:
      package_name: com.example.app
      credentials_path: /abs/path/to/service-account.json
    app_store:
      app_id: "1234567890"
      key_id: ABC123DEF4
      issuer_id: 11111111-2222-3333-4444-555555555555
      private_key_path: /abs/path/to/AuthKey_ABC123DEF4.p8
```

## Google Play

Typical required fields:

- `package_name`
- `credentials_path`

`credentials_path` should point to a Play Console service account JSON key with
the permissions needed for the operations you plan to run.

For Play Developer Reporting API tools such as `play-vitals` and
`perfectdeck_query_play_vitals`, the service account's Google Cloud project must
have the `playdeveloperreporting.googleapis.com` API enabled. The service
account also needs Play Console access to the target app. Different metric sets
can require different Play Console permissions, so grant the smallest role that
can read the data you need.

For Play Console report exports such as `play-report-files`,
`play-report-download`, `perfectdeck_list_play_report_files`, and
`perfectdeck_download_play_report_file`, the service account needs Cloud Storage
read access to the Play report bucket and the OAuth scope
`https://www.googleapis.com/auth/devstorage.read_only`. Google Play report
buckets usually have names like `pubsite_prod_rev_0123456789`.

## App Store Connect

Typical required fields:

- `app_id`
- `key_id`
- `issuer_id`
- `private_key_path`

`private_key_path` should point to the `.p8` key downloaded from App Store
Connect.

App Store reporting tools have additional role requirements:

- `app-store-sales-report` and `perfectdeck_get_app_store_sales_report` need a
  Team API key and a vendor number. The key role must allow Sales and Trends
  report downloads.
- `app-store-analytics-request` and
  `perfectdeck_request_app_store_analytics_reports` require a key that can
  create Analytics Reports requests. Apple requires an Admin role for the first
  request of a report type.
- `app-store-analytics-list-*`,
  `app-store-analytics-download-segment`, and the matching MCP tools require a
  key role that can list and download generated Analytics Reports, such as
  Sales and Reports or Finance.

A key can be valid for normal App Store Connect reads but still fail analytics
calls with `403 FORBIDDEN_ERROR` if the key role does not allow Analytics
Reports.

Custom product pages, product page optimization experiments, keyword links,
screenshot uploads, app-preview uploads, deletes, and review submissions require
App Store Connect roles that can manage app metadata and marketing assets, such
as Account Holder, Admin, App Manager, or Marketing. Apple can reject individual
operations even when the key can read the app, so treat write tools as
permission-sensitive.

## MCP behavior

MCP tools can resolve credentials from stored values when explicit arguments are
omitted. Explicit values still take precedence over stored credentials.

This means you can configure credentials once per app and store, then reuse the
same project in repeated MCP sessions.

Generic official API request tools (`app-store-api-request`,
`play-api-request`, `perfectdeck_app_store_api_request`, and
`perfectdeck_play_api_request`) use the same credentials as typed operations.
Non-read generic requests require explicit confirmation (`--yes` for CLI or
`confirm_destructive=true` for MCP) because endpoint-specific side effects
cannot be inferred safely.

## Operational guidance

- Use absolute paths for credential files when possible.
- Keep the credential files outside the repository when practical.
- Rotate compromised keys immediately.
- If you change app identifiers or service account files, update the stored
  credentials before running sync operations.
