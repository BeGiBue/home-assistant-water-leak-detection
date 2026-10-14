"""Additional production regressions for the seven independent review findings."""

import asyncio
import json
from pathlib import Path

import pytest
from homeassistant.core import Event
from homeassistant.util.file import WriteError
from test_f04_security_review_controls import setup
from test_hydrus_mqtt_diagnostics import running

from custom_components.water_leak_detection.const import DOMAIN, EVENT_ACKNOWLEDGED
from custom_components.water_leak_detection.manager import WaterLeakManager
from custom_components.water_leak_detection.notifications import NotificationRecipient
from custom_components.water_leak_detection.sensor import ActiveEventDurationSensor


@pytest.mark.parametrize("token", [None, False, True, 0, 1, [], {}, "", "  "])
def test_invalid_tokens_rejected_for_all_authorization_paths(token):
    raw = dict(
        id="phone",
        name="Phone",
        notify_service="notify.phone",
        tracker_entity="device_tracker.phone",
        token=token,
    )
    assert NotificationRecipient.from_dict(raw) is None


async def test_ack_private_until_actual_write_then_retry(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch
):
    m = await setup(runtime_hass, runtime_entry, measurement_clock)
    event = m.external.sources["a"].event_id
    await m._async_save()
    before = Path(m._store.path).read_bytes()
    successes = []
    runtime_hass.bus.async_listen(EVENT_ACKNOWLEDGED, lambda e: successes.append(e.data))
    entered, release = asyncio.Event(), asyncio.Event()
    save = m._store.async_save

    async def fail(data):
        entered.set()
        await release.wait()
        raise WriteError("controlled ACK failure")

    with monkeypatch.context() as patch:
        patch.setattr(m._store, "async_save", fail)
        task = asyncio.create_task(m.async_acknowledge_event(event, "phone", "token"))
        await entered.wait()
        assert not m.notifications.state_for(event).globally_acknowledged
        assert m.alarm_active and m.shutoff_request
        assert not successes
        release.set()
        with pytest.raises(WriteError):
            await task
    assert Path(m._store.path).read_bytes() == before
    assert not m.notifications.state_for(event).globally_acknowledged
    assert not successes
    assert await m.async_acknowledge_event(event, "phone", "token")
    await runtime_hass.async_block_till_done()
    assert len(successes) == 1
    assert m.alarm_active and m.shutoff_request
    assert m._store.async_save == save


async def test_external_duration_restart_and_rollback(
    runtime_hass, runtime_entry, measurement_clock
):
    m = await setup(runtime_hass, runtime_entry, measurement_clock)
    event = m.external.sources["a"].event_id
    measurement_clock.advance(125)
    assert ActiveEventDurationSensor(m).native_value == 125
    await m.async_unload()
    measurement_clock.advance(3600)
    measurement_clock.wall_shift -= 172800
    restored = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    restored.notifications._async_common_translations = m.notifications._async_common_translations
    await restored.async_setup()
    assert restored.display_event()["event_id"] == event
    assert ActiveEventDurationSensor(restored).native_value == 125
    measurement_clock.advance(60)
    assert ActiveEventDurationSensor(restored).native_value == 185


@pytest.mark.parametrize(
    "field,value",
    [
        ("timestamp", None),
        ("timestamp", False),
        ("timestamp", "bad"),
        ("timestamp", "2099-01-01T00:00:00Z"),
        ("timestamp", "2026-10-06T00:00:00Z"),
    ],
)
async def test_invalid_original_measurement_breaks_quiet_and_preserves_alarm(
    runtime_hass, runtime_entry, measurement_clock, field, value
):
    from homeassistant.components.mqtt.models import ReceiveMessage

    t, m = await running(runtime_hass, runtime_entry, measurement_clock)
    await t.telegram(0)
    await t.telegram(0, 120)
    event = m.display_event()["event_id"]
    measurement_clock.advance(60)
    payload = {"flow_m3h": 0, "total_m3": t.total_m3, field: value}
    msg = ReceiveMessage(
        "wmbusmeters/hydrus",
        json.dumps(payload),
        1,
        False,
        "wmbusmeters/hydrus",
        measurement_clock.monotonic(),
    )
    t.sensor._message_callback(
        t.sensor._state_message_received,
        {"_attr_native_value", "_attr_last_reset", "_expired"},
        msg,
    )
    t.data.state_write_requests.process_write_state_requests(msg)
    await runtime_hass.async_block_till_done()
    assert m.display_event()["event_id"] == event
    assert m.source_diagnostics()["low_reset_confirmed_seconds"] == 0
    assert not m.source_available
    await t.telegram(0, 0)
    assert m._flow_evidence.credited_seconds == 0
    await t.telegram(0, 179)
    assert m.display_event()["event_id"] == event
    await t.telegram(0, 1)
    assert not m.alarm_active


