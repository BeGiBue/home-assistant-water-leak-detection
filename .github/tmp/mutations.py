# ruff: noqa
"""TEMPORARY: mutation check for the display guards (removed before the end)."""
import subprocess
from pathlib import Path

C = Path("custom_components/water_leak_detection")
M = {
    "home: display always home": (C / "notifications.py", "    if recipient.is_display:\n        return True\n    tracker", "    tracker"),
    "home: external reset display branch": (C / "manager.py", "display = recipient.get(RECIPIENT_KIND) == RECIPIENT_KIND_DISPLAY", "display = False"),
    "dispatch: retry loop skip": (C / "notifications.py", "                if recipient.is_display:\n                    continue  # never part of notification dispatch\n", ""),
    "dispatch: _eligible guard": (C / "notifications.py", "            and not recipient.is_display\n", ""),
    "dispatch: send guard": (C / "notifications.py", "        if recipient.is_display:\n            return False  # defense in depth: a display has no notify service\n", ""),
    "dispatch: external reset notification": (C / "manager.py", "if source is None or recipient is None or recipient.is_display:", "if source is None or recipient is None:"),
    "actions: display rejection": (C / "notifications.py", "        if recipient.is_display:\n            # Displays never receive notifications, hence never notification actions.\n            self._fire_rejected(event_id, recipient_id, \"display_recipient\")\n            return\n", ""),
    "mute: websocket pre-check": (C / "websocket.py", "        if _require_recipient(hass, manager, connection).is_display:\n            raise CommandError(ERR_MUTE_NOT_APPLICABLE, \"A display receives no notifications\")\n", "        _require_recipient(hass, manager, connection)\n"),
    "mute: controller guard": (C / "notifications.py", "        if self.recipients[recipient_id].is_display:\n            # A display receives no notifications, so there is nothing to mute.\n            return \"not_applicable\"\n", ""),
}
both = {
    "dispatch: loop skip + _eligible": ["dispatch: retry loop skip", "dispatch: _eligible guard"],
    "mute: both guards": ["mute: websocket pre-check", "mute: controller guard"],
}
TESTS = ["tests/test_display_recipient.py", "tests/test_card_backend_contract.py", "tests/test_notification_runtime.py"]


def run(names):
    originals = {}
    for name in names:
        path, a, b = M[name]
        text = originals.get(path) or path.read_text()
        originals.setdefault(path, text)
        current = path.read_text()
        assert current.count(a) == 1, (name, current.count(a))
        path.write_text(current.replace(a, b))
    try:
        r = subprocess.run(["pytest", "-q", "-p", "no:cacheprovider", *TESTS], capture_output=True, text=True)
        failed = [l for l in r.stdout.splitlines() if l.startswith("FAILED")]
        return r.returncode, failed
    finally:
        for path, text in originals.items():
            path.write_text(text)


lines = []
rc, failed = run([])
lines.append(f"BASELINE: {'FAILING' if rc else 'green'} {failed[:3]}")
for name in M:
    rc, failed = run([name])
    lines.append(f"{name}: {'KILLED' if rc else 'SURVIVED'} ({len(failed)}) {failed[:1]}")
for name, parts in both.items():
    rc, failed = run(parts)
    lines.append(f"{name}: {'KILLED' if rc else 'SURVIVED'} ({len(failed)}) {failed[:1]}")
print("::warning::" + "%0A".join(l.replace("%", "%25") for l in lines))
