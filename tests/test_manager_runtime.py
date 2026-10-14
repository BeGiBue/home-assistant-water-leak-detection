"""Manager/Store/ConfigEntry regressions using actual HA runtime objects."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import EVENT_HOMEASSISTANT_FINAL_WRITE
from homeassistant.core import Event, State

import custom_components.water_leak_detection as integration
from custom_components.water_leak_detection.const import (
    CONF_FLOW_ENTITY,
    CONF_NOTIFICATION_RECIPIENTS,
    CONF_SOURCE_MAX_AGE_SEC,
    CONF_TOTAL_ENTITY,
    DOMAIN,
    EVENT_LEAK_ENDED,
    EVENT_LEAK_STARTED,
    DetectorKind,
    DetectorPhase,
)
from custom_components.water_leak_detection.manager import WaterLeakManager


def report(hass, clock, value, entity="sensor.flow", unit="L/h"):
    hass.states.async_set(entity, str(value), {"unit_of_measurement": unit},
                          timestamp=clock.utcnow().timestamp())


async def start_manager(hass, entry, clock, value=7, *, configured_gap=0):
    # Existing runtime regressions exercise the explicitly stored 1.1.0 Burst
    # basis. F04 default tests separately exercise new/missing options (3500).
    hass.config_entries.async_update_entry(entry, options={
        "burst_threshold_lph": 2000, **entry.options,
    })
    if configured_gap:
        # Tests of established safety states can explicitly declare their cadence.
        hass.config_entries.async_update_entry(entry, options={
            **entry.options, CONF_SOURCE_MAX_AGE_SEC: configured_gap,
        })
    report(hass, clock, value)
    manager = WaterLeakManager(hass, entry)
    manager.notifications._async_common_translations = AsyncMock(return_value={})
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    assert hass.loop is asyncio.get_running_loop()
    await asyncio.wait_for(manager.async_setup(), 5)
    return manager


async def flush(manager):
    if manager._save_handle is not None:
        manager._save_handle.cancel()
        manager._save_handle = None
    manager._start_save()
    await manager._save_task


async def test_f01_fixed_deadline_and_real_store_write(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock)
    deadline = manager._save_handle.when()
    for _ in range(20):
        measurement_clock.advance(1)
        report(runtime_hass, measurement_clock, 7)
        await manager.async_refresh()
        assert manager._save_handle.when() == deadline
    await flush(manager)
    persisted = json.loads(Path(manager._store.path).read_text())["data"]
    assert persisted["sources"]["flow"] == "sensor.flow"
    manager._notification_state_changed()
    urgent = manager._save_handle.when()
    assert urgent <= runtime_hass.loop.time() + 1
    manager._schedule_save()
    assert manager._save_handle.when() == urgent


async def test_f01_final_write_flushes_pending_state(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock)
    runtime_hass.bus.async_fire(EVENT_HOMEASSISTANT_FINAL_WRITE)
    await runtime_hass.async_block_till_done()
    assert json.loads(Path(manager._store.path).read_text())["data"]["sources"]["flow"]
    assert manager._save_handle is None


async def test_f05_identical_reports_are_fresh_but_frozen_value_is_not(
    runtime_hass, runtime_entry, measurement_clock
):
    # The old automatic expiry is now an explicit expert policy.
    manager = await start_manager(
        runtime_hass, runtime_entry, measurement_clock, 2500, configured_gap=10
    )
    initial = runtime_hass.states.get("sensor.flow").last_updated
    for _ in range(5):
        measurement_clock.advance(10)
        report(runtime_hass, measurement_clock, 2500)
        await manager.async_refresh()
    assert runtime_hass.states.get("sensor.flow").last_updated == initial
    assert manager.engine.runtimes[DetectorKind.BURST_LEAK].phase is DetectorPhase.ACTIVE
    event_id = manager.engine.runtimes[DetectorKind.BURST_LEAK].event_id
    measurement_clock.advance(1)
    report(runtime_hass, measurement_clock, 0)
    await manager.async_refresh()
    measurement_clock.advance(61)
    await manager.async_refresh()
    assert not manager.source_available
    assert manager.engine.runtimes[DetectorKind.BURST_LEAK].event_id == event_id
    assert manager.engine.runtimes[DetectorKind.BURST_LEAK].quiet_since is None


async def test_f05_single_high_report_cannot_mature_after_expiry(
    runtime_hass, runtime_entry, measurement_clock
):
    # The old automatic expiry is now an explicit expert policy.
    manager = await start_manager(
        runtime_hass, runtime_entry, measurement_clock, 2500, configured_gap=10
    )
    measurement_clock.advance(30)
    await manager.async_refresh()
    assert not manager.engine.snapshot().alarm_active
    assert not manager.source_available
    report(runtime_hass, measurement_clock, 2500)
    await manager.async_refresh()
    assert manager.engine.runtimes[DetectorKind.BURST_LEAK].phase is DetectorPhase.MONITORING


@pytest.mark.parametrize("invalid", [-1, "unknown", "unavailable", "None", "nan", "bad"])
async def test_invalid_source_keeps_alarm_and_shutoff(
    runtime_hass, runtime_entry, measurement_clock, invalid
):
    manager = await start_manager(
        runtime_hass, runtime_entry, measurement_clock, 2500, configured_gap=10
    )
    for _ in range(3):
        measurement_clock.advance(10)
        report(runtime_hass, measurement_clock, 2500)
        await manager.async_refresh()
    report(runtime_hass, measurement_clock, invalid)
    await manager.async_refresh()
    measurement_clock.advance(100)
    await manager.async_refresh()
    assert manager.engine.snapshot().alarm_active
    assert manager.engine.snapshot().shutoff_request
    assert not manager.source_available


async def test_f13_switch_source_preserves_active_identity_without_old_total(
    runtime_hass, runtime_entry, measurement_clock
):
    runtime_hass.config_entries.async_update_entry(runtime_entry, data={
        CONF_FLOW_ENTITY: "sensor.flow", CONF_TOTAL_ENTITY: "sensor.total",
    })
    report(runtime_hass, measurement_clock, 1000, "sensor.total", "L")
    manager = await start_manager(
        runtime_hass, runtime_entry, measurement_clock, 2500, configured_gap=10
    )
    for _ in range(3):
        measurement_clock.advance(10)
        report(runtime_hass, measurement_clock, 2500)
        await manager.async_refresh()
    event_id = manager.engine.snapshot().active_event_id
    volume = manager.engine.runtimes[DetectorKind.BURST_LEAK].estimated_volume_l
    await runtime_hass.async_block_till_done()
    await manager.async_unload()
    runtime_hass.config_entries.async_update_entry(runtime_entry, data={
        CONF_FLOW_ENTITY: "sensor.new_flow", CONF_TOTAL_ENTITY: "sensor.new_total",
    })
    report(runtime_hass, measurement_clock, 2500, "sensor.new_flow")
    report(runtime_hass, measurement_clock, 100000, "sensor.new_total", "L")
    restored = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    await restored.async_setup()
    assert restored.engine.snapshot().active_event_id == event_id
    assert restored.engine.snapshot().shutoff_request
    assert restored.engine.snapshot(
        restored.current_total_l
    ).active_volume_l == pytest.approx(volume)
    assert restored.engine.runtimes[DetectorKind.BURST_LEAK].start_total_l != 1000


async def test_f15_old_sample_and_wall_jump_cannot_mature_timer(
    runtime_hass, runtime_entry, measurement_clock
):
    runtime_hass.config_entries.async_update_entry(runtime_entry, options={
        CONF_SOURCE_MAX_AGE_SEC: 3600,
    })
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock)
    before = manager.engine.to_dict()
    old = State("sensor.flow", "0", {"unit_of_measurement": "L/h"},
                last_reported=measurement_clock.origin.replace(year=2025))
    await manager._async_source_changed(Event("state_changed", {
        "entity_id": "sensor.flow", "new_state": old,
    }))
    assert manager.engine.to_dict() == before
    measurement_clock.wall_shift = 86400
    report(runtime_hass, measurement_clock, 7)
    await manager.async_refresh()
    assert not manager.engine.snapshot().alarm_active


async def test_f17_bus_ended_payload_has_original_burst_reason(
    runtime_hass, runtime_entry, measurement_clock
):
    started, ended = [], []
    runtime_hass.bus.async_listen(EVENT_LEAK_STARTED, lambda event: started.append(event.data))
    runtime_hass.bus.async_listen(EVENT_LEAK_ENDED, lambda event: ended.append(event.data))
    manager = await start_manager(
        runtime_hass, runtime_entry, measurement_clock, 0, configured_gap=10
    )
    for flow in (2500, 2500, 0, 0, 0, 0, 0, 0, 0):
        measurement_clock.advance(10)
        report(runtime_hass, measurement_clock, flow)
        await manager.async_refresh()
        await runtime_hass.async_block_till_done()
    burst_end = next(payload for payload in ended if payload["type"] == "burst_leak")
    assert burst_end["reason"] == "rapid_rise"
    assert burst_end["event_id"] == next(
        payload["event_id"] for payload in started if payload["type"] == "burst_leak"
    )


async def test_f14_setup_failure_rolls_back_real_manager(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch
):
    report(runtime_hass, measurement_clock, 7)
    created = []
    def construct(hass, entry):
        manager = WaterLeakManager(hass, entry)
        created.append(manager)
        return manager
    monkeypatch.setattr(integration, "WaterLeakManager", construct)
    monkeypatch.setattr(runtime_hass.config_entries, "async_forward_entry_setups",
                        AsyncMock(side_effect=RuntimeError("platform failed")))
    monkeypatch.setattr(runtime_hass.config_entries, "async_unload_platforms",
                        AsyncMock(return_value=True))
    with pytest.raises(RuntimeError, match="platform failed"):
        await asyncio.wait_for(integration.async_setup_entry(runtime_hass, runtime_entry), 3)
    assert runtime_entry.entry_id not in runtime_hass.data[DOMAIN]
    assert created[0]._closed
    assert not created[0]._unsubs
    assert created[0]._save_handle is None
    monkeypatch.setattr(runtime_hass.config_entries, "async_forward_entry_setups", AsyncMock())
    assert await asyncio.wait_for(integration.async_setup_entry(runtime_hass, runtime_entry), 3)
    assert len(created[1]._unsubs) == 4  # Includes the stable source-registry listener.


async def test_f12_config_entry_recipient_update_retains_monitoring(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch
):
    report(runtime_hass, measurement_clock, 7)
    monkeypatch.setattr(runtime_hass.config_entries, "async_forward_entry_setups", AsyncMock())
    await asyncio.wait_for(integration.async_setup_entry(runtime_hass, runtime_entry), 3)
    manager = runtime_hass.data[DOMAIN][runtime_entry.entry_id]
    for _ in range(5):
        measurement_clock.advance(10)
        report(runtime_hass, measurement_clock, 7)
        await manager.async_refresh()
    started_at = manager.engine.runtimes[DetectorKind.SLOW_LEAK].started_at
    runtime_hass.config_entries.async_update_entry(runtime_entry, options={
        CONF_NOTIFICATION_RECIPIENTS: [{
            "id": "new", "name": "New phone", "notify_service": "notify.mobile_app_new",
            "tracker_entity": "device_tracker.new", "token": "new-token",
        }],
    })
    await runtime_hass.async_block_till_done()
    assert runtime_hass.data[DOMAIN][runtime_entry.entry_id] is manager
    assert manager.engine.runtimes[DetectorKind.SLOW_LEAK].started_at == started_at
    assert "new" in manager.notifications.recipients


async def test_f01_real_timer_saves_safety_transition_within_bound(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(
        runtime_hass, runtime_entry, measurement_clock, 2500, configured_gap=10
    )
    for _ in range(3):
        measurement_clock.advance(10)
        report(runtime_hass, measurement_clock, 2500)
        await manager.async_refresh()
    assert manager._save_handle.when() <= runtime_hass.loop.time() + 1
    await asyncio.sleep(1.05)
    await runtime_hass.async_block_till_done()
    stored = json.loads(Path(manager._store.path).read_text())["data"]
    assert stored["engine"]["runtimes"]["burst_leak"]["phase"] == "active"


async def test_f16_corrupt_real_store_fields_do_not_prevent_safe_restart(
    runtime_hass, runtime_entry, measurement_clock
):
    report(runtime_hass, measurement_clock, "unavailable")
    manager = WaterLeakManager(runtime_hass, runtime_entry)
    await manager._store.async_save({
        "sources": {"flow": "sensor.flow", "total": None},
        "bypass_until": "2026-10-07T01:00:00",  # naive time is invalid
        "engine": {"runtimes": {"burst_leak": {
            "phase": "active", "event_id": "valid-active", "started_at": "bad",
            "detected_at": "2026-10-07T00:00:00", "start_total_l": "nan",
            "estimated_volume_l": -1, "plausible_volume_l": "inf",
        }}},
        "acknowledgements": {"valid-active": {
            "globally_acknowledged_at": "2026-10-07T00:00:00",
            "muted_recipients": 5, "delivered_recipients": [None],
        }},
        "learning": {"samples": [{"timestamp": "2026-10-07T00:00:00", "peak_lph": "inf"}]},
    })
    runtime_hass.data.setdefault(DOMAIN, {})[runtime_entry.entry_id] = manager
    await manager.async_setup()
    assert manager.engine.snapshot().active_event_id == "valid-active"
    assert manager.engine.snapshot().shutoff_request
    assert manager.bypass_until is None
    assert manager.notifications.acknowledgements["valid-active"].muted_recipients == set()
    await manager.async_unload()
    runtime_hass.data[DOMAIN].pop(runtime_entry.entry_id)


async def test_f14_cleanup_preserves_setup_error_if_platform_rollback_fails(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch
):
    report(runtime_hass, measurement_clock, 7)
    monkeypatch.setattr(runtime_hass.config_entries, "async_forward_entry_setups",
                        AsyncMock(side_effect=RuntimeError("original setup error")))
    monkeypatch.setattr(runtime_hass.config_entries, "async_unload_platforms",
                        AsyncMock(side_effect=RuntimeError("rollback platform error")))
    with pytest.raises(RuntimeError, match="original setup error"):
        await integration.async_setup_entry(runtime_hass, runtime_entry)
    assert not runtime_hass.data[DOMAIN]


async def test_f22_existing_entry_cannot_use_own_derived_sensor(
    runtime_hass, runtime_entry, measurement_clock
):
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(runtime_hass)
    derived = registry.async_get_or_create(
        "sensor", DOMAIN, "derived-output", suggested_object_id="derived",
        config_entry=runtime_entry,
    )
    runtime_hass.config_entries.async_update_entry(runtime_entry, data={
        CONF_FLOW_ENTITY: derived.entity_id,
    })
    report(runtime_hass, measurement_clock, 2500, derived.entity_id)
    manager = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data.setdefault(DOMAIN, {})[runtime_entry.entry_id] = manager
    await manager.async_setup()
    assert not manager.source_available
    assert not manager.engine.snapshot().alarm_active


async def test_f15_queued_old_invalid_report_does_not_discard_current_monitoring(
    runtime_hass, runtime_entry, measurement_clock
):
    old = State("sensor.flow", "unavailable", {}, last_updated=measurement_clock.utcnow())
    measurement_clock.advance(10)
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 7)
    started = manager.engine.runtimes[DetectorKind.SLOW_LEAK].started_at
    await manager._async_source_changed(Event("state_changed", {
        "entity_id": "sensor.flow", "new_state": old,
    }))
    assert manager.engine.runtimes[DetectorKind.SLOW_LEAK].started_at == started
    assert manager.source_available


async def test_f13_entry_unload_setup_rebases_new_meter_and_preserves_safety(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch
):
    monkeypatch.setattr(runtime_hass.config_entries, "async_forward_entry_setups", AsyncMock())
    monkeypatch.setattr(runtime_hass.config_entries, "async_unload_platforms",
                        AsyncMock(return_value=True))
    runtime_hass.config_entries.async_update_entry(runtime_entry, data={
        CONF_FLOW_ENTITY: "sensor.flow", CONF_TOTAL_ENTITY: "sensor.total",
    }, options={CONF_SOURCE_MAX_AGE_SEC: 10})
    report(runtime_hass, measurement_clock, 4000)
    report(runtime_hass, measurement_clock, 1000, "sensor.total", "L")
    await integration.async_setup_entry(runtime_hass, runtime_entry)
    manager = runtime_hass.data[DOMAIN][runtime_entry.entry_id]
    for _ in range(3):
        measurement_clock.advance(10)
        report(runtime_hass, measurement_clock, 4000)
        await manager.async_refresh()
        await runtime_hass.async_block_till_done()
    event_id = manager.engine.snapshot().active_event_id
    assert event_id
    runtime_hass.config_entries.async_update_entry(runtime_entry, data={
        CONF_FLOW_ENTITY: "sensor.new_flow", CONF_TOTAL_ENTITY: "sensor.new_total",
    })
    await runtime_hass.async_block_till_done()
    assert await integration.async_unload_entry(runtime_hass, runtime_entry)
    assert manager._closed and not manager._unsubs
    assert runtime_entry.entry_id not in runtime_hass.data[DOMAIN]
    report(runtime_hass, measurement_clock, 4000, "sensor.new_flow")
    report(runtime_hass, measurement_clock, 100000, "sensor.new_total", "L")
    await integration.async_setup_entry(runtime_hass, runtime_entry)
    restored = runtime_hass.data[DOMAIN][runtime_entry.entry_id]
    snapshot = restored.engine.snapshot(restored.current_total_l)
    assert snapshot.active_event_id == event_id
    assert snapshot.shutoff_request
    assert snapshot.active_volume_l < 100
