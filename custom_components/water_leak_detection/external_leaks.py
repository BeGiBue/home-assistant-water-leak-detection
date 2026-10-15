"""Independent external sensor lifecycles and generation-bound alarm tombstones."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from secrets import token_urlsafe
from typing import Any

from .source_identity import SourceIdentity, new_id, valid_id
from .validation import parse_datetime


class ExternalPhase(StrEnum):
    ARMED = "ARMED"
    ACTIVE = "ACTIVE"
    RESET_WAITING_FOR_OFF = "RESET_WAITING_FOR_OFF"


def validate_external_snapshot(raw: dict) -> None:
    """Reject contradictory safety roles before deleting any alarm identity.

    The ledger contains only retained ACTIVE generations: an authorized
    tombstone reset removes its record. A valid enum alone cannot prove that
    such an alarm ended. Raise into the Store recovery barrier, preserving the
    original event, time, generation, conflict and shutoff data byte for byte.
    Retained records must be interpretable without inventing alarm identities;
    their ledger role is safety evidence even when phase/event fields are lost.
    """
    for role in ("external_sources", "external_alarm_ledger"):
        for record in raw.get(role, []):
            if role == "external_alarm_ledger" or record.get("tombstone") is True:
                _validate_retained_alarm(record)
            elif role == "external_sources":
                # F04-FSR-H01: a configured source's own record is safety
                # evidence as well. A damaged one must not become ARMED
                # (dropped) or an alarm with an invented identity.
                _validate_source_record(record)
            if record.get("phase") not in (
                ExternalPhase.ARMED.value,
                ExternalPhase.RESET_WAITING_FOR_OFF.value,
            ):
                continue
            if (
                role == "external_alarm_ledger"
                or record.get("tombstone") is True
                or record.get("identity_conflict") is True
                or record.get("event_id") is not None
                or record.get("reset_nonce") is not None
                or (
                    record.get("phase") == ExternalPhase.ARMED.value
                    and record.get("started_at") is not None
                )
            ):
                raise ValueError("Contradictory external alarm identity; restore a verified backup")
            # WAITING legitimately retains started_at after a committed reset,
            # but owns no active event/nonce and is never a retained tombstone.


def _validate_retained_alarm(record: dict) -> None:
    """Require a reliable retained identity before parsing or capability rotation."""
    # A committed tombstone reset removes its record. Never let damaged fields
    # become None/continue or invented IDs in the subsequent permissive parser.
    if (
        record.get("phase") != ExternalPhase.ACTIVE.value
        or not all(
            valid_id(record.get(key))
            for key in ("event_id", "source_id", "generation", "learning_epoch")
        )
        or parse_datetime(record.get("started_at")) is None
        or not isinstance(record.get("entity_id"), str)
        or not record["entity_id"].startswith("binary_sensor.")
        or not isinstance(record.get("contributes_to_shutoff"), bool)
        or not isinstance(record.get("tombstone", False), bool)
        or not isinstance(record.get("identity_conflict", False), bool)
    ):
        raise ValueError(
            "Contradictory or uninterpretable retained external alarm; restore a verified backup"
        )


_SOURCE_DAMAGED = "Uninterpretable external source record (F04-FSR-H01); restore a verified backup"


def _optional(record: dict, key: str, kind: type) -> bool:
    """Absent (older writers) or None, else exactly the expected type."""
    value = record.get(key)
    return value is None or (isinstance(value, kind) and not isinstance(value, bool))


def _validate_source_record(record: dict) -> None:
    """Every field a writer of this schema produces must be interpretable.

    The phase decides whether an alarm and its shutoff contribution exist, so it
    is never guessed: a missing/unknown phase, an ACTIVE record without a valid
    Event-ID or aware start time, or damaged identity, routing or safety flags
    raise into the Store recovery barrier (alarm and shutoff held, original bytes
    kept, reset/ACK blocked, repair issue). Missing optional metadata of older
    writers (name, registry data, flags) is accepted; a wrong type is not.
    """
    phase = record.get("phase")
    started = record.get("started_at")
    if (
        phase not in tuple(item.value for item in ExternalPhase)
        or not all(
            valid_id(record.get(key)) for key in ("source_id", "generation", "learning_epoch")
        )
        or not isinstance(record.get("entity_id"), str)
        or not record["entity_id"].startswith("binary_sensor.")
        or not isinstance(record.get("contributes_to_shutoff"), bool)
        or not isinstance(record.get("tombstone", False), bool)
        or not isinstance(record.get("identity_conflict", False), bool)
        or not _optional(record, "name", str)
        or not _optional(record, "registry_id", str)
        or not _optional(record, "identity_signature", str)
        or not _optional(record, "reset_nonce", str)
        or (started is not None and parse_datetime(started) is None)
        or (
            phase == ExternalPhase.ACTIVE.value
            and (not valid_id(record.get("event_id")) or parse_datetime(started) is None)
        )
    ):
        raise ValueError(_SOURCE_DAMAGED)


@dataclass(slots=True)
class ExternalSource:
    source_id: str
    identity: SourceIdentity
    contributes_to_shutoff: bool = True
    phase: ExternalPhase = ExternalPhase.ARMED
    event_id: str | None = None
    reset_nonce: str | None = None
    started_at: datetime | None = None
    name: str = ""
    tombstone: bool = False
    identity_conflict: bool = False

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            **self.identity.to_dict(),
            "contributes_to_shutoff": self.contributes_to_shutoff,
            "phase": self.phase.value,
            "event_id": self.event_id,
            "reset_nonce": self.reset_nonce,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "name": self.name,
            "tombstone": self.tombstone,
            "identity_conflict": self.identity_conflict,
        }

    def public_payload(self) -> dict:
        """Event/diagnostic data never exposes a reset nonce or recipient token."""
        return {
            "type": "external_leak",
            "source_id": self.source_id,
            "source_generation": self.identity.generation,
            "event_id": self.event_id,
            "source_entity": self.identity.entity_id,
            "source_name": self.name,
            "phase": self.phase.value,
            "tombstone": self.tombstone,
            "identity_conflict": self.identity_conflict,
            "contributes_to_shutoff": self.contributes_to_shutoff,
            "started_at": self.started_at.isoformat() if self.started_at else None,
        }


class ExternalLeakController:
    """Pure states; the manager commits a private copy before publishing releases."""

    def __init__(self) -> None:
        self.sources: dict[str, ExternalSource] = {}
        self.tombstones: dict[tuple[str, str], ExternalSource] = {}
        self.quarantined_sources: list[ExternalSource] = []

    def copy(self) -> ExternalLeakController:
        return deepcopy(self)

    def all_sources(self) -> list[ExternalSource]:
        # During a forced replacement the same object briefly has two handles.
        # Distinct restored records remain distinct, even with identical keys.
        records = [*self.sources.values(), *self.tombstones.values(), *self.quarantined_sources]
        return list({id(source): source for source in records}.values())

    @property
    def has_active_sources(self) -> bool:
        return any(s.phase is ExternalPhase.ACTIVE for s in self.all_sources())

    @property
    def conflicted_event_ids(self) -> set[str]:
        return {s.event_id for s in self.all_sources() if s.identity_conflict and s.event_id}

    def quarantine_conflicts(self, hydraulic_event_ids=()) -> set[str]:
        """Preserve every safety record; ambiguous identities grant no capabilities.

        The flag is sticky and persisted: OFF/actions cannot guess which damaged
        record owns an identity. A verified backup is required to resolve it.
        """
        events = {}
        identities = {}
        hydraulic = set(hydraulic_event_ids)
        for source in self.all_sources():
            identities.setdefault((source.source_id, source.identity.generation), []).append(source)
            if source.phase is ExternalPhase.ACTIVE and source.event_id:
                events.setdefault(source.event_id, []).append(source)
        groups = [g for g in identities.values() if len(g) > 1]
        groups.extend(g for event, g in events.items() if len(g) > 1 or event in hydraulic)
        for group in groups:
            for source in group:
                source.identity_conflict = True
                source.reset_nonce = None
        for source in self.all_sources():
            if source.identity_conflict:
                source.reset_nonce = None
        return self.conflicted_event_ids

    def retain_tombstone(self, source: ExternalSource) -> None:
        """A repeated ledger key must never overwrite another ACTIVE record."""
        source.tombstone = True
        key = (source.source_id, source.identity.generation)
        current = self.tombstones.get(key)
        if current is None or current is source:
            self.tombstones[key] = source
        else:
            self.quarantined_sources.append(source)

    def active_events(self) -> dict[str, ExternalSource]:
        records = self.all_sources()
        events = Counter(s.event_id for s in records if s.phase is ExternalPhase.ACTIVE)
        identities = Counter((s.source_id, s.identity.generation) for s in records)
        return {
            source.event_id: source
            for source in records
            if source.phase is ExternalPhase.ACTIVE
            and source.event_id
            and not source.identity_conflict
            and events[source.event_id] == 1
            and identities[(source.source_id, source.identity.generation)] == 1
        }

    @property
    def shutoff_request(self) -> bool:
        return any(
            source.contributes_to_shutoff
            for source in self.all_sources()
            if source.phase is ExternalPhase.ACTIVE
        )

    def configure(
        self,
        source_id: str,
        identity: SourceIdentity,
        contributes: bool,
        name: str,
        *,
        forced: bool = False,
    ) -> None:
        current = self.sources.get(source_id)
        if current and current.identity.generation == identity.generation:
            current.identity = identity
            current.name = name
            if not current.identity_conflict:
                current.contributes_to_shutoff = contributes
            return
        if current and current.phase is ExternalPhase.ACTIVE:
            if not forced:
                raise ValueError("external_source_active")
            self.retain_tombstone(current)
        self.sources[source_id] = ExternalSource(source_id, identity, contributes, name=name)
        self.quarantine_conflicts()

    def remove(self, source_id: str) -> None:
        source = self.sources.get(source_id)
        if source and source.phase is ExternalPhase.ACTIVE:
            raise ValueError("external_source_active")
        self.sources.pop(source_id, None)

    def observe(self, source_id: str, state: str, now: datetime) -> None:
        source = self.sources.get(source_id)
        if source is None or source.identity_conflict:
            return
        if state == "on" and source.phase is ExternalPhase.ARMED:
            source.phase = ExternalPhase.ACTIVE
            source.event_id = f"external_{new_id()}"
            source.reset_nonce = token_urlsafe(32)
            source.started_at = now
        elif state == "off":
            source.phase = ExternalPhase.ARMED
            source.event_id = None
            source.reset_nonce = None
            source.started_at = None
        self.quarantine_conflicts()
        # unknown/unavailable never means OFF, including after a manual reset.

    def event_for(self, source_id: str, generation: str, event_id: str) -> ExternalSource | None:
        source = self.active_events().get(event_id)
        return (
            source
            if source
            and (source.source_id == source_id and source.identity.generation == generation)
            else None
        )

    def reset(self, source_id: str, generation: str, event_id: str) -> None:
        source = self.event_for(source_id, generation, event_id)
        if source is None:
            raise ValueError("external_event_not_active")
        source.phase = ExternalPhase.RESET_WAITING_FOR_OFF
        source.event_id = None
        source.reset_nonce = None
        if source.tombstone:
            self.tombstones.pop((source_id, generation), None)

    def to_dict(self) -> dict:
        return {
            "external_sources": [source.to_dict() for _, source in sorted(self.sources.items())],
            "external_alarm_ledger": [
                source.to_dict() for _, source in sorted(self.tombstones.items())
            ]
            + [source.to_dict() for source in self.quarantined_sources],
        }

    def restore(self, raw: Any, now: datetime) -> None:
        """Restore safety independently of current options; rotate all ACTIVE nonces.

        Never discard a valid active alarm simply to satisfy a count cap: active
        tombstones are safety evidence, not expendable statistical history.
        """
        if isinstance(raw, dict):
            validate_external_snapshot(raw)
        self.sources.clear()
        self.tombstones.clear()
        self.quarantined_sources.clear()
        if not isinstance(raw, dict):
            return
        for field in ("external_sources", "external_alarm_ledger"):
            records = raw.get(field)
            if not isinstance(records, list):
                continue
            for item in records:
                source = _restore_source(item, now)
                if source is None:
                    continue
                if (
                    field == "external_alarm_ledger"
                    or source.tombstone
                    or source.source_id in self.sources
                ):
                    if source.phase is ExternalPhase.ACTIVE:
                        self.retain_tombstone(source)
                else:
                    self.sources[source.source_id] = source
        self.quarantine_conflicts()


def _restore_source(raw: Any, now: datetime) -> ExternalSource | None:
    if not isinstance(raw, dict):
        return None
    known_active = raw.get("phase") == ExternalPhase.ACTIVE.value or (
        (
            not isinstance(raw.get("phase"), str)
            or raw.get("phase") not in {phase.value for phase in ExternalPhase}
        )
        and valid_id(raw.get("event_id"))
    )
    if not all(valid_id(raw.get(key)) for key in ("source_id", "generation", "learning_epoch")):
        if not known_active:
            return None
        raw = {**raw, "tombstone": True}
        for key in ("source_id", "generation", "learning_epoch"):
            if not valid_id(raw.get(key)):
                raw[key] = new_id()
    if not isinstance(raw.get("entity_id"), str) or not raw["entity_id"].startswith(
        "binary_sensor."
    ):
        if not known_active:
            return None
        # Damaged routing metadata cannot be evidence that an alarm ended.
        raw = {**raw, "entity_id": f"binary_sensor.unresolved_{new_id()}", "tombstone": True}
    try:
        phase = ExternalPhase(raw["phase"])
    except KeyError, TypeError, ValueError:
        # Recover a remaining confirmed identity conservatively, not as ARMED.
        if not valid_id(raw.get("event_id")):
            return None
        phase = ExternalPhase.ACTIVE
    identity = SourceIdentity(
        raw["entity_id"],
        raw.get("registry_id"),
        raw.get("identity_signature"),
        raw["generation"],
        raw["learning_epoch"],
    )
    active = phase is ExternalPhase.ACTIVE
    return ExternalSource(
        raw["source_id"],
        identity,
        raw.get("contributes_to_shutoff") is not False,
        phase,
        (raw["event_id"] if valid_id(raw.get("event_id")) else f"external_{new_id()}")
        if active
        else None,
        token_urlsafe(32) if active else None,
        (parse_datetime(raw.get("started_at")) or now) if active else None,
        raw.get("name") if isinstance(raw.get("name"), str) else raw["entity_id"],
        raw.get("tombstone") is True,
        raw.get("identity_conflict") is True,
    )
