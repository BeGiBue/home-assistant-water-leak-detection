"""Recovery/identity boundaries against production HA Store and MQTT components."""

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.util.file import WriteError
from test_external_leaks import controller
from test_f04_security_review_controls import action, setup
from test_hydrus_mqtt_diagnostics import TOPIC, running

from custom_components.water_leak_detection.const import DOMAIN
from custom_components.water_leak_detection.external_leaks import ExternalLeakController
from custom_components.water_leak_detection.manager import WaterLeakManager
from custom_components.water_leak_detection.sensor import WaterLeakStatusSensor


async def restart(hass, entry, manager):
    if not manager._closed:
        await manager.async_unload()
    restored = WaterLeakManager(hass, entry)
    restored.notifications._async_common_translations = (
        manager.notifications._async_common_translations
    )
    hass.data[DOMAIN][entry.entry_id] = restored
    await restored.async_setup()
    return restored


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("operation", ["on", "off", "options", "registry"])
async def test_corrupt_body_barrier_covers_writers_and_restart(
    runtime_hass, runtime_entry, measurement_clock, version, operation
):
    manager = await setup(runtime_hass, runtime_entry, measurement_clock)
    await manager.async_unload()
    path = Path(manager._store.path)
    raw = json.loads(path.read_text())
    raw["version"] = version
    raw["data"] = [raw["data"]]  # Keep recoverable original safety data, don't infer its shape.
    path.write_text(json.dumps(raw))
    original = path.read_bytes()
    runtime_hass.states.async_set("binary_sensor.a", "unavailable")
    manager = await restart(runtime_hass, runtime_entry, manager)
    if operation == "on":
        runtime_hass.states.async_set("binary_sensor.b", "on")
    elif operation == "off":
        runtime_hass.states.async_set("binary_sensor.a", "off")
    elif operation == "options":
        with pytest.raises(RuntimeError):
            await manager.async_update_options({**runtime_entry.options, "external_sensors": []})
    else:
        er.async_get(runtime_hass).async_update_entity(
            "binary_sensor.a", new_entity_id="binary_sensor.renamed_a"
        )
    await runtime_hass.async_block_till_done()
    assert manager._storage_load_failed and not manager._migration_ready
    assert (
        ir.async_get(runtime_hass).async_get_issue(
            DOMAIN, f"{runtime_entry.entry_id}_runtime_safety_recovery"
        )
        is not None
    )
    assert manager.alarm_active and manager.shutoff_request
    assert path.read_bytes() == original
    manager = await restart(runtime_hass, runtime_entry, manager)
    assert manager._storage_load_failed and manager.alarm_active and manager.shutoff_request
    assert path.read_bytes() == original


@pytest.mark.parametrize("version", [1, 2])
async def test_verified_backup_restore_reopens_writes_but_retains_active(
    runtime_hass, runtime_entry, measurement_clock, version
):
    manager = await setup(runtime_hass, runtime_entry, measurement_clock)
    await manager.async_unload()
    path = Path(manager._store.path)
    good = path.read_bytes()
    raw = json.loads(good)
    raw["version"] = version
    raw["data"] = "damaged"
    path.write_text(json.dumps(raw))
    runtime_hass.states.async_set("binary_sensor.a", "unavailable")
    manager = await restart(runtime_hass, runtime_entry, manager)
    assert manager._storage_load_failed and manager.shutoff_request
    await manager.async_unload()
    path.write_bytes(good)  # Offline restoration of a verified full backup, not inferred learning.
    manager = await restart(runtime_hass, runtime_entry, manager)
    assert not manager._storage_load_failed and manager._migration_ready
    assert (
        ir.async_get(runtime_hass).async_get_issue(
            DOMAIN, f"{runtime_entry.entry_id}_runtime_safety_recovery"
        )
        is None
    )
    assert manager.external.sources["a"].phase.value == "ACTIVE"
    assert manager.alarm_active and manager.shutoff_request


@pytest.mark.parametrize("version", [1, 2])
async def test_null_body_is_not_a_missing_store(
    runtime_hass, runtime_entry, measurement_clock, version
):
    manager = await setup(runtime_hass, runtime_entry, measurement_clock)
    await manager.async_unload()
    path = Path(manager._store.path)
    raw = json.loads(path.read_text())
    raw.update(version=version, data=None)
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    runtime_hass.states.async_set("binary_sensor.a", "unavailable")
    manager = await restart(runtime_hass, runtime_entry, manager)
    assert manager._storage_load_failed and not manager._migration_ready
    assert manager.alarm_active and manager.shutoff_request
    assert path.read_bytes() == before


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize(
    "field", ["engine", "runtimes", "external_sources", "external_alarm_ledger"]
)
async def test_damaged_safety_container_is_quarantined_without_overwrite(
    runtime_hass, runtime_entry, measurement_clock, version, field
):
    manager = await setup(runtime_hass, runtime_entry, measurement_clock)
    await manager.async_unload()
    path = Path(manager._store.path)
    raw = json.loads(path.read_text())
    raw["version"] = version
    if field == "runtimes":
        raw["data"]["engine"]["runtimes"] = [raw["data"]["engine"]["runtimes"]]
    else:
        raw["data"][field] = (
            {"recoverable": raw["data"][field]} if field != "engine" else [raw["data"][field]]
        )
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    runtime_hass.states.async_set("binary_sensor.a", "unavailable")
    manager = await restart(runtime_hass, runtime_entry, manager)
    assert manager._storage_load_failed and not manager._migration_ready
    assert manager.alarm_active and manager.shutoff_request
    assert path.read_bytes() == before


