# Changelog

## 2.0.0-beta.3 — 2026-10-15

- Dashboard card 0.6.0: "High Flow bypass" and "Learning" start **expanded**. New option
  `collapsed: true` (editor: "Start with sections collapsed") starts them collapsed, needed only on short screens such
  as a Raspberry Pi 7″ display in landscape (800×480); in portrait (480×800) the default open card fits
  under the toolbar (idle about 550 px, card 448–464 px wide, measured ±15 px). In-card toggles stay in memory; changing the option resets to its default. Idle height
  (Chromium, ±15 px): expanded about 615/550/550 px at 320/386/500 px and about 465 px in two columns
  (744 px); collapsed unchanged at about 335 px (188 px in two columns).
- New recipient kind **wall display** (`kind: display`, options: "Add wall display") for a fixed display
  such as TouchKio: no notify service, no device tracker, never notified or part of dispatch, always
  counts as home, requires a pairing, permissions are the usual flags (global acknowledgement off by
  default, also for a hand-edited entry without the key). The session reports `kind` and `can_mute`; mute answers `mute_not_applicable` and the card
  hides it. The kind cannot be changed after creation. Entries without `kind` stay mobile; no migration.
  The admin acknowledgement form offers only mobile recipients. Wiki: TouchKio example automation.
- Wall display pairing: either a single login (🔑, binds the rights to the one kiosk session; renew it
  after the kiosk logs in again) or a **dedicated kiosk user** (👤). A kiosk user must be active, neither
  owner nor administrator, and used by no other recipient's pairing, neither as user nor through one of
  its logins (form errors `display_user_not_allowed`, `display_user_in_use`); in return no other
  recipient can select that user or its logins (`session_user_reserved_for_display`). The same rule is
  enforced when resolving sessions: such a hand-edited display never resolves and is logged by name.
  With a user pairing every login of the kiosk user counts as home, also a remote one with its
  password; docs and form texts recommend a non-admin kiosk user with its own strong password.
- Wall display login pairing: Companion app logins (`https://home-assistant.io/iOS…`, `…/android…`) and
  logins of a user that a mobile recipient's pairing uses are not offered, rejected
  (`display_login_not_allowed`) and refused at runtime with a warning; a mobile recipient cannot select
  the user of a display's login. Kiosk-user and display-login rules count the pairings of all instances
  of the integration.
- A display can no longer reset an external leak through the notification action or the
  `external_reset` service (rejected with `display_recipient` resp. not authorized); only the card's
  websocket command may act as a display. The recipient kind is read from the stored options.
- Dashboard card 0.6.1: `getCardSize()` returns 11 with a section expanded, 7 with both collapsed, 14
  during an alarm. New card tests for `canClear` and DE/EN I18N key parity.
- Recipients with an unknown or empty `kind` are logged by id and name (they receive no notifications);
  the external-reset validator rejects them as well.
- The shutoff-request binary sensor's icon follows its state via a new `icons.json`: `mdi:valve-open`
  while no shutoff is requested, `mdi:valve-closed` while one is requested, `mdi:valve` otherwise (the
  fixed `mdi:valve-closed` entity icon is gone). The card already shows `mdi:valve-closed` only for a
  requested shutoff and is unchanged.
- Wiki (TouchKio): recommend only turning the display on when the card's dashboard is the kiosk start
  page; a `text.set_value` page URL must use exactly TouchKio's `web_url` base (scheme, host, port),
  otherwise the browser has no stored login and the dashboard does not load.

## 2.0.0-beta.2 — 2026-10-14

- Dashboard card 0.5.0 – compact, collapsible, responsive layout. The idle single-column card
  (320–500 px wide, i.e. every masonry or sections column, which Home Assistant caps at about 500 px,
  including an iPad or a Raspberry Pi 7″ 800×480 display) shrinks from about 830–930 px to about 335 px
  (measured in Chromium, ±15 px depending on fonts); it fits under the HA toolbar on the 800×480 display.
  Two columns (about 190 px high) only when the card itself is at least about 600 px wide: panel view, or
  a sections view with `column_span` ≥ 2 and `grid_options: columns: full`. While monitoring is
  confirmed active and nothing is impaired (status and monitoring entities available, no source or
  store problem, no unreachable external sensor), a compact "Hydraulics active" pill replaces the
  monitoring row; every other state keeps the full row. All controls have a hit area of at least 44 px. Flatter header (about 76 px) with a smaller shield that text never overlaps;
  detectors as a 2×2 status grid; "High Flow bypass" and "Learning" are collapsible
  (summary row is a button with `aria-expanded`, collapsed by default, state kept per card across
  updates); the four learning values sit in one row. Two columns once the card itself is about 600 px
  wide (CSS container query). The alarm box comes right after the header. An insufficient learning
  state is no longer green; only "reliable" is.
