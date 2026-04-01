# Contributing

## Development setup

This project targets Python 3.11+.

Recommended setup:

```bash
uv venv
uv pip install -e ".[dev]"
```

## Local validation

Before opening a pull request, run:

```bash
pytest
python -m build
```

## Project structure

- `src/perfectdeckcli/cli.py`: CLI entrypoint
- `src/perfectdeckcli/mcp_server.py`: MCP server entrypoint and tool surface
- `src/perfectdeckcli/service.py`: listing mutation and versioning logic
- `src/perfectdeckcli/play_store.py`: Google Play API integration
- `src/perfectdeckcli/app_store.py`: App Store Connect API integration
- `tests/`: automated test suite

## Contribution guidelines

- Keep changes focused. Avoid mixing unrelated refactors with behavior changes.
- Add or update tests for behavior changes.
- Preserve backward compatibility unless the change is clearly documented.
- Do not commit credentials, API keys, `.listing_credentials.yaml`, or local
  snapshot state.

## Pull requests

When opening a pull request:

- Explain the user-facing behavior change.
- Mention any store API assumptions or edge cases.
- Include the validation you ran locally.

## Questions

If a change affects store-specific behavior, describe whether it was validated
against Google Play, App Store Connect, or only test fixtures.
