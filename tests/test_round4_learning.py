"""F15: retain admitted UTC history across observed, bounded clock rollbacks."""

from datetime import timedelta

import pytest
from test_manager_runtime import start_manager
from test_round2_measurements import fresh, measurement_origin

from custom_components.water_leak_detection.const import DOMAIN
from custom_components.water_leak_detection.learning import AdaptiveFlowLearner, LearningSample
from custom_components.water_leak_detection.manager import WaterLeakManager


@pytest.mark.parametrize("shifts", [(-3600,), (-7200,), (3600,), (3600, -7200, 1800, -3600)])
@pytest.mark.parametrize("report_after_shift", [False, True])
async def test_f15_completed_sample_then_clock_change_survives_real_unload_restore(
    runtime_hass, runtime_entry, measurement_clock, shifts, report_after_shift
):
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 50)
    for _ in range(25):
        measurement_clock.advance(5)
        await fresh(runtime_hass, manager, measurement_clock, 0)
    assert len(manager.learner.samples) == 1
    sample = manager.learner.samples[0]
    assert sample.timestamp == measurement_clock.utcnow()
    for shift in shifts:
        measurement_clock.wall_shift += shift
        measurement_clock.advance(5)
        if report_after_shift:
            await fresh(runtime_hass, manager, measurement_clock, 0)
    await manager.async_unload()
    raw = await manager._store.async_load()
    assert raw["rolling_learning"]["samples"] == [sample.to_dict()]
    if sample.timestamp > measurement_clock.utcnow():
        assert "clock_rollback" in raw["rolling_learning"]
    restored = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    await restored.async_setup()
    assert restored.learner.samples == [sample]
    # The bounded context also survives another clean restart before UTC catches up.
    await restored.async_unload()
    again = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = again
    await again.async_setup()
    assert again.learner.samples == [sample]
    assert again.learner.snapshot(sample.timestamp + timedelta(days=29)).sample_count == 1
    assert again.learner.snapshot(sample.timestamp + timedelta(days=31)).sample_count == 0


@pytest.mark.parametrize(
    "context",
    [None, {}, {"observed_at": "bad", "valid_until": "bad"},
     {"observed_at": None, "valid_until": []}],
)
def test_f15_future_sample_without_valid_clock_context_is_rejected(context):
    now = measurement_origin()
    sample = LearningSample(now + timedelta(hours=1), 50)
    learner = AdaptiveFlowLearner()
    learner.restore({"samples": [sample.to_dict()], "clock_rollback": context}, now)
    assert not learner.samples


@pytest.mark.parametrize("future", [timedelta(hours=3), timedelta(days=3650)])
def test_f15_corrupt_future_sample_outside_observed_rollback_is_rejected(future):
    now = measurement_origin()
    valid = LearningSample(now + timedelta(hours=1), 50)
    corrupt = LearningSample(now + future, 100)
    admitted = AdaptiveFlowLearner()
    admitted.samples = [valid]
    admitted.observe_clock(valid.timestamp, valid.timestamp)
    raw = admitted.to_dict(now=now, runtime_now=valid.timestamp)
    raw["samples"].append(corrupt.to_dict())
    learner = AdaptiveFlowLearner()
    learner.restore(raw, now)
    assert learner.samples == [valid]


@pytest.mark.parametrize("observed_delta,valid_delta", [(0, 25 * 3600), (60, 3600)])
def test_f15_unbounded_context_or_unobserved_offline_rollback_is_rejected(
    observed_delta, valid_delta
):
    now = measurement_origin()
    sample = LearningSample(now + timedelta(seconds=valid_delta), 50)
    learner = AdaptiveFlowLearner()
    learner.restore({
        "samples": [sample.to_dict()],
        "clock_rollback": {
            "observed_at": (now + timedelta(seconds=observed_delta)).isoformat(),
            "valid_until": sample.timestamp.isoformat(),
        },
    }, now)
    assert not learner.samples


def test_f15_serialization_cannot_legitimize_future_sample_without_observed_correction():
    now = measurement_origin()
    learner = AdaptiveFlowLearner()
    learner.samples = [LearningSample(now + timedelta(hours=1), 50)]
    raw = learner.to_dict(now=now, runtime_now=now)
    assert "clock_rollback" not in raw
    restored = AdaptiveFlowLearner()
    restored.restore(raw, now)
    assert not restored.samples


def test_f15_clock_context_never_changes_episode_or_quiet_runtime():
    now = measurement_origin()
    learner = AdaptiveFlowLearner(quiet_seconds=120)
    learner.observe(now, 50, runtime_now=now, suspicious=False, high_flow_bypassed=False)
    learner.observe(
        now + timedelta(seconds=5), 0, runtime_now=now + timedelta(seconds=5),
        suspicious=False, high_flow_bypassed=False,
    )
    episode = learner._episode
    started, quiet = episode.started_at, episode.quiet_since
    for seconds, shift in [(10, -3600), (15, 3600), (20, -7200)]:
        wall = now + timedelta(seconds=seconds + shift)
        runtime = now + timedelta(seconds=seconds)
        learner.to_dict(now=wall, runtime_now=runtime)
        learner.observe(wall, 0, runtime_now=runtime, suspicious=False, high_flow_bypassed=False)
        assert learner._episode is episode
        assert (episode.started_at, episode.quiet_since) == (started, quiet)
        assert not learner.samples
    wall = now + timedelta(seconds=125 - 7200)
    learner.observe(
        wall, 0, runtime_now=now + timedelta(seconds=125),
        suspicious=False, high_flow_bypassed=False,
    )
    assert learner.samples == [LearningSample(wall, 50)]
