from __future__ import annotations

from typing import Any, Dict, Literal


StoreName = Literal["play", "app_store"]


DEFAULT_STORE_SECTION: Dict[str, Any] = {
    "global": {},
    "locales": {},
    "release_notes": {},
    "products": {},
    "subscriptions": {},
}


DEFAULT_LISTING_DOC: Dict[str, Any] = {
    "apps": {},
}
