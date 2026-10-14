"""Startup boundaries through HA MQTT callbacks, disk restore and source changes."""

import json
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from test_f04_mqtt_latency import deliver
from test_hydrus_mqtt_diagnostics import HydrusTransport, running

from custom_components.water_leak_detection.const import DOMAIN, DetectorKind, DetectorPhase
from custom_components.water_leak_detection.manager import WaterLeakManager
from custom_components.water_leak_detection.mqtt_provenance import MqttProvenance


async def start(hass, entry):
    manager = WaterLeakManager(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    await manager.async_setup()
    return manager


@pytest.mark.parametrize("latency", [0, 0.1])
@pytest.mark.parametrize("load_delay", [0, 30])
async def test_first_fresh_original_after_actual_setup_start(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch, latency, load_delay
):
    transport = HydrusTransport(runtime_hass, runtime_entry, measurement_clock, True)
    manager = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data.setdefault(DOMAIN, {})[runtime_entry.entry_id] = manager
    boundary = manager.timer_now
    original_load = manager._store.async_load

    async def delayed_load():
        measurement_clock.advance(load_delay)
        return await original_load()

    monkeypatch.setattr(manager._store, "async_load", delayed_load)
    await manager.async_setup()
    # Delayed loading must not move the captured admission boundary.
    await deliver(transport, measurement_clock, 0.25, 60 - load_delay, latency, 0)
    assert manager.source_available
    assert manager._mqtt_provenance.started_at == boundary
    assert manager._mqtt_provenance.reason == "verified_original_measurement"
    assert manager._flow_evidence.credited_seconds == 0
    await deliver(transport, measurement_clock, 0.25, 60, latency, latency)
    assert manager._flow_evidence.credited_seconds == 60


@pytest.mark.parametrize("latency", [0, 0.1])
async def test_original_arriving_while_store_loads_is_after_setup_boundary(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch, latency
):
    transport = HydrusTransport(runtime_hass, runtime_entry, measurement_clock, True)
    manager = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data.setdefault(DOMAIN, {})[runtime_entry.entry_id] = manager
    boundary = manager.timer_now
    original_load = manager._store.async_load

    async def load_with_new_telegram():
        await deliver(transport, measurement_clock, 0.25, 15, latency, 0)
        measurement_clock.advance(15)
        return await original_load()

    monkeypatch.setattr(manager._store, "async_load", load_with_new_telegram)
    await manager.async_setup()
    assert manager.source_available
    assert manager._mqtt_provenance.started_at == boundary
    assert manager._flow_evidence.credited_seconds == 0


@pytest.mark.parametrize("latency", [0, 0.1])
async def test_original_before_setup_remains_excluded(
    runtime_hass, runtime_entry, measurement_clock, latency
):
    transport = HydrusTransport(runtime_hass, runtime_entry, measurement_clock, True)
    manager = await start(runtime_hass, runtime_entry)
    await deliver(transport, measurement_clock, 0, -1, 61 + latency, 0)
    assert not manager.source_available
    assert manager._mqtt_provenance.reason == "pre_startup_measurement"
    assert manager._flow_evidence.credited_seconds == 0


async def test_restart_restores_marker_but_rebuilds_evidence_and_preserves_alarm(
    runtime_hass, runtime_entry, measurement_clock
):
    transport, manager = await running(runtime_hass, runtime_entry, measurement_clock)
    low = manager.engine.runtimes[DetectorKind.LOW_FLOW]
    event_id = low.event_id
    marker = manager._mqtt_provenance.timestamp
    generation = manager.measurement_source.generation
    await manager.async_unload()
    measurement_clock.advance(60)
    boundary = measurement_clock.utcnow()
    restored = await start(runtime_hass, runtime_entry)
    assert restored.measurement_source.generation == generation
    assert restored._mqtt_provenance.timestamp == marker
    assert restored._mqtt_provenance.started_at == boundary
    assert restored.engine.runtimes[DetectorKind.LOW_FLOW].event_id == event_id
    await deliver(transport, measurement_clock, 0, 60, 0.1, 0)
    assert restored.source_available
    assert restored._flow_evidence.credited_seconds == 0
    assert restored.engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.ACTIVE
    assert restored.engine.runtimes[DetectorKind.LOW_FLOW].event_id == event_id
    await deliver(transport, measurement_clock, 0, 179, 0.1, 0.1)
    assert restored.alarm_active
    await deliver(transport, measurement_clock, 0, 1, 0.1, 0.1)
    assert not restored.alarm_active


@pytest.mark.parametrize("change", ["registry", "configured_source"])
async def test_new_generation_binds_before_first_mqtt_report(
    runtime_hass, runtime_entry, measurement_clock, change
):
    transport = HydrusTransport(runtime_hass, runtime_entry, measurement_clock, True)
    manager = await start(runtime_hass, runtime_entry)
    old_generation = manager.measurement_source.generation
    measurement_clock.advance(10)
    boundary = manager.timer_now
    if change == "registry":
        registry = er.async_get(runtime_hass)
        registry.async_update_entity("sensor.flow", new_unique_id="replacement_hydrus")
        await runtime_hass.async_block_till_done()
    else:
        await manager.async_update_sources({**runtime_entry.data, "flow_entity": "sensor.other"})
        await manager.async_update_sources({**runtime_entry.data, "flow_entity": "sensor.flow"})
    assert manager.measurement_source.generation != old_generation
    assert manager._mqtt_provenance.started_at == boundary
    await deliver(transport, measurement_clock, 0.25, 60, 0.1, 0)
    assert manager.source_available
    assert manager._mqtt_provenance.started_at == boundary
    assert manager._flow_evidence.credited_seconds == 0


async def test_outage_boundary_survives_later_original_reception(
    runtime_hass, runtime_entry, measurement_clock
):
    transport = HydrusTransport(runtime_hass, runtime_entry, measurement_clock, True)
    manager = await start(runtime_hass, runtime_entry)
    await deliver(transport, measurement_clock, 0.25, 60, 0.1, 0)
    measurement_clock.advance(10)
    boundary = manager.timer_now
    runtime_hass.states.async_set("sensor.flow", "unavailable")
    await runtime_hass.async_block_till_done()
    await deliver(transport, measurement_clock, 0, -1, 2, 0)
    assert not manager.source_available
    assert manager._mqtt_provenance.reason == "pre_startup_measurement"
    assert manager._mqtt_provenance.started_at >= boundary
    boundary = manager._mqtt_provenance.started_at
    await deliver(transport, measurement_clock, 0, 60, 0.1, 2)
    assert manager.source_available
    assert manager._flow_evidence.credited_seconds == 0
    assert manager._mqtt_provenance.started_at == boundary


async def test_first_marker_write_failure_never_admits_source(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch
):
    transport = HydrusTransport(runtime_hass, runtime_entry, measurement_clock, True)
    manager = await start(runtime_hass, runtime_entry)

    async def fail(_data):
        raise OSError("marker write failed")

    with monkeypatch.context() as patch:
        patch.setattr(manager._store, "async_save", fail)
        await deliver(transport, measurement_clock, 0.25, 60, 0.1, 0)
        assert not manager.source_available
        assert manager._mqtt_provenance.reason == "provenance_persistence_failed"
        assert manager._flow_evidence.credited_seconds == 0
        stored = json.loads(Path(manager._store.path).read_text())["data"]
        assert stored["mqtt_measurement_provenance"]["measurement_timestamp"] is None


def proof_fixture():
    now = datetime(2026, 10, 14, tzinfo=UTC)
    messages = deque()
    entity = SimpleNamespace(state="0.25", _config={"state_topic": "hydrus"})
    hass = SimpleNamespace(data={
        "sensor": SimpleNamespace(get_entity=lambda _: entity),
        "mqtt": SimpleNamespace(debug_info_entities={
            "sensor.flow": {"subscriptions": {"hydrus": {"messages": messages}}}
        }),
    })
    return now, messages, hass, State("sensor.flow", "0.25")


@pytest.mark.parametrize("case", ["retained", "replay", "out_of_order", "future", "stale"])
def test_start_binding_keeps_existing_rejection_rules(case):
    now, messages, hass, state = proof_fixture()
    proof = MqttProvenance("generation")
    proof.bind_startup(now - timedelta(seconds=600))
    stamp = now
    if case == "future":
        stamp += timedelta(seconds=3)
    if case == "stale":
        stamp -= timedelta(seconds=301)
    if case == "replay":
        proof.commit((stamp, None))
    if case == "out_of_order":
        messages.append(ReceiveMessage("hydrus", json.dumps({
            "timestamp": (stamp + timedelta(seconds=1)).isoformat()
        }), 0, False, "hydrus", 0))
    messages.append(ReceiveMessage("hydrus", json.dumps({"timestamp": stamp.isoformat()}),
                                   0, case == "retained", "hydrus", 0))
    assert proof.validate(hass, "sensor.flow", state, now) is None
    assert proof.reason == {
        "retained": "retained_or_unbound_message",
        "replay": "replayed_or_out_of_order_measurement",
        "out_of_order": "out_of_order_original_message",
        "future": "future_measurement",
        "stale": "stale_measurement",
    }[case]


def test_persisted_future_boundary_is_not_weakened_or_rebound():
    now, _, hass, state = proof_fixture()
    boundary = now + timedelta(seconds=60)
    proof = MqttProvenance("generation")
    proof.restore({"source_generation": "generation", "admission_since": boundary.isoformat()})
    proof.bind_startup(now)
    assert proof.started_at == boundary
    proof.bind_startup(now + timedelta(seconds=120))
    assert proof.started_at == boundary
    # An uninitialized standalone adapter fails closed, without inventing a start time.
    unbound = MqttProvenance("generation")
    assert unbound.validate(hass, "sensor.flow", state, now) is None
    assert unbound.started_at is None
    assert unbound.reason == "startup_not_initialized"
