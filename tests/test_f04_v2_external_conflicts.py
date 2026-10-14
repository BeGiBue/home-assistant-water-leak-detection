import json
from pathlib import Path

import pytest
from test_f04_security_review_controls import setup

from custom_components.water_leak_detection.const import DOMAIN
from custom_components.water_leak_detection.manager import WaterLeakManager


@pytest.mark.parametrize("collision", [False, True])
async def test_active_source_contribution_survives_event_identity_conflict(
    runtime_hass, runtime_entry, measurement_clock, collision
):
    m = await setup(runtime_hass, runtime_entry, measurement_clock)
    sources = [
        {**s, "contributes_to_shutoff": s["id"] == "a"}
        for s in runtime_entry.options["external_sensors"]
    ]
    options = {**runtime_entry.options, "external_sensors": sources}
    await m.async_configure_external(options)
    runtime_hass.config_entries.async_update_entry(runtime_entry, options=options)
    runtime_hass.states.async_set("binary_sensor.b", "on")
    await runtime_hass.async_block_till_done()
    assert len(m.external.active_events()) == 2 and m.shutoff_request
    await m.async_unload()
    path = Path(m._store.path)
    raw = json.loads(path.read_text())
    records = raw["data"]["external_sources"]
    if collision:
        records[1]["event_id"] = records[0]["event_id"]
    path.write_text(json.dumps(raw))
    restored = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    restored.notifications._async_common_translations = m.notifications._async_common_translations
    await restored.async_setup()
    assert restored.external.sources["a"].phase.value == "ACTIVE"
    assert restored.external.sources["a"].contributes_to_shutoff
    print(
        "COLLISION",
        collision,
        "active_sources",
        sum(s.phase.value == "ACTIVE" for s in restored.external.all_sources()),
        "enumerated_events",
        len(restored.external.active_events()),
        "shutoff",
        restored.shutoff_request,
    )
    assert restored.shutoff_request, (
        "Another ACTIVE source sharing a damaged event_id must not hide source a contribution"
    )
