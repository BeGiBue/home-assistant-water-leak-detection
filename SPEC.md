> **Aktueller Implementierungsvertrag: F04 V3.** Die verbindlichen Regeln für
> Schema-2-Migration, getrennte Lernkanäle, Burst/Rapid Rise und externe Quellen
> stehen in [docs/F04_V3.md](docs/F04_V3.md). F02 und F08 bleiben geschlossen.
> Die darunterstehenden älteren Roadmap- und Entwurfsabschnitte sind historischer
> Kontext; abweichende Burst-/High-Lernanforderungen werden durch V3 ersetzt.
> Keine Release- oder Merge-Freigabe, Produktversion unverändert 1.1.0.

> Sicherheitskorrektur: Unterstützte Store-Versionen mit nicht-dict Body werden
> konservativ gesperrt. MQTT-Timeouts und direkte Gap-Rückkehr verwenden eine
> persistierte Ausschlussgrenze; Vor-Ausfall-Messungen sind keine Reset-Evidenz.
> Externe Konfliktidentitäten behalten alle ACTIVE-/Shutoff-Beiträge und sperren
> betroffene ACK-/Reset-Capabilities. [Recovery-Vertrag](docs/F04_LOW_ACK_DURATION.md#safety-recovery-and-mqtt-interruption-boundaries).

# Water Leak Guard

## 1. Purpose

This repository contains the backend implementation of a Home Assistant custom integration for detecting abnormal water consumption and possible leaks.

The integration must remain backend-focused. A dedicated frontend/Lovelace card is explicitly out of scope for the initial versions and may be developed separately later.

The integration shall use Home Assistant native entities, services, events, config flows and option flows wherever possible.

---

## 2. Project identity

- **Display name:** Water Leak Guard
- **Repository:** `BeGiBue/homeassistant-water-leak-detection`
- **Target platform:** Home Assistant
- **Scope:** Backend integration only
- **Frontend/custom card:** Out of scope for now
- **Preferred integration domain:** `water_leak_detection`

The technical domain should remain stable once released because renaming a Home Assistant integration domain later is disruptive.

---

## 3. Primary data sources

The integration shall allow the user to select either a device or individual entities as measurement sources.

### 3.1 Required source

A flow-rate sensor is required.

Example from the reference installation:

`sensor.wasserzahler_flow`

Reference characteristics:

- native unit: `m³/h`
- resolution: 0.001 m³/h
- effective resolution: 1 l/h

Internally, all flow values shall be normalized to **litres per hour (l/h)**.

### 3.2 Optional but strongly recommended source

A cumulative consumption / total water meter entity.

Example:

`sensor.wasserzahler_total`

Internally, total consumption shall be normalized to **litres (l)**.

This source is used to:

- measure event volume,
- plausibility-check flow-rate measurements,
- provide event statistics,
- improve future high-flow and burst-leak detection.

---

## 4. Detection classes

The integration shall treat the following four detection classes as separate detectors:

1. Slow Leak
2. Low Flow
3. High Flow
4. Burst Leak

Each detector must have independent logic, timing, thresholds and reset behavior.

They may contribute to a common overall status, but must not be implemented as one generic threshold detector.

---

## 5. Slow Leak

### 5.1 Typical use cases

- leaking toilet cistern,
- small continuous pipe leakage,
- dripping or slightly leaking fittings,
- other very small but continuous losses.

### 5.2 Default logic

Initial default:

- threshold: **3 l/h**
- detection time: **60 minutes continuous**
- reset time: **10 minutes below threshold**

Example:

A constant flow of 7 l/h should reliably result in a Slow Leak event after 60 minutes.

### 5.3 Behavior

- Measurement must be continuous enough to identify a persistent leak.
- If flow drops below the threshold long enough to satisfy the reset condition, the monitoring timer resets.
- Acknowledging an alarm must **not** terminate the detector state.
- Detection ends only when the detector reset condition is actually met.

### 5.4 Notification severity

Default severity:

`notice`

---

## 6. Low Flow

### 6.1 Typical use case

A tap has been left running.

Low Flow is **not** the same as Slow Leak.

It represents a moderate water flow that is individually plausible but persists for an implausibly long period.

### 6.2 Main design constraint

Normal household usage must not cause nuisance notifications.

In particular, consecutive showers by several people must not trivially trigger a Low Flow alarm.

### 6.3 Initial defaults

Provisional defaults:

- start threshold: **150 l/h**
- detection duration: **60 minutes**
- quiet-flow threshold: **20 l/h**
- quiet period required for reset: **3 minutes**

The values must be configurable in expert settings.

### 6.4 Reset logic

Low Flow must not reset on every short drop in flow.

Instead, the event resets only after a configurable quiet period, by default 3 minutes.

Default:

**3 minutes below the quiet threshold**

### 6.5 Stability acceleration (F08)

Low Flow has two activation paths in the band **150 L/h ≤ flow < the static High threshold** (default 600 L/h):

- **Long-lasting Low Flow:** the normal 60-minute path remains the safety net, including variable consumption.
- **Particularly steady Low Flow:** enabled by default, activation after 30 minutes of continuous confirmed Low evidence, with a stable trailing 15-minute window.

Steadiness is an additional indication of a tap left open, **not a prerequisite for Low Flow detection**. The reference is the time-weighted median M of the window; tolerance is `max(20 L/h, 0.10 × M)`. At least 90% of confirmed window time must lie within `M ± tolerance`. Both the median and the share use interval duration, not sample count. The oldest interval is trimmed at the window boundary. Credited intervals belong to the current valid report, following F05; the first report in a new chain contributes zero seconds. Different reporting frequencies therefore do not add extra weight; sampling still limits which physical variations can be observed.

Any real report below the Low threshold immediately discards the stability series, including 20–149 L/h and even a short quiet pause. Thus 15 minutes steady, 30 seconds quiet, then 15 minutes steady cannot trigger early activation. The normal Low progress continues under its existing rules until a full quiet reset. A continuous confirmed phase **below 20 L/h for 3 minutes** resets Low monitoring and active Low events (179 seconds does not; 180 seconds does). Existing explicitly saved reset durations, including 7 minutes, remain unchanged.

High-band reports discard Low stability and retain the existing Low/High handover. Unknown, unavailable and invalid values interrupt stability; the returning first report contributes zero evidence. Round7 retains normal confirmed Low progress across same-source outages. Internal ticks supply no evidence. Stability cannot end an already ACTIVE Low event; only its physical quiet/reset condition does. Stability history is transient and is rebuilt after restart; active event persistence is unchanged.


Presence and device-state context may be added as a second-stage modifier, but must not be required for base detection.

### 6.6 Notification severity

Default severity:

`notice`

---

## 7. High Flow

### 7.1 Meaning

High Flow is **not automatically a leak**.

Typical valid causes include:

- filling a bathtub,
- garden irrigation,
- filling a pool,
- other sustained high-consumption activities.

High Flow therefore represents unusual but potentially legitimate sustained consumption.

### 7.2 Detection concept

High Flow should combine:

- flow rate,
- event duration,
- accumulated volume.

Provisional values may initially be used, but the final logic should be configurable and later informed by learned household behavior.

Example provisional starting point:

- flow >= 600 l/h,
- and/or sustained duration,
- and/or event volume above a configured threshold.

### 7.3 Notification severity

Default severity:

`warning`

---

## 8. High Flow bypass

High Flow must have a dedicated temporary bypass.

Typical use case:

Filling a pool.

### 8.1 Required behavior

While bypass is active:

- Slow Leak remains active.
- Low Flow remains active.
- High Flow detection is suppressed.
- Burst Leak remains fully active.

**Burst Leak must never be disabled by the High Flow bypass.**

### 8.2 Home Assistant exposure

The bypass shall be reachable directly from Home Assistant and from automations.

It must not exist only as an internal configuration flag.

Preferred implementation:

- native HA timer-style entity or equivalent HA-native controllable entity,
- remaining time visible in Home Assistant,
- callable from scripts/automations.

The integration shall also expose service actions for programmatic control if needed, for example:

- start High Flow bypass with a supplied duration,
- cancel High Flow bypass.

The bypass must always expire automatically.

A permanently forgotten bypass is unacceptable.

---

## 9. Burst Leak

### 9.1 Meaning

Burst Leak represents catastrophic or near-catastrophic failure such as:

- burst pipe,
- failed hose,
- major line rupture.

### 9.2 Detection principles

Burst Leak must be independent from High Flow.

It must be detected aggressively using a combination of:

1. very high absolute flow,
2. rapid increase in flow,
3. learned household maximum,
4. hydraulic plausibility limits.

The implementation should support both:

### Absolute burst

Very high flow sustained for only a short confirmation period.

### Dynamic burst

A very rapid rise in flow over a short period.

### 9.3 Bypass behavior

Burst Leak ignores the High Flow bypass completely.

### 9.4 Notification severity

Default severity:

`critical`

Critical Companion App notification behavior must support iOS and Android using their respective Home Assistant Companion mechanisms.

---

## 10. Hydraulic installation parameters

Expert settings shall allow configuring installation parameters.

Reference installation:

- nominal pipe size: **1" / DN25**
- static pressure: **3.5 bar**

These values must **not** be used as the sole basis for a burst threshold.

They provide a hydraulic plausibility envelope.

Actual deliverable flow also depends on:

- water meter,
- pressure reducer,
- pipe length,
- fittings,
- dynamic pressure,
- upstream supply conditions.

### 10.1 Expert settings

Provide at minimum:

- nominal pipe size / diameter,
- static pressure,
- optional manually known maximum flow,
- automatic learned maximum flow,
- relevant safety factors.

---

## 11. Adaptive learning

The integration shall continuously learn normal peak water consumption.

This is not a one-time calibration.

### 11.1 Reason

Normal usage varies seasonally.

Examples:

- longer/hotter showers in colder periods,
- shorter/cooler showers in summer,
- more frequent baths in cold weather,
- seasonal garden usage.

The learned reference must therefore continue to adapt.

### 11.2 Learning window

Default rolling learning window:

**30 days**

Expert options may allow values such as:

- 14 days,
- 30 days,
- 60 days,
- 90 days.

### 11.3 Learning state

The integration must expose that a learned maximum is not immediately trustworthy.

Required user-visible information:

- learned maximum flow,
- configured learning window,
- amount of valid learning history,
- learning confidence / reliability state.

Suggested confidence states:

- `insufficient`
- `learning`
- `reliable`

Example representation:

- learned maximum: 1240 l/h
- learning window: 30 days
- valid data: 23 days
- confidence: reliable

### 11.4 Continuous adaptation

A combination of shorter-term and longer-term statistics may be used.

Example:

- short horizon around 7 days,
- longer horizon around 30 days.

The algorithm should adapt to changing household behavior without reacting excessively to one isolated day.

### 11.5 Learning safety

Detected suspicious events must never automatically teach the system that an extreme flow is normal.

At minimum, the following must be excluded from normal learning:

- Burst Leak events,
- detected High Flow anomalies,
- other events already classified as suspicious.

New extreme maxima should require either:

- strong plausibility checks,
- or explicit confirmation,
- or conservative statistical admission.

### Repeatedly confirmed normal High episodes

F04 V3 separates High learning completely from Rolling Learning. High remains
static (600 L/h, 45 minutes OR 500 L, five minutes below 100 L/h by default).
Only clean, fully observed High-MONITORING episodes below the **configured Burst
base** can enter Long-Term learning. Three independent episodes with
`max_peak <= min_peak * 1.15` confirm the first maximum. Every later increase
requires three **new** episodes above the previous maximum. High peaks never
become Rolling LearningSamples or receive its old multiplier again.

Long-Term pending and confirmed audit history do not expire; validated identities
share a deterministic newest-4096 budget, while the independent confirmed maximum
remains monotonic. Original timestamps and exact per-list F15 permissions are
preserved. Running episodes are transient. Bypass, alarms, Burst/Rapid Rise and
measurement gaps exclude episodes. Every startup requires the full configured
physical High quiet reset before a new eligible episode. Rolling P95, the default
30-day window and Confidence remain unchanged for ordinary samples.

See [F04 V3](docs/F04_V3.md) for the schema-2 legacy quarantine, separate threshold
formula, learning reset/source identity and external sensors.


---

## 12. Overall detector priority

If multiple detectors are active simultaneously, the highest-severity active detector determines the overall state.

Priority:

`Slow Leak < Low Flow < High Flow < Burst Leak`

A Burst Leak must immediately supersede any lower-severity status.

Lower detector states may remain internally tracked if useful.

---

## 13. State architecture

Detection, alarm delivery, acknowledgement and shutoff request must be **strictly separated**.

These are four different concepts:

1. **Detection** — what condition is currently detected?
2. **Alarm / notification** — who should be notified?
3. **Acknowledgement** — who has acknowledged or muted the event?
4. **Shutoff request** — should an external water valve be closed?

Acknowledging an alarm must not clear a detector.

Acknowledging an alarm must not automatically clear a shutoff request.

Ending a notification must not imply that the water problem has ended.

---

## 14. Event model

Each detected incident shall have its own event identity.

Example:

`slow_leak_20261006_001`

An active event should internally track at least:

- event ID,
- detector type,
- start time,
- duration,
- flow statistics,
- cumulative event volume,
- global acknowledgement state,
- recipient/device acknowledgement state.

When the physical condition ends and later returns, a **new event ID** must be created.

Acknowledgement must never permanently suppress future events of the same detector type.

---

## 15. Notification recipients

The integration shall support multiple Home Assistant Companion notification recipients.

Each notification target should be configurable individually.

Per-recipient/device settings should support:

- notification enabled,
- critical alerts enabled,
- personal acknowledgement allowed,
- global acknowledgement allowed when device is at home,
- presence tracker,
- trusted stationary-device behavior.

The implementation must treat notification devices independently even if multiple devices belong to the same person.

---

## 16. Device-based acknowledgement

Acknowledgement shall primarily be associated with the responding device, not merely with a Home Assistant person entity.

This is required because one person may use multiple devices.

Reference example:

- iPhone: mobile/personal device
- iPad: remains at home and may be used by other household members

### 16.1 Personal mute

Any authorized notification device may mute the current event **for itself**.

This only suppresses future notifications for that device for the current event.

It does not clear:

- the detector,
- the event,
- notifications for other devices,
- the shutoff request.

### 16.2 Global acknowledgement

Global acknowledgement suppresses further normal notifications for the active event across configured recipients.

It does **not** terminate the active leak event.

Global acknowledgement may only be accepted when the requesting device satisfies the configured home-presence rule.

This authorization must be checked in the backend.

The UI/notification button alone must not be trusted as authorization.

---

## 17. Geofencing and home presence

Each notification device may be linked to an appropriate Home Assistant device tracker.

Examples:

- `device_tracker.iphone`
- `device_tracker.ipad`

A `person.*` entity may still be useful for presence-related detector context, but acknowledgement authorization must be based on the device that submitted the action.

### 17.1 Device away from home

A device outside the Home zone may:

- mute the event for itself.

It may not:

- globally acknowledge the event.

### 17.2 Device at home

An authorized device in the Home zone may:

- mute for itself,
- globally acknowledge the event.

---

## 18. Trusted stationary devices

The integration shall support trusted stationary devices.

Example:

An iPad remains at home and may be used by the user's spouse or daughter.

The device may be configured as:

**trusted stationary home device**

If the device is in the Home zone, it may globally acknowledge an event regardless of which household member is physically holding it.

This avoids incorrectly tying acknowledgement permissions to a single person entity.

---

## 19. Re-notification on arrival home

For every configured notification device, the integration shall monitor the presence transition from away to Home while an event is active.

When the device changes from:

`not_home -> home`

the integration shall check:

- is the event still active?
- is the event not globally acknowledged?

If both conditions are true:

- clear that device's personal mute for the event if one exists,
- send the active event notification to that device again.

A prior personal mute is therefore not required for the return-home notification. Returning Home is treated as a fresh safety context.

The notification should clearly state that the condition is still active and may include:

- event duration,
- volume consumed since event start,
- current flow,
- event type.

A stationary device that never left home must not trigger this arrival behavior.

---

## 20. Shutoff request

The integration shall provide a clearly defined output for an optional motorized main water shutoff valve.

This output must be **decoupled from the alarm state**.

Suggested entity:

`binary_sensor.water_shutoff_request`

The exact final entity ID may follow Home Assistant naming conventions, but the semantic contract must remain stable.

### 20.1 Configurable detector-to-shutoff mapping

Each detector type may be configured to request shutoff independently.

Slow Leak and Low Flow must therefore be configurable to request shutoff if the user explicitly wants this.

They must not be hard-coded as incapable of shutdown.

Typical defaults may be conservative, for example:

- Slow Leak: off
- Low Flow: off
- High Flow: off or optional
- Burst Leak: on when automatic shutdown is enabled

But this is configuration, not hard-coded detector behavior.

### 20.2 Direct valve control

The integration may optionally allow selecting an existing Home Assistant valve/switch entity and directly operating it.

Supported operating modes should conceptually include:

- notification only,
- shutoff request only,
- direct valve control.

Automatic physical shutoff must require explicit user opt-in.

### 20.3 Independence from acknowledgement

Global or personal acknowledgement must not automatically remove a shutoff request.

Only the configured shutoff/reset rules may do that.

---

## 21. Home Assistant entities

The final names may be adapted to HA conventions, but the integration should expose a compact, useful backend entity model.

Suggested entities:

- independent Slow Leak enable/disable switch,
- independent Low Flow enable/disable switch,
- overall leak status sensor,
- overall active-alarm binary sensor,
- shutoff-request binary sensor,
- High Flow bypass timer/control entity,
- learned maximum-flow sensor,
- learning-confidence sensor,
- active-event duration sensor,
- active-event volume sensor,
- acknowledgement button/action where appropriate.

Avoid creating one entity for every internal implementation detail.

Device-specific acknowledgement state should normally remain internal rather than creating large numbers of entities.

---

## 22. Home Assistant services/actions

The integration should expose HA-native actions where entity interaction alone is insufficient.

Candidate actions:

- start High Flow bypass with duration,
- cancel High Flow bypass,
- acknowledge current event,
- mute event for a specific recipient/device,
- globally acknowledge event,
- trigger/request shutdown,
- reset adaptive-learning data.

Service/action names should follow the final integration domain.

Authorization checks for acknowledgement must happen in backend logic.

---

## 23. Home Assistant events

Where useful for external automations, the integration may emit events such as:

- leak event started,
- leak event ended,
- severity changed,
- shutdown requested,
- global acknowledgement accepted/rejected.

Example shutdown event payload:

```yaml
type: burst_leak
event_id: burst_leak_20261006_001
flow_lph: 2870
duration_seconds: 18
reason: absolute_burst_threshold
```

Events must not replace persistent entity states where a stateful HA entity is more appropriate.

---

## 24. Configuration UI

Configuration is handled through Home Assistant's integration UI.

No custom frontend card is part of the backend scope.

### 24.1 Initial configuration

The normal setup flow should stay simple.

Suggested sections:

1. Measurement sources
2. Notification recipients
3. Protection behavior
4. Optional valve/shutoff configuration

### 24.2 Expert settings

Advanced parameters belong in an Options Flow / expert area.

Expert settings include at least:

- Slow Leak threshold and duration,
- Slow Leak reset duration,
- Low Flow threshold,
- Low Flow detection duration,
- Low Flow quiet threshold,
- Low Flow reset duration,
- Low Flow stability enable, early duration, window, relative/absolute tolerance and required stable share,
- High Flow parameters,
- Burst Leak parameters,
- learning window,
- hydraulic pipe size,
- static pressure,
- manually supplied maximum flow,
- safety factors,
- detector-to-shutoff mapping,
- notification severity behavior.

Normal users should not be required to understand these values during initial setup.

---

## 25. Persistence and restart behavior

Relevant state must survive Home Assistant restarts where technically reasonable.

At minimum, design for persistence of:

- active event identity and start time,
- High Flow bypass expiry,
- learning history / learned reference values,
- acknowledgement state for active incidents where appropriate,
- shutoff-request state where required.

A Home Assistant restart must not silently convert an ongoing serious leak into a clean idle state without re-evaluation.

---

## 26. Units and normalization

Internal logic should use consistent units.

Preferred internal units:

- flow: **l/h**
- volume: **l**
- duration: seconds internally, HA-native display externally where appropriate.

Supported input sensors may expose other compatible units such as:

- m³/h,
- l/min,
- l/h,
- m³,
- l.

Conversions must be explicit and tested.

---

## 27. Error and availability handling

The integration must handle unavailable, unknown or malformed source sensor states safely.

A missing source value must not be interpreted as zero flow.

The integration should expose degraded/unavailable status when required rather than silently clearing an active condition.

Burst protection must fail conservatively where practical.

---

# 28. Implementation Roadmap

The implementation shall be delivered incrementally.

The roadmap is part of the specification and is intended to keep implementation reviewable and testable.

---

## v0.1.0 — Core Detection & Backend

### Scope

Implement the backend foundation.

Required:

- Home Assistant custom integration structure,
- manifest,
- Config Flow,
- Options Flow foundation,
- selection of flow sensor,
- selection of optional total-consumption sensor,
- unit normalization,
- Slow Leak detector,
- Low Flow detector,
- common detector/state architecture,
- High Flow detector framework,
- Burst Leak detector framework,
- active-event model and event IDs,
- overall status entity,
- active alarm entity,
- High Flow bypass as a Home Assistant-accessible timer/control,
- bypass callable from automations,
- bypass expiry persistence,
- independent shutoff-request entity,
- configurable detector-to-shutoff mapping foundation,
- persistent state model,
- diagnostic logging,
- automated tests for implemented behavior.

### Explicitly not required yet

- full Companion App notification workflow,
- device-specific acknowledgement,
- geofencing acknowledgement authorization,
- adaptive learned maximum flow,
- final hydraulic Burst algorithm.

The architecture must nevertheless be designed so these can be added without replacing the core event model.

### Definition of Done — v0.1.0

v0.1.0 is complete only when:

- integration can be added through HA UI,
- configured source entities are validated,
- input units are normalized correctly,
- Slow Leak behavior passes automated tests,
- Low Flow behavior passes automated tests,
- High Flow bypass affects only High Flow,
- Burst framework cannot be disabled by High Flow bypass,
- shutoff request is independent of alarm acknowledgement,
- restart/state restoration behavior has tests,
- invalid/unavailable measurements are handled safely,
- code follows current Home Assistant development conventions,
- linting/static checks used by the repository pass,
- README documents installation and basic configuration.

---

## v0.2.0 — Notifications, Devices & Acknowledgement

### Scope

Add multi-device Home Assistant Companion notification behavior.

Required:

- multiple notification recipients,
- recipient-specific settings,
- normal notifications,
- critical notification support for iOS,
- critical/high-priority behavior for Android Companion,
- actionable notifications,
- per-device mute for current event,
- global acknowledgement,
- backend authorization for global acknowledgement,
- device tracker association,
- home-zone validation,
- trusted stationary home devices,
- event-specific acknowledgement state,
- re-notification on `not_home -> home`,
- no re-notification after global acknowledgement,
- no permanent suppression of future event IDs.

### Definition of Done — v0.2.0

v0.2.0 is complete only when:

- multiple devices can receive the same event,
- one device can mute only itself,
- a device away from Home cannot globally acknowledge,
- an authorized device at Home can globally acknowledge,
- a trusted stationary tablet at Home can globally acknowledge,
- every configured mobile device is re-notified when it returns Home while the event remains active and is not globally acknowledged,
- global acknowledgement does not clear detection,
- acknowledgement does not automatically clear shutoff request,
- new physical leak occurrence creates a new event and notification cycle,
- all security-relevant acknowledgement checks are enforced in backend code,
- behavior is covered by automated tests.

---

## v0.3.0 — Adaptive Detection & Hydraulic Model

### Scope

Implement continuous adaptive learning and mature High Flow/Burst detection.

Required:

- rolling normal-flow learning,
- learned maximum-flow sensor,
- learning-window state,
- confidence/reliability state,
- configurable rolling learning window,
- safe exclusion of suspicious events from learning,
- seasonal adaptation,
- short-term and long-term reference logic,
- DN/pipe-size configuration,
- static pressure configuration,
- optional manual maximum-flow reference,
- hydraulic plausibility layer,
- mature High Flow logic using flow + duration + volume,
- mature Burst Leak logic using absolute flow + rate-of-rise + learned/hydraulic context,
- conservative behavior while learning confidence is insufficient.

### Definition of Done — v0.3.0

v0.3.0 is complete only when:

- learned maximum is visible in HA,
- learning-window coverage is visible,
- confidence is visible,
- initial unreliable learning state is clearly represented,
- learning updates continuously rather than through one-time calibration,
- suspicious leak events cannot silently raise the learned normal maximum,
- Burst detection works with both low and high learning confidence,
- High Flow remains bypassable,
- Burst remains non-bypassable,
- hydraulic settings are treated as plausibility context rather than exact theoretical truth,
- learning and Burst algorithms are covered by deterministic automated tests.

---

## 29. Future scope

Potential later additions may include:

- optional custom Lovelace card,
- richer flow-pattern classification,
- presence-aware Low Flow timing,
- appliance/device-state context,
- statistical anomaly scoring,
- user-guided calibration workflow,
- direct integration with compatible smart shutoff valves.

These features must not be required for the first three implementation milestones.

---

## 30. Non-negotiable design rules

The following rules are binding across all implementation versions:

1. **Burst Leak is independent from High Flow.**
2. **High Flow bypass must never suppress Burst Leak.**
3. **Detection, notification, acknowledgement and shutoff request are separate concepts.**
4. **Acknowledgement must never mean that a leak physically ended.**
5. **Shutoff request is configurable independently of alarm state.**
6. **Slow Leak and Low Flow may be configured to request shutoff.**
7. **Global acknowledgement authorization is checked in backend logic.**
8. **An away device may mute only itself.**
9. **An authorized Home device may globally acknowledge.**
10. **Trusted stationary Home devices are supported.**
11. **A personally muted mobile device must be re-notified upon returning Home if the event is still active and not globally acknowledged.**
12. **Adaptive learning is continuous and rolling, not one-time calibration.**
13. **Suspicious events must not automatically redefine abnormal behavior as normal.**
14. **The integration must remain usable without any custom frontend card.**
15. **Home Assistant-native mechanisms should be preferred wherever practical.**
16. **Slow Leak and Low Flow detector enable state is independent from alarm state and exposed as dedicated HA entities.**

## F02 — Statische High-Flow-Startschwelle

High startet MONITORING exakt bei `high_threshold_lph` (Standard 600 L/h).
Slow: 3 bis <150 L/h; Low: 150 bis <High; High: >=High. Lernen, manuelles
Maximum, Hydraulik, Multiplikatoren und `effective_high_threshold_lph` dürfen
diese Grenze nicht verschieben. Die Engine nutzt statisches High auch als
Referenz im bestehenden Dynamic Burst Floor. Burst bleibt adaptiv; F04 und
Rapid Rise werden nicht neu definiert. Bestätigung über Dauer/Volumen,
Quiet/Reset und High-Bypass bleiben unverändert.

`high_learned_multiplier` bleibt als gespeicherter Altwert toleriert, wird
nicht angezeigt oder verwendet. Der Burst-Multiplikator bleibt unabhängig.
`effective_high_threshold` behält Entity-Identität und translation key.

Der allgemeine Lernpfad behandelt High-MONITORING weiterhin als suspicious.
Der separate High-Normal-Pfad darf ausschließlich mehrfach bestätigte, sauber
beendete High-Episoden als Burst-Normalkontext zulassen. Bypass und Alarmepisoden
bleiben ausgeschlossen. Die F02-Detektionsregeln ändern sich dadurch nicht.
F02 bleibt unverändert; F04 und Rapid Rise folgen dem freigegebenen V3-Vertrag.

## Low reset, acknowledgement and duration follow-up

MQTT Flow sensors need `force_update: true` to expose repeated equal telegrams.
Short MQTT expiry or explicit source timeout can repeatedly interrupt reset
evidence. Missing reports never mean zero. Configure now provides an authorized
active-event acknowledgement form; numeric event seconds gain DE/EN display
attributes. Full diagnostics, semantics and limits: [follow-up contract](docs/F04_LOW_ACK_DURATION.md).


### F04 Sicherheitsreview: MQTT-Messherkunft und Quittierung

MQTT-Durchflussquellen benötigen jetzt die originale timezone-aware Radio-/
Empfänger-Messzeit im JSON-Feld `timestamp`; `force_update` allein beweist keine
neue Messung. Retained, alte oder ungebundene Nachrichten liefern keine Evidenz.
Fehlende Messherkunft sperrt die Auswertung und erzeugt einen Repair-Hinweis;
bestehende ACTIVE-Alarme bleiben erhalten. Die fremde Discovery wird nicht
überschrieben. Details und Vertrauensgrenzen: [Low/ACK/Dauer](docs/F04_LOW_ACK_DURATION.md).

ACK wird erst nach erfolgreicher Persistenz veröffentlicht. Das Configure-ACK ist
administrative Delegation anhand des ausgewählten Recipients und dessen Home-
Tracker. Status und Dauer wählen dasselbe hydraulische oder externe Ereignis.
