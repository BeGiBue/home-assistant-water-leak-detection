"""Measurement and state regressions without changing detector definitions."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.water_leak_detection.const import DetectorKind, DetectorPhase
from custom_components.water_leak_detection.engine import DetectionEngine, DetectorSettings
from custom_components.water_leak_detection.learning import AdaptiveFlowLearner
from custom_components.water_leak_detection.notifications import EventAcknowledgement
from custom_components.water_leak_detection.units import normalize_flow_lph

BASE = datetime(2026, 10, 7, tzinfo=UTC)


def at(seconds):
    return BASE + timedelta(seconds=seconds)


@pytest.mark.parametrize("kind,flow", [
    (DetectorKind.SLOW_LEAK, 7), (DetectorKind.LOW_FLOW, 200),
    (DetectorKind.HIGH_FLOW, 800), (DetectorKind.BURST_LEAK, 4000),
])
@pytest.mark.parametrize("invalid", [-1, float("nan"), float("inf")])
def test_invalid_flow_preserves_confirmed_safety_state(kind, flow, invalid):
    engine = DetectionEngine(DetectorSettings(
        slow_detection_seconds=1, low_detection_seconds=1, high_detection_seconds=1,
        burst_detection_seconds=1, shutoff_slow=True, shutoff_low=True, shutoff_high=True,
    ))
    engine.sample(at(0), flow, None)
    engine.sample(at(1), flow, None)
    event_id = engine.runtimes[kind].event_id
    engine.sample(at(2), 0, None)
    engine.sample(at(10000), invalid, None)
    runtime = engine.runtimes[kind]
    assert runtime.phase is DetectorPhase.ACTIVE
    assert runtime.event_id == event_id
    assert runtime.quiet_since is None
    assert engine.snapshot().shutoff_request


@pytest.mark.parametrize("unit", ["L/h", "m³/h", "L/min"])
def test_negative_flow_is_not_normalized_as_quiet(unit):
    with pytest.raises(ValueError):
        normalize_flow_lph(-1, unit)


def test_reset_and_jump_do_not_create_volume_alarm():
    for next_total in (0, 1500):
        engine = DetectionEngine()
        engine.sample(at(0), 800, 1000)
        engine.sample(at(10), 800, next_total)
        assert engine.runtimes[DetectorKind.HIGH_FLOW].phase is DetectorPhase.MONITORING
        assert engine._event_volume(engine.runtimes[DetectorKind.HIGH_FLOW], next_total) < 3


def test_frozen_total_does_not_veto_volume_detection():
    engine = DetectionEngine(DetectorSettings(high_volume_l=100))
    for second in range(0, 461, 10):
        engine.sample(at(second), 800, 1000)
    assert engine.runtimes[DetectorKind.HIGH_FLOW].phase is DetectorPhase.ACTIVE


def test_total_returning_after_gap_does_not_add_unobserved_volume():
    engine = DetectionEngine()
    engine.sample(at(0), 800, 1000)
    engine.sample(at(10), 800, None)
    engine.sample(at(20), 800, 100000)
    assert engine.runtimes[DetectorKind.HIGH_FLOW].phase is DetectorPhase.MONITORING
    assert engine.snapshot(100000).active_volume_l == 0
    assert engine._event_volume(engine.runtimes[DetectorKind.HIGH_FLOW], 100000) < 5


def test_burst_ended_transition_retains_reason():
    engine = DetectionEngine()
    engine.sample(at(0), 0, None)
    engine.sample(at(10), 4000, None)
    engine.sample(at(20), 4000, None)
    engine.sample(at(30), 0, None)
    ended = engine.sample(at(90), 0, None)
    burst = next(item for item in ended if item.kind is DetectorKind.BURST_LEAK)
    assert burst.reason == "rapid_rise"
    assert engine.runtimes[DetectorKind.BURST_LEAK].reason is None


def test_out_of_order_sample_does_not_change_timers_or_volume():
    engine = DetectionEngine()
    engine.sample(at(0), 800, None)
    engine.sample(at(10), 800, None)
    before = engine.to_dict()
    assert engine.sample(at(5), 0, None) == []
    assert engine.to_dict() == before
    engine.sample(at(20), 800, None)
    assert engine.runtimes[DetectorKind.HIGH_FLOW].estimated_volume_l == pytest.approx(800/180)


def test_corrupt_runtime_keeps_active_alarm_and_repairs_identity():
    engine = DetectionEngine()
    engine.restore({"runtimes": {"burst_leak": {
        "phase": "active", "event_id": None, "started_at": "2026-10-07T00:00:00",
        "detected_at": "bad", "estimated_volume_l": "nan", "start_total_l": -1,
    }}})
    runtime = engine.runtimes[DetectorKind.BURST_LEAK]
    assert runtime.phase is DetectorPhase.ACTIVE
    assert runtime.event_id
    assert runtime.started_at is None
    assert runtime.estimated_volume_l == 0
    assert engine.snapshot().shutoff_request


def test_corrupt_learning_and_ack_are_isolated():
    learner = AdaptiveFlowLearner()
    learner.restore({"samples": [
        {"timestamp": "2026-10-07T00:00:00", "peak_lph": 100},
        {"timestamp": BASE.isoformat(), "peak_lph": "nan"},
        {"timestamp": BASE.isoformat(), "peak_lph": 200},
        {"timestamp": at(100).isoformat(), "peak_lph": 900},
    ]}, BASE)
    assert learner.snapshot(BASE).sample_count == 1
    ack = EventAcknowledgement.from_dict({
        "muted_recipients": None, "delivered_recipients": [],
        "globally_acknowledged_at": "bad", "globally_acknowledged": "false",
    })
    assert not ack.globally_acknowledged
    assert not ack.muted_recipients
    assert ack.globally_acknowledged_at is None


def test_f04_v3_floor_and_existing_f08_short_pause_behavior():
    """Approved Burst floor changes; existing Low safety net still applies."""
    engine = DetectionEngine()
    engine.sample(at(0), 0, None)
    engine.sample(at(10), 1500, None)
    engine.sample(at(20), 1500, None)
    assert engine.runtimes[DetectorKind.BURST_LEAK].phase is DetectorPhase.IDLE  # F04 V3
    engine = DetectionEngine()
    engine.sample(at(0), 200, None)
    engine.sample(at(3590), 0, None)
    engine.sample(at(3600), 0, None)
    assert engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.ACTIVE  # F08
