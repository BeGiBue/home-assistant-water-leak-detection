# F04-FSR-H01: damaged persisted data of configured external leak sensors

Status: **fixed in Water Leak Guard 2.0.0** (released 2026-10-15). The original finding text
is not in the repository; the betas only recorded it as "an open security finding for damaged
persisted alarm data of currently configured external water sensors" and restricted the beta scope
to installations without configured external sensors and with empty `external_sources` /
`external_alarm_ledger` lists. This page derives the finding from the code as it was before the
fix (2.0.0-beta.3, the last beta) and documents the behavior after the fix.

## Definition (derived from the code)

Retained alarm-ledger records (`external_alarm_ledger`, and records marked `tombstone`) were
already validated by their safety role: any damage raised into the Store recovery barrier. The
records of the **configured sources themselves** (`external_sources`, one per configured
sensor) were not. `ExternalLeakController.restore` parsed them leniently:

- A record whose `phase` was missing or unknown **and** whose `event_id` was missing or invalid was
  **dropped**. The configured sensor came back as a fresh `ARMED` source with a new generation.
  An `ACTIVE` alarm and its shutoff contribution were
  silently lost unless the sensor happened to report `on` again at startup. A sensor that is
  `unavailable` while its radio or bridge starts is enough to lose it. The startup save then
  overwrote the damaged record, so the evidence was gone. Nothing was logged and no repair
  issue was raised.
- Other damaged `ACTIVE` records were kept as alarms, but with **invented** identities: a new
  Event-ID, new source/generation IDs, an `unresolved_*` entity or `now` as start time. These
  identities granted ACK and reset capabilities as if they were genuine. A damaged
  `identity_conflict` flag silently re-enabled capabilities for an ambiguous identity. The next
  save rewrote everything as a "clean" record.

In addition, HA itself renames a Store file that is not valid JSON (`NaN`, truncation) to
`<file>.corrupt.<time>` (here `water_leak_detection.runtime.<entry_id>.corrupt.<time>`) and loads
nothing. The first start after that held the recovery barrier,
but the **next** start found no file and behaved like a new installation. All persisted alarms
and shutoff contributions were then gone.

H01 is therefore: *damaged persisted state of a configured external sensor can silently end, or
turn into a trusted but invented identity, an ACTIVE alarm and its shutoff contribution.*

## Case table

Unless stated otherwise, the record is the ACTIVE, shutoff-contributing `external_sources` record of
a configured sensor, and the sensor does not report `on` at restart. "Barrier" means the existing
Store recovery barrier: `storage_recovery_required=true`, aggregate alarm and shutoff request
held, no Store write (original bytes kept), external reset and ACK refused, and the ERROR repair
"runtime safety recovery". In the barrier no persisted event identity is active, so nothing can
be acknowledged or reset.

| Case | Before the fix | After the fix |
|---|---|---|
| List not a list (`null`, dict, string, number) or an entry that is not a dict | Barrier | Barrier (unchanged) |
| A list is missing in a current-schema body (`learning_schema_version: 2`) | Treated as "no external records": ACTIVE alarms and shutoff lost, then overwritten, not reported | Barrier |
| File is not valid JSON (`NaN`, truncated), any installation (hydraulic-only included) | HA renames it to `.corrupt.*`. First start: barrier. Next start: new installation, alarm and shutoff lost, only HA's own storage-corruption repair | Barrier on every start while the file is missing and this entry's `.corrupt.*` copy exists (**behavior change**, also for hydraulic-only installations) |
| `phase` missing/unknown/wrong type, `event_id` valid | Kept ACTIVE with that Event-ID; reset/ACK allowed; rewritten as clean; not reported | Barrier |
| `phase` missing/unknown **and** `event_id` missing/invalid | **Dropped**: source ARMED, alarm and shutoff released, damaged record overwritten, not reported | Barrier |
| ACTIVE, `event_id` missing/invalid | Invented Event-ID; alarm kept; reset/ACK on the invented ID; rewritten; not reported | Barrier |
| `source_id` / `generation` / `learning_epoch` invalid | ACTIVE: tombstone with invented IDs, resettable. Not ACTIVE: dropped | Barrier |
| `entity_id` missing or not `binary_sensor.*` | ACTIVE: tombstone on `binary_sensor.unresolved_*`, resettable. Not ACTIVE: dropped | Barrier |
| `started_at` missing, naive, garbage, number | Replaced by "now" (wrong duration), rewritten | Barrier |
| `contributes_to_shutoff` not a bool (`"false"`, `null`) | Treated as `true` (conservative), rewritten | Barrier |
| `identity_conflict` / `tombstone` not a bool | Treated as `false`: an ambiguous identity regained reset/ACK | Barrier |
| `name` / `registry_id` / `identity_signature` / `reset_nonce` wrong type | Fallback or ignored, rewritten | Barrier |
| ARMED/WAITING record that still carries an Event-ID, nonce or (ARMED) a start time | Barrier (existing contradiction rule) | Barrier (unchanged) |
| Valid duplicate records (same source/generation or same Event-ID) | `identity_conflict` quarantine: every contribution kept, capabilities blocked, sticky, ERROR repair | Unchanged |
| Valid ACTIVE record of a sensor **removed** from the options | Kept as a tombstone (V2-H03): alarm and shutoff held; authorized reset possible | Unchanged |
| Damaged record of a removed sensor | As the damaged rows above (dropped or invented) | Barrier |
| Any damage in `external_alarm_ledger` | Barrier | Barrier (unchanged) |
| Undamaged records (ACTIVE, WAITING, ARMED), hydraulic-only installation | Normal restore | Unchanged |

