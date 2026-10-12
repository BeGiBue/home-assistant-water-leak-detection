"""Production independent source lifecycle, restart nonce and replacement safety."""

from datetime import UTC, datetime

import pytest

from custom_components.water_leak_detection.external_leaks import (
    ExternalLeakController,
    ExternalPhase,
)
from custom_components.water_leak_detection.source_identity import SourceIdentity

NOW = datetime(2026, 10, 11, tzinfo=UTC)


def controller(contributes=True):
    target = ExternalLeakController()
    target.configure("a", identity("g1"), contributes, "Kitchen")
    return target


def identity(generation, entity="binary_sensor.kitchen"):
    return SourceIdentity(entity, "registry", "signature", generation, "epoch")


@pytest.mark.parametrize("initial", list(ExternalPhase))
@pytest.mark.parametrize("state", ["on", "off", "unknown", "unavailable"])
def test_every_lifecycle_transition(initial, state):
    target = controller()
    if initial is not ExternalPhase.ARMED:
        target.observe("a", "on", NOW)
    if initial is ExternalPhase.RESET_WAITING_FOR_OFF:
        target.reset("a", "g1", target.sources["a"].event_id)
    target.observe("a", state, NOW)
    expected = (
        ExternalPhase.ARMED
        if state == "off"
        else (ExternalPhase.ACTIVE if initial is ExternalPhase.ARMED and state == "on" else initial)
    )
    assert target.sources["a"].phase is expected
    assert bool(target.active_events()) is (expected is ExternalPhase.ACTIVE)


@pytest.mark.parametrize("phase", list(ExternalPhase))
def test_restart_preserves_lifecycle_and_event_but_rotates_active_nonce(phase):
    target = controller()
    if phase is not ExternalPhase.ARMED:
        target.observe("a", "on", NOW)
    if phase is ExternalPhase.RESET_WAITING_FOR_OFF:
        target.reset("a", "g1", target.sources["a"].event_id)
    before = target.sources["a"]
    raw = target.to_dict()
    restored = ExternalLeakController()
    restored.restore(raw, NOW)
    after = restored.sources["a"]
    assert after.phase is phase
    assert after.event_id == before.event_id
    if phase is ExternalPhase.ACTIVE:
        assert after.reset_nonce != before.reset_nonce
        assert len(after.reset_nonce) >= 22
    restored.observe("a", "on", NOW)
    assert restored.sources["a"].phase is (
        ExternalPhase.ACTIVE if phase is ExternalPhase.ARMED else phase
    )


@pytest.mark.parametrize("phase", list(ExternalPhase))
def test_rename_preserves_generation_lifecycle_and_event(phase):
    target = controller()
    target.sources["a"].phase = phase
    target.configure("a", identity("g1", "binary_sensor.renamed"), True, "Renamed")
    assert target.sources["a"].phase is phase
    assert target.sources["a"].identity.generation == "g1"


@pytest.mark.parametrize("phase", list(ExternalPhase))
def test_remove_and_deliberate_replace_block_only_active(phase):
    target = controller()
    target.sources["a"].phase = phase
    if phase is ExternalPhase.ACTIVE:
        with pytest.raises(ValueError, match="external_source_active"):
            target.remove("a")
        with pytest.raises(ValueError, match="external_source_active"):
            target.configure("a", identity("g2"), True, "New")
    else:
        target.configure("a", identity("g2"), True, "New")
        assert target.sources["a"].phase is ExternalPhase.ARMED
        assert target.sources["a"].event_id is None
        target.remove("a")
        assert not target.sources


def test_forced_replacement_keeps_old_active_tombstone_and_new_source_independent():
    target = controller()
    target.observe("a", "on", NOW)
    old = target.sources["a"].event_id
    target.configure("a", identity("g2"), True, "New", forced=True)
    assert target.sources["a"].phase is ExternalPhase.ARMED
    assert old in target.active_events()
    assert target.shutoff_request
    target.observe("a", "off", NOW)
    assert old in target.active_events()
    target.observe("a", "on", NOW)
    new = target.sources["a"].event_id
    target.reset("a", "g1", old)
    assert old not in target.active_events()
    assert new in target.active_events()
    assert target.shutoff_request


@pytest.mark.parametrize("contributes", [False, True])
def test_parallel_sources_reset_only_the_exact_event(contributes):
    target = controller()
    target.configure("b", identity("g2"), contributes, "Bathroom")
    target.observe("a", "on", NOW)
    target.observe("b", "on", NOW)
    target.reset("a", "g1", target.sources["a"].event_id)
    assert len(target.active_events()) == 1
    assert target.shutoff_request is contributes
    assert target.sources["b"].phase is ExternalPhase.ACTIVE


def test_public_data_never_contains_secrets_and_private_staging_does_not_release_alarm():
    target = controller()
    target.observe("a", "on", NOW)
    staged = target.copy()
    staged.reset("a", "g1", target.sources["a"].event_id)
    assert target.shutoff_request
    assert not staged.shutoff_request
    assert "reset_nonce" not in target.sources["a"].public_payload()


@pytest.mark.parametrize("field", ["generation", "learning_epoch", "source_id", "entity_id"])
@pytest.mark.parametrize("value", [None, [], False])
def test_damaged_active_routing_is_quarantined_as_alarm_not_dry(field, value):
    controller = ExternalLeakController()
    source = SourceIdentity("binary_sensor.kitchen", "registry", "signature", "generation", "epoch")
    controller.configure("kitchen", source, True, "Kitchen")
    controller.observe("kitchen", "on", NOW)
    raw = controller.to_dict()
    raw["external_sources"][0][field] = value
    restored = ExternalLeakController()
    restored.restore(raw, NOW)
    assert restored.shutoff_request
    assert len(restored.active_events()) == 1
    assert not restored.sources
