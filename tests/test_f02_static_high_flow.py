"""F02: static High boundary, unchanged confirmation and adaptive Burst context."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from custom_components.water_leak_detection.config_flow import WaterLeakOptionsFlow
from custom_components.water_leak_detection.const import (
    CONF_BURST_LEARNED_MULTIPLIER,
    CONF_HIGH_LEARNED_MULTIPLIER,
    CONF_HIGH_THRESHOLD_LPH,
    CONF_MANUAL_MAX_FLOW_LPH,
    CONF_PIPE_DIAMETER_MM,
    CONF_STATIC_PRESSURE_BAR,
    DetectorKind,
    DetectorPhase,
)
from custom_components.water_leak_detection.engine import DetectionEngine, DetectorSettings
from custom_components.water_leak_detection.learning import LearningConfidence, LearningSnapshot
from custom_components.water_leak_detection.manager import WaterLeakManager
from custom_components.water_leak_detection.sensor import EffectiveHighThresholdSensor


def at(seconds):
    return datetime(2026, 10, 10, tzinfo=UTC) + timedelta(seconds=seconds)


def phase(engine, kind):
    return engine.runtimes[kind].phase


@pytest.mark.parametrize("high", [150.001, 600, 900, 1999, 9999])
@pytest.mark.parametrize("offset", [-0.001, 0, 0.001])
def test_exact_low_high_boundary_without_gap(high, offset):
    engine = DetectionEngine(DetectorSettings(high_threshold_lph=high))
    engine.sample(at(0), high + offset, None, effective_high_threshold_lph=high * 10)
    assert phase(engine, DetectorKind.LOW_FLOW) is (
        DetectorPhase.MONITORING if offset < 0 else DetectorPhase.IDLE
    )
    assert phase(engine, DetectorKind.HIGH_FLOW) is (
        DetectorPhase.IDLE if offset < 0 else DetectorPhase.MONITORING
    )


@pytest.mark.parametrize("external_high", [1, 600, 1500, 50000])
@pytest.mark.parametrize("flow", [800, 1000, 1200])
def test_external_context_cannot_shift_high_in_either_direction(external_high, flow):
    engine = DetectionEngine()
    engine.sample(at(0), flow, None, effective_high_threshold_lph=external_high)
    assert phase(engine, DetectorKind.HIGH_FLOW) is DetectorPhase.MONITORING
    assert phase(engine, DetectorKind.LOW_FLOW) is DetectorPhase.IDLE


@pytest.mark.parametrize("confidence", [LearningConfidence.LEARNING, LearningConfidence.RELIABLE])
@pytest.mark.parametrize("learned", [1200, 1250, 5000])
@pytest.mark.parametrize("options", [
    {},
    {CONF_MANUAL_MAX_FLOW_LPH: 3000},
    {CONF_PIPE_DIAMETER_MM: 100, CONF_STATIC_PRESSURE_BAR: 12},
    {CONF_HIGH_LEARNED_MULTIPLIER: "obsolete value"},
    {CONF_HIGH_THRESHOLD_LPH: 900},
])
def test_manager_keeps_high_static_and_burst_adaptive(confidence, learned, options):
    manager = WaterLeakManager.__new__(WaterLeakManager)
    manager.entry = SimpleNamespace(options=options)
    snapshot = LearningSnapshot(
        learned_max_lph=learned, short_reference_lph=learned,
        long_reference_lph=learned, sample_count=30, coverage_days=20,
        age_days=20, window_days=30, confidence=confidence,
    )
    manager.learner = SimpleNamespace(snapshot=lambda _now: snapshot)
    thresholds = manager.adaptive_thresholds(at(0))
    high = options.get(CONF_HIGH_THRESHOLD_LPH, 600)
    assert thresholds.effective_high_lph == high
    assert thresholds.normal_reference_lph is not None
    assert thresholds.effective_burst_lph >= 2000
    if confidence is LearningConfidence.RELIABLE and learned == 1200 and not options:
        assert thresholds.effective_burst_lph == 3500
    for flow in (800, 1000, 1200):
        engine = DetectionEngine(DetectorSettings(high_threshold_lph=high))
        engine.sample(at(0), flow, None,
                      effective_high_threshold_lph=thresholds.effective_high_lph,
                      effective_burst_threshold_lph=thresholds.effective_burst_lph)
        assert phase(engine, DetectorKind.HIGH_FLOW) is (
            DetectorPhase.MONITORING if flow >= high else DetectorPhase.IDLE
        )


def test_high_duration_confirmation_unchanged():
    engine = DetectionEngine()
    for second in range(0, 2700, 30):
        engine.sample(at(second), 600.001, None)
        assert phase(engine, DetectorKind.HIGH_FLOW) is DetectorPhase.MONITORING
    engine.sample(at(2700), 600.001, None)
    assert phase(engine, DetectorKind.HIGH_FLOW) is DetectorPhase.ACTIVE


def test_high_volume_confirmation_unchanged():
    engine = DetectionEngine()
    engine.sample(at(0), 1000, 10000)
    for second in range(30, 1800, 30):
        engine.sample(at(second), 1000, 10000 + second / 3.6)
        assert phase(engine, DetectorKind.HIGH_FLOW) is DetectorPhase.MONITORING
    engine.sample(at(1800), 1000, 10500)
    assert phase(engine, DetectorKind.HIGH_FLOW) is DetectorPhase.ACTIVE


def test_short_legitimate_use_resets_after_existing_quiet_window():
    engine = DetectionEngine()
    engine.sample(at(0), 800, None)
    engine.sample(at(30), 800, None)
    assert phase(engine, DetectorKind.HIGH_FLOW) is DetectorPhase.MONITORING
    for second in range(60, 360, 30):
        engine.sample(at(second), 0, None)
        assert phase(engine, DetectorKind.HIGH_FLOW) is DetectorPhase.MONITORING
    engine.sample(at(360), 0, None)
    assert phase(engine, DetectorKind.HIGH_FLOW) is DetectorPhase.IDLE


def test_bypass_suppresses_high_but_not_burst_and_static_boundary_returns():
    engine = DetectionEngine()
    engine.sample(at(0), 4000, None, high_flow_bypassed=True)
    engine.sample(at(30), 4000, None, high_flow_bypassed=True)
    assert phase(engine, DetectorKind.HIGH_FLOW) is DetectorPhase.IDLE
    assert phase(engine, DetectorKind.BURST_LEAK) is DetectorPhase.ACTIVE
    engine.sample(at(31), 600, None, effective_high_threshold_lph=1500)
    assert phase(engine, DetectorKind.HIGH_FLOW) is DetectorPhase.MONITORING


def test_rapid_burst_requires_absolute_threshold_with_static_high_reference():
    engine = DetectionEngine()
    engine.sample(at(0), 0, None, effective_high_threshold_lph=1500)
    engine.sample(at(10), 1500, None, effective_high_threshold_lph=1500)
    assert phase(engine, DetectorKind.BURST_LEAK) is DetectorPhase.IDLE
    engine.sample(at(20), 1500, None, effective_high_threshold_lph=1500)
    assert phase(engine, DetectorKind.BURST_LEAK) is DetectorPhase.IDLE


async def test_options_hide_legacy_multiplier_and_preserve_saved_value(runtime_hass, runtime_entry):
    runtime_hass.config_entries.async_update_entry(
        runtime_entry, options={CONF_HIGH_LEARNED_MULTIPLIER: 3.0}
    )
    flow = WaterLeakOptionsFlow()
    flow.hass = runtime_hass
    flow.handler = runtime_entry.entry_id
    form = await flow.async_step_expert()
    assert CONF_HIGH_LEARNED_MULTIPLIER not in {str(key) for key in form["data_schema"].schema}
    values = {
        "slow_threshold_lph": 3, "low_threshold_lph": 150,
        "low_quiet_lph": 20, "high_threshold_lph": 600,
        "high_quiet_lph": 100, "burst_threshold_lph": 2000,
        "burst_reset_lph": 500,
    }
    values[CONF_BURST_LEARNED_MULTIPLIER] = 1.1
    assert flow._validate_expert_options(values) == {}
    await flow.async_step_expert(values)
    assert runtime_entry.options[CONF_HIGH_LEARNED_MULTIPLIER] == 3.0


def test_effective_high_entity_identity_is_preserved():
    manager = SimpleNamespace(
        entry=SimpleNamespace(entry_id="f02"),
        adaptive_thresholds=lambda: SimpleNamespace(effective_high_lph=600),
    )
    sensor = EffectiveHighThresholdSensor(manager)
    assert sensor.translation_key == "effective_high_threshold"
    assert sensor.unique_id == "f02_effective_high_threshold"
    assert sensor.native_value == 600
