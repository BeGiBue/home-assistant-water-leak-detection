"""F04-FSR-H01: damaged persisted records of configured external sensors.

Before the fix only retained ledger records were validated by their safety
role. A damaged ``external_sources`` record of a configured sensor was parsed
leniently: an unknown phase without a valid Event-ID was dropped (the source
came back ARMED, the alarm and its shutoff contribution were lost while the
sensor was not reporting ON), and an ACTIVE record with damaged fields got an
invented Event-ID or identity that the reset/ACK paths then trusted. Now every
source record must be interpretable, otherwise the existing Store recovery
barrier applies. All tests use the real manager, HA Store files and restarts.
"""

import json
from pathlib import Path

import pytest
from homeassistant.helpers import issue_registry as ir
from test_external_leaks import NOW, controller
from test_f04_security_review_controls import action, setup
from test_f04_v2_safety_boundaries import restart

from custom_components.water_leak_detection.const import CONF_EXTERNAL_SENSORS, DOMAIN
from custom_components.water_leak_detection.external_leaks import (
    ExternalLeakController,
    ExternalPhase,
)
from custom_components.water_leak_detection.sensor import WaterLeakStatusSensor
from custom_components.water_leak_detection.storage import validate_snapshot_body

# One damaged field (or a combination) of the configured, ACTIVE source "a".
CHANGES = {
    "phase_none": {"phase": None},
    "phase_unknown": {"phase": "damaged"},
    "phase_number": {"phase": 3},
    "phase_list": {"phase": []},
    "phase_and_event_damaged": {"phase": "damaged", "event_id": None},
    "phase_none_event_none": {"phase": None, "event_id": None},
    "event_id_none": {"event_id": None},
    "event_id_invalid": {"event_id": "broken id"},
    "event_id_bool": {"event_id": False},
    "event_id_dict": {"event_id": {}},
    "source_id_none": {"source_id": None},
    "generation_bool": {"generation": False},
    "learning_epoch_invalid": {"learning_epoch": "bad epoch"},
    "entity_id_none": {"entity_id": None},
    "entity_id_wrong_domain": {"entity_id": "sensor.a"},
    "started_at_none": {"started_at": None},
    "started_at_naive": {"started_at": "2026-10-13T12:00:00"},
    "started_at_garbage": {"started_at": "yesterday"},
    "started_at_number": {"started_at": 12.5},
    "contributes_string": {"contributes_to_shutoff": "false"},
    "contributes_none": {"contributes_to_shutoff": None},
    "identity_conflict_string": {"identity_conflict": "true"},
    "tombstone_list": {"tombstone": []},
    "name_number": {"name": 5},
    "registry_id_number": {"registry_id": 5},
    "reset_nonce_list": {"reset_nonce": []},
}
MISSING = ["phase", "event_id", "source_id", "entity_id", "contributes_to_shutoff"]


async def active_source(hass, entry, clock):
    """Source "a" ACTIVE (contributes to shutoff), saved by the real writer."""
    manager = await setup(hass, entry, clock)
    source = manager.external.sources["a"]
    assert source.phase is ExternalPhase.ACTIVE and manager.shutoff_request
    old_action = action(manager)
    await manager.async_unload()
    path = Path(manager._store.path)
    good = path.read_bytes()
    raw = json.loads(good)
    record = next(r for r in raw["data"]["external_sources"] if r["source_id"] == "a")
    assert record["phase"] == "ACTIVE" and record["contributes_to_shutoff"] is True
    return manager, path, good, raw, record, old_action


def recovery_issue(hass, entry):
    return ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_runtime_safety_recovery")


async def assert_held_and_blocked(hass, entry, manager, path, before, old_action):
    """Alarm and shutoff held, nothing written, every capability blocked, reported."""
    assert manager._storage_load_failed
    assert manager.alarm_active and manager.shutoff_request
    assert path.read_bytes() == before
    attributes = WaterLeakStatusSensor(manager).extra_state_attributes
    assert attributes["storage_recovery_required"] is True
    assert attributes["aggregate_alarm_active"] and attributes["aggregate_shutoff_request"]
    assert recovery_issue(hass, entry) is not None
    event_id = old_action["event_id"]
    assert event_id not in manager.active_events()
    assert not await manager.async_acknowledge_event(event_id, "phone", "token")
    assert not await manager.async_external_reset(old_action)
    assert not await manager.async_request_external_reset_action("a", "phone")
    assert manager.alarm_active and manager.shutoff_request
    assert path.read_bytes() == before


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("change", [*CHANGES, *(f"missing_{key}" for key in MISSING)])
async def test_damaged_configured_source_record_holds_alarm_and_preserves_bytes(
    runtime_hass, runtime_entry, measurement_clock, version, change
):
    manager, path, _, raw, record, old_action = await active_source(
        runtime_hass, runtime_entry, measurement_clock
    )
    if change.startswith("missing_"):
        record.pop(change.removeprefix("missing_"))
    else:
        record.update(CHANGES[change])
    raw["version"] = version
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    # The sensor is not reporting ON at restart (e.g. its radio is still starting).
    runtime_hass.states.async_set("binary_sensor.a", "unavailable")
    manager = await restart(runtime_hass, runtime_entry, manager)
    await assert_held_and_blocked(runtime_hass, runtime_entry, manager, path, before, old_action)


