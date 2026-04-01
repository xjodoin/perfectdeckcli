# perfectdeckcli

`perfectdeckcli` manages App Store Connect and Google Play listing data from a
single local source of truth.

It supports:
- Command-line operations through `perfectdeckcli`
- MCP server tools through `perfectdeck-mcp`
- Structured listing edits through dotted key paths
- Version tracking for language updates and release note workflows
- Regional pricing generation for one-time products

Related docs:
- MCP client setup: `docs/mcp-client-setup.md`
- Authentication and credential storage: `docs/authentication.md`
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

## Development

Install dev dependencies and run the validation steps used in CI:

```bash
uv pip install -e ".[dev]"
pytest
python -m build
```

See `CONTRIBUTING.md` for the contribution workflow.
