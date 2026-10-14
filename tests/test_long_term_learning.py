"""Exercise the production V3 learner, including years, ratchets, identity and F15."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from itertools import permutations
from random import Random

import pytest

from custom_components.water_leak_detection.long_term_learning import (
    MAX_LONG_TERM_HISTORY,
    HighEpisode,
    LongTermHighLearner,
)

NOW = datetime(2026, 10, 11, tzinfo=UTC)


def learner():
    return LongTermHighLearner("source", "epoch")


def admit(target, peaks, base=3500, start=NOW):
    for index, peak in enumerate(peaks):
        target.add_candidate(start + timedelta(seconds=index), peak, base)
    return target


@pytest.mark.parametrize("peaks", list(permutations((3000, 3300, 3450))))
def test_inclusive_cluster_all_orders_and_original_timestamps(peaks):
    target = admit(learner(), peaks)
    assert target.confirmed_long_term_normal_max_lph == 3450
    assert sorted(r.peak_lph for r in target.confirmed_high_history) == [3000, 3300, 3450]
    assert sorted(r.timestamp for r in target.confirmed_high_history) == [
        NOW + timedelta(seconds=i) for i in range(3)
    ]


@pytest.mark.parametrize("count", [1, 2])
def test_one_or_two_episodes_never_confirm(count):
    target = admit(learner(), [3300] * count)
    assert target.confirmed_long_term_normal_max_lph is None
    assert len(target.pending_high_candidates) == count


@pytest.mark.parametrize("peak", [3499.999, 3500, 3500.001, 3800, 50000])
def test_configured_base_is_strict_admission_anchor(peak):
    target = admit(learner(), [peak] * 3)
    assert (target.confirmed_long_term_normal_max_lph == peak) is (peak < 3500)


def test_no_self_reinforcing_ratchet_and_every_raise_requires_three_new_episodes():
    target = admit(learner(), [3000] * 3)
    for count in range(1, 4):
        target.add_candidate(NOW + timedelta(days=count), 3450, 3500)
        assert target.confirmed_long_term_normal_max_lph == (3000 if count < 3 else 3450)
    admit(target, [3800] * 3, start=NOW + timedelta(days=10))
    assert target.confirmed_long_term_normal_max_lph == 3450
    assert len(target.confirmed_high_history) == 6


def test_fourth_lower_peak_does_not_reuse_previous_confirmation():
    target = admit(learner(), [750, 780, 800])
    target.add_candidate(NOW + timedelta(days=1), 770, 3500)
    assert target.confirmed_long_term_normal_max_lph == 800
    assert len(target.confirmed_high_history) == 3


@pytest.mark.parametrize("days", [(0, 31, 365), (0, 365, 730), (0, 730, 3650)])
def test_non_expiring_history_confirms_across_years(days):
    target = learner()
    for day in days:
        target.add_candidate(NOW + timedelta(days=day), 3300, 3500)
    assert target.confirmed_long_term_normal_max_lph == 3300


def test_reduced_base_revalidates_pending_but_does_not_reduce_valid_summary():
    target = admit(learner(), [4000] * 3, 5000)
    admit(target, [4400, 4500], 5000, NOW + timedelta(days=1))
    target.promote(NOW + timedelta(days=2), 3500)
    assert not target.pending_high_candidates
    assert target.confirmed_long_term_normal_max_lph == 4000
    restored = learner()
    restored.restore(
        target.to_dict(now=NOW + timedelta(days=2), runtime_now=NOW), NOW + timedelta(days=2), 3500
    )
    assert restored.confirmed_long_term_normal_max_lph == 4000


def test_summary_survives_history_cleanup_and_repeated_restore_without_reconstruction():
    target = admit(learner(), [3300] * 3)
    target.confirmed_high_history.clear()
    raw = target.to_dict(now=NOW + timedelta(days=2), runtime_now=NOW)
    for _ in range(3):
        restored = learner()
        restored.restore(raw, NOW + timedelta(days=2), 3500)
        assert restored.confirmed_long_term_normal_max_lph == 3300
        assert not restored.confirmed_high_history
        raw = restored.to_dict(now=NOW + timedelta(days=2), runtime_now=NOW)


@pytest.mark.parametrize("damage", [True, False, -1, 0, "nan", "inf", 1.7e308, 50000])
def test_malformed_summary_never_disables_burst(damage):
    target = admit(learner(), [3300] * 3)
    raw = target.to_dict(now=NOW + timedelta(days=1), runtime_now=NOW)
    raw["confirmed_long_term_normal_max_lph"] = damage
    target.restore(raw, NOW + timedelta(days=1), 3500)
    assert target.confirmed_long_term_normal_max_lph is None


@pytest.mark.parametrize(
    "field", ["episode_id", "source_generation", "learning_epoch", "timestamp", "peak_lph"]
)
def test_conflicting_identity_is_quarantined_in_both_input_orders(field):
    record = HighEpisode("episode", "source", "epoch", NOW, 3300).to_dict()
    other = deepcopy(record)
    other[field] = {
        "episode_id": "episode",
        "source_generation": "replacement",
        "learning_epoch": "other",
        "timestamp": (NOW - timedelta(seconds=1)).isoformat(),
        "peak_lph": 3350,
    }[field]
    for records in ([record, other], [other, record]):
        target = learner()
        raw = target.to_dict(now=NOW, runtime_now=NOW)
        raw["pending_high_candidates"] = records
        target.restore(raw, NOW, 3500)
        assert len(target.pending_high_candidates) == (1 if field == "episode_id" else 0)


@pytest.mark.parametrize("order", ["ascending", "descending", "shuffled"])
def test_validate_then_keep_newest_4096_with_no_ttl(order):
    records = [
        HighEpisode(f"ep_{i}", "source", "epoch", NOW - timedelta(days=i), 3300).to_dict()
        for i in range(4100)
    ]
    if order == "descending":
        records.reverse()
    elif order == "shuffled":
        Random(4).shuffle(records)
    raw = learner().to_dict(now=NOW, runtime_now=NOW)
    raw["pending_high_candidates"] = [None] * 4096 + records
    target = learner()
    target.restore(raw, NOW, 3500)
    assert len(target.pending_high_candidates) == MAX_LONG_TERM_HISTORY
    assert {r.episode_id for r in target.pending_high_candidates} == {
        f"ep_{i}" for i in range(4096)
    }


@pytest.mark.parametrize("shift", [0.5, 3600, 86400, 172800, 432000])
def test_rollback_keeps_summary_and_exact_future_permissions_only_up_to_one_day(shift):
    target = admit(learner(), [3000] * 3, start=NOW - timedelta(days=1))
    admit(target, [3300, 3300], start=NOW - timedelta(seconds=1))
    target.observe_clock(NOW, NOW)
    wall = NOW - timedelta(seconds=shift)
    raw = target.to_dict(now=wall, runtime_now=NOW)
    restored = learner()
    restored.restore(raw, wall, 3500)
    assert restored.confirmed_long_term_normal_max_lph == 3000
    assert len(restored.pending_high_candidates) == (2 if shift <= 86400 else 0)
    restored.promote(NOW, 3500)
    restored.add_candidate(NOW, 3300, 3500)
    assert restored.confirmed_long_term_normal_max_lph == (3300 if shift <= 86400 else 3000)


@pytest.mark.parametrize("role", ["pending", "confirmed"])
@pytest.mark.parametrize("mutation", ["none", "other_role", "peak", "id", "generation", "time"])
def test_future_permission_is_exact_and_never_crosses_history_lists(role, mutation):
    target = admit(learner(), [3000] * 3, start=NOW - timedelta(seconds=3))
    target.add_candidate(NOW, 3300, 3500)
    target.observe_clock(NOW, NOW)
    wall = NOW - timedelta(seconds=10)
    raw = target.to_dict(now=wall, runtime_now=NOW)
    field = "pending_high_candidates" if role == "pending" else "confirmed_high_history"
    key = f"high_{role}_fingerprints"
    if mutation == "none":
        raw["clock_rollback"][key] = []
    elif mutation == "other_role":
        other = "confirmed" if role == "pending" else "pending"
        raw["clock_rollback"][key] = raw["clock_rollback"][f"high_{other}_fingerprints"]
    else:
        change = {
            "peak": ("peak_lph", 3400),
            "id": ("episode_id", "new"),
            "generation": ("source_generation", "new"),
            "time": ("timestamp", (NOW + timedelta(seconds=1)).isoformat()),
        }[mutation]
        for record in raw[field]:
            record[change[0]] = change[1]
    restored = learner()
    restored.restore(raw, wall, 3500)
    assert not (
        restored.pending_high_candidates if role == "pending" else restored.confirmed_high_history
    )
    restored.promote(NOW + timedelta(seconds=30), 3500)
    assert restored.confirmed_long_term_normal_max_lph == 3000


def test_fingerprint_canonicalizes_integer_float_and_utc_offset():
    record = HighEpisode("episode", "source", "epoch", NOW, 3300).to_dict()
    other = {**record, "peak_lph": 3300.0, "timestamp": "2026-10-11T02:00:00+02:00"}
    assert HighEpisode.parse(record).fingerprint == HighEpisode.parse(other).fingerprint