async def test_external_on_off_and_reload_during_recovery_never_release_or_write(
    runtime_hass, runtime_entry, measurement_clock
):
    manager, path, good, raw, record, old_action = await active_source(
        runtime_hass, runtime_entry, measurement_clock
    )
    record.update(phase="damaged", event_id=None)
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    runtime_hass.states.async_set("binary_sensor.a", "unavailable")
    manager = await restart(runtime_hass, runtime_entry, manager)
    for state in ("off", "on", "off"):
        for entity in ("binary_sensor.a", "binary_sensor.b"):
            runtime_hass.states.async_set(entity, state)
        await runtime_hass.async_block_till_done()
        assert manager.alarm_active and manager.shutoff_request
        assert path.read_bytes() == before
    # Saving changed options is refused instead of writing a "clean" snapshot.
    with pytest.raises(RuntimeError):
        await manager.async_update_options(dict(runtime_entry.options))
    # Reload (unload + setup) keeps the barrier and the original bytes.
    manager = await restart(runtime_hass, runtime_entry, manager)
    await assert_held_and_blocked(runtime_hass, runtime_entry, manager, path, before, old_action)
    await manager.async_unload()
    assert path.read_bytes() == before
    # Restoring the verified backup with HA stopped brings back the exact alarm.
    path.write_bytes(good)
    runtime_hass.states.async_set("binary_sensor.a", "unavailable")
    manager = await restart(runtime_hass, runtime_entry, manager)
    assert not manager._storage_load_failed
    assert old_action["event_id"] in manager.active_events() and manager.shutoff_request
    assert recovery_issue(runtime_hass, runtime_entry) is None


@pytest.mark.parametrize(
    "change",
    [{"started_at": "garbage"}, {"started_at": 7}, {"phase": None}, {"contributes_to_shutoff": 1}],
)
async def test_damaged_waiting_record_holds_alarm(
    runtime_hass, runtime_entry, measurement_clock, change
):
    """A WAITING record (after an authorized reset) is checked as strictly."""
    manager = await setup(runtime_hass, runtime_entry, measurement_clock)
    assert await manager.async_external_reset(action(manager))
    assert manager.external.sources["a"].phase is ExternalPhase.RESET_WAITING_FOR_OFF
    await manager.async_unload()
    path = Path(manager._store.path)
    raw = json.loads(path.read_text())
    record = next(r for r in raw["data"]["external_sources"] if r["source_id"] == "a")
    assert record["phase"] == "RESET_WAITING_FOR_OFF" and record["started_at"]
    record.update(change)
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    manager = await restart(runtime_hass, runtime_entry, manager)
    assert manager._storage_load_failed
    assert manager.alarm_active and manager.shutoff_request
    assert path.read_bytes() == before


@pytest.mark.parametrize("damaged", [False, True])
async def test_record_of_a_removed_source(runtime_hass, runtime_entry, measurement_clock, damaged):
    """V2-H03: a removed ACTIVE source stays an alarm (tombstone); damage means recovery."""
    manager, path, _, raw, record, old_action = await active_source(
        runtime_hass, runtime_entry, measurement_clock
    )
    if damaged:
        record.update(phase=None)
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    runtime_hass.config_entries.async_update_entry(
        runtime_entry,
        options={
            **runtime_entry.options,
            CONF_EXTERNAL_SENSORS: [
                s for s in runtime_entry.options[CONF_EXTERNAL_SENSORS] if s["id"] != "a"
            ],
        },
    )
    manager = await restart(runtime_hass, runtime_entry, manager)
    if damaged:
        await assert_held_and_blocked(
            runtime_hass, runtime_entry, manager, path, before, old_action
        )
        return
    assert not manager._storage_load_failed
    assert "a" not in manager.external.sources
    retained = [s for s in manager.external.tombstones.values() if s.source_id == "a"]
    assert len(retained) == 1 and retained[0].event_id == old_action["event_id"]
    assert manager.alarm_active and manager.shutoff_request


