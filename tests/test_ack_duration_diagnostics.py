"""Native acknowledgement security, repeated notification IDs and real-time display."""

import json
from pathlib import Path

import pytest
from homeassistant.core import Event
from homeassistant.exceptions import HomeAssistantError
from test_config_runtime import options_flow
from test_hydrus_mqtt_diagnostics import running
from test_notification_runtime import configure

from custom_components.water_leak_detection import async_setup
from custom_components.water_leak_detection.const import DOMAIN, DetectorKind, DetectorPhase
from custom_components.water_leak_detection.duration import human_duration
from custom_components.water_leak_detection.sensor import (
    ActiveEventDurationSensor,
    WaterLeakStatusSensor,
)


@pytest.mark.parametrize(
    "seconds,de,en",
    [
        (0, "0 Sekunden", "0 seconds"),
        (1, "1 Sekunde", "1 second"),
        (45, "45 Sekunden", "45 seconds"),
        (60, "1 Minute", "1 minute"),
        (125, "2 Minuten", "2 minutes"),
        (3600, "1 Stunde", "1 hour"),
        (6043, "1 Stunde 40 Minuten", "1 hour 40 minutes"),
        (90000, "1 Tag 1 Stunde", "1 day 1 hour"),
        (172800, "2 Tage", "2 days"),
    ],
)
def test_human_duration_examples(seconds, de, en):
    assert human_duration(seconds, "de") == de
    assert human_duration(seconds, "de-CH") == de
    assert human_duration(seconds, "en") == en


async def ack_manager(hass, entry, clock):
    configure(hass, entry, clock, "phone")
    # Use automatic report evidence for the actual 60-second radio cadence.
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, "source_max_age_seconds": 0, "shutoff_low": True}
    )
    calls = []

    async def notify(call):
        calls.append(call.data)

    hass.services.async_register("notify", "mobile_app_phone", notify)
    transport, manager = await running(hass, entry, clock)
    event_id = manager.engine.runtimes[DetectorKind.LOW_FLOW].event_id
    await hass.async_block_till_done()
    return transport, manager, event_id, calls


@pytest.mark.parametrize("tracker", ["home", "away", "unavailable", "unknown"])
async def test_native_service_requires_current_home_and_preserves_safety(
    runtime_hass, runtime_entry, measurement_clock, tracker
):
    transport, manager, event_id, _ = await ack_manager(
        runtime_hass, runtime_entry, measurement_clock
    )
    await async_setup(runtime_hass, {})
    runtime_hass.states.async_set("device_tracker.phone", tracker)
    payload = {"event_id": event_id, "recipient_id": "phone", "recipient_token": "token_phone"}
    if tracker == "home":
        await runtime_hass.services.async_call(DOMAIN, "acknowledge_event", payload, blocking=True)
        assert manager.notifications.state_for(event_id).globally_acknowledged
        disk = json.loads(Path(manager._store.path).read_text())["data"]
        assert disk["acknowledgements"][event_id]["globally_acknowledged"]
    else:
        with pytest.raises(HomeAssistantError):
            await runtime_hass.services.async_call(
                DOMAIN, "acknowledge_event", payload, blocking=True
            )
        assert not manager.notifications.state_for(event_id).globally_acknowledged
    assert manager.alarm_active and manager.shutoff_request
    assert manager.engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.ACTIVE
    # ACK does not prevent the physical reset when actual evidence later arrives.
    await transport.telegram(0)
    for _ in range(3):
        await transport.telegram(0)
    assert not manager.alarm_active


