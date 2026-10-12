# F04 follow-up: Low reset, acknowledgement and event age

This follow-up on PR #14 preserves F02/F08/F15/F04 evidence and detector rules.
It makes the received evidence and acknowledgement state visible. Missing radio
telegrams, cached states and unavailable sources never mean zero consumption.

## Reproduced causes of a Low alarm remaining active

The Home Assistant 2026.9.4 MQTT Sensor checks whether its rendered value changed.
With the default `force_update: false`, a new wmbusmeters JSON telegram can contain
`flow_m3h: 0` and still produce **no new HA flow report** when the rendered value
is unchanged. Listening to `state_reported` inside Water Leak Guard cannot recover
reports MQTT never wrote. A first transition to zero starts the quiet phase, but
repeated hidden zero telegrams cannot confirm its duration. More total-meter
reports also do not supply Flow evidence.

Set **`force_update: true` on the MQTT Flow sensor** in its sensor/discovery
configuration. Preserve its state topic, identity, units and value template.
For example, the relevant discovery fields are:

```json
{
  "state_topic": "your_existing_wmbusmeters_topic",
  "value_template": "{{ value_json.flow_m3h }}",
  "unit_of_measurement": "m³/h",
  "force_update": true
}
```

This is an excerpt for an existing discovery configuration, not a complete new
sensor definition. The integration does not publish or silently edit another
integration's discovery. A HA Repair warning points out a loaded MQTT Flow sensor
without force_update; it disappears once the valid source uses force_update.
No automatic synthetic reports or null-flow fallback are introduced.

Second reproduced cause: an MQTT `expire_after` shorter than actual radio
intervals repeatedly makes the sensor unavailable. For example, 45-second expiry
with 60-second telegrams interrupts quiet evidence every time. The integration
must discard that quiet progress; first valid recovery supplies **zero** retroactive
seconds. Choose MQTT expiry using measured intervals, loss tolerance and acceptable
fault-detection delay. Too short prevents reset; too long delays outage recognition.

The integration default **`source_max_age_seconds = 0`** disables automatic age
expiry; it accepts completed fresh valid report intervals without learning a
cadence. It does not let cached values or ticks advance detection/reset timers.
An explicit positive limit excludes intervals exceeding that limit. A saved
30-second value without `source_gap_policy_explicit` is the legacy automatic
setting and is interpreted as 0; explicitly saved 30 seconds stays 30.
At 60-second reports an explicit 30-second limit repeatedly excludes evidence.
No default or explicit user limit is overwritten by this follow-up.

The repo cannot reveal a particular installation's saved ConfigEntry or discovery
payload. Read the new runtime diagnostics before changing configuration. The
reported real 07:22–07:27 unavailable period is consistent with broken chains;
it does not prove either exact timeout value. An ACTIVE display at 08:18:22 does
not identify the event's monitoring or activation time without its Event-ID.

## Meaning of the observations

| Observation | Consequence |
|---|---|
| physical water is off, no report | no evidence available to the integration |
| fresh valid HA report of zero | starts/continues confirmed quiet; first after gap has 0 s credit |
| MQTT zero suppressed before HA | no new Flow report; no new interval credit |
| repeated identical HA Flow report | real report evidence, even without last_changed moving |
| cached state on internal tick | no evidence; no Low reset progress |
| lost radio telegram | not a zero report; no tick-based clearance |
| explicit excessive gap / unavailable / invalid | interrupts quiet; ACTIVE and Shutoff remain |
| valid source recovery | new chain, first report 0 s credit |
| HA restart | ACTIVE retained, quiet rebuilt; offline duration not added |

Default Low reset remains three confirmed minutes strictly below 20 L/h.
179 seconds does not reset; 180 does. Explicit seven-minute values remain seven.
The total meter does not replace instantaneous Flow evidence. Automatic mode has
no artificial interval cutoff: a later fresh valid report can complete an interval
under the existing F05 contract. It cannot prove every unobserved change inside
that interval; configure an explicit limit/appropriate availability when necessary.

## Runtime diagnostics

On the Status sensor, inspect:

- `hydraulic_detectors`: all four phases, per-detector Event-ID, monitoring start,
  ACTIVE time, numeric event age and runtime quiet marker.
