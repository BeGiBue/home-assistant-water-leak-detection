# Installation and updates

## Requirements

- Home Assistant 2026.9.0 or newer
- HACS for the recommended installation path
- One compatible flow-rate sensor
- Optional cumulative water-consumption sensor
- Home Assistant Companion App devices if notification/acknowledgement features are used

## HACS installation

### One-click

[![Open your Home Assistant instance and open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=BeGiBue&repository=homeassistant-water-leak-detection&category=integration)

### Manual HACS repository

1. Open **HACS** in Home Assistant.
2. Open the HACS menu and choose **Custom repositories**.
3. Add:
   - Repository: `https://github.com/BeGiBue/homeassistant-water-leak-detection`
   - Category: **Integration**
4. Open **Water Leak Guard** in HACS.
5. Download the latest release.
6. Restart Home Assistant.
7. Open **Settings → Devices & services → Add integration**.
8. Search for **Water Leak Guard**.
9. Complete the configuration flow.

## Manual installation

1. Download the repository source for the desired release.
2. Copy `custom_components/water_leak_detection` to:
   `<config>/custom_components/water_leak_detection`
3. Restart Home Assistant.
4. Add the integration from **Settings → Devices & services**.

## Updating with HACS

1. Open HACS.
2. Install the offered update.
3. Restart Home Assistant if HACS requests it.
4. Review release notes before changing detector thresholds or shutoff behavior.

Runtime learning history, active acknowledgement state, and relevant integration state are stored by Home Assistant and are not intended to be replaced by HACS package files.

## Removing the integration

1. Remove the config entry under **Settings → Devices & services**.
2. Remove the integration from HACS.
3. Restart Home Assistant if requested.

If you configured external automations that react to the **Water shutoff request** entity or integration events, remove or disable those automations separately.

## Versioning

When GitHub Releases are published, HACS uses the latest published release tag as the remote version. A Git tag without a published GitHub Release is not sufficient for HACS release versioning.


## Language

The integration uses the language configured in Home Assistant. German (`de`) is included as a complete runtime translation; English is the fallback.

Entity and device names are translated by Home Assistant when they are created. Existing user-renamed entities are not overwritten.

## Changing the configuration later

After the integration is installed, open **Settings → Devices & services → Integrations → Water Leak Guard**.

**Configure** can be opened again at any time and contains:

- **Measurement sources** — flow-rate and optional cumulative-consumption source entities.
- **Notification recipients** — add, edit, or remove Companion App recipients.
- **Expert settings** — detector, learning, hydraulic, bypass, and shutoff options.

Home Assistant's separate **Reconfigure** action for measurement sources remains supported as an additional path.

Saving a Configure subsection returns to the appropriate menu instead of closing the full dialog. Under **Notification recipients**, use **Back to configuration** to return to the main menu. The X in the header closes the complete options flow.

Notification recipients do not have to be configured only during initial installation; they can be added, edited, or removed later.

### Back without saving

Each source, expert and recipient form now has a **Back without saving** switch.
Enable it and submit to return to the preceding menu without saving or validating
unfinished fields. Changing only recipients preserves running detection timers.

## Upgrading to the published 1.2.0-beta.3

A GitHub pre-release does **not** update an already running Home Assistant.
Back up HA configuration and the integration runtime Store first. In HACS enable
pre-release/beta versions and explicitly download `1.2.0-beta.3` (or copy that
release's integration directory manually), then restart HA. Confirm the installed
version and find **Hydraulic monitoring** / **Hydraulische Überwachung** on the
existing integration device. Keep your existing config entry; do not delete it
or its Store to resolve a blocked state. Check the
[beta prerequisites and user-confirmed restart test](BETA_1.2.0.md).

Card 0.1.0 of this beta had to be registered manually; since 2.0.0-beta.1 the card is loaded
automatically (see below).

## Upgrading from 2.0.0-beta.1 to 2.0.0-beta.2

Back up, download `2.0.0-beta.2` in HACS and restart Home Assistant, then reload the browser /
Companion app (the card URL changes with its content, so card 0.5.0 loads automatically). Existing
recipient pairings keep working without migration. Optionally switch a pairing from a single login
to the Home Assistant user (*Configure → Notification recipients → Edit recipient*), so it survives a
new login. The card no longer shows on/off switches; Slow Leak/Low Flow stay switchable on the device
page.

## Upgrading to 2.0.0-beta.1

A GitHub pre-release does **not** update a running Home Assistant. Back up the HA configuration
and the integration runtime Store. In HACS enable beta versions, download `2.0.0-beta.1` and restart
Home Assistant. Then:

1. Reload the browser / Companion app and add the card via **Add card → Water Leak Guard**. No file
   copy and no dashboard resource are needed.
2. If you added the card manually before, delete the resource `/local/water-leak-guard-card.js`
   (*Settings → Dashboards → ⋮ → Resources*) and the file in `<config>/www/`. Existing card
   configurations (`type: custom:water-leak-guard-card`) keep working.
3. Optional: pair devices for alarm actions in the card under **Configure → Notification recipients →
   Edit recipient → Pairing for the dashboard card** (a Home Assistant user, the default, or a single
   login).

The beta scope is unchanged: hydraulic detection with notifications, without configured external
leak sensors or persisted external records. See [2.0 beta notes](BETA_2.0.0.md) and
[card guide](CARD.md).
