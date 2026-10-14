"""Tests for detector state machines."""

from datetime import UTC, datetime, timedelta

from custom_components.water_leak_detection.const import DetectorKind, DetectorPhase
from custom_components.water_leak_detection.engine import DetectionEngine, DetectorSettings


def at(seconds: int) -> datetime:
    return datetime(2026, 10, 6, tzinfo=UTC) + timedelta(seconds=seconds)


def test_slow_leak_detects_seven_lph_after_hour() -> None:
    engine = DetectionEngine()
    engine.sample(at(0), 7.0, 1000.0)
    assert engine.runtimes[DetectorKind.SLOW_LEAK].phase is DetectorPhase.MONITORING
    engine.sample(at(3599), 7.0, 1006.9)
    assert engine.runtimes[DetectorKind.SLOW_LEAK].phase is DetectorPhase.MONITORING
    engine.sample(at(3600), 7.0, 1007.0)
    assert engine.runtimes[DetectorKind.SLOW_LEAK].phase is DetectorPhase.ACTIVE


def test_slow_monitoring_requires_continuous_flow() -> None:
    engine = DetectionEngine()
    engine.sample(at(0), 7.0, None)
    engine.sample(at(1800), 0.0, None)
    assert engine.runtimes[DetectorKind.SLOW_LEAK].phase is DetectorPhase.IDLE


def test_low_flow_short_pause_does_not_reset() -> None:
    engine = DetectionEngine()
    engine.sample(at(0), 200.0, None)
    engine.sample(at(3000), 0.0, None)
    engine.sample(at(3300), 200.0, None)
    engine.sample(at(3600), 200.0, None)
    assert engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.ACTIVE


def test_low_flow_seven_minute_quiet_period_resets() -> None:
    engine = DetectionEngine()
    engine.sample(at(0), 200.0, None)
    engine.sample(at(3000), 0.0, None)
    engine.sample(at(3420), 0.0, None)
    assert engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.IDLE


def test_pool_fill_band_does_not_start_slow_or_low_when_high_is_bypassed() -> None:
    engine = DetectionEngine()
    engine.sample(at(0), 800.0, None, high_flow_bypassed=True)
    assert engine.runtimes[DetectorKind.SLOW_LEAK].phase is DetectorPhase.IDLE
    assert engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.IDLE
    assert engine.runtimes[DetectorKind.HIGH_FLOW].phase is DetectorPhase.IDLE
    assert engine.runtimes[DetectorKind.BURST_LEAK].phase is DetectorPhase.IDLE


def test_high_flow_bypass_only_resets_high_flow() -> None:
    settings = DetectorSettings(
        high_detection_seconds=10,
        burst_threshold_lph=1000,
        burst_detection_seconds=10,
    )
    engine = DetectionEngine(settings)
    engine.sample(at(0), 2500.0, None)
    engine.sample(at(10), 2500.0, None, high_flow_bypassed=True)
    assert engine.runtimes[DetectorKind.HIGH_FLOW].phase is DetectorPhase.IDLE
    assert engine.runtimes[DetectorKind.BURST_LEAK].phase is DetectorPhase.ACTIVE


def test_shutdown_mapping_is_independent() -> None:
    settings = DetectorSettings(
        slow_detection_seconds=1,
        shutoff_slow=True,
        shutoff_burst=False,
    )
    engine = DetectionEngine(settings)
    engine.sample(at(0), 10.0, None)
    engine.sample(at(1), 10.0, None)
    snapshot = engine.snapshot()
    assert snapshot.alarm_active is True
    assert snapshot.shutoff_request is True


def test_active_to_idle_transition_keeps_event_metadata() -> None:
    engine = DetectionEngine()
    engine.sample(at(0), 7.0, 1000.0)
    started = engine.sample(at(3600), 7.0, 1007.0)
    event_id = started[-1].event_id

    engine.sample(at(4200), 0.0, 1007.0)
    ended = engine.sample(at(4800), 0.0, 1007.0)[-1]

    assert ended.old_phase is DetectorPhase.ACTIVE
    assert ended.new_phase is DetectorPhase.IDLE
    assert ended.event_id == event_id
    assert ended.started_at == at(0)
    assert ended.detected_at == at(3600)
    assert ended.volume_l == 7.0


