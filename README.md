# perfectdeckcli

`perfectdeckcli` manages App Store + Play Store listing content from a single local data file.

It supports:
- Command-line operations (`perfectdeckcli ...`)
- MCP server tools (`perfectdeck-mcp`)
- Add/update/delete any listing element through dotted key paths

Client setup guide: `docs/mcp-client-setup.md`
Pricing policy: `docs/pricing-policy.md`

## Data model

The default file is `listings.yaml` with this shape:

```yaml
apps:
  prod:
    play:
      global: {}
      locales: {}
    app_store:
      global: {}
      locales: {}
```

## CLI quick start

```bash
perfectdeckcli set --app prod --store play --key title --locale en-US --value "AI Plant Doctor"
perfectdeckcli set --app prod --store app_store --key metadata.promotional_text --locale en-US --value "Diagnose plant problems fast"
perfectdeckcli get --app prod --store play --key title --locale en-US
perfectdeckcli upsert-locale --app prod --store play --locale fr-FR --data '{"title":"Docteur des plantes IA","short_description":"Diagnostic rapide"}'
perfectdeckcli delete --app prod --store app_store --key metadata.promotional_text --locale en-US
perfectdeckcli list --app prod --store play --locale en-US
perfectdeckcli init --app prod --stores play,app_store --locales en-US,fr-FR,es-ES --baseline-locale en-US
perfectdeckcli status --app prod --store play
perfectdeckcli mark-language-updated --app prod --store play --locale fr-FR
perfectdeckcli bump-version --app prod --store play --reason "new feature copy update" --source-locale en-US
perfectdeckcli init-from-existing --app prod-v2 --store app_store --from-app prod --from-store play --locales en-US,fr-FR --baseline-locale en-US
```

## MCP quick start

```bash
perfectdeck-mcp --root-folder .
```

For multi-project usage, pass `project_path` in each MCP tool call (relative to `--root-folder`).
Example:
- `project_path: "aiplantdoctor"`
- `project_path: "perfectdeck/mobile-app"`

Available MCP tools:
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
