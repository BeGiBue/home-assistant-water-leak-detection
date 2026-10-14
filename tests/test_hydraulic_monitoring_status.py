"""Visibility uses manager decisions, never changes hydraulic safety state."""

import json
from pathlib import Path

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from test_f04_mqtt_latency import deliver
from test_hydrus_mqtt_diagnostics import HydrusTransport, running
from test_hydrus_mqtt_startup import start

from custom_components.water_leak_detection.const import DOMAIN, DetectorKind
from custom_components.water_leak_detection.manager import WaterLeakManager
from custom_components.water_leak_detection.sensor import HydraulicMonitoringStatusSensor


async def test_initial_wait_and_fresh_measurement(runtime_hass, runtime_entry, measurement_clock):
    transport = HydrusTransport(runtime_hass, runtime_entry, measurement_clock, True)
    manager = await start(runtime_hass, runtime_entry)
    entity = HydraulicMonitoringStatusSensor(manager)
    assert entity.available
    assert entity.native_value == "waiting_for_measurement"
    assert entity.extra_state_attributes["last_valid_measurement"] is None
    assert entity.extra_state_attributes["observation_age_seconds"] is None
    await deliver(transport, measurement_clock, 0.25, 60, 0.1, 0)
    assert entity.native_value == "active"
    attributes = entity.extra_state_attributes
    assert attributes["reason"] == "verified_measurement"
    assert attributes["mqtt_provenance_status"] == "verified_original_measurement"
    assert attributes["source_available"]
    assert attributes["source_entity_id"] == "sensor.flow"
    assert attributes["last_valid_measurement"] == manager._last_valid_reported_at.isoformat()
    measurement_clock.advance(10)
    assert entity.extra_state_attributes["observation_age_seconds"] == pytest.approx(10)


async def test_first_rejected_original_is_blocked_not_waiting(
    runtime_hass, runtime_entry, measurement_clock
):
    transport = HydrusTransport(runtime_hass, runtime_entry, measurement_clock, True)
    manager = await start(runtime_hass, runtime_entry)
    entity = HydraulicMonitoringStatusSensor(manager)
    await deliver(transport, measurement_clock, 0, -1, 61, 0)
    assert entity.available
    assert entity.native_value == "blocked"
    assert entity.extra_state_attributes["reason"] == "pre_startup_measurement"
    assert entity.extra_state_attributes["last_valid_measurement"] is None
    await manager._async_tick(measurement_clock.utcnow())
    assert entity.native_value == "blocked"


@pytest.mark.parametrize("invalid", ["unavailable", "unknown", "nan", "-1"])
async def test_source_exclusion_and_return(runtime_hass, runtime_entry, measurement_clock, invalid):
    transport = HydrusTransport(runtime_hass, runtime_entry, measurement_clock, True)
    manager = await start(runtime_hass, runtime_entry)
    entity = HydraulicMonitoringStatusSensor(manager)
    await transport.telegram(0.25)
    runtime_hass.states.async_set("sensor.flow", invalid, {"unit_of_measurement": "m³/h"})
    await runtime_hass.async_block_till_done()
    assert entity.native_value == "blocked"
    assert not entity.extra_state_attributes["source_available"]
    assert entity.available
    await transport.telegram(0.25)
    assert entity.native_value == "active"
    assert manager._flow_evidence.credited_seconds == 0


async def test_timeout_is_visible_without_alarm_release(
    runtime_hass, runtime_entry, measurement_clock
):
    transport, manager = await running(runtime_hass, runtime_entry, measurement_clock)
    entity = HydraulicMonitoringStatusSensor(manager)
    low = manager.engine.runtimes[DetectorKind.LOW_FLOW]
    event_id = low.event_id
    alarm = manager.alarm_active
    shutoff = manager.shutoff_request
    await manager.async_update_options({
        **runtime_entry.options, "source_max_age_seconds": 120, "source_gap_policy_explicit": True
    })
    measurement_clock.advance(121)
    await manager._async_tick(measurement_clock.utcnow())
    assert entity.native_value == "blocked"
    assert entity.extra_state_attributes["reason"] == "source_timeout"
    assert low.event_id == event_id
    assert manager.alarm_active == alarm
    assert manager.shutoff_request == shutoff
    # Reading visibility must not acknowledge, reset, or otherwise mutate safety state.
    before = manager.engine.to_dict()
    _ = entity.native_value, entity.extra_state_attributes
    assert manager.engine.to_dict() == before
    await transport.telegram(0.25)
    assert entity.native_value == "active"
    assert low.event_id == event_id


async def test_source_switch_waits_and_releases_only_after_new_measurement(
    runtime_hass, runtime_entry, measurement_clock
):
    transport = HydrusTransport(runtime_hass, runtime_entry, measurement_clock, True)
    manager = await start(runtime_hass, runtime_entry)
    entity = HydraulicMonitoringStatusSensor(manager)
    await transport.telegram(0.25)
    await manager.async_update_sources({**runtime_entry.data, "flow_entity": "sensor.new_meter"})
    assert entity.native_value == "waiting_for_measurement"
    assert entity.extra_state_attributes["source_entity_id"] == "sensor.new_meter"
    assert entity.extra_state_attributes["last_valid_measurement"] is None
    await manager.async_update_sources({**runtime_entry.data, "flow_entity": "sensor.flow"})
    assert entity.native_value == "waiting_for_measurement"
    await transport.telegram(0.25)
    assert entity.native_value == "active"