@pytest.mark.parametrize("container", [None, {}, "damaged", 5, [None], ["record"], [[]]])
@pytest.mark.parametrize("field", ["external_sources", "external_alarm_ledger"])
async def test_damaged_list_containers_hold_alarm(
    runtime_hass, runtime_entry, measurement_clock, container, field
):
    manager, path, _, raw, _, old_action = await active_source(
        runtime_hass, runtime_entry, measurement_clock
    )
    raw["data"][field] = container
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    runtime_hass.states.async_set("binary_sensor.a", "unavailable")
    manager = await restart(runtime_hass, runtime_entry, manager)
    await assert_held_and_blocked(runtime_hass, runtime_entry, manager, path, before, old_action)


@pytest.mark.parametrize("field", ["external_sources", "external_alarm_ledger"])
async def test_missing_list_in_current_schema_holds_alarm(
    runtime_hass, runtime_entry, measurement_clock, field
):
    manager, path, _, raw, _, old_action = await active_source(
        runtime_hass, runtime_entry, measurement_clock
    )
    assert raw["data"]["learning_schema_version"] == 2
    raw["data"].pop(field)
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    runtime_hass.states.async_set("binary_sensor.a", "unavailable")
    manager = await restart(runtime_hass, runtime_entry, manager)
    await assert_held_and_blocked(runtime_hass, runtime_entry, manager, path, before, old_action)


@pytest.mark.parametrize("damage", ["nan", "truncated"])
async def test_invalid_json_is_renamed_by_ha_and_the_next_start_still_holds_the_alarm(
    runtime_hass, runtime_entry, measurement_clock, damage
):
    """HA moves an unreadable Store file to "<file>.corrupt.<time>" and loads nothing.

    Without the corrupt-copy check the second start looked like a new installation.
    """
    manager, path, good, raw, record, old_action = await active_source(
        runtime_hass, runtime_entry, measurement_clock
    )
    if damage == "nan":
        record["started_at"] = "__NAN__"
        text = json.dumps(raw).replace('"__NAN__"', "NaN")
    else:
        text = good.decode()[: len(good) // 2]
    path.write_text(text)
    before = path.read_bytes()
    runtime_hass.states.async_set("binary_sensor.a", "unavailable")
    for _ in range(2):
        manager = await restart(runtime_hass, runtime_entry, manager)
        assert manager._storage_load_failed
        assert manager.alarm_active and manager.shutoff_request
        assert recovery_issue(runtime_hass, runtime_entry) is not None
        assert not path.exists()  # renamed by HA, never replaced by a fresh snapshot
        copies = sorted(path.parent.glob(f"{path.name}.corrupt.*"))
        assert len(copies) == 1 and copies[0].read_bytes() == before
        assert not await manager.async_external_reset(old_action)
    await manager.async_unload()
    assert not path.exists()
    # Restoring the verified backup with HA stopped ends the recovery.
    path.write_bytes(good)
    manager = await restart(runtime_hass, runtime_entry, manager)
    assert not manager._storage_load_failed
    assert old_action["event_id"] in manager.active_events() and manager.shutoff_request


@pytest.mark.parametrize("waiting", [False, True])
async def test_undamaged_records_restore_exactly_as_before(
    runtime_hass, runtime_entry, measurement_clock, waiting
):
    manager, path, good, raw, record, old_action = await active_source(
        runtime_hass, runtime_entry, measurement_clock
    )
    runtime_hass.states.async_set("binary_sensor.a", "unavailable")
    manager = await restart(runtime_hass, runtime_entry, manager)
    assert not manager._storage_load_failed
    assert recovery_issue(runtime_hass, runtime_entry) is None
    assert old_action["event_id"] in manager.active_events() and manager.shutoff_request
    if waiting:
        # A normal authorized reset still works and survives a restart as WAITING.
        assert await manager.async_external_reset(action(manager))
        manager = await restart(runtime_hass, runtime_entry, manager)
        assert not manager._storage_load_failed
        assert manager.external.sources["a"].phase is ExternalPhase.RESET_WAITING_FOR_OFF
        assert not manager.shutoff_request


def test_validator_rejects_damaged_source_record_before_live_state_changes():
    target = controller()
    target.observe("a", "on", NOW)
    before = target.to_dict()
    raw = target.to_dict()
    raw["external_sources"][0]["phase"] = "damaged"
    raw["external_sources"][0]["event_id"] = None
    with pytest.raises(ValueError, match="F04-FSR-H01"):
        validate_snapshot_body(raw)
    with pytest.raises(ValueError, match="F04-FSR-H01"):
        target.restore(raw, NOW)
    assert target.to_dict() == before
    # Older writers without optional metadata stay restorable.
    legacy = target.to_dict()
    for key in ("name", "registry_id", "identity_signature", "tombstone", "identity_conflict"):
        legacy["external_sources"][0].pop(key)
    validate_snapshot_body(legacy)
    restored = ExternalLeakController()
    restored.restore(legacy, NOW)
    assert restored.sources["a"].phase is ExternalPhase.ACTIVE