@pytest.mark.parametrize("age,max_age", [(299, 120), (300, 120), (299, 180), (300, 180)])
async def test_direct_gap_return_cannot_use_pre_boundary_zero(
    runtime_hass, runtime_entry, measurement_clock, age, max_age
):
    runtime_hass.config_entries.async_update_entry(
        runtime_entry,
        options={
            "source_max_age_seconds": max_age,
            "source_gap_policy_explicit": True,
            "shutoff_low": True,
        },
    )
    transport, manager = await running(runtime_hass, runtime_entry, measurement_clock)
    last = manager.timer_now
    measurement_clock.advance(400)  # No tick: the return report itself reveals the gap.
    for i in range(4):
        if i:
            measurement_clock.advance(60)
        msg = ReceiveMessage(
            TOPIC,
            json.dumps(
                {
                    "flow_m3h": 0,
                    "total_m3": transport.total_m3,
                    "timestamp": (last + timedelta(seconds=400 - age + 60 * i)).isoformat(),
                }
            ),
            1,
            False,
            TOPIC,
            measurement_clock.monotonic(),
        )
        transport.sensor._message_callback(
            transport.sensor._state_message_received,
            {"_attr_native_value", "_attr_last_reset", "_expired"},
            msg,
        )
        transport.data.state_write_requests.process_write_state_requests(msg)
        await runtime_hass.async_block_till_done()
    assert manager.alarm_active and manager.shutoff_request
    assert manager.source_diagnostics()["low_reset_confirmed_seconds"] == 0


async def test_timeout_boundary_durable_before_restart_with_utc_rollback(
    runtime_hass, runtime_entry, measurement_clock
):
    runtime_hass.config_entries.async_update_entry(
        runtime_entry,
        options={
            "source_max_age_seconds": 120,
            "source_gap_policy_explicit": True,
            "shutoff_low": True,
        },
    )
    transport, manager = await running(runtime_hass, runtime_entry, measurement_clock)
    measurement_clock.advance(400)
    boundary = manager.timer_now
    await manager._async_tick(measurement_clock.utcnow())
    raw = json.loads(Path(manager._store.path).read_text())["data"]
    assert raw["mqtt_measurement_provenance"]["admission_since"] == boundary.isoformat()
    measurement_clock.wall_shift = -3600
    manager = await restart(runtime_hass, runtime_entry, manager)
    assert manager._mqtt_provenance.started_at >= boundary
    assert manager.alarm_active and manager.shutoff_request
    assert manager.source_diagnostics()["low_reset_confirmed_seconds"] == 0
    # The unchanged relay contract remains physical UTC, not HA's shifted UTC.
    await transport.telegram(0, 60)
    assert manager.alarm_active and manager.shutoff_request


async def test_boundary_write_failure_cannot_admit_quiet_then_clean_retry(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch
):
    runtime_hass.config_entries.async_update_entry(
        runtime_entry,
        options={
            "source_max_age_seconds": 120,
            "source_gap_policy_explicit": True,
            "shutoff_low": True,
        },
    )
    transport, manager = await running(runtime_hass, runtime_entry, measurement_clock)
    path = Path(manager._store.path)
    before = path.read_bytes()

    def fail(*_):
        raise WriteError("controlled exclusion boundary write failure")

    with monkeypatch.context() as patch:
        patch.setattr(manager._store, "_write_prepared_data", fail)
        measurement_clock.advance(400)
        await manager._async_tick(measurement_clock.utcnow())
        for _ in range(4):
            await transport.telegram(0, 60)
        assert manager.alarm_active and manager.shutoff_request
        assert path.read_bytes() == before
        assert manager.source_diagnostics()["low_reset_confirmed_seconds"] == 0
    await transport.telegram(0, 60)
    assert manager.source_diagnostics()["low_reset_confirmed_seconds"] == 0
    for _ in range(3):
        await transport.telegram(0, 60)
    assert not manager.alarm_active and not manager.shutoff_request