async def test_restart_keeps_alarm_but_cached_original_is_blocked(
    runtime_hass, runtime_entry, measurement_clock
):
    transport, manager = await running(runtime_hass, runtime_entry, measurement_clock)
    event_id = manager.engine.runtimes[DetectorKind.LOW_FLOW].event_id
    await manager.async_unload()
    measurement_clock.advance(60)
    restored = await start(runtime_hass, runtime_entry)
    entity = HydraulicMonitoringStatusSensor(restored)
    assert entity.native_value == "blocked"
    assert entity.extra_state_attributes["reason"] == "pre_startup_measurement"
    assert restored.engine.runtimes[DetectorKind.LOW_FLOW].event_id == event_id
    assert restored.alarm_active
    await transport.telegram(0.25)
    assert entity.native_value == "active"
    assert restored.engine.runtimes[DetectorKind.LOW_FLOW].event_id == event_id


async def test_missing_optional_diagnostics(runtime_hass, runtime_entry, monkeypatch):
    manager = WaterLeakManager(runtime_hass, runtime_entry)
    monkeypatch.setattr(manager, "source_diagnostics", lambda: {})
    attributes = HydraulicMonitoringStatusSensor(manager).extra_state_attributes
    assert attributes["mqtt_provenance_status"] is None
    assert attributes["last_valid_measurement"] is None
    assert attributes["observation_age_seconds"] is None


@pytest.mark.parametrize("language,name,states", [
    ("de", "Hydraulische Überwachung", ["Aktiv", "Warte auf Messung", "Gesperrt"]),
    ("en", "Hydraulic monitoring", ["Active", "Waiting for measurement", "Blocked"]),
])
def test_translated_states(language, name, states):
    data = json.loads(Path(f"custom_components/water_leak_detection/translations/{language}.json")
                      .read_text())["entity"]["sensor"]["hydraulic_monitoring_status"]
    assert data["name"] == name
    keys = ["active", "waiting_for_measurement", "blocked"]
    assert [data["state"][key] for key in keys] == states


async def test_ha_registration_and_listener_updates(runtime_hass, runtime_entry, measurement_clock):
    from homeassistant import loader

    import custom_components

    loader.async_setup(runtime_hass)
    runtime_hass.data[loader.DATA_INTEGRATIONS][DOMAIN] = loader.Integration.resolve_from_root(
        runtime_hass, custom_components, DOMAIN
    )
    assert await runtime_hass.config_entries.async_setup(runtime_entry.entry_id)
    await runtime_hass.async_block_till_done()
    registry = er.async_get(runtime_hass)
    record = next(
        item for item in er.async_entries_for_config_entry(registry, runtime_entry.entry_id)
        if item.unique_id == f"{runtime_entry.entry_id}_hydraulic_monitoring_status"
    )
    assert record.device_id
    device = dr.async_get(runtime_hass).async_get(record.device_id)
    assert (DOMAIN, runtime_entry.entry_id) in device.identifiers
    assert runtime_hass.states.get(record.entity_id).state == "waiting_for_measurement"
    runtime_hass.states.async_set("sensor.flow", "250", {"unit_of_measurement": "L/h"})
    await runtime_hass.async_block_till_done()
    assert runtime_hass.states.get(record.entity_id).state == "active"
    runtime_hass.states.async_set("sensor.flow", "unavailable")
    await runtime_hass.async_block_till_done()
    state = runtime_hass.states.get(record.entity_id)
    assert state.state == "blocked"
    assert state.attributes["reason"] == "source_unavailable"
    await runtime_hass.config_entries.async_unload(runtime_entry.entry_id)


@pytest.mark.parametrize("failure,expected", [
    ("missing_timestamp", "original_measurement_missing"),
    ("retained", "retained_or_unbound_message"),
    ("replay", "replayed_or_out_of_order_measurement"),
])
async def test_mqtt_rejections_publish_precise_block_reason(
    runtime_hass, runtime_entry, measurement_clock, failure, expected
):
    from homeassistant.components.mqtt.models import ReceiveMessage
    from test_hydrus_mqtt_diagnostics import TOPIC

    transport = HydrusTransport(runtime_hass, runtime_entry, measurement_clock, True)
    manager = await start(runtime_hass, runtime_entry)
    entity = HydraulicMonitoringStatusSensor(manager)
    await transport.telegram(0.25)
    old_timestamp = manager._mqtt_provenance.timestamp
    measurement_clock.advance(60)
    payload = {"flow_m3h": 0.25, "total_m3": transport.total_m3}
    if failure != "missing_timestamp":
        timestamp = old_timestamp if failure == "replay" else measurement_clock.utcnow()
        payload["timestamp"] = timestamp.isoformat()
    message = ReceiveMessage(TOPIC, json.dumps(payload), 0, failure == "retained", TOPIC, 0)
    transport.sensor._message_callback(
        transport.sensor._state_message_received,
        {"_attr_native_value", "_attr_last_reset", "_expired"}, message,
    )
    transport.data.state_write_requests.process_write_state_requests(message)
    await runtime_hass.async_block_till_done()
    assert entity.native_value == "blocked"
    assert entity.extra_state_attributes["reason"] == expected
    assert entity.extra_state_attributes["mqtt_provenance_status"] == expected
    # Removing the state after a rejection must not erase the known exclusion.
    runtime_hass.states.async_remove("sensor.flow")
    await runtime_hass.async_block_till_done()
    assert entity.native_value == "blocked"