- `measurement_diagnostics`: Flow/Total source, raw current HA source state,
  availability, last valid Flow, HA last_reported label, monotonic observation age,
  stored/default/effective source age limit, timeout flag, credit/gap, MQTT
  force_update and loaded expire_after, Low quiet limit and confirmed/required
  Low reset seconds. Confirmed reset progress uses the engine's last sampled
  evidence time, **not** wall time since the last zero on a cached tick.
- `notification_events`: acknowledgement, muted/accepted recipient IDs and
  dispatch status separately for each Event-ID. No recipient token is exposed.

Age is measured from the last valid HA state observation on the process monotonic
axis. On startup the first observation may be a retained existing HA state; its
HA last_reported timestamp is shown separately, and first evidence credit is zero.
The timestamp of the original radio packet cannot be inferred from these fields.
Loaded MQTT expiry is a best-effort read of the MQTT entity; null means unknown
or not configured, not proof that no expiry exists. Runtime metadata is volatile.

## Acknowledgement in Home Assistant

Open **Configure → Acknowledge active notifications**, select the exact Event-ID
and a configured recipient. The HA administrator Configure flow uses that
recipient's current token internally, without exposing it. Current global ACK
permission and an actual `home` tracker state are checked under the same writer
and mobile validator. Stale events, removed/changed recipients, revoked rights
and away/unknown/unavailable tracker states are rejected. This does not modify
configuration. ✓ identifies an event already globally acknowledged.

The supported action **`water_leak_detection.acknowledge_event`** is also available
in Developer Tools / automations. It requires `event_id`, `recipient_id`, the
current **`recipient_token`**, and `config_entry_id` when several entries exist.
Do not expose the token in public dashboards. The service has no implicit
recipient impersonation or Home override. Mute remains personal; global ACK
suppresses event notifications only. Neither ends ACTIVE, resets a detector,
clears Shutoff or opens a valve. External Reset remains a separate action.

Mobile actions now reload current recipients before validation, so an action
cannot use an old cached token or revoked ACK permission. Malformed non-boolean
global permission values are rejected; valid existing bool values and legacy
missing-permission default remain supported.

Ordinary ticks, reports, duplicate event-start messages and restarts do not resend
an accepted route for the same Event-ID. Notify failures may retry; an interrupted
ambiguous handoff is not blindly resent. Returning Home while an unacknowledged
event remains ACTIVE is an existing intentional fresh safety notification; it
may reuse the same Event-ID. A changed notify route and an explicitly requested
external-reset action are separate intentional deliveries. HA acceptance is not
proof of a smartphone delivery, so Event-ID and dispatch metadata must be checked.

## Human event age

The numeric duration sensor remains in seconds for automations. Attributes add
`duration_human`, `duration_human_de` and `duration_human_en`, plus Event-ID,
`started_at` and `active_since`.

| Seconds | Deutsch | English |
|---:|---|---|
| 45 | 45 Sekunden | 45 seconds |
| 125 | 2 Minuten | 2 minutes |
| 6043 | 1 Stunde 40 Minuten | 1 hour 40 minutes |
| 90000 | 1 Tag 1 Stunde | 1 day 1 hour |

Lower units are omitted/floored for readability. Existing numeric event age
starts at MONITORING; it is **not** only time since ACTIVE. Thus an alarm first
activated after 30 minutes already has about 1800 seconds of event age.
Source outages keep ACTIVE and event age in the running HA process; persisted
age excludes HA offline time. UTC labels and monotonic age are deliberately
separate to preserve F15 on clock changes.

## Validation limits

Regression tests use real HA MQTT Sensor decoding/change suppression, the state
write queue, actual HA states/registries, the production manager/engine and real
Store files. Only broker/radio transport, platform attachment and clock delivery
are simulated; no detector/reset durations are shortened. A real broker and
physical Hydrus/nanoCUL reception were not available. The installation-specific
ConfigEntry, discovery, raw telegram log and prior Event-IDs are still needed
to identify the exact field cause in that installation. Do not infer them from
these tested scenarios. PR #14 requires another independent review; no merge,
release, product-version change or wiki publication.
