from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence, cast

from .models import StoreName
from .service import ListingService
from .storage import FileStorageBackend


def _json_or_string(raw: str, parse_json: bool) -> Any:
    if not parse_json:
        return raw
    return json.loads(raw)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="perfectdeckcli: manage Play Store and App Store listing elements.",
    )
    parser.add_argument("--file", type=Path, default=Path("listings.yaml"), help="Listing data file path.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    get_parser = subparsers.add_parser("get", help="Read one key from global or locale section.")
    get_parser.add_argument("--app", required=True)
    get_parser.add_argument("--store", required=True, choices=["play", "app_store"])
    get_parser.add_argument("--key", required=True, help="Dotted key path, e.g. metadata.title")
    get_parser.add_argument("--locale", help="Locale key. If omitted, uses global section.")

    set_parser = subparsers.add_parser("set", help="Set one key on global or locale section.")
    set_parser.add_argument("--app", required=True)
    set_parser.add_argument("--store", required=True, choices=["play", "app_store"])
    set_parser.add_argument("--key", required=True)
    set_parser.add_argument("--value", required=True)
    set_parser.add_argument("--json-value", action="store_true", help="Parse --value as JSON.")
    set_parser.add_argument("--locale")

    delete_parser = subparsers.add_parser("delete", help="Delete one key from global or locale section.")
    delete_parser.add_argument("--app", required=True)
    delete_parser.add_argument("--store", required=True, choices=["play", "app_store"])
    delete_parser.add_argument("--key", required=True)
    delete_parser.add_argument("--locale")

    upsert_parser = subparsers.add_parser("upsert-locale", help="Merge or replace an entire locale payload.")
    upsert_parser.add_argument("--app", required=True)
    upsert_parser.add_argument("--store", required=True, choices=["play", "app_store"])
    upsert_parser.add_argument("--locale", required=True)
    upsert_parser.add_argument("--data", required=True, help='JSON object string, e.g. {"title":"..."}')
    upsert_parser.add_argument("--replace", action="store_true", help="Replace locale content instead of merge.")

    list_parser = subparsers.add_parser("list", help="List the whole store section or one locale payload.")
    list_parser.add_argument("--app", required=True)
    list_parser.add_argument("--store", required=True, choices=["play", "app_store"])
    list_parser.add_argument("--locale")

    init_parser = subparsers.add_parser("init", help="Initialize listing skeleton for an app.")
    init_parser.add_argument("--app", required=True)
    init_parser.add_argument("--stores", default="play,app_store", help="Comma-separated stores.")
    init_parser.add_argument("--locales", help="Comma-separated locale list.")
    init_parser.add_argument("--baseline-locale", help="Baseline/source locale for translation tracking.")
    init_parser.add_argument("--overwrite", action="store_true")

    baseline_parser = subparsers.add_parser("set-baseline-language", help="Set baseline language for one app/store.")
    baseline_parser.add_argument("--app", required=True)
    baseline_parser.add_argument("--store", required=True, choices=["play", "app_store"])
    baseline_parser.add_argument("--locale", required=True)

    bump_parser = subparsers.add_parser("bump-version", help="Manually bump listing version.")
    bump_parser.add_argument("--app", required=True)
    bump_parser.add_argument("--store", required=True, choices=["play", "app_store"])
    bump_parser.add_argument("--reason", default="manual-bump")
    bump_parser.add_argument("--source-locale")

    mark_parser = subparsers.add_parser("mark-language-updated", help="Mark one language updated at current version.")
    mark_parser.add_argument("--app", required=True)
    mark_parser.add_argument("--store", required=True, choices=["play", "app_store"])
    mark_parser.add_argument("--locale", required=True)

    status_parser = subparsers.add_parser("status", help="Show translation update status.")
    status_parser.add_argument("--app", required=True)
    status_parser.add_argument("--store", required=True, choices=["play", "app_store"])

    init_existing_parser = subparsers.add_parser(
        "init-from-existing",
        help="Bootstrap a target listing from an existing listing source.",
    )
    init_existing_parser.add_argument("--app", required=True, help="Target app")
    init_existing_parser.add_argument("--store", required=True, choices=["play", "app_store"], help="Target store")
    init_existing_parser.add_argument("--from-app", required=True)
    init_existing_parser.add_argument("--from-store", required=True, choices=["play", "app_store"])
    init_existing_parser.add_argument("--from-file", type=Path, help="Optional source listing file path.")
    init_existing_parser.add_argument("--locales", help="Comma-separated subset of locales to copy.")
    init_existing_parser.add_argument("--baseline-locale")
    init_existing_parser.add_argument("--overwrite", action="store_true")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    service = ListingService(FileStorageBackend(args.file))
    store = cast(StoreName, getattr(args, "store", "play"))

    if args.command == "get":
        result = service.get_element(app=args.app, store=store, key_path=args.key, locale=args.locale)
    elif args.command == "set":
        value = _json_or_string(args.value, parse_json=args.json_value)
        result = service.set_element(app=args.app, store=store, key_path=args.key, value=value, locale=args.locale)
    elif args.command == "delete":
        result = service.delete_element(app=args.app, store=store, key_path=args.key, locale=args.locale)
    elif args.command == "upsert-locale":
        payload = json.loads(args.data)
        if not isinstance(payload, dict):
            raise ValueError("--data must be a JSON object")
        result = service.upsert_locale(
            app=args.app,
            store=store,
            locale=args.locale,
            data=payload,
            replace=bool(args.replace),
        )
    elif args.command == "list":
        result = service.list_section(app=args.app, store=store, locale=args.locale)
    elif args.command == "init":
        parsed_stores = [part.strip() for part in args.stores.split(",") if part.strip()]
        parsed_locales = [part.strip() for part in (args.locales or "").split(",") if part.strip()] or None
        result = service.init_listing(
            app=args.app,
            stores=cast(list[StoreName], parsed_stores),
            locales=parsed_locales,
            baseline_locale=args.baseline_locale,
            overwrite=bool(args.overwrite),
        )
    elif args.command == "set-baseline-language":
        result = service.set_baseline_locale(app=args.app, store=store, locale=args.locale)
    elif args.command == "bump-version":
        result = service.bump_version(
            app=args.app,
            store=store,
            reason=args.reason,
            source_locale=args.source_locale,
        )
    elif args.command == "mark-language-updated":
        result = service.mark_language_updated(app=args.app, store=store, locale=args.locale)
    elif args.command == "status":
        result = service.get_update_status(app=args.app, store=store)
    elif args.command == "init-from-existing":
        source_service = ListingService(FileStorageBackend(args.from_file)) if args.from_file else service
        source_section = source_service.list_section(
            app=args.from_app,
            store=cast(StoreName, args.from_store),
            locale=None,
        )
        selected_locales = [part.strip() for part in (args.locales or "").split(",") if part.strip()] or None
        result = service.init_from_existing_section(
            target_app=args.app,
            target_store=store,
            source_section=source_section,
            overwrite=bool(args.overwrite),
            locales=selected_locales,
            baseline_locale=args.baseline_locale,
        )
    else:
        parser.error(f"Unsupported command: {args.command}")
        return 2

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
