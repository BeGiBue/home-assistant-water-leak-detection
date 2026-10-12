# Water Leak Guard

[![Open your Home Assistant instance and open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=BeGiBue&repository=homeassistant-water-leak-detection&category=integration)

A backend-focused Home Assistant custom integration for detecting abnormal water consumption and possible water leaks from an existing water-meter flow sensor.

**Current release:** 1.1.0
**Minimum Home Assistant:** 2026.9.0
**Integration domain:** `water_leak_detection`

> [!IMPORTANT]
> This integration can detect suspicious water usage and expose a shutoff request. It does not guarantee prevention of water damage. Automatic valve closure is opt-in and should be tested carefully.

## Highlights

- Separate **Slow Leak**, **Low Flow**, **High Flow**, and **Burst Leak** detectors.
- Independent enable/disable switches for Slow Leak and Low Flow.
- Temporary High Flow bypass for intentional high consumption such as pool filling.
- Burst Leak remains active even while High Flow is bypassed.
- Optional cumulative consumption sensor for event-volume tracking.
- Multi-device Home Assistant Companion notifications.
- Device-specific mute and Home-zone-authorized global acknowledgement.
- Trusted stationary Home devices such as a shared iPad.
- Return-home re-notification while an event is still active and not globally acknowledged.
- Independent `Water shutoff request` entity for an external motorized valve automation.
- Continuous rolling learning of normal peak consumption.
- Learning confidence states: `insufficient`, `learning`, and `reliable`.
- Hydraulic plausibility context using nominal pipe diameter and static pressure.
- Static High Flow and adaptive Burst Leak thresholds.
- Evidence-based Rapid Rise acceleration above the effective Burst boundary.
- Multiple independent external leak sensors, with persistent per-source lifecycle.
- Separate Home-authorized External Reset with replay-safe event nonces.
- Independent Rolling and confirmed Long-Term learning, with legacy quarantine.
- Persistent event state, bypass expiry, acknowledgements, and learned history across Home Assistant restarts.

## Installation

### HACS — recommended

Use the button above, or add the repository manually in HACS:

- Repository: `https://github.com/BeGiBue/homeassistant-water-leak-detection`
- Category: **Integration**

Then:

1. Download **Water Leak Guard** in HACS.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration**.
4. Search for **Water Leak Guard**.
5. Complete the config flow.

Detailed installation and update instructions: [docs/INSTALLATION.md](docs/INSTALLATION.md)

### Manual installation

Copy:

`custom_components/water_leak_detection`

to:

`<config>/custom_components/water_leak_detection`

Restart Home Assistant and add the integration through **Settings → Devices & services**.

## Measurement sources

The integration requires a compatible flow-rate sensor and can optionally use a cumulative water-consumption sensor.

Reference installation:

- Flow: `sensor.wasserzahler_flow` in `m³/h`
- Total: `sensor.wasserzahler_total`
- Reference flow resolution: 0.001 m³/h = 1 L/h
- Reference installation: DN25 / 1", static pressure 3.5 bar

Flow values are normalized internally to **L/h** and total consumption to **L**.

Supported flow units include L/h, L/min, L/s, m³/h, m³/min, and m³/s.

## Detector defaults

| Detector | Purpose | Default |
|---|---|---|
| Slow Leak | Very small continuous loss | ≥ 3 L/h for 60 min |
| Low Flow | Moderate flow lasting too long | 150–<600 L/h for 60 min, or stable for 30 min |
| High Flow | Sustained unusually high use | Static; default 600 L/h |
| Burst Leak | Major leak / pipe failure | Base 3,500 L/h; 30 s confirmed, accelerated to 10 s by Rapid Rise above the effective boundary |

Low Flow has two activation paths in the band **150 L/h ≤ flow < the static High threshold** (default 600 L/h):

- **Long-lasting Low Flow:** the normal 60-minute path remains the safety net, including variable consumption.
- **Particularly steady Low Flow:** enabled by default, activation after 30 minutes of continuous confirmed Low evidence, with a stable trailing 15-minute window.

Steadiness is an additional indication of a tap left open, **not a prerequisite for Low Flow detection**. The reference is the time-weighted median M of the window; tolerance is `max(20 L/h, 0.10 × M)`. At least 90% of confirmed window time must lie within `M ± tolerance`. Both the median and the share use interval duration, not sample count. The oldest interval is trimmed at the window boundary. Credited intervals belong to the current valid report, following F05; the first report in a new chain contributes zero seconds. Different reporting frequencies therefore do not add extra weight; sampling still limits which physical variations can be observed.

Any real report below the Low threshold immediately discards the stability series, including 20–149 L/h and even a short quiet pause. Thus 15 minutes steady, 30 seconds quiet, then 15 minutes steady cannot trigger early activation. The normal Low progress continues under its existing rules until a full quiet reset. A continuous confirmed phase **below 20 L/h for 3 minutes** resets Low monitoring and active Low events (179 seconds does not; 180 seconds does). Existing explicitly saved reset durations, including 7 minutes, remain unchanged.

High-band reports discard Low stability and retain the existing Low/High handover. Unknown, unavailable and invalid values interrupt stability; the returning first report contributes zero evidence. Round7 retains normal confirmed Low progress across same-source outages. Internal ticks supply no evidence. Stability cannot end an already ACTIVE Low event; only its physical quiet/reset condition does. Stability history is transient and is rebuilt after restart; active event persistence is unchanged.

Slow Leak and Low Flow can be switched off independently. High Flow can be temporarily bypassed. Burst Leak cannot be bypassed by the High Flow bypass.

All expert thresholds and reset times can be adjusted through the integration options.

## Main entities

The integration creates a Home Assistant device with backend entities including:

- **Status**
- **Current flow**
- **Leak alarm**
- **Water shutoff request**
- **Active event duration**
- **Active event volume**
- **Slow Leak detection**
- **Low Flow detection**
- **High Flow bypass**
- **High Flow bypass duration**
- **High Flow bypass remaining**
- **Learned maximum flow**
- **Learning confidence**
- **Learning coverage**
- **Hydraulic reference flow**
- **High Flow threshold**
- **Effective Burst Leak threshold**

## Language and later configuration

The integration follows the configured Home Assistant backend language.

- German Home Assistant: German integration title, device/entity names, configuration dialogs, states, service actions, and Companion notification text.
- Other supported languages fall back to English unless a matching translation file is provided.

During initial setup, notification recipients can already be added after selecting the measurement sources.

After installation, **Configure** can be opened again at any time. It contains:

- **Measurement sources** — change the flow-rate and optional total-consumption sensors.
- **Notification recipients** — add, edit, or remove Companion App devices.
- **Expert settings** — change detector thresholds, learning, hydraulic context, bypass, and shutoff mapping.

Home Assistant's separate **Reconfigure** action for the measurement sources is also supported.

Changes are applied by reloading the integration automatically. Saving a subsection returns to the appropriate Configure menu instead of closing the entire dialog. The notification-recipient submenu also provides an explicit **Back to configuration** entry.

## Companion notifications and acknowledgement

Notification recipients are configured per Companion App device. Each device can have its own:

- `notify.mobile_app_*` service,
- matching `device_tracker.*`,
- critical Burst-alert setting,
- permission for global acknowledgement while Home,
- trusted stationary Home-device flag.

An away device can mute the current event for itself. Global acknowledgement is accepted only when the configured tracker for the responding device is currently `home`. The check is enforced in backend code.

A shared iPad that normally stays Home can be configured as a trusted stationary Home device and used by another household member to globally acknowledge an event.

Returning Home is treated as a fresh safety context: if an event is still active and not globally acknowledged, that device is notified again.

## High Flow bypass

The integration intentionally does not create a custom `timer.*` platform. It exposes the bypass with HA-native controllable entities and actions:

- switch: start/cancel bypass,
- number: default duration,
- sensor: remaining duration,
- action: `water_leak_detection.start_high_flow_bypass`,
- action: `water_leak_detection.cancel_high_flow_bypass`.

Example:

```yaml
sequence:
  - action: water_leak_detection.start_high_flow_bypass
    data:
      duration_minutes: 240
```

## Adaptive learning

Rolling Learning retains normal clean sub-High episodes, the default 30-day
window, P95 and Confidence. High episodes have a separate persistent Long-Term
channel: three independent clean episodes within a 15% spread confirm a maximum;
every increase requires three new peaks above the old maximum, strictly below the
configured Burst base. They never enter the Rolling pool. Long-Term history does
not age out and cannot automatically ratchet through the adaptive threshold.

`water_leak_detection.reset_learning` clears both channels and rollback context.
Bypass, any ACTIVE alarm (including external sources), Burst/Rapid-Rise candidates,
measurement gaps and interrupted High episodes are excluded. Every startup needs
the configured physical High quiet reset before new High learning.

See [F04 V3 configuration and safety contract](docs/F04_V3.md).

## Hydraulic context

Nominal pipe diameter and static pressure are used as a **plausibility envelope**, not as an exact physical maximum. Actual flow depends on the meter, pressure reducer, dynamic pressure, pipe length, fittings, and upstream supply.

The hydraulic model caps the rolling/manual candidate. The independently confirmed
Long-Term candidate is not capped by that heuristic ceiling.

## Shutoff request

`binary_sensor.*_water_shutoff_request` is deliberately independent from alarm acknowledgement.

Example external automation:

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.water_leak_detection_water_shutoff_request
    to: "on"
actions:
  - action: valve.close_valve
    target:
      entity_id: valve.main_water
```

Replace the entity IDs with the IDs from your Home Assistant instance.

## Events

The integration emits:

- `water_leak_detection_event_started`
- `water_leak_detection_event_ended`
- `water_leak_detection_shutoff_requested`
- `water_leak_detection_shutoff_cleared`
- `water_leak_detection_acknowledged`
- `water_leak_detection_ack_rejected`

Event payloads include the event ID and relevant detector context. Burst events can report reasons such as `absolute_flow` or `rapid_rise`.

## Documentation

- [Installation and updates](docs/INSTALLATION.md)
- [Configuration reference](docs/CONFIGURATION.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Changelog](CHANGELOG.md)
- [v1.0.3 release notes](RELEASE_NOTES_1.0.3.md)
- [Release procedure](docs/RELEASING.md)
- [Project Wiki](https://github.com/BeGiBue/homeassistant-water-leak-detection/wiki)
- [Technical specification and roadmap](SPEC.md)

## Release status

Version 1.0.3 is the current stable release. It includes the complete original v0.1 → v0.3 backend roadmap plus the independently reviewed technical stabilization through correction round 7:

- **v0.1.0** — detection core and backend entities
- **v0.2.0** — notifications, device acknowledgement, and geofencing
- **v0.3.0** — adaptive learning and hydraulic plausibility

The previously published **0.3.0** GitHub release was tagged before the Home Assistant integration-type correction and still declared itself as a `helper`. **1.0.3 continues the corrected stable line introduced with 1.0.0, explicitly declares `integration_type: "service"`, and contains the reviewed safety and reliability corrections released after 1.0.2.**

The release is validated against Home Assistant 2026.9.4 / Python 3.14.2 with compile checks, Ruff, JSON validation, and automated tests.


## License

Water Leak Guard is licensed under the **GNU Affero General Public License v3.0 only (AGPL-3.0-only)**.

See [LICENSE](LICENSE) for the complete license text.

## Operational contract after 1.1.0

Version **1.1.0** contains the seven reviewed technical correction rounds together with
F02 static High Flow, F08 Low Flow stability, and the repeatedly confirmed seasonal
learning of clean High Flow episodes. High remains static and learning can influence only
the existing adaptive Burst context in that release. The unreleased F04 V3 feature
on this branch replaces the shared High-learning channel and Rapid-Rise rule;
see the current [V3 contract](docs/F04_V3.md). Release metadata remains 1.1.0.

Only actual flow reports supply detection/quiet evidence. Re-reading a cached HA
state on an internal tick never matures a timer. Object identity and report
notifications, including `last_reported` changes in either UTC direction, distinguish
new reports from cached readings. Superseded queued state events are rejected by
current-state identity, not UTC ordering. Runtime intervals and active durations
use a process-local monotonic axis. Persisted active duration excludes offline time.

`source_max_age_seconds` defaults to **0 (no artificial report-gap limit)**.
The integration evaluates fresh measurement reports; automatic operation does not
statistically guess the sensor's reporting cadence. Two consecutive fresh valid
flow reports confirm their completed interval. No interval is credited while
waiting for the second report: internal ticks supply **zero seconds** of evidence.
The first report starts the measurement chain with zero credit.

The expert option **Maximum credited gap between measurement reports** accepts a
positive limit in seconds. An interval equal to the limit counts; a larger interval
adds zero seconds without deleting previously accumulated confirmed monitoring
progress. Subsequent normal intervals count again, without any qualification phase.
The existing detector thresholds and flow-based reset rules remain unchanged.
The engine represents accumulated confirmed monitoring time by shifting the timer
origin over excluded intervals; report history never reclassifies earlier credit.

Observed `unknown`, `unavailable`, negative, nonfinite or otherwise invalid flow
breaks the measurement chain and supplies neither leak nor quiet evidence.
A temporary interruption preserves confirmed Slow/Low/High monitoring time while
clearing quiet windows and unconfirmed Burst candidates. Confirmed leaks and
shutoff requests stay active. An interruption is not a measurement of zero flow.
Actual values measured after recovery still run the normal detector/reset rules.
A switch to another configured source discards unconfirmed monitoring instead;
evidence from the old physical source never transfers to the replacement.
The first valid report after recovery starts a new
chain with zero credit; time across the interruption is excluded. A frozen state
without new reports cannot activate or reset a leak.

Without an explicit maximum gap, a legitimate slow reporting cadence and a silent
communication failure between valid endpoints are indistinguishable. A later valid
report can therefore confirm a long interval, but cannot prove continuous physical
flow between reports. Users of normally frequent sensors can set an expert limit
when long silence could indicate a frozen source. There is no automatic derivation
of that limit. Round 1's persisted 30-second default remains unlimited unless
explicitly re-saved; other positive legacy limits are preserved.

Optional total-meter progress is compared with accumulated confirmed flow volume,
without a fixed litre-resolution offset or a 1.5 volume multiplier. Unused flow
credit is retained across accepted quantized increments. A rejected cached total
cannot become accepted merely because flow catches up: another actual total report
or value change is required. A fresh identical report may confirm it only after
sufficient independent flow evidence exists. Frozen or absent totals never veto
flow integration. Counter regression/reset and return after unavailable rebase the
reference without importing unknown volume or clearing active events. Very long
single flow-integration intervals retain their existing volume cap; total
plausibility uses only the confirmed interval, not an unknown communication gap.
This is a consistency check, not a guarantee of meter accuracy or a new leak threshold.

Safety transitions request a write within 1 s; ordinary sample/learning updates
within 10 s of the first pending update, without postponement by later samples.
These bounds exclude event-loop stalls and storage failures. Final-write/unload
flushes pending state. Corrupt active records retain safety when remaining confirmed
event identity/detection evidence is strong; unconfirmed monitoring is discarded.
Future records redundantly persist `confirmed_active`. Legacy reconstruction uses
class-independent confirmation fields; Burst's optional `reason` is never required.
Restored event IDs must contain 1–128 ASCII letters, digits, underscores or hyphens.
Invalid IDs are replaced without transferring old acknowledgements.

Notifications use isolated tasks per event/recipient/notify-service route. States distinguish not yet
dispatched, in flight, locally failed, accepted by HA, and interrupted/ambiguous.
Missing services and local exceptions leave dispatch open for later periodic retry.
A slow/hanging service does not block other recipients. No 5-second cancellation
and automatic duplicate retry applies to a running handoff. A second handoff for
that event/route cannot start while the first is running. Acknowledgement is
checked immediately before the HA call and never clears detection or shutoff.

**The integration guarantees handoff to the configured Home Assistant Notify service,
not physical delivery to the phone.** A normal service return records HA acceptance;
mobile_app may internally handle remote push failures without reporting them here.
Already handed-off calls cannot be recalled. Unload cancels local waiting tasks;
an interrupted in-flight call is persisted as ambiguous and is not automatically
resent on the same route after restore, because it may already have pushed.
A changed notify service is a new route and remains eligible unless acknowledged.
Accepted and interrupted states are persisted per route. Round 2 interrupted
records did not contain service provenance: migration retains that unknown route
explicitly instead of attaching it to a potentially new configured service. An
eligible current route may dispatch; if it was also the unrecorded old route, this
upgrade ambiguity can produce a duplicate. Historical service identity cannot be
reconstructed from missing metadata. Event end cancels and
awaits its local dispatch workers without affecting another event. This can require manual
operator follow-up. A crash before persisting acceptance can still cause a duplicate;
exactly-once physical delivery is impossible without downstream confirmation.

Bypass duration uses a monotonic deadline in the running process. On save its UTC
expiry is projected from remaining monotonic time; restore uses that absolute expiry.
Clock changes during the same process neither shorten nor extend the bypass. A
clock correction during an unclean outage remains inherently ambiguous.

Controls are applied even without a new report: disabling Slow/Low and activating
High-Flow-Bypass immediately apply their existing reset rules. Cancelling bypass
does not reuse stale measurements to create a new event. Changing recipients does
not reload detection. Learning episode intervals use process timing, while admitted
learning-history timestamps and rolling windows use actual UTC. Changing sources retains active
safety states but discards old meter baselines, unconfirmed timers and learning.
Every form submenu offers **Back without saving**; enable it and submit to return
without validating or saving unfinished fields. Own derived Water Leak Guard sensors
are rejected as sources. Physical valve control remains in user HA automations.

These technical rounds do not establish absence of false alarms during normal use.

### F02: static High Flow boundary

High Flow starts MONITORING at exactly the configured expert threshold (default
600 L/h). Slow Leak covers 3 to <150 L/h; Low Flow covers 150 L/h to strictly
below High. Low ends exactly where High starts. Learning, manual maximum usage,
hydraulic context and legacy High multipliers cannot raise this boundary.
Monitoring is not an immediate alarm: duration, volume, quiet/reset rules and
High bypass are unchanged. Burst remains active during bypass and can still use
adaptive context; Rapid Rise now accelerates only above its effective boundary.

The general learning path still treats High MONITORING as suspicious. The separate
High-normal confirmation gate admits only repeatedly confirmed, cleanly ended
High episodes; bypass and alarm episodes remain excluded. This extends learning
outside F02 without changing static High or Low stability. F04 V3 now separates
this gate into Long-Term learning; the current rules are documented above.
