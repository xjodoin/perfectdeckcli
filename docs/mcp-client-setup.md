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

