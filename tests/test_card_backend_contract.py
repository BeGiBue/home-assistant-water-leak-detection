"""Dashboard card contract: device pairing and server-side authorization.

Rights belong to the paired device (HA login), not to the user: one user's
iPad at home may acknowledge globally while the same user's phone away may only
mute itself. All tests use the real manager, Store, event bus and HA auth.
"""

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest
from homeassistant.auth import auth_manager_from_config
from homeassistant.auth.models import TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN
from test_ack_duration_diagnostics import ack_manager
from test_config_runtime import options_flow
from test_external_reset_runtime import configured
from test_notification_runtime import recipient

from custom_components.water_leak_detection import async_setup
from custom_components.water_leak_detection.const import (
    CONF_NOTIFICATION_RECIPIENTS,
    DetectorKind,
    DetectorPhase,
)
from custom_components.water_leak_detection.external_leaks import ExternalPhase
from custom_components.water_leak_detection.notifications import NotificationRecipient
from custom_components.water_leak_detection.websocket import (
    WS_ACKNOWLEDGE,
    WS_EXTERNAL_RESET,
    WS_MUTE,
    WS_SESSION,
    handle_acknowledge,
    handle_external_reset,
    handle_mute,
    handle_session,
)

CLIENT = "https://home-assistant.io/iOS"


class Connection:
    """Minimal websocket connection: authenticated user plus its login id."""

    def __init__(self, user, token_id):
        self.user = user
        self.refresh_token_id = token_id
        self.results = []
        self.errors = []

    def send_result(self, msg_id, result=None):
        self.results.append(result)

    def send_error(self, msg_id, code, message, **_):
        self.errors.append(code)


async def logins(hass, *names):
    """One HA user with one normal login per device name."""
    hass.auth = await auth_manager_from_config(hass, [], [])
    user = await hass.auth.async_create_user("Bea")
    tokens = {}
    for name in names:
        tokens[name] = await hass.auth.async_create_refresh_token(
            user, CLIENT, client_name=name
        )
    return user, tokens


def pair(hass, entry, pairs, users=None):
    """Store recipient -> login / user pairing like the options flow does."""
    users = users or {}
    raws = []
    for raw in entry.options[CONF_NOTIFICATION_RECIPIENTS]:
        raw = dict(raw)
        raw.pop("session_token_id", None)
        raw.pop("session_user_id", None)
        if raw["id"] in pairs:
            raw["session_token_id"] = pairs[raw["id"]]
        elif raw["id"] in users:
            raw["session_user_id"] = users[raw["id"]]
        raws.append(raw)
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_NOTIFICATION_RECIPIENTS: raws}
    )


async def call(handler, hass, connection, **msg):
    """Exactly one reply per command: either a result or an error code."""
    connection.results.clear()
    connection.errors.clear()
    await handler(hass, connection, {"id": 1, **msg})
    assert len(connection.results) + len(connection.errors) == 1
    return (connection.results or [None])[-1], (connection.errors or [None])[-1]


def assert_safety(manager):
    assert manager.alarm_active and manager.shutoff_request
    assert manager.engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.ACTIVE


async def test_commands_are_registered(runtime_hass):
    await async_setup(runtime_hass, {})
    handlers = runtime_hass.data["websocket_api"]
    for command in (WS_SESSION, WS_MUTE, WS_ACKNOWLEDGE, WS_EXTERNAL_RESET):
        assert command in handlers


async def test_unpaired_login_is_view_only(runtime_hass, runtime_entry, measurement_clock):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    user, tokens = await logins(runtime_hass, "browser")
    conn = Connection(user, tokens["browser"].id)
    assert (await call(handle_session, runtime_hass, conn))[0] == {"paired": False}
    for handler in (handle_mute, handle_acknowledge):
        assert (await call(handler, runtime_hass, conn, event_id=event_id))[1] == "not_paired"
    state = manager.notifications.state_for(event_id)
    assert not state.muted_recipients and not state.globally_acknowledged
    assert_safety(manager)


