"""Semantic ledger corruption through actual HA Store, writes and restarts."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.util.file import WriteError
from test_external_leaks import NOW, controller
from test_f04_security_review_controls import action, setup
from test_f04_v2_safety_boundaries import restart

from custom_components.water_leak_detection.external_leaks import ExternalLeakController
from custom_components.water_leak_detection.storage import validate_snapshot_body


async def retained_alarm(hass, entry, clock):
    manager = await setup(hass, entry, clock)
    old = manager.external.sources["a"].identity.generation
    registry = er.async_get(hass)
    registry.async_remove("binary_sensor.a")
    hass.states.async_set("binary_sensor.a", "unavailable")
    await hass.async_block_till_done()
    registry.async_get_or_create("binary_sensor", "test", "replacement", suggested_object_id="a")
    hass.states.async_set("binary_sensor.a", "off")
    await hass.async_block_till_done()
    assert manager.external.tombstones[("a", old)].phase.value == "ACTIVE"
    assert manager.shutoff_request
    await manager.async_unload()
    path = Path(manager._store.path)
    good = path.read_bytes()
    raw = json.loads(good)
    record = next(r for r in raw["data"]["external_alarm_ledger"] if r["generation"] == old)
    return manager, path, good, raw, record


@pytest.mark.parametrize("role", ["external_sources", "external_alarm_ledger"])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("phase", ["ARMED", "RESET_WAITING_FOR_OFF"])
async def test_contradictory_identity_preserves_original_store_across_reordered_restores(
    runtime_hass, runtime_entry, measurement_clock, role, reverse, phase
):
    manager, path, _, raw, record = await retained_alarm(
        runtime_hass, runtime_entry, measurement_clock
    )
    record["phase"] = phase
    if role == "external_sources":
        raw["data"]["external_alarm_ledger"].remove(record)
        raw["data"][role].append(record)
    if reverse:
        raw["data"][role].reverse()
    path.write_text(json.dumps(raw))
    original = path.read_bytes()
    for _ in range(2):
        manager = await restart(runtime_hass, runtime_entry, manager)
        assert manager._storage_load_failed and not manager._migration_ready
        assert manager.alarm_active and manager.shutoff_request
        assert not manager.active_events()  # No guessed identity grants actions.
        assert path.read_bytes() == original


@pytest.mark.parametrize(
    "change",
    [
        {"event_id": None},
        {"started_at": None},
        {"generation": None},
        {"tombstone": False},
        {"identity_conflict": True},
        {"contributes_to_shutoff": False},
    ],
)
def test_ledger_role_itself_cannot_prove_inactive_generation_is_safe(change):
    target = controller()
    target.observe("a", "on", NOW)
    raw = target.to_dict()
    record = raw["external_sources"].pop()
    record.update(phase="ARMED", tombstone=True)
    record.update(change)
    raw["external_alarm_ledger"].append(record)
    original = deepcopy(raw)
    current = target.to_dict()
    with pytest.raises(ValueError, match="Contradictory"):
        validate_snapshot_body(raw)
    with pytest.raises(ValueError, match="Contradictory"):
        target.restore(raw, NOW)
    assert target.to_dict() == current  # Validate ALL records before clearing live safety.
    assert raw == original


@pytest.mark.parametrize("phase", ["ARMED", "RESET_WAITING_FOR_OFF"])
@pytest.mark.parametrize("version", [1, 2])
async def test_ledger_recovery_blocks_writes_then_verified_backup_retains_alarm(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch, phase, version
):
    manager, path, good, raw, record = await retained_alarm(
        runtime_hass, runtime_entry, measurement_clock
    )
    record["phase"] = phase
    raw["version"] = version
    path.write_text(json.dumps(raw))
    original = path.read_bytes()
    manager = await restart(runtime_hass, runtime_entry, manager)
    assert manager._storage_load_failed

    def fail(*_):
        raise WriteError("controlled recovery write failure")

    with monkeypatch.context() as patch:
        patch.setattr(manager._store, "_write_prepared_data", fail)
        runtime_hass.states.async_set("binary_sensor.b", "on")
        await runtime_hass.async_block_till_done()
        runtime_hass.states.async_set("binary_sensor.b", "off")
        await runtime_hass.async_block_till_done()
        with pytest.raises(RuntimeError):
            await manager.async_update_options(dict(runtime_entry.options))
        assert manager.alarm_active and manager.shutoff_request
        assert path.read_bytes() == original
    await manager.async_unload()
    assert path.read_bytes() == original
    path.write_bytes(good)  # Offline verified complete backup, never infer a replacement body.
    manager = await restart(runtime_hass, runtime_entry, manager)
    assert not manager._storage_load_failed
    assert manager.external.has_active_sources and manager.shutoff_request


async def test_authorized_tombstone_reset_failure_then_success_affects_only_exact_generation(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch
):
    manager, path, _, _, _ = await retained_alarm(runtime_hass, runtime_entry, measurement_clock)
    manager = await restart(runtime_hass, runtime_entry, manager)
    runtime_hass.states.async_set("binary_sensor.b", "on")
    await runtime_hass.async_block_till_done()
    other = manager.external.sources["b"].event_id
    tombstone = next(iter(manager.external.tombstones.values()))
    reset = {
        **action(manager),
        "source_generation": tombstone.identity.generation,
        "event_id": tombstone.event_id,
        "reset_nonce": tombstone.reset_nonce,
    }
    original = path.read_bytes()

    def fail(*_):
        raise WriteError("controlled tombstone reset write failure")

    with monkeypatch.context() as patch:
        patch.setattr(manager._store, "_write_prepared_data", fail)
        assert not await manager.async_external_reset(reset)
        assert manager.external.has_active_sources and manager.shutoff_request
        assert path.read_bytes() == original
    assert await manager.async_external_reset(reset)
    assert not manager.external.tombstones
    assert other in manager.active_events() and manager.shutoff_request
    manager = await restart(runtime_hass, runtime_entry, manager)
    assert not manager._storage_load_failed and not manager.external.tombstones
    assert other in manager.active_events() and manager.shutoff_request


@pytest.mark.parametrize("waiting", [False, True])
def test_legal_inactive_sources_remain_restorable_without_recovery(waiting):
    target = controller()
    if waiting:
        target.observe("a", "on", NOW)
        target.reset("a", "g1", target.sources["a"].event_id)
    raw = target.to_dict()
    validate_snapshot_body(raw)
    restored = ExternalLeakController()
    restored.restore(raw, NOW)
    assert restored.sources["a"].phase == target.sources["a"].phase
    assert not restored.has_active_sources and not restored.shutoff_request
