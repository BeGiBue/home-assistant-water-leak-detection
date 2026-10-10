"""Repeated clean High episodes enter the existing rolling model conservatively."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from itertools import permutations
from types import SimpleNamespace

import pytest
from test_manager_runtime import start_manager as raw_start_manager
from test_round2_measurements import fresh

from custom_components.water_leak_detection.const import (
    DEFAULT_BURST_LEARNED_MULTIPLIER,
    DEFAULT_HIGH_DETECTION_MIN,
    DEFAULT_HIGH_RESET_MIN,
    DEFAULT_HIGH_VOLUME_L,
    DOMAIN,
    DetectorKind,
    DetectorPhase,
)
from custom_components.water_leak_detection.engine import DetectionEngine, DetectorSettings
from custom_components.water_leak_detection.learning import (
    MAX_HIGH_NORMAL_HISTORY,
    AdaptiveFlowLearner,
    LearningConfidence,
    LearningSample,
)
from custom_components.water_leak_detection.manager import WaterLeakManager

BASE = datetime(2026, 9, 1, tzinfo=UTC)
HIGH = DetectorKind.HIGH_FLOW
BURST = DetectorKind.BURST_LEAK


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
    assert not manager.learner._high_blocked
    if flow:
        clock.advance(30)
        await fresh(hass, manager, clock, flow)
    return manager


def candidates(peaks, days=None, learner=None):
    learner = learner or AdaptiveFlowLearner()
    days = list(range(len(peaks))) if days is None else days
    for peak, day in zip(peaks, days, strict=True):
        learner.add_high_candidate(BASE + timedelta(days=day), peak)
    return learner


def learned_peaks(learner):
    return sorted(sample.peak_lph for sample in learner.samples)


@pytest.mark.parametrize("count", [1, 2])
def test_one_or_two_high_candidates_do_not_affect_normal_learning(count):
    learner = candidates([750, 780][:count])
    assert len(learner.pending_high_candidates) == count
    assert not learner.confirmed_high_history
    assert not learner.samples
    snapshot = learner.snapshot(BASE + timedelta(days=count))
    assert snapshot.learned_max_lph is None
    assert snapshot.short_reference_lph is None
    assert snapshot.long_reference_lph is None
    assert snapshot.confidence is LearningConfidence.INSUFFICIENT


@pytest.mark.parametrize(
    "peaks",
    [
        (750, 780, 820),
        (700, 750, 800),
        (700, 805, 800),
    ],
)
def test_three_similar_candidates_promote_all_original_timestamps(peaks):
    learner = candidates(peaks, [0, 14, 28])
    assert not learner.pending_high_candidates
    assert learned_peaks(learner) == sorted(peaks)
    assert learner.confirmed_high_history == learner.samples
    assert [sample.timestamp for sample in learner.samples] == [
        BASE + timedelta(days=day) for day in [0, 14, 28]
    ]
    assert learner.snapshot(BASE + timedelta(days=28)).confidence is LearningConfidence.INSUFFICIENT


@pytest.mark.parametrize("peaks", [(700, 805.000001, 800), (650, 850, 1400)])
def test_peaks_outside_exact_spread_do_not_confirm(peaks):
    learner = candidates(peaks)
    assert len(learner.pending_high_candidates) == 3
    assert not learner.samples


@pytest.mark.parametrize("peaks", list(permutations((700, 805, 800))))
def test_cluster_decision_is_independent_of_order(peaks):
    assert learned_peaks(candidates(peaks)) == [700, 800, 805]


@pytest.mark.parametrize("peaks", list(permutations((650, 850, 1400))))
def test_dissimilar_cluster_is_rejected_in_every_order(peaks):
    assert not candidates(peaks).samples


def test_overlapping_bands_are_not_consumed_greedily():
    # Both triples are valid; the combined spread is not one valid cluster.
    results = set()
    for peaks in permutations((700, 790, 805, 900)):
        results.add(tuple(learned_peaks(candidates(peaks))))
    assert results == {(700, 790, 805, 900)}


def test_fourth_candidate_uses_confirmed_history_without_duplicates():
    learner = candidates([750, 780, 800], [0, 4, 9])
    original = list(learner.samples)
    learner.add_high_candidate(BASE + timedelta(days=14), 770)
    assert len(learner.samples) == 4
    assert learner.samples[:3] == original
    assert not learner.pending_high_candidates
    assert len(learner.confirmed_high_history) == 4
    assert learner.add_high_candidate(BASE + timedelta(days=14), 770) is False
    assert len(learner.samples) == 4


def test_pending_outside_window_does_not_confirm():
    learner = candidates([750, 780, 800], [0, 20, 31])
    assert [sample.peak_lph for sample in learner.pending_high_candidates] == [780, 800]
    assert not learner.samples


def test_expired_confirmed_history_cannot_confirm_new_summer_episode():
    learner = candidates([750, 780, 800], [0, 4, 9])
    learner.add_high_candidate(BASE + timedelta(days=40), 770)
    assert not learner.confirmed_high_history
    assert not learner.samples
    assert [sample.peak_lph for sample in learner.pending_high_candidates] == [770]


def test_two_current_confirmed_members_plus_new_candidate_are_enough():
    learner = candidates([750, 780, 800], [0, 20, 21])
    learner.add_high_candidate(BASE + timedelta(days=31), 770)
    assert learned_peaks(learner) == [770, 780, 800]
    assert not learner.pending_high_candidates


def test_window_reduction_prunes_pending_confirmed_and_samples_immediately():
    learner = candidates([750, 780, 800], [0, 1, 2])
    learner.add_high_candidate(BASE + timedelta(days=3), 1400)
    learner.add_high_candidate(BASE + timedelta(days=14), 1450)
    learner.update_window(7, BASE + timedelta(days=14))
    assert not learner.confirmed_high_history
    assert not learner.samples
    assert [sample.peak_lph for sample in learner.pending_high_candidates] == [1450]


@pytest.mark.parametrize("confirmed", [False, True])
def test_high_history_round_trip_and_repeat_restore_do_not_duplicate(confirmed):
    learner = candidates([750, 780, 800] if confirmed else [750, 780])
    raw = learner.to_dict()
    restored = AdaptiveFlowLearner()
    for _ in range(3):
        restored.restore(deepcopy(raw), BASE + timedelta(days=3))
        assert restored.samples == learner.samples
        assert restored.pending_high_candidates == learner.pending_high_candidates
        assert restored.confirmed_high_history == learner.confirmed_high_history
    if not confirmed:
        restored.add_high_candidate(BASE + timedelta(days=3), 800)
        assert len(restored.samples) == 3


def test_old_store_has_empty_optional_histories_and_unchanged_samples():
    sample = LearningSample(BASE, 300)
    learner = AdaptiveFlowLearner()
    learner.restore({"samples": [sample.to_dict()]}, BASE)
    assert learner.samples == [sample]
    assert not learner.pending_high_candidates
    assert not learner.confirmed_high_history


@pytest.mark.parametrize("field", ["pending_high_candidates", "confirmed_high_history"])
@pytest.mark.parametrize(
    "malformed",
    [
        None,
        {},
        "bad",
        [None],
        [{"timestamp": None, "peak_lph": 750}],
        [{"timestamp": BASE.replace(tzinfo=None).isoformat(), "peak_lph": 750}],
        [{"timestamp": BASE.isoformat(), "peak_lph": -1}],
        [{"timestamp": BASE.isoformat(), "peak_lph": 0}],
        [{"timestamp": BASE.isoformat(), "peak_lph": True}],
        [{"timestamp": BASE.isoformat(), "peak_lph": float("nan")}],
        [{"timestamp": BASE.isoformat(), "peak_lph": float("inf")}],
        [{"timestamp": (BASE + timedelta(days=1)).isoformat(), "peak_lph": 750}],
    ],
)
def test_malformed_high_history_is_ignored(field, malformed):
    learner = AdaptiveFlowLearner()
    learner.restore({"samples": [LearningSample(BASE, 300).to_dict()], field: malformed}, BASE)
    assert not learner.pending_high_candidates
    assert not learner.confirmed_high_history
    assert learned_peaks(learner) == [300]


def test_restore_prunes_high_histories_with_configured_window():
    raw = candidates([750, 780, 800], [0, 1, 2]).to_dict()
    raw["pending_high_candidates"] = [LearningSample(BASE + timedelta(days=3), 1400).to_dict()]
    restored = AdaptiveFlowLearner(window_days=7)
    restored.restore(raw, BASE + timedelta(days=11))
    assert not restored.samples
    assert not restored.pending_high_candidates
    assert not restored.confirmed_high_history


def test_history_size_is_bounded_on_input_and_runtime():
    learner = AdaptiveFlowLearner()
    records = [
        LearningSample(BASE + timedelta(seconds=i), 750).to_dict()
        for i in range(MAX_HIGH_NORMAL_HISTORY + 10)
    ]
    learner.restore({"samples": [], "pending_high_candidates": records}, BASE + timedelta(days=1))
    assert len(learner.pending_high_candidates) <= MAX_HIGH_NORMAL_HISTORY
    learner.add_high_candidate(BASE + timedelta(days=1), 750)
    assert len(learner.pending_high_candidates) + len(learner.confirmed_high_history) <= (
        MAX_HIGH_NORMAL_HISTORY
    )


def test_duplicate_high_store_records_cannot_supply_three_confirmations():
    first = LearningSample(BASE, 750).to_dict()
    same_in_other_zone = {"timestamp": "2026-09-01T01:00:00+01:00", "peak_lph": 750}
    learner = AdaptiveFlowLearner()
    learner.restore(
        {"samples": [], "pending_high_candidates": [first, first, same_in_other_zone]},
        BASE + timedelta(days=1),
    )
    assert len(learner.pending_high_candidates) == 1
    learner.add_high_candidate(BASE + timedelta(days=1), 780)
    assert not learner.samples


@pytest.mark.parametrize("confirmed", [False, True])
@pytest.mark.parametrize("shift", [-0.5, -3600, -7200])
def test_high_history_uses_f15_permissions_across_repeated_restore(confirmed, shift):
    learner = candidates(
        [750, 780, 800] if confirmed else [750, 780], [0, 0.001, 0.002] if confirmed else [0, 0.001]
    )
    runtime = BASE + timedelta(minutes=5)
    learner.observe_clock(runtime, runtime)
    raw = learner.to_dict(now=BASE + timedelta(seconds=shift), runtime_now=runtime)
    originals = deepcopy(learner.to_dict())
    restored = AdaptiveFlowLearner()
    for _ in range(3):
        restored.restore(raw, BASE + timedelta(seconds=shift))
        assert restored.to_dict() == originals
        raw = restored.to_dict(now=BASE + timedelta(seconds=shift), runtime_now=runtime)
    restored.to_dict(now=runtime, runtime_now=runtime)
    assert not restored._rollback_high_pending
    assert not restored._rollback_high_confirmed
    restored.snapshot(BASE + timedelta(days=31))
    assert not restored.samples
    assert not restored.pending_high_candidates
    assert not restored.confirmed_high_history


def test_promotion_after_rollback_transfers_existing_identity_permissions():
    learner = candidates([750, 780], [0, 0.001])
    runtime = BASE + timedelta(minutes=5)
    learner.observe_clock(runtime, runtime)
    wall = BASE - timedelta(hours=1)
    learner.observe_clock(wall, runtime)
    learner.add_high_candidate(wall, 800)
    originals = list(learner.samples)
    assert len(originals) == 3
    raw = learner.to_dict(now=wall, runtime_now=runtime)
    restored = AdaptiveFlowLearner()
    restored.restore(raw, wall)
    assert restored.samples == originals
    assert len(restored.confirmed_high_history) == 3
    assert not restored.pending_high_candidates


@pytest.mark.parametrize(
    "field,identities",
    [
        ("pending_high_candidates", "high_pending_fingerprints"),
        ("confirmed_high_history", "high_confirmed_fingerprints"),
    ],
)
def test_high_future_permissions_bind_exact_fields_and_counts(field, identities):
    learner = candidates(
        [750, 780, 800] if field == "confirmed_high_history" else [750, 780],
        [0, 0.001, 0.002] if field == "confirmed_high_history" else [0, 0.001],
    )
    runtime = BASE + timedelta(minutes=5)
    learner.observe_clock(runtime, runtime)
    wall = BASE - timedelta(hours=1)
    raw = learner.to_dict(now=wall, runtime_now=runtime)
    original_count = len(raw[field])
    raw[field].extend([raw[field][0]] * 10)
    raw[field].append(LearningSample(BASE + timedelta(seconds=30), 50000).to_dict())
    restored = AdaptiveFlowLearner()
    restored.restore(raw, wall)
    assert len(getattr(restored, field)) == original_count
    raw[field][0] = LearningSample(BASE, 50000).to_dict()
    raw["clock_rollback"][identities] = ["bad"]
    restored.restore(raw, wall)
    assert not getattr(restored, field)


def test_reset_learning_clears_all_high_history_episodes_and_clock_context():
    learner = candidates([750, 780, 800])
    learner.add_high_candidate(BASE + timedelta(days=3), 1400)
    learner.observe_high(
        BASE, 750, runtime_now=BASE, started=True, finished=False, disqualified=False
    )
    learner.reset()
    assert not learner.samples
    assert not learner.pending_high_candidates
    assert not learner.confirmed_high_history
    assert learner._high_episode is None
    assert not learner._rollback_samples
    assert not learner._rollback_high_pending
    assert not learner._rollback_high_confirmed
    assert learner._clock_utc is None and learner._clock_runtime is None


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
            assert len(manager.learner.pending_high_candidates) == index + 1
            assert not manager.learner.samples  # General suspicious gate still applies.
    assert learned_peaks(manager.learner) == [750, 780, 800]
    assert [sample.timestamp for sample in manager.learner.samples] == ends
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
    assert not manager.learner.pending_high_candidates


@pytest.mark.parametrize(
    "peak,duration,reason",
    [
        (2500, 0, "absolute_flow"),
        (1600, 0, "rapid_rise"),
        (2500, 30, "absolute_flow"),
    ],
)
async def test_any_burst_candidate_permanently_disqualifies_high(
    runtime_hass, runtime_entry, measurement_clock, peak, duration, reason
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
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
    assert not manager.learner.pending_high_candidates
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
    assert not manager.learner.pending_high_candidates
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
        assert manager.learner._high_episode is not None
        await manager.async_start_bypass(60)
        assert manager.learner._high_episode is None
    await finish_high(runtime_hass, manager, measurement_clock)
    await manager.async_cancel_bypass()
    assert not manager.learner.pending_high_candidates
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
    assert manager.learner._high_episode is None
    measurement_clock.advance(300)
    await fresh(runtime_hass, manager, measurement_clock, 750)
    assert manager._flow_evidence.credited_seconds == 0
    assert (manager.timer_now - manager.engine.runtimes[HIGH].started_at).total_seconds() == before
    await finish_high(runtime_hass, manager, measurement_clock, duration=0)
    assert not manager.learner.pending_high_candidates
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
    assert manager.learner._high_episode is None
    await finish_high(runtime_hass, manager, measurement_clock, duration=0)
    assert not manager.learner.pending_high_candidates


@pytest.mark.parametrize("interval", [30, 30.0000001])
async def test_numerical_evidence_rounding_keeps_high_candidate(
    runtime_hass, runtime_entry, measurement_clock, interval
):
    measurement_clock.seconds = 0.1
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 750)
    await finish_high(runtime_hass, manager, measurement_clock, interval=interval)
    assert len(manager.learner.pending_high_candidates) == 1
    assert manager.learner.pending_high_candidates[0].peak_lph == 750
    assert not manager.engine.last_evidence_gap


def test_real_evidence_gap_uses_engine_decision_and_discards_candidate():
    engine = DetectionEngine()
    learner = AdaptiveFlowLearner()
    for elapsed, flow, credit in [(0, 750, 0), (30, 750, 30 - 3e-6), (60, 0, 30), (360, 0, 300)]:
        now = BASE + timedelta(seconds=elapsed)
        transitions = engine.sample(now, flow, None, evidence_seconds=credit)
        learner.observe_high(
            now,
            flow,
            runtime_now=now,
            started=any(
                t.kind is HIGH and t.new_phase is DetectorPhase.MONITORING for t in transitions
            ),
            finished=any(t.kind is HIGH and t.new_phase is DetectorPhase.IDLE for t in transitions),
            disqualified=engine.last_evidence_gap,
        )
    assert not learner.pending_high_candidates
    assert learner._high_episode is None


async def test_running_high_episode_is_not_persisted_or_resumed_after_restart(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 750)
    measurement_clock.advance(120)
    await fresh(runtime_hass, manager, measurement_clock, 750)
    assert manager.learner._high_episode is not None
    raw = manager._serialize()["learning"]
    assert "high_episode" not in raw and "_high_episode" not in raw
    assert not raw["pending_high_candidates"]
    await manager.async_unload()
    restored = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    await restored.async_setup()
    assert restored.learner._high_episode is None
    assert not restored.learner.pending_high_candidates
    # An immediate quiet return cannot complete the old candidate.
    measurement_clock.advance(30)
    await fresh(runtime_hass, restored, measurement_clock, 0)
    measurement_clock.advance(300)
    await fresh(runtime_hass, restored, measurement_clock, 0)
    assert not restored.learner.pending_high_candidates


async def test_two_completed_candidates_survive_real_restart_and_third_confirms(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    for peak in [750, 780]:
        await finish_high(runtime_hass, manager, measurement_clock, peak)
    original = list(manager.learner.pending_high_candidates)
    await manager.async_unload()
    restored = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    await restored.async_setup()
    assert restored.learner.pending_high_candidates == original
    await quiet_guard(runtime_hass, restored, measurement_clock)
    await finish_high(runtime_hass, restored, measurement_clock, 800)
    assert len(restored.learner.samples) == 3
    assert restored.learner.samples[:2] == original


async def test_reset_service_clears_normal_pending_confirmed_and_running_high(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    for peak in [750, 780, 800, 1400]:
        await finish_high(runtime_hass, manager, measurement_clock, peak)
    await manager.async_reset_learning()
    assert not manager.learner.samples
    assert not manager.learner.pending_high_candidates
    assert not manager.learner.confirmed_high_history
    stored = await manager._store.async_load()
    assert stored["learning"] == {
        "samples": [],
        "pending_high_candidates": [],
        "confirmed_high_history": [],
    }


def manager_for(learner, options=None):
    manager = WaterLeakManager.__new__(WaterLeakManager)
    manager.entry = SimpleNamespace(options=options or {})
    manager.learner = learner
    return manager


@pytest.mark.parametrize("high", [600, 900])
def test_confirmed_high_enters_existing_confidence_burst_path_without_changing_high(high):
    learner = AdaptiveFlowLearner()
    learner.samples = [LearningSample(BASE + timedelta(days=day), 500) for day in range(20)]
    manager = manager_for(learner, {"high_threshold_lph": high})
    baseline = manager.adaptive_thresholds(BASE + timedelta(days=20))
    for day in [20, 21, 22]:
        learner.add_high_candidate(BASE + timedelta(days=day), 1400)
    thresholds = manager.adaptive_thresholds(BASE + timedelta(days=22))
    assert learner.snapshot(BASE + timedelta(days=22)).confidence is LearningConfidence.RELIABLE
    assert thresholds.normal_reference_lph == 1400
    assert thresholds.effective_high_lph == baseline.effective_high_lph == high
    assert thresholds.effective_burst_lph == 1400 * DEFAULT_BURST_LEARNED_MULTIPLIER
    assert thresholds.effective_burst_lph > baseline.effective_burst_lph
    ceiling = thresholds.hydraulic_reference_lph * 0.75
    assert thresholds.effective_burst_lph <= ceiling
    settings = DetectorSettings()
    assert settings.high_detection_seconds == DEFAULT_HIGH_DETECTION_MIN * 60
    assert settings.high_volume_l == DEFAULT_HIGH_VOLUME_L
    assert settings.high_reset_seconds == DEFAULT_HIGH_RESET_MIN * 60


def test_three_confirmed_high_episodes_do_not_bypass_insufficient_confidence():
    learner = candidates([1400, 1400, 1400])
    snapshot = learner.snapshot(BASE + timedelta(days=3))
    assert snapshot.sample_count == 3
    assert snapshot.confidence is LearningConfidence.INSUFFICIENT
    thresholds = manager_for(learner).adaptive_thresholds(BASE + timedelta(days=3))
    assert thresholds.normal_reference_lph is None
    assert thresholds.effective_high_lph == 600
    assert thresholds.effective_burst_lph == 2000


def test_confirmed_high_keeps_hydraulic_ceiling_and_existing_learning_damping():
    learner = candidates([5000, 5000, 5000])
    learner.samples += [
        LearningSample(BASE + timedelta(days=3), 300),
        LearningSample(BASE + timedelta(days=4), 300),
    ]
    now = BASE + timedelta(days=4)
    assert learner.snapshot(now).confidence is LearningConfidence.LEARNING
    thresholds = manager_for(learner).adaptive_thresholds(now)
    assert thresholds.normal_reference_lph == 5000 * 0.85
    assert thresholds.effective_burst_lph == max(2000, thresholds.hydraulic_reference_lph * 0.75)
    assert thresholds.effective_high_lph == 600


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
    assert not manager.learner.pending_high_candidates


async def test_cancelled_bypass_cannot_reclassify_ongoing_high_consumption(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 750)
    await manager.async_start_bypass(60)
    measurement_clock.advance(30)
    await fresh(runtime_hass, manager, measurement_clock, 750)
    await manager.async_cancel_bypass()
    await finish_high(runtime_hass, manager, measurement_clock, duration=0)
    assert not manager.learner.pending_high_candidates
    # A subsequent fully observed fresh episode is eligible again after physical reset.
    await finish_high(runtime_hass, manager, measurement_clock)
    assert len(manager.learner.pending_high_candidates) == 1


async def test_source_rebind_keeps_existing_neutralization_of_all_learning(
    runtime_hass, runtime_entry, measurement_clock
):
    from test_manager_runtime import report

    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    for peak in [750, 780, 800, 1400]:
        await finish_high(runtime_hass, manager, measurement_clock, peak)
    assert manager.learner.samples and manager.learner.pending_high_candidates
    assert manager.learner.confirmed_high_history
    await manager.async_unload()
    runtime_hass.config_entries.async_update_entry(
        runtime_entry, data={"flow_entity": "sensor.new_flow"}
    )
    report(runtime_hass, measurement_clock, 750, entity="sensor.new_flow")
    rebound = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = rebound
    await rebound.async_setup()
    assert not rebound.learner.samples
    assert not rebound.learner.pending_high_candidates
    assert not rebound.learner.confirmed_high_history
    assert rebound.learner._high_episode is None


async def test_confirmed_high_and_pending_survive_real_clock_rollback_restart(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    for peak in [750, 780, 800, 1400]:
        await finish_high(runtime_hass, manager, measurement_clock, peak)
    originals = (
        list(manager.learner.samples),
        list(manager.learner.pending_high_candidates),
        list(manager.learner.confirmed_high_history),
    )
    measurement_clock.wall_shift -= 7200
    for _ in range(3):
        await manager.async_unload()
        manager = WaterLeakManager(runtime_hass, runtime_entry)
        runtime_hass.data[DOMAIN][runtime_entry.entry_id] = manager
        await manager.async_setup()
        assert (
            manager.learner.samples,
            manager.learner.pending_high_candidates,
            manager.learner.confirmed_high_history,
        ) == originals


@pytest.mark.parametrize("field", ["pending_high_candidates", "confirmed_high_history"])
def test_future_high_records_without_observed_rollback_are_never_authorized(field):
    sample = LearningSample(BASE + timedelta(hours=1), 750)
    learner = AdaptiveFlowLearner()
    raw = {
        "samples": [sample.to_dict()] if field == "confirmed_high_history" else [],
        field: [sample.to_dict()],
    }
    learner.restore(raw, BASE)
    assert not getattr(learner, field)


@pytest.mark.parametrize("field", ["pending_high_candidates", "confirmed_high_history"])
def test_offline_clock_rollback_does_not_reuse_an_observed_high_epoch(field):
    learner = candidates(
        [750, 780, 800] if field == "confirmed_high_history" else [750, 780],
        [0, 0.001, 0.002] if field == "confirmed_high_history" else [0, 0.001],
    )
    runtime = BASE + timedelta(minutes=5)
    learner.observe_clock(runtime, runtime)
    wall = BASE - timedelta(hours=1)
    raw = learner.to_dict(now=wall, runtime_now=runtime)
    restored = AdaptiveFlowLearner()
    restored.restore(raw, wall - timedelta(seconds=0.5))
    assert not getattr(restored, field)


def test_promoted_old_candidates_do_not_appear_in_recent_reference():
    learner = candidates([750, 780, 800], [0, 14, 28])
    snapshot = learner.snapshot(BASE + timedelta(days=28))
    assert snapshot.short_reference_lph == 800
    assert snapshot.long_reference_lph == 798
    assert snapshot.coverage_days == 3
    assert snapshot.age_days == 29


def test_duplicate_admitted_high_records_in_store_are_not_relearned():
    learner = candidates([750, 780, 800])
    raw = learner.to_dict()
    raw["samples"].extend([dict(raw["samples"][0])] * 5)
    restored = AdaptiveFlowLearner()
    restored.restore(raw, BASE + timedelta(days=3))
    assert restored.samples == learner.samples
    assert restored.confirmed_high_history == learner.confirmed_high_history
    restored.add_high_candidate(BASE + timedelta(days=3), 770)
    assert len(restored.samples) == 4


@pytest.mark.parametrize("first", [500, 0, 750])
async def test_restart_cannot_relearn_interrupted_high_without_physical_reset(
    runtime_hass, runtime_entry, measurement_clock, first
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 750)
    assert manager.learner._high_episode is not None
    await manager.async_unload()
    manager = await raw_start_manager(runtime_hass, runtime_entry, measurement_clock, first)
    assert manager.learner._high_blocked
    measurement_clock.advance(30)
    await fresh(runtime_hass, manager, measurement_clock, 750)
    assert manager.learner._high_episode is None
    await finish_high(runtime_hass, manager, measurement_clock)
    assert not manager.learner.pending_high_candidates


@pytest.mark.parametrize("seconds,flow,released", [(299, 0, False), (300, 0, True),
                                                   (300, 90, True), (300, 100, False)])
async def test_startup_guard_exact_physical_boundary(
    runtime_hass, runtime_entry, measurement_clock, seconds, flow, released
):
    manager = await raw_start_manager(runtime_hass, runtime_entry, measurement_clock, flow)
    assert manager.learner._high_blocked  # No known prior episode is required.
    await quiet_guard(runtime_hass, manager, measurement_clock, seconds, flow)
    assert manager.learner._high_blocked is not released
    await finish_high(runtime_hass, manager, measurement_clock)
    assert bool(manager.learner.pending_high_candidates) is released


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
    assert manager.learner._high_blocked
    measurement_clock.advance(1)
    await fresh(runtime_hass, manager, measurement_clock, 140)
    assert not manager.learner._high_blocked


@pytest.mark.parametrize("break_flow", [100, 500, "unknown", "unavailable", "-1", "nan", "inf"])
async def test_startup_guard_interruption_restarts_quiet(
    runtime_hass, runtime_entry, measurement_clock, break_flow
):
    manager = await raw_start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    await quiet_guard(runtime_hass, manager, measurement_clock, 299)
    await fresh(runtime_hass, manager, measurement_clock, break_flow)
    measurement_clock.advance(30)
    await quiet_guard(runtime_hass, manager, measurement_clock, 299)
    assert manager.learner._high_blocked
    measurement_clock.advance(1)
    await fresh(runtime_hass, manager, measurement_clock, 0)
    assert not manager.learner._high_blocked


async def test_startup_guard_source_max_age_gap_does_not_credit_quiet(
    runtime_hass, runtime_entry, measurement_clock
):
    runtime_hass.config_entries.async_update_entry(
        runtime_entry, options={"source_gap_policy_explicit": True}
    )
    manager = await raw_start_manager(runtime_hass, runtime_entry, measurement_clock, 0,
                                      configured_gap=30)
    await quiet_guard(runtime_hass, manager, measurement_clock, 180)
    measurement_clock.advance(120)
    await fresh(runtime_hass, manager, measurement_clock, 0)
    assert manager.engine.last_evidence_gap
    assert manager.learner._high_blocked
    await quiet_guard(runtime_hass, manager, measurement_clock, 299)
    assert manager.learner._high_blocked
    measurement_clock.advance(1)
    await fresh(runtime_hass, manager, measurement_clock, 0)
    assert not manager.learner._high_blocked


async def test_startup_guard_internal_ticks_do_not_create_reset_evidence(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await raw_start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    for _ in range(30):
        measurement_clock.advance(10)
        await manager._async_tick(measurement_clock.utcnow())
    assert manager.learner._high_blocked


async def test_full_startup_reset_allows_regular_three_episode_confirmation(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await raw_start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    await quiet_guard(runtime_hass, manager, measurement_clock)
    for peak in (750, 780, 800):
        await finish_high(runtime_hass, manager, measurement_clock, peak)
    assert learned_peaks(manager.learner) == [750, 780, 800]


def history_records(count=4100):
    return [LearningSample(BASE + timedelta(seconds=i), 750 + i / 10000).to_dict()
            for i in range(count)]


@pytest.mark.parametrize("field", ["pending_high_candidates", "confirmed_high_history"])
@pytest.mark.parametrize("order", ["ascending", "descending", "shuffled"])
def test_restore_limit_keeps_newest_valid_records(field, order):
    from random import Random

    records = history_records()
    expected = records[-MAX_HIGH_NORMAL_HISTORY:]
    if order == "descending":
        records.reverse()
    elif order == "shuffled":
        Random(42).shuffle(records)
    raw = {field: records, "samples": records if field == "confirmed_high_history" else []}
    learner = AdaptiveFlowLearner()
    learner.restore(raw, BASE + timedelta(days=1))
    assert [sample.to_dict() for sample in getattr(learner, field)] == expected
    learner.restore(raw, BASE + timedelta(days=1))
    assert [sample.to_dict() for sample in getattr(learner, field)] == expected


@pytest.mark.parametrize("prefix", ["expired", "malformed", "duplicate"])
def test_expired_prefix_cannot_hide_current_candidates(prefix):
    current = history_records(2)
    old = LearningSample(BASE - timedelta(days=31), 750).to_dict()
    preceding = {"expired": old, "malformed": {"timestamp": "invalid", "peak_lph": True},
                 "duplicate": current[0]}[prefix]
    learner = AdaptiveFlowLearner()
    learner.restore({"pending_high_candidates": [preceding] * 4096 + current}, BASE)
    # The second record is future here; move restore time beyond both records.
    learner.restore({"pending_high_candidates": [preceding] * 4096 + current},
                    BASE + timedelta(seconds=2))
    assert [sample.to_dict() for sample in learner.pending_high_candidates] == current


@pytest.mark.parametrize("authorized", ["pending", "confirmed"])
@pytest.mark.parametrize("target", ["pending", "confirmed"])
def test_restore_f15_permissions_cannot_cross_high_lists(authorized, target):
    learner = candidates([750, 780, 800] if authorized == "confirmed" else [750, 780],
                         [0, 0.001, 0.002] if authorized == "confirmed" else [0, 0.001])
    runtime = BASE + timedelta(minutes=5)
    learner.observe_clock(runtime, runtime)
    wall = BASE - timedelta(hours=1)
    raw = learner.to_dict(now=wall, runtime_now=runtime)
    source = "confirmed_high_history" if authorized == "confirmed" else "pending_high_candidates"
    destination = "confirmed_high_history" if target == "confirmed" else "pending_high_candidates"
    raw[destination] = raw[source]
    if target == "confirmed":
        raw["samples"] = raw[source]
        raw["clock_rollback"]["fingerprints"] = raw["clock_rollback"].get(
            "high_confirmed_fingerprints",
            raw["clock_rollback"].get("high_pending_fingerprints", [])
        ) or raw["clock_rollback"]["high_pending_fingerprints"]
    restored = AdaptiveFlowLearner()
    restored.restore(raw, wall)
    assert bool(getattr(restored, destination)) is (authorized == target)


def test_confirmed_consistency_before_limit_and_window_reduction():
    records = history_records()
    missing = LearningSample(BASE + timedelta(hours=2), 900).to_dict()
    learner = AdaptiveFlowLearner()
    learner.restore({"samples": records, "confirmed_high_history": records + [missing] * 4100},
                    BASE + timedelta(days=1))
    assert [sample.to_dict() for sample in learner.confirmed_high_history] == records[-4096:]
    learner.update_window(7, BASE + timedelta(days=8))
    assert not learner.samples and not learner.confirmed_high_history


@pytest.mark.parametrize("difference,blocked", [(2e-6, False), (3e-6, True)])
def test_startup_guard_reuses_engine_numeric_gap_tolerance(difference, blocked):
    engine = DetectionEngine()
    learner = AdaptiveFlowLearner()
    learner.restore({}, BASE)
    for elapsed in range(0, 301, 30):
        now = BASE + timedelta(seconds=elapsed)
        engine.sample(now, 0, None, evidence_seconds=30 - difference)
        learner.observe_high(now, 0, runtime_now=now, started=False, finished=False,
                             disqualified=engine.last_evidence_gap,
                             evidence_gap=engine.last_evidence_gap)
    assert learner._high_blocked is blocked
