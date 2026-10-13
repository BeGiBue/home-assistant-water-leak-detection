"""Independent PR14 counterexamples against real HA and production manager."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.water_leak_detection.const import CONF_EXTERNAL_SENSORS, DOMAIN
from custom_components.water_leak_detection.external_leaks import ExternalPhase
from custom_components.water_leak_detection.manager import WaterLeakManager


async def start(hass, entry, clock):
    hass.states.async_set(
        "sensor.flow", "0", {"unit_of_measurement": "L/h"}, timestamp=clock.utcnow().timestamp()
    )
    manager = WaterLeakManager(hass, entry)
    manager.notifications._async_common_translations = AsyncMock(return_value={})
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    await manager.async_setup()
    return manager


@pytest.mark.parametrize("reports", [0, 1, 5])
async def test_options_add_already_on_sensor_must_activate(
    runtime_hass, runtime_entry, measurement_clock, reports
):
    registry = er.async_get(runtime_hass)
    registry.async_get_or_create("binary_sensor", "test", "wet", suggested_object_id="wet")
    runtime_hass.states.async_set("binary_sensor.wet", "on")
    manager = await start(runtime_hass, runtime_entry, measurement_clock)
    await manager.async_update_options(
        {CONF_EXTERNAL_SENSORS: [{"id": "wet", "entity_id": "binary_sensor.wet"}]}
    )
    for _ in range(reports):
        runtime_hass.states.async_set("binary_sensor.wet", "on")
        await runtime_hass.async_block_till_done()
    disk = json.loads(Path(manager._store.path).read_text())["data"]
    assert manager.alarm_active and manager.shutoff_request, (
        manager.external_diagnostics(),
        disk["external_sources"],
    )


async def test_waiting_replacement_already_on_must_activate(
    runtime_hass, runtime_entry, measurement_clock
):
    registry = er.async_get(runtime_hass)
    registry.async_get_or_create("binary_sensor", "test", "old", suggested_object_id="old")
    registry.async_get_or_create("binary_sensor", "test", "new", suggested_object_id="new")
    runtime_hass.states.async_set("binary_sensor.old", "off")
    runtime_hass.states.async_set("binary_sensor.new", "on")
    runtime_hass.states.async_set("device_tracker.phone", "home")
    runtime_hass.config_entries.async_update_entry(
        runtime_entry,
        options={
            CONF_EXTERNAL_SENSORS: [{"id": "a", "entity_id": "binary_sensor.old"}],
            "notification_recipients": [
                {
                    "id": "phone",
                    "name": "Phone",
                    "notify_service": "notify.mobile_app_phone",
                    "tracker_entity": "device_tracker.phone",
                    "token": "token",
                    "allow_external_reset": True,
                }
            ],
        },
    )
    manager = await start(runtime_hass, runtime_entry, measurement_clock)
    runtime_hass.states.async_set("binary_sensor.old", "on")
    await runtime_hass.async_block_till_done()
    source = manager.external.sources["a"]
    payload = dict(
        action_kind="EXTERNAL_RESET",
        config_entry_id=runtime_entry.entry_id,
        source_id="a",
        source_generation=source.identity.generation,
        event_id=source.event_id,
        recipient_id="phone",
        recipient_token="token",
        reset_nonce=source.reset_nonce,
    )
    assert await manager.async_external_reset(payload)
    await manager.async_update_options(
        {
            **runtime_entry.options,
            CONF_EXTERNAL_SENSORS: [{"id": "a", "entity_id": "binary_sensor.new"}],
        }
    )
    assert manager.alarm_active and manager.shutoff_request, manager.external_diagnostics()


async def test_fresh_reset_notification_must_not_block_second_sensor(
    runtime_hass, runtime_entry, measurement_clock
):
    registry = er.async_get(runtime_hass)
    for name in ("a", "b"):
        registry.async_get_or_create("binary_sensor", "test", name, suggested_object_id=name)
        runtime_hass.states.async_set("binary_sensor." + name, "off")
    runtime_hass.states.async_set("device_tracker.phone", "home")
    runtime_hass.config_entries.async_update_entry(
        runtime_entry,
        options={
            CONF_EXTERNAL_SENSORS: [
                {"id": "a", "entity_id": "binary_sensor.a", "contributes_to_shutoff": False},
                {"id": "b", "entity_id": "binary_sensor.b"},
            ],
            "notification_recipients": [
                {
                    "id": "phone",
                    "name": "Phone",
                    "notify_service": "notify.mobile_app_phone",
                    "tracker_entity": "device_tracker.phone",
                    "token": "token",
                    "allow_external_reset": True,
                }
            ],
        },
    )
    manager = await start(runtime_hass, runtime_entry, measurement_clock)
    runtime_hass.states.async_set("binary_sensor.a", "on")
    await runtime_hass.async_block_till_done()
    event = manager.external.sources["a"].event_id
    manager.notifications.acknowledgements[event].globally_acknowledged = True
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow_notify(call):
        entered.set()
        await release.wait()

    runtime_hass.services.async_register("notify", "mobile_app_phone", slow_notify)
    request = asyncio.create_task(manager.async_request_external_reset_action("a", "phone"))
    await asyncio.wait_for(entered.wait(), 1)
    runtime_hass.states.async_set("binary_sensor.b", "on")
    for _ in range(10):
        await asyncio.sleep(0)
    observed = (
        manager.external.sources["b"].phase,
        manager.shutoff_request,
        manager._state_lock.locked(),
    )
    release.set()
    await request
    await runtime_hass.async_block_till_done()
    assert observed[0] is ExternalPhase.ACTIVE and observed[1], observed


@pytest.mark.parametrize("damage", ["future_version", "bad_wrapper"])
async def test_external_transition_must_not_overwrite_unrecoverable_store(
    runtime_hass, runtime_entry, measurement_clock, damage
):
    registry = er.async_get(runtime_hass)
    registry.async_get_or_create("binary_sensor", "test", "wet", suggested_object_id="wet")
    runtime_hass.states.async_set("binary_sensor.wet", "on")
    runtime_hass.config_entries.async_update_entry(
        runtime_entry,
        options={CONF_EXTERNAL_SENSORS: [{"id": "wet", "entity_id": "binary_sensor.wet"}]},
    )
    manager = WaterLeakManager(runtime_hass, runtime_entry)
    manager.notifications._async_common_translations = AsyncMock(return_value={})
    path = Path(manager._store.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = {
        "version": 3 if damage == "future_version" else "damaged",
        "minor_version": 1,
        "key": manager._store.key,
        "data": {
            "engine": {
                "runtimes": {
                    "burst_leak": {
                        "phase": "active",
                        "confirmed_active": True,
                        "event_id": "keep_me",
                    }
                }
            }
        },
    }
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    runtime_hass.states.async_set("sensor.flow", "0", {"unit_of_measurement": "L/h"})
    runtime_hass.data.setdefault(DOMAIN, {})[runtime_entry.entry_id] = manager
    await manager.async_setup()
    assert manager._storage_load_failed
    after = path.read_bytes()
    await manager.async_unload(save=False)
    runtime_hass.data[DOMAIN].pop(runtime_entry.entry_id)
    assert after == before, json.loads(after)


async def test_actual_options_flow_adds_wet_sensor_immediately(
    runtime_hass, runtime_entry, measurement_clock
):
    from homeassistant import loader

    import custom_components
    from custom_components.water_leak_detection.config_flow import WaterLeakOptionsFlow

    loader.async_setup(runtime_hass)
    runtime_hass.data[loader.DATA_INTEGRATIONS][DOMAIN] = loader.Integration.resolve_from_root(
        runtime_hass, custom_components, DOMAIN
    )
    registry = er.async_get(runtime_hass)
    registry.async_get_or_create("binary_sensor", "test", "wet", suggested_object_id="wet")
    runtime_hass.states.async_set("binary_sensor.wet", "on")
    runtime_hass.states.async_set("sensor.flow", "0", {"unit_of_measurement": "L/h"})
    assert await runtime_hass.config_entries.async_setup(runtime_entry.entry_id)
    await runtime_hass.async_block_till_done()
    manager = runtime_hass.data[DOMAIN][runtime_entry.entry_id]
    flow = WaterLeakOptionsFlow()
    flow.hass = runtime_hass
    flow.handler = runtime_entry.entry_id
    flow.flow_id = "independent"
    form = await flow.async_step_add_external_sensor()
    values = form["data_schema"]({"entity_id": "binary_sensor.wet", "contributes_to_shutoff": True})
    result = await flow.async_step_add_external_sensor(values)
    assert result["step_id"] == "external_sensors"
    await runtime_hass.async_block_till_done()
    observed = manager.alarm_active and manager.shutoff_request
    details = manager.external_diagnostics()
    await runtime_hass.config_entries.async_unload(runtime_entry.entry_id)
    assert observed, details