- Card: no on/off switches anymore (maintainer decision). Slow Leak/Low Flow can be disabled from the
  card only inside the alarm box while that detector's alarm is ACTIVE ("Disable detection", same
  confirmation and `switch.turn_off` call). This and "Start bypass" during a High Flow alarm end the
  alarm and are therefore offered only to a paired device at home, like the external reset;
  away they are shown disabled ("Only possible at home"). HA entities and services stay unrestricted.
  The detector switches are never linked or opened from the card. `getCardSize()` 9 → 7 (14 during an
  alarm); `getGridOptions()` unchanged. Minimum card width 280 px (the container query would otherwise
  let the card collapse in a content-sized container).
- Card (also on main before): with monitoring reported active but the runtime store damaged or the source
  impaired (`source_unavailable`, `source_available: false`) the card was green "All quiet"; it is now
  yellow "Monitoring impaired", the monitoring row shows a yellow "Impaired" instead of a green "Active"
  and the detector tiles show "Paused" instead of "Ready". An alarm (headline and tile) keeps priority.
- Card: the mute button names the paired recipient ("Mute for Bea" / "Für Bea stummschalten", from the
  session's `recipient_name`, escaped; old text without a name), because with a user pairing a laptop
  mutes the paired phone's recipient.
- Card logic tests in plain Node without npm packages (`tests/card/card_logic.test.mjs`), run by the
  Validate workflow.
- Recipients can be paired with a Home Assistant **user** (new default, `session_user_id`, every normal
  login of that user, survives a new login) or, as before, with a single **login**
  (`session_token_id`). A login pairing wins over a user pairing. Existing login pairings keep working
  without migration; editing a recipient keeps its pairing unless changed. A user and a login can each
  be paired with one recipient only (new errors `session_user_already_paired`,
  `session_user_not_found`). Mute, acknowledgement, the Home check (paired recipient's tracker) and the
  external reset are unchanged. The options form field is now `session_pairing` with values
  `user:<id>` / `token:<id>`; the choices are labelled language-neutrally "👤 name" (user) and
  "🔑 name – client · last used" (login).
- New preview image `docs/assets/card-preview.png` (iPhone idle and Burst Leak alarm).

## 2.0.0-beta.1 — 2026-10-14

Major release for the dashboard: the card ships with the integration, shows alarm and hydraulic
monitoring state separately, and offers alarm actions per paired device, authorized only by the
backend. Detection, alarm, shutoff, acknowledgement semantics, persistence and MQTT provenance are
unchanged. Beta scope as before: without configured external leak sensors (H01 remains open).

- Dashboard card 0.4.1: `session` is requested only on connect/instance change, page visible again,
  alarm start, after a card command, on a change of the paired recipient's tracker and every 60 s
  during an alarm (no polling without an alarm; never per render); a detached card makes no requests.
  Home-only buttons are disabled at once when the visible tracker state is not `home`. The session
  answer now includes the recipient's `tracker_entity` (additive, not a secret).
- Dashboard card 0.4.0 (stage C): the card asks the backend (`session`) what this device may do and
  offers only those alarm actions – device mute, global acknowledgement (Home only) and external reset
  (Home, permission, with confirmation) – with the exact event/source binding and `config_entry_id`.
  Rejections are explained per error code (DE/EN). Unpaired devices and older backends stay view only.
  "Home" comes only from the backend; the browser person-entity hint is removed. No backend change.
- Dashboard card 0.3.2: the confirmation before ending a hydraulic alarm reads the detector phase from
  the resolved status sensor, also when the editor points at another sensor of the integration; the
  editor offers only status sensors (`include_entities`). During an ACTIVE High Flow alarm the bypass
  header no longer opens the bypass switch's more-info dialog.
- Dashboard card 0.3.1: alarm hints are now correct per kind (Slow/Low also end when the detector is
  switched off, High when the bypass starts, Burst only physically); switching off an alarming
  Slow/Low detector or starting the bypass during a High Flow alarm asks for confirmation. Generic
  "Leak alarm" headline when the alarm kind is unknown; no "Ready" pills while the runtime store needs
  recovery; no green "All quiet" while an external leak sensor is unreachable. Command placeholders
  match the backend (`external_reset`), still unused. Pairing help text no longer claims card support.
- Dashboard card 0.3.0 ships with the integration and loads automatically: the integration
  serves the bundled file and registers it as an extra frontend module with a content-digest
  cache buster. No file copy or dashboard resource needed. `frontend`/`http` are ordering-only
  `after_dependencies`; leak detection still starts without the frontend. Remove an older manual
  `/local/water-leak-guard-card.js` resource; a duplicate copy only logs a console warning.
- Dashboard card 0.2.0: shows the new hydraulic monitoring state (active, waiting for
  measurement, blocked) separately from the alarm state, with reason and MQTT provenance.
  Green only for confirmed active monitoring; detectors show "paused" otherwise. An ACTIVE
  alarm stays in the headline even while the status reports `source_unavailable`.
- Card no longer offers acknowledge/clear buttons that the backend cannot serve; it explains
  personal mute, Home-only global acknowledgement, external reset and how hydraulic alarms end.
- Backend contract for dashboard card actions (used by the card from 0.4.0): pair a recipient with one
  HA login as an optional field of the recipient entry (add/edit; alarm settings unchanged);
  WebSocket commands `session`, `mute` (device-scoped, anywhere), `acknowledge` (global, Home checked at commit) and
  `external_reset` (Home, permission). Identity is the paired login, never a client token; there is
  no command for hydraulic alarms. Stable error codes for the card.
- Card uses the Home Assistant device name as title; unavailable external sensors are no
  longer shown as dry.

## 1.2.0-beta.3

- Add a regular, always-available hydraulic monitoring status sensor with active,
  waiting-for-measurement and blocked states, plus source diagnostics.
- Translate entity and states in German and English; retain existing alarms,
  evidence, MQTT protection, notification and shutoff behavior.


All notable changes to Water Leak Guard are documented here.

## Dashboard card 0.1.0 (merged before 1.2.0-beta.3)

- Prepared the `water-leak-guard-card` Lovelace card (frontend only, no backend change):
  status, flow, detectors, bypass, external sensors and learning, DE/EN, light/dark.
  Acknowledge (anywhere) and clear alarm (Home only) call proposed WebSocket commands
  and fall back to the Configure dialog. See [docs/CARD.md](docs/CARD.md).

## 1.2.0-beta.1 — 2026-10-14 (release candidate, not published)

- Prepared restricted household beta for hydraulic Slow/Low/High/Burst detection,
  notifications, personal mute, Home-authorized ACK and readable event duration.
- Separated physical MQTT evidence intervals from reception timing so normal
  delivery jitter no longer interrupts Burst confirmation or Low quiet reset.
  Replay, timeout, restart and F15 protections remain unchanged.
- F04 adds separate Rolling/Long-Term learning and legacy-learning quarantine,
  with a new default Burst base of 3,500 L/h; explicit existing values are preserved.
- F04-FSR-H01 remains open for damaged active external-sensor records. This beta
  is restricted to installations without external sources or saved external records.
- Version metadata and a prerelease/not-latest publisher path are prepared.
  No merge, tag or GitHub release has been performed.

## 1.1.0 — 2026-10-10

### High Flow

- High Flow now uses the configured static threshold as its authoritative detector boundary; the default remains 600 L/h.
- Adaptive learning no longer raises or lowers the High threshold. The existing 45-minute / 500-litre activation logic and physical reset behavior remain unchanged.
- Normal high-consumption episodes can now be admitted to adaptive learning only after they end safely and are repeatedly confirmed.

### Low Flow stability

- Added a stability-based early Low Flow path while retaining the existing normal duration path as a safety net.
- With defaults, a continuously stable Low Flow can be confirmed after 30 minutes using a 15-minute time-weighted stability window.
- Stability uses a time-weighted median and requires 90% of confirmed window time inside the larger of ±20 L/h or ±10%.
- The default Low Flow reset is now 3 minutes below the quiet threshold; explicitly stored older values remain preserved.
- Legacy configurations with shorter Low detection times receive compatible derived stability defaults without destructive migration.

### Seasonal learning of normal High Flow

- A clean High MONITORING episode is first stored only as a candidate; one or two episodes cannot affect adaptive references.
- At least three comparable clean episodes within the rolling learning window are required. Peaks are comparable when the cluster satisfies `max_peak <= min_peak * 1.15`.
- The existing learning window, 30 days by default, also ages pending and confirmed High evidence so seasonal behavior naturally falls out of the model.
- Confirmed episodes retain their original completion timestamps and then enter the existing P95, short/long reference and confidence model.
- High Flow bypass, High ACTIVE, Burst/Rapid Rise, other active alarms, source outages, invalid measurements and evidence gaps exclude an episode from High learning.
- After every startup or restore, High learning remains blocked until the complete configured physical High reset has been observed from valid measurement evidence.
- Pending and confirmed High history is restore-safe, F15 clock-rollback-safe, deduplicated and bounded to the newest 4096 valid in-window entries.

### Compatibility and validation

- No new Home Assistant entities or user-facing options are required for the High confirmation gate.
- Existing configuration and stored learning data remain backward compatible.
- High remains static; confirmed normal High episodes can influence only the existing adaptive Burst context through the normal confidence and hydraulic safety limits.
- Final reviewed state: 995 repository tests passed. The independent follow-up review additionally ran 49 external tests and reported no Critical, High, Medium or Low findings.

### Still open

- F04 / Rapid Rise remains a separate detector-design topic and is intentionally not changed in this release.

## 1.0.3 — 2026-10-10

### Safety and reliability

- Hardened persistence and restore handling so malformed or stale runtime data cannot silently weaken confirmed safety state.
- Negative, invalid, stale and out-of-order measurements no longer provide reset or quiet evidence.
- Added plausibility handling for the optional cumulative water meter and prevented rejected meter jumps from being accepted without fresh evidence.
- Preserved confirmed leak events and Water Shut Off requests across source outages and restore paths.
- Notification delivery is tracked per recipient and route, with retry-safe acknowledgement handling and cleanup of ended-event workers.
- Configuration/control changes are applied independently from the arrival of a new flow measurement.
- Source changes no longer inherit old meter baselines or unconfirmed monitoring evidence from a different sensor.

### Deterministic measurement evidence

- Replaced automatic sensor-cadence classification with deterministic evidence from consecutive fresh, valid flow reports.
- Internal ticks never create leak or quiet evidence.
- Constant and irregular report intervals are accepted without cadence learning.
- The optional expert maximum report gap is deterministic: intervals above the configured limit contribute zero time without deleting already confirmed monitoring progress.
- Temporary `unknown`, `unavailable` or invalid flow states pause Slow/Low/High monitoring without discarding already confirmed progress.
- Time spent unavailable contributes zero evidence; the first valid returning report also contributes zero time.
- Burst candidates and Rapid-Rise history remain conservative across observation gaps, while already ACTIVE events remain active.
- A real source rebind remains destructive for unconfirmed evidence, preventing progress from one physical meter from being transferred to another.

### Release and validation hardening

- Release publication is bound to the exact validated commit and verifies existing tags before accepting or creating a release.
- Added extensive regression coverage for persistence, evidence timing, outages, notification routing, source changes, restore behavior and release integrity.
- Final reviewed state: 713 repository tests passed; the independent acceptance review additionally ran 110 external tests and reported 0 Critical, High, Medium or Low findings.

### Known documented limits

- A Home Assistant restart still discards unconfirmed monitoring candidates; ACTIVE events are restored and offline time never counts as evidence.
- Without an explicit maximum report gap, a silent communications outage that never produces `unknown`/`unavailable` cannot be distinguished from a legitimate slowly reporting sensor.
- The separate detector-design topics F02, F04, F08 and the fachliche Rapid-Rise definition remain intentionally reserved for a later feature release.

## 1.0.2 — 2026-10-07

### Added

- Added the repository license: **GNU Affero General Public License v3.0 only (AGPL-3.0-only)**.

### Fixed

- Saving a Configure subsection no longer closes the complete Home Assistant options flow.
- Measurement-source and expert-setting changes return to the main Configure menu after saving.
- Adding, editing, or removing a notification recipient returns to the notification-recipient submenu.
- Added an explicit **Back to configuration** entry to the notification-recipient submenu.
- Fixed literal `\\n\\n` escape sequences being rendered in recipient descriptions.
- Simplified the recipient overview to compact Markdown names instead of long notification-service and tracker IDs.
- Added clearer **Save/Add/Remove and go back** action labels.
- Added regression coverage for Configure navigation and description rendering.

## 1.0.1 — 2026-10-06

### Improved

- Notification-recipient setup now shows all already configured alert devices instead of only the device currently being edited.
- The overview stays visible while adding, editing, or removing recipients.
- Each configured recipient is shown with display name, Companion notification service, and matching device tracker.
- The same overview is available both during initial setup and later through **Configure → Notification recipients**.
- Internal recipient IDs and action tokens remain hidden.

## 1.0.0 — 2026-10-06

### Stable release

- First stable release of Water Leak Guard / Wasserwächter.
- The published manifest explicitly uses `integration_type: "service"`; the integration is therefore exposed through **Settings → Devices & services → Integrations**, not through **Helpers**.
- Supersedes the 0.3.0 GitHub release, whose tag was created before the integration-type and visible-name corrections landed on `main`.
- Keeps the existing technical domain `water_leak_detection` and config-entry model, so an update does not create a new helper/domain.
- Includes the completed detection, notification, acknowledgement, Water Shut Off, adaptive-learning, hydraulic-plausibility, localization, and post-install configuration work from the 0.x roadmap.
- Adds release metadata regression coverage that requires the manifest to stay a normal `service` integration.

## 0.3.0 — 2026-10-06

### Fixed before first 0.3.0 release

- Integration is classified as a normal Home Assistant service integration instead of a helper, so it appears under **Settings → Devices & services → Integrations**.
- Complete runtime localization for English and German using Home Assistant's configured language.
- Device names, entity names, translated sensor states, action labels, and Companion notification text now follow the Home Assistant language.
- Notification recipients can be selected during initial setup.
- Measurement sources, notification recipients, and expert settings can all be reopened later through **Configure**.
- Measurement source entities can additionally be changed through Home Assistant's **Reconfigure** action.

### Added

- Continuous rolling adaptive normal-flow learning.
- Learning confidence states: insufficient, learning, reliable.
- Short-term and long-term references for seasonal adaptation.
- Hydraulic plausibility model using nominal pipe diameter and static pressure.
- Adaptive High Flow and Burst Leak thresholds.
- Rapid rate-of-rise Burst Leak detection.
- Learned maximum, confidence, coverage, hydraulic reference, and effective-threshold sensors.
- `water_leak_detection.reset_learning` action.
- Detector reason in leak/shutoff event payloads.
- Deterministic tests for adaptive learning, hydraulic context, and Burst behavior.

### Safety behavior

- Suspicious High/Burst candidates are excluded from learning.
- High Flow bypass periods are excluded from learning.
- Insufficient learning confidence does not raise safety thresholds.
- Burst Leak remains active during High Flow bypass.
- Adaptive thresholds are bounded by the hydraulic plausibility envelope.

## 0.2.0 — 2026-10-06

### Added

- Multiple Companion App notification recipients.
- Per-device mute.
- Backend-authorized global acknowledgement while the responding device is Home.
- Trusted stationary Home-device support.
- Return-home re-notification for active, globally unacknowledged events.
- Persistent acknowledgement state.
- Add/edit/remove recipient options UI.
- Critical Burst notification payloads for iOS and Android.

## 0.1.0 — 2026-10-06

### Added

- Initial Home Assistant custom integration.
- Config Flow and Options Flow.
- Flow/total source selection and unit normalization.
- Slow Leak, Low Flow, High Flow, and Burst Leak detectors.
- Independent Slow Leak and Low Flow enable switches.
- High Flow bypass.
- Persistent detector/event state.
- Independent Water shutoff request.
- Backend entities, actions, events, translations, and automated tests.
