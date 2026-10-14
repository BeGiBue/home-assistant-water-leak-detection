"""F08: stability accelerates Low only with continuous, time-weighted evidence."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_manager_runtime import start_manager
from test_round2_measurements import fresh

from custom_components.water_leak_detection.config_flow import WaterLeakOptionsFlow
from custom_components.water_leak_detection.const import (
    CONF_LOW_RESET_MIN,
    DEFAULT_LOW_RESET_MIN,
    DetectorKind,
    DetectorPhase,
)
from custom_components.water_leak_detection.engine import DetectionEngine, DetectorSettings

START = datetime(2026, 10, 10, tzinfo=UTC)
LOW = DetectorKind.LOW_FLOW


def report(engine, seconds, flow, credit=None):
    engine.sample(START + timedelta(seconds=seconds), flow, None, evidence_seconds=credit)
    return engine.runtimes[LOW].phase


def run(engine, start, end, interval=30, flow=250):
    for seconds in range(start, end + 1, interval):
        report(engine, seconds, flow(seconds) if callable(flow) else flow, interval)


@pytest.mark.parametrize("interval", [10, 30, 60, 120])
@pytest.mark.parametrize("flow", [250, 550, 599.999])
def test_stable_exact_early_boundary(interval, flow):
    engine = DetectionEngine()
    run(engine, 0, 1800 - interval, interval, flow)
    assert engine.runtimes[LOW].phase is DetectorPhase.MONITORING
    assert report(engine, 1800, flow, interval) is DetectorPhase.ACTIVE


@pytest.mark.parametrize("interval", [10, 30, 60, 120])
def test_variable_family_usage_keeps_normal_safety_net(interval):
    engine = DetectionEngine()
    values = [170, 350, 220, 500, 180]

    def pattern(seconds):
        return values[(seconds // 120) % len(values)]

    run(engine, 0, 3600 - interval, interval, pattern)
    assert engine.runtimes[LOW].phase is DetectorPhase.MONITORING
    assert report(engine, 3600, pattern(3600), interval) is DetectorPhase.ACTIVE


@pytest.mark.parametrize(
    "deviation,expected", [(270, True), (275, True), (276, False), (500, False)]
)
def test_tolerance_inclusive_and_large_deviations(deviation, expected):
    engine = DetectionEngine()
    # 20% of the final window differs, enough to fail when outside tolerance.
    run(engine, 0, 1800, 30, lambda seconds: deviation if seconds % 150 == 0 else 250)
    assert (engine.runtimes[LOW].phase is DetectorPhase.ACTIVE) is expected


def test_single_large_spike_is_robust_and_window_trims_partial_intervals():
    engine = DetectionEngine()
    run(engine, 0, 1770)
    assert report(engine, 1800, 500, 30) is DetectorPhase.ACTIVE
    assert sum(seconds for _, seconds in engine.low_stability_history) == 900


@pytest.mark.parametrize("quiet", [0, 19.999])
def test_quiet_reset_exact_179_180_seconds(quiet):
    engine = DetectionEngine()
    run(engine, 0, 900)
    report(engine, 910, quiet, 10)
    assert report(engine, 1089, quiet, 179) is DetectorPhase.MONITORING
    assert engine.runtimes[LOW].started_at == START
    assert report(engine, 1090, quiet, 1) is DetectorPhase.IDLE
    assert not engine.low_stability_history


@pytest.mark.parametrize("pause_flow", [0, 20, 100, 149.999])
def test_short_pause_breaks_series_without_deleting_normal_progress(pause_flow):
    engine = DetectionEngine()
    run(engine, 0, 900)
    report(engine, 901, pause_flow, 1)
    assert engine.low_stability_seconds == 0
    assert not engine.low_stability_history
    report(engine, 931, 250, 30)
    assert engine.low_stability_seconds == 0
    run(engine, 961, 1831)
    assert engine.runtimes[LOW].phase is DetectorPhase.MONITORING
    assert engine.runtimes[LOW].started_at == START
    assert engine.low_stability_seconds == 900


def test_high_boundary_discards_stability_and_low_monitoring():
    engine = DetectionEngine()
    run(engine, 0, 900, flow=599.999)
    assert report(engine, 930, 600, 30) is DetectorPhase.IDLE
    assert not engine.low_stability_history
    assert engine.runtimes[DetectorKind.HIGH_FLOW].phase is DetectorPhase.MONITORING


@pytest.mark.parametrize("invalid", [-1, float("nan"), float("inf")])
def test_invalid_engine_measurements_never_provide_stability(invalid):
    engine = DetectionEngine()
    run(engine, 0, 900)
    report(engine, 930, invalid, 30)
    assert engine.low_stability_seconds == 0
    report(engine, 1830, 250, 900)
    assert engine.low_stability_seconds == 0


@pytest.mark.parametrize("enabled,stability", [(False, True), (True, False)])
def test_disabled_paths(enabled, stability):
    engine = DetectionEngine(DetectorSettings(low_enabled=enabled, low_stability_enabled=stability))
    run(engine, 0, 1800)
    assert engine.runtimes[LOW].phase is (
        DetectorPhase.MONITORING if enabled else DetectorPhase.IDLE
    )
    assert not engine.low_stability_history


def test_active_survives_uneven_flow_and_restore_preserves_event():
    engine = DetectionEngine()
    run(engine, 0, 1800)
    event = engine.runtimes[LOW].event_id
    run(engine, 1830, 2100, flow=lambda seconds: 170 if seconds % 60 else 500)
    assert engine.runtimes[LOW].phase is DetectorPhase.ACTIVE
    restored = DetectionEngine()
    restored.restore(engine.to_dict())
    assert restored.runtimes[LOW].event_id == event
    assert restored.runtimes[LOW].phase is DetectorPhase.ACTIVE
    assert not restored.low_stability_history
    report(restored, 2200, 0, 0)
    assert report(restored, 2379, 0, 179) is DetectorPhase.ACTIVE
    assert report(restored, 2380, 0, 1) is DetectorPhase.IDLE


def test_irregular_reports_use_duration_for_median_and_share():
    engine = DetectionEngine()
    run(engine, 0, 900, 60)
    # 101 fast reports are only 101 seconds, versus 799 s at 250.
    for seconds in range(901, 1002):
        report(engine, seconds, 500, 1)
    run(engine, 1020, 1800, 60)
    assert engine.runtimes[LOW].phase is DetectorPhase.MONITORING
    assert not engine._low_is_stable()  # 101/900 > 10%, independent of count.
    report(engine, 1811, 250, 11)
    assert engine.runtimes[LOW].phase is DetectorPhase.ACTIVE  # exactly 90/900 outliers


def test_many_fast_reports_cannot_outvote_long_confirmed_intervals():
    engine = DetectionEngine()
    run(engine, 0, 900, 60)
    for seconds in range(901, 961):
        report(engine, seconds, 500, 1)
    run(engine, 1020, 1800, 60)
    assert engine.runtimes[LOW].phase is DetectorPhase.ACTIVE


@pytest.mark.parametrize("invalid", ["unavailable", "unknown", "-1", "nan", "inf", "bad"])
async def test_outage_retains_round7_progress_but_restarts_stability(
    runtime_hass, runtime_entry, measurement_clock, invalid
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 250)
    for _ in range(15):
        measurement_clock.advance(60)
        await fresh(runtime_hass, manager, measurement_clock, 250)
    runtime = manager.engine.runtimes[LOW]
    progress = (manager.timer_now - runtime.started_at).total_seconds()
    assert manager.engine.low_stability_seconds == 900
    measurement_clock.advance(1)
    await fresh(runtime_hass, manager, measurement_clock, invalid)
    assert not manager.engine.low_stability_history
    assert runtime.phase is DetectorPhase.MONITORING
    measurement_clock.advance(1800)
    await fresh(runtime_hass, manager, measurement_clock, 250)
    assert manager._flow_evidence.credited_seconds == 0
    assert manager.engine.low_stability_seconds == 0
    assert (manager.timer_now - runtime.started_at).total_seconds() == progress
    for _ in range(15):
        measurement_clock.advance(60)
        await fresh(runtime_hass, manager, measurement_clock, 250)
    assert runtime.phase is DetectorPhase.MONITORING
    assert manager.engine.low_stability_seconds == 900


async def test_internal_ticks_do_not_mature_stability(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 250)
    for _ in range(29):
        measurement_clock.advance(60)
        await fresh(runtime_hass, manager, measurement_clock, 250)
    for _ in range(100):
        measurement_clock.advance(10)
        await manager._async_tick(measurement_clock.utcnow())
    assert manager.engine.low_stability_seconds == 1740
    assert manager.engine.runtimes[LOW].phase is DetectorPhase.MONITORING


@pytest.mark.parametrize("saved,expected", [(None, 3), (7, 7)])
async def test_default_reset_and_explicit_legacy_value(
    runtime_hass, runtime_entry, measurement_clock, saved, expected
):
    if saved is not None:
        runtime_hass.config_entries.async_update_entry(
            runtime_entry, options={CONF_LOW_RESET_MIN: saved}
        )
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 250)
    assert manager.engine.settings.low_reset_seconds == expected * 60
    assert DEFAULT_LOW_RESET_MIN == 3


@pytest.mark.parametrize("lang", ["de", "en"])
def test_translations_cover_expert_fields_and_validation(lang):
    path = Path("custom_components/water_leak_detection/translations") / f"{lang}.json"
    data = json.loads(path.read_text())["options"]
    for suffix in [
        "enabled",
        "early_minutes",
        "window_minutes",
        "relative_percent",
        "absolute_lph",
        "required_percent",
    ]:
        assert data["step"]["expert"]["data"][f"low_stability_{suffix}"]
    assert data["error"]["invalid_low_stability"]


@pytest.mark.parametrize(
    "key,value",
    [
        ("window_minutes", 0),
        ("window_minutes", 31),
        ("early_minutes", 60),
        ("relative_percent", 0),
        ("absolute_lph", -1),
        ("required_percent", 0),
        ("required_percent", 101),
        ("relative_percent", float("nan")),
    ],
)
def test_expert_validation(key, value):
    values = dict(
        slow_threshold_lph=3,
        low_threshold_lph=150,
        high_threshold_lph=600,
        burst_threshold_lph=2000,
        low_quiet_lph=20,
        high_quiet_lph=100,
        burst_reset_lph=500,
        low_detection_minutes=60,
    )
    assert WaterLeakOptionsFlow._validate_expert_options(values) == {}
    values[f"low_stability_{key}"] = value
    assert WaterLeakOptionsFlow._validate_expert_options(values) == {
        "base": "invalid_low_stability"
    }


def test_custom_early_time_window_and_absolute_tolerance():
    engine = DetectionEngine(
        DetectorSettings(
            low_stability_early_seconds=600,
            low_stability_window_seconds=300,
            low_stability_relative_percent=1,
            low_stability_absolute_lph=20,
            low_stability_required_percent=95,
        )
    )
    run(engine, 0, 570, flow=lambda seconds: 260 if seconds % 60 else 250)
    assert engine.runtimes[LOW].phase is DetectorPhase.MONITORING
    assert report(engine, 600, 250, 30) is DetectorPhase.ACTIVE


async def test_expert_schema_defaults_save_and_runtime_wiring(runtime_hass, runtime_entry):
    from test_config_runtime import options_flow

    flow = options_flow(runtime_hass, runtime_entry)
    form = await flow.async_step_expert()
    values = form["data_schema"]({})
    assert values["low_stability_enabled"] is True
    assert values["low_stability_early_minutes"] == 30
    assert values["low_stability_window_minutes"] == 15
    assert values["low_stability_relative_percent"] == 10
    assert values["low_stability_absolute_lph"] == 20
    assert values["low_stability_required_percent"] == 90
    values.update(
        low_stability_early_minutes=20,
        low_stability_window_minutes=10,
        low_stability_relative_percent=8,
        low_stability_absolute_lph=15,
        low_stability_required_percent=95,
    )
    result = await flow.async_step_expert(values)
    assert result["type"] == "menu"
    from custom_components.water_leak_detection.manager import WaterLeakManager

    settings = WaterLeakManager(runtime_hass, runtime_entry).engine.settings
    assert settings.low_stability_early_seconds == 1200
    assert settings.low_stability_window_seconds == 600
    assert settings.low_stability_relative_percent == 8
    assert settings.low_stability_absolute_lph == 15
    assert settings.low_stability_required_percent == 95


async def test_explicit_source_max_age_is_not_relaxed(
    runtime_hass, runtime_entry, measurement_clock
):
    runtime_hass.config_entries.async_update_entry(
        runtime_entry, options={"source_max_age_seconds": 30, "source_gap_policy_explicit": True}
    )
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 250)
    measurement_clock.advance(10)
    await fresh(runtime_hass, manager, measurement_clock, 250)
    assert manager.engine.low_stability_seconds == 10
    measurement_clock.advance(120)
    await fresh(runtime_hass, manager, measurement_clock, 250)
    assert manager._flow_evidence.credited_seconds == 0
    assert manager.engine.low_stability_seconds == 0
    measurement_clock.advance(10)
    await fresh(runtime_hass, manager, measurement_clock, 250)
    assert manager.engine.low_stability_seconds == 10


def test_settings_disable_and_reenable_cannot_reuse_old_stability():
    engine = DetectionEngine()
    run(engine, 0, 900)
    engine.settings.low_enabled = False
    engine.apply_controls(START + timedelta(seconds=901), high_flow_bypassed=False)
    assert not engine.low_stability_history
    engine.settings.low_enabled = True
    report(engine, 930, 250, 30)
    assert engine.low_stability_seconds == 0
    run(engine, 960, 2700)
    assert engine.runtimes[LOW].phase is DetectorPhase.MONITORING
    assert report(engine, 2730, 250, 30) is DetectorPhase.ACTIVE


def test_zero_credit_gap_and_clock_rollback_do_not_accumulate_stability():
    engine = DetectionEngine()
    run(engine, 0, 900)
    report(engine, 899, 250, 100)
    assert engine.low_stability_seconds == 900
    report(engine, 1800, 250, 0)
    assert engine.low_stability_seconds == 0
    report(engine, 1830, 250, 30)
    assert engine.low_stability_seconds == 30


async def test_fractional_monotonic_origin_keeps_exact_30s_series(
    runtime_hass, runtime_entry, measurement_clock
):
    measurement_clock.seconds = 0.1
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 250)
    started = manager.engine.runtimes[LOW].started_at
    for index in range(60):
        measurement_clock.advance(30)
        await fresh(runtime_hass, manager, measurement_clock, 250)
        assert manager.engine.low_stability_seconds == (index + 1) * 30
        assert manager.engine.runtimes[LOW].started_at == started
        assert manager.engine.runtimes[LOW].phase is (
            DetectorPhase.ACTIVE if index == 59 else DetectorPhase.MONITORING
        )


async def test_submicrosecond_rounding_is_not_outage(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 250)
    started = manager.engine.runtimes[LOW].started_at
    previous = 0
    for index in range(60):
        measurement_clock.advance(30.0000001)
        await fresh(runtime_hass, manager, measurement_clock, 250)
        assert manager.engine.low_stability_seconds > previous
        assert manager.engine.runtimes[LOW].started_at == started
        assert manager.engine.last_flow_lph == 250
        assert manager.engine.runtimes[LOW].phase is (
            DetectorPhase.ACTIVE if index == 59 else DetectorPhase.MONITORING
        )
        previous = manager.engine.low_stability_seconds


@pytest.mark.parametrize("difference", [1e-10, 1e-7, 1e-6])
def test_rounding_preserves_quiet_history_and_monitoring_start(difference):
    engine = DetectionEngine()
    report(engine, 0, 250)
    low = engine.runtimes[LOW]
    low.quiet_since = START  # Existing quiet evidence must not be erased by rounding.
    report(engine, 30, 0, 30 - difference)
    assert low.started_at == START
    assert low.quiet_since == START
    assert engine.last_flow_lph == 0
    assert low.phase is DetectorPhase.MONITORING


def test_real_gap_just_above_rounding_tolerance_still_interrupts():
    from custom_components.water_leak_detection.engine import EVIDENCE_TIME_TOLERANCE_SECONDS

    engine = DetectionEngine()
    run(engine, 0, 900)
    low = engine.runtimes[LOW]
    low.quiet_since = START
    gap = EVIDENCE_TIME_TOLERANCE_SECONDS * 1.5  # 3 us: already a genuine uncredited gap.
    report(engine, 930, 250, 30 - gap)
    assert engine.low_stability_seconds == 0
    assert not engine.low_stability_history
    assert low.started_at == START + timedelta(seconds=gap)
    assert low.quiet_since is None
    assert low.phase is DetectorPhase.MONITORING


@pytest.mark.parametrize("gap", [3e-6, 0.001, 1.0])
def test_rapid_rise_history_cannot_bridge_real_unknown_gap(gap):
    engine = DetectionEngine(DetectorSettings(burst_rate_rise_lph_10s=100))
    report(engine, 0, 0)
    report(engine, 10, 4000, 10 - gap)
    assert engine.runtimes[DetectorKind.BURST_LEAK].phase is DetectorPhase.MONITORING
    assert engine.runtimes[DetectorKind.BURST_LEAK].reason == "absolute_flow"
    assert engine.burst_rapid_evidence_seconds is None


def test_rounding_preserves_existing_rapid_rise_evidence():
    engine = DetectionEngine(DetectorSettings(burst_rate_rise_lph_10s=100))
    report(engine, 0, 0)
    report(engine, 10, 4000, 10 - 1e-7)
    assert engine.runtimes[DetectorKind.BURST_LEAK].phase is DetectorPhase.MONITORING
    assert engine.runtimes[DetectorKind.BURST_LEAK].reason == "rapid_rise"


def test_zero_credit_is_not_promoted_even_inside_rounding_tolerance():
    engine = DetectionEngine()
    run(engine, 0, 900)
    engine.pause_source_evidence()
    report(engine, 900.000001, 250, 0)
    assert engine.low_stability_seconds == 0
    assert engine.runtimes[LOW].started_at == START + timedelta(microseconds=1)


@pytest.mark.parametrize("normal", [10, 20, 30, 60])
async def test_legacy_short_normal_defaults_are_valid(runtime_hass, runtime_entry, normal):
    from test_config_runtime import options_flow

    from custom_components.water_leak_detection.manager import WaterLeakManager

    expected = {10: (5, 2.5), 20: (10, 5), 30: (15, 7.5), 60: (30, 15)}[normal]
    runtime_hass.config_entries.async_update_entry(
        runtime_entry, options={"low_detection_minutes": normal}
    )
    settings = WaterLeakManager(runtime_hass, runtime_entry).engine.settings
    form = await options_flow(runtime_hass, runtime_entry).async_step_expert()
    values = form["data_schema"]({})
    actual = values["low_stability_early_minutes"], values["low_stability_window_minutes"]
    assert actual == expected
    assert actual == (
        settings.low_stability_early_seconds / 60,
        settings.low_stability_window_seconds / 60,
    )
    assert 0 < actual[1] <= actual[0] < normal
    assert WaterLeakOptionsFlow._validate_expert_options(values) == {}
    assert dict(runtime_entry.options) == {"low_detection_minutes": normal}


async def test_disabled_stability_can_save_short_normal(runtime_hass, runtime_entry):
    from test_config_runtime import options_flow

    from custom_components.water_leak_detection.manager import WaterLeakManager

    options = dict(
        low_detection_minutes=10,
        low_stability_enabled=False,
        low_stability_early_minutes=30,
        low_stability_window_minutes=15,
    )
    runtime_hass.config_entries.async_update_entry(runtime_entry, options=options)
    flow = options_flow(runtime_hass, runtime_entry)
    form = await flow.async_step_expert()
    values = form["data_schema"]({})
    assert WaterLeakOptionsFlow._validate_expert_options(values) == {}
    result = await flow.async_step_expert(values)
    assert result["type"] == "menu"
    settings = WaterLeakManager(runtime_hass, runtime_entry).engine.settings
    assert settings.low_stability_enabled is False
    assert settings.low_stability_early_seconds == 1800
    assert settings.low_stability_window_seconds == 900
    engine = DetectionEngine(settings)
    run(engine, 0, 570)
    assert engine.runtimes[LOW].phase is DetectorPhase.MONITORING
    assert not engine.low_stability_history
    assert report(engine, 600, 250, 30) is DetectorPhase.ACTIVE  # normal path only
    values["low_stability_enabled"] = True
    result = await flow.async_step_expert(values)
    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_low_stability"}
    assert runtime_entry.options["low_stability_enabled"] is False
    assert runtime_entry.options["low_stability_early_minutes"] == 30
    assert runtime_entry.options["low_stability_window_minutes"] == 15


@pytest.mark.parametrize(
    "explicit,expected",
    [
        ({"low_stability_early_minutes": 7, "low_stability_window_minutes": 3}, (7, 3)),
        ({"low_stability_early_minutes": 4}, (4, 2)),
        ({"low_stability_window_minutes": 1}, (5, 1)),
    ],
)
async def test_explicit_stability_times_are_preserved_in_ui_and_runtime(
    runtime_hass, runtime_entry, explicit, expected
):
    from test_config_runtime import options_flow

    from custom_components.water_leak_detection.manager import WaterLeakManager

    saved = {"low_detection_minutes": 10, **explicit}
    runtime_hass.config_entries.async_update_entry(runtime_entry, options=saved)
    settings = WaterLeakManager(runtime_hass, runtime_entry).engine.settings
    form = await options_flow(runtime_hass, runtime_entry).async_step_expert()
    values = form["data_schema"]({})
    assert (
        values["low_stability_early_minutes"],
        values["low_stability_window_minutes"],
    ) == expected
    assert (settings.low_stability_early_seconds, settings.low_stability_window_seconds) == (
        expected[0] * 60,
        expected[1] * 60,
    )
    assert dict(runtime_entry.options) == saved


@pytest.mark.parametrize("normal,expected", [(1, (0.5, 0.2)), (3, (1.5, 0.7)), (7, (3.5, 1.7))])
async def test_missing_defaults_use_valid_ui_resolution(
    runtime_hass, runtime_entry, normal, expected
):
    from test_config_runtime import options_flow

    from custom_components.water_leak_detection.manager import WaterLeakManager

    runtime_hass.config_entries.async_update_entry(
        runtime_entry, options={"low_detection_minutes": normal}
    )
    form = await options_flow(runtime_hass, runtime_entry).async_step_expert()
    values = form["data_schema"]({})
    actual = values["low_stability_early_minutes"], values["low_stability_window_minutes"]
    assert actual == expected
    assert WaterLeakOptionsFlow._validate_expert_options(values) == {}
    settings = WaterLeakManager(runtime_hass, runtime_entry).engine.settings
    assert (settings.low_stability_early_seconds, settings.low_stability_window_seconds) == (
        expected[0] * 60,
        expected[1] * 60,
    )
