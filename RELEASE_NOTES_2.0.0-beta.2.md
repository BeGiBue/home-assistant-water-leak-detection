# Water Leak Guard 2.0.0-beta.2

## Compact dashboard card (card 0.5.0)

- The idle card in one column is about **335 px** high instead of about 830–930 px. It fits an iPhone,
  an iPad dashboard column and a Raspberry Pi 7″ 800×480 display under the HA toolbar (measured in
  Chromium, ±15 px depending on fonts).
- **Collapsible sections:** "High Flow bypass" and "Learning" are collapsed by default. An active
  bypass shows its remaining time and "End" in the summary row. The four learning values sit in one row.
- Detectors are shown as a 2×2 status grid. The header is flatter, and while monitoring is healthy a
  compact "Hydraulics active" pill replaces the monitoring row.
- **Two columns** once the card itself is at least about 600 px wide. That is the panel view, or a
  sections view with `column_span` ≥ 2 and `grid_options: columns: full`. Home Assistant caps masonry
  and sections columns at about 500 px, so the card stays single-column there.
- All controls have a hit area of at least 44 px.

## No more on/off switches on the card

- The card no longer shows the Slow Leak / Low Flow switches; they remain on the device page.
- While a Slow Leak or Low Flow alarm is active, the alarm box offers **"Disable detection"**
  (with confirmation). During a High Flow alarm it offers **"Start bypass"**.
- Both end the alarm, so the card offers them only to a **paired device at home**, in line with
  "acknowledge from anywhere, clear only from home". Away they are shown disabled. Home Assistant
  entities and services themselves stay unrestricted.

## Honest status display

- With the source impaired (`source_unavailable`, `source_available: false`) or the runtime store
  damaged, nothing is green anymore. The card shows "Monitoring impaired", the row shows "Impaired" and
  the detector tiles show "Paused". An alarm keeps priority.
- An insufficient learning state is no longer green.
- The mute button names the paired recipient ("Mute for …").

## Pairing with a Home Assistant user

- A notification recipient can be paired with a **Home Assistant user**. This is the new default and
  survives a new login. The pairing with a **single login** remains for one user on several devices,
  and a login pairing wins over a user pairing.
- Long-lived access tokens never match. Inactive and system users are rejected. A user and a login can
  each be paired with one recipient only.
- Existing login pairings keep working without migration. Recipient alarm settings are unchanged.
- With a user pairing, every login of that user gets the paired device's rights; the home check still
  uses the paired recipient's tracker.

## README

- HACS-compatible logo (no raw HTML) and a card preview image.
- Card troubleshooting covers the served URL and frontend cache resets.

## Verification

- Complete repository test suite, Ruff, Hassfest and HACS validation pass. New card logic tests run in
  plain Node in the Validate workflow and were checked by mutation.
- An independent review instance reviewed every round from the code on GitHub and gave the final head
  its approval.
- **Not yet verified on a live Home Assistant installation** or on real devices.

## Upgrade

Back up, enable beta versions in HACS, download `2.0.0-beta.2`, restart Home Assistant and reload the
browser / Companion app. See [installation](docs/INSTALLATION.md#upgrading-from-200-beta1-to-200-beta2).
The beta scope is unchanged: hydraulic monitoring and notifications without configured external leak
sensors (see [Beta 2.0.0](docs/BETA_2.0.0.md)).
