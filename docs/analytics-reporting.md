# Store Analytics And Reporting

`perfectdeckcli` exposes read-only commands and MCP tools for App Store Connect
and Google Play reporting data. These commands do not mutate store listings,
releases, products, or pricing.

## API Surfaces

The stores expose analytics through different systems:

- App Store Connect Sales and Trends reports are gzip TSV downloads from the
  App Store Connect API.
- App Store Connect Analytics Reports are requested first, then downloaded as
  report segments once Apple generates instances.
- Google Play Android vitals are queried from the Play Developer Reporting API.
- Google Play statistics, reviews, acquisition, and financial exports are CSV
  files in the Play Console Cloud Storage reporting bucket.

## Google Play Vitals

Use `play-vitals` to query Android vitals metric sets:

```bash
perfectdeckcli --file /ABS/PATH/listings.yaml play-vitals \
  --app prod \
  --metric-set crash_rate \
  --start-date 2026-04-15 \
  --end-date 2026-04-22 \
  --dimensions versionCode,countryCode \
  --metrics crashRate,distinctUsers \
  --page-size 100
```

Supported `metric_set` values:

- `anr_rate`
- `crash_rate`
- `error_count`
- `excessive_wakeup_rate`
- `lmk_rate`
- `slow_rendering_rate`
- `slow_start_rate`
- `stuck_background_wakelock_rate`

The command uses stored Play credentials when `--app` is set. Pass
`--package-name` and `--credentials-path` to override stored values.

If the API is disabled, Google returns `SERVICE_DISABLED`. Enable it on the
service account's Google Cloud project:

```bash
gcloud services enable playdeveloperreporting.googleapis.com --project PROJECT_ID
```

Daily vitals use `America/Los_Angeles` by default. Hourly vitals use `UTC`.

## Google Play CSV Report Exports

List report files in the Play Console reporting bucket:

```bash
perfectdeckcli play-report-files \
  --credentials-path /ABS/PATH/service-account.json \
  --bucket pubsite_prod_rev_0123456789 \
  --prefix stats/installs/
```

Download and parse one object:

```bash
perfectdeckcli play-report-download \
  --credentials-path /ABS/PATH/service-account.json \
  --bucket pubsite_prod_rev_0123456789 \
  --object-name stats/installs/installs_com.example.app_202604_overview.csv \
  --max-rows 100
```

Play Console CSV exports are commonly UTF-16. The parser defaults to UTF-16 and
falls back to UTF-8 when needed. Gzip and zip-wrapped CSV files are also
handled.

For acquisition reports, avoid double counting: Google documents some aggregate
rows, such as organic totals, alongside their component rows.

## App Store Sales And Trends

Download and parse a Sales and Trends report:

```bash
perfectdeckcli --file /ABS/PATH/listings.yaml app-store-sales-report \
  --app prod \
  --vendor-number 12345678 \
  --report-type SALES \
  --report-sub-type SUMMARY \
  --frequency DAILY \
  --max-rows 100
```

Common report types include `SALES`, `SUBSCRIPTION`, `SUBSCRIBER`, and
`INSTALLS`. Apple restricts valid `report_type`, `report_sub_type`,
`frequency`, and `version` combinations. If Apple rejects a combination, use the
values from Apple's Sales and Trends documentation for that report type.

The command returns parsed rows from the decompressed TSV. Use `--include-text`
to include the full decompressed report text or `--include-base64` to include
the original gzip bytes.

## App Store Analytics Reports

Analytics Reports are a multi-step flow.

Create a report request:

```bash
perfectdeckcli --file /ABS/PATH/listings.yaml app-store-analytics-request \
  --app prod \
  --access-type ONGOING
```

List requests and reports:

```bash
perfectdeckcli --file /ABS/PATH/listings.yaml app-store-analytics-list-requests \
  --app prod

perfectdeckcli --file /ABS/PATH/listings.yaml app-store-analytics-list-reports \
  --app prod \
  --request-id REQUEST_ID
```

List instances and segments:

