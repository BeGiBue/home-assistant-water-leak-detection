"""Dashboard card contract: device pairing and server-side authorization.

Rights belong to the paired device (HA login), not to the user: one user's
iPad at home may acknowledge globally while the same user's phone away may only
mute itself. All tests use the real manager, Store, event bus and HA auth.
"""

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


def pair(hass, entry, pairs):
    """Store recipient -> login pairing like the options flow does."""
    raws = []
    for raw in entry.options[CONF_NOTIFICATION_RECIPIENTS]:
        raw = dict(raw)
        raw.pop("session_token_id", None)
        if raw["id"] in pairs:
            raw["session_token_id"] = pairs[raw["id"]]
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

    assert (await call(handle_session, runtime_hass, phone))[0]["home"] is False
    assert (await call(handle_session, runtime_hass, ipad_conn))[0]["home"] is True
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


async def test_responses_never_contain_secrets(runtime_hass, runtime_entry, measurement_clock):
    await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    user, tokens = await logins(runtime_hass, "phone")
    pair(runtime_hass, runtime_entry, {"phone": tokens["phone"].id})
    result, _ = await call(handle_session, runtime_hass, Connection(user, tokens["phone"].id))
    text = json.dumps(result)
    assert result["paired"] and result["recipient_id"] == "phone"
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
    return replace(parsed, session_token_id=None)


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
        flow, "phone", before["phone"], session_token_id=tokens["phone"].id
    )
    offered = [o["value"] for o in form["data_schema"].schema["session_token_id"].config["options"]]
    assert tokens["phone"].id in offered and tokens["ipad"].id in offered
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
    _, duplicate = await edit(flow, "ipad", after["ipad"], session_token_id=tokens["phone"].id)
    assert duplicate["errors"] == {"base": "session_already_paired"}
    assert recipients_by_id(runtime_entry) == after

    # Removing the pairing restores the original alarm configuration.
    _, result = await edit(flow, "phone", after["phone"], session_token_id="__none__")
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
            "session_token_id": tokens["tablet"].id,
        }
    )
    result = await flow.async_step_add_recipient(values)
    assert result["step_id"] == "notifications"
    after = recipients_by_id(runtime_entry)
    added = next(raw for key, raw in after.items() if key not in before)
    assert added["session_token_id"] == tokens["tablet"].id
    assert added["critical_enabled"] is False and added["allow_global_ack"] is False
    assert {key: after[key] for key in before} == before
