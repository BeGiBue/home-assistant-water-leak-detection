"""Production snapshot migration and actual HA atomic Store failure/restart."""

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from homeassistant.helpers.storage import Store

from custom_components.water_leak_detection.source_identity import SourceIdentity
from custom_components.water_leak_detection.storage import RuntimeStore, migrate_snapshot

NOW = datetime(2026, 10, 11, tzinfo=UTC)
SOURCE = SourceIdentity("sensor.flow", "registry", "signature", "generation", "epoch")


@pytest.mark.parametrize("legacy", [
    {"samples": [{"peak_lph": 3300}]},
    {"pending_high_candidates": [None]},
    {"confirmed_high_history": ["bad"]},
    {"samples": "corrupt"}, "corrupt", {"confidence": "reliable"},
])
def test_quarantine_all_legacy_without_guessing_origin(legacy):
    safety = {
        "engine": {"runtimes": {"burst_leak": {"phase": "active", "event_id": "alive"}}},
        "acknowledgements": {"alive": {"globally_acknowledged": True}},
        "options": {"burst_threshold_lph": 2000}, "recipients": ["unchanged"],
        "bypass_until": NOW.isoformat(), "external_alarm_ledger": [{"phase": "ACTIVE"}],
    }
    original = {**safety, "learning": legacy}
    migrated = migrate_snapshot(original, SOURCE, NOW, "entry")
    assert original["learning"] == legacy
    assert all(migrated[key] == value for key, value in safety.items())
    assert "learning" not in migrated
    assert migrated["rolling_learning"]["samples"] == []
    assert migrated["long_term_learning"]["pending_high_candidates"] == []
    assert migrated["legacy_learning_migration"]["legacy_learning_quarantined"] is True
    assert migrate_snapshot(migrated, SOURCE, NOW.replace(year=2020), "entry") == migrated


@pytest.mark.parametrize("raw", [{}, {"learning": {}}, {"learning": {"samples": []}}])
def test_new_or_empty_installation_has_no_legacy_repair(raw):
    assert "legacy_learning_migration" not in migrate_snapshot(raw, SOURCE, NOW, "entry")


def test_new_schema_is_not_migrated_or_reset_again():
    raw = migrate_snapshot({"learning": {"samples": [None]}}, SOURCE, NOW, "entry")
    raw["rolling_learning"]["samples"] = [{"peak_lph": 70}]
    raw["long_term_learning"]["confirmed_long_term_normal_max_lph"] = 3300
    assert migrate_snapshot(raw, SOURCE, NOW, "entry") == raw


async def test_real_store_upgrade_atomically_saves_marker_empty_channels_and_alarm(runtime_hass):
    old = Store(runtime_hass, 1, "f04_migration_test")
    raw = {"learning": {"samples": [None]}, "engine": {"alarm": "preserve"}}
    await old.async_save(raw)
    store = RuntimeStore(runtime_hass, 2, old.key,
                         lambda data: migrate_snapshot(data, SOURCE, NOW, "entry"))
    loaded = await store.async_load()
    disk = json.loads(Path(store.path).read_text())
    assert disk["version"] == 2
    assert disk["data"] == loaded
    assert loaded["engine"] == raw["engine"]
    assert loaded["legacy_learning_migration"]["legacy_learning_quarantined"]
    again = RuntimeStore(runtime_hass, 2, old.key, lambda _: pytest.fail("second migration"))
    assert await again.async_load() == loaded


async def test_real_atomic_write_failure_never_reports_commit(runtime_hass, monkeypatch):
    old = Store(runtime_hass, 1, "f04_failed_migration")
    raw = {"learning": {"samples": [None]}, "engine": {"alarm": "preserve"}}
    await old.async_save(raw)
    before = Path(old.path).read_bytes()
    store = RuntimeStore(runtime_hass, 2, old.key,
                         lambda data: migrate_snapshot(data, SOURCE, NOW, "entry"))
    writer = store._write_prepared_data

    def fail(*_args):
        from homeassistant.exceptions import HomeAssistantError
        raise HomeAssistantError("injected physical write failure")

    monkeypatch.setattr(store, "_write_prepared_data", fail)
    with pytest.raises(Exception, match="physical write failure"):
        await store.async_load()
    assert Path(old.path).read_bytes() == before
    assert store.recovered_data == raw
    monkeypatch.setattr(store, "_write_prepared_data", writer)
    await store.async_save(migrate_snapshot(deepcopy(raw), SOURCE, NOW, "entry"))
    assert json.loads(Path(old.path).read_text())["data"]["legacy_learning_migration"]