```bash
perfectdeckcli --file /ABS/PATH/listings.yaml app-store-analytics-list-instances \
  --app prod \
  --report-id REPORT_ID \
  --granularity DAILY \
  --processing-date 2026-04-20

perfectdeckcli --file /ABS/PATH/listings.yaml app-store-analytics-list-segments \
  --app prod \
  --instance-id INSTANCE_ID
```

Download one segment:

```bash
perfectdeckcli --file /ABS/PATH/listings.yaml app-store-analytics-download-segment \
  --app prod \
  --segment-id SEGMENT_ID \
  --max-rows 100
```

Apple does not generate Analytics Reports until a valid request exists. The
first `ONGOING` request can take 24 to 48 hours before reports appear. Daily
data can lag, and low-volume rows may be suppressed or privacy-thresholded.

## MCP Tool Mapping

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

## App Store Custom Product Pages

Custom product pages are official App Store Connect resources that let you
create audience-specific product pages with their own URL, promotional text,
screenshots, previews, keywords, and App Analytics reporting.

CLI workflow:

```bash
perfectdeckcli --file /ABS/PATH/listings.yaml app-store-custom-page-create \
  --app prod \
  --name "Campaign - herb garden"

perfectdeckcli --file /ABS/PATH/listings.yaml app-store-custom-page-version-create \
  --app prod \
  --page-id APP_CUSTOM_PRODUCT_PAGE_ID

perfectdeckcli --file /ABS/PATH/listings.yaml app-store-custom-page-localization-create \
  --app prod \
  --version-id APP_CUSTOM_PRODUCT_PAGE_VERSION_ID \
  --locale en-US \
  --promotional-text "Diagnose basil, mint, and parsley problems in seconds."

perfectdeckcli --file /ABS/PATH/listings.yaml app-store-custom-page-screenshots \
  --app prod \
  --localization-id APP_CUSTOM_PRODUCT_PAGE_LOCALIZATION_ID \
  --display-type APP_IPHONE_67 \
  --file-paths /ABS/PATH/01.png,/ABS/PATH/02.png

perfectdeckcli --file /ABS/PATH/listings.yaml app-store-custom-page-previews \
  --app prod \
  --localization-id APP_CUSTOM_PRODUCT_PAGE_LOCALIZATION_ID \
  --preview-type IPHONE_67 \
  --file-paths /ABS/PATH/preview.mp4

perfectdeckcli --file /ABS/PATH/listings.yaml app-store-keywords \
  --app prod \
  --locale en-US \
  --platform IOS

perfectdeckcli --file /ABS/PATH/listings.yaml app-store-custom-page-keywords-link \
  --app prod \
  --localization-id APP_CUSTOM_PRODUCT_PAGE_LOCALIZATION_ID \
  --keyword-ids KEYWORD_ID_1,KEYWORD_ID_2
```

Submit a custom product page version for review:

```bash
perfectdeckcli --file /ABS/PATH/listings.yaml app-store-review-submission-create \
  --app prod \
  --platform IOS

perfectdeckcli --file /ABS/PATH/listings.yaml app-store-review-submission-add-item \
  --app prod \
  --review-submission-id REVIEW_SUBMISSION_ID \
  --resource-type appCustomProductPageVersions \
  --resource-id APP_CUSTOM_PRODUCT_PAGE_VERSION_ID

perfectdeckcli --file /ABS/PATH/listings.yaml app-store-review-submission-submit \
  --app prod \
  --review-submission-id REVIEW_SUBMISSION_ID
```

MCP tools:

- `perfectdeck_list_app_store_custom_product_pages`
- `perfectdeck_create_app_store_custom_product_page`
- `perfectdeck_update_app_store_custom_product_page`
- `perfectdeck_delete_app_store_custom_product_page`
- `perfectdeck_list_app_store_keywords`
- `perfectdeck_list_app_store_custom_product_page_versions`
- `perfectdeck_create_app_store_custom_product_page_version`
- `perfectdeck_update_app_store_custom_product_page_version`
- `perfectdeck_list_app_store_custom_product_page_localizations`
- `perfectdeck_create_app_store_custom_product_page_localization`
- `perfectdeck_update_app_store_custom_product_page_localization`
- `perfectdeck_link_app_store_custom_product_page_keywords`
- `perfectdeck_unlink_app_store_custom_product_page_keywords`
- `perfectdeck_upload_app_store_custom_product_page_screenshots`
- `perfectdeck_upload_app_store_custom_product_page_previews`