@pytest.mark.parametrize("damage", ["token", "recipient", "event", "permission", "home"])
async def test_options_and_mobile_validate_current_recipient_configuration(
    runtime_hass, runtime_entry, measurement_clock, damage
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    raw = dict(runtime_entry.options["notification_recipients"][0])
    original_action = f"WLD|ACK_ALL|{runtime_entry.entry_id}|{event_id}|phone|token_phone"
    if damage == "token":
        raw["token"] = "rotated"
    elif damage == "recipient":
        raw["id"] = "replaced"
    elif damage == "permission":
        raw["allow_global_ack"] = False
    elif damage == "home":
        runtime_hass.states.async_set("device_tracker.phone", "away")
    runtime_hass.config_entries.async_update_entry(
        runtime_entry, options={**runtime_entry.options, "notification_recipients": [raw]}
    )
    if damage == "event":
        original_action = original_action.replace(event_id, "old_event")
    # No apply_options call: stale cached permissions must not authorize a new action.
    await manager.notifications._async_mobile_action(
        Event("mobile_app_notification_action", {"action": original_action})
    )
    assert not manager.notifications.state_for(event_id).globally_acknowledged
    assert manager.alarm_active and manager.shutoff_request


async def test_admin_options_ack_is_usable_and_does_not_change_configuration(
    runtime_hass, runtime_entry, measurement_clock
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    flow = options_flow(runtime_hass, runtime_entry)
    form = await flow.async_step_acknowledgements()
    before = dict(runtime_entry.options)
    values = form["data_schema"]({"event_id": event_id, "recipient_id": "phone"})
    result = await flow.async_step_acknowledgements(values)
    assert result["step_id"] == "init"
    assert manager.notifications.state_for(event_id).globally_acknowledged
    assert dict(runtime_entry.options) == before
    assert manager.alarm_active and manager.shutoff_request
    assert "recipient_token" not in form["data_schema"].schema


async def test_ticks_reports_duplicate_start_and_restart_do_not_repeat_accepted_route(
    runtime_hass, runtime_entry, measurement_clock
):
    transport, manager, event_id, calls = await ack_manager(
        runtime_hass, runtime_entry, measurement_clock
    )
    assert len(calls) == 1
    for _ in range(20):
        await transport.telegram(0.250)
        await manager._async_tick(measurement_clock.utcnow())
        await manager.notifications._async_leak_started(
            Event(
                "duplicate_start",
                {
                    "config_entry_id": runtime_entry.entry_id,
                    "event_id": event_id,
                    "type": "low_flow",
                },
            )
        )
    await runtime_hass.async_block_till_done()
    assert len(calls) == 1
    await manager.async_unload()
    from custom_components.water_leak_detection.manager import WaterLeakManager

    restored = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    await restored.async_setup()
    await restored.notifications.async_retry_pending()
    await runtime_hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0]["data"]["wld_event_id"] == event_id


async def test_duration_numeric_state_and_source_diagnostics_do_not_mature_on_ticks(
    runtime_hass, runtime_entry, measurement_clock
):
    transport, manager = await running(runtime_hass, runtime_entry, measurement_clock)
    duration = ActiveEventDurationSensor(manager)
    seconds = duration.native_value
    assert seconds == 1800  # This is event age from monitoring, not time since ACTIVE.
    await transport.telegram(0)
    measurement_clock.advance(125)
    await manager._async_tick(measurement_clock.utcnow())
    assert duration.native_value == seconds + 60 + 125
    attrs = duration.extra_state_attributes
    assert attrs["duration_human_de"] == human_duration(duration.native_value, "de")
    assert attrs["event_id"]
    assert attrs["started_at"] != attrs["active_since"]
    diagnostics = WaterLeakStatusSensor(manager).extra_state_attributes
    assert set(diagnostics["hydraulic_detectors"]) == {kind.value for kind in DetectorKind}
    source = diagnostics["measurement_diagnostics"]
    assert source["low_reset_confirmed_seconds"] == 0
    assert source["low_reset_required_seconds"] == 180
    assert source["last_valid_observation_age_seconds"] == 125
    assert source["source_max_age_seconds_stored"] is None
    assert source["source_max_age_seconds_effective"] == 0


@pytest.mark.parametrize("permission", [False, "true", "false", 1, None])
async def test_malformed_global_permission_cannot_authorize_native_ack(
    runtime_hass, runtime_entry, measurement_clock, permission
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    raw = {
        **runtime_entry.options["notification_recipients"][0],
        "allow_global_ack": permission,
        "name": "Changed recipient configuration",
    }
    # HA treats unchanged True and 1 as equal: the changed name ensures an
    # actual malformed saved option, not a no-op update of the original bool.
    runtime_hass.config_entries.async_update_entry(
        runtime_entry, options={**runtime_entry.options, "notification_recipients": [raw]}
    )
    assert not await manager.async_acknowledge_event(event_id, "phone", "token_phone")
    assert manager.alarm_active and manager.shutoff_request


async def test_options_ack_rejects_event_ended_after_form_was_opened(
    runtime_hass, runtime_entry, measurement_clock
):
    transport, manager, event_id, _ = await ack_manager(
        runtime_hass, runtime_entry, measurement_clock
    )
    flow = options_flow(runtime_hass, runtime_entry)
    await flow.async_step_acknowledgements()
    await transport.telegram(0)
    for _ in range(3):
        await transport.telegram(0)
    result = await flow.async_step_acknowledgements({"event_id": event_id, "recipient_id": "phone"})
    assert result["errors"]["base"] == "acknowledgement_rejected"
    assert event_id not in manager.notifications.acknowledgements
