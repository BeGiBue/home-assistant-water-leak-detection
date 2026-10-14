"""Serve and load the bundled dashboard card, so no manual resource is needed.

HACS installs the card file together with the integration. At startup the
integration serves it under its own URL and registers it as an extra frontend
module, which every dashboard (storage and YAML mode) loads. The URL carries a
content digest, so browsers fetch a new version after every update.

The card is optional: leak detection never depends on it. Without the frontend
(headless setups, tests) or on any registration error, setup simply continues.
"""

from __future__ import annotations

import logging
from hashlib import sha256
from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_FILE = Path(__file__).parent / "frontend" / "water-leak-guard-card.js"
CARD_URL = f"/{DOMAIN}/water-leak-guard-card.js"
DATA_CARD_URL = f"{DOMAIN}_card_url"


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
    return url
