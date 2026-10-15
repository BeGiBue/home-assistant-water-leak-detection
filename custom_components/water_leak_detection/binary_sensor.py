"""Binary sensors for Water Leak Guard."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .entity import WaterLeakEntity
from .manager import WaterLeakManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Water Leak Guard binary sensors."""
    manager: WaterLeakManager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LeakAlarmBinarySensor(manager), ShutoffRequestBinarySensor(manager)])


class LeakAlarmBinarySensor(WaterLeakEntity, BinarySensorEntity):
    """Whether any leak detector is active."""

    _attr_translation_key = "leak_alarm"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:pipe-leak"

    def __init__(self, manager: WaterLeakManager) -> None:
        super().__init__(manager, "leak_alarm")

    @property
    def is_on(self) -> bool:
        return self.manager.alarm_active

    @property
    def extra_state_attributes(self):
        snapshot = self.manager.engine.snapshot(self.manager.current_total_l)
        return {
            "hydraulic_active_events": list(self.manager.engine.active_events()),
            "external_sources": self.manager.external_diagnostics(),
            "status": snapshot.status,
            "event_id": snapshot.active_event_id,
            "detector": snapshot.active_kind.value if snapshot.active_kind else None,
        }


class ShutoffRequestBinarySensor(WaterLeakEntity, BinarySensorEntity):
    """Independent request for an external motorized shutoff valve."""

    # Icon by state from icons.json (translation key "shutoff_request"):
    # off = valve open (no shutoff requested), on = valve closed (requested).
    _attr_translation_key = "shutoff_request"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, manager: WaterLeakManager) -> None:
        super().__init__(manager, "shutoff_request")

    @property
    def is_on(self) -> bool:
        return self.manager.shutoff_request

    @property
    def extra_state_attributes(self):
        snapshot = self.manager.engine.snapshot(self.manager.current_total_l)
        return {
            "hydraulic_shutoff": snapshot.shutoff_request,
            "external_shutoff": self.manager.external.shutoff_request,
            "external_sources": self.manager.external_diagnostics(),
            "decoupled_from_alarm_acknowledgement": True,
            "status": snapshot.status,
            "event_id": snapshot.active_event_id,
        }
