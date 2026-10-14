"""Uninterpretable retained records never become inactive or trusted capabilities."""

import json
from copy import deepcopy

import pytest
from homeassistant.helpers import issue_registry as ir
from homeassistant.util.file import WriteError
from test_external_leaks import NOW, controller
from test_f04_nachreview_recovery import retained_alarm
from test_f04_v2_safety_boundaries import restart

from custom_components.water_leak_detection.const import DOMAIN
from custom_components.water_leak_detection.storage import validate_snapshot_body

CHANGES = [
    {"phase": None},
    {"phase": "damaged"},
    {"phase": []},
    {"phase": {}},
    {"phase": False},
    {"event_id": None},
    {"event_id": False},
    {"event_id": "broken id"},
    {"event_id": []},
    {"event_id": {}},
    {"source_id": None},
    {"generation": False},
    {"learning_epoch": "bad epoch"},
    {"started_at": None},
    {"started_at": "2026-10-13T12:00:00"},
    {"contributes_to_shutoff": "false"},
    {"identity_conflict": []},
    {"tombstone": "true"},
    {"entity_id": None},
    {"phase": "damaged", "event_id": None},
]


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("change", [*CHANGES, "missing_phase", "missing_event_id"])
async def test_every_retained_identity_damage_preserves_bytes_and_blocks_capabilities(
    runtime_hass, runtime_entry, measurement_clock, version, change
):
    manager, path, _, raw, record = await retained_alarm(
        runtime_hass, runtime_entry, measurement_clock
    )
    event = record["event_id"]
    generation = record["generation"]
    raw["version"] = version
    if isinstance(change, dict):
        record.update(change)
    else:
        record.pop(change.removeprefix("missing_"))
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    for _ in range(2):
        manager = await restart(runtime_hass, runtime_entry, manager)
        assert manager._storage_load_failed and not manager._migration_ready
        assert manager.alarm_active and manager.shutoff_request
        assert path.read_bytes() == before
        assert event not in manager.active_events()
        assert not await manager.async_acknowledge_event(event, "phone", "token")
        assert not await manager.async_request_external_reset_action(
            "a", "phone", generation, event
        )
        assert (
            ir.async_get(runtime_hass).async_get_issue(
                DOMAIN, f"{runtime_entry.entry_id}_runtime_safety_recovery"
            )
            is not None
        )


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("in_sources", [False, True])
async def test_multiple_generations_and_duplicate_records_cannot_hide_uninterpretable_alarm(
    runtime_hass, runtime_entry, measurement_clock, version, reverse, in_sources
):
    manager, path, _, raw, record = await retained_alarm(
        runtime_hass, runtime_entry, measurement_clock
    )
    another = deepcopy(record)
    another.update(generation="independent_generation", event_id="independent_event")
    raw["data"]["external_alarm_ledger"].extend([another, deepcopy(another)])
    record.pop("phase")
    record["event_id"] = {}
    if in_sources:
        raw["data"]["external_alarm_ledger"].remove(record)
        raw["data"]["external_sources"].append(record)  # Tombstone role follows its marker.
    raw["version"] = version
    if reverse:
        for field in ("external_sources", "external_alarm_ledger"):
            raw["data"][field].reverse()
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    manager = await restart(runtime_hass, runtime_entry, manager)
    assert manager._storage_load_failed and manager.shutoff_request and manager.alarm_active
    assert path.read_bytes() == before


@pytest.mark.parametrize("version", [1, 2])
async def test_unknown_ledger_write_failure_and_verified_backup_do_not_release_alarm(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch, version
):
    manager, path, good, raw, record = await retained_alarm(
        runtime_hass, runtime_entry, measurement_clock
    )
    raw["version"] = version
    record.update(phase=None, event_id=None)
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    manager = await restart(runtime_hass, runtime_entry, manager)

    def fail(*_):
        raise WriteError("controlled recovery save failure")

    with monkeypatch.context() as patch:
        patch.setattr(manager._store, "_write_prepared_data", fail)
        with pytest.raises(RuntimeError):
            await manager.async_update_options(dict(runtime_entry.options))
        runtime_hass.states.async_set("binary_sensor.b", "on")
        await runtime_hass.async_block_till_done()
        runtime_hass.states.async_set("binary_sensor.b", "off")
        await runtime_hass.async_block_till_done()
        for flow in [0, 250, 250, 0, 0, 0, 0]:
            measurement_clock.advance(60)
            runtime_hass.states.async_set(
                "sensor.flow", str(flow), {"unit_of_measurement": "L/h"}, force_update=True
            )
            await runtime_hass.async_block_till_done()
        assert not manager.learner.samples
        assert not manager.long_term_learner.pending_high_candidates
        assert manager.alarm_active and manager.shutoff_request
        assert path.read_bytes() == before
    await manager.async_unload()
    assert path.read_bytes() == before
    path.write_bytes(good)
    manager = await restart(runtime_hass, runtime_entry, manager)
    assert not manager._storage_load_failed and manager._migration_ready
    assert manager.external.has_active_sources and manager.shutoff_request
    assert (
        ir.async_get(runtime_hass).async_get_issue(
            DOMAIN, f"{runtime_entry.entry_id}_runtime_safety_recovery"
        )
        is None
    )


@pytest.mark.parametrize("role", ["external_sources", "external_alarm_ledger"])
def test_uninterpretable_retained_record_rejected_before_live_state_normalization(role):
    target = controller()
    target.observe("a", "on", NOW)
    before = target.to_dict()
    record = deepcopy(before["external_sources"][0])
    record.update(phase=None, event_id=False, tombstone=True)
    raw = {"external_sources": [], "external_alarm_ledger": [], role: [record]}
    saved = deepcopy(raw)
    with pytest.raises(ValueError):
        validate_snapshot_body(raw)
    with pytest.raises(ValueError):
        target.restore(raw, NOW)
    assert target.to_dict() == before and raw == saved


async def test_direct_store_write_rejects_damaged_ledger_before_atomic_writer(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch
):
    manager, path, _, raw, record = await retained_alarm(
        runtime_hass, runtime_entry, measurement_clock
    )
    before = path.read_bytes()
    record.update(phase=None, event_id=None)
    calls = []

    def fail(*args):
        calls.append(args)
        raise WriteError("must not reach physical writer for invalid ledger")

    with monkeypatch.context() as patch:
        patch.setattr(manager._store, "_write_prepared_data", fail)
        with pytest.raises(ValueError, match="uninterpretable retained"):
            await manager._store.async_save(raw["data"])
    assert not calls and path.read_bytes() == before
