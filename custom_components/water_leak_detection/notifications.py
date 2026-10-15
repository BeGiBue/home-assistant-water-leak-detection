"""Companion notification and acknowledgement handling."""

from __future__ import annotations

import ast
import asyncio
import base64
import inspect
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from functools import wraps
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import translation
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    ACTION_ACK_ALL,
    ACTION_EXTERNAL_RESET,
    ACTION_MUTE,
    ACTION_PREFIX,
    CONF_NOTIFICATION_RECIPIENTS,
    DOMAIN,
    EVENT_ACK_REJECTED,
    EVENT_ACKNOWLEDGED,
    EVENT_LEAK_ENDED,
    EVENT_LEAK_STARTED,
    MOBILE_ACTION_EVENT,
    RECIPIENT_ALLOW_EXTERNAL_RESET,
    RECIPIENT_ALLOW_GLOBAL_ACK,
    RECIPIENT_CRITICAL_ENABLED,
    RECIPIENT_ID,
    RECIPIENT_KIND,
    RECIPIENT_KIND_DISPLAY,
    RECIPIENT_KIND_MOBILE,
    RECIPIENT_KINDS,
    RECIPIENT_NAME,
    RECIPIENT_NOTIFY_SERVICE,
    RECIPIENT_SESSION_TOKEN_ID,
    RECIPIENT_SESSION_USER_ID,
    RECIPIENT_TOKEN,
    RECIPIENT_TRACKER_ENTITY,
    RECIPIENT_TRUSTED_STATIONARY,
    DetectorKind,
)
from .validation import parse_datetime, string_set

if TYPE_CHECKING:
    from homeassistant.auth.models import RefreshToken, User

    from .manager import WaterLeakManager

_LOGGER = logging.getLogger(__name__)
_WARNED: set[tuple[str, str]] = set()


def _warn_once(reason: str, raw: dict[str, Any], message: str) -> None:
    """Log a configuration problem of one recipient once per process (not per query)."""
    key = (reason, str(raw.get(RECIPIENT_ID)))
    if key in _WARNED:
        return
    _WARNED.add(key)
    _LOGGER.warning(message, raw.get(RECIPIENT_ID), raw.get(RECIPIENT_NAME))


def pairing_uses_user(hass: HomeAssistant, raw: dict[str, Any], user_id: str) -> bool:
    """Whether a stored recipient pairing refers to this HA user.

    True for a user pairing with this user and for a login pairing with one of
    this user's logins (of any token type). Both keys are checked, even though a
    login pairing takes precedence: this is a conflict check, so stricter is safer.
    """
    if raw.get(RECIPIENT_SESSION_USER_ID) == user_id:
        return True
    token_id = raw.get(RECIPIENT_SESSION_TOKEN_ID)
    if not isinstance(token_id, str) or not token_id:
        return False
    auth = getattr(hass, "auth", None)
    token = auth.async_get_refresh_token(token_id) if auth is not None else None
    return token is not None and token.user.id == user_id


# Client ids of the Home Assistant Companion apps (iOS/macOS and Android, also
# their dev/beta variants). Such a login belongs to a phone or tablet, never to a
# wall display, which always counts as home.
COMPANION_CLIENT_PREFIXES = ("https://home-assistant.io/ios", "https://home-assistant.io/android")


def is_companion_login(token: RefreshToken) -> bool:
    """Whether this login comes from a Companion app (phone/tablet)."""
    client_id = token.client_id if isinstance(token.client_id, str) else ""
    return client_id.casefold().startswith(COMPANION_CLIENT_PREFIXES)


def recipients_of_other_entries(hass: HomeAssistant, entry_id: str) -> list[dict[str, Any]]:
    """Stored recipients of every other config entry of this integration.

    The kiosk and display-login rules are about HA users and logins, which are
    shared by all instances, so their pairings count as "another recipient".
    """
    config_entries = getattr(hass, "config_entries", None)
    if config_entries is None:
        return []
    others: list[dict[str, Any]] = []
    for entry in config_entries.async_entries(DOMAIN):
        if entry.entry_id == entry_id:
            continue
        raws = entry.options.get(CONF_NOTIFICATION_RECIPIENTS, [])
        if isinstance(raws, list):
            others.extend(raw for raw in raws if isinstance(raw, dict))
    return others


def display_login_problem(
    hass: HomeAssistant, token: RefreshToken | None, others: list[Any]
) -> str | None:
    """Why this login may not act as a wall display, or None.

    A display is always Home, so a phone's login must never be one: a
    Companion app login is refused, and so is any login of a user that a mobile
    recipient's pairing uses (as user or through one of its logins). ``others``
    are the stored entries of every other recipient. An unknown login fails closed.
    """
    if token is None:
        return "unknown_login"
    if is_companion_login(token):
        return "companion_app"
    if any(
        isinstance(raw, dict)
        and raw.get(RECIPIENT_KIND, RECIPIENT_KIND_MOBILE) != RECIPIENT_KIND_DISPLAY
        and pairing_uses_user(hass, raw, token.user.id)
        for raw in others
    ):
        return "user_of_mobile"
    return None


_DISPLAY_REFUSALS = {
    "not_allowed": "is paired with a user that is the owner or an administrator (or not an "
    "active person)",
    "in_use": "is paired with a user that is also used by another recipient's pairing (as user "
    "or by one of its logins, in any instance)",
    "unknown_login": "was matched by a login that no longer exists",
    "companion_app": "was matched by a Companion app login (a phone or tablet)",
    "user_of_mobile": "was matched by a login of a user that a mobile recipient's pairing uses",
}


