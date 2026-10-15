# ruff: noqa
"""TEMPORARY: mutation check for F04-FSR-H01 (removed before the end)."""
import subprocess
from pathlib import Path

C = Path("custom_components/water_leak_detection")
X = C / "external_leaks.py"
S = C / "storage.py"
G = C / "manager.py"
M = {
    "source records not validated": (X, '            elif role == "external_sources":', '            elif False:'),
    "phase check": (X, "        phase not in tuple(item.value for item in ExternalPhase)\n        or not all(", "        not all("),
    "id checks": (X, '            valid_id(record.get(key)) for key in ("source_id", "generation", "learning_epoch")\n        )\n        or not isinstance(record.get("entity_id"), str)', '            True for key in ()\n        )\n        or not isinstance(record.get("entity_id"), str)'),
    "entity check": (X, '        or not record["entity_id"].startswith("binary_sensor.")\n        or not isinstance(record.get("contributes_to_shutoff"), bool)\n        or not isinstance(record.get("tombstone", False), bool)\n        or not isinstance(record.get("identity_conflict", False), bool)\n        or not _optional', '        or not isinstance(record.get("contributes_to_shutoff"), bool)\n        or not isinstance(record.get("tombstone", False), bool)\n        or not isinstance(record.get("identity_conflict", False), bool)\n        or not _optional'),
    "contributes bool": (X, '        or not isinstance(record.get("contributes_to_shutoff"), bool)\n        or not isinstance(record.get("tombstone", False), bool)\n        or not isinstance(record.get("identity_conflict", False), bool)\n        or not _optional', '        or not isinstance(record.get("tombstone", False), bool)\n        or not isinstance(record.get("identity_conflict", False), bool)\n        or not _optional'),
    "flag types": (X, '        or not isinstance(record.get("tombstone", False), bool)\n        or not isinstance(record.get("identity_conflict", False), bool)\n        or not _optional', '        or not _optional'),
    "optional types": (X, '    return value is None or (isinstance(value, kind) and not isinstance(value, bool))', '    return True'),
    "started_at any phase": (X, "        or (started is not None and parse_datetime(started) is None)\n", ""),
    "ACTIVE event/start": (X, '            and (not valid_id(record.get("event_id")) or parse_datetime(started) is None)', "            and False"),
    "missing list": (S, '        if field not in raw and raw.get("learning_schema_version") == LEARNING_SCHEMA_VERSION:', "        if False:"),
    "corrupt copy": (G, "        if not existed and self._corrupt_store_copies():", "        if False:"),
}
TESTS = ["tests/test_f04_fsr_h01.py", "tests/test_external_leaks.py"]


def run(name=None):
    original = None
    if name:
        path, a, b = M[name]
        original = path.read_text()
        n = original.count(a)
        if n != 1:
            return 99, [f"pattern count {n}"]
        path.write_text(original.replace(a, b))
    try:
        r = subprocess.run(["pytest", "-q", "-p", "no:cacheprovider", *TESTS], capture_output=True, text=True)
        return r.returncode, [l for l in r.stdout.splitlines() if l.startswith("FAILED")]
    finally:
        if name:
            path.write_text(original)


lines = []
rc, failed = run()
lines.append(f"BASELINE: {'FAILING' if rc else 'green'} {failed[:3]}")
for name in M:
    rc, failed = run(name)
    lines.append(f"{name}: {'KILLED' if rc else 'SURVIVED'} ({len(failed)}) {[f[:120] for f in failed[:2]]}")
print("::warning::" + "%0A".join(l.replace("%", "%25") for l in lines))