## Behavior after the fix

- `external_leaks._validate_source_record` checks every `external_sources` record:
  - `phase` must be a known phase;
  - source, generation and epoch IDs must be valid, and `entity_id` must be `binary_sensor.*`;
  - `contributes_to_shutoff` must be a bool;
  - `tombstone`, `identity_conflict`, `name`, `registry_id`, `identity_signature` and
    `reset_nonce` must have the right type if present;
  - a present `started_at` must be an aware timestamp;
  - an ACTIVE record needs a valid Event-ID and an aware start time.

  Optional metadata that older writers did not store may be absent. The check runs before any
  live state is replaced, before a version-1 migration and before every Store write.
- `storage.validate_snapshot_body` treats a missing list in a current-schema body as damage.
- `WaterLeakManager` enters the barrier when the Store file is missing and HA kept a copy of
  exactly this file (`water_leak_detection.runtime.<entry_id>.corrupt.<time>`). Copies of other
  entries or other Store keys do not count. The directory scan runs in the executor. This is a
  deliberate behavior change for **every** installation, hydraulic-only included: before, the
  second start after the rename began as a new installation and silently lost all stored alarms
  (hydraulic alarms in that file are safety evidence too).
- No parallel mechanism: everything reuses the existing Store recovery barrier, its repair issue
  and the `storage_recovery_required` status attribute. The dashboard card shows that attribute as
  its storage-recovery hint, so the card needed no change.
- External ON observations during the barrier still raise alarms in memory. OFF, reset, ACK, option
  changes and learning cannot release anything or write the Store.

### Recovery

1. Stop Home Assistant.
2. Keep the damaged file and any `.corrupt.*` copy for diagnosis.
3. Restore a verified complete HA backup, or the entry's verified runtime Store
   (`.storage/water_leak_detection.runtime.<entry_id>`) together with its matching config entry.
4. Start HA and check that `storage_recovery_required` is false and that the expected ACTIVE alarms
   and shutoff request are back. Only a genuine physical reset or an authorized, unambiguous
   external reset may then end them.

There is no in-app override. In the `.corrupt.*` case without a usable backup: stop HA and move
`.storage/water_leak_detection.runtime.<entry_id>.corrupt.<time>` out of `.storage`. This
deliberately accepts the loss of the persisted state, the same as deleting the Store. Do not do
that to clear an alarm.

## Residual limits

- **Plausible damage is not detectable.** A record changed to a fully consistent ARMED record
  (phase `ARMED`, no Event-ID, nonce or start time), or a `contributes_to_shutoff` flipped from
  `true` to `false`, looks genuine. If the sensor still reports `on` at startup it raises a new
  alarm; if it is unavailable, the old alarm is not restored.
- **Strict instead of selective.** The barrier is global: one damaged source record holds every
  alarm and the shutoff request, and blocks learning and all resets until recovery.
- **Missing optional keys are accepted.** A record from an older writer may legitimately lack them.
  Required keys (phase, IDs, entity, shutoff flag, and for ACTIVE the Event-ID and start time) may
  not be missing.
- **Store-level copy.** The `.corrupt.*` check only looks next to the Store file. If the copy is
  moved away while the Store file is missing, the next start is a new installation, the same as
  deleting the Store. Without a backup that is the deliberate way out (HA stopped).
- The integration never operates a valve; the shutoff request is a signal for external automations.
