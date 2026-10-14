"""Sensors for Water Leak Guard."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime, UnitOfVolume, UnitOfVolumeFlowRate
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, DetectorKind
from .duration import human_duration
from .entity import WaterLeakEntity
from .manager import WaterLeakManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Water Leak Guard sensors."""
    manager: WaterLeakManager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            WaterLeakStatusSensor(manager),
            CurrentFlowSensor(manager),
            ActiveEventDurationSensor(manager),
            ActiveEventVolumeSensor(manager),
            BypassRemainingSensor(manager),
            LearnedMaximumFlowSensor(manager),
            LearningConfidenceSensor(manager),
            LearningCoverageSensor(manager),
            HydraulicReferenceFlowSensor(manager),
            EffectiveHighThresholdSensor(manager),
            EffectiveBurstThresholdSensor(manager),
            LongTermMaximumFlowSensor(manager),
        ]
    )


class WaterLeakStatusSensor(WaterLeakEntity, SensorEntity):
    """Overall detector state."""

    _attr_translation_key = "status"
    _attr_icon = "mdi:water-alert"

    def __init__(self, manager: WaterLeakManager) -> None:
        super().__init__(manager, "status")

    @property
    def native_value(self) -> str:
        if (
            self.manager.external.has_active_sources
            and not self.manager.engine.snapshot().alarm_active
        ):
            return "external_leak"
        if not self.manager.source_available:
            return "source_unavailable"
        return self.manager.engine.snapshot(self.manager.current_total_l).status

    @property
    def extra_state_attributes(self):
        display = self.manager.display_event()
        acknowledgement = self.manager.notifications.state_for(display["event_id"])
        return {
            "hydraulic_detectors": self.manager.hydraulic_diagnostics(),
            "measurement_diagnostics": self.manager.source_diagnostics(),
            "notification_events": {
                event_id: {
                    "globally_acknowledged": state.globally_acknowledged,
                    "globally_acknowledged_by": state.globally_acknowledged_by,
                    "muted_recipients": sorted(state.muted_recipients),
                    "accepted_recipient_ids": sorted(state.accepted_recipients),
                    "dispatch_states": dict(state.dispatch_states),
                }
                for event_id, state in self.manager.notifications.acknowledgements.items()
            },
            "hydraulic_active_events": list(self.manager.engine.active_events()),
            "external_sources": self.manager.external_diagnostics(),
            "aggregate_alarm_active": self.manager.alarm_active,
            "aggregate_shutoff_request": self.manager.shutoff_request,
            "learning_storage_ready": self.manager._migration_ready,
            "storage_recovery_required": self.manager._storage_load_failed,
            "measurement_source_generation": self.manager.measurement_source.generation,
            "learning_epoch": self.manager.measurement_source.learning_epoch,
            "legacy_learning_migration": self.manager.legacy_learning_migration,
            "flow_source": self.manager.flow_entity_id,
            "total_source": self.manager.total_entity_id,
            "source_available": self.manager.source_available,
            "active_event_id": display["event_id"],
            "active_detector": display["type"],
            "globally_acknowledged": (
                acknowledgement.globally_acknowledged if acknowledgement is not None else False
            ),
            "globally_acknowledged_by": (
                acknowledgement.globally_acknowledged_by if acknowledgement is not None else None
            ),
            "globally_acknowledged_at": (
                acknowledgement.globally_acknowledged_at.isoformat()
                if acknowledgement is not None
                and acknowledgement.globally_acknowledged_at is not None
                else None
            ),
            "muted_recipients": (
                sorted(acknowledgement.muted_recipients) if acknowledgement is not None else []
            ),
            "high_flow_bypass": self.manager.high_flow_bypass_active,
            "slow_leak_enabled": self.manager.engine.settings.slow_enabled,
            "low_flow_enabled": self.manager.engine.settings.low_enabled,
            "detectors": {
                kind.value: self.manager.engine.runtimes[kind].phase.value for kind in DetectorKind
            },
        }


