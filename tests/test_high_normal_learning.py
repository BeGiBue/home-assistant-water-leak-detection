"""F04: retained High runtime safety regressions with separate Long-Term admission."""

from datetime import UTC, datetime

import pytest
from test_manager_runtime import start_manager as raw_start_manager
from test_round2_measurements import fresh

from custom_components.water_leak_detection.const import DOMAIN, DetectorKind, DetectorPhase
from custom_components.water_leak_detection.engine import DetectorSettings
from custom_components.water_leak_detection.learning import LearningConfidence
from custom_components.water_leak_detection.manager import WaterLeakManager

BASE = datetime(2026, 9, 1, tzinfo=UTC)
HIGH = DetectorKind.HIGH_FLOW
BURST = DetectorKind.BURST_LEAK


def learned_peaks(learner):
    records = getattr(learner, "confirmed_high_history", getattr(learner, "samples", []))
    return sorted(record.peak_lph for record in records)


async def quiet_guard(hass, manager, clock, seconds=300, flow=0):
    await fresh(hass, manager, clock, flow)
    for _ in range(seconds // 30):
        clock.advance(30)
        await fresh(hass, manager, clock, flow)
    if seconds % 30:
        clock.advance(seconds % 30)
        await fresh(hass, manager, clock, flow)


async def start_manager(hass, entry, clock, flow):
    """Existing episode tests start after the newly required physical startup reset."""
    manager = await raw_start_manager(hass, entry, clock, 0)
    await quiet_guard(hass, manager, clock)
    assert not manager.long_term_learner._high_blocked
    if flow:
        clock.advance(30)
        await fresh(hass, manager, clock, flow)
    return manager


async def finish_high(hass, manager, clock, peak=750, duration=720, interval=30):
    clock.advance(interval)
    await fresh(hass, manager, clock, peak)
    for _ in range(round(duration / interval)):
        clock.advance(interval)
        await fresh(hass, manager, clock, peak)
    clock.advance(interval)
    await fresh(hass, manager, clock, 0)
    for _ in range(round(300 / interval)):
        clock.advance(interval)
        await fresh(hass, manager, clock, 0)
    assert manager.engine.runtimes[HIGH].phase is DetectorPhase.IDLE
    return clock.utcnow()


async def test_real_high_transitions_admit_only_after_third_clean_reset(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    ends = []
    for index, peak in enumerate([750, 780, 800]):
        ends.append(await finish_high(runtime_hass, manager, measurement_clock, peak))
        if index < 2:
            assert len(manager.long_term_learner.pending_high_candidates) == index + 1
            assert not manager.learner.samples  # General suspicious gate still applies.
    assert learned_peaks(manager.long_term_learner) == [750, 780, 800]
    assert [sample.timestamp for sample in manager.long_term_learner.confirmed_high_history] == ends
    assert not manager.learner.samples
    assert manager.learning_snapshot.confidence is LearningConfidence.INSUFFICIENT
    assert manager.adaptive_thresholds().effective_high_lph == 600
    assert manager.adaptive_thresholds().effective_burst_lph == 2000


@pytest.mark.parametrize("mode", ["duration", "volume"])
async def test_high_active_is_never_learned_after_event_ends(
    runtime_hass, runtime_entry, measurement_clock, mode
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    if mode == "duration":
        # Isolate unchanged 45-min time criterion from the independent volume criterion.
        manager.engine.settings.high_volume_l = 999999
    peak, duration = (700, 2700) if mode == "duration" else (1200, 1530)
    measurement_clock.advance(30)
    await fresh(runtime_hass, manager, measurement_clock, peak)
    for _ in range(duration // 30):
        measurement_clock.advance(30)
        await fresh(runtime_hass, manager, measurement_clock, peak)
    assert manager.engine.runtimes[HIGH].phase is DetectorPhase.ACTIVE
    await finish_high(runtime_hass, manager, measurement_clock, peak, duration=0)
    assert not manager.learner.samples
    assert not manager.long_term_learner.pending_high_candidates


@pytest.mark.parametrize(
    "peak,duration,reason",
    [
        (2100, 0, "absolute_flow"),
        (2500, 0, "rapid_rise"),
        (2500, 30, "rapid_rise"),
    ],
)
async def test_any_burst_candidate_permanently_disqualifies_high(
    runtime_hass, runtime_entry, measurement_clock, peak, duration, reason
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    if reason == "absolute_flow":
        manager.engine.settings.burst_rate_rise_lph_10s = 10000
    measurement_clock.advance(10)
    await fresh(runtime_hass, manager, measurement_clock, peak)
    assert manager.engine.runtimes[BURST].reason == reason
    if duration:
        measurement_clock.advance(duration)
        await fresh(runtime_hass, manager, measurement_clock, peak)
        assert manager.engine.runtimes[BURST].phase is DetectorPhase.ACTIVE
    else:
        assert manager.engine.runtimes[BURST].phase is DetectorPhase.MONITORING
    await finish_high(runtime_hass, manager, measurement_clock, 750, duration=0)
    assert not manager.long_term_learner.pending_high_candidates
    assert not manager.learner.samples


@pytest.mark.parametrize("kind", [DetectorKind.SLOW_LEAK, DetectorKind.LOW_FLOW])
async def test_other_active_alarm_disqualifies_high_even_when_later_disabled(
    runtime_hass, runtime_entry, measurement_clock, kind
):
    initial = 7 if kind is DetectorKind.SLOW_LEAK else 250
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, initial)
    settings = DetectorSettings(slow_detection_seconds=30, low_detection_seconds=30)
    manager.engine.update_settings(settings)
    measurement_clock.advance(30)
    await fresh(runtime_hass, manager, measurement_clock, initial)
    assert manager.engine.runtimes[kind].phase is DetectorPhase.ACTIVE
    measurement_clock.advance(30)
    await fresh(runtime_hass, manager, measurement_clock, 750)
    await manager.async_set_detector_enabled(
        "slow" if kind is DetectorKind.SLOW_LEAK else "low", False
    )
    await finish_high(runtime_hass, manager, measurement_clock, duration=0)
    assert not manager.long_term_learner.pending_high_candidates
    assert not manager.learner.samples


@pytest.mark.parametrize("when", ["before", "during"])
async def test_bypass_never_admits_high_episode(
    runtime_hass, runtime_entry, measurement_clock, when
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    if when == "before":
        await manager.async_start_bypass(60)
    measurement_clock.advance(30)
    await fresh(runtime_hass, manager, measurement_clock, 750)
    if when == "during":
        assert manager.long_term_learner._high_episode is not None
        await manager.async_start_bypass(60)
        assert manager.long_term_learner._high_episode is None
    await finish_high(runtime_hass, manager, measurement_clock)
    await manager.async_cancel_bypass()
    assert not manager.long_term_learner.pending_high_candidates
    assert not manager.learner.samples


@pytest.mark.parametrize("invalid", ["unavailable", "unknown", "bad", "-1", "nan", "inf"])
async def test_source_outage_disqualifies_but_does_not_destroy_round7_progress(
    runtime_hass, runtime_entry, measurement_clock, invalid
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 750)
    measurement_clock.advance(120)
    await fresh(runtime_hass, manager, measurement_clock, 750)
    before = (manager.timer_now - manager.engine.runtimes[HIGH].started_at).total_seconds()
    measurement_clock.advance(1)
    await fresh(runtime_hass, manager, measurement_clock, invalid)
    assert manager.long_term_learner._high_episode is None
    measurement_clock.advance(300)
    await fresh(runtime_hass, manager, measurement_clock, 750)
    assert manager._flow_evidence.credited_seconds == 0
    assert (manager.timer_now - manager.engine.runtimes[HIGH].started_at).total_seconds() == before
    await finish_high(runtime_hass, manager, measurement_clock, duration=0)
    assert not manager.long_term_learner.pending_high_candidates
    assert not manager.learner.samples


async def test_explicit_source_max_age_gap_disqualifies_high(
    runtime_hass, runtime_entry, measurement_clock
):
    runtime_hass.config_entries.async_update_entry(
        runtime_entry, options={"source_max_age_seconds": 30, "source_gap_policy_explicit": True}
    )
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 750)
    measurement_clock.advance(120)
    await fresh(runtime_hass, manager, measurement_clock, 750)
    assert manager.engine.last_evidence_gap is True
    assert manager.long_term_learner._high_episode is None
    await finish_high(runtime_hass, manager, measurement_clock, duration=0)
    assert not manager.long_term_learner.pending_high_candidates


@pytest.mark.parametrize("interval", [30, 30.0000001])
async def test_numerical_evidence_rounding_keeps_high_candidate(
    runtime_hass, runtime_entry, measurement_clock, interval
):
    measurement_clock.seconds = 0.1
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 750)
    await finish_high(runtime_hass, manager, measurement_clock, interval=interval)
    assert len(manager.long_term_learner.pending_high_candidates) == 1
    assert manager.long_term_learner.pending_high_candidates[0].peak_lph == 750
    assert not manager.engine.last_evidence_gap


async def test_running_high_episode_is_not_persisted_or_resumed_after_restart(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 750)
    measurement_clock.advance(120)
    await fresh(runtime_hass, manager, measurement_clock, 750)
    assert manager.long_term_learner._high_episode is not None
    raw = manager._serialize()["long_term_learning"]
    assert "high_episode" not in raw and "_high_episode" not in raw
    assert not raw["pending_high_candidates"]
    await manager.async_unload()
    restored = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    await restored.async_setup()
    assert restored.long_term_learner._high_episode is None
    assert not restored.long_term_learner.pending_high_candidates
    # An immediate quiet return cannot complete the old candidate.
    measurement_clock.advance(30)
    await fresh(runtime_hass, restored, measurement_clock, 0)
    measurement_clock.advance(300)
    await fresh(runtime_hass, restored, measurement_clock, 0)
    assert not restored.long_term_learner.pending_high_candidates


async def test_two_completed_candidates_survive_real_restart_and_third_confirms(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    for peak in [750, 780]:
        await finish_high(runtime_hass, manager, measurement_clock, peak)
    original = list(manager.long_term_learner.pending_high_candidates)
    await manager.async_unload()
    restored = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    await restored.async_setup()
    assert restored.long_term_learner.pending_high_candidates == original
    await quiet_guard(runtime_hass, restored, measurement_clock)
    await finish_high(runtime_hass, restored, measurement_clock, 800)
    assert len(restored.long_term_learner.confirmed_high_history) == 3
    assert not restored.learner.samples
    assert restored.long_term_learner.confirmed_high_history[:2] == original


async def test_reset_service_clears_normal_pending_confirmed_and_running_high(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    for peak in [750, 780, 800, 1400]:
        await finish_high(runtime_hass, manager, measurement_clock, peak)
    await manager.async_reset_learning()
    assert not manager.learner.samples
    assert not manager.long_term_learner.pending_high_candidates
    assert not manager.long_term_learner.confirmed_high_history
    stored = await manager._store.async_load()
    assert stored["rolling_learning"]["samples"] == []
    assert stored["long_term_learning"]["pending_high_candidates"] == []
    assert stored["long_term_learning"]["confirmed_high_history"] == []


async def test_sub_high_normal_learning_is_unchanged(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 250)
    measurement_clock.advance(30)
    await fresh(runtime_hass, manager, measurement_clock, 500)
    measurement_clock.advance(30)
    await fresh(runtime_hass, manager, measurement_clock, 0)
    measurement_clock.advance(120)
    await fresh(runtime_hass, manager, measurement_clock, 0)
    assert learned_peaks(manager.learner) == [500]
    assert not manager.long_term_learner.pending_high_candidates


async def test_cancelled_bypass_cannot_reclassify_ongoing_high_consumption(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 750)
    await manager.async_start_bypass(60)
    measurement_clock.advance(30)
    await fresh(runtime_hass, manager, measurement_clock, 750)
    await manager.async_cancel_bypass()
    await finish_high(runtime_hass, manager, measurement_clock, duration=0)
    assert not manager.long_term_learner.pending_high_candidates
    # A subsequent fully observed fresh episode is eligible again after physical reset.
    await finish_high(runtime_hass, manager, measurement_clock)
    assert len(manager.long_term_learner.pending_high_candidates) == 1


async def test_source_rebind_keeps_existing_neutralization_of_all_learning(
    runtime_hass, runtime_entry, measurement_clock
):
    from test_manager_runtime import report

    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    for peak in [750, 780, 800, 1400]:
        await finish_high(runtime_hass, manager, measurement_clock, peak)
    assert (
        manager.long_term_learner.confirmed_high_history
        and manager.long_term_learner.pending_high_candidates
    )
    assert manager.long_term_learner.confirmed_high_history
    await manager.async_unload()
    runtime_hass.config_entries.async_update_entry(
        runtime_entry, data={"flow_entity": "sensor.new_flow"}
    )
    report(runtime_hass, measurement_clock, 750, entity="sensor.new_flow")
    rebound = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = rebound
    await rebound.async_setup()
    assert not rebound.learner.samples
    assert not rebound.long_term_learner.pending_high_candidates
    assert not rebound.long_term_learner.confirmed_high_history
    assert rebound.long_term_learner._high_episode is None


async def test_confirmed_high_and_pending_survive_real_clock_rollback_restart(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    for peak in [750, 780, 800, 1400]:
        await finish_high(runtime_hass, manager, measurement_clock, peak)
    originals = (
        list(manager.learner.samples),
        list(manager.long_term_learner.pending_high_candidates),
        list(manager.long_term_learner.confirmed_high_history),
    )
    measurement_clock.wall_shift -= 7200
    for _ in range(3):
        await manager.async_unload()
        manager = WaterLeakManager(runtime_hass, runtime_entry)
        runtime_hass.data[DOMAIN][runtime_entry.entry_id] = manager
        await manager.async_setup()
        assert (
            manager.learner.samples,
            manager.long_term_learner.pending_high_candidates,
            manager.long_term_learner.confirmed_high_history,
        ) == originals


@pytest.mark.parametrize("first", [500, 0, 750])
async def test_restart_cannot_relearn_interrupted_high_without_physical_reset(
    runtime_hass, runtime_entry, measurement_clock, first
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 750)
    assert manager.long_term_learner._high_episode is not None
    await manager.async_unload()
    manager = await raw_start_manager(runtime_hass, runtime_entry, measurement_clock, first)
    assert manager.long_term_learner._high_blocked
    measurement_clock.advance(30)
    await fresh(runtime_hass, manager, measurement_clock, 750)
    assert manager.long_term_learner._high_episode is None
    await finish_high(runtime_hass, manager, measurement_clock)
    assert not manager.long_term_learner.pending_high_candidates


@pytest.mark.parametrize(
    "seconds,flow,released", [(299, 0, False), (300, 0, True), (300, 90, True), (300, 100, False)]
)
async def test_startup_guard_exact_physical_boundary(
    runtime_hass, runtime_entry, measurement_clock, seconds, flow, released
):
    manager = await raw_start_manager(runtime_hass, runtime_entry, measurement_clock, flow)
    assert manager.long_term_learner._high_blocked  # No known prior episode is required.
    await quiet_guard(runtime_hass, manager, measurement_clock, seconds, flow)
    assert manager.long_term_learner._high_blocked is not released
    await finish_high(runtime_hass, manager, measurement_clock)
    assert bool(manager.long_term_learner.pending_high_candidates) is released


async def test_startup_guard_uses_configured_high_reset(
    runtime_hass, runtime_entry, measurement_clock
):
    runtime_hass.config_entries.async_update_entry(
        runtime_entry, options={"high_quiet_lph": 150, "high_reset_minutes": 2}
    )
    manager = await raw_start_manager(runtime_hass, runtime_entry, measurement_clock, 140)
    assert manager.engine.settings.high_quiet_lph == 150
    assert manager.engine.settings.high_reset_seconds == 120
    await quiet_guard(runtime_hass, manager, measurement_clock, 119, 140)
    assert manager.long_term_learner._high_blocked
    measurement_clock.advance(1)
    await fresh(runtime_hass, manager, measurement_clock, 140)
    assert not manager.long_term_learner._high_blocked


@pytest.mark.parametrize("break_flow", [100, 500, "unknown", "unavailable", "-1", "nan", "inf"])
async def test_startup_guard_interruption_restarts_quiet(
    runtime_hass, runtime_entry, measurement_clock, break_flow
):
    manager = await raw_start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    await quiet_guard(runtime_hass, manager, measurement_clock, 299)
    await fresh(runtime_hass, manager, measurement_clock, break_flow)
    measurement_clock.advance(30)
    await quiet_guard(runtime_hass, manager, measurement_clock, 299)
    assert manager.long_term_learner._high_blocked
    measurement_clock.advance(1)
    await fresh(runtime_hass, manager, measurement_clock, 0)
    assert not manager.long_term_learner._high_blocked


async def test_startup_guard_source_max_age_gap_does_not_credit_quiet(
    runtime_hass, runtime_entry, measurement_clock
):
    runtime_hass.config_entries.async_update_entry(
        runtime_entry, options={"source_gap_policy_explicit": True}
    )
    manager = await raw_start_manager(
        runtime_hass, runtime_entry, measurement_clock, 0, configured_gap=30
    )
    await quiet_guard(runtime_hass, manager, measurement_clock, 180)
    measurement_clock.advance(120)
    await fresh(runtime_hass, manager, measurement_clock, 0)
    assert manager.engine.last_evidence_gap
    assert manager.long_term_learner._high_blocked
    await quiet_guard(runtime_hass, manager, measurement_clock, 299)
    assert manager.long_term_learner._high_blocked
    measurement_clock.advance(1)
    await fresh(runtime_hass, manager, measurement_clock, 0)
    assert not manager.long_term_learner._high_blocked


async def test_startup_guard_internal_ticks_do_not_create_reset_evidence(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await raw_start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    for _ in range(30):
        measurement_clock.advance(10)
        await manager._async_tick(measurement_clock.utcnow())
    assert manager.long_term_learner._high_blocked


async def test_full_startup_reset_allows_regular_three_episode_confirmation(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await raw_start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    await quiet_guard(runtime_hass, manager, measurement_clock)
    for peak in (750, 780, 800):
        await finish_high(runtime_hass, manager, measurement_clock, peak)
    assert learned_peaks(manager.long_term_learner) == [750, 780, 800]