@pytest.mark.parametrize("order", ["forward", "reverse"])
@pytest.mark.parametrize("ledger", [False, True])
async def test_conflicts_block_capabilities_and_survive_restart(
    runtime_hass, runtime_entry, measurement_clock, order, ledger
):
    manager = await setup(runtime_hass, runtime_entry, measurement_clock)
    runtime_hass.states.async_set("binary_sensor.b", "on")
    await runtime_hass.async_block_till_done()
    old_action = action(manager)
    common = manager.external.sources["a"].event_id
    assert await manager.async_acknowledge_event(common, "phone", "token")
    await manager.async_unload()
    path = Path(manager._store.path)
    raw = json.loads(path.read_text())
    records = raw["data"]["external_sources"]
    records[0]["contributes_to_shutoff"] = True
    records[1]["contributes_to_shutoff"] = False
    records[1]["event_id"] = common
    if order == "reverse":
        records.reverse()
    if ledger:
        raw["data"]["external_alarm_ledger"] = [records.pop()]
    path.write_text(json.dumps(raw))
    manager = await restart(runtime_hass, runtime_entry, manager)
    for _ in range(2):
        conflicted = [s for s in manager.external.all_sources() if s.event_id == common]
        assert len(conflicted) == 2
        assert all(s.identity_conflict and s.reset_nonce is None for s in conflicted)
        assert manager.alarm_active and manager.shutoff_request
        assert common not in manager.active_events()
        assert common not in manager.notifications.acknowledgements
        assert not await manager.async_acknowledge_event(common, "phone", "token")
        conflicted_a = next(s for s in conflicted if s.source_id == "a")
        assert not await manager.async_request_external_reset_action(
            "a", "phone", conflicted_a.identity.generation, common
        )
        assert not await manager.async_external_reset(old_action)
        assert WaterLeakStatusSensor(manager).native_value == "external_leak"
        assert any(s["identity_conflict"] for s in manager.external_diagnostics())
        manager = await restart(runtime_hass, runtime_entry, manager)


@pytest.mark.parametrize("order", ["forward", "reverse", "mixed"])
@pytest.mark.parametrize("ledger_only", [False, True])
def test_repeated_source_generation_keys_preserve_every_active_record(order, ledger_only):
    target = controller()
    target.observe("a", "on", datetime(2026, 10, 13, tzinfo=UTC))
    source = target.sources["a"].to_dict()
    records = [{**source, "contributes_to_shutoff": value} for value in [False, True, False]]
    if order == "reverse":
        records.reverse()
    elif order == "mixed":
        records = [records[1], records[2], records[0]]
    raw = {
        "external_sources": [] if ledger_only else records,
        "external_alarm_ledger": records if ledger_only else [],
    }
    for _ in range(3):
        restored = ExternalLeakController()
        restored.restore(deepcopy(raw), datetime(2026, 10, 13, tzinfo=UTC))
        assert len(restored.all_sources()) == 3
        assert restored.has_active_sources and restored.shutoff_request
        assert not restored.active_events()
        assert all(s.identity_conflict and s.reset_nonce is None for s in restored.all_sources())
        assert restored.event_for("a", "g1", source["event_id"]) is None
        raw = restored.to_dict()


def test_hydraulic_event_collision_quarantines_external_capability():
    target = controller()
    target.observe("a", "on", datetime(2026, 10, 13, tzinfo=UTC))
    event_id = target.sources["a"].event_id
    assert target.quarantine_conflicts([event_id]) == {event_id}
    assert target.has_active_sources and target.shutoff_request
    assert not target.active_events()


def test_ambiguous_capabilities_fail_closed_even_before_quarantine_scan():
    target = controller()
    now = datetime(2026, 10, 13, tzinfo=UTC)
    target.observe("a", "on", now)
    copied = deepcopy(target.sources["a"])
    copied.source_id = "b"
    target.sources["b"] = copied
    assert target.has_active_sources and target.shutoff_request
    assert not target.active_events()
    assert target.event_for("a", "g1", copied.event_id) is None


async def test_variable_store_latency_is_neither_evidence_nor_a_source_gap(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch
):
    transport, manager = await running(runtime_hass, runtime_entry, measurement_clock)
    original_save = manager._store.async_save
    calls = 0

    async def slow_save(data):
        nonlocal calls
        calls += 1
        # Model elapsed I/O while performing the actual HA atomic disk write.
        # No sensor report is generated by this elapsed time.
        measurement_clock.advance(0.005 if calls % 2 else 0.001)
        await original_save(data)

    monkeypatch.setattr(manager._store, "async_save", slow_save)
    await transport.telegram(0, 60)
    assert manager.source_diagnostics()["low_reset_confirmed_seconds"] == 0
    for _ in range(2):
        await transport.telegram(0, 60)
        assert manager.alarm_active
        assert not manager.engine.last_evidence_gap
    await transport.telegram(0, 60)
    assert not manager.alarm_active