def kiosk_user_problem(hass: HomeAssistant, user: User | None, others: list[Any]) -> str | None:
    """Why this user may not be the user pairing of a wall display, or None.

    A display is always Home, and a user pairing covers every normal login of
    that user, also a remote one. So only a dedicated kiosk user is allowed:
    active, not system-generated, neither owner nor administrator, and not used
    by any other recipient's pairing (as user or through one of its logins).
    ``others`` are the stored entries of every other recipient.

    Returns "not_allowed" (no such active person, owner or admin), "in_use" or None.
    """
    if user is None or not user.is_active or user.system_generated:
        return "not_allowed"
    if user.is_owner or user.is_admin:
        return "not_allowed"
    if any(isinstance(raw, dict) and pairing_uses_user(hass, raw, user.id) for raw in others):
        return "in_use"
    return None


def notification_writer(method):
    """Use the manager's shared writer for per-event metadata mutations."""

    @wraps(method)
    async def guarded(self, *args, **kwargs):
        writer = getattr(self.manager, "async_notification_action", None)
        if writer is None:
            return await method(self, *args, **kwargs)
        return await writer(lambda: method(self, *args, **kwargs))

    return guarded


@dataclass(slots=True, frozen=True)
class NotificationRecipient:
    """One configured Companion notification target."""

    id: str
    name: str
    notify_service: str
    tracker_entity: str
    critical_enabled: bool
    allow_global_ack: bool
    trusted_stationary: bool
    token: str
    allow_external_reset: bool = False
    session_token_id: str | None = None
    session_user_id: str | None = None
    kind: str = RECIPIENT_KIND_MOBILE

    @property
    def is_display(self) -> bool:
        """Stationary display: no notifications, no tracker, always Home."""
        return self.kind == RECIPIENT_KIND_DISPLAY

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> NotificationRecipient | None:
        """Create a recipient from config-entry options.

        Entries without ``kind`` are mobile recipients (all entries before the
        display kind existed). An unknown or empty kind is ignored entirely and
        logged, because such a recipient would silently receive no alarms.
        """
        kind = raw.get(RECIPIENT_KIND, RECIPIENT_KIND_MOBILE)
        if kind not in RECIPIENT_KINDS:
            _warn_once(
                "unknown_kind",
                raw,
                "Notification recipient %s (%s) has an unknown kind and is ignored: "
                "it receives no leak notifications. Edit or re-add it under Configure.",
            )
            return None
        display = kind == RECIPIENT_KIND_DISPLAY
        try:
            recipient_id = str(raw[RECIPIENT_ID])
            name = str(raw[RECIPIENT_NAME])
            notify_service = "" if display else str(raw[RECIPIENT_NOTIFY_SERVICE])
            tracker_entity = "" if display else str(raw[RECIPIENT_TRACKER_ENTITY])
            token = raw[RECIPIENT_TOKEN]
        except KeyError, TypeError, ValueError:
            return None

        if (
            not recipient_id
            or not name
            or (not display and not notify_service.startswith("notify."))
            or (not display and not tracker_entity.startswith("device_tracker."))
            or not isinstance(token, str)
            or not token.strip()
        ):
            return None

        session_token_id = raw.get(RECIPIENT_SESSION_TOKEN_ID)
        session_token_id = (
            session_token_id if isinstance(session_token_id, str) and session_token_id else None
        )
        session_user_id = raw.get(RECIPIENT_SESSION_USER_ID)
        # A pairing is either one login or one user, never both; the narrower
        # login pairing wins if a hand-edited entry carries both keys.
        session_user_id = (
            session_user_id
            if session_token_id is None and isinstance(session_user_id, str) and session_user_id
            else None
        )

        return cls(
            id=recipient_id,
            name=name,
            notify_service=notify_service,
            tracker_entity=tracker_entity,
            critical_enabled=not display and bool(raw.get(RECIPIENT_CRITICAL_ENABLED, True)),
            # Mobile default True (as before); a display defaults to False.
            allow_global_ack=raw.get(RECIPIENT_ALLOW_GLOBAL_ACK, not display) is True,
            trusted_stationary=not display and bool(raw.get(RECIPIENT_TRUSTED_STATIONARY, False)),
            token=token,
            allow_external_reset=raw.get(RECIPIENT_ALLOW_EXTERNAL_RESET) is True,
            session_token_id=session_token_id,
            session_user_id=session_user_id,
            kind=kind,
        )


def recipient_is_home(hass: HomeAssistant, recipient: NotificationRecipient) -> bool:
    """Home authority for every Home-only action.

    A stationary display has no tracker and is always Home (the admin chose it
    for a fixed place); a mobile recipient is Home only while its tracker says so.
    """
    if recipient.is_display:
        return True
    tracker = hass.states.get(recipient.tracker_entity)
    return tracker is not None and tracker.state == "home"


class DispatchState(StrEnum):
    """HA service handoff only; none of these states imply phone receipt."""

    NOT_DISPATCHED = "not_dispatched"
    IN_FLIGHT = "in_flight"
    ACCEPTED = "accepted"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass(slots=True)
