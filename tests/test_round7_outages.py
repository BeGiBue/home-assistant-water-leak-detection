"""F05: same-source pauses preserve confirmed time, never unknown time."""

import pytest
from test_manager_runtime import start_manager
from test_round2_measurements import fresh

from custom_components.water_leak_detection.const import DetectorKind, DetectorPhase
from custom_components.water_leak_detection.engine import DetectorSettings

BANDS = [(DetectorKind.SLOW_LEAK, 7), (DetectorKind.LOW_FLOW, 200),
         (DetectorKind.HIGH_FLOW, 800)]
INVALID = ['unavailable', 'unknown', '-1', 'nan', 'inf', 'bad']


def settings(duration=3600):
    return DetectorSettings(
        # Keep Round7 focused on retained normal monitoring progress.
        low_stability_enabled=False,
        slow_detection_seconds=duration, low_detection_seconds=duration,
        high_detection_seconds=duration, high_volume_l=999999,
        slow_reset_seconds=300, low_reset_seconds=300, high_reset_seconds=300,
        burst_reset_seconds=300, shutoff_slow=True, shutoff_low=True, shutoff_high=True,
    )


async def pause(hass, manager, clock, invalid='unavailable', duration=600):
    previous = manager.engine.last_sample_at
    clock.advance(1)
    await fresh(hass, manager, clock, invalid)
    assert manager._flow_evidence.credited_seconds == 0
    assert manager.engine.last_sample_at == previous
    assert manager.engine.last_flow_lph is None
    for _ in range(3):
        clock.advance(duration / 3)
        await manager._async_tick(clock.utcnow())
        assert manager._flow_evidence.credited_seconds == 0
        assert manager.engine.last_sample_at == previous


@pytest.mark.parametrize('kind,flow', BANDS)
@pytest.mark.parametrize('invalid', INVALID)
@pytest.mark.parametrize('duration', [600, 30 * 86400])
async def test_f05_review_3480_seconds_survive_interruption_without_offline_credit(
    runtime_hass, runtime_entry, measurement_clock, kind, flow, invalid, duration
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, flow)
    manager.engine.update_settings(settings())
    runtime = manager.engine.runtimes[kind]
    for _ in range(29):
        measurement_clock.advance(120)
        await fresh(runtime_hass, manager, measurement_clock, flow)
    assert runtime.phase is DetectorPhase.MONITORING
    assert (manager.timer_now - runtime.started_at).total_seconds() == 3480
    await pause(runtime_hass, manager, measurement_clock, invalid, duration)
    assert runtime.phase is DetectorPhase.MONITORING
    await fresh(runtime_hass, manager, measurement_clock, flow)
    assert manager._flow_evidence.credited_seconds == 0
    assert (manager.timer_now - runtime.started_at).total_seconds() == 3480
    assert runtime.phase is DetectorPhase.MONITORING
    # Re-reading the returned state cannot shift its start a second time.
    started = runtime.started_at
    await manager._async_tick(measurement_clock.utcnow())
    assert runtime.started_at == started
    measurement_clock.advance(120)
    await fresh(runtime_hass, manager, measurement_clock, flow)
    assert (manager.timer_now - runtime.started_at).total_seconds() == 3600
    assert runtime.phase is DetectorPhase.ACTIVE


@pytest.mark.parametrize('kind,flow', BANDS)
async def test_f05_many_early_outages_cannot_prevent_event(
    runtime_hass, runtime_entry, measurement_clock, kind, flow
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, flow)
    manager.engine.update_settings(settings())
    runtime = manager.engine.runtimes[kind]
    for index in range(30):
        measurement_clock.advance(120)
        await fresh(runtime_hass, manager, measurement_clock, flow)
        assert (manager.timer_now - runtime.started_at).total_seconds() == (index + 1) * 120
        if runtime.phase is DetectorPhase.ACTIVE:
            break
        await pause(runtime_hass, manager, measurement_clock, INVALID[index % len(INVALID)], 10)
        await fresh(runtime_hass, manager, measurement_clock, flow)
        assert manager._flow_evidence.credited_seconds == 0
        assert (manager.timer_now - runtime.started_at).total_seconds() == (index + 1) * 120
    assert runtime.phase is DetectorPhase.ACTIVE


