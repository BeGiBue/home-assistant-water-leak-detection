import json
from datetime import timedelta

import pytest
from homeassistant.components.mqtt.models import ReceiveMessage
from test_hydrus_mqtt_diagnostics import TOPIC, HydrusTransport, running

from custom_components.water_leak_detection.const import DOMAIN, DetectorKind, DetectorPhase
from custom_components.water_leak_detection.manager import WaterLeakManager


async def deliver(t, clock, flow, physical_seconds, latency, previous_latency):
    clock.advance(physical_seconds + latency - previous_latency)
    original = clock.utcnow() - timedelta(seconds=latency)
    t.total_m3 += flow * physical_seconds / 3600
    msg = ReceiveMessage(
        TOPIC,
        json.dumps(
            {
                "flow_m3h": flow,
                "total_m3": t.total_m3,
                "timestamp": original.isoformat().replace("+00:00", "Z"),
            }
        ),
        0,
        False,
        TOPIC,
        clock.monotonic(),
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
    await t.hass.async_block_till_done()


@pytest.mark.parametrize("jitter", [0, 0.001, 0.01])
async def test_genuine_zero_measurements_allow_reset_despite_transport_jitter(
    runtime_hass, runtime_entry, measurement_clock, jitter
):
    t, m = await running(runtime_hass, runtime_entry, measurement_clock)
    for i, period in enumerate([60, 103, 132, 60]):
        await deliver(t, measurement_clock, 0, period, jitter * i, jitter * max(i - 1, 0))
    print(
        "QUIET",
        jitter,
        "active",
        m.alarm_active,
        "gap",
        m.engine.last_evidence_gap,
        "quiet",
        m.source_diagnostics()["low_reset_confirmed_seconds"],
    )
    assert not m.alarm_active, (
        "Three physical minutes of accepted zero measurements must reset "
        "despite millisecond delivery jitter"
    )


@pytest.mark.parametrize("jitter", [0, 0.001, 0.01])
async def test_genuine_burst_measurements_confirm_despite_transport_jitter(
    runtime_hass, runtime_entry, measurement_clock, jitter
):
    t = HydrusTransport(runtime_hass, runtime_entry, measurement_clock, True)
    await t.telegram(0, 0)
    m = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data.setdefault(DOMAIN, {})[runtime_entry.entry_id] = m
    await m.async_setup()
    for i in range(4):
        await deliver(t, measurement_clock, 5, 60, jitter * i, jitter * max(i - 1, 0))
    burst = m.engine.runtimes[DetectorKind.BURST_LEAK]
    print(
        "BURST",
        jitter,
        "phase",
        burst.phase.value,
        "gap",
        m.engine.last_evidence_gap,
        "source",
        m.source_available,
        "provenance",
        m._mqtt_provenance.reason,
    )
    assert burst.phase is DetectorPhase.ACTIVE, (
        "Verified original high flow must not restart Burst solely due to transport jitter"
    )


@pytest.mark.parametrize("variation", [-0.01, 0.01])
async def test_quiet_reset_needs_exact_physical_180_seconds(
    runtime_hass, runtime_entry, measurement_clock, variation
):
    transport, manager = await running(runtime_hass, runtime_entry, measurement_clock)
    await deliver(transport, measurement_clock, 0, 60, 2, 0)
    await deliver(transport, measurement_clock, 0, 179, 2 + variation, 2)
    assert manager.alarm_active
    assert not manager.engine.last_evidence_gap
    await deliver(transport, measurement_clock, 0, 1, 2, 2 + variation)
    assert not manager.alarm_active
    assert not manager.engine.last_evidence_gap


@pytest.mark.parametrize("variation", [-0.01, 0.01])
async def test_burst_needs_exact_physical_30_seconds(
    runtime_hass, runtime_entry, measurement_clock, variation
):
    transport = HydrusTransport(runtime_hass, runtime_entry, measurement_clock, True)
    await transport.telegram(0, 0)
    manager = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data.setdefault(DOMAIN, {})[runtime_entry.entry_id] = manager
    await manager.async_setup()
    await deliver(transport, measurement_clock, 5, 60, 2, 0)
    await deliver(transport, measurement_clock, 5, 29, 2 + variation, 2)
    assert manager.engine.runtimes[DetectorKind.BURST_LEAK].phase is DetectorPhase.MONITORING
    assert not manager.engine.last_evidence_gap
    await deliver(transport, measurement_clock, 5, 1, 2, 2 + variation)
    assert manager.engine.runtimes[DetectorKind.BURST_LEAK].phase is DetectorPhase.ACTIVE
    assert not manager.engine.last_evidence_gap
