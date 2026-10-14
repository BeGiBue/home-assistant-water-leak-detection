# Configuration reference

Runtime safety recovery never resets an alarm by discarding its Store. An ERROR
repair explains damaged bodies or conflicting external event identities. Preserve
the file, stop HA and restore a verified complete backup; see the
[recovery procedure](F04_LOW_ACK_DURATION.md#safety-recovery-and-mqtt-interruption-boundaries).
`identity_conflict` sources retain alarm/Shutoff and cannot use ambiguous ACK/reset
actions. MQTT timeout/restart boundaries also reject buffered pre-outage values.

## Reopening the configuration

After installation, open **Settings → Devices & services → Integrations → Water Leak Guard → Configure**.

The configuration remains editable and contains:

- **Measurement sources**
- **Notification recipients**
- **Expert settings**

The measurement-source form is also available through Home Assistant's **Reconfigure** action.

Saving a Configure subsection keeps the options flow open. Measurement sources and expert settings return to the main Configure menu; recipient add/edit/remove actions return to the notification-recipient submenu. That submenu includes an explicit **Back to configuration** action.

## Measurement sources

A flow-rate sensor is required. A cumulative consumption sensor is optional but recommended.

The config flow supports:

- direct selection of individual sensor entities,
- selecting a Home Assistant device and choosing compatible entities from it.

Internally:

- flow is normalized to L/h,
- cumulative consumption is normalized to L.

A missing or unavailable flow sensor is not treated as zero flow.

## Slow Leak

Default:

- threshold: 3 L/h
- detection time: 60 min
- reset: 10 min below threshold

Typical purpose: leaking toilet cistern, tiny continuous losses, small fitting leaks.

Slow Leak has its own enable/disable switch.

## Low Flow

Default:

- start threshold: 150 L/h
- detection time: 60 min
- quiet threshold: 20 L/h
- quiet/reset time: 3 min

Typical purpose: a tap left running.

Low Flow has two activation paths in the band **150 L/h ≤ flow < the static High threshold** (default 600 L/h):

- **Long-lasting Low Flow:** the normal 60-minute path remains the safety net, including variable consumption.
- **Particularly steady Low Flow:** enabled by default, activation after 30 minutes of continuous confirmed Low evidence, with a stable trailing 15-minute window.

Steadiness is an additional indication of a tap left open, **not a prerequisite for Low Flow detection**. The reference is the time-weighted median M of the window; tolerance is `max(20 L/h, 0.10 × M)`. At least 90% of confirmed window time must lie within `M ± tolerance`. Both the median and the share use interval duration, not sample count. The oldest interval is trimmed at the window boundary. Credited intervals belong to the current valid report, following F05; the first report in a new chain contributes zero seconds. Different reporting frequencies therefore do not add extra weight; sampling still limits which physical variations can be observed.

Any real report below the Low threshold immediately discards the stability series, including 20–149 L/h and even a short quiet pause. Thus 15 minutes steady, 30 seconds quiet, then 15 minutes steady cannot trigger early activation. The normal Low progress continues under its existing rules until a full quiet reset. A continuous confirmed phase **below 20 L/h for 3 minutes** resets Low monitoring and active Low events (179 seconds does not; 180 seconds does). Existing explicitly saved reset durations, including 7 minutes, remain unchanged.

High-band reports discard Low stability and retain the existing Low/High handover. Unknown, unavailable and invalid values interrupt stability; the returning first report contributes zero evidence. Round7 retains normal confirmed Low progress across same-source outages. Internal ticks supply no evidence. Stability cannot end an already ACTIVE Low event; only its physical quiet/reset condition does. Stability history is transient and is rebuilt after restart; active event persistence is unchanged.

| Expert option | Default |
|---|---|
| `low_stability_enabled` | true |
| `low_stability_early_minutes` | 30 min |
| `low_stability_window_minutes` | 15 min |
| `low_stability_relative_percent` | 10% |
| `low_stability_absolute_lph` | 20 L/h |
| `low_stability_required_percent` | 90% |
| `low_reset_minutes` (only when unset) | 3 min |

When stability is enabled, the window must be positive and no longer than early detection, which must be shorter than normal Low detection. When disabled, the relation between stability times does not block saving; saved times remain intact and are checked again on reactivation. Tolerances must be positive; required share must be >0 and ≤100%. No additional HA entities are created.

Only missing stability times are derived jointly for UI and runtime: `early = min(30, normal / 2)` minutes and `window = min(15, resolved early / 2)` minutes, rounded down to the 0.1-minute UI grid with a 0.1-minute minimum. An explicit early time is used when deriving a missing window. Explicitly stored times are never overwritten. For the UI's normal Low minimum of 1 minute, the derived times remain valid.

| Normal Low detection | Missing early default | Missing window default |
|---|---:|---:|
| 10 min | 5 min | 2.5 min |
| 20 min | 10 min | 5 min |
| 30 min | 15 min | 7.5 min |
| 60 min | 30 min | 15 min |

Low Flow has its own enable/disable switch.

## High Flow

High Flow represents unusually high but potentially legitimate water use.

The start threshold is static and configurable in expert settings (default
600 L/h). Low Flow covers 150 L/h to strictly below this threshold; High Flow
starts MONITORING at the threshold, with no gap. Learned maxima, manual maxima
and hydraulics cannot raise it. Duration, volume, quiet and reset confirmation
rules are unchanged: reaching 600 L/h is not an immediate alarm.

The former High multiplier is hidden and ignored; existing saved values are
preserved. The Burst multiplier remains available without a High-multiplier
comparison. Burst remains adaptive; Rapid Rise qualifies only at or above effective Burst.

High Flow can be temporarily bypassed. This bypass does not disable Burst Leak.

## Burst Leak

Burst Leak is intended for major failures such as a burst pipe or failed hose.

Detection combines:

- adaptive absolute flow threshold,
- rapid rate-of-rise detection,
- learned household context,
- hydraulic plausibility.

Burst Leak remains active during High Flow bypass.

## High Flow bypass

Backend controls:

- High Flow bypass switch
- High Flow bypass duration number
- High Flow bypass remaining sensor
- `water_leak_detection.start_high_flow_bypass`
- `water_leak_detection.cancel_high_flow_bypass`

The bypass expires automatically and its expiry is persisted across Home Assistant restarts.

## Companion notification devices

Recipients can be selected during initial setup and managed later under **Configure → Notification recipients**. The overview shows the configured display names in a compact list; technical notification-service and tracker IDs remain available in the edit forms instead of being repeated in the overview.

Each recipient is configured independently with:

- display name,
- `notify.mobile_app_*` service,
- matching `device_tracker.*`,
- critical-alert permission,
- global acknowledgement permission while Home,
- optional trusted stationary Home-device flag.

### Personal mute

An authorized notification device can mute the current event for itself.

This does not clear:

- the detector state,
- the event,
- notifications on other devices,
- the shutoff request.

### Global acknowledgement

Global acknowledgement is accepted only when:

- the device is configured to allow it, and
- its assigned `device_tracker.*` currently reports `home`.

Authorization is checked by backend logic, not only by which notification button is shown.

### Trusted stationary Home device

A shared tablet that normally remains Home can be marked as trusted stationary.

This allows the device itself to act as a Home terminal for global acknowledgement without assuming which person is holding it.

### Return Home

When a configured notification device transitions from away to Home while an event is still active and not globally acknowledged, it is notified again.

Any per-device mute for that event is cleared when the device returns Home.

## Adaptive learning

Default learning window: 30 days.

The learner admits completed normal-use episodes and excludes suspicious events and bypass periods.

Confidence states:

- `insufficient`
- `learning`
- `reliable`

The model combines recent and longer-term references to allow seasonal adaptation.

Use `water_leak_detection.reset_learning` to clear normal samples, pending High candidates, confirmed High history and their rollback context.

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

See [F04 V3](F04_V3.md) for the schema-2 legacy quarantine, separate threshold
formula, learning reset/source identity and external sensors.


## Hydraulic settings

Reference defaults:

- nominal diameter: 25 mm / DN25
- static pressure: 3.5 bar

These settings form a plausibility envelope only. They are not an exact theoretical maximum-flow calculation.

## Shutoff request

Each detector can be configured independently to request shutoff.

The **Water shutoff request** entity is independent from acknowledgement.

Typical conservative behavior:

- Slow Leak: no shutoff by default
- Low Flow: no shutoff by default
- High Flow: no shutoff by default
- Burst Leak: shutoff request enabled by default

Physical valve control is intentionally external/opt-in so users can decide which existing `valve.*` or `switch.*` should react.

## Expert settings

The integration options expose detector thresholds, durations, reset limits, bypass duration, hydraulic context, learning parameters, and detector-to-shutoff mapping.

Change these values only with measured household data where possible.

## Measurement validity and navigation

`source_max_age_seconds` defaults to 0 (no artificial gap limit), range 0–3600.
This is the **Maximum credited gap between measurement reports** expert setting.
Only fresh valid flow reports confirm completed intervals; ticks contribute zero.
A positive limit includes equality (60 s counts at a 60 s limit); larger intervals
add zero without removing previously accumulated confirmed monitoring evidence.
Normal subsequent reports count immediately. Automatic mode never learns cadence.
Observed invalid/unavailable/unknown flow breaks the chain; recovery's first report
adds zero. Temporary interruptions of the same source preserve confirmed
Slow/Low/High monitoring progress, clear quiet windows and unconfirmed Burst
candidates, and retain active leaks/shutoff requests. An outage is not zero flow;
actual returned values follow the existing detector/reset rules. Changing the
configured source discards unconfirmed monitoring instead of transferring it.
Without a positive limit, legitimate slow reports and silent communication failures
between valid endpoints cannot be distinguished. See the README for this boundary.
Negative and nonfinite samples are invalid, not zero. Low/High quiet and Burst reset
flow limits remain strictly positive; legacy zero values are clamped to 1 L/h.
Other detector thresholds and detection times are unchanged.

All source, expert and recipient forms provide **Back without saving**. Recipient
changes apply live and preserve detection timers. Source changes rebase meter volume,
reset unconfirmed windows and learning, and retain confirmed safety. See README for
total-meter quantization, parallel HA dispatch and interruption semantics.

F02 is closed. The general learning path excludes High MONITORING and bypass;
a separate repeated-confirmation gate can admit only clean, normally completed
High episodes in an independent Long-Term channel under F04 V3.
The `effective_high_threshold` entity identity and translation key are retained;
its displayed value stays static.

## F04 V3 configuration and upgrade

The new default Burst base is **3,500 L/h**; explicitly saved values remain intact.
External binary sensors can be added during setup or under Configure → External
leak sensors. Every source has its own Shutoff contribution (default true).
Recipients have independent `allow_external_reset` (default false) and global ACK
permissions. External reset always requires the current tracker to be Home.
See [F04 V3](F04_V3.md) for all lifecycle, restart, nonce, migration, failed-write,
calibration and separate Rolling/Long-Term threshold rules.

## Low reset, acknowledgement and duration follow-up

MQTT Flow sensors need `force_update: true` to expose repeated equal telegrams.
Short MQTT expiry or explicit source timeout can repeatedly interrupt reset
evidence. Missing reports never mean zero. Configure now provides an authorized
active-event acknowledgement form; numeric event seconds gain DE/EN display
attributes. Full diagnostics, semantics and limits: [follow-up contract](F04_LOW_ACK_DURATION.md).


### F04 Sicherheitsreview: MQTT-Messherkunft und Quittierung

MQTT-Durchflussquellen benötigen jetzt die originale timezone-aware Radio-/
Empfänger-Messzeit im JSON-Feld `timestamp`; `force_update` allein beweist keine
neue Messung. Retained, alte oder ungebundene Nachrichten liefern keine Evidenz.
Fehlende Messherkunft sperrt die Auswertung und erzeugt einen Repair-Hinweis;
bestehende ACTIVE-Alarme bleiben erhalten. Die fremde Discovery wird nicht
überschrieben. Details und Vertrauensgrenzen: [Low/ACK/Dauer](F04_LOW_ACK_DURATION.md).

Die Startup-Grenze wird am tatsächlichen Setupbeginn erfasst und nach dem Restore
an die Messherkunft gebunden; eine strengere gespeicherte Grenze bleibt erhalten.
Ein neues Telegramm wird dadurch nicht allein wegen normaler MQTT-Zustelllatenz
als Vor-Startup-Messung abgelehnt. Die erste gültige Messung liefert weiterhin
0 Sekunden Evidenz. Messquellenwechsel setzen eine neue Grenze; Unterbrechungs-,
Replay-, Retained- und Altersprüfungen bleiben wirksam.

ACK wird erst nach erfolgreicher Persistenz veröffentlicht. Das Configure-ACK ist
administrative Delegation anhand des ausgewählten Recipients und dessen Home-
Tracker. Status und Dauer wählen dasselbe hydraulische oder externe Ereignis.

### Hydraulische Überwachung

Ab 1.2.0-beta.3 besitzt das vorhandene Integrationsgerät einen regulären Sensor
**Hydraulische Überwachung** (`hydraulic_monitoring_status`). Die stabile Unique-ID
setzt sich aus Config-Entry-ID und diesem Schlüssel zusammen.

| Zustand | Bedeutung |
|---|---|
| Aktiv (`active`) | Der Manager hat die Durchflussmessquelle freigegeben und verarbeitet ihre gültigen Messungen. |
| Warte auf Messung (`waiting_for_measurement`) | Nach Start oder Quellenwechsel fehlt die erste gültige Messung, ohne bereits festgestellte ausdrückliche Sperre. |
| Gesperrt (`blocked`) | Eine Messung wurde abgelehnt, die Quelle ist ungültig/nicht verfügbar oder ihr konfigurierter Timeout wurde erreicht. |

„Kein Alarm“ bedeutet nicht automatisch „Überwachung aktiv“. Auch bei einer
Sperre bleibt der neue Sensor verfügbar. Ein zuvor bestätigter ACTIVE-Alarm und
sein Shutoff-Beitrag bleiben entsprechend den bestehenden Resetregeln erhalten.
ACK und Mute ändern die hydraulische Freigabe nicht.

Hilfreiche Attribute: `reason` nennt die tatsächliche letzte Annahme-/Sperrentscheidung
des Managers; `source_entity_id` zeigt die Flowquelle, `source_available` den
vorhandenen Manager-Freigabewert und `mqtt_provenance_status` die MQTT-Prüfung.
`last_valid_measurement` ist der Zeitstempel des letzten gültigen **HA-Reports**
(kein erfundener physischer Timestamp); `observation_age_seconds` ist dessen
monotones Beobachtungsalter. Nicht vorhandene optionale Werte bleiben leer/null.
Während eines Quellenwechsels wartet die Anzeige bis zur neuen Freigabe, auch wenn
der vorhandene Manager-Freigabewert vorübergehend noch die alte Quelle beschreibt.
Die Anzeige verändert weder diesen Wert noch Evidenz, Erkennung oder Persistenz.
