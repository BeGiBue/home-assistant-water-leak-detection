"""WebSocket commands for the dashboard card.

The card is not a trust boundary. Every command identifies the calling device
only by the authenticated HA login of the connection (``refresh_token_id``) and
its user. An administrator pairs a notification recipient either with one HA
user (every normal login of that user) or with exactly one login; a login
pairing wins over a user pairing (see ``session_recipient``). The
card never sends or receives a recipient token or reset nonce; they are read
server side and handed to the existing, tested validators:

- mute:            device-scoped, from anywhere (same effect as the MUTE action)
- acknowledge:     global, only while that recipient is Home
                   (``WaterLeakManager.async_acknowledge_event``)
- external_reset:  external sources only, Home and permission required
                   (``WaterLeakManager.async_external_reset``)

There is no WebSocket command for hydraulic alarms. They end when the flow meets
their quiet/reset condition, or through the existing controls outside this module
(switching the Slow Leak/Low Flow detector off, starting the High Flow bypass);
Burst Leak ends only physically. No command here ends detection, an alarm or the
shutoff request except the explicit external reset, which the backend validates
at commit time.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.auth.models import TOKEN_TYPE_NORMAL
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import ACTION_EXTERNAL_RESET, ATTR_CONFIG_ENTRY_ID, DOMAIN

if TYPE_CHECKING:
    from .manager import WaterLeakManager
    from .notifications import NotificationRecipient

_LOGGER = logging.getLogger(__name__)

WS_SESSION = f"{DOMAIN}/session"
WS_MUTE = f"{DOMAIN}/mute"
WS_ACKNOWLEDGE = f"{DOMAIN}/acknowledge"
WS_EXTERNAL_RESET = f"{DOMAIN}/external_reset"

# Stable error codes for the card. Messages are English diagnostics only.
ERR_INSTANCE = "instance_not_found"
ERR_NOT_PAIRED = "not_paired"
ERR_NOT_ACTIVE = "event_not_active"
ERR_NOT_ALLOWED = "not_allowed"
ERR_NOT_HOME = "not_home"
ERR_REJECTED = "rejected"
ERR_NOT_COMMITTED = "not_committed"


class CommandError(Exception):
    """Rejected card command with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _manager(hass: HomeAssistant, msg: dict[str, Any]) -> WaterLeakManager:
    managers: dict[str, WaterLeakManager] = hass.data.get(DOMAIN, {})
    entry_id = msg.get(ATTR_CONFIG_ENTRY_ID)
    if entry_id:
        manager = managers.get(entry_id)
    elif len(managers) == 1:
        manager = next(iter(managers.values()))
    else:
        manager = None
    if manager is None or manager._closed:
        raise CommandError(ERR_INSTANCE, "Water Leak Guard instance not found or ambiguous")
    return manager


@callback
def session_recipient(
    hass: HomeAssistant, manager: WaterLeakManager, connection
) -> NotificationRecipient | None:
    """Recipient paired with this connection's login or user, or None.

    Only a still existing, normal (app/browser) login of an active, non-system
    user that belongs to the connection's user is accepted; long-lived access
    tokens never match. Then:

    1. a recipient paired with exactly this login wins,
    2. otherwise a recipient paired with the connection's user applies,
    3. otherwise the session is not paired.

    With a user pairing every login of that user (e.g. a laptop browser) gets
    the paired recipient's rights; the Home check still uses that recipient's
    device tracker. Deleting the login in HA, or deactivating the user, removes
    the pairing's effect.
    """
    token_id = getattr(connection, "refresh_token_id", None)
    user = getattr(connection, "user", None)
    if not token_id or user is None:
        return None
    auth = getattr(hass, "auth", None)
    token = auth.async_get_refresh_token(token_id) if auth is not None else None
    if (
        token is None
        or token.token_type != TOKEN_TYPE_NORMAL
        or token.user.id != user.id
        or not token.user.is_active
        or token.user.system_generated
    ):
        return None
    return manager.notifications.recipient_for_session(token_id, token.user.id)


def _require_recipient(hass, manager, connection) -> NotificationRecipient:
    recipient = session_recipient(hass, manager, connection)
    if recipient is None:
        raise CommandError(ERR_NOT_PAIRED, "This device is not paired with a recipient")
    return recipient


def _is_home(hass: HomeAssistant, recipient: NotificationRecipient) -> bool:
    tracker = hass.states.get(recipient.tracker_entity)
    return tracker is not None and tracker.state == "home"


def _send(connection, msg, job_result: dict | None = None, error: CommandError | None = None):
    if error is not None:
        connection.send_error(msg["id"], error.code, str(error))
    else:
        connection.send_result(msg["id"], job_result or {})


