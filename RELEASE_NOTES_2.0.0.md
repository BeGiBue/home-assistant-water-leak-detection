# Water Leak Guard 2.0.0

The first stable release since 1.1.0. It contains everything from the 1.2.0 and 2.0.0 betas plus
the fix for the security finding F04-FSR-H01, which was the reason the betas excluded external leak
sensors. Home Assistant **2026.9.0** or newer is required (unchanged since 1.1.0).

These notes are for upgrades from **1.1.0** and from the **betas**. Everything is listed in the
[changelog](CHANGELOG.md).

## Highlights

- **Dashboard card included (card 0.6.2).** The integration ships and loads the card itself. In the
  dashboard choose **Add card → Water Leak Guard**; there is no file to copy and no resource to add.
  The card:
  - shows the alarm state and the hydraulic monitoring state separately;
  - offers alarm actions per device (mute, global acknowledgement, external reset), which the backend
    authorizes.
- **Device pairing.** A notification recipient can be paired with a Home Assistant user or with one
  single login. The card then knows which device it runs on and offers only what that device may do.
- **Wall display recipient** for a fixed kiosk display such as TouchKio:
  - it is never notified and always counts as home;
  - its rights are the usual permission checkboxes;
  - the wiki has an example automation that wakes the display on an alarm.
- **F04 V3 detection:**
  - Burst Leak with evidence-based Rapid Rise;
  - separate rolling and confirmed long-term learning;
  - MQTT measurement time separated from delivery jitter, with replay and timeout protection;
  - a **Hydraulic monitoring** sensor that shows whether the meter is actually admitted to
    detection (active / waiting for measurement / blocked).
- **External leak sensors (`binary_sensor`).** Each sensor has its own alarm lifecycle and
  contributes to the shutoff request on its own. A Home-authorized external reset is available.
  With the F04-FSR-H01 fix, external sensors are no longer excluded from use.
- **Safer recovery.** Damaged or contradictory stored safety data keeps alarms and the shutoff
  request active and shows a repair issue, instead of silently starting "dry".

## Behavior changes – please read

- **Burst base 3,500 L/h if the expert options were never saved.** If the expert options were
  never saved, 3,500 L/h now applies. A saved value, including 2,000 L/h stored by 1.1.0 when the
  options were saved, is kept. Please check it: two large consumers at once or a garden hose can
  reach high flows.
- **Learning data from 1.1.0 is quarantined.** The legacy learning history is not reused. A repair
  issue explains the migration; adaptive thresholds learn again from new data.
- **Damaged store files now keep the safety lock (F04-FSR-H01).** If Home Assistant sets the
  runtime store aside as `water_leak_detection.runtime.<entry_id>.corrupt.<time>` because it is not
  valid JSON, every start keeps alarm and shutoff request active until you restore a backup. This
  also applies to hydraulic-only installations. Previously the second start began fresh and
  silently lost all stored alarms. Without a backup, you can deliberately move the copy out of
  `.storage` with HA stopped; this accepts the loss of the stored state. The same lock applies to
  damaged records of configured external sensors.
- **No detector switches in the card.** The card no longer has on/off switches:
  - Slow Leak and Low Flow can be disabled from the card only inside the alarm box while their own
    alarm is active ("Disable detection", with confirmation).
  - "Start bypass" is offered during a High Flow alarm.
  - Both end the alarm, so they are offered only to a paired device at home.
  - The switch entities and services in Home Assistant are unchanged.
- **Pairing and wall display rules:**
  - A login pairing takes precedence over a user pairing. Ambiguous pairings never authorize.
  - A wall display may only be paired with a single kiosk login, or with a dedicated kiosk user
    (not an administrator or owner, used by no other recipient). Every login of such a user counts as
    the display and is treated as at home, also a remote one.
  - Companion app logins can never be a display.
  - A display cannot use notification actions or the `external_reset` service.
- **Dashboard resource.** In the default (UI) resource mode the integration adds one Lovelace
  resource, "water-leak-guard-card loader" (`data:text/javascript…`). It makes the card load
  reliably even when a page was opened while Home Assistant was still starting. Do not delete it;
  it is removed with the last Water Leak Guard entry.
- **Shutoff-request icon** now follows its state (valve open / valve closed).

## Upgrading

1. **Back up.** Make a complete Home Assistant backup, including `.storage/`, before upgrading.
2. **Install.** Update Water Leak Guard to 2.0.0 in HACS.
3. **Restart** Home Assistant.
4. **Reload the frontend.** Reload the browser. In the Companion app use *Settings → Companion App →
   Debugging → Reset frontend cache* if the card or the new version does not appear.
5. **Remove the old card resource.** If you added the card by hand earlier, delete the
   `/local/water-leak-guard-card.js` resource (*Settings → Dashboards → ⋮ → Resources*) and the file in
   `<config>/www/`.
6. **Recipients and pairing.** For dashboard actions, edit each notification recipient and choose
   *Pairing for the dashboard card*: a user, or one single login. Existing pairings from the betas
   keep working.
7. **Wall display (optional).** Add it under *Configure → Notification recipients → Add wall display*.
   Use a dedicated non-admin kiosk user, or pair the kiosk's single login.
8. **Check.** Open the status entity and the Hydraulic monitoring sensor; check
   `storage_recovery_required` (should be `false`) and your Burst threshold.

Uninstalling: remove the Water Leak Guard entries first (this also removes the loader resource),
then remove the integration in HACS.

## Known limitations

- **The integration never operates a valve.** The shutoff request is a signal for your own
  automation; test that automation carefully.
- **Undetectable damage.** A stored record changed to a fully plausible state, for example a
  consistent ARMED record or a shutoff flag flipped to `false`, cannot be detected.
- **One damaged record locks everything.** The recovery lock is global: it holds every alarm and
  the shutoff request, and blocks learning and resets until recovery
  ([F04-FSR-H01](docs/F04_FSR_H01.md)).
- **No hydraulic leak/usage distinction.** A leak and normal usage with the same flow curve cannot
  be told apart hydraulically.
- **Deliberately open card items** (low impact, see [docs/CARD.md](docs/CARD.md#entwicklungsstand)):
  - a device mute exactly during an integration reload can be lost although reported as successful;
  - changing only a recipient's pairing while a notification is being handed off can drop that one
    notification;
  - without a visible device tracker, home-only buttons are disabled only after the next permission
    query;
  - a storage failure during an external reset is reported as "rejected".
- **YAML resource mode.** The loader resource is not added; reload the page after Home Assistant
  has fully started, or add the entry yourself.

## Verification

- **Automated checks.** The complete test suite, Ruff, the card logic tests, Hassfest and HACS
  validation pass in CI.
- **Reviews.** Every stage was reviewed by an independent review instance from the code, including
  the Home Assistant 2026.9.4 and frontend 20260826.7 sources; findings were fixed and re-reviewed.
- **Card.** Tested in Chromium with a simulated Home Assistant, including a reproduction of the
  startup loading race.
- **Hardware.** The physical Hydrus restart was confirmed by the user with 1.2.0-beta.3.
- **Not verified.** Not tested on every real device, meter or sensor. The card was not verified in a
  real Companion app on iOS/iPadOS, and real wall-display hardware was not tested. The integration
  does not replace mechanical water protection or human attention.
