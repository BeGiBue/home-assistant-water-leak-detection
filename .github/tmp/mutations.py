# ruff: noqa
"""TEMPORARY: mutation check for the review fixes (removed before the end)."""
import subprocess
from pathlib import Path

C = Path("custom_components/water_leak_detection")
N = C / "notifications.py"
F = C / "config_flow.py"
M = {
    "rule: owner/admin": (N, '    if user.is_owner or user.is_admin:\n        return "not_allowed"\n', ""),
    "rule: in use": (N, '        return "in_use"\n', "        return None\n"),
    "rule: token of that user": (N, "    return token is not None and token.user.id == user_id\n", "    return False\n"),
    "rule: fail closed without user": (N, '    if user is None or not user.is_active or user.system_generated:\n        return "not_allowed"\n', '    if user is None:\n        return None\n'),
    "runtime: kiosk check in recipient_for_session": (N, "            if problem := kiosk_user_problem(self.hass, user, others):", "            if problem := None:"),
    "runtime: warning": (N, '                _warn_once(\n                    f"display_user_{problem}",', '                (lambda *a: None)(\n                    f"display_user_{problem}",'),
    "flow: display user error": (F, "        if not session_id.startswith(_PAIR_USER):\n            return None\n        user = (await", "        return None\n        user = (await"),
    "flow: reverse conflict": (F, '            return "session_user_reserved_for_display"\n', "            return None\n"),
    "flow: display offers users": (F, 'options = [o for o in session_options if o["value"] != _NO_PAIRING]', 'options = [o for o in session_options if o["value"].startswith(_PAIR_TOKEN)]'),
    "display ack default off": (N, "raw.get(RECIPIENT_ALLOW_GLOBAL_ACK, not display) is True", "raw.get(RECIPIENT_ALLOW_GLOBAL_ACK, True) is True"),
    "unknown kind warning": (N, '            _warn_once(\n                "unknown_kind",', '            (lambda *a: None)(\n                "unknown_kind",'),
    "manager unknown kind": (C / "manager.py", "        if recipient.get(RECIPIENT_KIND, RECIPIENT_KIND_MOBILE) not in RECIPIENT_KINDS:\n            return False\n", ""),
}
TESTS = ["tests/test_display_recipient.py", "tests/test_card_backend_contract.py", "tests/test_config_runtime.py"]


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
    lines.append(f"{name}: {'KILLED' if rc else 'SURVIVED'} ({len(failed)}) {[f[:110] for f in failed[:2]]}")
print("::warning::" + "%0A".join(l.replace("%", "%25") for l in lines))
