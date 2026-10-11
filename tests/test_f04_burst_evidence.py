"""Production dual deadlines, current absolute floor, gaps, and option invalidation."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from math import nextafter

import pytest

from custom_components.water_leak_detection.const import DetectorKind, DetectorPhase
from custom_components.water_leak_detection.engine import DetectionEngine, DetectorSettings

NOW = datetime(2026, 10, 11, tzinfo=UTC)
BURST = DetectorKind.BURST_LEAK


def report(engine, second, flow, **kwargs):
    engine.sample(NOW + timedelta(seconds=second), flow, None, **kwargs)
    return engine.runtimes[BURST].phase


@pytest.mark.parametrize("flow", [2000, 2800, 3000, 3300, 3499.999])
def test_rapid_never_creates_burst_below_effective_threshold(flow):
    engine = DetectionEngine()
    report(engine, 0, 0)
    for time in (5, 15, 30):
        assert report(engine, time, flow) is DetectorPhase.IDLE


@pytest.mark.parametrize("flow", [3500, 3600])
def test_rapid_qualifies_at_absolute_boundary_and_needs_full_ten_seconds(flow):
    engine = DetectionEngine()
    report(engine, 0, 0)
    assert report(engine, 10, flow) is DetectorPhase.MONITORING
    assert report(engine, 19.999999, flow) is DetectorPhase.MONITORING
    assert report(engine, 20, flow) is DetectorPhase.ACTIVE
    assert engine.runtimes[BURST].reason == "rapid_rise"


@pytest.mark.parametrize("qualification,deadline", [(5, 15), (15, 25), (25, 30), (29, 30)])
def test_late_rapid_uses_earlier_deadline_without_backdating_or_extension(qualification, deadline):
    engine = DetectionEngine()
    assert report(engine, 0, 3500) is DetectorPhase.MONITORING
    # The qualifying rise is large enough at each report interval.
    report(engine, qualification, 3500 + qualification * 100)
    assert (
        report(engine, deadline - 0.000001, 3500 + qualification * 100) is DetectorPhase.MONITORING
    )
    assert report(engine, deadline, 3500 + qualification * 100) is DetectorPhase.ACTIVE
    assert engine.runtimes[BURST].reason == ("rapid_rise" if deadline < 30 else "absolute_flow")


def test_normal_confirmation_requires_thirty_seconds():
    engine = DetectionEngine()
    report(engine, 0, 3500)
    assert report(engine, 29.999999, 3500) is DetectorPhase.MONITORING
    assert report(engine, 30, 3500) is DetectorPhase.ACTIVE


@pytest.mark.parametrize("gap", [0.000003, 1, 10, 100, 10000])
def test_authoritative_gap_discards_both_deadlines_and_previous_rise(gap):
    engine = DetectionEngine()
    report(engine, 0, 0)
    report(engine, 10, 3500)
    report(engine, 15, 3500)
    assert report(engine, 20 + gap, 3500, evidence_seconds=5) is DetectorPhase.MONITORING
    assert engine.last_evidence_gap
    assert engine.burst_normal_evidence_seconds == 0
    assert engine.burst_rapid_evidence_seconds is None
    assert report(engine, 49 + gap, 3500) is DetectorPhase.MONITORING
    assert report(engine, 50 + gap, 3500) is DetectorPhase.ACTIVE


@pytest.mark.parametrize("difference", [0.000001, 0.000002])
def test_existing_two_microsecond_tolerance_is_preserved(difference):
    engine = DetectionEngine()
    report(engine, 0, 3500)
    # Round credit toward the interval so the binary representation itself is
    # within the unchanged absolute 2µs tolerance (not microscopically above it).
    report(engine, 10, 3500, evidence_seconds=nextafter(10 - difference, float("inf")))
    assert not engine.last_evidence_gap
    assert engine.burst_normal_evidence_seconds == 10
    assert report(engine, 30, 3500, evidence_seconds=20) is DetectorPhase.ACTIVE


@pytest.mark.parametrize(
    "field,value",
    [
        ("burst_threshold_lph", 4000),
        ("burst_rate_rise_lph_10s", 2000),
        ("burst_detection_seconds", 40),
        ("burst_rate_confirm_seconds", 15),
    ],
)
@pytest.mark.parametrize("active", [False, True])
def test_relevant_options_reset_only_unconfirmed_monitoring(field, value, active):
    engine = DetectionEngine()
    report(engine, 0, 3500)
    report(engine, 30 if active else 20, 3500)
    engine.update_settings(replace(engine.settings, **{field: value}))
    assert engine.runtimes[BURST].phase is (DetectorPhase.ACTIVE if active else DetectorPhase.IDLE)


def test_unchanged_options_do_not_restart_evidence():
    engine = DetectionEngine()
    report(engine, 0, 3500)
    report(engine, 20, 3500)
    engine.update_settings(replace(engine.settings))
    assert report(engine, 30, 3500) is DetectorPhase.ACTIVE


def test_changed_effective_threshold_starts_fresh_under_current_rules():
    engine = DetectionEngine()
    report(engine, 0, 4000, effective_burst_threshold_lph=3500)
    report(engine, 20, 4000, effective_burst_threshold_lph=3500)
    report(engine, 30, 4000, effective_burst_threshold_lph=3900)
    assert engine.runtimes[BURST].phase is DetectorPhase.MONITORING
    assert engine.burst_normal_evidence_seconds == 0
    assert report(engine, 60, 4000, effective_burst_threshold_lph=3900) is DetectorPhase.ACTIVE


def test_bypass_never_suppresses_burst_or_rapid():
    engine = DetectionEngine(DetectorSettings())
    report(engine, 0, 0, high_flow_bypassed=True)
    report(engine, 10, 4000, high_flow_bypassed=True)
    assert report(engine, 20, 4000, high_flow_bypassed=True) is DetectorPhase.ACTIVE
