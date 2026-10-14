# Water Leak Guard 2.0.0-beta.1

## The dashboard card is now part of the integration

**Water Leak Guard card 0.4.1** is installed and loaded together with the integration. After
installing or updating and restarting Home Assistant, choose **Add card → Water Leak Guard**. No
file copy and no dashboard resource are needed. The card URL carries a content digest, so browsers
load the new version after every update. `frontend`/`http` are ordering-only dependencies: leak
detection starts even if the card cannot be registered.

If you installed an earlier card manually, remove the `/local/water-leak-guard-card.js` resource
and the file in `<config>/www/`. A leftover copy only logs a console warning.

## Alarm state and monitoring state, shown separately

- The headline shows the alarm state only. A separate row shows **Hydraulic monitoring**
  (active / waiting for measurement / blocked) with reason and MQTT provenance.
- Green and "All quiet" appear only when monitoring is confirmed active and no external sensor is
  offline. An ACTIVE alarm is never hidden, also while the status reports `source_unavailable`.
- Switching off Slow/Low during its own alarm or starting the High Flow bypass during a High Flow
  alarm ends that alarm; the card now asks for confirmation with a clear warning. Burst cannot be
  bypassed or disabled.

## Alarm actions per device

- A notification recipient can be **paired with one Home Assistant login** (the device's app or
  browser session) in its recipient entry: *Configure → Notification recipients → Edit recipient →
  Paired login for the dashboard card*. Rights belong to the device, not the user: an iPad at home
  can acknowledge globally while the same user's phone away can only mute itself.
- The card offers only what this device may do right now: mute for this device (anywhere), global
  acknowledgement (permission and Home), external leak reset (permission and Home, with
  confirmation). Hydraulic alarms have no clear button. Unpaired devices are view only.
- New WebSocket commands `water_leak_detection/session`, `/mute`, `/acknowledge`,
  `/external_reset`. Identity is the paired login of the connection; recipient tokens and reset
  nonces never leave the server. Home presence, permissions and the exact event binding are checked
  by the existing validators at execution time. Stable error codes are shown as plain messages.
- Acknowledging or muting never ends detection, an alarm or the shutoff request.

## Verification

- Complete repository test suite, Ruff, Hassfest and HACS validation pass.
- Each stage was reviewed by an independent review instance from the code on GitHub, including
  Home Assistant 2026.9.4 API semantics; findings were fixed and re-reviewed.
- The card was tested in Chromium with a simulated Home Assistant (desktop/phone width, light/dark).
- **Not yet verified on a live Home Assistant installation** (card loading in the Companion app,
  real pairing with logins and device trackers).

## Known limitations

- The beta remains intended for hydraulic monitoring and notifications without configured external
  leak sensors or persisted external alarm records; H01 (corrupted external alarm data) remains
  open. External reset in the card therefore only matters outside this beta scope.
- Low-impact items left open deliberately: a device mute exactly during an integration reload may
  be lost although reported as successful; changing only a recipient's pairing while a notification
  to it is being handed off may drop that one notification; without a visible device tracker the
  card disables home-only buttons only after the next permission query (the backend rejects with
  `not_home` meanwhile); a storage failure during external reset is reported as "rejected".
- The integration never operates a physical valve.

Home Assistant 2026.9.0 or newer is required. Back up your configuration and the integration's
runtime store before upgrading; enable beta versions in HACS, download 2.0.0-beta.1 and restart.
