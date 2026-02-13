from __future__ import annotations

import json
from pathlib import Path

from perfectdeckcli.cli import main


def test_cli_set_get_and_list(tmp_path: Path, capsys) -> None:
    listing_file = tmp_path / "listings.yaml"

    rc = main(
        [
            "--file",
            str(listing_file),
            "set",
            "--app",
            "prod",
            "--store",
            "play",
            "--locale",
            "en-US",
            "--key",
            "title",
            "--value",
            "AI Plant Doctor",
        ]
    )
    assert rc == 0
    capsys.readouterr()

    rc = main(
        [
            "--file",
            str(listing_file),
            "get",
            "--app",
            "prod",
            "--store",
            "play",
            "--locale",
            "en-US",
            "--key",
            "title",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload == "AI Plant Doctor"

    rc = main(
        [
            "--file",
            str(listing_file),
            "list",
            "--app",
            "prod",
            "--store",
            "play",
            "--locale",
            "en-US",
        ]
    )
    assert rc == 0


def test_cli_init_from_existing(tmp_path: Path, capsys) -> None:
    file_path = tmp_path / "listings.yaml"

    rc = main(
        [
            "--file",
            str(file_path),
            "init",
            "--app",
            "source",
            "--stores",
            "play",
            "--locales",
            "en-US,fr-FR",
            "--baseline-locale",
            "en-US",
        ]
    )
    assert rc == 0
    capsys.readouterr()

    rc = main(
        [
            "--file",
            str(file_path),
            "set",
            "--app",
            "source",
            "--store",
            "play",
            "--locale",
            "fr-FR",
            "--key",
            "title",
            "--value",
            "Bonjour",
        ]
    )
    assert rc == 0
    capsys.readouterr()

    rc = main(
        [
            "--file",
            str(file_path),
            "init-from-existing",
            "--app",
            "target",
            "--store",
            "app_store",
            "--from-app",
            "source",
            "--from-store",
            "play",
            "--locales",
            "fr-FR",
            "--baseline-locale",
            "fr-FR",
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ok"] is True
