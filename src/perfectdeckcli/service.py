from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, MutableMapping, Sequence

from .models import DEFAULT_STORE_SECTION, StoreName
from .validation import validate_listing as _validate_listing

if TYPE_CHECKING:
    from .storage import StorageBackend


def _split_key_path(key_path: str) -> List[str]:
    parts = [part.strip() for part in key_path.split(".") if part.strip()]
    if not parts:
        raise ValueError("key path must not be empty")
    return parts


def _set_nested(mapping: MutableMapping[str, Any], key_path: str, value: Any) -> None:
    parts = _split_key_path(key_path)
    cursor: MutableMapping[str, Any] = mapping
    for part in parts[:-1]:
        existing = cursor.get(part)
        if existing is None:
            existing = {}
            cursor[part] = existing
        if not isinstance(existing, dict):
            raise ValueError(f"Cannot set '{key_path}': '{part}' is not an object.")
        cursor = existing
    cursor[parts[-1]] = value


def _get_nested(mapping: MutableMapping[str, Any], key_path: str) -> Any:
    parts = _split_key_path(key_path)
    cursor: Any = mapping
    for part in parts:
        if not isinstance(cursor, dict) or part not in cursor:
            raise KeyError(key_path)
        cursor = cursor[part]
    return cursor


def _delete_nested(mapping: MutableMapping[str, Any], key_path: str) -> bool:
    parts = _split_key_path(key_path)
    cursor: Any = mapping
    for part in parts[:-1]:
        if not isinstance(cursor, dict) or part not in cursor:
            return False
        cursor = cursor[part]
    if not isinstance(cursor, dict):
        return False
    return cursor.pop(parts[-1], None) is not None


def diff_objects(left: Any, right: Any, prefix: str = "") -> Dict[str, Any]:
    if isinstance(left, dict) and isinstance(right, dict):
        added: List[str] = []
        removed: List[str] = []
        changed: List[Dict[str, Any]] = []
        keys = set(left.keys()) | set(right.keys())
        for key in sorted(keys):
            key_prefix = f"{prefix}.{key}" if prefix else str(key)
            if key not in left:
                added.append(key_prefix)
                continue
            if key not in right:
                removed.append(key_prefix)
                continue
            nested = diff_objects(left[key], right[key], key_prefix)
            added.extend(nested["added"])
            removed.extend(nested["removed"])
            changed.extend(nested["changed"])
        return {"added": added, "removed": removed, "changed": changed}

    if left != right:
        return {
            "added": [],
            "removed": [],
            "changed": [{"path": prefix or "$", "before": left, "after": right}],
        }
    return {"added": [], "removed": [], "changed": []}


