"""Independent controls; production modules and actual HA atomic disk writes."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.util.file import WriteError
from test_f04_security_review_adversarial import start

from custom_components.water_leak_detection.const import (
    ACTION_EXTERNAL_RESET,
    CONF_EXTERNAL_SENSORS,
    DetectorKind,
    DetectorPhase,
)
from custom_components.water_leak_detection.engine import DetectionEngine
from custom_components.water_leak_detection.external_leaks import ExternalPhase
from custom_components.water_leak_detection.long_term_learning import (
    HighEpisode,
    LongTermHighLearner,
)


async def setup(hass, entry, clock):
    registry = er.async_get(hass)
    for name in ("a", "b"):
        registry.async_get_or_create("binary_sensor", "test", name, suggested_object_id=name)
        hass.states.async_set("binary_sensor." + name, "off")
    hass.states.async_set("device_tracker.phone", "home")
    hass.config_entries.async_update_entry(
        entry,
        options={
            CONF_EXTERNAL_SENSORS: [
                {"id": name, "entity_id": "binary_sensor." + name} for name in ("a", "b")
            ],
            "notification_recipients": [
                {
                    "id": "phone",
                    "name": "Phone",
                    "notify_service": "notify.mobile_app_phone",
                    "tracker_entity": "device_tracker.phone",
                    "token": "token",
                    "allow_external_reset": True,
                    "allow_global_ack": True,
                }
            ],
        },
    )
    manager = await start(hass, entry, clock)
    hass.states.async_set("binary_sensor.a", "on")
    await hass.async_block_till_done()
    return manager


def action(m):
    s = m.external.sources["a"]
    return dict(
        action_kind=ACTION_EXTERNAL_RESET,
        config_entry_id=m.entry.entry_id,
        source_id="a",
        source_generation=s.identity.generation,
        event_id=s.event_id,
        recipient_id="phone",
        recipient_token="token",
        reset_nonce=s.reset_nonce,
    )


@pytest.mark.parametrize(
    "field",
    [
        "action_kind",
        "config_entry_id",
        "source_id",
        "source_generation",
        "event_id",
        "recipient_id",
        "recipient_token",
        "reset_nonce",
    ],
)
async def test_wrong_binding_retains_disk_and_alarm(
    runtime_hass, runtime_entry, measurement_clock, field
):
    m = await setup(runtime_hass, runtime_entry, measurement_clock)
    await m._async_save()
    before = Path(m._store.path).read_bytes()
    p = action(m)
    p[field] = "wrong"
    assert not await m.async_external_reset(p)
    assert m.alarm_active and m.shutoff_request
    assert Path(m._store.path).read_bytes() == before


@pytest.mark.parametrize("state", ["not_home", "away", "unknown", "unavailable"])
async def test_actual_tracker_rejection(runtime_hass, runtime_entry, measurement_clock, state):
    m = await setup(runtime_hass, runtime_entry, measurement_clock)
    runtime_hass.states.async_set("device_tracker.phone", state)
    assert not await m.async_external_reset(action(m))
    assert m.shutoff_request


async def test_physical_writer_error_no_release_or_success(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch
):
    m = await setup(runtime_hass, runtime_entry, measurement_clock)
    await m._async_save()
    before = Path(m._store.path).read_bytes()

    def fail(*args):
        raise WriteError("independent writer failure")

    with monkeypatch.context() as patch:
        patch.setattr(m._store, "_write_prepared_data", fail)
        assert not await m.async_external_reset(action(m))
    assert m.alarm_active and m.shutoff_request
    assert Path(m._store.path).read_bytes() == before


async def test_actual_event_bus_reset_other_source_replay(
    runtime_hass, runtime_entry, measurement_clock
):
    m = await setup(runtime_hass, runtime_entry, measurement_clock)
    runtime_hass.states.async_set("binary_sensor.b", "on")
    await runtime_hass.async_block_till_done()
    old = action(m)
    assert await m.async_external_reset(old)
    assert not await m.async_external_reset(old)
    assert m.external.sources["b"].phase is ExternalPhase.ACTIVE
    assert m.shutoff_request
    runtime_hass.states.async_set("binary_sensor.a", "off")
    runtime_hass.states.async_set("binary_sensor.a", "on")
    await runtime_hass.async_block_till_done()
    assert m.external.sources["a"].event_id != old["event_id"]
    assert not await m.async_external_reset(old)
    assert len(m.active_events()) == 2


NOW = datetime(2026, 10, 12, tzinfo=UTC)


@pytest.mark.parametrize("order", ["ascending", "descending", "shuffle"])
def test_shared_cap_and_direct_maintenance_determinism(order):
    learner = LongTermHighLearner("generation", "epoch")
    for i in range(3):
        learner.add_candidate(
            NOW - timedelta(days=2, seconds=3 - i), 3000, 3500, episode_id=f"old_{i}"
        )
    raw = learner.to_dict(now=NOW, runtime_now=NOW)
    confirmed = [
        HighEpisode(
            f"c_{i}", "generation", "epoch", NOW - timedelta(seconds=8200 - 2 * i), 3000
        ).to_dict()
        for i in range(4100)
    ]
    pending = [
        HighEpisode(
            f"p_{i}", "generation", "epoch", NOW - timedelta(seconds=8199 - 2 * i), 3300
        ).to_dict()
        for i in range(4100)
    ]
    if order == "descending":
        confirmed.reverse()
        pending.reverse()
    if order == "shuffle":
        Random(42).shuffle(confirmed)
        Random(43).shuffle(pending)
    raw["pending_high_candidates"] = [None] * 4096 + pending
    raw["confirmed_high_history"] = confirmed
    learner.restore(raw, NOW, 3500)
    ids = {r.episode_id for r in learner.pending_high_candidates + learner.confirmed_high_history}
    assert ids == {f"{prefix}_{i}" for prefix in ["p", "c"] for i in range(2052, 4100)}
    learner.maintain(NOW, 3500, promote=False)
    assert ids == {
        r.episode_id for r in learner.pending_high_candidates + learner.confirmed_high_history
    }
    assert learner.confirmed_long_term_normal_max_lph == 3000


@pytest.mark.parametrize("shift", [0.5, 3600, 86400, 172800, 432000])
def test_summary_rollback_no_ttl_no_derivation(shift):
    learner = LongTermHighLearner("generation", "epoch")
    for i in range(3):
        learner.add_candidate(NOW - timedelta(seconds=3 - i), 3300, 3500)
    learner.observe_clock(NOW, NOW)
    raw = learner.to_dict(now=NOW - timedelta(seconds=shift), runtime_now=NOW)
    r = LongTermHighLearner("generation", "epoch")
    r.restore(raw, NOW - timedelta(seconds=shift), 3500)
    assert r.confirmed_long_term_normal_max_lph == 3300
    r.confirmed_high_history.clear()
    r.maintain(NOW + timedelta(days=500), 3500)
    assert r.confirmed_long_term_normal_max_lph == 3300


@pytest.mark.parametrize(
    "base,peaks,expected",
    [
        (3500, [3300] * 3 + [3800] * 3, 3300),
        (3500, [3000] * 3 + [3450], 3000),
        (3500, [3000] * 3 + [3300, 3350, 3400], 3400),
        (3500, [3000, 3300, 3450], 3450),
        (3500, [3000, 3300, 3450.000001], None),
    ],
)
def test_anchor_new_votes_inclusive_ratio(base, peaks, expected):
    learner = LongTermHighLearner("generation", "epoch")
    for i, p in enumerate(peaks):
        learner.add_candidate(NOW + timedelta(seconds=i), p, base, episode_id=f"ep_{i}")
    assert learner.confirmed_long_term_normal_max_lph == expected


@pytest.mark.parametrize("qualification,expected", [(5, 15), (15, 25), (25, 30), (29, 30)])
def test_burst_earliest_deadline(qualification, expected):
    e = DetectionEngine()
    e.sample(NOW, 3500, None)
    e.sample(NOW + timedelta(seconds=qualification), 3500 + 100 * qualification, None)
    e.sample(NOW + timedelta(seconds=expected - 0.000001), 3500 + 100 * qualification, None)
    assert e.runtimes[DetectorKind.BURST_LEAK].phase is DetectorPhase.MONITORING
    e.sample(NOW + timedelta(seconds=expected), 3500 + 100 * qualification, None)
    assert e.runtimes[DetectorKind.BURST_LEAK].phase is DetectorPhase.ACTIVE


@pytest.mark.parametrize("role", ["pending", "confirmed"])
@pytest.mark.parametrize("permission", ["correct", "opposite", "mutated"])
def test_exact_role_future_permissions_without_count_shortcut(role, permission):
    learner = LongTermHighLearner("generation", "epoch")
    for i in range(3):
        learner.add_candidate(NOW - timedelta(seconds=3 - i), 3000, 3500, episode_id=f"c_{i}")
    learner.confirmed_high_history = learner.confirmed_high_history[-1:]
    learner.add_candidate(NOW, 3300, 3500, episode_id="p")
    learner.observe_clock(NOW, NOW)
    wall = NOW - timedelta(seconds=10)
    raw = learner.to_dict(now=wall, runtime_now=NOW)
    key = f"high_{role}_fingerprints"
    if permission == "opposite":
        other = "pending" if role == "confirmed" else "confirmed"
        raw["clock_rollback"][key] = raw["clock_rollback"][f"high_{other}_fingerprints"]
    if permission == "mutated":
        raw["clock_rollback"][key] = ["0" * 64]
    r = LongTermHighLearner("generation", "epoch")
    r.restore(raw, wall, 3500)
    records = r.pending_high_candidates if role == "pending" else r.confirmed_high_history
    assert bool(records) == (permission == "correct")
    assert r.confirmed_long_term_normal_max_lph == 3000
    r.promote(wall, 3500)
    assert r.confirmed_long_term_normal_max_lph == 3000
    r.promote(NOW + timedelta(seconds=30), 3500)
    assert r.confirmed_long_term_normal_max_lph == 3000