class EventAcknowledgement:
    """Acknowledgement state belonging to one leak event ID."""

    globally_acknowledged: bool = False
    globally_acknowledged_by: str | None = None
    globally_acknowledged_at: datetime | None = None
    muted_recipients: set[str] = field(default_factory=set)
    accepted_recipients: dict[str, str] = field(default_factory=dict)
    dispatch_states: dict[str, str] = field(default_factory=dict)
    route_states: dict[str, str] = field(default_factory=dict)

    @property
    def delivered_recipients(self) -> dict[str, str]:
        """Legacy API alias: these entries mean HA accepted, NEVER phone receipt."""
        return self.accepted_recipients

    def to_dict(self) -> dict[str, Any]:
        """Serialize acknowledgement state."""
        return {
            "globally_acknowledged": self.globally_acknowledged,
            "globally_acknowledged_by": self.globally_acknowledged_by,
            "globally_acknowledged_at": (
                self.globally_acknowledged_at.isoformat() if self.globally_acknowledged_at else None
            ),
            "muted_recipients": sorted(self.muted_recipients),
            "accepted_recipients": dict(self.accepted_recipients),
            "dispatch_states": dict(self.dispatch_states),
            "route_states": dict(self.route_states),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> EventAcknowledgement:
        """Restore acknowledgement state."""
        delivered = raw.get("accepted_recipients", raw.get("delivered_recipients", {}))
        statuses = raw.get("dispatch_states", {})
        routes = raw.get("route_states", {})
        return cls(
            globally_acknowledged=raw.get("globally_acknowledged") is True,
            globally_acknowledged_by=(
                raw.get("globally_acknowledged_by")
                if isinstance(raw.get("globally_acknowledged_by"), str)
                else None
            ),
            globally_acknowledged_at=parse_datetime(raw.get("globally_acknowledged_at")),
            muted_recipients=string_set(raw.get("muted_recipients")),
            accepted_recipients={
                key: value
                for key, value in delivered.items()
                if isinstance(key, str) and isinstance(value, str)
            }
            if isinstance(delivered, dict)
            else {},
            dispatch_states={
                key: (
                    DispatchState.INTERRUPTED.value if value == DispatchState.IN_FLIGHT else value
                )
                for key, value in statuses.items()
                if isinstance(key, str)
                and isinstance(value, str)
                and value in {s.value for s in DispatchState}
            }
            if isinstance(statuses, dict)
            else {},
            route_states={
                key: (
                    DispatchState.INTERRUPTED.value if value == DispatchState.IN_FLIGHT else value
                )
                for key, value in routes.items()
                if isinstance(key, str)
                and isinstance(value, str)
                and value in {status.value for status in DispatchState}
            }
            if isinstance(routes, dict)
            else {},
        )


class NotificationController:
    """Send notifications and enforce acknowledgement authorization."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        manager: WaterLeakManager,
        persist_callback: Callable[[], None],
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.manager = manager
        self._persist_callback = persist_callback
        self.recipients: dict[str, NotificationRecipient] = {}
        self.acknowledgements: dict[str, EventAcknowledgement] = {}
        self._unsubs: list[Callable[[], None]] = []
        self._tracker_unsub: Callable[[], None] | None = None
        self._events: dict[str, dict[str, Any]] = {}
        self._dispatch_tasks: dict[tuple[str, str], asyncio.Task] = {}
        self._delivery_tasks: set[asyncio.Task] = set()
        self._closed = False

    async def async_setup(self) -> None:
        """Register event and presence listeners."""
        self._unsubs.append(
            self.hass.bus.async_listen(MOBILE_ACTION_EVENT, self._async_mobile_action)
        )
        self._unsubs.append(
            self.hass.bus.async_listen(EVENT_LEAK_STARTED, self._async_leak_started)
        )
        self._unsubs.append(self.hass.bus.async_listen(EVENT_LEAK_ENDED, self._async_leak_ended))
        self.reload_recipients()
        self._migrate_routes()
        for event_id, kind in self.manager.engine.active_events().items():
            if (
                hasattr(self.manager, "active_events")
                and event_id not in self.manager.active_events()
            ):
                continue
            runtime = self.manager.engine.runtimes[kind]
            self._events[event_id] = {
                "type": kind.value,
                "flow_lph": self.manager.current_flow_lph,
                "started_at": runtime.started_at.isoformat() if runtime.started_at else None,
            }
            self.acknowledgements.setdefault(event_id, EventAcknowledgement())
        external = getattr(self.manager, "external", None)
        if external is not None:
            for event_id, source in external.active_events().items():
                self._events[event_id] = source.public_payload()
                self.acknowledgements.setdefault(event_id, EventAcknowledgement())
        self.acknowledgements = {
            event_id: state
            for event_id, state in self.acknowledgements.items()
            if event_id in self._events
        }

    async def async_unload(self) -> None:
        """Remove listeners and cancel in-flight deliveries before saving."""
        self._closed = True
        tasks = tuple(self._delivery_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._dispatch_tasks.clear()
        self._delivery_tasks.clear()
        if self._tracker_unsub is not None:
            self._tracker_unsub()
            self._tracker_unsub = None
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    @callback
    def reload_recipients(self) -> None:
        """Reload recipient configuration after Options Flow changes."""
        raw_recipients = self.entry.options.get(CONF_NOTIFICATION_RECIPIENTS, [])
        recipients: dict[str, NotificationRecipient] = {}
        if isinstance(raw_recipients, list):
            for raw in raw_recipients:
                if not isinstance(raw, dict):
                    continue
                recipient = NotificationRecipient.from_dict(raw)
                if recipient is not None:
                    recipients[recipient.id] = recipient
        self.recipients = recipients

        if self._tracker_unsub is not None:
            self._tracker_unsub()
            self._tracker_unsub = None

        trackers = sorted({r.tracker_entity for r in recipients.values() if not r.is_display})
        if trackers:
            self._tracker_unsub = async_track_state_change_event(
                self.hass,
                trackers,
                self._async_tracker_changed,
            )

    def restore(self, raw: Any) -> None:
        """Restore acknowledgement state from persistent storage."""
        if not isinstance(raw, dict):
            return
        restored: dict[str, EventAcknowledgement] = {}
        for event_id, state in raw.items():
            if isinstance(event_id, str) and isinstance(state, dict):
                restored[event_id] = EventAcknowledgement.from_dict(state)
        self.acknowledgements = restored

    def to_dict(self) -> dict[str, Any]:
        """Serialize acknowledgement state."""
        return {event_id: state.to_dict() for event_id, state in self.acknowledgements.items()}

    def recipient_for_session(
        self,
        session_token_id: str | None,
        session_user_id: str | None = None,
        session_user: User | None = None,
    ) -> NotificationRecipient | None:
        """Recipient paired with this HA login or, failing that, with its user.

        The caller (websocket.session_recipient) has already verified that the
        login is a normal app/browser login of an active, non-system user and
        that ``session_user_id`` (``session_user``) is the owner of exactly that login.

        Resolution order:
        1. A recipient paired with exactly this login (``session_token_id``) wins.
        2. Otherwise a recipient paired with the login's user (``session_user_id``).
        3. Otherwise the session is not paired.

        A wall display is always Home, and its user pairing covers every login of
        that user, also a remote one. It therefore only resolves for a dedicated
        kiosk user (see kiosk_user_problem): never for the owner or an admin and
        never when another recipient's pairing uses that user or one of its
        logins (in any instance of the integration). Whatever the pairing, a
        display never resolves for a Companion app login or for a login of a user
        that a mobile recipient's pairing uses. Hand-edited options cannot bypass
        this; such a display is logged and treated as not paired. Without
        ``session_user`` a display user pairing never resolves.

        Current options are authoritative: they are parsed directly instead of
        reload_recipients(), so a read-only query never re-subscribes the tracker
        listeners. An ambiguous pairing never authorizes anything.
        """
        if not session_token_id:
            return None
        raw_recipients = self.entry.options.get(CONF_NOTIFICATION_RECIPIENTS, [])
        if not isinstance(raw_recipients, list):
            return None
        parsed = [
            (raw, NotificationRecipient.from_dict(raw))
            for raw in raw_recipients
            if isinstance(raw, dict)
        ]
        recipients = [recipient for _, recipient in parsed if recipient is not None]
        foreign = recipients_of_other_entries(self.hass, self.entry.entry_id)
        by_token = [r for r in recipients if r.session_token_id == session_token_id]
        if by_token:
            if len(by_token) != 1:
                return None
            refusal = self._display_refusal(
                by_token[0], parsed, foreign, session_token_id, None, via_user=False
            )
            return None if refusal else by_token[0]
        if not session_user_id:
            return None
        by_user = [r for r in recipients if r.session_user_id == session_user_id]
        user = (
            session_user
            if session_user is not None and session_user.id == session_user_id
            else None
        )
        # A display that is not a valid kiosk-user pairing is logged and never
        # resolves; checked before the ambiguity rule so that it is always logged.
        refused = [
            candidate
            for candidate in by_user
            if self._display_refusal(
                candidate, parsed, foreign, session_token_id, user, via_user=True
            )
        ]
        if refused or len(by_user) != 1:
            return None
        return by_user[0]

    def _display_refusal(
        self,
        candidate: NotificationRecipient,
        parsed: list[tuple[dict[str, Any], NotificationRecipient | None]],
        foreign: list[dict[str, Any]],
        session_token_id: str,
        user: User | None,
        *,
        via_user: bool,
    ) -> str | None:
        """Why this session may not act as the display ``candidate`` (logged), or None.

        Mobile candidates are never refused here. For a display, every other
        stored entry counts (also ones that do not parse and those of other
        instances): a user pairing needs a dedicated kiosk user, and the login
        itself must be neither a Companion app login nor one of a user that a
        mobile recipient's pairing uses.
        """
        if not candidate.is_display:
            return None
        others = [raw for raw, parsed_one in parsed if parsed_one is not candidate] + foreign
        problem = kiosk_user_problem(self.hass, user, others) if via_user else None
        if problem is None:
            auth = getattr(self.hass, "auth", None)
            token = auth.async_get_refresh_token(session_token_id) if auth is not None else None
            problem = display_login_problem(self.hass, token, others)
        if problem is not None:
            _warn_once(
                f"display_{problem}",
                {RECIPIENT_ID: candidate.id, RECIPIENT_NAME: candidate.name},
                "Wall display %s (%s) "
                + _DISPLAY_REFUSALS[problem]
                + "; it is treated as not paired. Pair a dedicated non-admin kiosk user "
                "nobody else uses, or the kiosk browser's single login.",
            )
        return problem

    async def async_session_mute(self, event_id: str, recipient_id: str) -> str | None:
        """Device-scoped mute from a paired dashboard session; None means accepted.

        Same effect as the notification MUTE action: only this recipient stops
        receiving notifications. Detection, alarm and shutoff are unaffected.
        """
        self.reload_recipients()
        if recipient_id not in self.recipients:
            return "not_paired"
        if self.recipients[recipient_id].is_display:
            # A display receives no notifications, so there is nothing to mute.
            return "not_applicable"
        if event_id not in self.manager.active_events():
            return "event_not_active"
        state = self.acknowledgements.setdefault(event_id, EventAcknowledgement())
        if recipient_id in state.muted_recipients:
            return None
        state.muted_recipients.add(recipient_id)
        self._persist_callback()
        self.hass.bus.async_fire(
            EVENT_ACKNOWLEDGED,
            {
                "config_entry_id": self.entry.entry_id,
                "event_id": event_id,
                "recipient_id": recipient_id,
                "scope": "device",
                "origin": "dashboard",
            },
        )
        return None

    def state_for(self, event_id: str | None) -> EventAcknowledgement | None:
        """Return acknowledgement state for an event."""
        if event_id is None:
            return None
        return self.acknowledgements.get(event_id)

    @notification_writer
    async def _async_leak_started(self, event: Event) -> None:
        if event.data.get("config_entry_id") != self.entry.entry_id:
            return
        event_id = event.data.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            return

        self._events[event_id] = dict(event.data)
        self.acknowledgements.setdefault(event_id, EventAcknowledgement())
        self._persist_callback()
        await self.async_retry_pending()

    @staticmethod
    def _delivery_key(recipient: NotificationRecipient) -> str:
        """Stable route identity: recipient identity and actual notify service."""
        return json.dumps([recipient.id, recipient.notify_service], separators=(",", ":"))

    def _migrate_routes(self) -> None:
        """Migrate known routes; never invent a service for legacy ambiguity."""
        for state in self.acknowledgements.values():
            if state.route_states:
                continue
            for recipient_id, accepted in tuple(state.accepted_recipients.items()):
                try:
                    # Round 1/2 stored repr(sorted(asdict(recipient).items())).
                    old = dict(ast.literal_eval(accepted))
                    key = json.dumps([recipient_id, old["notify_service"]], separators=(",", ":"))
                except ValueError, SyntaxError, TypeError, KeyError:
                    key = accepted
                state.accepted_recipients[recipient_id] = key
                state.route_states[key] = DispatchState.ACCEPTED.value
            for recipient_id, status in state.dispatch_states.items():
                if status == DispatchState.INTERRUPTED:
                    # Round 2 did not persist the service of an interrupted call.
                    # Keep that missing provenance explicit, not bound to a new
                    # configured service that may never have been called.
                    unknown_route = json.dumps([recipient_id, None], separators=(",", ":"))
                    state.route_states.setdefault(unknown_route, status)

    def _eligible(self, event_id: str, recipient: NotificationRecipient) -> bool:
        active_events = getattr(self.manager, "active_events", None) or getattr(
            self.manager.engine, "active_events", None
        )
        if active_events is not None and event_id not in active_events():
            return False
        state = self.acknowledgements.get(event_id)
        return (
            not self._closed
            and not recipient.is_display
            and event_id in self._events
            and self.recipients.get(recipient.id) == recipient
            and state is not None
            and not state.globally_acknowledged
            and recipient.id not in state.muted_recipients
        )

    async def async_retry_pending(self) -> None:
        """Schedule isolated handoffs; never timeout/restart an ongoing service call."""
        if self._closed:
            return
        for event_id, payload in tuple(self._events.items()):
            for recipient in tuple(self.recipients.values()):
                if recipient.is_display:
                    continue  # never part of notification dispatch
                route = self._delivery_key(recipient)
                identity = (event_id, route)
                if identity in self._dispatch_tasks or not self._eligible(event_id, recipient):
                    continue
                state = self.acknowledgements[event_id]
                if state.route_states.get(route) == DispatchState.ACCEPTED or (
                    state.accepted_recipients.get(recipient.id) == route
                ):
                    continue
                if state.route_states.get(route) == DispatchState.INTERRUPTED:
                    # A cancelled handoff may already have pushed. Do not blindly
                    # resend after reload; retain its ambiguous status for diagnosis.
                    continue
                task = asyncio.create_task(self._dispatch(event_id, recipient, dict(payload)))
                self._dispatch_tasks[identity] = task
                self._delivery_tasks.add(task)
        # Fast local services complete without making slower recipients a barrier.
        await asyncio.sleep(0)

    async def _async_metadata(self, mutation) -> None:
        async def apply():
            mutation()

        writer = getattr(self.manager, "async_notification_action", None)
        if writer is None:
            mutation()
        else:
            # Track the short writer acquisition with HA, while the possibly
            # slow notify service remains an isolated dispatch worker.
            task = self.hass.async_create_task(writer(apply))
            await task

    async def _dispatch(self, event_id, recipient, payload) -> None:
        route = self._delivery_key(recipient)
        identity = (event_id, route)
        state = self.acknowledgements.get(event_id)
        if state is None:
            # The ended listener may have run after scheduling but before this
            # worker's first turn. No state, no handoff, no orphaned task entry.
            self._dispatch_tasks.pop(identity, None)
            self._delivery_tasks.discard(asyncio.current_task())
            return

        async def set_status(status: DispatchState) -> None:
            def mutate():
                if self.acknowledgements.get(event_id) is not state:
                    return
                state.route_states[route] = status.value
                if self.recipients.get(recipient.id) == recipient:
                    state.dispatch_states[recipient.id] = status.value

            await self._async_metadata(mutate)

        await set_status(DispatchState.NOT_DISPATCHED)

        async def handed_off():
            await set_status(DispatchState.IN_FLIGHT)
            self._persist_callback()

        try:
            sent = await self._async_send_event_notification(
                recipient,
                event_id,
                str(payload.get("type", "unknown")),
                {**payload, "flow_lph": self.manager.current_flow_lph},
                returning_home=bool(payload.get("returning_home")),
                authorize=lambda: self._eligible(event_id, recipient),
                on_dispatch=handed_off,
            )
            if sent is not False and self.acknowledgements.get(event_id) is state:
                await self._async_metadata(
                    lambda: (
                        state.accepted_recipients.update({recipient.id: route})
                        if self.acknowledgements.get(event_id) is state
                        else None
                    )
                )
                await set_status(DispatchState.ACCEPTED)
        except asyncio.CancelledError:
            if state.route_states.get(route) == DispatchState.IN_FLIGHT:
                # Event-end holds the writer while cancelling its workers. Queue
                # cleanup instead of awaiting that same writer in cancellation.
                def interrupted():
                    if self.acknowledgements.get(event_id) is state:
                        state.route_states[route] = DispatchState.INTERRUPTED.value
                        state.dispatch_states[recipient.id] = DispatchState.INTERRUPTED.value

                self._defer_mutation(interrupted)
            raise
        except Exception:
            await set_status(DispatchState.FAILED)
            _LOGGER.exception("HA notify dispatch to %s failed; will retry", recipient.name)
        finally:
            self._dispatch_tasks.pop(identity, None)
            self._delivery_tasks.discard(asyncio.current_task())
            self._persist_callback()

    @notification_writer
    async def _async_leak_ended(self, event: Event) -> None:
        if event.data.get("config_entry_id") != self.entry.entry_id:
            return
        event_id = event.data.get("event_id")
        if isinstance(event_id, str):
            self._events.pop(event_id, None)
            self.acknowledgements.pop(event_id, None)
            tasks = [
                task
                for (pending_event, _route), task in self._dispatch_tasks.items()
                if pending_event == event_id
            ]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            # A worker cancelled before its first turn cannot execute finally.
            for identity in tuple(self._dispatch_tasks):
                if identity[0] == event_id:
                    self._delivery_tasks.discard(self._dispatch_tasks.pop(identity))
            self._persist_callback()

    async def _async_mobile_action(self, event: Event) -> None:
        writer = getattr(self.manager, "async_mobile_notification_action", None) or getattr(
            self.manager, "async_notification_action", None
        )
        if writer is not None:
            await writer(lambda: self._async_handle_mobile_action(event))
        else:
            await self._async_handle_mobile_action(event)

    def _raw_kind(self, recipient_id: Any) -> str | None:
        """Stored kind of a recipient (mobile if missing), straight from the options."""
        raws = self.entry.options.get(CONF_NOTIFICATION_RECIPIENTS, [])
        if not isinstance(raws, list):
            return None
        for raw in raws:
            if isinstance(raw, dict) and raw.get(RECIPIENT_ID) == recipient_id:
                return raw.get(RECIPIENT_KIND, RECIPIENT_KIND_MOBILE)
        return None

    async def _async_handle_mobile_action(self, event: Event) -> None:
        action = event.data.get("action")
        if not isinstance(action, str) or not action.startswith(f"{ACTION_PREFIX}|"):
            return

        if action.startswith(f"{ACTION_PREFIX}|{ACTION_EXTERNAL_RESET}|"):
            try:
                encoded = action.split("|", 2)[2]
                if len(encoded) > 4096:
                    return
                payload = json.loads(base64.urlsafe_b64decode(encoded.encode()))
            except ValueError, TypeError, UnicodeError:
                return
            if isinstance(payload, dict):
                if self._raw_kind(payload.get("recipient_id")) == RECIPIENT_KIND_DISPLAY:
                    # Displays never receive notifications, hence never notification actions.
                    self._fire_rejected(
                        payload.get("event_id"), payload.get("recipient_id"), "display_recipient"
                    )
                    return
                success = await self.manager.async_external_reset(payload)
                if not success:
                    self._fire_rejected(
                        payload.get("event_id"),
                        payload.get("recipient_id"),
                        "external_reset_rejected",
                    )
            return

        parsed = self._parse_action(action)
        if parsed is None:
            return
        action_kind, entry_id, event_id, recipient_id, token = parsed
        if entry_id != self.entry.entry_id:
            return

        recipient = self.recipients.get(recipient_id)
        if recipient is None or recipient.token != token:
            self._fire_rejected(event_id, recipient_id, "invalid_recipient_or_token")
            return
        if recipient.is_display:
            # Displays never receive notifications, hence never notification actions.
            self._fire_rejected(event_id, recipient_id, "display_recipient")
            return

        snapshot = self.manager.engine.snapshot(self.manager.current_total_l)
        active_ids = {
            runtime.event_id
            for runtime in getattr(self.manager.engine, "runtimes", {}).values()
            if runtime.phase.value == "active"
        }
        all_events = getattr(self.manager, "active_events", None)
        if all_events is not None:
            active_ids.update(all_events())
        if snapshot.active_event_id != event_id and event_id not in active_ids:
            self._fire_rejected(event_id, recipient_id, "event_not_active")
            return

        state = self.acknowledgements.setdefault(event_id, EventAcknowledgement())

        if action_kind == ACTION_MUTE:
            if recipient_id in state.muted_recipients:
                return
            state.muted_recipients.add(recipient_id)
            self._persist_callback()
            self.hass.bus.async_fire(
                EVENT_ACKNOWLEDGED,
                {
                    "config_entry_id": self.entry.entry_id,
                    "event_id": event_id,
                    "recipient_id": recipient_id,
                    "scope": "device",
                },
            )
            return

        if action_kind != ACTION_ACK_ALL:
            return

        if state.globally_acknowledged:
            return

        if not recipient.allow_global_ack:
            self._fire_rejected(event_id, recipient_id, "global_ack_not_allowed")
            return

        tracker = self.hass.states.get(recipient.tracker_entity)
        if tracker is None or tracker.state != "home":
            self._fire_rejected(event_id, recipient_id, "device_not_home")
            await self._async_send_feedback(
                recipient,
                "global_ack_rejected_title",
                "global_ack_rejected_message",
            )
            return

        native_ack = getattr(self.manager, "async_acknowledge_event", None)
        if native_ack is not None:
            await native_ack(event_id, recipient_id, token)
            return

        state.globally_acknowledged = True
        state.globally_acknowledged_by = recipient_id
        state.globally_acknowledged_at = dt_util.utcnow()
        self._persist_callback()
        self.hass.bus.async_fire(
            EVENT_ACKNOWLEDGED,
            {
                "config_entry_id": self.entry.entry_id,
                "event_id": event_id,
                "recipient_id": recipient_id,
                "scope": "global",
                "trusted_stationary": recipient.trusted_stationary,
                "kind": recipient.kind,
            },
        )

    @notification_writer
    async def _async_tracker_changed(self, event: Event) -> None:
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if old_state is None or new_state is None:
            return
        if old_state.state == "home" or new_state.state != "home":
            return

        tracker_entity = event.data.get("entity_id")
        if not isinstance(tracker_entity, str):
            return

        events = (
            self.manager.active_events()
            if hasattr(self.manager, "active_events")
            else self.manager.engine.active_events()
        )
        for event_id, kind in events.items():
            state = self.acknowledgements.get(event_id)
            if state is None or state.globally_acknowledged:
                continue
            for recipient in tuple(self.recipients.values()):
                if recipient.is_display or recipient.tracker_entity != tracker_entity:
                    continue
                state.muted_recipients.discard(recipient.id)
                route = self._delivery_key(recipient)
                state.accepted_recipients.pop(recipient.id, None)
                if state.route_states.get(route) == DispatchState.ACCEPTED:
                    state.route_states.pop(route, None)
                self._persist_callback()
                if not isinstance(kind, DetectorKind):
                    source = self.manager.external.active_events()[event_id]
                    payload = source.public_payload()
                else:
                    runtime = self.manager.engine.runtimes[kind]
                    payload = {
                        "type": kind.value,
                        "flow_lph": self.manager.current_flow_lph,
                        "volume_l": runtime.plausible_volume_l,
                        "started_at": runtime.started_at.isoformat()
                        if runtime.started_at
                        else None,
                    }
                self._events[event_id] = {**payload, "returning_home": True}
        await self.async_retry_pending()

    async def _async_send_event_notification(
        self,
        recipient: NotificationRecipient,
        event_id: str,
        detector_type: str,
        payload: dict[str, Any],
        *,
        returning_home: bool,
        authorize: Callable[[], bool] | None = None,
        on_dispatch: Callable[[], None] | None = None,
    ) -> bool:
        if recipient.is_display:
            return False  # defense in depth: a display has no notify service
        domain, service = recipient.notify_service.split(".", 1)
        if not self.hass.services.has_service(domain, service):
            _LOGGER.warning(
                "Notification service %s for recipient %s is unavailable",
                recipient.notify_service,
                recipient.name,
            )
            return False

        strings = await self._async_common_translations()
        is_burst = detector_type == DetectorKind.BURST_LEAK.value
        detector = self._translate(
            strings,
            f"detector_{detector_type}",
            detector_type.replace("_", " ").title(),
        )
        if detector_type == "external_leak":
            detector = f"{detector}: {payload.get('source_name', payload.get('source_entity', ''))}"
        title = (
            self._translate(
                strings,
                "notification_title_returning_home",
                "Water leak still active",
            )
            if returning_home
            else self._translate(
                strings,
                "notification_title",
                "Water Leak Guard: {detector}",
                detector=detector,
            )
        )

        message_parts: list[str] = []
        if returning_home:
            message_parts.append(
                self._translate(
                    strings,
                    "notification_returned_home",
                    "You returned home while this event is still active.",
                )
            )
        flow = payload.get("flow_lph")
        if isinstance(flow, (int, float)):
            message_parts.append(
                self._translate(
                    strings,
                    "notification_current_flow",
                    "Current flow: {flow} L/h.",
                    flow=f"{float(flow):.1f}",
                )
            )
        volume = payload.get("volume_l")
        if isinstance(volume, (int, float)):
            message_parts.append(
                self._translate(
                    strings,
                    "notification_volume",
                    "Volume since detection started: {volume} L.",
                    volume=f"{float(volume):.1f}",
                )
            )
        if not message_parts:
            message_parts.append(
                self._translate(
                    strings,
                    "notification_event_active",
                    "A water event is active.",
                )
            )

        notification_data: dict[str, Any] = {
            "tag": f"wld_{self.entry.entry_id}_{event_id}",
            "wld_event_id": event_id,
            "wld_recipient_id": recipient.id,
            "actions": [
                {
                    "action": self._action_id(ACTION_MUTE, event_id, recipient),
                    "title": self._translate(
                        strings,
                        "action_mute_device",
                        "Mute for this device",
                    ),
                }
            ],
        }

        tracker = self.hass.states.get(recipient.tracker_entity)
        device_is_home = tracker is not None and tracker.state == "home"
        if recipient.allow_global_ack and device_is_home:
            notification_data["actions"].append(
                {
                    "action": self._action_id(ACTION_ACK_ALL, event_id, recipient),
                    "title": self._translate(
                        strings,
                        "action_ack_all",
                        "Acknowledge for everyone",
                    ),
                }
            )

        if detector_type == "external_leak" and recipient.allow_external_reset and device_is_home:
            reset_action = self.external_reset_action(event_id, recipient)
            if reset_action is not None:
                notification_data["actions"].append(
                    {
                        "action": reset_action,
                        "title": self._translate(
                            strings, "action_external_reset", "Reset external alarm"
                        ),
                    }
                )

        if is_burst and recipient.critical_enabled:
            notification_data.update(
                {
                    "ttl": 0,
                    "priority": "high",
                    "channel": "alarm_stream",
                    "push": {"interruption-level": "critical"},
                }
            )

        if authorize is not None and not authorize():
            return False
        if on_dispatch is not None:
            result = on_dispatch()
            if inspect.isawaitable(result):
                await result
        if authorize is not None and not authorize():
            return False
        await self.hass.services.async_call(
            domain,
            service,
            {
                "title": title,
                "message": " ".join(message_parts),
                "data": notification_data,
            },
            blocking=True,
        )
        return True

    async def _async_send_feedback(
        self,
        recipient: NotificationRecipient,
        title_key: str,
        message_key: str,
    ) -> None:
        if recipient.is_display:
            return
        domain, service = recipient.notify_service.split(".", 1)
        if not self.hass.services.has_service(domain, service):
            return
        strings = await self._async_common_translations()
        await self.hass.services.async_call(
            domain,
            service,
            {
                "title": self._translate(
                    strings,
                    title_key,
                    "Global acknowledgement rejected",
                ),
                "message": self._translate(
                    strings,
                    message_key,
                    (
                        "This device is not currently in the Home zone. "
                        "The alarm can only be muted for this device."
                    ),
                ),
            },
            blocking=False,
        )

    async def _async_common_translations(self) -> dict[str, str]:
        """Load notification strings in the configured Home Assistant language."""
        translations = await translation.async_get_translations(
            self.hass,
            self.hass.config.language,
            "common",
            [DOMAIN],
        )
        prefix = f"component.{DOMAIN}.common."
        return {
            key.removeprefix(prefix): value
            for key, value in translations.items()
            if key.startswith(prefix)
        }

    @staticmethod
    def _translate(
        strings: dict[str, str],
        key: str,
        fallback: str,
        **placeholders: str,
    ) -> str:
        """Translate a runtime notification string with an English fallback."""
        value = strings.get(key, fallback)
        try:
            return value.format(**placeholders)
        except KeyError:
            return fallback.format(**placeholders)

    def _action_id(
        self,
        action_kind: str,
        event_id: str,
        recipient: NotificationRecipient,
    ) -> str:
        return "|".join(
            (
                ACTION_PREFIX,
                action_kind,
                self.entry.entry_id,
                event_id,
                recipient.id,
                recipient.token,
            )
        )

    def external_reset_action(self, event_id: str, recipient: NotificationRecipient) -> str | None:
        external = getattr(self.manager, "external", None)
        source = external.active_events().get(event_id) if external is not None else None
        if source is None:
            return None
        payload = {
            "action_kind": ACTION_EXTERNAL_RESET,
            "config_entry_id": self.entry.entry_id,
            "source_id": source.source_id,
            "source_generation": source.identity.generation,
            "event_id": event_id,
            "recipient_id": recipient.id,
            "recipient_token": recipient.token,
            "reset_nonce": source.reset_nonce,
        }
        encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        return f"{ACTION_PREFIX}|{ACTION_EXTERNAL_RESET}|{encoded.decode()}"

    def _defer_mutation(self, mutation) -> None:
        writer = getattr(self.manager, "defer_notification_mutation", None)
        if writer is None:
            mutation()
        else:
            writer(mutation)

    @staticmethod
    def _parse_action(
        action: str,
    ) -> tuple[str, str, str, str, str] | None:
        parts = action.split("|")
        if len(parts) != 6 or parts[0] != ACTION_PREFIX:
            return None
        _, action_kind, entry_id, event_id, recipient_id, token = parts
        if action_kind not in (ACTION_MUTE, ACTION_ACK_ALL):
            return None
        return action_kind, entry_id, event_id, recipient_id, token

    def _fire_rejected(
        self,
        event_id: str,
        recipient_id: str,
        reason: str,
    ) -> None:
        self.hass.bus.async_fire(
            EVENT_ACK_REJECTED,
            {
                "config_entry_id": self.entry.entry_id,
                "event_id": event_id,
                "recipient_id": recipient_id,
                "reason": reason,
            },
        )
