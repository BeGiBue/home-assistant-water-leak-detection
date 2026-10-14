"""Stationary display recipients (e.g. TouchKio): no push, no tracker, always Home.

A display is only useful paired with a HA login or a dedicated kiosk user (active,
neither owner nor admin, used by no other recipient's pairing). It never takes part in
notification dispatch, has nothing to mute and passes every Home check; its
permissions are the ordinary per-recipient flags. Mobile recipients are unchanged.
"""

import pytest
from homeassistant.auth.const import GROUP_ID_ADMIN
from homeassistant.auth.models import TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN
from test_ack_duration_diagnostics import ack_manager
from test_card_backend_contract import (
    ALARM_FIELDS,
    CLIENT,
    Connection,
    alarm_settings,
    assert_safety,
    call,
    edit,
    logins,
    recipients_by_id,
)
from test_config_runtime import options_flow
from test_external_reset_runtime import configured

from custom_components.water_leak_detection import notifications as notifications_module
from custom_components.water_leak_detection.const import (
    ACTION_ACK_ALL,
    ACTION_PREFIX,
    CONF_NOTIFICATION_RECIPIENTS,
    EVENT_ACK_REJECTED,
    MOBILE_ACTION_EVENT,
)
from custom_components.water_leak_detection.external_leaks import ExternalPhase
from custom_components.water_leak_detection.notifications import (
    NotificationRecipient,
    recipient_is_home,
)
from custom_components.water_leak_detection.websocket import (
    handle_acknowledge,
    handle_external_reset,
    handle_mute,
    handle_session,
)


def display(**extra):
    return {
        "id": "wall",
        "name": "Flur",
        "kind": "display",
        "token": "token_wall",
        "allow_global_ack": True,
        "allow_external_reset": True,
        **extra,
    }


def add(hass, entry, raw):
    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            CONF_NOTIFICATION_RECIPIENTS: [*entry.options[CONF_NOTIFICATION_RECIPIENTS], raw],
        },
    )


async def kiosk_user(hass, *names, admin=False):
    """A further HA user (not the owner, created after logins()) with normal logins."""
    user = await hass.auth.async_create_user(
        "Admin" if admin else "Kiosk", group_ids=[GROUP_ID_ADMIN] if admin else None
    )
    tokens = {}
    for name in names:
        tokens[name] = await hass.auth.async_create_refresh_token(user, CLIENT, client_name=name)
    return user, tokens


def set_recipients(hass, entry, raws):
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_NOTIFICATION_RECIPIENTS: raws}
    )


def mobile_pairing(entry, **pairing):
    """The configured phone with exactly this pairing (and nothing else changed)."""
    raws = []
    for raw in entry.options[CONF_NOTIFICATION_RECIPIENTS]:
        raw = dict(raw)
        if raw.get("id") == "phone":
            raw.pop("session_token_id", None)
            raw.pop("session_user_id", None)
            raw.update(pairing)
        raws.append(raw)
    return raws


def test_parsing_display_and_legacy_kind(runtime_hass):
    wall = NotificationRecipient.from_dict(display())
    assert wall is not None and wall.is_display and wall.kind == "display"
    assert wall.notify_service == "" and wall.tracker_entity == ""
    assert wall.critical_enabled is False and wall.trusted_stationary is False
    assert recipient_is_home(runtime_hass, wall) is True
    legacy = NotificationRecipient.from_dict(
        {
            "id": "phone",
            "name": "Phone",
            "notify_service": "notify.mobile_app_phone",
            "tracker_entity": "device_tracker.phone",
            "token": "t",
        }
    )
    assert legacy.kind == "mobile" and not legacy.is_display
    # Mobile still needs both; its home check still uses the tracker.
    assert recipient_is_home(runtime_hass, legacy) is False
    runtime_hass.states.async_set("device_tracker.phone", "home")
    assert recipient_is_home(runtime_hass, legacy) is True
    assert NotificationRecipient.from_dict({**display(), "kind": "mobile"}) is None
    assert NotificationRecipient.from_dict(display(kind="tablet")) is None
    assert NotificationRecipient.from_dict(display(token="")) is None


