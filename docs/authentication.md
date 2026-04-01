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

## App Store Connect

Typical required fields:

- `app_id`
- `key_id`
- `issuer_id`
- `private_key_path`

`private_key_path` should point to the `.p8` key downloaded from App Store
Connect.

## MCP behavior

MCP tools can resolve credentials from stored values when explicit arguments are
omitted. Explicit values still take precedence over stored credentials.

This means you can configure credentials once per app and store, then reuse the
same project in repeated MCP sessions.

## Operational guidance

- Use absolute paths for credential files when possible.
- Keep the credential files outside the repository when practical.
- Rotate compromised keys immediately.
- If you change app identifiers or service account files, update the stored
  credentials before running sync operations.
