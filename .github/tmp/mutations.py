# ruff: noqa
"""TEMPORARY: mutation check for the review fixes (removed before the end)."""
import subprocess
from pathlib import Path

C = Path("custom_components/water_leak_detection")
M = {
    "display ignores user pairing": (C / "notifications.py", "            session_user_id = None\n", ""),
    "display ack default off": (C / "notifications.py", "raw.get(RECIPIENT_ALLOW_GLOBAL_ACK, not display) is True", "raw.get(RECIPIENT_ALLOW_GLOBAL_ACK, True) is True"),
    "unknown kind warning": (C / "notifications.py", '            _warn_once(\n                "unknown_kind",', '            (lambda *a: None)(\n                "unknown_kind",'),
    "manager unknown kind": (C / "manager.py", "        if recipient.get(RECIPIENT_KIND, RECIPIENT_KIND_MOBILE) not in RECIPIENT_KINDS:\n            return False\n", ""),
    "flow: display_requires_login check": (C / "config_flow.py", '            elif not session_id.startswith(_PAIR_TOKEN):\n                errors["base"] = "display_requires_login"\n', ""),
    "flow: token-only options": (C / "config_flow.py", 'options = [o for o in session_options if o["value"].startswith(_PAIR_TOKEN)]', 'options = [o for o in session_options if o["value"] != _NO_PAIRING]'),
}
TESTS = ["tests/test_display_recipient.py", "tests/test_card_backend_contract.py", "tests/test_config_runtime.py"]


def run(name=None):
    original = None
    if name:
        path, a, b = M[name]
        original = path.read_text()
        n = original.count(a)
        if n < 1:
            return 99, [f"pattern not found ({n})"]
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
    lines.append(f"{name}: {'KILLED' if rc else 'SURVIVED'} ({len(failed)}) {failed[:1]}")
print("::warning::" + "%0A".join(l.replace("%", "%25") for l in lines))
