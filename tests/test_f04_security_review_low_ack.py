"""Independent HA/MQTT boundary tests against current production modules."""

import json
from pathlib import Path

import pytest
from aiohttp.test_utils import make_mocked_request
from homeassistant.auth.models import User
from homeassistant.components.config.config_entries import OptionManagerFlowIndexView
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers.entity_platform import async_get_platforms
from homeassistant.util.file import WriteError
from test_f04_security_review_controls import setup
from test_hydrus_mqtt_diagnostics import HydrusTransport

from custom_components.water_leak_detection.const import DOMAIN, DetectorKind, DetectorPhase
from custom_components.water_leak_detection.duration import human_duration
from custom_components.water_leak_detection.manager import WaterLeakManager
from custom_components.water_leak_detection.sensor import (
    ActiveEventDurationSensor,
    WaterLeakStatusSensor,
)


async def low(hass, entry, clock, force=True):
    hass.config_entries.async_update_entry(entry, options={**entry.options, "shutoff_low": True})
    t = HydrusTransport(hass, entry, clock, force)
    await t.telegram(0.250, 0)
    m = WaterLeakManager(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = m
    await m.async_setup()
    for i in range(30):
        await t.telegram(0.250 if i % 2 else 0.251, 60)
    assert m.engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.ACTIVE
    return t, m


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("expiry", [None, 45, 150])
@pytest.mark.parametrize("intervals", [(60, 60, 60), (30, 120, 30), (90, 90)])
async def test_mqtt_identical_null_cadence_matrix(
    runtime_hass, runtime_entry, measurement_clock, force, expiry, intervals
):
    t, m = await low(runtime_hass, runtime_entry, measurement_clock, force)
    if expiry:
        t.sensor._setup_from_config({**t.sensor._config, "expire_after": expiry})
    await t.telegram(0, 60)
    for sec in intervals:
        if expiry and sec > expiry:
            measurement_clock.advance(expiry + 0.001)
            t.sensor._value_is_expired()
            await runtime_hass.async_block_till_done()
            await t.telegram(0, sec - expiry - 0.001)
        else:
            await t.telegram(0, sec)
    expected = force and (expiry is None or expiry >= max(intervals))
    assert (m.engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.IDLE) == expected
    if t.sensor._expiration_trigger:
        t.sensor._expiration_trigger()
        t.sensor._expiration_trigger = None


@pytest.mark.parametrize("force", [False, True])
async def test_last_changed_updated_reported_actual_mqtt(
    runtime_hass, runtime_entry, measurement_clock, force
):
    t = HydrusTransport(runtime_hass, runtime_entry, measurement_clock, force)
    await t.telegram(0, 0)
    first = runtime_hass.states.get("sensor.flow")
    initial = (first.last_changed, first.last_updated, first.last_reported)
    await t.telegram(0, 60)
    last = runtime_hass.states.get("sensor.flow")
    assert (last.last_changed != initial[0]) == force
    assert (last.last_reported != initial[2]) == force
    assert (last.last_updated != initial[1]) == force


@pytest.mark.parametrize("flow", [0, 0.250])
async def test_no_packet_ticks_total_only_no_new_interval(
    runtime_hass, runtime_entry, measurement_clock, flow
):
    t, m = await low(runtime_hass, runtime_entry, measurement_clock)
    await t.telegram(flow, 60)
    event = m.engine.runtimes[DetectorKind.LOW_FLOW].event_id
    for _ in range(20):
        measurement_clock.advance(60)
        runtime_hass.states.async_set(
            "sensor.total", str(t.total_m3), {"unit_of_measurement": "m³"}
        )
        await runtime_hass.async_block_till_done()
        await m._async_tick(measurement_clock.utcnow())
    assert m.engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.ACTIVE
    assert m.engine.runtimes[DetectorKind.LOW_FLOW].event_id == event
    assert m.source_diagnostics()["low_reset_confirmed_seconds"] == 0


@pytest.mark.parametrize("retain", [False, True])
@pytest.mark.parametrize("limit", [0, 120])
async def test_old_radio_zero_replayed_must_not_clear_active(
    runtime_hass, runtime_entry, measurement_clock, retain, limit
):
    t, m = await low(runtime_hass, runtime_entry, measurement_clock)
    await m.async_update_options(
        {
            **runtime_entry.options,
            "source_max_age_seconds": limit,
            "source_gap_policy_explicit": True,
        }
    )
    assert m.shutoff_request
    # No new radio measurement: the exact same old JSON is re-delivered four times.
    packet = json.dumps({"flow_m3h": 0, "total_m3": 123.456, "timestamp": "2026-10-07T00:00:00Z"})
    for sec in [0, 60, 60, 60]:
        measurement_clock.advance(sec)
        msg = ReceiveMessage(
            "wmbusmeters/hydrus",
            packet,
            0,
            retain,
            "wmbusmeters/hydrus",
            measurement_clock.utcnow().timestamp(),
        )
        t.sensor._message_callback(
            t.sensor._state_message_received,
            {"_attr_native_value", "_attr_last_reset", "_expired"},
            msg,
        )
        t.total_sensor._message_callback(
            t.total_sensor._state_message_received,
            {"_attr_native_value", "_attr_last_reset", "_expired"},
            msg,
        )
        t.data.state_write_requests.process_write_state_requests(msg)
        await runtime_hass.async_block_till_done()
    assert m.engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.ACTIVE, (
        m.source_diagnostics(),
        m.shutoff_request,
    )


@pytest.mark.parametrize("shift", [-0.5, -3600, -172800])
async def test_clock_rollback_uses_monotonic_reset_and_duration(
    runtime_hass, runtime_entry, measurement_clock, shift
):
    t, m = await low(runtime_hass, runtime_entry, measurement_clock)
    event = m.engine.runtimes[DetectorKind.LOW_FLOW].event_id
    before = m.event_elapsed_seconds(event)
    measurement_clock.wall_shift += shift
    await t.telegram(0, 0)
    await t.telegram(0, 179)
    assert m.engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.ACTIVE
    assert m.event_elapsed_seconds(event) == before + 179
    await t.telegram(0, 1)
    assert m.engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.IDLE


async def test_ack_write_failure_must_not_leave_uncommitted_ack(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch
):
    m = await setup(runtime_hass, runtime_entry, measurement_clock)
    event = m.external.sources["a"].event_id
    await m._async_save()
    before = Path(m._store.path).read_bytes()

    def fail(*args):
        raise WriteError("independent ack write failure")

    with monkeypatch.context() as patch:
        patch.setattr(m._store, "_write_prepared_data", fail)
        with pytest.raises(WriteError):
            await m.async_acknowledge_event(event, "phone", "token")
    assert Path(m._store.path).read_bytes() == before
    assert m.alarm_active and m.shutoff_request
    assert not m.notifications.state_for(event).globally_acknowledged


async def test_options_endpoint_nonadmin_rejected_by_real_ha_decorator(runtime_hass):
    view = OptionManagerFlowIndexView(runtime_hass.config_entries.options)
    request = make_mocked_request("POST", "/api/config/config_entries/options/flow")
    request["hass_user"] = User(name="Normal user", perm_lookup=None, groups=[], is_active=True)
    with pytest.raises(Unauthorized):
        await view.post(request)


async def test_ack_restart_new_event_and_two_active_sources(
    runtime_hass, runtime_entry, measurement_clock
):
    m = await setup(runtime_hass, runtime_entry, measurement_clock)
    runtime_hass.states.async_set("binary_sensor.b", "on")
    await runtime_hass.async_block_till_done()
    ids = list(m.active_events())
    for event in ids:
        assert await m.async_acknowledge_event(event, "phone", "token")
    assert m.alarm_active and m.shutoff_request
    runtime_hass.states.async_set("binary_sensor.a", "on")
    await runtime_hass.async_block_till_done()
    await m.async_unload()
    restored = WaterLeakManager(runtime_hass, runtime_entry)
    restored.notifications._async_common_translations = m.notifications._async_common_translations
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    await restored.async_setup()
    assert all(restored.notifications.state_for(e).globally_acknowledged for e in ids)
    runtime_hass.states.async_set("binary_sensor.a", "off")
    runtime_hass.states.async_set("binary_sensor.a", "on")
    await runtime_hass.async_block_till_done()
    fresh = restored.external.sources["a"].event_id
    assert fresh not in ids
    assert not restored.notifications.state_for(fresh).globally_acknowledged
    assert restored.alarm_active and restored.shutoff_request


@pytest.mark.parametrize(
    "seconds,de,en",
    [
        (45, "45 Sekunden", "45 seconds"),
        (125, "2 Minuten", "2 minutes"),
        (6043, "1 Stunde 40 Minuten", "1 hour 40 minutes"),
        (90000, "1 Tag 1 Stunde", "1 day 1 hour"),
        (-1, "0 Sekunden", "0 seconds"),
        (float("inf"), "0 Sekunden", "0 seconds"),
    ],
)
def test_duration_examples(seconds, de, en):
    assert human_duration(seconds, "de") == de
    assert human_duration(seconds, "en") == en


async def test_external_display_event_duration_must_match(
    runtime_hass, runtime_entry, measurement_clock
):
    m = await setup(runtime_hass, runtime_entry, measurement_clock)
    measurement_clock.advance(125)
    status = WaterLeakStatusSensor(m)
    duration = ActiveEventDurationSensor(m)
    assert status.native_value == "external_leak"
    assert duration.extra_state_attributes["event_id"] == m.external.sources["a"].event_id
    assert duration.native_value == 125


async def test_actual_published_diagnostics_age_updates_on_ha_poll(
    runtime_hass, runtime_entry, measurement_clock
):
    from homeassistant import loader
    from homeassistant.helpers import entity_registry as er

    import custom_components

    loader.async_setup(runtime_hass)
    runtime_hass.data[loader.DATA_INTEGRATIONS][DOMAIN] = loader.Integration.resolve_from_root(
        runtime_hass, custom_components, DOMAIN
    )
    runtime_hass.states.async_set("sensor.flow", "0", {"unit_of_measurement": "L/h"})
    assert await runtime_hass.config_entries.async_setup(runtime_entry.entry_id)
    await runtime_hass.async_block_till_done()
    m = runtime_hass.data[DOMAIN][runtime_entry.entry_id]
    status_id = next(
        e.entity_id
        for e in er.async_entries_for_config_entry(
            er.async_get(runtime_hass), runtime_entry.entry_id
        )
        if e.unique_id.endswith("_status")
    )
    measurement_clock.advance(120)
    await m._async_tick(measurement_clock.utcnow())
    await runtime_hass.async_block_till_done()
    # Fake measurement time does not advance HA's platform scheduler.
    for platform in async_get_platforms(runtime_hass, DOMAIN):
        if platform.domain == "sensor":
            await platform._async_update_entity_states()
    await runtime_hass.async_block_till_done()
    published = runtime_hass.states.get(status_id).attributes["measurement_diagnostics"][
        "last_valid_observation_age_seconds"
    ]
    live = m.source_diagnostics()["last_valid_observation_age_seconds"]
    await runtime_hass.config_entries.async_unload(runtime_entry.entry_id)
    assert published == live == 120, (published, live)


async def test_old_positive_packet_repeated_must_not_create_active(
    runtime_hass, runtime_entry, measurement_clock
):
    t = HydrusTransport(runtime_hass, runtime_entry, measurement_clock, True)
    await t.telegram(0, 0)
    m = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data.setdefault(DOMAIN, {})[runtime_entry.entry_id] = m
    await m.async_setup()
    packet = json.dumps(
        {"flow_m3h": 0.250, "total_m3": 123.456, "timestamp": "2026-10-06T00:00:00Z"}
    )
    for i in range(31):
        measurement_clock.advance(0 if i == 0 else 60)
        msg = ReceiveMessage(
            "wmbusmeters/hydrus",
            packet,
            0,
            True,
            "wmbusmeters/hydrus",
            measurement_clock.utcnow().timestamp(),
        )
        for sensor in (t.sensor, t.total_sensor):
            sensor._message_callback(
                sensor._state_message_received,
                {"_attr_native_value", "_attr_last_reset", "_expired"},
                msg,
            )
        t.data.state_write_requests.process_write_state_requests(msg)
        await runtime_hass.async_block_till_done()
    assert m.engine.runtimes[DetectorKind.LOW_FLOW].phase is not DetectorPhase.ACTIVE


async def test_actual_published_duration_updates_via_ha_poll_without_measurements(
    runtime_hass, runtime_entry, measurement_clock
):
    from homeassistant import loader
    from homeassistant.helpers import entity_registry as er

    import custom_components

    loader.async_setup(runtime_hass)
    runtime_hass.data[loader.DATA_INTEGRATIONS][DOMAIN] = loader.Integration.resolve_from_root(
        runtime_hass, custom_components, DOMAIN
    )
    runtime_hass.states.async_set("sensor.flow", "250", {"unit_of_measurement": "L/h"})
    assert await runtime_hass.config_entries.async_setup(runtime_entry.entry_id)
    await runtime_hass.async_block_till_done()
    m = runtime_hass.data[DOMAIN][runtime_entry.entry_id]
    measurement_clock.advance(1800)
    runtime_hass.states.async_set("sensor.flow", "250", {"unit_of_measurement": "L/h"})
    await runtime_hass.async_block_till_done()
    assert m.engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.ACTIVE
    duration_id = next(
        e.entity_id
        for e in er.async_entries_for_config_entry(
            er.async_get(runtime_hass), runtime_entry.entry_id
        )
        if e.unique_id.endswith("_active_event_duration")
    )
    measurement_clock.advance(120)
    await m._async_tick(measurement_clock.utcnow())
    await runtime_hass.async_block_till_done()
    for platform in async_get_platforms(runtime_hass, DOMAIN):
        if platform.domain == "sensor":
            await platform._async_update_entity_states()
    await runtime_hass.async_block_till_done()
    published = int(runtime_hass.states.get(duration_id).state)
    live = ActiveEventDurationSensor(m).native_value
    await runtime_hass.config_entries.async_unload(runtime_entry.entry_id)
    assert published == live == 1920, (published, live)


@pytest.mark.parametrize("invalid_token", [None, False, True])
async def test_nonstring_saved_token_must_not_become_guessable_ack_credential(
    runtime_hass, runtime_entry, measurement_clock, invalid_token
):
    m = await setup(runtime_hass, runtime_entry, measurement_clock)
    event = m.external.sources["a"].event_id
    recipients = [
        {**r, "token": invalid_token} for r in runtime_entry.options["notification_recipients"]
    ]
    runtime_hass.config_entries.async_update_entry(
        runtime_entry, options={**runtime_entry.options, "notification_recipients": recipients}
    )
    # The stored capability is invalid, not the printable guessed string.
    accepted = await m.async_acknowledge_event(event, "phone", str(invalid_token))
    assert m.alarm_active and m.shutoff_request
    assert not accepted