class ListingService:
    def __init__(self, storage: StorageBackend) -> None:
        self.storage = storage

    def get_credentials(self, app: str, store: str) -> Dict[str, Any]:
        return self.storage.load_credentials(app, store)

    def save_credentials(self, app: str, store: str, data: Dict[str, Any]) -> None:
        self.storage.save_credentials(app, store, data)

    def _doc(self) -> Dict[str, Any]:
        return self.storage.load()

    def _ensure_versioning(self, section: Dict[str, Any]) -> Dict[str, Any]:
        versioning = section.get("versioning")
        if not isinstance(versioning, dict):
            versioning = {}
            section["versioning"] = versioning

        current_version = versioning.get("current_version")
        if not isinstance(current_version, int) or current_version < 1:
            versioning["current_version"] = 1

        baseline_locale = versioning.get("baseline_locale")
        if baseline_locale is not None and not isinstance(baseline_locale, str):
            versioning["baseline_locale"] = None

        locale_versions = versioning.get("locale_versions")
        if not isinstance(locale_versions, dict):
            locale_versions = {}
            versioning["locale_versions"] = locale_versions

        changelog = versioning.get("changelog")
        if not isinstance(changelog, list):
            changelog = []
            versioning["changelog"] = changelog

        return versioning

    def _current_version(self, section: Dict[str, Any]) -> int:
        versioning = self._ensure_versioning(section)
        return int(versioning["current_version"])

    def _record_version_change(
        self,
        section: Dict[str, Any],
        *,
        reason: str,
        scope: str,
        locale: str | None = None,
    ) -> int:
        versioning = self._ensure_versioning(section)
        next_version = int(versioning["current_version"]) + 1
        versioning["current_version"] = next_version
        changelog = versioning["changelog"]
        changelog.append(
            {
                "version": next_version,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reason": reason,
                "scope": scope,
                "locale": locale,
            }
        )
        if len(changelog) > 200:
            del changelog[:-200]
        return next_version

    def _mark_locale_at_current_version(self, section: Dict[str, Any], locale: str) -> None:
        versioning = self._ensure_versioning(section)
        locale_versions = versioning["locale_versions"]
        locale_versions[locale] = self._current_version(section)

    def _store_section(
        self,
        doc: Dict[str, Any],
        app: str,
        store: StoreName,
        *,
        create: bool = True,
    ) -> Dict[str, Any]:
        apps = doc.setdefault("apps", {})
        app_payload = apps.get(app)
        if app_payload is None:
            if not create:
                raise KeyError(f"App not found: {app}")
            app_payload = {}
            apps[app] = app_payload
        if not isinstance(app_payload, dict):
            raise ValueError(f"Invalid app payload for {app}; expected object.")

        store_payload = app_payload.get(store)
        if store_payload is None:
            if not create:
                raise KeyError(f"Store not found: {app}/{store}")
            store_payload = deepcopy(DEFAULT_STORE_SECTION)
            app_payload[store] = store_payload
        if not isinstance(store_payload, dict):
            raise ValueError(f"Invalid store payload for {app}/{store}; expected object.")

        store_payload.setdefault("global", {})
        store_payload.setdefault("locales", {})
        store_payload.setdefault("release_notes", {})
        store_payload.setdefault("products", {})
        store_payload.setdefault("subscriptions", {})
        if not isinstance(store_payload["global"], dict):
            raise ValueError(f"{app}/{store}/global must be an object.")
        if not isinstance(store_payload["locales"], dict):
            raise ValueError(f"{app}/{store}/locales must be an object.")
        if not isinstance(store_payload["release_notes"], dict):
            store_payload["release_notes"] = {}
        if not isinstance(store_payload["products"], dict):
            store_payload["products"] = {}
        if not isinstance(store_payload["subscriptions"], dict):
            store_payload["subscriptions"] = {}
        self._ensure_versioning(store_payload)
        return store_payload

    def _apply_version_tracking_for_mutation(
        self,
        section: Dict[str, Any],
        *,
        reason: str,
        locale: str | None,
        default_scope_for_none: str,
    ) -> None:
        versioning = self._ensure_versioning(section)
        baseline_locale = versioning.get("baseline_locale")

        if locale is None:
            self._record_version_change(section, reason=reason, scope=default_scope_for_none, locale=None)
            return

        if baseline_locale is not None and locale == baseline_locale:
            self._record_version_change(section, reason=reason, scope="baseline", locale=locale)
            self._mark_locale_at_current_version(section, locale)
            return

        self._mark_locale_at_current_version(section, locale)

    def list_section(self, app: str, store: StoreName, locale: str | None = None) -> Dict[str, Any]:
        doc = self._doc()
        section = self._store_section(doc, app, store, create=False)
        if locale:
            return dict(section["locales"].get(locale, {}))
        result: Dict[str, Any] = {
            "global": dict(section["global"]),
            "locales": dict(section["locales"]),
        }
        products = section.get("products", {})
        subscriptions = section.get("subscriptions", {})
        if products:
            result["products"] = dict(products)
        if subscriptions:
            result["subscriptions"] = dict(subscriptions)
        return result

    def list_apps(self) -> List[str]:
        doc = self._doc()
        apps = doc.get("apps", {})
        if not isinstance(apps, dict):
            return []
        return sorted(str(item) for item in apps.keys())

    def list_stores(self, app: str) -> List[str]:
        doc = self._doc()
        apps = doc.get("apps", {})
        if not isinstance(apps, dict):
            return []
        app_payload = apps.get(app, {})
        if not isinstance(app_payload, dict):
            return []
        return sorted(str(store) for store in app_payload.keys())

    def init_listing(
        self,
        app: str,
        stores: Sequence[StoreName] | None = None,
        locales: Sequence[str] | None = None,
        baseline_locale: str | None = None,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        selected_stores = list(stores or ["play", "app_store"])
        doc = self._doc()
        apps = doc.setdefault("apps", {})
        app_payload = apps.get(app)
        if app_payload is None:
            app_payload = {}
            apps[app] = app_payload
        if not isinstance(app_payload, dict):
            raise ValueError(f"Invalid app payload for {app}; expected object.")

        initialized: List[str] = []
        for store in selected_stores:
            if overwrite or store not in app_payload or not isinstance(app_payload.get(store), dict):
                app_payload[store] = deepcopy(DEFAULT_STORE_SECTION)
                initialized.append(store)
            section = app_payload[store]
            if not isinstance(section, dict):
                raise ValueError(f"Invalid store payload for {app}/{store}; expected object.")
            section.setdefault("global", {})
            section.setdefault("locales", {})
            versioning = self._ensure_versioning(section)

            if locales:
                locale_map = section["locales"]
                if not isinstance(locale_map, dict):
                    raise ValueError(f"{app}/{store}/locales must be an object.")
                for locale in locales:
                    locale_map.setdefault(locale, {})
                    versioning["locale_versions"].setdefault(locale, versioning["current_version"])

            selected_baseline = baseline_locale or (locales[0] if locales else None)
            if selected_baseline:
                versioning["baseline_locale"] = selected_baseline
                versioning["locale_versions"].setdefault(selected_baseline, versioning["current_version"])

        self.storage.save(doc)
        return {"ok": True, "initialized_stores": initialized, "stores": selected_stores}

    def list_languages(self, app: str, store: StoreName) -> List[str]:
        doc = self._doc()
        section = self._store_section(doc, app, store, create=False)
        locales = section["locales"]
        if not isinstance(locales, dict):
            raise ValueError(f"{app}/{store}/locales must be an object.")
        return sorted(str(locale) for locale in locales.keys())

    def add_language(
        self,
        app: str,
        store: StoreName,
        locale: str,
        copy_from_locale: str | None = None,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        doc = self._doc()
        section = self._store_section(doc, app, store, create=True)
        locales = section["locales"]
        if not isinstance(locales, dict):
            raise ValueError(f"{app}/{store}/locales must be an object.")

        if copy_from_locale:
            source = locales.get(copy_from_locale)
            if source is None:
                raise KeyError(f"Source locale not found: {copy_from_locale}")
            if not isinstance(source, dict):
                raise ValueError(f"{app}/{store}/locales/{copy_from_locale} must be an object.")
            data = deepcopy(source)
        else:
            data = {}

        created = locale not in locales
        if created or overwrite:
            locales[locale] = data
        else:
            existing = locales.get(locale)
            if not isinstance(existing, dict):
                raise ValueError(f"{app}/{store}/locales/{locale} must be an object.")
            if copy_from_locale:
                for key, value in data.items():
                    existing.setdefault(key, value)

        versioning = self._ensure_versioning(section)
        versioning["locale_versions"].setdefault(locale, 0)
        self.storage.save(doc)
        return {"ok": True, "created": created, "locale": locale}

    def get_element(self, app: str, store: StoreName, key_path: str, locale: str | None = None) -> Any:
        doc = self._doc()
        section = self._store_section(doc, app, store, create=False)
        source = section["locales"].get(locale, {}) if locale else section["global"]
        if not isinstance(source, dict):
            raise ValueError("Requested section is not an object.")
        return _get_nested(source, key_path)

    def set_element(
        self,
        app: str,
        store: StoreName,
        key_path: str,
        value: Any,
        locale: str | None = None,
    ) -> Dict[str, Any]:
        doc = self._doc()
        section = self._store_section(doc, app, store, create=True)
        if locale:
            locales = section["locales"]
            current = locales.get(locale)
            if current is None:
                current = {}
                locales[locale] = current
            if not isinstance(current, dict):
                raise ValueError(f"{app}/{store}/locales/{locale} must be an object.")
            target = current
        else:
            target = section["global"]
        _set_nested(target, key_path, value)

        self._apply_version_tracking_for_mutation(
            section,
            reason=f"set:{key_path}",
            locale=locale,
            default_scope_for_none="global",
        )
        self.storage.save(doc)
        return {"ok": True}

    def replace_section(
        self,
        app: str,
        store: StoreName,
        payload: Dict[str, Any],
        locale: str | None = None,
        merge: bool = False,
    ) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        doc = self._doc()
        section = self._store_section(doc, app, store, create=True)
        if locale:
            locales = section["locales"]
            current = locales.get(locale)
            if merge and isinstance(current, dict):
                current.update(deepcopy(payload))
            else:
                locales[locale] = deepcopy(payload)
            self._apply_version_tracking_for_mutation(
                section,
                reason="replace-section",
                locale=locale,
                default_scope_for_none="store",
            )
        else:
            if "global" in payload or "locales" in payload:
                global_payload = payload.get("global", {})
                locales_payload = payload.get("locales", {})
                if not isinstance(global_payload, dict) or not isinstance(locales_payload, dict):
                    raise ValueError("section payload must contain object values for global/locales")
                if merge:
                    section["global"].update(deepcopy(global_payload))
                    section["locales"].update(deepcopy(locales_payload))
                else:
                    section["global"] = deepcopy(global_payload)
                    section["locales"] = deepcopy(locales_payload)
            elif merge and isinstance(section["global"], dict):
                section["global"].update(deepcopy(payload))
            else:
                section["global"] = deepcopy(payload)

            self._record_version_change(section, reason="replace-section", scope="store", locale=None)
        self.storage.save(doc)
        return {"ok": True}

    def delete_element(
        self,
        app: str,
        store: StoreName,
        key_path: str,
        locale: str | None = None,
    ) -> Dict[str, Any]:
        doc = self._doc()
        section = self._store_section(doc, app, store, create=False)
        if locale:
            target = section["locales"].get(locale, {})
            if not isinstance(target, dict):
                raise ValueError(f"{app}/{store}/locales/{locale} must be an object.")
        else:
            target = section["global"]
        deleted = _delete_nested(target, key_path)
        if deleted:
            self._apply_version_tracking_for_mutation(
                section,
                reason=f"delete:{key_path}",
                locale=locale,
                default_scope_for_none="global",
            )
        self.storage.save(doc)
        return {"ok": True, "deleted": deleted}

    def upsert_locale(
        self,
        app: str,
        store: StoreName,
        locale: str,
        data: Dict[str, Any],
        replace: bool = False,
    ) -> Dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("locale data must be an object")
        doc = self._doc()
        section = self._store_section(doc, app, store, create=True)
        locales = section["locales"]
        existing = locales.get(locale)
        if existing is None or replace:
            locales[locale] = deepcopy(data)
        else:
            if not isinstance(existing, dict):
                raise ValueError(f"{app}/{store}/locales/{locale} must be an object.")
            existing.update(data)

        self._apply_version_tracking_for_mutation(
            section,
            reason="upsert-locale",
            locale=locale,
            default_scope_for_none="store",
        )
        self.storage.save(doc)
        return {"ok": True}

    def set_baseline_locale(self, app: str, store: StoreName, locale: str) -> Dict[str, Any]:
        doc = self._doc()
        section = self._store_section(doc, app, store, create=True)
        locales = section["locales"]
        locales.setdefault(locale, {})
        versioning = self._ensure_versioning(section)
        versioning["baseline_locale"] = locale
        versioning["locale_versions"].setdefault(locale, self._current_version(section))
        self.storage.save(doc)
        return {"ok": True, "baseline_locale": locale}

    def _save_snapshot(
        self,
        app: str,
        store: StoreName,
        section: Dict[str, Any],
        version: int,
        reason: str,
    ) -> None:
        snapshot_data = {
            "version": version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "global": deepcopy(section.get("global", {})),
            "locales": deepcopy(section.get("locales", {})),
        }
        self.storage.save_snapshot(app, store, version, snapshot_data)

    def bump_version(
        self,
        app: str,
        store: StoreName,
        reason: str,
        source_locale: str | None = None,
    ) -> Dict[str, Any]:
        doc = self._doc()
        section = self._store_section(doc, app, store, create=True)

        # Snapshot current state before bumping
        current_ver = self._current_version(section)
        self._save_snapshot(app, store, section, current_ver, reason or "manual-bump")

        scope = "manual"
        if source_locale:
            baseline_locale = self._ensure_versioning(section).get("baseline_locale")
            scope = "baseline" if baseline_locale == source_locale else "locale"
        next_version = self._record_version_change(
            section,
            reason=reason or "manual-bump",
            scope=scope,
            locale=source_locale,
        )
        if source_locale:
            self._mark_locale_at_current_version(section, source_locale)
        self.storage.save(doc)
        return {"ok": True, "current_version": next_version}

    def mark_language_updated(self, app: str, store: StoreName, locale: str) -> Dict[str, Any]:
        doc = self._doc()
        section = self._store_section(doc, app, store, create=True)
        locales = section["locales"]
        locales.setdefault(locale, {})
        self._mark_locale_at_current_version(section, locale)
        self.storage.save(doc)
        return {"ok": True, "locale": locale, "version": self._current_version(section)}

    def get_update_status(self, app: str, store: StoreName) -> Dict[str, Any]:
        doc = self._doc()
        section = self._store_section(doc, app, store, create=False)
        versioning = self._ensure_versioning(section)
        current_version = self._current_version(section)
        baseline_locale = versioning.get("baseline_locale")
        locale_versions = versioning.get("locale_versions", {})
        locales = section["locales"]

        stale_locales: List[str] = []
        up_to_date_locales: List[str] = []
        missing_version_locales: List[str] = []

        for locale in sorted(locales.keys()):
            raw = locale_versions.get(locale)
            if not isinstance(raw, int):
                missing_version_locales.append(locale)
                stale_locales.append(locale)
                continue
            if raw < current_version:
                stale_locales.append(locale)
            else:
                up_to_date_locales.append(locale)

        if baseline_locale and baseline_locale in stale_locales:
            stale_locales.remove(baseline_locale)
            up_to_date_locales.append(baseline_locale)
            up_to_date_locales = sorted(set(up_to_date_locales))

        return {
            "current_version": current_version,
            "baseline_locale": baseline_locale,
            "stale_locales": stale_locales,
            "up_to_date_locales": up_to_date_locales,
            "missing_version_locales": missing_version_locales,
            "changelog": list(versioning.get("changelog", [])),
        }

    @staticmethod
    def _map_play_store_data(data: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
        """Map raw Play Store API data to PerfectDeck locale keys.

        Input  ``{locale: {title, shortDescription, fullDescription}}``
        Output ``{locale: {title, short_description, full_description}}``
        """
        mapped_locales: Dict[str, Dict[str, str]] = {}
        for locale, fields in sorted(data.items()):
            mapped: Dict[str, str] = {}
            if fields.get("title"):
                mapped["title"] = fields["title"]
            if fields.get("shortDescription"):
                mapped["short_description"] = fields["shortDescription"]
            if fields.get("fullDescription"):
                mapped["full_description"] = fields["fullDescription"]
            if mapped:
                mapped_locales[locale] = mapped
        return mapped_locales

    @staticmethod
    def _map_app_store_data(data: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Filter empty values from already-mapped App Store data."""
        mapped_locales: Dict[str, Dict[str, Any]] = {}
        for locale, fields in sorted(data.items()):
            mapped = {k: v for k, v in fields.items() if v}
            if mapped:
                mapped_locales[locale] = mapped
        return mapped_locales

    def import_from_play_store(
        self,
        app: str,
        data: Dict[str, Dict[str, str]],
        global_data: Dict[str, str] | None = None,
        products_data: Dict[str, Any] | None = None,
        subscriptions_data: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Import fetched Play Store listings into the local ``play`` store.

        *data* is ``{locale: {title, shortDescription, fullDescription}}`` as
        returned by :func:`play_store.fetch_listings`.
        *global_data* is app-level metadata (defaultLanguage, contact info).
        *products_data* is ``{product_id: {...}}`` for one-time products.
        *subscriptions_data* is ``{subscription_id: {...}}`` for subscriptions.
        """
        mapped_locales = self._map_play_store_data(data)
        doc = self._doc()
        section = self._store_section(doc, app, "play", create=True)

        # Populate global section with app-level data
        if global_data:
            section["global"].update(global_data)

        locales_map = section["locales"]
        imported_locales: List[str] = []

        for locale, mapped in mapped_locales.items():
            existing = locales_map.get(locale)
            if existing is None or not isinstance(existing, dict):
                locales_map[locale] = mapped
            else:
                existing.update(mapped)

            self._mark_locale_at_current_version(section, locale)
            imported_locales.append(locale)

        # Store products and subscriptions data
        if products_data:
            section["products"] = deepcopy(products_data)
        if subscriptions_data:
            section["subscriptions"] = deepcopy(subscriptions_data)

        self._record_version_change(
            section, reason="import-from-play-store", scope="store", locale=None,
        )
        self.storage.save(doc)

        # Snapshot state after import
        new_ver = self._current_version(section)
        self._save_snapshot(app, "play", section, new_ver, "import-from-play-store")

        return {"ok": True, "imported_locales": imported_locales}

    def import_from_app_store(
        self,
        app: str,
        data: Dict[str, Dict[str, Any]],
        global_data: Dict[str, str] | None = None,
        products_data: Dict[str, Any] | None = None,
        subscriptions_data: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Import fetched App Store listings into the local ``app_store`` store.

        *data* is ``{locale: {app_name, subtitle, description, …}}`` as
        returned by :func:`app_store.fetch_listings` (already mapped to
        PerfectDeck key names).
        *global_data* is app-level metadata (primaryLocale, bundleId, etc.).
        *products_data* is ``{product_id: {...}}`` for in-app purchases.
        *subscriptions_data* is ``{subscription_id: {...}}`` for subscriptions.
        """
        mapped_locales = self._map_app_store_data(data)
        doc = self._doc()
        section = self._store_section(doc, app, "app_store", create=True)

        # Populate global section with app-level data
        if global_data:
            section["global"].update(global_data)

        locales_map = section["locales"]
        imported_locales: List[str] = []

        for locale, mapped in mapped_locales.items():
            existing = locales_map.get(locale)
            if existing is None or not isinstance(existing, dict):
                locales_map[locale] = mapped
            else:
                existing.update(mapped)

            self._mark_locale_at_current_version(section, locale)
            imported_locales.append(locale)

        # Store products and subscriptions data
        if products_data:
            section["products"] = deepcopy(products_data)
        if subscriptions_data:
            section["subscriptions"] = deepcopy(subscriptions_data)

        self._record_version_change(
            section, reason="import-from-app-store", scope="store", locale=None,
        )
        self.storage.save(doc)

        # Snapshot state after import
        new_ver = self._current_version(section)
        self._save_snapshot(app, "app_store", section, new_ver, "import-from-app-store")

        return {"ok": True, "imported_locales": imported_locales}

    def diff_with_play_store_data(
        self,
        app: str,
        data: Dict[str, Dict[str, str]],
    ) -> Dict[str, Any]:
        """Diff fetched Play Store data against local ``play`` store (read-only).

        Returns per-locale diffs showing what would change if imported.
        """
        mapped_locales = self._map_play_store_data(data)
        return self._diff_remote_vs_local(app, "play", mapped_locales)

    def diff_with_app_store_data(
        self,
        app: str,
        data: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Diff fetched App Store data against local ``app_store`` store (read-only).

        Returns per-locale diffs showing what would change if imported.
        """
        mapped_locales = self._map_app_store_data(data)
        return self._diff_remote_vs_local(app, "app_store", mapped_locales)

    def _diff_remote_vs_local(
        self,
        app: str,
        store: StoreName,
        remote_locales: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compare mapped remote locale data against local store (read-only).

        Returns ``{locales: {locale: {added, removed, changed, same}}, summary: …}``.
        """
        doc = self._doc()
        try:
            section = self._store_section(doc, app, store, create=False)
            local_locales = section.get("locales", {})
        except KeyError:
            local_locales = {}

        all_locales = sorted(set(remote_locales.keys()) | set(local_locales.keys()))
        per_locale: Dict[str, Any] = {}
        new_locales: List[str] = []
        changed_locales: List[str] = []
        unchanged_locales: List[str] = []

        for locale in all_locales:
            local_data = local_locales.get(locale, {})
            if not isinstance(local_data, dict):
                local_data = {}
            remote_data = remote_locales.get(locale, {})

            if locale not in remote_locales:
                # Locale only exists locally — nothing from remote to compare
                continue

            diff = diff_objects(local_data, remote_data)
            is_same = not diff["added"] and not diff["removed"] and not diff["changed"]
            diff["same"] = is_same
            per_locale[locale] = diff

            if locale not in local_locales or not local_data:
                new_locales.append(locale)
            elif not is_same:
                changed_locales.append(locale)
            else:
                unchanged_locales.append(locale)

        return {
            "locales": per_locale,
            "summary": {
                "new_locales": new_locales,
                "changed_locales": changed_locales,
                "unchanged_locales": unchanged_locales,
                "total_remote": len(remote_locales),
            },
        }

    def init_from_existing_section(
        self,
        *,
        target_app: str,
        target_store: StoreName,
        source_section: Dict[str, Any],
        overwrite: bool = False,
        locales: Sequence[str] | None = None,
        baseline_locale: str | None = None,
    ) -> Dict[str, Any]:
        if not isinstance(source_section, dict):
            raise ValueError("source_section must be an object")
        source_global = source_section.get("global", {})
        source_locales = source_section.get("locales", {})
        if not isinstance(source_global, dict) or not isinstance(source_locales, dict):
            raise ValueError("source_section must contain object values for global/locales")

        selected_locales = (
            [locale for locale in locales if locale in source_locales]
            if locales is not None
            else sorted(source_locales.keys())
        )
        copied_locales = {locale: deepcopy(source_locales[locale]) for locale in selected_locales}
        selected_baseline = baseline_locale or next(iter(copied_locales.keys()), None)

        doc = self._doc()
        section = self._store_section(doc, target_app, target_store, create=True)

        has_existing_data = bool(section.get("global")) or bool(section.get("locales"))
        if has_existing_data and not overwrite:
            raise ValueError(
                f"Target listing {target_app}/{target_store} already has data. Use overwrite=true to replace."
            )

        section["global"] = deepcopy(source_global)
        section["locales"] = copied_locales

        versioning = self._ensure_versioning(section)
        versioning["current_version"] = 1
        versioning["baseline_locale"] = selected_baseline
        versioning["locale_versions"] = {locale: 1 for locale in copied_locales.keys()}
        versioning["changelog"] = [
            {
                "version": 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reason": "init-from-existing",
                "scope": "store",
                "locale": None,
            }
        ]

        self.storage.save(doc)
        return {
            "ok": True,
            "target_app": target_app,
            "target_store": target_store,
            "locales_copied": sorted(copied_locales.keys()),
            "baseline_locale": selected_baseline,
        }

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def save_snapshot(
        self,
        app: str,
        store: StoreName,
        reason: str | None = None,
    ) -> Dict[str, Any]:
        """Explicitly save a snapshot of the current listing state."""
        doc = self._doc()
        section = self._store_section(doc, app, store, create=False)
        version = self._current_version(section)
        self._save_snapshot(app, store, section, version, reason or "manual-snapshot")
        return {"ok": True, "version": version}

    def list_snapshots(
        self,
        app: str,
        store: StoreName,
    ) -> List[Dict[str, Any]]:
        """List available version snapshots for an app/store."""
        return self.storage.list_snapshots(app, store)

    def restore_snapshot(
        self,
        app: str,
        store: StoreName,
        version: int | None = None,
    ) -> Dict[str, Any]:
        """Restore listing data from a snapshot version.

        If *version* is ``None``, restores from the latest snapshot.
        """
        if version is None:
            version = self.storage.latest_snapshot_version(app, store)
            if version is None:
                raise FileNotFoundError(f"No snapshots found for {app}/{store}")

        snapshot = self.storage.load_snapshot(app, store, version)
        doc = self._doc()
        section = self._store_section(doc, app, store, create=True)

        # Replace global + locales data from snapshot
        section["global"] = deepcopy(snapshot.get("global", {}))
        section["locales"] = deepcopy(snapshot.get("locales", {}))

        # Record version change for the restoration
        new_ver = self._record_version_change(
            section,
            reason=f"restore-from-v{version}",
            scope="store",
            locale=None,
        )
        self.storage.save(doc)
        return {"ok": True, "restored_version": version, "current_version": new_ver}

    def diff_with_snapshot(
        self,
        app: str,
        store: StoreName,
        version: int | None = None,
    ) -> Dict[str, Any]:
        """Diff current listing data against a snapshot version.

        If *version* is ``None``, diffs against the latest snapshot.
        """
        if version is None:
            version = self.storage.latest_snapshot_version(app, store)
            if version is None:
                raise FileNotFoundError(f"No snapshots found for {app}/{store}")

        snapshot = self.storage.load_snapshot(app, store, version)
        doc = self._doc()
        section = self._store_section(doc, app, store, create=False)

        current_data = {
            "global": section.get("global", {}),
            "locales": section.get("locales", {}),
        }
        snapshot_data = {
            "global": snapshot.get("global", {}),
            "locales": snapshot.get("locales", {}),
        }

        diff = diff_objects(snapshot_data, current_data)
        diff["same"] = not diff["added"] and not diff["removed"] and not diff["changed"]
        return {
            "snapshot_version": version,
            "diff": diff,
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_listing(
        self,
        app: str,
        store: StoreName,
        locales: Sequence[str] | None = None,
    ) -> Dict[str, Any]:
        """Validate local listing data against store character limits.

        Returns ``{"ok": bool, "errors": [...]}``.
        """
        doc = self._doc()
        section = self._store_section(doc, app, store, create=False)
        locales_map = section.get("locales", {})

        if locales:
            locales_map = {k: v for k, v in locales_map.items() if k in locales}

        return _validate_listing(store, locales_map)

    # ------------------------------------------------------------------
    # Release notes
    # ------------------------------------------------------------------

    def set_release_notes(
        self,
        app: str,
        store: StoreName,
        app_version: str,
        locale: str,
        text: str,
    ) -> Dict[str, Any]:
        doc = self._doc()
        section = self._store_section(doc, app, store, create=True)
        rn = section["release_notes"]
        version_notes = rn.get(app_version)
        if version_notes is None:
            version_notes = {}
            rn[app_version] = version_notes
        if not isinstance(version_notes, dict):
            raise ValueError(f"release_notes[{app_version}] must be an object.")
        version_notes[locale] = text
        self.storage.save(doc)
        return {"ok": True}

    def upsert_release_notes(
        self,
        app: str,
        store: StoreName,
        app_version: str,
        data: Dict[str, str],
    ) -> Dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("data must be an object")
        doc = self._doc()
        section = self._store_section(doc, app, store, create=True)
        rn = section["release_notes"]
        version_notes = rn.get(app_version)
        if version_notes is None:
            version_notes = {}
            rn[app_version] = version_notes
        if not isinstance(version_notes, dict):
            raise ValueError(f"release_notes[{app_version}] must be an object.")
        version_notes.update(data)
        self.storage.save(doc)
        return {"ok": True}

    def get_release_notes(
        self,
        app: str,
        store: StoreName,
        app_version: str,
        locale: str | None = None,
    ) -> Dict[str, Any]:
        doc = self._doc()
        section = self._store_section(doc, app, store, create=False)
        rn = section["release_notes"]
        version_notes = rn.get(app_version)
        if version_notes is None:
            raise KeyError(f"No release notes for version {app_version}")
        if not isinstance(version_notes, dict):
            raise ValueError(f"release_notes[{app_version}] must be an object.")
        if locale is not None:
            text = version_notes.get(locale)
            if text is None:
                raise KeyError(f"No release notes for {app_version}/{locale}")
            return {"app_version": app_version, "locale": locale, "text": text}
        return {"app_version": app_version, "notes": dict(version_notes)}

    def list_release_versions(
        self,
        app: str,
        store: StoreName,
    ) -> List[str]:
        doc = self._doc()
        section = self._store_section(doc, app, store, create=False)
        rn = section["release_notes"]
        return sorted(rn.keys())

    def delete_release_notes(
        self,
        app: str,
        store: StoreName,
        app_version: str,
    ) -> Dict[str, Any]:
        doc = self._doc()
        section = self._store_section(doc, app, store, create=False)
        rn = section["release_notes"]
        deleted = rn.pop(app_version, None) is not None
        self.storage.save(doc)
        return {"ok": True, "deleted": deleted}

    def validate_release_notes(
        self,
        app: str,
        store: StoreName,
        app_version: str | None = None,
    ) -> Dict[str, Any]:
        doc = self._doc()
        section = self._store_section(doc, app, store, create=False)
        rn = section["release_notes"]
        listing_locales = set(section["locales"].keys())

        char_limit = 500 if store == "play" else 4000

        versions_to_check: List[str]
        if app_version is not None:
            if app_version not in rn:
                raise KeyError(f"No release notes for version {app_version}")
            versions_to_check = [app_version]
        else:
            versions_to_check = sorted(rn.keys())

        all_ok = True
        versions_result: Dict[str, Any] = {}
        for ver in versions_to_check:
            notes = rn[ver]
            if not isinstance(notes, dict):
                continue
            errors: List[Dict[str, Any]] = []
            note_locales = set(notes.keys())

            for loc, text in sorted(notes.items()):
                length = len(str(text))
                if length > char_limit:
                    errors.append({
                        "locale": loc,
                        "length": length,
                        "limit": char_limit,
                        "over_by": length - char_limit,
                    })

            missing = sorted(listing_locales - note_locales)
            extra = sorted(note_locales - listing_locales)
            ok = len(errors) == 0
            if not ok or missing or extra:
                all_ok = False
            versions_result[ver] = {
                "ok": ok,
                "errors": errors,
                "missing_locales": missing,
                "extra_locales": extra,
            }

        return {"ok": all_ok, "versions": versions_result}

    # ------------------------------------------------------------------
    # Prepare data for push
    # ------------------------------------------------------------------

    def prepare_play_push_data(
        self,
        app: str,
        locales: Sequence[str] | None = None,
    ) -> Dict[str, Dict[str, str]]:
        """Read local ``play`` listing and return Play Store API-formatted data.

        Returns ``{play_locale: {title, shortDescription, fullDescription}}``.
        Applies locale mapping from :mod:`play_store`.
        """
        from . import play_store as ps

        doc = self._doc()
        section = self._store_section(doc, app, "play", create=False)
        locales_map = section.get("locales", {})

        if locales:
            locales_map = {k: v for k, v in locales_map.items() if k in locales}

        result: Dict[str, Dict[str, str]] = {}
        for locale, fields in sorted(locales_map.items()):
            if not isinstance(fields, dict):
                continue
            play_locale = ps.map_locale(locale)
            body: Dict[str, str] = {}
            if fields.get("title"):
                body["title"] = fields["title"]
            if fields.get("short_description"):
                body["shortDescription"] = fields["short_description"]
            if fields.get("full_description"):
                body["fullDescription"] = fields["full_description"]
            if body:
                result[play_locale] = body

        return result

    def prepare_play_release_notes(
        self,
        app: str,
        app_version: str,
        locales: Sequence[str] | None = None,
    ) -> Dict[str, str]:
        """Read release notes for *app_version* from the ``play`` store.

        Returns ``{play_locale: text}``.
        """
        from . import play_store as ps

        doc = self._doc()
        section = self._store_section(doc, app, "play", create=False)
        rn = section["release_notes"]
        version_notes = rn.get(app_version, {})
        if not isinstance(version_notes, dict):
            return {}

        if locales:
            version_notes = {k: v for k, v in version_notes.items() if k in locales}

        result: Dict[str, str] = {}
        for locale, text in sorted(version_notes.items()):
            if text:
                play_locale = ps.map_locale(locale)
                result[play_locale] = str(text)

        return result

    def prepare_app_store_push_data(
        self,
        app: str,
        locales: Sequence[str] | None = None,
        *,
        app_version: str | None = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Read local ``app_store`` listing data for push.

        When *app_version* is set, ``whats_new`` is injected from
        ``release_notes[app_version]`` for each locale.

        Returns ``{locale: {app_name, subtitle, description, keywords, …}}``.
        """
        doc = self._doc()
        section = self._store_section(doc, app, "app_store", create=False)
        locales_map = section.get("locales", {})

        if locales:
            locales_map = {k: v for k, v in locales_map.items() if k in locales}

        version_notes: Dict[str, str] = {}
        if app_version:
            rn = section["release_notes"]
            raw = rn.get(app_version, {})
            if isinstance(raw, dict):
                version_notes = raw

        result: Dict[str, Dict[str, Any]] = {}
        for locale, fields in sorted(locales_map.items()):
            if not isinstance(fields, dict):
                continue
            filtered = {k: v for k, v in fields.items() if v}
            if app_version and locale in version_notes and version_notes[locale]:
                filtered["whats_new"] = version_notes[locale]
            if filtered:
                result[locale] = filtered

        return result
