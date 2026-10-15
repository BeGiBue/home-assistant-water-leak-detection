"""Serve and load the bundled dashboard card, so no manual resource is needed.

HACS installs the card file together with the integration. At startup the
integration serves it under its own URL and registers it as an extra frontend
module, which every dashboard (storage and YAML mode) loads. The URL carries a
content digest, so browsers fetch a new version after every update.

Extra modules are written into the index page when HA serves it. HA serves the
frontend long before custom integrations are set up, and the frontend never
asks for extra modules again, so a page loaded while HA is starting (e.g. the
Companion app reconnecting after a restart) never got the card: HA's
``_customCreate`` then shows its "configuration error" card after two seconds
and waits for ``customElements.whenDefined`` forever. In storage resource mode
the integration therefore also keeps one Lovelace resource: a tiny ``data:``
module (no server request, available from the first dashboard load) that
imports the card and retries until the integration serves it. Once the element
is defined, HA's ``ll-rebuild`` replaces the error card by itself.

The card is optional: leak detection never depends on it. Without the frontend
(headless setups, tests) or on any registration error, setup simply continues.
"""

from __future__ import annotations

import json
import logging
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_FILE = Path(__file__).parent / "frontend" / "water-leak-guard-card.js"
CARD_URL = f"/{DOMAIN}/water-leak-guard-card.js"
DATA_CARD_URL = f"{DOMAIN}_card_url"


CARD_TAG = "water-leak-guard-card"
LOADER_MARKER = "water-leak-guard-card loader"
_LOADER_PREFIX = "data:text/javascript;charset=utf-8,"
LOADER_GRACE_MS = 3000


def loader_url(card_url: str) -> str:
    """The Lovelace resource: a data: module that loads the card, with retries.

    It needs no server route, so it works even when the dashboard loads before
    the integration serves the card. It first waits up to LOADER_GRACE_MS for the
    page's own extra module to define the card (then it does nothing, so a cached
    page with an older digest does not run a second copy). A retry adds a query
    parameter, because a browser may remember a failed module URL. Retries stop
    after 40 attempts, or after three failures once HA reports RUNNING (e.g. the
    files were removed but the resource was not).
    """
    source = (
        f"/* {LOADER_MARKER}: managed by the Water Leak Guard integration */"
        f"(()=>{{const T={json.dumps(CARD_TAG)},U={json.dumps(card_url)};let n=0,r=0;"
        # Stop after repeated failures once HA reports RUNNING (files removed, e.g.).
        "const running=()=>"
        "document.querySelector('home-assistant')?.hass?.config?.state==='RUNNING';"
        "const go=()=>{if(customElements.get(T))return;"
        "const u=new URL(U,location.origin);if(n)u.searchParams.set('retry',String(n));"
        "import(u.href).catch(()=>{n+=1;if(running())r+=1;"
        "if(n<=40&&r<3)setTimeout(go,Math.min(30000,1000*2**Math.min(n,5)));});};"
        # Give the page's own extra module a moment: no second copy when it defines the card.
        "Promise.race([customElements.whenDefined(T),"
        f"new Promise((d)=>setTimeout(d,{LOADER_GRACE_MS}))])"
        ".then(go);})();"
    )
    return _LOADER_PREFIX + quote(source, safe="")


def _is_loader(item: dict) -> bool:
    url = item.get("url")
    return isinstance(url, str) and quote(LOADER_MARKER, safe="") in url


def _storage_resources(hass: HomeAssistant):
    """The Lovelace resource collection in storage mode, else None (YAML mode, no Lovelace)."""
    from homeassistant.components.lovelace.const import LOVELACE_DATA
    from homeassistant.components.lovelace.resources import ResourceStorageCollection

    data = hass.data.get(LOVELACE_DATA)
    resources = getattr(data, "resources", None)
    return resources if isinstance(resources, ResourceStorageCollection) else None


async def async_ensure_loader_resource(hass: HomeAssistant, card_url: str) -> bool:
    """Keep exactly one current loader resource in storage mode; never raise."""
    try:
        resources = _storage_resources(hass)
        if resources is None:
            return False
        await resources.async_get_info()  # loads the collection
        url = loader_url(card_url)
        ours = [item for item in resources.async_items() if _is_loader(item)]
        if not ours:
            await resources.async_create_item({"res_type": "module", "url": url})
            return True
        first, *duplicates = ours
        if first.get("url") != url or first.get("type") != "module":
            await resources.async_update_item(first["id"], {"res_type": "module", "url": url})
        for item in duplicates:
            await resources.async_delete_item(item["id"])
    except Exception:  # the card must never block leak detection
        _LOGGER.warning("Dashboard card loader resource could not be registered", exc_info=True)
        return False
    return True


async def async_remove_loader_resource(hass: HomeAssistant) -> None:
    """Remove the loader resource when the last entry is removed; never raise."""
    try:
        resources = _storage_resources(hass)
        if resources is None:
            return
        await resources.async_get_info()
        for item in [item for item in resources.async_items() if _is_loader(item)]:
            await resources.async_delete_item(item["id"])
    except Exception:
        _LOGGER.warning("Dashboard card loader resource could not be removed", exc_info=True)


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()[:12]


async def async_register_card(hass: HomeAssistant) -> str | None:
    """Serve the card and load it in the frontend once; return the loaded URL."""
    if url := hass.data.get(DATA_CARD_URL):
        return url
    if getattr(hass, "http", None) is None or "frontend" not in hass.config.components:
        _LOGGER.debug("Frontend not loaded; dashboard card not registered")
        return None
    try:
        from homeassistant.components.frontend import add_extra_js_url
        from homeassistant.components.http import StaticPathConfig

        digest = await hass.async_add_executor_job(_digest, CARD_FILE)
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=True)]
        )
        url = f"{CARD_URL}?v={digest}"
        add_extra_js_url(hass, url)
    except Exception:  # the card must never block leak detection
        _LOGGER.warning("Dashboard card could not be registered", exc_info=True)
        return None
    hass.data[DATA_CARD_URL] = url
    await async_ensure_loader_resource(hass, url)
    return url
