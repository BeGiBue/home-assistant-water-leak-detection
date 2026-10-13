import json
from pathlib import Path

import pytest
from test_f04_security_review_controls import setup

from custom_components.water_leak_detection.const import DOMAIN
from custom_components.water_leak_detection.manager import WaterLeakManager


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("shape", ["list", "string", "number", "boolean"])
async def test_supported_wrapper_with_corrupt_body_is_not_overwritten(
    runtime_hass, runtime_entry, measurement_clock, shape, version
):
    m = await setup(runtime_hass, runtime_entry, measurement_clock)
    assert m.alarm_active and m.shutoff_request
    await m.async_unload()
    path = Path(m._store.path)
    wrapper = json.loads(path.read_text())
    wrapper["version"] = version
    old_data = wrapper["data"]
    wrapper["data"] = {
        "list": [old_data],
        "string": json.dumps(old_data),
        "number": 17,
        "boolean": True,
    }[shape]
    path.write_text(json.dumps(wrapper))
    original = path.read_bytes()
    runtime_hass.states.async_set("binary_sensor.a", "unavailable")
    restored = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    restored.notifications._async_common_translations = m.notifications._async_common_translations
    await restored.async_setup()
    print(
        "RECOVERY",
        shape,
        version,
        "bytes_unchanged",
        path.read_bytes() == original,
        "recovery",
        restored._storage_load_failed,
        "alarm",
        restored.alarm_active,
        "shutoff",
        restored.shutoff_request,
    )
    assert path.read_bytes() == original, "Malformed store body must remain available for recovery"
    assert restored._storage_load_failed
    assert restored.alarm_active and restored.shutoff_request
