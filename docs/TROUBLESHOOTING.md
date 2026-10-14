# Troubleshooting

## Integration is not shown after HACS installation

1. Confirm HACS downloaded the repository as an **Integration**.
2. Restart Home Assistant.
3. Verify that this directory exists:
   `<config>/custom_components/water_leak_detection`
4. Check Home Assistant logs for `water_leak_detection`.

## Flow sensor is rejected

The flow source must expose a supported unit.

Common supported flow units:

- L/h
- L/min
- L/s
- m³/h
- m³/min
- m³/s

The integration validates and normalizes the unit. An entity without a supported flow unit is rejected rather than guessed.

## Total sensor is not available

The cumulative consumption sensor is optional.

Without it, the integration can still detect flow patterns. Event volume may rely on integrated flow instead of meter-total deltas.

## Notification device cannot be added

The Companion App must already have registered a `notify.mobile_app_*` service in Home Assistant.

Also verify that a matching `device_tracker.*` exists for that device.

## Global acknowledgement is missing from a notification

The global acknowledgement action is only offered when the configured device tracker currently reports `home` and that recipient is allowed to globally acknowledge.

The backend validates the Home state again when the action is received.

## Global acknowledgement is rejected

Check:

- the recipient still exists in the integration options,
- its tracker entity is correct,
- the tracker state is exactly `home`,
- global acknowledgement is enabled for that recipient.

An away device can still mute the event for itself.

## Shared Home tablet

For a tablet that normally stays Home, enable the **trusted stationary Home device** option and global acknowledgement permission.

The integration authorizes the responding configured device, not the identity of the person holding it.

## High Flow bypass did not suppress an alarm

The High Flow bypass suppresses only High Flow.

It intentionally does not suppress:

- Slow Leak
- Low Flow
- Burst Leak

Burst Leak protection always remains active.

## Learned maximum looks wrong

Check the following sensors:

- Learned maximum flow
- Learning confidence
- Learning coverage
- Effective High Flow threshold
- Effective Burst Leak threshold

Suspicious High/Burst candidates and High Flow bypass periods are excluded from learning.

Use `water_leak_detection.reset_learning` if you intentionally want to restart the learning history.

## Source sensor becomes unavailable

Unavailable/unknown source values are not interpreted as zero flow.

The integration exposes source unavailability and suspends incomplete learning episodes instead of admitting them as normal data.

## Debug logging

Add temporary logger configuration in Home Assistant:

```yaml
logger:
  default: info
  logs:
    custom_components.water_leak_detection: debug
```

Restart or reload logging as appropriate, reproduce the problem, and remove debug logging afterward.

## Reporting an issue

Open:

`https://github.com/BeGiBue/homeassistant-water-leak-detection/issues`

Include:

- Home Assistant version
- integration version
- source sensor entity IDs and units
- relevant integration settings
- relevant log excerpts
- reproduction steps

Do not post private access tokens or other credentials.

## Hydraulic monitoring: waiting or blocked

First distinguish the alarm sensor from **Hydraulic monitoring**. No alarm does
not establish that measurement admission is working. Conversely `blocked` does
not end a previously ACTIVE alarm or its shutoff contribution. The monitoring
sensor itself stays available while blocked when the integration is loaded.

1. Confirm the **installed** version after a HACS download and HA restart;
   release publication alone does not install it. Open the integration device and
   select the new sensor; entity IDs may have been renamed.
2. For `waiting_for_measurement`, check the selected Flow entity and await a
   genuinely new valid report. Startup/rebind may wait without any rejection.
   Explicit unknown/unavailable or rejected originals instead produce `blocked`.
3. For `blocked`, record `reason`, `source_entity_id`, `source_available`,
   `mqtt_provenance_status`, `last_valid_measurement` and `observation_age_seconds`.
   `last_valid_measurement` is a **HA-report timestamp**, not the radio's original
   timestamp. Null means no such accepted observation is available. Observation
   age uses monotonic time; an unchanged old state is not a new measurement.
4. Inspect the Flow entity's actual availability, supported unit and new reports.
   Review the configured/effective `source_max_age_seconds` and MQTT `expire_after`
   alongside actual report intervals. The integration's default gap limit is 0;
   it cannot infer silent radio failure from silence alone. Do not choose timeout
   values solely from a pair of telegrams.
5. For MQTT inspect the **new original payload** on the Flow state topic: an aware
   `timestamp`, supported flow template and `force_update: true` for repeated
   values. Total JSON attributes alone do not provide Flow provenance. A repeated
   old payload never becomes evidence because force_update is enabled.

| Diagnostic value | What to examine; not a conclusion about private hardware |
|---|---|
| `original_measurement_missing` | Original JSON/timestamp, Flow entity/topic adapter and HA compatibility; the same reason can cover several failures. |
| `pre_startup_measurement` | Original time against `admission_since`, actual setup/outage boundary and persisted restrictions. |
| `retained_or_unbound_message` | Retained flag and state-topic binding. |
| `replayed_or_out_of_order_measurement` / `out_of_order_original_message` | Repeated or reordered original identities/timestamps. |
| `future_measurement` / `stale_measurement` | Clock alignment and actual delivery age. |
| `provenance_persistence_failed` | Logs and storage write failures; do not bypass persistence. |
| `source_timeout` / `source_unavailable` / `source_missing` | Last observed availability and configured timeout. |
| `verified_original_measurement` | That original was accepted; inspect the current state/reason too, since a later outage may block the source. |

Use the overall status sensor's `measurement_diagnostics` for additional values
such as `mqtt_measurement_provenance.admission_since`, configured timeout and Low
reset progress. A general provenance Repair message is not a unique diagnosis.
Other Repairs concern identical-report suppression, migration or safety recovery;
follow their actual text. Damaged runtime data must be preserved and recovered
from a verified backup, not deleted to create an apparent fresh installation.

The startup fix accepts a genuinely post-setup first original despite delivery
latency; it does not admit old retained/replayed originals. First accepted evidence
is zero seconds. Missing telegrams, unknown and unavailable never mean zero flow.
Record Event-IDs when investigating alarm duration, end or repeated notifications.

User-observed Hydrus telegrams and `verified_original_measurement` demonstrate
the real chain at those instants. They are not a completed **physical Beta.3
HA-restart regression**; that check remains open. Software and TCP-broker tests
must be reported separately. See [beta verification status](BETA_1.2.0.md).
