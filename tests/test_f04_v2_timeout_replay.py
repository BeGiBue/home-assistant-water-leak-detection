import json
from datetime import timedelta

import pytest
from homeassistant.components.mqtt.models import ReceiveMessage
from test_hydrus_mqtt_diagnostics import TOPIC, running


@pytest.mark.parametrize(
    "outage,age,max_age",
    [
        ("timeout", 299, 120),
        ("timeout", 300, 120),
        ("timeout", 299, 180),
        ("timeout", 300, 180),
        ("unknown", 299, 120),
        ("unavailable", 299, 120),
        ("timeout", 301, 120),
    ],
)
async def test_outage_excludes_pre_outage_originals(
    runtime_hass, runtime_entry, measurement_clock, outage, age, max_age
):
    runtime_hass.config_entries.async_update_entry(
        runtime_entry,
        options={
            "source_max_age_seconds": max_age,
            "source_gap_policy_explicit": True,
            "shutoff_low": True,
        },
    )
    t, m = await running(runtime_hass, runtime_entry, measurement_clock)
    assert m.alarm_active and m.shutoff_request
    last = m.timer_now
    measurement_clock.advance(400)
    if outage == "timeout":
        await m._async_tick(measurement_clock.utcnow())
    else:
        runtime_hass.states.async_set("sensor.flow", outage)
        await runtime_hass.async_block_till_done()
    assert not m.source_available
    for i in range(4):
        if i:
            measurement_clock.advance(60)
        original = last + timedelta(seconds=400 - age + 60 * i)
        msg = ReceiveMessage(
            TOPIC,
            json.dumps({"flow_m3h": 0, "total_m3": t.total_m3, "timestamp": original.isoformat()}),
            1,
            False,
            TOPIC,
            measurement_clock.monotonic(),
        )
        t.sensor._message_callback(
            t.sensor._state_message_received,
            {"_attr_native_value", "_attr_last_reset", "_expired"},
            msg,
        )
        t.data.state_write_requests.process_write_state_requests(msg)
        await runtime_hass.async_block_till_done()
    print(
        "TIMEOUT",
        outage,
        age,
        max_age,
        "alarm",
        m.alarm_active,
        "shutoff",
        m.shutoff_request,
        "provenance",
        m._mqtt_provenance.reason,
    )
    assert m.alarm_active, "Pre-outage queued radio measurements must not clear ACTIVE Low"
    assert m.shutoff_request


async def test_genuinely_post_timeout_zero_measurements_reset(
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
    t, m = await running(runtime_hass, runtime_entry, measurement_clock)
    measurement_clock.advance(400)
    await m._async_tick(measurement_clock.utcnow())
    assert not m.source_available and m.alarm_active
    await t.telegram(0, 0)
    for _ in range(3):
        await t.telegram(0, 60)
    assert not m.alarm_active and not m.shutoff_request