def test_unavailable_source_discards_unconfirmed_evidence() -> None:
    engine = DetectionEngine()
    engine.sample(at(0), 7.0, None)
    assert engine.runtimes[DetectorKind.SLOW_LEAK].phase is DetectorPhase.MONITORING

    engine.suspend_for_unavailable_source()

    assert engine.runtimes[DetectorKind.SLOW_LEAK].phase is DetectorPhase.IDLE
    engine.sample(at(7200), 7.0, None)
    assert engine.runtimes[DetectorKind.SLOW_LEAK].phase is DetectorPhase.MONITORING


def test_unavailable_source_preserves_confirmed_alarm() -> None:
    settings = DetectorSettings(slow_detection_seconds=1)
    engine = DetectionEngine(settings)
    engine.sample(at(0), 7.0, None)
    engine.sample(at(1), 7.0, None)
    event_id = engine.runtimes[DetectorKind.SLOW_LEAK].event_id

    engine.suspend_for_unavailable_source()

    assert engine.runtimes[DetectorKind.SLOW_LEAK].phase is DetectorPhase.ACTIVE
    assert engine.runtimes[DetectorKind.SLOW_LEAK].event_id == event_id
    assert engine.runtimes[DetectorKind.SLOW_LEAK].quiet_since is None


def test_engine_runtime_round_trip() -> None:
    settings = DetectorSettings(slow_detection_seconds=1)
    engine = DetectionEngine(settings)
    engine.sample(at(0), 10.0, 1000.0)
    engine.sample(at(1), 10.0, 1000.1)
    event_id = engine.runtimes[DetectorKind.SLOW_LEAK].event_id

    restored = DetectionEngine(settings)
    restored.restore(engine.to_dict())
    assert restored.runtimes[DetectorKind.SLOW_LEAK].phase is DetectorPhase.ACTIVE
    assert restored.runtimes[DetectorKind.SLOW_LEAK].event_id == event_id


def test_slow_candidate_resets_when_usage_enters_low_flow_range() -> None:
    engine = DetectionEngine()
    engine.sample(at(0), 7.0, None)
    engine.sample(at(1800), 200.0, None)
    assert engine.runtimes[DetectorKind.SLOW_LEAK].phase is DetectorPhase.IDLE
    assert engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.MONITORING


def test_monitoring_state_is_not_restored_across_restart_gap() -> None:
    engine = DetectionEngine()
    engine.sample(at(0), 7.0, None)
    assert engine.runtimes[DetectorKind.SLOW_LEAK].phase is DetectorPhase.MONITORING

    restored = DetectionEngine()
    restored.restore(engine.to_dict())

    assert restored.runtimes[DetectorKind.SLOW_LEAK].phase is DetectorPhase.IDLE
    assert restored.last_sample_at is None


def test_active_state_restores_but_quiet_reset_timer_does_not() -> None:
    settings = DetectorSettings(slow_detection_seconds=1)
    engine = DetectionEngine(settings)
    engine.sample(at(0), 7.0, None)
    engine.sample(at(1), 7.0, None)
    engine.sample(at(10), 0.0, None)
    assert engine.runtimes[DetectorKind.SLOW_LEAK].phase is DetectorPhase.ACTIVE
    assert engine.runtimes[DetectorKind.SLOW_LEAK].quiet_since is not None

    restored = DetectionEngine(settings)
    restored.restore(engine.to_dict())

    runtime = restored.runtimes[DetectorKind.SLOW_LEAK]
    assert runtime.phase is DetectorPhase.ACTIVE
    assert runtime.event_id is not None
    assert runtime.quiet_since is None