async def test_watermark_is_durable_and_cached_restart_is_not_evidence(
    runtime_hass, runtime_entry, measurement_clock
):
    t, m = await running(runtime_hass, runtime_entry, measurement_clock)
    stored = json.loads(Path(m._store.path).read_text())["data"]["mqtt_measurement_provenance"]
    assert stored == m._mqtt_provenance.to_dict()
    await m.async_unload()
    restored = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    await restored.async_setup()
    assert restored._flow_evidence.credited_seconds == 0
    assert restored._mqtt_provenance.reason == "replayed_or_out_of_order_measurement"
    assert restored.alarm_active
    await t.telegram(0, 60)
    assert restored._flow_evidence.credited_seconds == 0


async def test_external_notify_revocation_before_handoff(
    runtime_hass, runtime_entry, measurement_clock
):
    m = await setup(runtime_hass, runtime_entry, measurement_clock)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def translations():
        entered.set()
        await release.wait()
        return {}

    async def notify(call):
        calls.append(call)

    runtime_hass.services.async_register("notify", "mobile_app_phone", notify)
    m.notifications._async_common_translations = translations
    task = asyncio.create_task(m.async_request_external_reset_action("a", "phone"))
    await entered.wait()
    recipients = [
        {**r, "allow_external_reset": False}
        for r in runtime_entry.options["notification_recipients"]
    ]
    runtime_hass.config_entries.async_update_entry(
        runtime_entry, options={**runtime_entry.options, "notification_recipients": recipients}
    )
    release.set()
    assert not await task
    assert not calls
    assert m.alarm_active and m.shutoff_request


@pytest.mark.parametrize("version", [3, "damaged"])
async def test_recovery_remains_byte_identical_after_off_options_and_restart(
    runtime_hass, runtime_entry, measurement_clock, version
):
    from homeassistant.helpers import entity_registry as er

    er.async_get(runtime_hass).async_get_or_create(
        "binary_sensor", "test", "wet", suggested_object_id="wet"
    )
    runtime_hass.states.async_set("binary_sensor.wet", "on")
    runtime_hass.states.async_set("sensor.flow", "0", {"unit_of_measurement": "L/h"})
    runtime_hass.config_entries.async_update_entry(
        runtime_entry,
        options={"external_sensors": [{"id": "wet", "entity_id": "binary_sensor.wet"}]},
    )
    manager = WaterLeakManager(runtime_hass, runtime_entry)
    path = Path(manager._store.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": version,
                "minor_version": 1,
                "key": manager._store.key,
                "data": {"engine": {"active": "recover_me"}},
            }
        )
    )
    original = path.read_bytes()
    runtime_hass.data.setdefault(DOMAIN, {})[runtime_entry.entry_id] = manager
    await manager.async_setup()
    assert manager._storage_load_failed and not manager._migration_ready
    assert manager.alarm_active and manager.shutoff_request
    runtime_hass.states.async_set("binary_sensor.wet", "off")
    await runtime_hass.async_block_till_done()
    assert manager.alarm_active and manager.shutoff_request
    with pytest.raises(RuntimeError):
        await manager.async_update_options({**runtime_entry.options, "high_threshold_lph": 900})
    await manager._async_registry_updated(
        Event(
            "entity_registry_updated",
            {"entity_id": "binary_sensor.wet", "action": "update", "changes": {}},
        )
    )
    await manager._async_save()
    assert path.read_bytes() == original
    await manager.async_unload()
    restored = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    await restored.async_setup()
    assert restored._storage_load_failed and not restored._migration_ready
    assert restored.alarm_active and restored.shutoff_request
    assert path.read_bytes() == original


