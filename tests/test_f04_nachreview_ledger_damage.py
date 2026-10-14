import json
from pathlib import Path

import pytest
from homeassistant.helpers import entity_registry as er
from test_f04_security_review_controls import setup

from custom_components.water_leak_detection.const import DOMAIN
from custom_components.water_leak_detection.manager import WaterLeakManager


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize(
    "phase", ["ACTIVE", "ARMED", "RESET_WAITING_FOR_OFF", "damaged", None, False]
)
async def test_corrupted_active_ledger_cannot_imply_event_end(
    runtime_hass, runtime_entry, measurement_clock, phase, version
):
    m = await setup(runtime_hass, runtime_entry, measurement_clock)
    old = m.external.sources["a"].identity.generation
    registry = er.async_get(runtime_hass)
    registry.async_remove("binary_sensor.a")
    runtime_hass.states.async_set("binary_sensor.a", "unavailable")
    await runtime_hass.async_block_till_done()
    registry.async_get_or_create("binary_sensor", "test", "replacement", suggested_object_id="a")
    runtime_hass.states.async_set("binary_sensor.a", "off")
    await runtime_hass.async_block_till_done()
    assert any(
        s.identity.generation == old and s.phase.value == "ACTIVE" for s in m.external.all_sources()
    )
    assert m.shutoff_request
    await m.async_unload()
    path = Path(m._store.path)
    raw = json.loads(path.read_text())
    raw["version"] = version
    records = raw["data"]["external_alarm_ledger"]
    original = next(s for s in records if s["generation"] == old)
    assert original["phase"] == "ACTIVE" and original["event_id"] and original["started_at"]
    original["phase"] = phase
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    restored = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    restored.notifications._async_common_translations = m.notifications._async_common_translations
    await restored.async_setup()
    print(
        "LEDGER",
        phase,
        version,
        "alarm",
        restored.alarm_active,
        "shutoff",
        restored.shutoff_request,
        "byte_equal",
        path.read_bytes() == before,
        "recovery",
        restored._storage_load_failed,
        "ledger_count",
        len(json.loads(path.read_text())["data"]["external_alarm_ledger"]),
    )
    assert restored.alarm_active and restored.shutoff_request, (
        "Contradictory retained ACTIVE ledger identity must not silently lose its contribution"
    )
