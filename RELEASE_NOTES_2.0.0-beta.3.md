# Water Leak Guard 2.0.0-beta.3

## Dashboard card 0.6.1

- "High Flow bypass" and "Learning" now start **expanded**.
- The new card option `collapsed: true` (editor: "Start with sections collapsed") is meant for short
  screens such as a Raspberry Pi 7″ display in landscape (800×480). In portrait (480×800) the default
  open card fits under the toolbar.
- The card size hint follows the expanded state.

## Wall display as a recipient

A new recipient kind for a fixed wall display such as TouchKio (*Configure → Notification recipients
→ Add wall display*):

- It needs no notify service and no device tracker.
- It never receives notifications and always counts as at home.
- It has no mute.
- Its rights come from the usual checkboxes; global acknowledgement is off by default.

Card actions that need "paired and at home" become available on the display. These are global
acknowledgement and external reset (if permitted), plus disabling Slow/Low or starting the bypass
during an alarm.

**Pairing** works in one of two ways:

- **A dedicated kiosk user.** The user must be active, neither owner nor administrator, and paired
  nowhere else. Every login of this user counts as at home, including a remote one with its password,
  so give it its own strong password.
- **The single login of the kiosk.** This binds the rights to that one session. It must be renewed
  after the kiosk logs in again.

Companion app logins, and logins of users that a phone recipient uses, cannot be paired with a
display. The rules apply in the forms and at runtime, also across several instances of the
integration.

An external leak can be reset from a display only through the card, not through notification actions
or the `external_reset` service. A recipient with an unknown kind is logged and never authorized.

The wiki has an example automation for TouchKio. The recommended variant only turns the display on.
If the automation sets a page URL, it must use exactly the same base URL the kiosk starts with.

## Shutoff-request icon

The shutoff-request binary sensor shows `mdi:valve-open` while no shutoff is requested and
`mdi:valve-closed` while one is requested.

## Verification

- The complete test suite, Ruff, Hassfest and HACS validation pass. The card logic tests (Node) also
  pass.
- An independent review instance reviewed every round from the code on GitHub and approved the final
  state. The key guards were checked by mutation.
- Not yet verified on a live installation with TouchKio.

## Upgrade

Back up, download `2.0.0-beta.3` in HACS, restart Home Assistant and reload the browser / Companion
app. Existing recipients and pairings are unchanged. See
[installation](docs/INSTALLATION.md#upgrading-to-200-beta3).
