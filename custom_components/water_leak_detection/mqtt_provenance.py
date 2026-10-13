"""Fail-closed physical MQTT evidence, independent of HA reception timestamps.

The HA MQTT adapter exposes the original state-topic message in its bounded debug
queue. This is a read-only, version-tested bridge; missing adapter data never falls
back to treating reception/force_update as proof of a physical measurement.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from .validation import parse_datetime

MAX_MEASUREMENT_DELIVERY_AGE_SECONDS = 300
MAX_MEASUREMENT_FUTURE_SKEW_SECONDS = 2
MAX_PAYLOAD_BYTES = 65536


class MqttProvenance:
    """Durable per-generation strictly increasing original measurement timestamp."""

    def __init__(self, generation: str) -> None:
        self.generation = generation
        self.timestamp = None
        self.sequence = None
        self.started_at = None
        self.reason = "awaiting_original_measurement"

    def restore(self, raw) -> None:
        if isinstance(raw, dict) and raw.get("source_generation") == self.generation:
            self.timestamp = parse_datetime(raw.get("measurement_timestamp"))
            seq = raw.get("telegram_id")
            self.sequence = seq if type(seq) is int and 0 <= seq < 2**63 else None

    def to_dict(self) -> dict:
        return {
            "source_generation": self.generation,
            "measurement_timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "telegram_id": self.sequence,
        }

    def validate(self, hass, entity_id, state, now):
        """Return a new provenance marker or refuse all consumption/reset credit."""
        if self.started_at is None:
            self.started_at = now
        component = hass.data.get("sensor")
        entity = component.get_entity(entity_id) if hasattr(component, "get_entity") else None
        config = getattr(entity, "_config", {})
        if not isinstance(config, Mapping):
            self.reason = "unsupported_mqtt_adapter"
            return None
        topic = config.get("state_topic")
        data = hass.data.get("mqtt")
        info = getattr(data, "debug_info_entities", {}).get(entity_id, {})
        messages = info.get("subscriptions", {}).get(topic, {}).get("messages", ())
        self.reason = "original_measurement_missing"
        if not messages:
            return None
        msg = messages[-1]
        if msg.topic != topic or msg.retain:
            self.reason = "retained_or_unbound_message"
            return None
        payload = msg.payload
        if not isinstance(payload, (str, bytes)) or len(payload) > MAX_PAYLOAD_BYTES:
            return None
        try:
            raw = json.loads(payload)
        except ValueError, TypeError, UnicodeError:
            return None
        stamp = parse_datetime(raw.get("timestamp")) if isinstance(raw, dict) else None
        if stamp is None:
            return None
        if stamp < self.started_at:
            self.reason = "pre_startup_measurement"
            return None
        # Match the actual MQTT entity rendering; an unrelated HA state write is
        # not a measurement even when it happens to share a numerical flow.
        if str(getattr(entity, "native_value", None)) != state.state:
            self.reason = "unbound_rendered_state"
            return None
        seq = raw.get("telegram_id")
        if "telegram_id" in raw and not (type(seq) is int and 0 <= seq < 2**63):
            self.reason = "invalid_original_identity"
            return None
        seq = seq if type(seq) is int and 0 <= seq < 2**63 else None
        same_time_new_frame = (
            stamp == self.timestamp
            and seq is not None
            and self.sequence is not None
            and seq > self.sequence
        )
        if self.timestamp is not None and (
            stamp < self.timestamp or (stamp == self.timestamp and not same_time_new_frame)
        ):
            self.reason = "replayed_or_out_of_order_measurement"
            return None
        age = (now - stamp).total_seconds()
        if age < -MAX_MEASUREMENT_FUTURE_SKEW_SECONDS:
            self.reason = "future_measurement"
            return None
        if age > MAX_MEASUREMENT_DELIVERY_AGE_SECONDS:
            self.reason = "stale_measurement"
            return None
        self.reason = "verified_original_measurement"
        return stamp, seq

    def commit(self, marker) -> None:
        self.timestamp, self.sequence = marker
