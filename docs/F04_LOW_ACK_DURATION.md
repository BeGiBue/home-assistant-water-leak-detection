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

Preserve original measurement provenance as described below, then set
**`force_update: true` on the MQTT Flow sensor** in its sensor/discovery
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

For MQTT only accepted original measurements update age. Age is measured from the last valid HA state observation on the process monotonic
axis. Cached and retained pre-startup MQTT measurements are rejected. The first
accepted post-startup measurement has zero interval credit.
The timestamp cannot be inferred from HA receipt; it must exist in the original payload.
Loaded MQTT expiry is a best-effort read of the MQTT entity; null means unknown
or not configured, not proof that no expiry exists. Runtime metadata is volatile.

## Acknowledgement in Home Assistant

Open **Configure → Acknowledge active notifications**, select the exact Event-ID
and a configured recipient. The HA administrator Configure flow uses that
recipient's current token internally, without exposing it. Current global ACK
permission and an actual `home` tracker state are checked under the same writer
and authorization contract. This is administrative delegation: it checks the
selected recipient's tracker, not the HA administrator's location or mobile
identity. Normal non-admin HA users have no Configure access. Stale events, removed/changed recipients, revoked rights
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


## Original MQTT measurement contract (security review correction)

**Compatibility requirement:** MQTT Flow sources now need a concrete state topic
and a JSON `timestamp` containing the timezone-aware original radio measurement
or original receiver timestamp. This field must be generated only when a new
physical telegram is received, and preserved by every relay. For example:

```json
{"flow_m3h": 0, "total_m3": 123.456,
 "timestamp": "2026-10-13T08:30:00Z", "telegram_id": 12345}
```

`telegram_id` is optional. If used, it must be an original nonnegative integer
below 2^63, increasing for distinct original frames sharing the same timestamp;
it must not be regenerated by MQTT re-delivery. Do not manufacture new timestamps
or IDs in an automation that merely republishes a cached measurement. No numerical
flow/volume equality heuristic can distinguish these cases.

The integration reads the original MQTT state-topic message through the actual
HA MQTT entity's bounded message queue (tested on HA 2026.9.4), validates its
binding to the rendered sensor value and preserves a durable source-generation-
bound timestamp/identity watermark **before** using it as detector evidence.
Missing/incompatible adapter information blocks the report; there is no receipt-
time fallback. The foreign Discovery configuration is not changed automatically.

All retained messages are rejected as new evidence. Duplicate, out-of-order,
pre-startup, malformed and stale messages are rejected. The delivery age limit
is 300 seconds; allowed original timestamp future skew is at most 2 seconds.
These bounds describe message provenance, not a radio reporting interval: a fresh
telegram every 600 seconds remains admissible. The clock used for these bounds
is the process's monotonic UTC anchor; an HA UTC rollback cannot speed it up.
After restart an original timestamp ahead of the new anchor is conservatively
blocked until the clock catches up. Watermarks are never lowered by rollback.

A valid interval is capped by both reception evidence and elapsed original
measurement time. Redelivery cannot create Quiet, Low/High or Burst credit.
A rejected report interrupts the evidence chain, preserves confirmed ACTIVE
alarms/Shutoff and clears incomplete Quiet evidence. After recovery the first
valid report again contributes zero seconds. The existing 2-microsecond engine
rounding tolerance is unchanged.

An ERROR repair and `mqtt_provenance_status` / `mqtt_measurement_provenance`
diagnosis explain why a stream is blocked. Existing MQTT sources lacking the
required origin field must be corrected upstream before hydraulic detection can
resume. The integration cannot prove sensor authenticity or distinguish a forged
new timestamp from a genuine measurement: the original receiver/broker and ACLs
are part of the trust boundary. The actual installation's payloads remain unknown.

## Durable ACK, recovery and displayed event