def test_high_flow_detects_after_duration() -> None:
    settings = DetectorSettings(
        high_threshold_lph=600,
        high_detection_seconds=60,
        high_volume_l=10_000,
        burst_threshold_lph=2000,
    )
    engine = DetectionEngine(settings)
    engine.sample(at(0), 800.0, 1000.0)
    assert engine.runtimes[DetectorKind.HIGH_FLOW].phase is DetectorPhase.MONITORING
    engine.sample(at(60), 800.0, 1013.3)
    assert engine.runtimes[DetectorKind.HIGH_FLOW].phase is DetectorPhase.ACTIVE


def test_high_flow_detects_by_total_volume_before_duration() -> None:
    settings = DetectorSettings(
        high_threshold_lph=600,
        high_detection_seconds=3600,
        high_volume_l=100,
        burst_threshold_lph=2000,
    )
    engine = DetectionEngine(settings)
    engine.sample(at(0), 800.0, 1000.0)
    engine.sample(at(300), 800.0, 1100.0)
    # F07: 66.7 L of flow evidence cannot validate a 100 L total jump.
    assert engine.runtimes[DetectorKind.HIGH_FLOW].phase is DetectorPhase.MONITORING
    engine.sample(at(450), 800.0, 1100.0, total_fresh=True)
    assert engine.runtimes[DetectorKind.HIGH_FLOW].phase is DetectorPhase.ACTIVE


def test_burst_detection_ignores_high_flow_bypass() -> None:
    settings = DetectorSettings(
        burst_threshold_lph=2000,
        burst_detection_seconds=15,
    )
    engine = DetectionEngine(settings)
    engine.sample(at(0), 2500.0, None, high_flow_bypassed=True)
    assert engine.runtimes[DetectorKind.BURST_LEAK].phase is DetectorPhase.MONITORING
    engine.sample(at(15), 2500.0, None, high_flow_bypassed=True)
    assert engine.runtimes[DetectorKind.BURST_LEAK].phase is DetectorPhase.ACTIVE


def test_burst_has_priority_over_lower_active_detector() -> None:
    settings = DetectorSettings(
        slow_detection_seconds=1,
        burst_threshold_lph=2000,
        burst_detection_seconds=1,
    )
    engine = DetectionEngine(settings)
    engine.sample(at(0), 7.0, None)
    engine.sample(at(1), 7.0, None)
    assert engine.snapshot().active_kind is DetectorKind.SLOW_LEAK

    engine.sample(at(2), 2500.0, None)
    engine.sample(at(3), 2500.0, None)

    snapshot = engine.snapshot()
    assert snapshot.active_kind is DetectorKind.BURST_LEAK
    assert snapshot.status == DetectorKind.BURST_LEAK.value


def test_burst_shutdown_request_can_be_disabled_independently() -> None:
    settings = DetectorSettings(
        burst_threshold_lph=2000,
        burst_detection_seconds=1,
        shutoff_burst=False,
    )
    engine = DetectionEngine(settings)
    engine.sample(at(0), 2500.0, None)
    engine.sample(at(1), 2500.0, None)

    snapshot = engine.snapshot()
    assert snapshot.alarm_active is True
    assert snapshot.shutoff_request is False


def test_disabling_slow_detector_clears_only_slow_state() -> None:
    settings = DetectorSettings(
        slow_detection_seconds=1,
        low_detection_seconds=3600,
    )
    engine = DetectionEngine(settings)
    engine.sample(at(0), 7.0, None)
    engine.sample(at(1), 7.0, None)
    assert engine.runtimes[DetectorKind.SLOW_LEAK].phase is DetectorPhase.ACTIVE

    engine.update_settings(
        DetectorSettings(
            slow_enabled=False,
            low_enabled=True,
            low_detection_seconds=3600,
        )
    )
    transitions = engine.sample(at(2), 7.0, None)

    assert engine.runtimes[DetectorKind.SLOW_LEAK].phase is DetectorPhase.IDLE
    assert any(
        transition.kind is DetectorKind.SLOW_LEAK
        and transition.old_phase is DetectorPhase.ACTIVE
        and transition.new_phase is DetectorPhase.IDLE
        for transition in transitions
    )