class CurrentFlowSensor(WaterLeakEntity, SensorEntity):
    """Normalized source flow."""

    _attr_translation_key = "current_flow"
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_HOUR
    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:water-pump"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_suggested_display_precision = 1

    def __init__(self, manager: WaterLeakManager) -> None:
        super().__init__(manager, "current_flow")

    @property
    def available(self) -> bool:
        return self.manager.source_available and self.manager.current_flow_lph is not None

    @property
    def native_value(self) -> float | None:
        return self.manager.current_flow_lph


class ActiveEventDurationSensor(WaterLeakEntity, SensorEntity):
    """Duration of the highest priority active event."""

    _attr_translation_key = "active_event_duration"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:timer-alert-outline"

    def __init__(self, manager: WaterLeakManager) -> None:
        super().__init__(manager, "active_event_duration")

    @property
    def native_value(self) -> int:
        return int(self.manager.event_elapsed_seconds(self.manager.display_event()["event_id"]))

    @property
    def extra_state_attributes(self):
        display = self.manager.display_event()
        seconds = self.native_value
        return {
            "event_id": display["event_id"],
            "duration_human": human_duration(seconds, self.manager.hass.config.language),
            "duration_human_de": human_duration(seconds, "de"),
            "duration_human_en": human_duration(seconds, "en"),
            "started_at": display["started_at"].isoformat() if display["started_at"] else None,
            "active_since": display["detected_at"].isoformat() if display["detected_at"] else None,
            "duration_basis": "monitoring_start_excluding_ha_offline_time",
        }


class ActiveEventVolumeSensor(WaterLeakEntity, SensorEntity):
    """Water volume used since the highest priority event started."""

    _attr_translation_key = "active_event_volume"
    _attr_device_class = SensorDeviceClass.WATER
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_icon = "mdi:water-plus"
    _attr_suggested_display_precision = 1

    def __init__(self, manager: WaterLeakManager) -> None:
        super().__init__(manager, "active_event_volume")

    @property
    def native_value(self) -> float:
        return round(
            self.manager.engine.snapshot(self.manager.current_total_l).active_volume_l,
            2,
        )


class BypassRemainingSensor(WaterLeakEntity, SensorEntity):
    """Remaining High Flow bypass time."""

    _attr_translation_key = "high_flow_bypass_remaining"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:timer-sand"

    def __init__(self, manager: WaterLeakManager) -> None:
        super().__init__(manager, "high_flow_bypass_remaining")

    @property
    def native_value(self) -> int:
        return self.manager.bypass_remaining_seconds

    @property
    def extra_state_attributes(self):
        return {
            "active": self.manager.high_flow_bypass_active,
            "finishes_at": self.manager.bypass_until.isoformat()
            if self.manager.bypass_until
            else None,
        }


class LearnedMaximumFlowSensor(WaterLeakEntity, SensorEntity):
    """Robust rolling learned normal peak flow."""

    _attr_translation_key = "learned_maximum_flow"
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_HOUR
    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chart-timeline-variant"
    _attr_suggested_display_precision = 1

    def __init__(self, manager: WaterLeakManager) -> None:
        super().__init__(manager, "learned_maximum_flow")

    @property
    def native_value(self) -> float | None:
        value = self.manager.learning_snapshot.learned_max_lph
        return round(value, 1) if value is not None else None

    @property
    def extra_state_attributes(self):
        snapshot = self.manager.learning_snapshot
        return {
            "short_reference_lph": snapshot.short_reference_lph,
            "long_reference_lph": snapshot.long_reference_lph,
            "sample_count": snapshot.sample_count,
            "coverage_days": snapshot.coverage_days,
            "window_days": snapshot.window_days,
            "confidence": snapshot.confidence.value,
        }


