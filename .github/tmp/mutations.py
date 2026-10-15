# ruff: noqa
"""TEMPORARY: mutation check for the review fixes (removed before the end)."""
import subprocess
from pathlib import Path

C = Path("custom_components/water_leak_detection")
N = C / "notifications.py"
F = C / "config_flow.py"
G = C / "manager.py"
W = C / "websocket.py"
M = {
    "runtime: companion login": (N, '    if is_companion_login(token):\n        return "companion_app"\n', ""),
    "runtime: user of mobile": (N, '        return "user_of_mobile"\n', "        return None\n"),
    "runtime: token pairing refusal": (N, "            return None if refusal else by_token[0]\n", "            return by_token[0]\n"),
    "all instances": (N, "    return others\n\n\ndef display_login_problem", "    return []\n\n\ndef display_login_problem"),
    "flow: display login error": (F, "        if not session_id.startswith(_PAIR_TOKEN):\n            return None\n        token = self._token", "        return None\n        token = self._token"),
    "flow: display login options filter": (F, '            and not self._display_login_error(option["value"], recipients, editing_id)\n', ""),
    "flow: mobile reserves display login user": (F, "            if mobile and pairing.startswith(_PAIR_TOKEN):", "            if False:"),
    "manager: display not via action/service": (G, "        if display and not allow_display:\n            return False\n", ""),
    "action handler: display_recipient": (N, 'if self._raw_kind(payload.get("recipient_id")) == RECIPIENT_KIND_DISPLAY:', "if False:"),
    "manager: prepare guard": (G, "if source is None or recipient is None or recipient.is_display:", "if source is None or recipient is None:"),
    "ws: allow_display": (W, "payload, allow_display=current.is_display", "payload"),
}
TESTS = ["tests/test_display_recipient.py", "tests/test_card_backend_contract.py", "tests/test_config_runtime.py", "tests/test_external_reset_runtime.py"]


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