async def handle_session(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """What this device may do right now. Informational; every action re-checks."""
    try:
        manager = _manager(hass, msg)
    except CommandError as err:
        _send(connection, msg, error=err)
        return
    recipient = session_recipient(hass, manager, connection)
    if recipient is None:
        _send(connection, msg, {"paired": False})
        return
    _send(
        connection,
        msg,
        {
            "paired": True,
            "recipient_id": recipient.id,
            "recipient_name": recipient.name,
            "home": _is_home(hass, recipient),
            # Not a secret: lets the card refresh this answer when the tracker changes.
            "tracker_entity": recipient.tracker_entity,
            "trusted_stationary": recipient.trusted_stationary,
            "can_global_ack": recipient.allow_global_ack,
            "can_external_reset": recipient.allow_external_reset,
        },
    )


async def _locked(manager: WaterLeakManager, action):
    """Run inside the manager's writer, like notification actions.

    The pairing is resolved again inside the writer, so a pairing removed or
    changed while the command waited for the writer can no longer authorize it.
    """
    return await manager.async_mobile_notification_action(action)


async def handle_mute(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Device-scoped mute for this paired device only, from anywhere."""
    try:
        manager = _manager(hass, msg)
        _require_recipient(hass, manager, connection)

        async def action():
            recipient = _require_recipient(hass, manager, connection)
            return await manager.notifications.async_session_mute(msg["event_id"], recipient.id)

        reason = await _locked(manager, action)
        if reason == "not_paired":
            raise CommandError(ERR_NOT_PAIRED, "Recipient no longer configured")
        if reason == "event_not_active":
            raise CommandError(ERR_NOT_ACTIVE, "Event is not active")
    except CommandError as err:
        _send(connection, msg, error=err)
        return
    _send(connection, msg, {"muted": True, "scope": "device"})


async def handle_acknowledge(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Global acknowledgement through the native validator; Home checked at commit."""
    event_id = msg["event_id"]
    try:
        manager = _manager(hass, msg)
        recipient = _require_recipient(hass, manager, connection)

        async def action():
            current = _require_recipient(hass, manager, connection)
            # Native validator re-reads options and checks token, permission,
            # Home and the active event; it is reentrant inside the writer.
            return current, await manager.async_acknowledge_event(
                event_id, current.id, current.token
            )

        try:
            recipient, accepted = await _locked(manager, action)
        except CommandError:
            raise
        except Exception as exc:  # durable write failed; nothing was published
            _LOGGER.exception("Dashboard acknowledgement not committed")
            raise CommandError(ERR_NOT_COMMITTED, "Acknowledgement was not saved") from exc
        if not accepted:
            # Explain the rejection; the decision itself was made by the validator.
            if event_id not in manager.active_events():
                raise CommandError(ERR_NOT_ACTIVE, "Event is not active")
            current = manager.notifications.recipients.get(recipient.id)
            if current is None:
                raise CommandError(ERR_NOT_PAIRED, "Recipient no longer configured")
            if not current.allow_global_ack:
                raise CommandError(ERR_NOT_ALLOWED, "Global acknowledgement not allowed")
            if not _is_home(hass, current):
                raise CommandError(ERR_NOT_HOME, "Device is not Home")
            raise CommandError(ERR_REJECTED, "Acknowledgement rejected")
    except CommandError as err:
        _send(connection, msg, error=err)
        return
    _send(connection, msg, {"acknowledged": True, "scope": "global"})


async def handle_external_reset(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Reset one exact external event through the native validator."""
    try:
        manager = _manager(hass, msg)
        _require_recipient(hass, manager, connection)

        async def action():
            # Binding, pairing and nonce are read inside the writer, the same
            # serialization the notification reset action uses.
            current = _require_recipient(hass, manager, connection)
            source = manager.external.event_for(
                msg["source_id"], msg["source_generation"], msg["event_id"]
            )
            if source is None or msg["event_id"] not in manager.active_events():
                raise CommandError(ERR_NOT_ACTIVE, "External event is not active")
            payload = {
                "action_kind": ACTION_EXTERNAL_RESET,
                "config_entry_id": manager.entry.entry_id,
                "source_id": source.source_id,
                "source_generation": source.identity.generation,
                "event_id": source.event_id,
                "recipient_id": current.id,
                "recipient_token": current.token,
                "reset_nonce": source.reset_nonce,
            }
            return current, await manager.async_external_reset(payload)

        recipient, reset = await _locked(manager, action)
        if not reset:
            if not recipient.allow_external_reset:
                raise CommandError(ERR_NOT_ALLOWED, "External reset not allowed")
            if not _is_home(hass, recipient):
                raise CommandError(ERR_NOT_HOME, "Device is not Home")
            if manager.external.event_for(
                msg["source_id"], msg["source_generation"], msg["event_id"]
            ) is None:
                raise CommandError(ERR_NOT_ACTIVE, "External event is not active")
            raise CommandError(ERR_REJECTED, "External reset rejected or not committed")
    except CommandError as err:
        _send(connection, msg, error=err)
        return
    _send(connection, msg, {"reset": True})


_ENTRY = vol.Optional(ATTR_CONFIG_ENTRY_ID)
_EVENT = vol.Required("event_id")

COMMANDS = (
    (handle_session, {vol.Required("type"): WS_SESSION, _ENTRY: str}),
    (handle_mute, {vol.Required("type"): WS_MUTE, _ENTRY: str, _EVENT: str}),
    (handle_acknowledge, {vol.Required("type"): WS_ACKNOWLEDGE, _ENTRY: str, _EVENT: str}),
    (
        handle_external_reset,
        {
            vol.Required("type"): WS_EXTERNAL_RESET,
            _ENTRY: str,
            _EVENT: str,
            vol.Required("source_id"): str,
            vol.Required("source_generation"): str,
        },
    ),
)


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register all card commands (idempotent)."""
    for handler, schema in COMMANDS:
        websocket_api.async_register_command(
            hass,
            websocket_api.websocket_command(schema)(websocket_api.async_response(handler)),
        )
