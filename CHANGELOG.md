# Changelog

## 1.2.0-beta.3

- Add a regular, always-available hydraulic monitoring status sensor with active,
  waiting-for-measurement and blocked states, plus source diagnostics.
- Translate entity and states in German and English; retain existing alarms,
  evidence, MQTT protection, notification and shutoff behavior.


All notable changes to Water Leak Guard are documented here.

## Unreleased

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
