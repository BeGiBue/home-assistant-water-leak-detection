"""Constants for Water Leak Guard."""

from __future__ import annotations

from enum import StrEnum

from homeassistant.const import Platform

DOMAIN = "water_leak_detection"
NAME = "Water Leak Guard"
VERSION = "1.2.0-beta.3"

PLATFORMS: tuple[Platform, ...] = (
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
)

CONF_FLOW_ENTITY = "flow_entity"
CONF_SOURCE_MAX_AGE_SEC = "source_max_age_seconds"
CONF_SOURCE_GAP_EXPLICIT = "source_gap_policy_explicit"
DEFAULT_SOURCE_MAX_AGE_SEC = 0.0
CONF_TOTAL_ENTITY = "total_entity"
CONF_SOURCE_MODE = "source_mode"
CONF_SOURCE_DEVICE = "source_device"
CONF_NOTIFICATION_RECIPIENTS = "notification_recipients"

RECIPIENT_ID = "id"
RECIPIENT_NAME = "name"
RECIPIENT_NOTIFY_SERVICE = "notify_service"
RECIPIENT_TRACKER_ENTITY = "tracker_entity"
RECIPIENT_CRITICAL_ENABLED = "critical_enabled"
RECIPIENT_ALLOW_GLOBAL_ACK = "allow_global_ack"
RECIPIENT_TRUSTED_STATIONARY = "trusted_stationary"
RECIPIENT_TOKEN = "token"

CONF_SLOW_ENABLED = "slow_enabled"
CONF_SLOW_THRESHOLD_LPH = "slow_threshold_lph"
CONF_SLOW_DETECTION_MIN = "slow_detection_minutes"
CONF_SLOW_RESET_MIN = "slow_reset_minutes"
CONF_LOW_ENABLED = "low_enabled"
CONF_LOW_THRESHOLD_LPH = "low_threshold_lph"
CONF_LOW_DETECTION_MIN = "low_detection_minutes"
CONF_LOW_QUIET_LPH = "low_quiet_lph"
CONF_LOW_RESET_MIN = "low_reset_minutes"
CONF_LOW_STABILITY_ENABLED = "low_stability_enabled"
CONF_LOW_STABILITY_EARLY_MIN = "low_stability_early_minutes"
CONF_LOW_STABILITY_WINDOW_MIN = "low_stability_window_minutes"
CONF_LOW_STABILITY_RELATIVE_PERCENT = "low_stability_relative_percent"
CONF_LOW_STABILITY_ABSOLUTE_LPH = "low_stability_absolute_lph"
CONF_LOW_STABILITY_REQUIRED_PERCENT = "low_stability_required_percent"
CONF_HIGH_THRESHOLD_LPH = "high_threshold_lph"
CONF_HIGH_DETECTION_MIN = "high_detection_minutes"
CONF_HIGH_VOLUME_L = "high_volume_l"
CONF_HIGH_QUIET_LPH = "high_quiet_lph"
CONF_HIGH_RESET_MIN = "high_reset_minutes"
CONF_BURST_THRESHOLD_LPH = "burst_threshold_lph"
CONF_BURST_DETECTION_SEC = "burst_detection_seconds"
CONF_BURST_RESET_LPH = "burst_reset_lph"
CONF_BURST_RESET_SEC = "burst_reset_seconds"
CONF_BYPASS_DEFAULT_MIN = "bypass_default_minutes"
CONF_LEARNING_WINDOW_DAYS = "learning_window_days"
CONF_MANUAL_MAX_FLOW_LPH = "manual_max_flow_lph"
CONF_PIPE_DIAMETER_MM = "pipe_diameter_mm"
CONF_STATIC_PRESSURE_BAR = "static_pressure_bar"
CONF_HIGH_LEARNED_MULTIPLIER = "high_learned_multiplier"
CONF_BURST_LEARNED_MULTIPLIER = "burst_learned_multiplier"
CONF_HYDRAULIC_BURST_FRACTION = "hydraulic_burst_fraction"
CONF_BURST_RATE_RISE_LPH_10S = "burst_rate_rise_lph_10s"
CONF_BURST_RATE_CONFIRM_SEC = "burst_rate_confirm_seconds"

CONF_SHUTOFF_SLOW = "shutoff_slow"
CONF_SHUTOFF_LOW = "shutoff_low"
CONF_SHUTOFF_HIGH = "shutoff_high"
CONF_SHUTOFF_BURST = "shutoff_burst"

