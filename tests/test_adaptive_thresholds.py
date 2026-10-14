"""Tests for adaptive threshold calculation."""

from datetime import UTC, datetime
from types import SimpleNamespace

from custom_components.water_leak_detection.const import (
    CONF_BURST_LEARNED_MULTIPLIER,
    CONF_BURST_THRESHOLD_LPH,
    CONF_HIGH_LEARNED_MULTIPLIER,
    CONF_HIGH_THRESHOLD_LPH,
    CONF_HYDRAULIC_BURST_FRACTION,
    CONF_MANUAL_MAX_FLOW_LPH,
    CONF_PIPE_DIAMETER_MM,
    CONF_STATIC_PRESSURE_BAR,
)
from custom_components.water_leak_detection.learning import (
    LearningConfidence,
    LearningSnapshot,
)
from custom_components.water_leak_detection.manager import WaterLeakManager

NOW = datetime(2026, 10, 6, tzinfo=UTC)


def _manager_with_learning(
    confidence: LearningConfidence,
    learned_max_lph: float | None,
    *,
    options: dict[str, float] | None = None,
) -> WaterLeakManager:
    manager = WaterLeakManager.__new__(WaterLeakManager)
    manager.entry = SimpleNamespace(options={CONF_BURST_THRESHOLD_LPH: 2000, **(options or {})})
    snapshot = LearningSnapshot(
        learned_max_lph=learned_max_lph,
        short_reference_lph=learned_max_lph,
        long_reference_lph=learned_max_lph,
        sample_count=30,
        coverage_days=20,
        age_days=20,
        window_days=30,
        confidence=confidence,
    )
    manager.learner = SimpleNamespace(snapshot=lambda _now: snapshot)
    return manager


def test_insufficient_learning_does_not_raise_safety_thresholds() -> None:
    manager = _manager_with_learning(
        LearningConfidence.INSUFFICIENT,
        1800.0,
    )

    thresholds = manager.adaptive_thresholds(NOW)

    assert thresholds.normal_reference_lph is None
    assert thresholds.effective_high_lph == 600.0
    assert thresholds.effective_burst_lph == 2000.0


def test_learning_confidence_uses_damped_reference() -> None:
    manager = _manager_with_learning(
        LearningConfidence.LEARNING,
        1200.0,
    )

    thresholds = manager.adaptive_thresholds(NOW)

    assert thresholds.normal_reference_lph == 1020.0
    assert thresholds.effective_high_lph == 600.0


def test_reliable_learning_uses_full_reference() -> None:
    manager = _manager_with_learning(
        LearningConfidence.RELIABLE,
        1200.0,
    )

    thresholds = manager.adaptive_thresholds(NOW)

    assert thresholds.normal_reference_lph == 1200.0
    assert thresholds.effective_high_lph == 600.0
    assert thresholds.effective_burst_lph == 2160.0


def test_manual_reference_is_used_even_before_learning_is_reliable() -> None:
    manager = _manager_with_learning(
        LearningConfidence.INSUFFICIENT,
        700.0,
        options={CONF_MANUAL_MAX_FLOW_LPH: 1500.0},
    )

    thresholds = manager.adaptive_thresholds(NOW)

    assert thresholds.normal_reference_lph == 1500.0
    assert thresholds.effective_high_lph == 600.0
    assert thresholds.effective_burst_lph == 2700.0


def test_hydraulic_plausibility_caps_excessive_learned_burst_threshold() -> None:
    manager = _manager_with_learning(
        LearningConfidence.RELIABLE,
        5000.0,
        options={
            CONF_HIGH_THRESHOLD_LPH: 600.0,
            CONF_BURST_THRESHOLD_LPH: 2000.0,
            CONF_HIGH_LEARNED_MULTIPLIER: 1.1,
            CONF_BURST_LEARNED_MULTIPLIER: 2.0,
            CONF_PIPE_DIAMETER_MM: 25.0,
            CONF_STATIC_PRESSURE_BAR: 3.5,
            CONF_HYDRAULIC_BURST_FRACTION: 0.75,
        },
    )

    thresholds = manager.adaptive_thresholds(NOW)

    assert thresholds.hydraulic_reference_lph > 5000.0
    assert thresholds.effective_burst_lph < 10000.0
    assert thresholds.effective_burst_lph >= thresholds.effective_high_lph
