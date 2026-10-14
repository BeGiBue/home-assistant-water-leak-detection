"""Actual manager + HA Store: authorization, durable resets, races and restarts."""

import asyncio
import json
from pathlib import Path

import pytest
from homeassistant.core import Event
from homeassistant.helpers import entity_registry as er
from test_manager_runtime import start_manager

from custom_components.water_leak_detection.const import (
    ACTION_EXTERNAL_RESET,
    CONF_EXTERNAL_SENSORS,
    CONF_NOTIFICATION_RECIPIENTS,
    DOMAIN,
    DetectorKind,
    DetectorPhase,
)
from custom_components.water_leak_detection.external_leaks import ExternalPhase
from custom_components.water_leak_detection.manager import WaterLeakManager


async def configured(hass, entry, clock):
    er.async_get(hass).async_get_or_create(
        "binary_sensor", "test", "kitchen", suggested_object_id="kitchen"
    )
    er.async_get(hass).async_get_or_create(
        "binary_sensor", "test", "bathroom", suggested_object_id="bathroom"
    )
    hass.states.async_set("binary_sensor.kitchen", "off")
    hass.states.async_set("binary_sensor.bathroom", "off")
    hass.states.async_set("device_tracker.phone", "home")
    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            CONF_EXTERNAL_SENSORS: [
                {"id": "a", "entity_id": "binary_sensor.kitchen", "contributes_to_shutoff": True},
                {"id": "b", "entity_id": "binary_sensor.bathroom", "contributes_to_shutoff": True},
            ],
            CONF_NOTIFICATION_RECIPIENTS: [
                {
                    "id": "phone",
                    "name": "Phone",
                    "notify_service": "notify.mobile_app_phone",
                    "tracker_entity": "device_tracker.phone",
                    "token": "recipient_token",
                    "allow_external_reset": True,
                    "allow_global_ack": False,
                }
            ],
        },
    )
    return await start_manager(hass, entry, clock, 0)


def action(manager, source_id="a"):
    source = manager.external.sources[source_id]
    return {
        "action_kind": ACTION_EXTERNAL_RESET,
        "config_entry_id": manager.entry.entry_id,
        "source_id": source.source_id,
        "source_generation": source.identity.generation,
        "event_id": source.event_id,
        "recipient_id": "phone",
        "recipient_token": "recipient_token",
        "reset_nonce": source.reset_nonce,
    }