async def test_invalid_reading_consumes_origin_so_older_zero_cannot_reopen_chain(
    runtime_hass, runtime_entry, measurement_clock
):
    from datetime import timedelta

    from homeassistant.components.mqtt.models import ReceiveMessage

    transport, manager = await running(runtime_hass, runtime_entry, measurement_clock)
    measurement_clock.advance(60)
    last = measurement_clock.utcnow()

    async def deliver(flow, stamp):
        packet = json.dumps({"flow_m3h": flow, "timestamp": stamp.isoformat()})
        msg = ReceiveMessage(
            "wmbusmeters/hydrus",
            packet,
            1,
            False,
            "wmbusmeters/hydrus",
            measurement_clock.monotonic(),
        )
        transport.sensor._message_callback(
            transport.sensor._state_message_received,
            {"_attr_native_value", "_attr_last_reset", "_expired"},
            msg,
        )
        transport.data.state_write_requests.process_write_state_requests(msg)
        await runtime_hass.async_block_till_done()

    await deliver(-1, last)
    assert manager._mqtt_provenance.timestamp == last
    assert not manager.source_available
    for _ in range(4):
        measurement_clock.advance(60)
        await deliver(0, last - timedelta(seconds=1))
    assert manager.alarm_active
    assert manager.source_diagnostics()["low_reset_confirmed_seconds"] == 0


def test_provenance_binds_rendered_ha_units_not_native_units():
    from collections import deque
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from homeassistant.components.mqtt.models import ReceiveMessage
    from homeassistant.core import State

    from custom_components.water_leak_detection.mqtt_provenance import MqttProvenance

    now = datetime(2026, 10, 13, tzinfo=UTC)
    packet = ReceiveMessage(
        "meter/flow",
        json.dumps({"flow_m3h": 0.25, "timestamp": now.isoformat()}),
        0,
        False,
        "meter/flow",
        0,
    )
    # HA has converted the native 0.25 m³/h to the configured 250.0 L/h.
    entity = SimpleNamespace(native_value=0.25, state=250.0, _config={"state_topic": "meter/flow"})
    hass = SimpleNamespace(
        data={
            "sensor": SimpleNamespace(get_entity=lambda _: entity),
            "mqtt": SimpleNamespace(
                debug_info_entities={
                    "sensor.flow": {"subscriptions": {"meter/flow": {"messages": deque([packet])}}}
                }
            ),
        }
    )
    proof = MqttProvenance("generation")
    proof.bind_startup(now)
    assert proof.validate(hass, "sensor.flow", State("sensor.flow", "250.0"), now) == (now, None)
    assert proof.validate(hass, "sensor.flow", State("sensor.flow", "999"), now) is None


async def test_unknown_outage_excludes_pre_outage_original_measurements(
    runtime_hass, runtime_entry, measurement_clock
):
    from datetime import timedelta

    from homeassistant.components.mqtt.models import ReceiveMessage

    transport, manager = await running(runtime_hass, runtime_entry, measurement_clock)
    measurement_clock.advance(100)
    boundary = manager.timer_now
    runtime_hass.states.async_set("sensor.flow", "unavailable")
    await runtime_hass.async_block_till_done()
    assert manager._mqtt_provenance.started_at == boundary
    for _ in range(4):
        measurement_clock.advance(60)
        packet = json.dumps(
            {"flow_m3h": 0, "timestamp": (boundary - timedelta(seconds=1)).isoformat()}
        )
        msg = ReceiveMessage(
            "wmbusmeters/hydrus",
            packet,
            1,
            False,
            "wmbusmeters/hydrus",
            measurement_clock.monotonic(),
        )
        transport.sensor._message_callback(
            transport.sensor._state_message_received,
            {"_attr_native_value", "_attr_last_reset", "_expired"},
            msg,
        )
        transport.data.state_write_requests.process_write_state_requests(msg)
        await runtime_hass.async_block_till_done()
    assert manager.alarm_active
    assert manager.source_diagnostics()["low_reset_confirmed_seconds"] == 0
