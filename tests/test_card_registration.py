"""The bundled dashboard card is served and loaded without a manual resource.

Registration is optional: leak detection must start without the frontend and
even when registering the card fails.
"""

import json
import logging
from hashlib import sha256
from pathlib import Path

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL

from custom_components.water_leak_detection import async_setup
from custom_components.water_leak_detection.card import (
    CARD_FILE,
    CARD_URL,
    DATA_CARD_URL,
    async_register_card,
)
from custom_components.water_leak_detection.const import DOMAIN


class FakeHttp:
    """Records static paths like HomeAssistantHTTP.async_register_static_paths."""

    def __init__(self, fail=False):
        self.configs = []
        self.fail = fail

    async def async_register_static_paths(self, configs):
        if self.fail:
            raise RuntimeError("static path already registered")
        self.configs.extend(configs)


def with_frontend(hass, http):
    hass.http = http
    hass.config.components.add("frontend")
    loaded = set()  # UrlManager exposes add(); a set records the same calls
    hass.data[DATA_EXTRA_MODULE_URL] = loaded
    return loaded


async def test_card_is_served_and_loaded_once_with_content_digest(runtime_hass):
    loaded = with_frontend(runtime_hass, FakeHttp())
    url = await async_register_card(runtime_hass)

    digest = sha256(CARD_FILE.read_bytes()).hexdigest()[:12]
    assert url == f"{CARD_URL}?v={digest}"
    assert loaded == {url}
    (config,) = runtime_hass.http.configs
    assert config.url_path == CARD_URL == "/water_leak_detection/water-leak-guard-card.js"
    assert Path(config.path) == CARD_FILE and CARD_FILE.is_file()
    assert config.cache_headers is True  # safe: the digest changes with the content

    # A second call (e.g. reload) never registers twice.
    assert await async_register_card(runtime_hass) == url
    assert len(runtime_hass.http.configs) == 1 and loaded == {url}


async def test_setup_registers_card_and_services(runtime_hass):
    loaded = with_frontend(runtime_hass, FakeHttp())
    assert await async_setup(runtime_hass, {})
    assert loaded == {runtime_hass.data[DATA_CARD_URL]}
    assert runtime_hass.services.has_service(DOMAIN, "start_high_flow_bypass")


async def test_setup_without_frontend_skips_card_only(runtime_hass):
    assert await async_setup(runtime_hass, {})
    assert DATA_CARD_URL not in runtime_hass.data
    assert runtime_hass.services.has_service(DOMAIN, "start_high_flow_bypass")


async def test_card_registration_error_never_blocks_leak_detection(runtime_hass, caplog):
    loaded = with_frontend(runtime_hass, FakeHttp(fail=True))
    with caplog.at_level(logging.WARNING):
        assert await async_setup(runtime_hass, {})
    assert not loaded and DATA_CARD_URL not in runtime_hass.data
    assert runtime_hass.services.has_service(DOMAIN, "start_high_flow_bypass")
    assert "Dashboard card could not be registered" in caplog.text


def test_frontend_is_ordering_only_not_a_hard_dependency():
    manifest = json.loads(
        Path("custom_components/water_leak_detection/manifest.json").read_text()
    )
    assert manifest["dependencies"] == []
    assert set(manifest["after_dependencies"]) == {"frontend", "http"}


def test_card_file_reports_its_version():
    source = CARD_FILE.read_text()
    assert 'const CARD_VERSION = "0.3.1";' in source
    assert "static get cardVersion()" in source
