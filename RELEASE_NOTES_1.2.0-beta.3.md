# Water Leak Guard 1.2.0-beta.3

## Hydraulic monitoring is now visible

A new regular sensor, **Hydraulic monitoring** / **Hydraulische Überwachung**, shows
whether the hydraulic source is actually admitted to detection:

- `active`: validated measurements are admitted.
- `waiting_for_measurement`: startup/source change has not yet admitted a measurement,
  and no explicit exclusion has been observed.
- `blocked`: source unavailability, timeout, invalid flow or rejected MQTT provenance.

The sensor remains available when monitoring is blocked. Its attributes expose the
manager's reason, source entity, source availability, MQTT provenance status, last
valid HA measurement observation timestamp and monotonic observation age.

**No alarm** and **monitoring active** are independent. A blocked source does not
clear an existing alarm, ACK it, or release a shutoff request. Detection, evidence,
MQTT replay protection, notifications, ACK and persistence rules are unchanged.

## Upgrade

Home Assistant 2026.9.0 or newer is required. Install this pre-release through HACS
with beta versions enabled, restart Home Assistant, and find the new sensor on the
existing integration device. No manual MQTT subscriptions or dashboard changes are
needed. Version 1.2.0-beta.2 is not modified or overwritten.

## Known limitations

The beta remains intended for hydraulic monitoring and notifications in the restricted
household setup without external leak sensors or persisted external alarm records.
The previously documented H01 limitation concerning corrupted external alarm data
remains open; external sensors are not unconditionally approved. No physical Hydrus
radio/hardware validation is claimed. The integration never opens a physical valve.