class LearningConfidenceSensor(WaterLeakEntity, SensorEntity):
    """Confidence state of adaptive normal-flow learning."""

    _attr_translation_key = "learning_confidence"
    _attr_icon = "mdi:brain"

    def __init__(self, manager: WaterLeakManager) -> None:
        super().__init__(manager, "learning_confidence")

    @property
    def native_value(self) -> str:
        return self.manager.learning_snapshot.confidence.value

    @property
    def extra_state_attributes(self):
        snapshot = self.manager.learning_snapshot
        return {
            "sample_count": snapshot.sample_count,
            "coverage_days": snapshot.coverage_days,
            "age_days": snapshot.age_days,
            "window_days": snapshot.window_days,
        }


class LearningCoverageSensor(WaterLeakEntity, SensorEntity):
    """Number of days represented by admitted normal-use samples."""

    _attr_translation_key = "learning_coverage"
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:calendar-check-outline"

    def __init__(self, manager: WaterLeakManager) -> None:
        super().__init__(manager, "learning_coverage")

    @property
    def native_value(self) -> int:
        return self.manager.learning_snapshot.coverage_days

    @property
    def extra_state_attributes(self):
        snapshot = self.manager.learning_snapshot
        return {
            "learning_age_days": snapshot.age_days,
            "sample_count": snapshot.sample_count,
            "window_days": snapshot.window_days,
        }


class HydraulicReferenceFlowSensor(WaterLeakEntity, SensorEntity):
    """Heuristic hydraulic plausibility reference flow."""

    _attr_translation_key = "hydraulic_reference_flow"
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_HOUR
    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:pipe"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_suggested_display_precision = 0

    def __init__(self, manager: WaterLeakManager) -> None:
        super().__init__(manager, "hydraulic_reference_flow")

    @property
    def native_value(self) -> float:
        return round(self.manager.adaptive_thresholds().hydraulic_reference_lph, 0)


class EffectiveHighThresholdSensor(WaterLeakEntity, SensorEntity):
    """Configured static High Flow threshold."""

    _attr_translation_key = "effective_high_threshold"
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_HOUR
    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:water-alert-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_suggested_display_precision = 0

    def __init__(self, manager: WaterLeakManager) -> None:
        super().__init__(manager, "effective_high_threshold")

    @property
    def native_value(self) -> float:
        return round(self.manager.adaptive_thresholds().effective_high_lph, 0)


class EffectiveBurstThresholdSensor(WaterLeakEntity, SensorEntity):
    """Current adaptive absolute Burst Leak threshold."""

    _attr_translation_key = "effective_burst_threshold"
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_HOUR
    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:pipe-leak"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_suggested_display_precision = 0

    def __init__(self, manager: WaterLeakManager) -> None:
        super().__init__(manager, "effective_burst_threshold")

    @property
    def native_value(self) -> float:
        return round(self.manager.adaptive_thresholds().effective_burst_lph, 0)

    @property
    def extra_state_attributes(self):
        thresholds = self.manager.adaptive_thresholds()
        return {
            "configured_burst_base_lph": self.manager.engine.settings.burst_threshold_lph,
            "confirmed_long_term_normal_max_lph": (
                self.manager.long_term_learner.confirmed_long_term_normal_max_lph
            ),
            "normal_reference_lph": thresholds.normal_reference_lph,
            "hydraulic_reference_lph": thresholds.hydraulic_reference_lph,
            "hydraulic_model_is_plausibility_only": True,
        }


class LongTermMaximumFlowSensor(WaterLeakEntity, SensorEntity):
    """Persistent confirmed maximum, separate from seasonal rolling confidence."""

    _attr_translation_key = "long_term_normal_maximum"
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_HOUR
    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chart-line"

    def __init__(self, manager: WaterLeakManager) -> None:
        super().__init__(manager, "long_term_normal_maximum")

    @property
    def native_value(self) -> float | None:
        return self.manager.long_term_learner.confirmed_long_term_normal_max_lph

    @property
    def extra_state_attributes(self):
        learner = self.manager.long_term_learner
        return {
            "pending_count": len(learner.pending_high_candidates),
            "confirmed_history_count": len(learner.confirmed_high_history),
            "startup_guard_blocked": learner._high_blocked,
            "source_generation": learner.source_generation,
            "learning_epoch": learner.learning_epoch,
            "non_expiring": True,
        }
