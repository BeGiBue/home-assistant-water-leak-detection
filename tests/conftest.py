"""Real Home Assistant primitives for runtime regression tests."""


from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.water_leak_detection.const import CONF_FLOW_ENTITY, DOMAIN


@pytest_asyncio.fixture
async def runtime_hass(tmp_path, monkeypatch):
    """Use actual states, event bus, services, registries, entries and disk Store."""
    hass = HomeAssistant(str(tmp_path))
    # Sandbox worker threads cannot wake the asyncio selector reliably. Execute
    # executor functions on the test loop; disk Store serialization/I/O stays real.
    def executor_job(executor, target, *args):
        future = hass.loop.create_future()
        try:
            future.set_result(target(*args))
        except Exception as err:
            future.set_exception(err)
        return future

    monkeypatch.setattr(hass.loop, "run_in_executor", executor_job)
    hass.config_entries = ConfigEntries(hass, {})
    dr.async_setup(hass)
    await dr.async_load(hass, load_empty=True)
    await er.async_load(hass, load_empty=True)
    yield hass
    for manager in tuple(hass.data.get(DOMAIN, {}).values()):
        await manager.async_unload()
    await hass.async_stop(force=True)
    hass.import_executor.shutdown(wait=True)


@pytest.fixture
def runtime_entry(runtime_hass):
    er.async_get(runtime_hass).async_get_or_create(
        "sensor", "test", "flow", suggested_object_id="flow"
    )
    entry = ConfigEntry(
        domain=DOMAIN, title="Review meter", data={CONF_FLOW_ENTITY: "sensor.flow"},
        options={}, version=1, minor_version=1, source="user", unique_id=None,
        discovery_keys={}, subentries_data=[],
    )
    # Register the actual entry without starting network/discovery/platform bootstrap.
    runtime_hass.config_entries._entries[entry.entry_id] = entry
    return entry


@pytest.fixture
def measurement_clock(monkeypatch):
    """Advance measurement wall/monotonic time without touching asyncio's clock."""
    class Clock:
        seconds = 0.0
        wall_shift = 0.0
        origin = datetime(2026, 10, 7, tzinfo=UTC)

        def utcnow(self):
            return self.origin + timedelta(seconds=self.seconds + self.wall_shift)

        def monotonic(self):
            return self.seconds

        def advance(self, seconds):
            self.seconds += seconds

    clock = Clock()
    monkeypatch.setattr(
        "custom_components.water_leak_detection.manager.dt_util.utcnow", clock.utcnow
    )
    monkeypatch.setattr("custom_components.water_leak_detection.manager.monotonic", clock.monotonic)
    return clock
