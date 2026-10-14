import json

import pytest
from test_f04_nachreview_recovery import retained_alarm
from test_f04_v2_safety_boundaries import restart


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("phase", ["ACTIVE", "damaged", None])
@pytest.mark.parametrize("event_id", [None, False, "broken id"])
async def test_retained_ledger_role_survives_damaged_phase_and_event_id(
    runtime_hass, runtime_entry, measurement_clock, version, phase, event_id
):
    m, path, good, raw, record = await retained_alarm(
        runtime_hass, runtime_entry, measurement_clock
    )
    raw["version"] = version
    record["phase"] = phase
    record["event_id"] = event_id
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    m = await restart(runtime_hass, runtime_entry, m)
    print(
        "LEDGER",
        version,
        phase,
        event_id,
        "alarm",
        m.alarm_active,
        "shutoff",
        m.shutoff_request,
        "recovery",
        m._storage_load_failed,
        "bytes_preserved",
        path.read_bytes() == before,
        "ledger_count",
        len(json.loads(path.read_text())["data"]["external_alarm_ledger"]),
    )
    assert m.alarm_active and m.shutoff_request, (
        "Retained ledger with generation/start/tombstone evidence "
        "cannot be silently treated as ended"
    )
