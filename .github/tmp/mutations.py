# ruff: noqa
import subprocess
from pathlib import Path
C = Path("custom_components/water_leak_detection")
M = {
    "options condition": (C / "manager.py", "            and self._external_sensors_configured()\n", ""),
    "exact file name": (C / "manager.py", 'path.parent.glob(f"{glob.escape(path.name)}.corrupt.*")', 'path.parent.glob("*.corrupt.*")'),
    "identity_signature type": (C / "external_leaks.py", '        or not _optional(record, "identity_signature", str)\n', ""),
}
TESTS = ["tests/test_f04_fsr_h01.py"]
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
    lines.append(f"{n}: {'KILLED' if rc else 'SURVIVED'} ({len(f)}) {[x[:120] for x in f[:2]]}")
print("::warning::" + "%0A".join(lines))