DEFAULT_SLOW_ENABLED = True
DEFAULT_SLOW_THRESHOLD_LPH = 3.0
DEFAULT_SLOW_DETECTION_MIN = 60.0
DEFAULT_SLOW_RESET_MIN = 10.0
DEFAULT_LOW_ENABLED = True
DEFAULT_LOW_THRESHOLD_LPH = 150.0
DEFAULT_LOW_DETECTION_MIN = 60.0
DEFAULT_LOW_QUIET_LPH = 20.0
DEFAULT_LOW_RESET_MIN = 3.0
DEFAULT_LOW_STABILITY_ENABLED = True
DEFAULT_LOW_STABILITY_EARLY_MIN = 30.0
DEFAULT_LOW_STABILITY_WINDOW_MIN = 15.0
DEFAULT_LOW_STABILITY_RELATIVE_PERCENT = 10.0
DEFAULT_LOW_STABILITY_ABSOLUTE_LPH = 20.0
DEFAULT_LOW_STABILITY_REQUIRED_PERCENT = 90.0
DEFAULT_HIGH_THRESHOLD_LPH = 600.0
DEFAULT_HIGH_DETECTION_MIN = 45.0
DEFAULT_HIGH_VOLUME_L = 500.0
DEFAULT_HIGH_QUIET_LPH = 100.0
DEFAULT_HIGH_RESET_MIN = 5.0
DEFAULT_BURST_THRESHOLD_LPH = 3500.0
DEFAULT_BURST_DETECTION_SEC = 30.0
DEFAULT_BURST_RESET_LPH = 500.0
DEFAULT_BURST_RESET_SEC = 60.0
DEFAULT_BYPASS_DEFAULT_MIN = 240.0
DEFAULT_LEARNING_WINDOW_DAYS = 30
DEFAULT_MANUAL_MAX_FLOW_LPH = 0.0
DEFAULT_PIPE_DIAMETER_MM = 25.0
DEFAULT_STATIC_PRESSURE_BAR = 3.5
DEFAULT_HIGH_LEARNED_MULTIPLIER = 1.20
DEFAULT_BURST_LEARNED_MULTIPLIER = 1.80
DEFAULT_HYDRAULIC_BURST_FRACTION = 0.75
DEFAULT_BURST_RATE_RISE_LPH_10S = 1000.0
DEFAULT_BURST_RATE_CONFIRM_SEC = 10.0

DEFAULT_SHUTOFF_SLOW = False
DEFAULT_SHUTOFF_LOW = False
DEFAULT_SHUTOFF_HIGH = False
DEFAULT_SHUTOFF_BURST = True

STORAGE_VERSION = 2
STORAGE_KEY_PREFIX = f"{DOMAIN}.runtime"
TICK_SECONDS = 10

SERVICE_START_HIGH_FLOW_BYPASS = "start_high_flow_bypass"
SERVICE_CANCEL_HIGH_FLOW_BYPASS = "cancel_high_flow_bypass"
SERVICE_RESET_LEARNING = "reset_learning"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_DURATION_MINUTES = "duration_minutes"

EVENT_LEAK_STARTED = f"{DOMAIN}_event_started"
EVENT_LEAK_ENDED = f"{DOMAIN}_event_ended"
EVENT_SHUTOFF_REQUESTED = f"{DOMAIN}_shutoff_requested"
EVENT_SHUTOFF_CLEARED = f"{DOMAIN}_shutoff_cleared"
EVENT_ACKNOWLEDGED = f"{DOMAIN}_acknowledged"
EVENT_ACK_REJECTED = f"{DOMAIN}_ack_rejected"

MOBILE_ACTION_EVENT = "mobile_app_notification_action"
ACTION_PREFIX = "WLD"
ACTION_MUTE = "MUTE"
ACTION_ACK_ALL = "ACK_ALL"
ACTION_EXTERNAL_RESET = "EXTERNAL_RESET"
RECIPIENT_ALLOW_EXTERNAL_RESET = "allow_external_reset"
CONF_EXTERNAL_SENSORS = "external_sensors"
SERVICE_EXTERNAL_RESET = "external_reset"


class DetectorKind(StrEnum):
    """Leak detector kinds ordered by severity."""

    SLOW_LEAK = "slow_leak"
    LOW_FLOW = "low_flow"
    HIGH_FLOW = "high_flow"
    BURST_LEAK = "burst_leak"


DETECTOR_PRIORITY: tuple[DetectorKind, ...] = (
    DetectorKind.SLOW_LEAK,
    DetectorKind.LOW_FLOW,
    DetectorKind.HIGH_FLOW,
    DetectorKind.BURST_LEAK,
)


class DetectorPhase(StrEnum):
    """Runtime phase of one detector."""

    IDLE = "idle"
    MONITORING = "monitoring"
    ACTIVE = "active"
