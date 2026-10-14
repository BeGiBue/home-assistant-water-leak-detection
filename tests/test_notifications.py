"""Tests for notification recipient and acknowledgement primitives."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.water_leak_detection.const import (
    ACTION_ACK_ALL,
    ACTION_MUTE,
    RECIPIENT_ALLOW_GLOBAL_ACK,
    RECIPIENT_CRITICAL_ENABLED,
    RECIPIENT_ID,
    RECIPIENT_NAME,
    RECIPIENT_NOTIFY_SERVICE,
    RECIPIENT_TOKEN,
    RECIPIENT_TRACKER_ENTITY,
    RECIPIENT_TRUSTED_STATIONARY,
    DetectorKind,
    DetectorPhase,
)
from custom_components.water_leak_detection.notifications import (
    EventAcknowledgement,
    NotificationController,
    NotificationRecipient,
)


def _recipient_raw() -> dict[str, object]:
    return {
        RECIPIENT_ID: "ipad_home",
        RECIPIENT_NAME: "Home iPad",
        RECIPIENT_NOTIFY_SERVICE: "notify.mobile_app_ipad",
        RECIPIENT_TRACKER_ENTITY: "device_tracker.ipad",
        RECIPIENT_CRITICAL_ENABLED: True,
        RECIPIENT_ALLOW_GLOBAL_ACK: True,
        RECIPIENT_TRUSTED_STATIONARY: True,
        RECIPIENT_TOKEN: "secret-token",
    }


def test_recipient_parses_stationary_home_device() -> None:
    recipient = NotificationRecipient.from_dict(_recipient_raw())

    assert recipient is not None
    assert recipient.id == "ipad_home"
    assert recipient.notify_service == "notify.mobile_app_ipad"
    assert recipient.tracker_entity == "device_tracker.ipad"
    assert recipient.allow_global_ack is True
    assert recipient.trusted_stationary is True


def test_invalid_recipient_service_is_rejected() -> None:
    raw = _recipient_raw()
    raw[RECIPIENT_NOTIFY_SERVICE] = "persistent_notification.create"

    assert NotificationRecipient.from_dict(raw) is None


def test_event_acknowledgement_round_trip() -> None:
    acknowledged_at = datetime(2026, 10, 6, 8, 30, tzinfo=UTC)
    original = EventAcknowledgement(
        globally_acknowledged=True,
        globally_acknowledged_by="ipad_home",
        globally_acknowledged_at=acknowledged_at,
        muted_recipients={"iphone_benedikt"},
    )

    restored = EventAcknowledgement.from_dict(original.to_dict())

    assert restored.globally_acknowledged is True
    assert restored.globally_acknowledged_by == "ipad_home"
    assert restored.globally_acknowledged_at == acknowledged_at
    assert restored.muted_recipients == {"iphone_benedikt"}


def test_action_parser_accepts_mute_and_global_ack() -> None:
    mute = "WLD|MUTE|entry123|slow_leak_1|iphone|token"
    global_ack = "WLD|ACK_ALL|entry123|slow_leak_1|ipad|token2"

    assert NotificationController._parse_action(mute) == (
        ACTION_MUTE,
        "entry123",
        "slow_leak_1",
        "iphone",
        "token",
    )
    assert NotificationController._parse_action(global_ack) == (
        ACTION_ACK_ALL,
        "entry123",
        "slow_leak_1",
        "ipad",
        "token2",
    )


def test_action_parser_rejects_unknown_action() -> None:
    assert (
        NotificationController._parse_action("WLD|DELETE|entry123|slow_leak_1|iphone|token") is None
    )


class _FakeBus:
    def __init__(self) -> None:
        self.fired: list[tuple[str, dict[str, object]]] = []

    def async_fire(self, event_type: str, data: dict[str, object]) -> None:
        self.fired.append((event_type, data))


class _FakeStates:
    def __init__(self, states: dict[str, str]) -> None:
        self._states = states

    def get(self, entity_id: str):
        value = self._states.get(entity_id)
        return SimpleNamespace(state=value) if value is not None else None


class _FakeServices:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def has_service(self, domain: str, service: str) -> bool:
        return True

    async def async_call(
        self,
        domain: str,
        service: str,
        data: dict[str, object],
        *,
        blocking: bool,
    ) -> None:
        self.calls.append((domain, service, data))


class _FakeHass:
    def __init__(self, states: dict[str, str], *, language: str = "en") -> None:
        self.bus = _FakeBus()
        self.states = _FakeStates(states)
        self.services = _FakeServices()
        self.config = SimpleNamespace(language=language)


def _controller_for_action(*, tracker_state: str):
    hass = _FakeHass({"device_tracker.ipad": tracker_state})
    snapshot = SimpleNamespace(
        active_event_id="slow_leak_1",
        active_kind=SimpleNamespace(value="slow_leak"),
        active_volume_l=12.0,
        active_started_at=datetime(2026, 10, 6, 7, 0, tzinfo=UTC),
    )
    manager = SimpleNamespace(
        current_total_l=None,
        current_flow_lph=7.0,
        engine=SimpleNamespace(
            snapshot=lambda _total: snapshot,
            active_events=lambda: {"slow_leak_1": DetectorKind.SLOW_LEAK},
            runtimes={
                DetectorKind.SLOW_LEAK: SimpleNamespace(
                    plausible_volume_l=12.0,
                    started_at=snapshot.active_started_at,
                    phase=DetectorPhase.ACTIVE,
                    event_id="slow_leak_1",
                )
            },
        ),
    )
    entry = SimpleNamespace(entry_id="entry123", options={})
    persisted: list[bool] = []
    controller = NotificationController(
        hass,
        entry,
        manager,
        lambda: persisted.append(True),
    )
    controller._async_common_translations = AsyncMock(return_value={})
    recipient = NotificationRecipient.from_dict(_recipient_raw())
    assert recipient is not None
    controller.recipients = {recipient.id: recipient}
    return controller, recipient, hass, persisted


@pytest.mark.asyncio
async def test_remote_device_can_mute_only_itself() -> None:
    controller, recipient, _hass, persisted = _controller_for_action(tracker_state="not_home")
    event = SimpleNamespace(
        data={"action": (f"WLD|MUTE|entry123|slow_leak_1|{recipient.id}|{recipient.token}")}
    )

    await controller._async_mobile_action(event)

    state = controller.acknowledgements["slow_leak_1"]
    assert recipient.id in state.muted_recipients
    assert state.globally_acknowledged is False
    assert persisted


@pytest.mark.asyncio
async def test_remote_device_cannot_acknowledge_globally() -> None:
    controller, recipient, hass, persisted = _controller_for_action(tracker_state="not_home")
    controller._async_send_feedback = AsyncMock()
    event = SimpleNamespace(
        data={"action": (f"WLD|ACK_ALL|entry123|slow_leak_1|{recipient.id}|{recipient.token}")}
    )

    await controller._async_mobile_action(event)

    state = controller.acknowledgements["slow_leak_1"]
    assert state.globally_acknowledged is False
    assert not persisted
    assert any(data.get("reason") == "device_not_home" for _event_type, data in hass.bus.fired)


@pytest.mark.asyncio
async def test_home_device_can_acknowledge_globally() -> None:
    controller, recipient, _hass, persisted = _controller_for_action(tracker_state="home")
    event = SimpleNamespace(
        data={"action": (f"WLD|ACK_ALL|entry123|slow_leak_1|{recipient.id}|{recipient.token}")}
    )

    await controller._async_mobile_action(event)

    state = controller.acknowledgements["slow_leak_1"]
    assert state.globally_acknowledged is True
    assert state.globally_acknowledged_by == recipient.id
    assert state.globally_acknowledged_at is not None
    assert persisted


@pytest.mark.asyncio
async def test_arriving_home_retriggers_unacknowledged_alarm() -> None:
    controller, recipient, _hass, persisted = _controller_for_action(tracker_state="home")
    controller.acknowledgements["slow_leak_1"] = EventAcknowledgement(
        muted_recipients={recipient.id}
    )
    controller._async_send_event_notification = AsyncMock()
    event = SimpleNamespace(
        data={
            "entity_id": recipient.tracker_entity,
            "old_state": SimpleNamespace(state="not_home"),
            "new_state": SimpleNamespace(state="home"),
        }
    )

    await controller._async_tracker_changed(event)

    assert recipient.id not in controller.acknowledgements["slow_leak_1"].muted_recipients
    controller._async_send_event_notification.assert_awaited_once()
    assert persisted


@pytest.mark.asyncio
async def test_arriving_home_does_not_retrigger_globally_acknowledged_event() -> None:
    controller, recipient, _hass, _persisted = _controller_for_action(tracker_state="home")
    controller.acknowledgements["slow_leak_1"] = EventAcknowledgement(globally_acknowledged=True)
    controller._async_send_event_notification = AsyncMock()
    event = SimpleNamespace(
        data={
            "entity_id": recipient.tracker_entity,
            "old_state": SimpleNamespace(state="not_home"),
            "new_state": SimpleNamespace(state="home"),
        }
    )

    await controller._async_tracker_changed(event)

    controller._async_send_event_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_event_start_notifies_multiple_devices() -> None:
    controller, recipient, _hass, _persisted = _controller_for_action(tracker_state="home")
    second_raw = _recipient_raw()
    second_raw[RECIPIENT_ID] = "iphone_personal"
    second_raw[RECIPIENT_NAME] = "Personal iPhone"
    second_raw[RECIPIENT_NOTIFY_SERVICE] = "notify.mobile_app_iphone"
    second_raw[RECIPIENT_TRACKER_ENTITY] = "device_tracker.iphone"
    second_raw[RECIPIENT_TOKEN] = "other-token"
    second = NotificationRecipient.from_dict(second_raw)
    assert second is not None
    controller.recipients[second.id] = second
    controller._async_send_event_notification = AsyncMock()

    event = SimpleNamespace(
        data={
            "config_entry_id": "entry123",
            "event_id": "slow_leak_1",
            "type": "slow_leak",
            "flow_lph": 7.0,
            "volume_l": 7.0,
        }
    )

    await controller._async_leak_started(event)

    assert controller._async_send_event_notification.await_count == 2
    assert "slow_leak_1" in controller.acknowledgements


@pytest.mark.asyncio
async def test_event_end_removes_ack_and_new_event_starts_clean() -> None:
    controller, recipient, _hass, _persisted = _controller_for_action(tracker_state="home")
    controller._async_send_event_notification = AsyncMock()
    controller.acknowledgements["slow_leak_old"] = EventAcknowledgement(
        globally_acknowledged=True,
        globally_acknowledged_by=recipient.id,
    )

    await controller._async_leak_ended(
        SimpleNamespace(
            data={
                "config_entry_id": "entry123",
                "event_id": "slow_leak_old",
            }
        )
    )
    assert "slow_leak_old" not in controller.acknowledgements

    await controller._async_leak_started(
        SimpleNamespace(
            data={
                "config_entry_id": "entry123",
                "event_id": "slow_leak_new",
                "type": "slow_leak",
            }
        )
    )

    new_state = controller.acknowledgements["slow_leak_new"]
    assert new_state.globally_acknowledged is False
    assert new_state.muted_recipients == set()


@pytest.mark.asyncio
async def test_burst_critical_payload_supports_ios_and_android() -> None:
    controller, recipient, hass, _persisted = _controller_for_action(tracker_state="home")

    await controller._async_send_event_notification(
        recipient,
        "burst_leak_1",
        "burst_leak",
        {"flow_lph": 2500.0, "volume_l": 20.0},
        returning_home=False,
    )

    assert len(hass.services.calls) == 1
    domain, service, service_data = hass.services.calls[0]
    assert domain == "notify"
    assert service == "mobile_app_ipad"

    payload = service_data["data"]
    assert payload["ttl"] == 0
    assert payload["priority"] == "high"
    assert payload["channel"] == "alarm_stream"
    assert payload["push"]["interruption-level"] == "critical"


@pytest.mark.asyncio
async def test_away_notification_only_offers_personal_mute() -> None:
    controller, recipient, hass, _persisted = _controller_for_action(tracker_state="not_home")

    await controller._async_send_event_notification(
        recipient,
        "slow_leak_1",
        "slow_leak",
        {"flow_lph": 7.0},
        returning_home=False,
    )

    payload = hass.services.calls[0][2]["data"]
    actions = payload["actions"]
    assert len(actions) == 1
    assert "|MUTE|" in actions[0]["action"]


@pytest.mark.asyncio
async def test_home_notification_offers_global_acknowledgement() -> None:
    controller, recipient, hass, _persisted = _controller_for_action(tracker_state="home")

    await controller._async_send_event_notification(
        recipient,
        "slow_leak_1",
        "slow_leak",
        {"flow_lph": 7.0},
        returning_home=False,
    )

    payload = hass.services.calls[0][2]["data"]
    actions = payload["actions"]
    assert len(actions) == 2
    assert any("|ACK_ALL|" in action["action"] for action in actions)


@pytest.mark.asyncio
async def test_notification_uses_home_assistant_language_strings() -> None:
    controller, recipient, hass, _persisted = _controller_for_action(tracker_state="home")
    controller._async_common_translations = AsyncMock(
        return_value={
            "detector_slow_leak": "Slow Leak",
            "notification_title": "Wasserwächter: {detector}",
            "notification_current_flow": "Aktueller Durchfluss: {flow} L/h.",
            "action_mute_device": "Auf diesem Gerät stummschalten",
            "action_ack_all": "Für alle quittieren",
        }
    )

    await controller._async_send_event_notification(
        recipient,
        "slow_leak_1",
        "slow_leak",
        {"flow_lph": 7.0},
        returning_home=False,
    )

    service_data = hass.services.calls[0][2]
    assert service_data["title"] == "Wasserwächter: Slow Leak"
    assert service_data["message"] == "Aktueller Durchfluss: 7.0 L/h."
    assert service_data["data"]["actions"][0]["title"] == ("Auf diesem Gerät stummschalten")
    assert service_data["data"]["actions"][1]["title"] == "Für alle quittieren"


@pytest.mark.asyncio
async def test_runtime_translation_loader_uses_home_assistant_language(
    monkeypatch,
) -> None:
    controller, _recipient, _hass, _persisted = _controller_for_action(tracker_state="home")
    controller.hass.config.language = "de"

    async def _fake_get_translations(
        hass,
        language,
        category,
        integrations,
    ):
        assert language == "de"
        assert category == "common"
        assert list(integrations) == ["water_leak_detection"]
        return {"component.water_leak_detection.common.action_ack_all": ("Für alle quittieren")}

    monkeypatch.setattr(
        "custom_components.water_leak_detection.notifications.translation.async_get_translations",
        _fake_get_translations,
    )
    controller._async_common_translations = (
        NotificationController._async_common_translations.__get__(
            controller,
            NotificationController,
        )
    )

    strings = await controller._async_common_translations()

    assert strings["action_ack_all"] == "Für alle quittieren"
