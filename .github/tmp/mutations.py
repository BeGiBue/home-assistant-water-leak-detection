# ruff: noqa
import subprocess
from pathlib import Path
C = Path("custom_components/water_leak_detection")
M = {
    "no loader resource": (C / "card.py", "    await async_ensure_loader_resource(hass, url)\n", ""),
    "no update on new digest": (C / "card.py", '        if first.get("url") != url or first.get("type") != "module":', "        if False:"),
    "duplicates kept": (C / "card.py", "        for item in duplicates:\n            await resources.async_delete_item(item[\"id\"])\n", ""),
    "remove ignores other entries": (C / "__init__.py", "    if not any(\n", "    if True or not any(\n"),
    "yaml mode not skipped": (C / "card.py", "    return resources if isinstance(resources, ResourceStorageCollection) else None", "    return resources"),
    "error not contained": (C / "card.py", "    except Exception:  # the card must never block leak detection\n        _LOGGER.warning(\"Dashboard card loader", "    except ZeroDivisionError:  # the card must never block leak detection\n        _LOGGER.warning(\"Dashboard card loader"),
}
TESTS = ["tests/test_card_registration.py"]
def run(name=None):
    original = None
    if name:
        path, a, b = M[name]
        original = path.read_text()
        if original.count(a) != 1:
            return 99, ["pattern"]
        path.write_text(original.replace(a, b))
    try:
        r = subprocess.run(["pytest", "-q", "-p", "no:cacheprovider", *TESTS], capture_output=True, text=True)
        return r.returncode, [l for l in r.stdout.splitlines() if l.startswith("FAILED")]
    finally:
        if name:
            path.write_text(original)
lines = []
rc, f = run()
lines.append(f"BASELINE: {'FAILING' if rc else 'green'} {f[:3]}")
for n in M:
    rc, f = run(n)
    lines.append(f"{n}: {'KILLED' if rc else 'SURVIVED'} ({len(f)}) {[x[:110] for x in f[:2]]}")
print("::warning::" + "%0A".join(lines))