def test_disabling_low_detector_does_not_disable_burst() -> None:
    settings = DetectorSettings(
        low_enabled=False,
        burst_threshold_lph=2000,
        burst_detection_seconds=1,
    )
    engine = DetectionEngine(settings)
    engine.sample(at(0), 2500.0, None)
    engine.sample(at(1), 2500.0, None)

    assert engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.IDLE
    assert engine.runtimes[DetectorKind.BURST_LEAK].phase is DetectorPhase.ACTIVE


def test_external_adaptive_high_threshold_cannot_create_gap() -> None:
    engine = DetectionEngine()
    engine.sample(
        at(0),
        1000.0,
        None,
        effective_high_threshold_lph=1500.0,
        effective_burst_threshold_lph=2500.0,
    )

    assert engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.IDLE
    assert engine.runtimes[DetectorKind.HIGH_FLOW].phase is DetectorPhase.MONITORING
    assert engine.runtimes[DetectorKind.BURST_LEAK].phase is DetectorPhase.IDLE


def test_adaptive_high_threshold_still_detects_above_reference() -> None:
    settings = DetectorSettings(high_detection_seconds=10)
    engine = DetectionEngine(settings)
    engine.sample(
        at(0),
        1600.0,
        None,
        effective_high_threshold_lph=1500.0,
        effective_burst_threshold_lph=3000.0,
    )
    engine.sample(
        at(10),
        1600.0,
        None,
        effective_high_threshold_lph=1500.0,
        effective_burst_threshold_lph=3000.0,
    )

    assert engine.runtimes[DetectorKind.HIGH_FLOW].phase is DetectorPhase.ACTIVE


def test_rapid_rise_burst_never_triggers_below_absolute_threshold() -> None:
    settings = DetectorSettings(
        burst_threshold_lph=2000.0,
        burst_detection_seconds=30,
        burst_rate_rise_lph_10s=1000.0,
        burst_rate_confirm_seconds=10,
    )
    engine = DetectionEngine(settings)
    engine.sample(
        at(0),
        100.0,
        None,
        effective_high_threshold_lph=600.0,
        effective_burst_threshold_lph=4000.0,
    )
    engine.sample(
        at(10),
        3200.0,
        None,
        effective_high_threshold_lph=600.0,
        effective_burst_threshold_lph=4000.0,
    )

    runtime = engine.runtimes[DetectorKind.BURST_LEAK]
    assert runtime.phase is DetectorPhase.IDLE
    assert runtime.reason is None

    engine.sample(
        at(20),
        3200.0,
        None,
        effective_high_threshold_lph=600.0,
        effective_burst_threshold_lph=4000.0,
    )
    assert engine.runtimes[DetectorKind.BURST_LEAK].phase is DetectorPhase.IDLE


def test_rapid_rise_burst_ignores_high_flow_bypass() -> None:
    settings = DetectorSettings(
        burst_rate_rise_lph_10s=1000.0,
        burst_rate_confirm_seconds=10,
    )
    engine = DetectionEngine(settings)
    engine.sample(
        at(0),
        100.0,
        None,
        high_flow_bypassed=True,
        effective_high_threshold_lph=600.0,
        effective_burst_threshold_lph=4000.0,
    )
    engine.sample(
        at(10),
        4500.0,
        None,
        high_flow_bypassed=True,
        effective_high_threshold_lph=600.0,
        effective_burst_threshold_lph=4000.0,
    )
    engine.sample(
        at(20),
        4500.0,
        None,
        high_flow_bypassed=True,
        effective_high_threshold_lph=600.0,
        effective_burst_threshold_lph=4000.0,
    )

    assert engine.runtimes[DetectorKind.HIGH_FLOW].phase is DetectorPhase.IDLE
    assert engine.runtimes[DetectorKind.BURST_LEAK].phase is DetectorPhase.ACTIVE


def test_static_burst_threshold_works_without_learning_context() -> None:
    settings = DetectorSettings(
        burst_threshold_lph=2000.0,
        burst_detection_seconds=10,
    )
    engine = DetectionEngine(settings)
    engine.sample(at(0), 2500.0, None)
    engine.sample(at(10), 2500.0, None)

    assert engine.runtimes[DetectorKind.BURST_LEAK].phase is DetectorPhase.ACTIVE
