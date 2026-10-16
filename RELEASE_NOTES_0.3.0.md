# Water Leak Guard 0.3.0

Version 0.3.0 completes the original backend roadmap through adaptive detection and hydraulic plausibility.

## Home Assistant UI

- Appears as a normal integration under **Settings → Devices & services → Integrations**.
- Uses the configured Home Assistant language for the integration title, device/entity names, states, configuration dialogs, service actions, and Companion notification text.
- Complete German (`de`) runtime translation is included; English is the fallback.
- Notification recipients can be configured during initial setup and later through **Configure**.
- **Configure** also exposes measurement sources and expert settings after installation.
- Source sensors can additionally be changed through Home Assistant's **Reconfigure** action.

## Highlights

- Four independent detector classes: Slow Leak, Low Flow, High Flow, Burst Leak.
- Multi-device Companion notifications and geofenced acknowledgement.
- Trusted stationary Home devices such as a shared tablet.
- Persistent High Flow bypass that never disables Burst Leak.
- Independent shutoff-request endpoint.
- Rolling adaptive learning of normal household peak flow.
- Learning confidence and coverage sensors.
- Hydraulic plausibility context using pipe diameter and static pressure.
- Adaptive High/Burst thresholds.
- Rapid rate-of-rise Burst detection.
- 80 automated tests validated against Home Assistant 2026.9.4 / Python 3.14.2.

## Installation

Recommended: install through HACS as a custom Integration repository:

`https://github.com/BeGiBue/home-assistant-water-leak-detection`

Minimum Home Assistant: 2026.9.0.

After HACS installation, restart Home Assistant and add **Water Leak Guard** under **Settings → Devices & services**.

## Upgrade notes

This is the first published 0.3.0 release. Existing development installations should:

1. update the integration files,
2. restart Home Assistant,
3. review expert options,
4. verify notification-recipient trackers,
5. verify any automation reacting to the Water shutoff request.

Adaptive learning begins with insufficient confidence and gains influence only as valid normal-use samples accumulate.

## Safety notes

- High Flow bypass suppresses High Flow only.
- Burst Leak always remains active.
- Acknowledgement does not mean the physical leak has ended.
- Acknowledgement does not automatically clear the shutoff request.
- Hydraulic calculations are plausibility context, not a guaranteed physical maximum.
- Automatic valve closure must be explicitly configured and tested by the user.

## Documentation

See:

- README.md
- docs/INSTALLATION.md
- docs/CONFIGURATION.md
- docs/TROUBLESHOOTING.md
- SPEC.md
