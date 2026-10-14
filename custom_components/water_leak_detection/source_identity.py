"""Observable HA source identity, independent of an entity's display name."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any
from uuid import uuid4

from homeassistant.helpers import entity_registry as er


def valid_id(value: Any) -> bool:
    """Bound persistent identifiers; never accept arbitrary containers or booleans."""
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) is not None


def new_id() -> str:
    """Return an opaque independent generation/event identity."""
    return uuid4().hex


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    """Registry identity is authoritative; entity_id is renameable metadata."""

    entity_id: str
    registry_id: str | None
    identity_signature: str | None
    generation: str
    learning_epoch: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_source(hass, entity_id: str, previous: Any = None) -> SourceIdentity:
    """Preserve only a reliably identical registry source across reload/rename.

    Without a registry identity a restart cannot prove physical continuity, so it
    intentionally starts new learning. Confirmed alarms are handled separately.
    """
    registry = er.async_get(hass)
    registered = registry.async_get(entity_id)
    if registered is None and isinstance(previous, dict) and previous.get("entity_id") == entity_id:
        # Registry UUID survives a rename while HA or this integration was offline.
        old_registry_id = previous.get("registry_id")
        if isinstance(old_registry_id, str):
            registered = registry.async_get(old_registry_id)
    if registered:
        entity_id = registered.entity_id
    registry_id = registered.id if registered else None
    signature = None
    if registered:
        payload = [registered.platform, registered.unique_id, registered.device_id]
        signature = sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    same = (
        isinstance(previous, dict)
        and registry_id is not None
        and previous.get("registry_id") == registry_id
        and previous.get("identity_signature") == signature
        and valid_id(previous.get("generation"))
        and valid_id(previous.get("learning_epoch"))
    )
    return SourceIdentity(
        entity_id,
        registry_id,
        signature,
        previous["generation"] if same else new_id(),
        previous["learning_epoch"] if same else new_id(),
    )