@pytest.mark.parametrize(
    "field",
    [
        "action_kind",
        "config_entry_id",
        "source_id",
        "source_generation",
        "event_id",
        "recipient_id",
        "recipient_token",
        "reset_nonce",
    ],
)
async def test_each_wrong_binding_rejects_without_physical_release(
    runtime_hass, runtime_entry, measurement_clock, field
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    payload = action(manager)
    payload[field] = "wrong"
    assert not await manager.async_external_reset(payload)
    assert manager.alarm_active and manager.shutoff_request
    assert manager.external.sources["a"].phase is ExternalPhase.ACTIVE


@pytest.mark.parametrize("tracker", ["away", "unknown", "unavailable", "not_home"])
async def test_trusted_stationary_does_not_replace_actual_home(
    runtime_hass, runtime_entry, measurement_clock, tracker
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    recipient = {
        **runtime_entry.options[CONF_NOTIFICATION_RECIPIENTS][0],
        "trusted_stationary": True,
        "allow_global_ack": True,
    }
    runtime_hass.config_entries.async_update_entry(
        runtime_entry,
        options={
            **runtime_entry.options,
            CONF_NOTIFICATION_RECIPIENTS: [recipient],
        },
    )
    runtime_hass.states.async_set("device_tracker.phone", tracker)
    assert not await manager.async_external_reset(action(manager))
    assert manager.shutoff_request


@pytest.mark.parametrize("permission", [False, "true", 1, None])
async def test_external_permission_is_independent_and_strict_bool(
    runtime_hass, runtime_entry, measurement_clock, permission
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    recipient = {
        **runtime_entry.options[CONF_NOTIFICATION_RECIPIENTS][0],
        "allow_external_reset": permission,
        "allow_global_ack": True,
    }
    runtime_hass.config_entries.async_update_entry(
        runtime_entry,
        options={
            **runtime_entry.options,
            CONF_NOTIFICATION_RECIPIENTS: [recipient],
        },
    )
    assert not await manager.async_external_reset(action(manager))
    assert manager.shutoff_request


async def test_real_store_reset_restart_waiting_replay_and_new_event(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    payload = action(manager)
    assert await manager.async_external_reset(payload)
    assert not manager.alarm_active and not manager.shutoff_request
    disk = json.loads(Path(manager._store.path).read_text())["data"]
    assert disk["external_sources"][0]["phase"] == "RESET_WAITING_FOR_OFF"
    assert not await manager.async_external_reset(payload)
    runtime_hass.states.async_set("binary_sensor.kitchen", "on")
    await runtime_hass.async_block_till_done()
    await manager.async_unload()
    restored = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    await restored.async_setup()
    assert restored.external.sources["a"].phase is ExternalPhase.RESET_WAITING_FOR_OFF
    assert not restored.alarm_active
    await restored._async_external_changed("binary_sensor.kitchen", "off")
    await restored._async_external_changed("binary_sensor.kitchen", "on")
    assert restored.external.sources["a"].event_id != payload["event_id"]
    assert not await restored.async_external_reset(payload)
    assert restored.shutoff_request


async def test_boot_rotates_nonce_preserves_event_and_ack(
    runtime_hass, runtime_entry, measurement_clock
):
    from custom_components.water_leak_detection.notifications import EventAcknowledgement

    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    payload = action(manager)
    manager.notifications.acknowledgements[payload["event_id"]] = EventAcknowledgement(
        globally_acknowledged=True
    )
    runtime_hass.states.async_set("binary_sensor.kitchen", "on")
    await runtime_hass.async_block_till_done()
    await manager.async_unload()
    restored = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    await restored.async_setup()
    source = restored.external.sources["a"]
    assert source.event_id == payload["event_id"]
    assert source.reset_nonce != payload["reset_nonce"]
    assert restored.notifications.acknowledgements[source.event_id].globally_acknowledged
    assert not await restored.async_external_reset(payload)


async def test_real_writer_failure_keeps_memory_disk_alarm_and_shutoff(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    before = Path(manager._store.path).read_bytes()
    payload = action(manager)

    def fail(*_args):
        raise OSError("injected disk write failure")

    with monkeypatch.context() as patch:
        patch.setattr(manager._store, "_write_prepared_data", fail)
        assert not await manager.async_external_reset(payload)
    assert manager.external.sources["a"].phase is ExternalPhase.ACTIVE
    assert manager.alarm_active and manager.shutoff_request
    assert Path(manager._store.path).read_bytes() == before


async def test_private_reset_commit_readers_and_ordered_off_on_actions(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    payload = action(manager)
    entered, proceed = asyncio.Event(), asyncio.Event()
    actual_save = manager._store.async_save

    async def slow_save(snapshot):
        entered.set()
        await proceed.wait()
        await actual_save(snapshot)

    monkeypatch.setattr(manager._store, "async_save", slow_save)
    reset = asyncio.create_task(manager.async_external_reset(payload))
    await entered.wait()
    assert manager.alarm_active and manager.shutoff_request
    assert manager.external.sources["a"].phase is ExternalPhase.ACTIVE
    assert (
        json.loads(Path(manager._store.path).read_text())["data"]["external_sources"][0]["phase"]
        == "ACTIVE"
    )
    off = asyncio.create_task(manager._async_external_changed("binary_sensor.kitchen", "off"))
    on = asyncio.create_task(manager._async_external_changed("binary_sensor.kitchen", "on"))
    replay = asyncio.create_task(manager.async_external_reset(payload))
    proceed.set()
    assert await reset
    await asyncio.gather(off, on)
    assert not await replay
    assert manager.alarm_active and manager.shutoff_request
    assert manager.external.sources["a"].event_id != payload["event_id"]
    assert (
        json.loads(Path(manager._store.path).read_text())["data"]["external_sources"][0]["phase"]
        == "ACTIVE"
    )


async def test_reset_leaves_other_external_and_hydraulic_shutoff_contributions(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    for entity in ("binary_sensor.kitchen", "binary_sensor.bathroom"):
        await manager._async_external_changed(entity, "on")
    runtime = manager.engine.runtimes[DetectorKind.BURST_LEAK]
    runtime.phase = DetectorPhase.ACTIVE
    runtime.event_id = "burst_active"
    assert await manager.async_external_reset(action(manager))
    assert len(manager.external.active_events()) == 1
    assert manager.shutoff_request
    assert await manager.async_external_reset(action(manager, "b"))
    assert not manager.external.active_events()
    assert manager.shutoff_request and manager.alarm_active
    assert runtime.event_id == "burst_active"


async def test_notification_action_uses_same_exact_validator(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    recipient = manager.notifications.recipients["phone"]
    action_id = manager.notifications.external_reset_action(
        manager.external.sources["a"].event_id, recipient
    )
    await manager.notifications._async_mobile_action(
        Event("mobile_app_notification_action", {"action": action_id})
    )
    assert manager.external.sources["a"].phase is ExternalPhase.RESET_WAITING_FOR_OFF