@pytest.mark.parametrize('kind,flow', BANDS)
async def test_f05_returned_real_quiet_flow_still_runs_normal_monitoring_reset(
    runtime_hass, runtime_entry, measurement_clock, kind, flow
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, flow)
    manager.engine.update_settings(settings())
    runtime = manager.engine.runtimes[kind]
    measurement_clock.advance(120)
    await fresh(runtime_hass, manager, measurement_clock, flow)
    await pause(runtime_hass, manager, measurement_clock)
    await fresh(runtime_hass, manager, measurement_clock, 0)
    assert manager._flow_evidence.credited_seconds == 0
    if kind is DetectorKind.SLOW_LEAK:
        assert runtime.phase is DetectorPhase.IDLE
    else:
        assert runtime.phase is DetectorPhase.MONITORING
        assert runtime.quiet_since == manager.timer_now
        measurement_clock.advance(299)
        await fresh(runtime_hass, manager, measurement_clock, 0)
        assert runtime.phase is DetectorPhase.MONITORING
        measurement_clock.advance(1)
        await fresh(runtime_hass, manager, measurement_clock, 0)
        assert runtime.phase is DetectorPhase.IDLE


@pytest.mark.parametrize('kind,flow', BANDS + [(DetectorKind.BURST_LEAK, 4000)])
async def test_f05_active_leak_shutoff_and_quiet_reset_survive_unknown_time(
    runtime_hass, runtime_entry, measurement_clock, kind, flow
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, flow)
    manager.engine.update_settings(settings(10))
    # A changed Burst signature starts a fresh evidential deadline (V3).
    await fresh(runtime_hass, manager, measurement_clock, flow)
    for _ in range(3):
        measurement_clock.advance(10)
        await fresh(runtime_hass, manager, measurement_clock, flow)
    runtime = manager.engine.runtimes[kind]
    assert runtime.phase is DetectorPhase.ACTIVE
    event = runtime.event_id
    measurement_clock.advance(1)
    await fresh(runtime_hass, manager, measurement_clock, 0)
    measurement_clock.advance(120)
    await fresh(runtime_hass, manager, measurement_clock, 0)
    assert runtime.quiet_since is not None
    await pause(runtime_hass, manager, measurement_clock, duration=1800)
    assert runtime.phase is DetectorPhase.ACTIVE
    assert runtime.event_id == event
    assert manager.engine.snapshot().shutoff_request
    assert runtime.quiet_since is None
    await fresh(runtime_hass, manager, measurement_clock, 0)
    assert runtime.quiet_since == manager.timer_now
    assert runtime.phase is DetectorPhase.ACTIVE
    measurement_clock.advance(299)
    await fresh(runtime_hass, manager, measurement_clock, 0)
    assert runtime.phase is DetectorPhase.ACTIVE
    measurement_clock.advance(1)
    await fresh(runtime_hass, manager, measurement_clock, 0)
    assert runtime.phase is DetectorPhase.IDLE


async def test_f05_burst_candidate_and_previous_flow_do_not_cross_pause(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 2500)
    burst = manager.engine.runtimes[DetectorKind.BURST_LEAK]
    assert burst.phase is DetectorPhase.MONITORING
    await pause(runtime_hass, manager, measurement_clock)
    assert burst.phase is DetectorPhase.IDLE
    assert manager.engine.last_flow_lph is None
    await fresh(runtime_hass, manager, measurement_clock, 2500)
    assert burst.phase is DetectorPhase.MONITORING
    assert burst.started_at == manager.timer_now
    assert burst.reason == 'absolute_flow'
    assert manager._flow_evidence.credited_seconds == 0


@pytest.mark.parametrize('kind,flow', BANDS)
async def test_f05_actual_source_rebind_discards_previous_monitoring(
    runtime_hass, runtime_entry, measurement_clock, kind, flow
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, flow)
    manager.engine.update_settings(settings())
    measurement_clock.advance(3480)
    await fresh(runtime_hass, manager, measurement_clock, flow)
    runtime = manager.engine.runtimes[kind]
    assert runtime.phase is DetectorPhase.MONITORING
    manager.engine.rebind_sources()
    assert runtime.phase is DetectorPhase.IDLE
    assert manager.engine.last_sample_at is None
    # A first sample from the replacement source cannot import old evidence.
    manager.engine.sample(manager.timer_now, flow, None, evidence_seconds=3480)
    assert runtime.started_at == manager.timer_now
    assert runtime.phase is DetectorPhase.MONITORING


async def test_f05_rate_rise_cannot_use_pre_outage_flow(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    manager.engine.update_settings(DetectorSettings(burst_rate_rise_lph_10s=100))
    await pause(runtime_hass, manager, measurement_clock, duration=1)
    await fresh(runtime_hass, manager, measurement_clock, 1500)
    burst = manager.engine.runtimes[DetectorKind.BURST_LEAK]
    assert burst.phase is DetectorPhase.IDLE
    assert burst.reason is None
    assert manager._flow_evidence.credited_seconds == 0
    measurement_clock.advance(10)
    await fresh(runtime_hass, manager, measurement_clock, 1500)
    assert burst.phase is DetectorPhase.IDLE
