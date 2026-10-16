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

## Dashboard card

**Card is missing in "Add card".** Since 2.0.0-beta.1 the integration loads the card itself.

1. Restart Home Assistant after installing/updating (a HACS download alone loads nothing).
2. Open `http://<your-ha>:8123/water_leak_detection/water-leak-guard-card.js` in a browser. JavaScript
   text means the integration serves the card; 404 means it was not registered — check the log for
   `water_leak_detection` / `Dashboard card could not be registered` (leak detection keeps running).
3. Browsers and the Companion app cache the Home Assistant start page. Do a hard reload in the browser
   (Ctrl/Cmd+Shift+R); in the Companion app use *Settings → Companion App → Debugging → Reset frontend
   cache*, then reopen the app.
4. In *Add card* search for "Water Leak Guard"; custom cards are listed below the built-in cards.

**"Configuration error" ("Konfigurationsfehler") instead of the card, a reload fixes it.** Most likely
the page did not get the card module in time. HA writes extra modules into the start page only when
it serves the page, serves the frontend before custom integrations are set up and never asks again;
the Companion app and the browser's service worker may also show a cached start page from such a
moment (without the module, or with an older `?v=` digest). HA then shows its error card after two
seconds and waits for the card element. Since 2.0.0 the integration also keeps a small
Lovelace resource (*Settings → Dashboards → ⋮ → Resources*, a `data:text/javascript…` entry
"water-leak-guard-card loader"). It needs no server request, waits briefly for the card, then loads
it as soon as the integration serves it (with retries), and HA replaces the error card by itself.
Do not delete that entry; it is removed when the last Water Leak Guard entry is removed. With
resources in YAML mode (`lovelace: resource_mode: yaml`) the integration cannot add it: add the same
entry yourself or reload the page after HA has started.

- *Two copies of the card code.* A cached start page with an older `?v=` digest and the loader with
  the current one can both load the card file. The first one defines the element; the second only
  logs the "version … is already loaded" warning if the versions differ (the define guard prevents
  any error). The loader skips its import when the card gets defined within a few seconds.
- *Card 0.6.2 hardening.* The card's `hass` setter and render path no longer throw. If a render
  error happens anyway, the browser console shows `water-leak-guard-card: render failed, retrying on
  the next update`, the card shows "Loading …" (plus an alarm line if an alarm is active) and tries
  again on the next update. Please include that console line in a bug report.

**Uninstall in this order.** First remove all Water Leak Guard entries under *Settings → Devices &
services* (this also removes the loader resource), then remove the integration in HACS and restart.
If the files are removed first, the loader resource stays: delete the "water-leak-guard-card
loader" entry under *Resources* by hand. Until then it tries to load the missing card a few times
and stops once Home Assistant reports that it has fully started.

**Console warning "version … is already loaded".** An older, manually added resource
`/local/water-leak-guard-card.js` is still present. Remove it under *Settings → Dashboards → ⋮ →
Resources* and delete the file from `<config>/www/`.

**Card says "This device is not paired – view only".** Edit the recipient of this device and select
its user (or a single login) under *Pairing for the dashboard card*. A user pairing survives a new
login; with a single-login pairing, select the new login after the device logs in anew.

**"Global acknowledge" is disabled or rejected with "not at home".** The backend uses the paired
recipient's `device_tracker.*`. Check that tracker; a trusted stationary flag does not replace it.

**Card stays grey/yellow with "No alarm".** Monitoring is not confirmed active or an external sensor is
offline; see the monitoring row and [Hydraulic monitoring: waiting or
blocked](#hydraulic-monitoring-waiting-or-blocked).

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

`https://github.com/BeGiBue/water-leak-guard/issues`

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

The user confirmed a successful **physical Hydrus HA restart on 14 October 2026**
with installed Beta.3: no false alarm or Repair, initially blocked for 11 seconds,
then automatically active with `verified_original_measurement`. This was not a
Codex-performed hardware test. The temporary block is compatible with conservative
source admission; 11 seconds is not a guaranteed duration or a reason to disable
safety checks. It does not prove all MQTT outage/restart scenarios. Software and
TCP-broker tests remain separate. See [observations and limits](BETA_1.2.0.md).