## App Store Product Page Optimization

Product page optimization experiments test alternate product page treatments
against the default product page. Apple supports alternate screenshots, app
previews, and app icons. Alternate app icons must already be included in the
current app binary.

CLI workflow:

```bash
perfectdeckcli --file /ABS/PATH/listings.yaml app-store-experiment-create \
  --app prod \
  --name "Screenshot ordering test" \
  --platform IOS \
  --traffic-proportion 50

perfectdeckcli --file /ABS/PATH/listings.yaml app-store-experiment-treatment-create \
  --app prod \
  --experiment-id APP_STORE_EXPERIMENT_ID \
  --name "Treatment A"

perfectdeckcli --file /ABS/PATH/listings.yaml app-store-experiment-treatment-localization-create \
  --app prod \
  --treatment-id TREATMENT_ID \
  --locale en-US

perfectdeckcli --file /ABS/PATH/listings.yaml app-store-experiment-screenshots \
  --app prod \
  --localization-id TREATMENT_LOCALIZATION_ID \
  --display-type APP_IPHONE_67 \
  --file-paths /ABS/PATH/01.png,/ABS/PATH/02.png

perfectdeckcli --file /ABS/PATH/listings.yaml app-store-experiment-previews \
  --app prod \
  --localization-id TREATMENT_LOCALIZATION_ID \
  --preview-type IPHONE_67 \
  --file-paths /ABS/PATH/preview.mp4
```

After assets are approved, start an experiment:

```bash
perfectdeckcli --file /ABS/PATH/listings.yaml app-store-experiment-update \
  --app prod \
  --experiment-id APP_STORE_EXPERIMENT_ID \
  --started true
```

MCP tools:

- `perfectdeck_list_app_store_experiments`
- `perfectdeck_create_app_store_experiment`
- `perfectdeck_update_app_store_experiment`
- `perfectdeck_delete_app_store_experiment`
- `perfectdeck_list_app_store_experiment_treatments`
- `perfectdeck_create_app_store_experiment_treatment`
- `perfectdeck_update_app_store_experiment_treatment`
- `perfectdeck_delete_app_store_experiment_treatment`
- `perfectdeck_list_app_store_experiment_treatment_localizations`
- `perfectdeck_create_app_store_experiment_treatment_localization`
- `perfectdeck_upload_app_store_experiment_screenshots`
- `perfectdeck_upload_app_store_experiment_previews`
- `perfectdeck_create_app_store_review_submission`
- `perfectdeck_add_app_store_review_submission_item`
- `perfectdeck_submit_app_store_review_submission`

## Google Play Experiments And Custom Listings

Google Play's Android Publisher API supports default store listing metadata and
images through edit resources. It does not currently expose public resources for
creating or managing Play Store Listing Experiments or Custom Store Listings.

Use Play Console for those setup workflows. Use `perfectdeckcli` to:

- update the default listing and screenshots,
- fetch Play vitals,
- parse Play Console reporting CSV exports,
- compare reporting metrics for manual Play experiments or custom-listing
  campaigns.

## Troubleshooting

`Google Play Developer Reporting API has not been used... or it is disabled`

Enable `playdeveloperreporting.googleapis.com` on the service account's Google
Cloud project, then retry after propagation.

`403 FORBIDDEN_ERROR` from App Store Analytics Reports

The App Store Connect key can be valid for ordinary app metadata reads but lack
Analytics Reports permission. Use an Admin key to create requests, and a Sales
and Reports or Finance key to list and download generated reports.

No rows from a valid Play vitals query

The app may have no data for that metric set, time range, cohort, or dimension
combination. Retry without dimensions, use a wider date range, or check
`nextPageToken`.

No App Store Analytics report instances

Confirm that the report request exists, the key can list reports, and enough
time has passed for Apple to generate the first instance.
