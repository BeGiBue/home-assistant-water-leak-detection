"""Versioned runtime storage and atomic, provenance-free legacy quarantine."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from homeassistant.helpers.storage import Store

from .external_leaks import validate_external_snapshot
from .source_identity import SourceIdentity

LEARNING_SCHEMA_VERSION = 2
LEGACY_MIGRATION_ID = "legacy_to_f04_v3"


def validate_snapshot_body(raw: Any) -> None:
    """Reject uninterpretable safety containers; never infer that they were dry.

    Missing legacy fields remain compatible. Valid record dictionaries retain
    the component-specific conservative validation/identity quarantine.
    """
    if not isinstance(raw, dict):
        raise ValueError("Invalid runtime snapshot body; restore a verified backup")
    if "engine" in raw:
        engine = raw["engine"]
        if not isinstance(engine, dict):
            raise ValueError("Invalid hydraulic safety container")
        if "runtimes" in engine and (
            not isinstance(engine["runtimes"], dict)
            or any(not isinstance(record, dict) for record in engine["runtimes"].values())
        ):
            raise ValueError("Invalid hydraulic runtime records")
    for field in ("external_sources", "external_alarm_ledger"):
        if field in raw and (
            not isinstance(raw[field], list)
            or any(not isinstance(record, dict) for record in raw[field])
        ):
            raise ValueError("Invalid external safety records")
    # Run before version-1 migration writes as well as version-2 normalization.
    # A contradictory retained alarm must not become an empty fresh snapshot.
    validate_external_snapshot(raw)


def migrate_snapshot(raw: Any, source: SourceIdentity, now: datetime, entry_id: str) -> dict:
    """Transform the complete snapshot once; never reconstruct legacy provenance.

    The marker and empty channels are one HA Store atomic write. All unrelated
    control/alarm fields, including newer external state, survive unchanged.
    """
    if raw is not None:
        validate_snapshot_body(raw)
    snapshot = deepcopy(raw) if raw is not None else {}
    if snapshot.get("learning_schema_version") == LEARNING_SCHEMA_VERSION:
        return snapshot
    legacy = snapshot.pop("learning", None)
    evidence = bool(legacy) and (
        not isinstance(legacy, dict)
        or any(
            bool(legacy.get(key))
            for key in ("samples", "pending_high_candidates", "confirmed_high_history")
        )
        or any(key in legacy for key in ("learned_max_lph", "confidence"))
    )
    binding = {"source_generation": source.generation, "learning_epoch": source.learning_epoch}
    snapshot.update(
        {
            "learning_schema_version": LEARNING_SCHEMA_VERSION,
            "measurement_source": source.to_dict(),
            "rolling_learning": {**binding, "samples": []},
            "long_term_learning": {
                **binding,
                "confirmed_long_term_normal_max_lph": None,
                "summary_confirmed": False,
                "pending_high_candidates": [],
                "confirmed_high_history": [],
            },
        }
    )
    if evidence:
        samples = legacy.get("samples") if isinstance(legacy, dict) else None
        snapshot["legacy_learning_migration"] = {
            "migration_id": LEGACY_MIGRATION_ID,
            "legacy_learning_quarantined": True,
            "legacy_learning_migrated_at": now.isoformat(),
            "legacy_learning_sample_count": len(samples) if isinstance(samples, list) else None,
            "repair_id": f"{entry_id}_{LEGACY_MIGRATION_ID}",
        }
    snapshot.setdefault("external_sources", [])
    snapshot.setdefault("external_alarm_ledger", [])
    return snapshot


class RuntimeStore(Store[dict[str, Any]]):
    """HA Store major-version upgrade with recoverable safety state on failure."""

    def __init__(self, hass, version, key, migrate):
        super().__init__(hass, version, key)
        self._migrate = migrate
        self.recovered_data: Any = None

    async def async_save(self, data: dict[str, Any]) -> None:
        """Require durable HA atomic I/O, including propagation of write errors.

        HA's regular Store logs WriteError without raising and may defer saves
        while stopping. Neither behavior is a successful safety transaction.
        Keep HA's writer/atomic file primitive, but explicitly await its result.
        """
        # The role contract applies to every writer, not just initial restore.
        # Never commit a partially damaged retained identity as a new snapshot.
        validate_snapshot_body(data)
        async with self._write_lock:
            if self._read_only:
                raise RuntimeError("Cannot commit a safety state to a read-only Store")
            self._manager.async_invalidate(self.key)
            self._async_cleanup_delay_listener()
            self._async_cleanup_final_write_listener()
            self._data = None
            await self._async_write_data(
                {
                    "version": self.version,
                    "minor_version": self.minor_version,
                    "key": self.key,
                    "data": data,
                }
            )

    async def _async_migrate_func(self, old_major_version, old_minor_version, old_data):
        self.recovered_data = None
        if old_major_version != 1:
            raise ValueError("Unsupported Water Leak Guard runtime storage version")
        # Reject before HA's migration can write, or recovered_data can bypass
        # the manager's recovery barrier. Only a missing file is a fresh install.
        validate_snapshot_body(old_data)
        self.recovered_data = deepcopy(old_data)
        return self._migrate(old_data)