Native and mobile global ACK stage a private revision. A success event and public
ACK appear only after the HA atomic write succeeds; a failed write leaves the old
ACK/dispatch state intact, permits retry and never clears physical alarms/Shutoff.
Nonempty string tokens are required; null, booleans, containers, numbers and
whitespace-only tokens are rejected, never coerced into guessed credentials.

All snapshot writers share the same recovery barrier. An unknown/corrupted Store
wrapper is preserved byte-for-byte, including recoverable safety data. Current
external ON observations remain conservatively visible in memory. The unknown
persisted safety state also holds aggregate alarm/Shutoff requests until a valid
backup can be restored; this does not operate a valve. OFF and reset
cannot publish release without a valid durable Store. Restore a verified backup;
no successful migration is claimed while `storage_recovery_required` is true.

New/replaced external generations immediately evaluate their current HA state;
already ON produces its own event. WAITING and old ACTIVE tombstones remain bound
to their original generation. Reset-action notification delivery runs outside the
safety writer and rechecks current authority before handoff and again at reset.

Status event attributes and duration use one selection: hydraulic priority first,
otherwise the earliest active external source with deterministic identity ties.
External event elapsed time uses process-monotonic time and is saved/restored;
HA offline time is excluded. UTC rollback never makes it negative. All concurrent
alarms remain visible separately and keep their own ACK/Shutoff contribution.

## Safety recovery and MQTT interruption boundaries

A supported Store version does not make a damaged body valid. Version 1 and 2
bodies must be dictionaries; lists, strings, numbers, booleans and null in an
existing file trigger recovery. The original file is never normalized into an
empty installation. A missing file remains a normal new installation. All writers
respect the recovery barrier; aggregate alarm and shutoff requests remain held.

An explicit source timeout, invalid/unknown/unavailable flow or direct return after
an excluded gap closes the same evidence chain. Its generation-bound
`admission_since` exclusion boundary is saved before return evidence may act.
It never moves backwards during UTC rollback. A failed write leaves the source
blocked; MQTT evidence must commit its boundary and original marker before credit.
Ticks only exclude unknown time, never confirm water consumption or quiet.
Buffered measurements originating before this boundary are rejected even when
previously unseen, strictly ordered, non-retained and within the 300-second
delivery-age allowance. First accepted return contributes zero interval seconds.
The 2-µs engine tolerance and configured timeout semantics remain unchanged.

External alarm and shutoff aggregation uses every ACTIVE source, including
tombstones and quarantined records. Conflicting Event-IDs or repeated
Source/Generation keys cannot discard a contribution. `identity_conflict=true`
identifies affected records. Their original IDs and safety contributions remain,
but reset nonces are removed and ambiguous IDs are excluded from notification,
ACK and reset capability lookup. Old ACKs are not inherited. They are not renamed
into apparently trustworthy events. A conflicting OFF cannot identify which record
ended, so quarantined alarms remain held for verified recovery. Unaffected events
retain their normal lifecycle and authorization. Learning stays blocked while any
external source is ACTIVE, including quarantine. Conflicts remain sticky at restart.

Home Assistant displays an ERROR repair when runtime safety recovery is required.
To recover: preserve the original file and diagnostics, stop HA fully, and restore
a verified complete HA backup (or the exact entry's verified runtime Store with
its matching ConfigEntry/source identities). Do not edit learning provenance,
invent event identities, delete the Store to clear alarms, or restore while HA is
running. Restart HA and verify `storage_recovery_required=false`, no conflicting
sources, all expected ACTIVE alarms/ACKs and the aggregate shutoff request. A valid
backup retains its ACTIVE state; only genuine physical reset or a currently
authorized unambiguous external reset can then end it. The repair clears when the
valid state is restored. The integration never operates a valve.

The MQTT component/Store regressions have also been exercised against declared
minimum HA 2026.9.0. This does not prove the actual Hydrus Discovery configuration;
that installation's original payloads, timezone, relay behavior, force_update and
expire_after still require a field export and verification.
