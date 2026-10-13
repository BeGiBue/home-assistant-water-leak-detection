from datetime import timedelta

import pytest
from test_hydrus_mqtt_diagnostics import running


@pytest.mark.parametrize("latency", [0.005, 1.0, 5.0])
async def test_receipt_clock_survives_variable_real_store_latency(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch, latency
):
    t, m = await running(runtime_hass, runtime_entry, measurement_clock)
    original = m._store.async_save
    delays = iter([latency, latency / 5, latency / 2, 0, latency])

    async def delayed(data):
        measurement_clock.advance(next(delays, 0))
        await original(data)

    monkeypatch.setattr(m._store, "async_save", delayed)
    start = measurement_clock.seconds
    for elapsed in [0, 60, 120, 175, 180]:
        await t.telegram(0, start + elapsed - measurement_clock.seconds)
        assert m.engine.last_sample_at == measurement_clock.origin + timedelta(
            seconds=start + elapsed
        )
        assert not m.engine.last_evidence_gap
        if elapsed < 180:
            assert m.alarm_active
    assert not m.alarm_active


@pytest.mark.parametrize("max_age", [120, 180])
async def test_direct_gap_new_originals_are_not_backdated(
    runtime_hass, runtime_entry, measurement_clock, max_age
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
    await t.telegram(0, 400)
    assert m.alarm_active and m.shutoff_request
    assert m.source_diagnostics()["low_reset_confirmed_seconds"] == 0
    await t.telegram(0, 179 if max_age == 180 else 120)
    assert m.alarm_active