async def test_mute_is_device_scoped_and_allowed_away(
    runtime_hass, runtime_entry, measurement_clock
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    user, tokens = await logins(runtime_hass, "phone")
    pair(runtime_hass, runtime_entry, {"phone": tokens["phone"].id})
    runtime_hass.states.async_set("device_tracker.phone", "not_home")
    result, error = await call(
        handle_mute, runtime_hass, Connection(user, tokens["phone"].id), event_id=event_id
    )
    assert error is None and result == {"muted": True, "scope": "device"}
    state = manager.notifications.state_for(event_id)
    assert state.muted_recipients == {"phone"}
    assert not state.globally_acknowledged
    assert_safety(manager)


@pytest.mark.parametrize("tracker", ["home", "not_home", "unavailable", "unknown"])
async def test_global_ack_requires_home_at_execution(
    runtime_hass, runtime_entry, measurement_clock, tracker
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    user, tokens = await logins(runtime_hass, "phone")
    pair(runtime_hass, runtime_entry, {"phone": tokens["phone"].id})
    runtime_hass.states.async_set("device_tracker.phone", tracker)
    result, error = await call(
        handle_acknowledge, runtime_hass, Connection(user, tokens["phone"].id), event_id=event_id
    )
    acknowledged = manager.notifications.state_for(event_id).globally_acknowledged
    if tracker == "home":
        assert error is None and result == {"acknowledged": True, "scope": "global"}
        assert acknowledged
        disk = json.loads(Path(manager._store.path).read_text())["data"]
        assert disk["acknowledgements"][event_id]["globally_acknowledged"]
    else:
        assert error == "not_home" and not acknowledged
    # Acknowledgement never ends detection, the alarm or the shutoff request.
    assert_safety(manager)


async def test_same_user_ipad_home_has_more_rights_than_phone_away(
    runtime_hass, runtime_entry, measurement_clock
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    ipad = {**recipient("ipad"), "trusted_stationary": True}
    runtime_hass.config_entries.async_update_entry(
        runtime_entry,
        options={
            **runtime_entry.options,
            CONF_NOTIFICATION_RECIPIENTS: [
                *runtime_entry.options[CONF_NOTIFICATION_RECIPIENTS],
                ipad,
            ],
        },
    )
    user, tokens = await logins(runtime_hass, "phone", "ipad")
    pair(runtime_hass, runtime_entry, {"phone": tokens["phone"].id, "ipad": tokens["ipad"].id})
    runtime_hass.states.async_set("device_tracker.phone", "not_home")
    runtime_hass.states.async_set("device_tracker.ipad", "home")
    phone, ipad_conn = Connection(user, tokens["phone"].id), Connection(user, tokens["ipad"].id)

    phone_session = (await call(handle_session, runtime_hass, phone))[0]
    ipad_session = (await call(handle_session, runtime_hass, ipad_conn))[0]
    assert phone_session["home"] is False
    assert ipad_session["home"] is True
    # The paired recipient's own tracker, so the card can refresh on its changes.
    assert phone_session["tracker_entity"] == "device_tracker.phone"
    assert ipad_session["tracker_entity"] == "device_tracker.ipad"
    assert (await call(handle_acknowledge, runtime_hass, phone, event_id=event_id))[1] == "not_home"
    assert not manager.notifications.state_for(event_id).globally_acknowledged
    assert (await call(handle_mute, runtime_hass, phone, event_id=event_id))[1] is None
    assert (await call(handle_acknowledge, runtime_hass, ipad_conn, event_id=event_id))[1] is None
    state = manager.notifications.state_for(event_id)
    assert state.globally_acknowledged and state.globally_acknowledged_by == "ipad"
    assert state.muted_recipients == {"phone"}
    assert_safety(manager)


async def test_permission_wrong_event_and_foreign_logins_are_rejected(
    runtime_hass, runtime_entry, measurement_clock
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    user, tokens = await logins(runtime_hass, "phone")
    other = await runtime_hass.auth.async_create_user("Guest")
    lla = await runtime_hass.auth.async_create_refresh_token(
        user, client_name="script", token_type=TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN
    )
    pair(runtime_hass, runtime_entry, {"phone": tokens["phone"].id})
    conn = Connection(user, tokens["phone"].id)

    assert (await call(handle_acknowledge, runtime_hass, conn, event_id="old"))[1] == (
        "event_not_active"
    )
    raw = {**runtime_entry.options[CONF_NOTIFICATION_RECIPIENTS][0], "allow_global_ack": False}
    runtime_hass.config_entries.async_update_entry(
        runtime_entry, options={**runtime_entry.options, CONF_NOTIFICATION_RECIPIENTS: [raw]}
    )
    assert (await call(handle_acknowledge, runtime_hass, conn, event_id=event_id))[1] == (
        "not_allowed"
    )
    # The login id alone is not enough: it must belong to the connection's user.
    stolen = Connection(other, tokens["phone"].id)
    assert (await call(handle_mute, runtime_hass, stolen, event_id=event_id))[1] == "not_paired"
    # Long-lived access tokens (scripts) can never act as a paired device.
    pair(runtime_hass, runtime_entry, {"phone": lla.id})
    script = Connection(user, lla.id)
    assert (await call(handle_mute, runtime_hass, script, event_id=event_id))[1] == "not_paired"
    # Deleting the login in HA removes the pairing's effect immediately.
    pair(runtime_hass, runtime_entry, {"phone": tokens["phone"].id})
    runtime_hass.auth.async_remove_refresh_token(tokens["phone"])
    assert (await call(handle_mute, runtime_hass, conn, event_id=event_id))[1] == "not_paired"
    state = manager.notifications.state_for(event_id)
    assert not state.muted_recipients and not state.globally_acknowledged
    assert_safety(manager)


@pytest.mark.parametrize("handler", [handle_mute, handle_acknowledge])
async def test_pairing_changed_while_waiting_for_writer_rejects(
    runtime_hass, runtime_entry, measurement_clock, handler
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    user, tokens = await logins(runtime_hass, "phone", "other")
    pair(runtime_hass, runtime_entry, {"phone": tokens["phone"].id})
    conn = Connection(user, tokens["phone"].id)
    # Hold the manager's writer: the command must wait and re-check the pairing.
    async with manager._state_lock:
        task = asyncio.create_task(handler(runtime_hass, conn, {"id": 1, "event_id": event_id}))
        for _ in range(5):
            await asyncio.sleep(0)
        assert not conn.results and not conn.errors
        pair(runtime_hass, runtime_entry, {"phone": tokens["other"].id})
    await task
    assert conn.errors == ["not_paired"] and not conn.results
    state = manager.notifications.state_for(event_id)
    assert not state.muted_recipients and not state.globally_acknowledged
    assert_safety(manager)


async def test_session_query_does_not_resubscribe_trackers(
    runtime_hass, runtime_entry, measurement_clock
):
    _, manager, _, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    user, tokens = await logins(runtime_hass, "phone")
    pair(runtime_hass, runtime_entry, {"phone": tokens["phone"].id})
    subscription = manager.notifications._tracker_unsub
    result, _ = await call(handle_session, runtime_hass, Connection(user, tokens["phone"].id))
    assert result["paired"]
    assert manager.notifications._tracker_unsub is subscription


async def test_responses_never_contain_secrets(runtime_hass, runtime_entry, measurement_clock):
    await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    user, tokens = await logins(runtime_hass, "phone")
    pair(runtime_hass, runtime_entry, {"phone": tokens["phone"].id})
    result, _ = await call(handle_session, runtime_hass, Connection(user, tokens["phone"].id))
    text = json.dumps(result)
    assert result["paired"] and result["recipient_id"] == "phone"
    # The tracker entity id is not a secret and is allowed in the answer.
    assert result["tracker_entity"] == "device_tracker.phone"
    assert "token_phone" not in text and tokens["phone"].id not in text
    assert tokens["phone"].token not in text


@pytest.mark.parametrize("tracker", ["home", "not_home"])
async def test_external_reset_uses_native_validator(
    runtime_hass, runtime_entry, measurement_clock, tracker
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    source = manager.external.sources["a"]
    user, tokens = await logins(runtime_hass, "phone")
    pair(runtime_hass, runtime_entry, {"phone": tokens["phone"].id})
    runtime_hass.states.async_set("device_tracker.phone", tracker)
    conn = Connection(user, tokens["phone"].id)
    binding = {
        "event_id": source.event_id,
        "source_id": "a",
        "source_generation": source.identity.generation,
    }
    wrong = {**binding, "source_generation": "old"}
    assert (await call(handle_external_reset, runtime_hass, conn, **wrong))[1] == (
        "event_not_active"
    )
    result, error = await call(handle_external_reset, runtime_hass, conn, **binding)
    if tracker == "home":
        assert error is None and result == {"reset": True}
        assert manager.external.sources["a"].phase is ExternalPhase.RESET_WAITING_FOR_OFF
    else:
        assert error == "not_home"
        assert manager.external.sources["a"].phase is ExternalPhase.ACTIVE
        assert manager.alarm_active and manager.shutoff_request


async def test_hydraulic_alarm_cannot_be_cleared_through_external_reset(
    runtime_hass, runtime_entry, measurement_clock
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    user, tokens = await logins(runtime_hass, "phone")
    raw = {**runtime_entry.options[CONF_NOTIFICATION_RECIPIENTS][0], "allow_external_reset": True}
    runtime_hass.config_entries.async_update_entry(
        runtime_entry, options={**runtime_entry.options, CONF_NOTIFICATION_RECIPIENTS: [raw]}
    )
    pair(runtime_hass, runtime_entry, {"phone": tokens["phone"].id})
    result, error = await call(
        handle_external_reset,
        runtime_hass,
        Connection(user, tokens["phone"].id),
        event_id=event_id,
        source_id="a",
        source_generation="g",
    )
    assert error == "event_not_active"
    assert_safety(manager)


ALARM_FIELDS = ("name", "notify_service", "tracker_entity", "critical_enabled",
                "allow_global_ack", "trusted_stationary")


def recipients_by_id(entry):
    return {raw["id"]: dict(raw) for raw in entry.options[CONF_NOTIFICATION_RECIPIENTS]}


def alarm_settings(raw):
    """Everything that decides who is alerted and how, without the pairing."""
    parsed = NotificationRecipient.from_dict(raw)
    return replace(parsed, session_token_id=None, session_user_id=None)


async def edit(flow, recipient_id, raw, **extra):
    flow._editing_recipient_id = recipient_id
    form = await flow.async_step_edit_recipient_details()
    values = form["data_schema"]({**{key: raw[key] for key in ALARM_FIELDS}, **extra})
    return form, await flow.async_step_edit_recipient_details(values)


async def test_pairing_is_part_of_the_recipient_entry_and_keeps_alarm_settings(
    runtime_hass, runtime_entry, measurement_clock
):
    await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    ipad = {**recipient("ipad"), "critical_enabled": False, "trusted_stationary": True}
    runtime_hass.config_entries.async_update_entry(
        runtime_entry,
        options={
            **runtime_entry.options,
            CONF_NOTIFICATION_RECIPIENTS: [
                *runtime_entry.options[CONF_NOTIFICATION_RECIPIENTS],
                ipad,
            ],
        },
    )
    _, tokens = await logins(runtime_hass, "phone", "ipad")
    before = recipients_by_id(runtime_entry)
    flow = options_flow(runtime_hass, runtime_entry)

    # One entry per recipient: no separate pairing menu anymore.
    menu = await flow.async_step_notifications()
    assert "pair_device" not in menu["menu_options"]

    # Pair the phone inside its recipient form.
    form, result = await edit(
        flow, "phone", before["phone"], session_pairing=f"token:{tokens['phone'].id}"
    )
    offered = [o["value"] for o in form["data_schema"].schema["session_pairing"].config["options"]]
    assert f"token:{tokens['phone'].id}" in offered and f"token:{tokens['ipad'].id}" in offered
    assert result["step_id"] == "notifications"
    after = recipients_by_id(runtime_entry)
    assert after["phone"]["session_token_id"] == tokens["phone"].id
    assert after["phone"]["token"] == before["phone"]["token"]
    assert alarm_settings(after["phone"]) == alarm_settings(before["phone"])
    assert after["ipad"] == before["ipad"]

    # Saving the form again without touching the pairing keeps everything.
    _, result = await edit(flow, "phone", after["phone"])
    assert recipients_by_id(runtime_entry) == after

    # A login belongs to at most one recipient; nothing is saved on error.
    _, duplicate = await edit(
        flow, "ipad", after["ipad"], session_pairing=f"token:{tokens['phone'].id}"
    )
    assert duplicate["errors"] == {"base": "session_already_paired"}
    assert recipients_by_id(runtime_entry) == after

    # Removing the pairing restores the original alarm configuration.
    _, result = await edit(flow, "phone", after["phone"], session_pairing="__none__")
    final = recipients_by_id(runtime_entry)
    assert "session_token_id" not in final["phone"]
    assert alarm_settings(final["phone"]) == alarm_settings(before["phone"])
    assert final["ipad"] == before["ipad"]


async def test_new_recipient_can_be_paired_while_adding(
    runtime_hass, runtime_entry, measurement_clock
):
    await ack_manager(runtime_hass, runtime_entry, measurement_clock)

    async def notify(call):
        pass

    runtime_hass.services.async_register("notify", "mobile_app_tablet", notify)
    _, tokens = await logins(runtime_hass, "tablet")
    before = recipients_by_id(runtime_entry)
    flow = options_flow(runtime_hass, runtime_entry)
    form = await flow.async_step_add_recipient()
    values = form["data_schema"](
        {
            "name": "Tablet",
            "notify_service": "notify.mobile_app_tablet",
            "tracker_entity": "device_tracker.tablet",
            "critical_enabled": False,
            "allow_global_ack": False,
            "trusted_stationary": False,
            "session_pairing": f"token:{tokens['tablet'].id}",
        }
    )
    result = await flow.async_step_add_recipient(values)
    assert result["step_id"] == "notifications"
    after = recipients_by_id(runtime_entry)
    added = next(raw for key, raw in after.items() if key not in before)
    assert added["session_token_id"] == tokens["tablet"].id
    assert added["critical_enabled"] is False and added["allow_global_ack"] is False
    assert {key: after[key] for key in before} == before


# --------------------------------------------------------------------------
# User pairing (default) next to login pairing: "one device = always one user".


def add_recipients(hass, entry, *names, **overrides):
    raws = [*entry.options[CONF_NOTIFICATION_RECIPIENTS]]
    for name in names:
        raws.append({**recipient(name), **overrides.get(name, {})})
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_NOTIFICATION_RECIPIENTS: raws}
    )


async def test_user_pairing_covers_every_normal_login_of_that_user(
    runtime_hass, runtime_entry, measurement_clock
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    user, tokens = await logins(runtime_hass, "phone_app", "laptop", "after_reinstall")
    pair(runtime_hass, runtime_entry, {}, users={"phone": user.id})
    for name, token in tokens.items():
        session = (await call(handle_session, runtime_hass, Connection(user, token.id)))[0]
        assert session["paired"] is True and session["recipient_id"] == "phone", name
    # A login of another user never matches, even with the same client.
    other = await runtime_hass.auth.async_create_user("Guest")
    guest = await runtime_hass.auth.async_create_refresh_token(other, CLIENT, client_name="g")
    assert (await call(handle_session, runtime_hass, Connection(other, guest.id)))[0] == {
        "paired": False
    }
    # Stealing another user's login id does not help either.
    stolen = Connection(other, tokens["laptop"].id)
    assert (await call(handle_mute, runtime_hass, stolen, event_id=event_id))[1] == "not_paired"
    assert_safety(manager)


async def test_user_pairing_rejects_long_lived_tokens(
    runtime_hass, runtime_entry, measurement_clock
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    user, _ = await logins(runtime_hass, "phone")
    lla = await runtime_hass.auth.async_create_refresh_token(
        user, client_name="script", token_type=TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN
    )
    pair(runtime_hass, runtime_entry, {}, users={"phone": user.id})
    script = Connection(user, lla.id)
    assert (await call(handle_session, runtime_hass, script))[0] == {"paired": False}
    for handler in (handle_mute, handle_acknowledge):
        assert (await call(handler, runtime_hass, script, event_id=event_id))[1] == "not_paired"
    state = manager.notifications.state_for(event_id)
    assert not state.muted_recipients and not state.globally_acknowledged
    assert_safety(manager)


async def test_login_pairing_wins_over_user_pairing(
    runtime_hass, runtime_entry, measurement_clock
):
    """User paired to recipient A, one of its logins to recipient B."""
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    add_recipients(runtime_hass, runtime_entry, "ipad")
    user, tokens = await logins(runtime_hass, "phone_app", "ipad_app", "laptop")
    pair(
        runtime_hass,
        runtime_entry,
        {"ipad": tokens["ipad_app"].id},
        users={"phone": user.id},
    )
    resolved = {
        name: (await call(handle_session, runtime_hass, Connection(user, token.id)))[0][
            "recipient_id"
        ]
        for name, token in tokens.items()
    }
    assert resolved == {"phone_app": "phone", "ipad_app": "ipad", "laptop": "phone"}
    # Deleting the paired login falls back to nothing for that login only.
    runtime_hass.auth.async_remove_refresh_token(tokens["ipad_app"])
    gone = Connection(user, tokens["ipad_app"].id)
    assert (await call(handle_session, runtime_hass, gone))[0] == {"paired": False}
    assert_safety(manager)


async def test_existing_login_pairing_works_unchanged(
    runtime_hass, runtime_entry, measurement_clock
):
    """Stored session_token_id pairings from 2.0.0-beta.1 need no migration."""
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    user, tokens = await logins(runtime_hass, "phone", "laptop")
    pair(runtime_hass, runtime_entry, {"phone": tokens["phone"].id})
    assert "session_user_id" not in runtime_entry.options[CONF_NOTIFICATION_RECIPIENTS][0]
    phone = Connection(user, tokens["phone"].id)
    assert (await call(handle_session, runtime_hass, phone))[0]["recipient_id"] == "phone"
    # Only exactly that login: another login of the same user stays unpaired.
    laptop = Connection(user, tokens["laptop"].id)
    assert (await call(handle_session, runtime_hass, laptop))[0] == {"paired": False}
    assert (await call(handle_mute, runtime_hass, phone, event_id=event_id))[1] is None
    assert manager.notifications.state_for(event_id).muted_recipients == {"phone"}
    assert_safety(manager)


@pytest.mark.parametrize("problem", ["inactive", "system"])
async def test_inactive_and_system_users_never_match(
    runtime_hass, runtime_entry, measurement_clock, problem
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    user, tokens = await logins(runtime_hass, "phone")
    if problem == "inactive":
        pair(runtime_hass, runtime_entry, {}, users={"phone": user.id})
        await runtime_hass.auth.async_deactivate_user(user)
        conn = Connection(user, tokens["phone"].id)
    else:
        system = await runtime_hass.auth.async_create_system_user("Supervisor")
        token = await runtime_hass.auth.async_create_refresh_token(system)
        pair(runtime_hass, runtime_entry, {}, users={"phone": system.id})
        conn = Connection(system, token.id)
    assert (await call(handle_session, runtime_hass, conn))[0] == {"paired": False}
    assert (await call(handle_mute, runtime_hass, conn, event_id=event_id))[1] == "not_paired"
    # Neither is offered for pairing.
    flow = options_flow(runtime_hass, runtime_entry)
    flow._editing_recipient_id = "phone"
    form = await flow.async_step_edit_recipient_details()
    offered = [o["value"] for o in form["data_schema"].schema["session_pairing"].config["options"]]
    paired_id = user.id if problem == "inactive" else system.id
    assert all(paired_id not in value for value in offered[:-1])
    # The stored but no longer valid pairing stays visible, so saving keeps it.
    assert offered[-1] == f"user:{paired_id}"
    assert_safety(manager)


async def test_mute_with_user_pairing_is_recipient_scoped(
    runtime_hass, runtime_entry, measurement_clock
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    add_recipients(runtime_hass, runtime_entry, "ipad")
    bea, bea_tokens = await logins(runtime_hass, "phone")
    max_user = await runtime_hass.auth.async_create_user("Max")
    max_token = await runtime_hass.auth.async_create_refresh_token(
        max_user, CLIENT, client_name="ipad"
    )
    pair(runtime_hass, runtime_entry, {}, users={"phone": bea.id, "ipad": max_user.id})
    runtime_hass.states.async_set("device_tracker.phone", "not_home")
    result, error = await call(
        handle_mute, runtime_hass, Connection(bea, bea_tokens["phone"].id), event_id=event_id
    )
    assert error is None and result == {"muted": True, "scope": "device"}
    state = manager.notifications.state_for(event_id)
    assert state.muted_recipients == {"phone"}
    assert not state.globally_acknowledged
    session = (await call(handle_session, runtime_hass, Connection(max_user, max_token.id)))[0]
    assert session["recipient_id"] == "ipad"
    assert_safety(manager)


async def test_home_check_uses_the_paired_recipients_tracker(
    runtime_hass, runtime_entry, measurement_clock
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    add_recipients(runtime_hass, runtime_entry, "ipad")
    user, tokens = await logins(runtime_hass, "laptop")
    pair(runtime_hass, runtime_entry, {}, users={"phone": user.id})
    # Another recipient's tracker at home never helps the user-paired laptop.
    runtime_hass.states.async_set("device_tracker.phone", "not_home")
    runtime_hass.states.async_set("device_tracker.ipad", "home")
    laptop = Connection(user, tokens["laptop"].id)
    session = (await call(handle_session, runtime_hass, laptop))[0]
    assert session["home"] is False and session["tracker_entity"] == "device_tracker.phone"
    assert (await call(handle_acknowledge, runtime_hass, laptop, event_id=event_id))[1] == (
        "not_home"
    )
    assert not manager.notifications.state_for(event_id).globally_acknowledged
    runtime_hass.states.async_set("device_tracker.phone", "home")
    assert (await call(handle_session, runtime_hass, laptop))[0]["home"] is True
    assert (await call(handle_acknowledge, runtime_hass, laptop, event_id=event_id))[1] is None
    state = manager.notifications.state_for(event_id)
    assert state.globally_acknowledged and state.globally_acknowledged_by == "phone"
    assert_safety(manager)


async def test_user_pairing_changed_while_waiting_for_writer_rejects(
    runtime_hass, runtime_entry, measurement_clock
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    user, tokens = await logins(runtime_hass, "phone")
    other = await runtime_hass.auth.async_create_user("Max")
    pair(runtime_hass, runtime_entry, {}, users={"phone": user.id})
    conn = Connection(user, tokens["phone"].id)
    async with manager._state_lock:
        task = asyncio.create_task(handle_mute(runtime_hass, conn, {"id": 1, "event_id": event_id}))
        for _ in range(5):
            await asyncio.sleep(0)
        assert not conn.results and not conn.errors
        pair(runtime_hass, runtime_entry, {}, users={"phone": other.id})
    await task
    assert conn.errors == ["not_paired"] and not conn.results
    assert not manager.notifications.state_for(event_id).muted_recipients
    assert_safety(manager)


async def test_user_pairing_in_the_recipient_form(runtime_hass, runtime_entry, measurement_clock):
    await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    add_recipients(
        runtime_hass,
        runtime_entry,
        "ipad",
        ipad={"critical_enabled": False, "trusted_stationary": True, "allow_external_reset": True},
    )
    bea, tokens = await logins(runtime_hass, "phone", "ipad")
    max_user = await runtime_hass.auth.async_create_user("Max")
    before = recipients_by_id(runtime_entry)
    flow = options_flow(runtime_hass, runtime_entry)

    # Users are offered first (default kind of pairing), then single logins.
    form, result = await edit(flow, "phone", before["phone"], session_pairing=f"user:{bea.id}")
    offered = [o["value"] for o in form["data_schema"].schema["session_pairing"].config["options"]]
    assert offered[0] == "__none__"
    kinds = [value.split(":", 1)[0] for value in offered[1:]]
    assert kinds == sorted(kinds, key=lambda kind: kind != "user")
    assert {f"user:{bea.id}", f"user:{max_user.id}"} <= set(offered)
    assert {f"token:{tokens['phone'].id}", f"token:{tokens['ipad'].id}"} <= set(offered)
    assert result["step_id"] == "notifications"
    after = recipients_by_id(runtime_entry)
    assert after["phone"]["session_user_id"] == bea.id
    assert "session_token_id" not in after["phone"]
    assert after["phone"]["token"] == before["phone"]["token"]
    assert alarm_settings(after["phone"]) == alarm_settings(before["phone"])
    assert after["ipad"] == before["ipad"]

    # Saving again without touching the pairing keeps everything.
    form, _ = await edit(flow, "phone", after["phone"])
    assert form["data_schema"]({**{k: after["phone"][k] for k in ALARM_FIELDS}})[
        "session_pairing"
    ] == f"user:{bea.id}"
    assert recipients_by_id(runtime_entry) == after

    # A user belongs to at most one recipient; nothing is saved on error.
    _, duplicate = await edit(flow, "ipad", after["ipad"], session_pairing=f"user:{bea.id}")
    assert duplicate["errors"] == {"base": "session_user_already_paired"}
    assert recipients_by_id(runtime_entry) == after

    # One of the user's logins may still go to another recipient (login wins).
    _, result = await edit(
        flow, "ipad", after["ipad"], session_pairing=f"token:{tokens['ipad'].id}"
    )
    assert result["step_id"] == "notifications"
    after = recipients_by_id(runtime_entry)
    assert after["ipad"]["session_token_id"] == tokens["ipad"].id
    assert alarm_settings(after["ipad"]) == alarm_settings(before["ipad"])
    assert after["ipad"]["allow_external_reset"] is True

    # Switching from login to user pairing stores only the user, never both.
    _, result = await edit(flow, "ipad", after["ipad"], session_pairing=f"user:{max_user.id}")
    after = recipients_by_id(runtime_entry)
    assert after["ipad"]["session_user_id"] == max_user.id
    assert "session_token_id" not in after["ipad"]
    assert alarm_settings(after["ipad"]) == alarm_settings(before["ipad"])

    # A user that disappears between showing and saving the form is rejected.
    flow._editing_recipient_id = "phone"
    form = await flow.async_step_edit_recipient_details()
    values = form["data_schema"](
        {**{k: after["phone"][k] for k in ALARM_FIELDS}, "session_pairing": f"user:{max_user.id}"}
    )
    await runtime_hass.auth.async_deactivate_user(max_user)
    _, gone = form, await flow.async_step_edit_recipient_details(values)
    assert gone["errors"] == {"base": "session_user_not_found"}
    assert recipients_by_id(runtime_entry) == after

    # Removing the pairing keeps every alarm setting.
    _, result = await edit(flow, "phone", after["phone"], session_pairing="__none__")
    final = recipients_by_id(runtime_entry)
    assert "session_user_id" not in final["phone"] and "session_token_id" not in final["phone"]
    assert alarm_settings(final["phone"]) == alarm_settings(before["phone"])


async def test_editing_keeps_a_login_pairing_whose_login_is_gone(
    runtime_hass, runtime_entry, measurement_clock
):
    await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    _, tokens = await logins(runtime_hass, "phone")
    pair(runtime_hass, runtime_entry, {"phone": tokens["phone"].id})
    runtime_hass.auth.async_remove_refresh_token(tokens["phone"])
    before = recipients_by_id(runtime_entry)
    flow = options_flow(runtime_hass, runtime_entry)
    _, result = await edit(flow, "phone", before["phone"])
    assert result["step_id"] == "notifications"
    assert recipients_by_id(runtime_entry) == before


async def test_new_recipient_can_be_paired_with_a_user(
    runtime_hass, runtime_entry, measurement_clock
):
    await ack_manager(runtime_hass, runtime_entry, measurement_clock)

    async def notify(call):
        pass

    runtime_hass.services.async_register("notify", "mobile_app_tablet", notify)
    user, _ = await logins(runtime_hass, "tablet")
    pair(runtime_hass, runtime_entry, {}, users={"phone": user.id})
    before = recipients_by_id(runtime_entry)
    flow = options_flow(runtime_hass, runtime_entry)
    form = await flow.async_step_add_recipient()
    base = {
        "name": "Tablet",
        "notify_service": "notify.mobile_app_tablet",
        "tracker_entity": "device_tracker.tablet",
        "critical_enabled": True,
        "allow_global_ack": True,
        "trusted_stationary": False,
    }
    duplicate = await flow.async_step_add_recipient(
        form["data_schema"]({**base, "session_pairing": f"user:{user.id}"})
    )
    assert duplicate["errors"] == {"base": "session_user_already_paired"}
    assert recipients_by_id(runtime_entry) == before
    other = await runtime_hass.auth.async_create_user("Max")
    form = await flow.async_step_add_recipient()
    result = await flow.async_step_add_recipient(
        form["data_schema"]({**base, "session_pairing": f"user:{other.id}"})
    )
    assert result["step_id"] == "notifications"
    added = next(raw for key, raw in recipients_by_id(runtime_entry).items() if key not in before)
    assert added["session_user_id"] == other.id and "session_token_id" not in added