async def test_display_session_is_home_and_has_no_mute(
    runtime_hass, runtime_entry, measurement_clock
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    user, tokens = await logins(runtime_hass, "kiosk")
    add(runtime_hass, runtime_entry, display(session_token_id=tokens["kiosk"].id))
    conn = Connection(user, tokens["kiosk"].id)
    session = (await call(handle_session, runtime_hass, conn))[0]
    assert session["paired"] and session["recipient_id"] == "wall"
    assert session["kind"] == "display" and session["home"] is True
    assert session["tracker_entity"] is None and session["can_mute"] is False
    # Mute is not applicable, with a stable code; nothing is muted.
    controller_mute = manager.notifications.async_session_mute

    async def must_not_be_called(*_):
        raise AssertionError("the websocket command must reject a display before the writer")

    manager.notifications.async_session_mute = must_not_be_called
    assert (await call(handle_mute, runtime_hass, conn, event_id=event_id))[1] == (
        "mute_not_applicable"
    )
    manager.notifications.async_session_mute = controller_mute
    assert await manager.notifications.async_session_mute(event_id, "wall") == "not_applicable"
    assert not manager.notifications.state_for(event_id).muted_recipients
    assert_safety(manager)


@pytest.mark.parametrize("allowed", [True, False])
async def test_display_global_ack_follows_permission_not_a_tracker(
    runtime_hass, runtime_entry, measurement_clock, allowed
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    # The phone is away: only the display can be "home", and it is, always.
    runtime_hass.states.async_set("device_tracker.phone", "not_home")
    user, tokens = await logins(runtime_hass, "kiosk")
    add(
        runtime_hass,
        runtime_entry,
        display(session_token_id=tokens["kiosk"].id, allow_global_ack=allowed),
    )
    result, error = await call(
        handle_acknowledge, runtime_hass, Connection(user, tokens["kiosk"].id), event_id=event_id
    )
    state = manager.notifications.state_for(event_id)
    if allowed:
        assert error is None and result == {"acknowledged": True, "scope": "global"}
        assert state.globally_acknowledged and state.globally_acknowledged_by == "wall"
    else:
        assert error == "not_allowed" and not state.globally_acknowledged
    assert_safety(manager)


@pytest.mark.parametrize("allowed", [True, False])
async def test_display_external_reset_follows_permission(
    runtime_hass, runtime_entry, measurement_clock, allowed
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    source = manager.external.sources["a"]
    runtime_hass.states.async_set("device_tracker.phone", "not_home")
    user, tokens = await logins(runtime_hass, "kiosk")
    add(
        runtime_hass,
        runtime_entry,
        display(session_token_id=tokens["kiosk"].id, allow_external_reset=allowed),
    )
    # The notification path never prepares an external-reset action for a display
    # (the event is active here, so only the display guard decides).
    assert await manager._prepare_external_reset_action("a", "wall", None, None) is None
    result, error = await call(
        handle_external_reset,
        runtime_hass,
        Connection(user, tokens["kiosk"].id),
        event_id=source.event_id,
        source_id="a",
        source_generation=source.identity.generation,
    )
    if allowed:
        assert error is None and result == {"reset": True}
        assert manager.external.sources["a"].phase is ExternalPhase.RESET_WAITING_FOR_OFF
    else:
        assert error == "not_allowed"
        assert manager.external.sources["a"].phase is ExternalPhase.ACTIVE
        assert manager.alarm_active and manager.shutoff_request
    # A display never gets a notification with a reset action.
    assert not await manager.async_request_external_reset_action("a", "wall")


async def test_display_is_never_part_of_notification_dispatch(
    runtime_hass, runtime_entry, measurement_clock
):
    _, manager, event_id, calls = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    before = len(calls)
    add(runtime_hass, runtime_entry, display())
    notifications = manager.notifications
    notifications.reload_recipients()
    wall = notifications.recipients["wall"]
    assert not notifications._eligible(event_id, wall)
    # A new event round and a tracker returning home: still only mobile routes.
    state = notifications.state_for(event_id)
    state.accepted_recipients.clear()
    state.route_states.clear()
    await notifications.async_retry_pending()
    await runtime_hass.async_block_till_done()
    runtime_hass.states.async_set("device_tracker.phone", "not_home")
    runtime_hass.states.async_set("device_tracker.phone", "home")
    await runtime_hass.async_block_till_done()
    assert all(call.get("data", {}).get("wld_recipient_id") != "wall" for call in calls)
    assert len(calls) > before  # the phone was notified again
    assert "wall" not in state.dispatch_states
    assert all('"wall"' not in route for route in state.route_states)
    assert not await notifications._async_send_event_notification(
        wall, event_id, "low_flow", {}, returning_home=False
    )
    # Each guard on its own: even if eligibility said yes, the dispatch loop skips it.
    notifications._eligible = lambda *_: True
    await notifications.async_retry_pending()
    await runtime_hass.async_block_till_done()
    assert "wall" not in state.dispatch_states
    assert all('"wall"' not in route for route in state.route_states)
    assert_safety(manager)


async def test_display_cannot_use_notification_actions(
    runtime_hass, runtime_entry, measurement_clock
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    add(runtime_hass, runtime_entry, display())
    rejected = []
    runtime_hass.bus.async_listen(EVENT_ACK_REJECTED, lambda event: rejected.append(event.data))
    action = "|".join(
        (ACTION_PREFIX, ACTION_ACK_ALL, runtime_entry.entry_id, event_id, "wall", "token_wall")
    )
    runtime_hass.bus.async_fire(MOBILE_ACTION_EVENT, {"action": action})
    await runtime_hass.async_block_till_done()
    assert not manager.notifications.state_for(event_id).globally_acknowledged
    assert [r.get("reason") for r in rejected] == ["display_recipient"]
    assert_safety(manager)


async def test_long_lived_tokens_never_match_a_display(
    runtime_hass, runtime_entry, measurement_clock
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    await logins(runtime_hass)
    user, tokens = await kiosk_user(runtime_hass, "kiosk_browser")
    lla = await runtime_hass.auth.async_create_refresh_token(
        user, client_name="script", token_type=TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN
    )
    add(runtime_hass, runtime_entry, display(session_token_id=lla.id))
    script = Connection(user, lla.id)
    assert (await call(handle_session, runtime_hass, script))[0] == {"paired": False}
    # A valid kiosk-user pairing: its normal login resolves, the long-lived token never.
    raws = [r for r in runtime_entry.options[CONF_NOTIFICATION_RECIPIENTS] if r.get("id") != "wall"]
    set_recipients(runtime_hass, runtime_entry, [*raws, display(session_user_id=user.id)])
    browser = Connection(user, tokens["kiosk_browser"].id)
    assert (await call(handle_session, runtime_hass, browser))[0]["recipient_id"] == "wall"
    assert (await call(handle_session, runtime_hass, script))[0] == {"paired": False}
    assert (await call(handle_acknowledge, runtime_hass, script, event_id=event_id))[1] == (
        "not_paired"
    )
    assert not manager.notifications.state_for(event_id).globally_acknowledged


async def _form(flow, step, **values):
    form = await getattr(flow, f"async_step_{step}")()
    return form, await getattr(flow, f"async_step_{step}")(form["data_schema"](values))


async def test_display_form_accepts_a_kiosk_user_or_a_login_and_keeps_mobile_unchanged(
    runtime_hass, runtime_entry, measurement_clock
):
    await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    owner, tokens = await logins(runtime_hass, "phone", "kiosk_browser")
    kiosk, _ = await kiosk_user(runtime_hass)
    assert owner.is_owner and not kiosk.is_owner and not kiosk.is_admin
    before = recipients_by_id(runtime_entry)
    flow = options_flow(runtime_hass, runtime_entry)
    menu = await flow.async_step_notifications()
    assert "add_display" in menu["menu_options"]

    form = await flow.async_step_add_display()
    fields = {str(key) for key in form["data_schema"].schema}
    assert fields >= {"name", "session_pairing", "allow_global_ack", "allow_external_reset"}
    assert not fields & {"notify_service", "tracker_entity", "critical_enabled"}
    offered = [o["value"] for o in form["data_schema"].schema["session_pairing"].config["options"]]
    # Users and single logins, but no "—".
    assert "__none__" not in offered
    assert f"user:{kiosk.id}" in offered and f"token:{tokens['kiosk_browser'].id}" in offered

    # Without a pairing, nothing is saved.
    flags = {"allow_global_ack": True, "allow_external_reset": False}
    missing = await flow.async_step_add_display({"name": "Flur", **flags})
    assert missing["errors"] == {"base": "required_fields_missing"}
    none = await flow.async_step_add_display(
        {"name": "Flur", "session_pairing": "__none__", **flags}
    )
    assert none["errors"] == {"base": "display_pairing_required"}
    assert recipients_by_id(runtime_entry) == before

    # Uniqueness: a login paired elsewhere cannot be paired to the display.
    set_recipients(
        runtime_hass,
        runtime_entry,
        mobile_pairing(runtime_entry, session_token_id=tokens["phone"].id),
    )
    before = recipients_by_id(runtime_entry)
    _, dup = await _form(
        flow, "add_display", name="Flur", session_pairing=f"token:{tokens['phone'].id}"
    )
    assert dup["errors"] == {"base": "session_already_paired"}

    # A kiosk user is accepted and stored as user pairing.
    _, result = await _form(
        flow,
        "add_display",
        name="Flur",
        session_pairing=f"user:{kiosk.id}",
        allow_global_ack=True,
    )
    assert result["step_id"] == "notifications"
    after = recipients_by_id(runtime_entry)
    wall = next(raw for key, raw in after.items() if key not in before)
    assert wall["kind"] == "display" and wall["session_user_id"] == kiosk.id
    assert "session_token_id" not in wall
    assert wall["allow_global_ack"] is True and wall["allow_external_reset"] is False
    assert not {"notify_service", "tracker_entity", "critical_enabled"} & wall.keys()
    assert wall["token"]

    # Editing routes to the display form, keeps kind, id, token and the pairing.
    flow._editing_recipient_id = wall["id"]
    form = await flow.async_step_edit_recipient({"id": wall["id"]})
    assert form["step_id"] == "edit_display_details"
    values = form["data_schema"]({"name": "Flur oben", "allow_external_reset": True})
    await flow.async_step_edit_display_details(values)
    edited = recipients_by_id(runtime_entry)[wall["id"]]
    assert edited == {**wall, "name": "Flur oben", "allow_external_reset": True}
    # Switching the display to the owner is rejected on edit, too.
    flow._editing_recipient_id = wall["id"]
    form = await flow.async_step_edit_display_details()
    rejected = await flow.async_step_edit_display_details(
        {"name": "Flur oben", "session_pairing": f"user:{owner.id}", **flags}
    )
    assert rejected["errors"] == {"base": "display_user_not_allowed"}
    assert recipients_by_id(runtime_entry)[wall["id"]] == edited
    # A single login stays allowed, also one of the owner (the stricter option).
    flow._editing_recipient_id = wall["id"]
    form = await flow.async_step_edit_display_details()
    result = await flow.async_step_edit_display_details(
        {
            "name": "Flur oben",
            "session_pairing": f"token:{tokens['kiosk_browser'].id}",
            **flags,
        }
    )
    assert result["step_id"] == "notifications"
    relogin = recipients_by_id(runtime_entry)[wall["id"]]
    assert relogin["session_token_id"] == tokens["kiosk_browser"].id
    assert "session_user_id" not in relogin

    # The mobile recipient's alarm settings are untouched by all of this.
    phone = recipients_by_id(runtime_entry)["phone"]
    assert alarm_settings(phone) == alarm_settings(before["phone"])
    assert {k: phone[k] for k in ALARM_FIELDS} == {k: before["phone"][k] for k in ALARM_FIELDS}

    # The admin acknowledgement form offers only mobile recipients.
    ack_form = await flow.async_step_acknowledgements()
    choices = [o["value"] for o in ack_form["data_schema"].schema["recipient_id"].config["options"]]
    assert wall["id"] not in choices and "phone" in choices


@pytest.mark.parametrize("who", ["owner", "admin"])
async def test_display_form_rejects_owner_and_admin_users(
    runtime_hass, runtime_entry, measurement_clock, who
):
    await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    owner, _ = await logins(runtime_hass, "phone")
    admin, _ = await kiosk_user(runtime_hass, admin=True)
    assert owner.is_owner and admin.is_admin and not admin.is_owner
    user = owner if who == "owner" else admin
    before = recipients_by_id(runtime_entry)
    flow = options_flow(runtime_hass, runtime_entry)
    _, result = await _form(flow, "add_display", name="Flur", session_pairing=f"user:{user.id}")
    assert result["errors"] == {"base": "display_user_not_allowed"}
    assert recipients_by_id(runtime_entry) == before


@pytest.mark.parametrize("via", ["user", "token"])
async def test_display_user_must_not_be_used_by_another_recipient(
    runtime_hass, runtime_entry, measurement_clock, via
):
    """Both directions: display after mobile, and mobile after display."""
    await ack_manager(runtime_hass, runtime_entry, measurement_clock)

    async def notify(call):
        pass

    runtime_hass.services.async_register("notify", "mobile_app_tablet", notify)
    await logins(runtime_hass, "phone")
    kiosk, kiosk_tokens = await kiosk_user(runtime_hass, "kiosk_browser", "kiosk_phone")
    mobile = (
        {"session_user_id": kiosk.id}
        if via == "user"
        else {"session_token_id": kiosk_tokens["kiosk_phone"].id}
    )
    choice = f"user:{kiosk.id}" if via == "user" else f"token:{kiosk_tokens['kiosk_phone'].id}"
    flow = options_flow(runtime_hass, runtime_entry)

    # 1. The phone uses the kiosk user (or one of its logins): no display with that user.
    set_recipients(runtime_hass, runtime_entry, mobile_pairing(runtime_entry, **mobile))
    before = recipients_by_id(runtime_entry)
    _, result = await _form(flow, "add_display", name="Flur", session_pairing=f"user:{kiosk.id}")
    assert result["errors"] == {"base": "display_user_in_use"}
    assert recipients_by_id(runtime_entry) == before

    # 2. The display has the kiosk user: no mobile recipient with it or its logins.
    set_recipients(runtime_hass, runtime_entry, mobile_pairing(runtime_entry))
    _, result = await _form(flow, "add_display", name="Flur", session_pairing=f"user:{kiosk.id}")
    assert result["step_id"] == "notifications"
    before = recipients_by_id(runtime_entry)
    _, rejected = await edit(flow, "phone", before["phone"], session_pairing=choice)
    assert rejected["errors"] == {"base": "session_user_reserved_for_display"}
    form = await flow.async_step_add_recipient()
    added = await flow.async_step_add_recipient(
        form["data_schema"](
            {
                "name": "Tablet",
                "notify_service": "notify.mobile_app_tablet",
                "tracker_entity": "device_tracker.tablet",
                "critical_enabled": True,
                "allow_global_ack": True,
                "trusted_stationary": False,
                "session_pairing": choice,
            }
        )
    )
    assert added["errors"] == {"base": "session_user_reserved_for_display"}
    # A second display cannot take one of the kiosk user's logins either.
    _, second = await _form(
        flow,
        "add_display",
        name="Küche",
        session_pairing=f"token:{kiosk_tokens['kiosk_browser'].id}",
    )
    assert second["errors"] == {"base": "session_user_reserved_for_display"}
    assert recipients_by_id(runtime_entry) == before


@pytest.mark.parametrize("problem", ["admin", "owner", "other_user", "other_token"])
async def test_hand_edited_display_user_pairing_that_is_not_a_kiosk_user_never_resolves(
    runtime_hass, runtime_entry, measurement_clock, caplog, problem
):
    """The display is always Home: an admin, the owner, or a user that another device
    also uses would give e.g. the laptop in the office or the phone away home rights."""
    notifications_module._WARNED.clear()
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    runtime_hass.states.async_set("device_tracker.phone", "not_home")
    owner, owner_tokens = await logins(runtime_hass, "laptop", "phone")
    if problem == "owner":
        user, tokens = owner, owner_tokens
    else:
        user, tokens = await kiosk_user(runtime_hass, "laptop", "phone", admin=problem == "admin")
    phone = {
        "other_user": {"session_user_id": user.id},
        "other_token": {"session_token_id": tokens["phone"].id},
    }.get(problem, {})
    set_recipients(
        runtime_hass,
        runtime_entry,
        [*mobile_pairing(runtime_entry, **phone), display(session_user_id=user.id)],
    )
    laptop = Connection(user, tokens["laptop"].id)
    assert manager.notifications.recipient_for_session(tokens["laptop"].id, user.id, user) is None
    session = (await call(handle_session, runtime_hass, laptop))[0]
    assert session == {"paired": False} or session["recipient_id"] == "phone"
    assert (await call(handle_acknowledge, runtime_hass, laptop, event_id=event_id))[1] in (
        "not_paired",
        "not_home",
    )
    assert not manager.notifications.state_for(event_id).globally_acknowledged
    assert "Wall display wall (Flur)" in caplog.text
    if problem == "other_token":
        # The phone keeps its own pairing and, away, gets no home rights.
        phone_conn = Connection(user, tokens["phone"].id)
        session = (await call(handle_session, runtime_hass, phone_conn))[0]
        assert session["recipient_id"] == "phone" and session["home"] is False
        assert (await call(handle_acknowledge, runtime_hass, phone_conn, event_id=event_id))[
            1
        ] == "not_home"
    if problem == "other_user":
        # Ambiguous user pairing: nothing resolves at all.
        assert session == {"paired": False}
    assert_safety(manager)


async def test_kiosk_user_pairing_resolves_for_its_logins_and_is_home(
    runtime_hass, runtime_entry, measurement_clock
):
    _, manager, event_id, _ = await ack_manager(runtime_hass, runtime_entry, measurement_clock)
    runtime_hass.states.async_set("device_tracker.phone", "not_home")
    owner, owner_tokens = await logins(runtime_hass, "phone")
    kiosk, tokens = await kiosk_user(runtime_hass, "kiosk_browser", "kiosk_relogin")
    set_recipients(
        runtime_hass,
        runtime_entry,
        [
            *mobile_pairing(runtime_entry, session_token_id=owner_tokens["phone"].id),
            display(session_user_id=kiosk.id),
        ],
    )
    for login in ("kiosk_browser", "kiosk_relogin"):
        conn = Connection(kiosk, tokens[login].id)
        session = (await call(handle_session, runtime_hass, conn))[0]
        assert session["recipient_id"] == "wall" and session["home"] is True
    # Without the session user (unknown caller) a display user pairing fails closed.
    assert manager.notifications.recipient_for_session(tokens["kiosk_browser"].id, kiosk.id) is None
    result, error = await call(
        handle_acknowledge,
        runtime_hass,
        Connection(kiosk, tokens["kiosk_relogin"].id),
        event_id=event_id,
    )
    assert error is None and result == {"acknowledged": True, "scope": "global"}
    state = manager.notifications.state_for(event_id)
    assert state.globally_acknowledged and state.globally_acknowledged_by == "wall"
    # The owner's phone keeps its own pairing and tracker.
    session = (
        await call(handle_session, runtime_hass, Connection(owner, owner_tokens["phone"].id))
    )[0]
    assert session["recipient_id"] == "phone" and session["home"] is False
    assert_safety(manager)


def test_display_global_ack_defaults_to_off():
    raw = display()
    raw.pop("allow_global_ack")
    assert NotificationRecipient.from_dict(raw).allow_global_ack is False
    mobile = {
        "id": "phone",
        "name": "Phone",
        "notify_service": "notify.mobile_app_phone",
        "tracker_entity": "device_tracker.phone",
        "token": "t",
    }
    assert NotificationRecipient.from_dict(mobile).allow_global_ack is True


@pytest.mark.parametrize("kind", ["", "tablet", None, "Mobile"])
def test_unknown_kind_is_ignored_and_logged(caplog, kind):
    notifications_module._WARNED.clear()
    raw = {
        "id": f"typo_{kind}",
        "name": "Phone",
        "kind": kind,
        "notify_service": "notify.mobile_app_phone",
        "tracker_entity": "device_tracker.phone",
        "token": "t",
    }
    assert NotificationRecipient.from_dict(raw) is None
    assert f"typo_{kind}" in caplog.text and "unknown kind" in caplog.text


async def test_external_reset_rejects_an_unknown_kind(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    source = manager.external.sources["a"]
    raws = [{**r, "kind": "tablet"} for r in runtime_entry.options[CONF_NOTIFICATION_RECIPIENTS]]
    runtime_hass.config_entries.async_update_entry(
        runtime_entry, options={**runtime_entry.options, CONF_NOTIFICATION_RECIPIENTS: raws}
    )
    payload = {
        "action_kind": "EXTERNAL_RESET",
        "config_entry_id": runtime_entry.entry_id,
        "source_id": source.source_id,
        "source_generation": source.identity.generation,
        "event_id": source.event_id,
        "recipient_id": "phone",
        "recipient_token": "recipient_token",
        "reset_nonce": source.reset_nonce,
    }
    assert not await manager.async_external_reset(payload)
    assert manager.external.sources["a"].phase is ExternalPhase.ACTIVE
    # The same payload with a valid kind is accepted (the tracker is home).
    raws = [{**r, "kind": "mobile"} for r in raws]
    runtime_hass.config_entries.async_update_entry(
        runtime_entry, options={**runtime_entry.options, CONF_NOTIFICATION_RECIPIENTS: raws}
    )
    assert await manager.async_external_reset(payload)
