"""The bundled dashboard card is served and loaded without a manual resource.

Registration is optional: leak detection must start without the frontend and
even when registering the card fails.
"""

import json
import logging
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

import pytest
from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.resources import (
    ResourceStorageCollection,
    ResourceYAMLCollection,
)
from homeassistant.exceptions import HomeAssistantError

from custom_components.water_leak_detection import async_remove_entry, async_setup
from custom_components.water_leak_detection.card import (
    CARD_FILE,
    CARD_URL,
    DATA_CARD_URL,
    LOADER_MARKER,
    async_register_card,
    loader_url,
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
    manifest = json.loads(Path("custom_components/water_leak_detection/manifest.json").read_text())
    assert manifest["dependencies"] == []
    assert set(manifest["after_dependencies"]) == {"frontend", "http", "lovelace"}


def test_card_file_reports_its_version():
    source = CARD_FILE.read_text()
    assert 'const CARD_VERSION = "0.6.1";' in source
    assert "static get cardVersion()" in source


class NoYamlConfig:
    """Lovelace default config without resources to import (storage mode)."""

    async def async_load(self, force):
        raise HomeAssistantError("no config")


def storage_resources(hass, items=()):
    collection = ResourceStorageCollection(hass, NoYamlConfig())
    hass.data[LOVELACE_DATA] = SimpleNamespace(resource_mode="storage", resources=collection)
    return collection


def loaders(collection):
    return [
        item
        for item in collection.async_items()
        if LOADER_MARKER.replace(" ", "%20") in item["url"]
    ]


async def test_storage_mode_keeps_exactly_one_current_loader_resource(runtime_hass):
    """The loader survives a page served before the integration was set up (card bug)."""
    collection = storage_resources(runtime_hass)
    await collection.async_get_info()
    own = await collection.async_create_item({"res_type": "module", "url": "/local/other.js"})
    with_frontend(runtime_hass, FakeHttp())
    url = await async_register_card(runtime_hass)
    (loader,) = loaders(collection)
    assert loader["type"] == "module" and loader["url"] == loader_url(url)
    assert loader["url"].startswith("data:text/javascript")  # needs no server route
    source = unquote(loader["url"].split(",", 1)[1])
    assert json.dumps(url) in source and "customElements.get" in source
    # New digest after an update: the same item is updated, duplicates removed.
    await collection.async_create_item({"res_type": "module", "url": loader["url"] + "%20"})
    runtime_hass.data.pop(DATA_CARD_URL)
    runtime_hass.http = FakeHttp()
    from custom_components.water_leak_detection import card as card_module

    original = card_module._digest
    card_module._digest = lambda path: "0123456789ab"
    try:
        new_url = await async_register_card(runtime_hass)
    finally:
        card_module._digest = original
    (updated,) = loaders(collection)
    assert updated["id"] == loader["id"] and updated["url"] == loader_url(new_url)
    # Other resources are never touched.
    assert collection.data[own["id"]]["url"] == "/local/other.js"
    # Removing the last entry removes the loader, keeping other resources.
    await async_remove_entry(runtime_hass, SimpleNamespace(entry_id="gone"))
    assert not loaders(collection) and own["id"] in collection.data


async def test_loader_is_kept_while_other_entries_exist(runtime_hass, runtime_entry):
    collection = storage_resources(runtime_hass)
    with_frontend(runtime_hass, FakeHttp())
    await async_register_card(runtime_hass)
    await async_remove_entry(runtime_hass, SimpleNamespace(entry_id="another"))
    assert len(loaders(collection)) == 1


async def test_yaml_mode_or_no_lovelace_only_uses_the_extra_module(runtime_hass):
    runtime_hass.data[LOVELACE_DATA] = SimpleNamespace(
        resource_mode="yaml", resources=ResourceYAMLCollection([])
    )
    loaded = with_frontend(runtime_hass, FakeHttp())
    url = await async_register_card(runtime_hass)
    assert loaded == {url} and runtime_hass.data[LOVELACE_DATA].resources.async_items() == []
    runtime_hass.data.pop(LOVELACE_DATA)
    runtime_hass.data.pop(DATA_CARD_URL)
    runtime_hass.http = FakeHttp()
    assert await async_register_card(runtime_hass) == url


async def test_loader_resource_error_never_blocks_setup(runtime_hass, caplog):
    collection = storage_resources(runtime_hass)

    async def broken(*_):
        raise RuntimeError("resource store unavailable")

    collection.async_get_info = broken
    loaded = with_frontend(runtime_hass, FakeHttp())
    with caplog.at_level(logging.WARNING):
        assert await async_setup(runtime_hass, {})
    assert loaded == {runtime_hass.data[DATA_CARD_URL]}
    assert "loader resource could not be registered" in caplog.text


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_loader_source_is_valid_javascript(tmp_path):
    source = unquote(loader_url(f"{CARD_URL}?v=abc").split(",", 1)[1])
    script = tmp_path / "loader.mjs"
    script.write_text(source)
    subprocess.run(["node", "--check", str(script)], check=True)
