"""Independent external sensor lifecycles and generation-bound alarm tombstones."""

from __future__ import annotations

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
            "contributes_to_shutoff": self.contributes_to_shutoff,
            "started_at": self.started_at.isoformat() if self.started_at else None,
        }


class ExternalLeakController:
    """Pure states; the manager commits a private copy before publishing releases."""

    def __init__(self) -> None:
        self.sources: dict[str, ExternalSource] = {}
        self.tombstones: dict[tuple[str, str], ExternalSource] = {}

    def copy(self) -> ExternalLeakController:
        return deepcopy(self)

    def all_sources(self) -> list[ExternalSource]:
        return [*self.sources.values(), *self.tombstones.values()]

    def active_events(self) -> dict[str, ExternalSource]:
        return {
            source.event_id: source
            for source in self.all_sources()
            if source.phase is ExternalPhase.ACTIVE and source.event_id
        }

    @property
    def shutoff_request(self) -> bool:
        return any(source.contributes_to_shutoff for source in self.active_events().values())

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
            current.contributes_to_shutoff = contributes
            return
        if current and current.phase is ExternalPhase.ACTIVE:
            if not forced:
                raise ValueError("external_source_active")
            current.tombstone = True
            self.tombstones[(source_id, current.identity.generation)] = current
        self.sources[source_id] = ExternalSource(source_id, identity, contributes, name=name)

    def remove(self, source_id: str) -> None:
        source = self.sources.get(source_id)
        if source and source.phase is ExternalPhase.ACTIVE:
            raise ValueError("external_source_active")
        self.sources.pop(source_id, None)

    def observe(self, source_id: str, state: str, now: datetime) -> None:
        source = self.sources.get(source_id)
        if source is None:
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
        # unknown/unavailable never means OFF, including after a manual reset.

    def event_for(self, source_id: str, generation: str, event_id: str) -> ExternalSource | None:
        for source in self.all_sources():
            if (
                source.source_id == source_id
                and source.identity.generation == generation
                and source.event_id == event_id
                and source.phase is ExternalPhase.ACTIVE
            ):
                return source
        return None

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
            ],
        }

    def restore(self, raw: Any, now: datetime) -> None:
        """Restore safety independently of current options; rotate all ACTIVE nonces.

        Never discard a valid active alarm simply to satisfy a count cap: active
        tombstones are safety evidence, not expendable statistical history.
        """
        self.sources.clear()
        self.tombstones.clear()
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
                if field == "external_alarm_ledger" or source.source_id in self.sources:
                    if source.phase is ExternalPhase.ACTIVE:
                        source.tombstone = True
                        self.tombstones[(source.source_id, source.identity.generation)] = source
                else:
                    self.sources[source.source_id] = source


def _restore_source(raw: Any, now: datetime) -> ExternalSource | None:
    if not isinstance(raw, dict) or not all(
        valid_id(raw.get(key)) for key in ("source_id", "generation", "learning_epoch")
    ):
        return None
    if not isinstance(raw.get("entity_id"), str) or not raw["entity_id"].startswith(
        "binary_sensor."
    ):
        return None
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
    )
