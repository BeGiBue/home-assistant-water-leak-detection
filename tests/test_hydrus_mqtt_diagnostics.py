"""Hydrus telegram simulation through real HA MQTT Sensor, queue and states.

Only the radio/broker transport and time are simulated. No detector durations,
reset settings or MQTT change-suppression algorithms are replaced.
"""

import json
from collections import deque
from datetime import timedelta

import pytest
from homeassistant.components.mqtt.models import DATA_MQTT, MqttData, ReceiveMessage
from homeassistant.components.mqtt.sensor import DISCOVERY_SCHEMA, MqttSensor
from homeassistant.config_entries import ConfigEntry

from custom_components.water_leak_detection.const import DOMAIN, DetectorKind, DetectorPhase
from custom_components.water_leak_detection.manager import WaterLeakManager

TOPIC = "wmbusmeters/hydrus"


class HydrusTransport:
    def __init__(self, hass, entry, clock, force_update):
        self.hass, self.clock = hass, clock
        from homeassistant import loader

        import custom_components

        loader.async_setup(hass)
        hass.data[loader.DATA_INTEGRATIONS][DOMAIN] = loader.Integration.resolve_from_root(
            hass, custom_components, DOMAIN
        )
        mqtt_entry = ConfigEntry(
            domain="mqtt",
            title="simulated broker transport",
            data={},
            options={},
            version=1,
            minor_version=1,
            source="user",
            unique_id=None,
            discovery_keys={},
            subentries_data=[],
        )
        config = DISCOVERY_SCHEMA(
            {
                "name": "Hydrus flow",
                "state_topic": TOPIC,
                "value_template": "{{ value_json.flow_m3h }}",
                "unit_of_measurement": "m³/h",
                "force_update": force_update,
                "unique_id": "hydrus_flow",
            }
        )
        self.sensor = MqttSensor(hass, config, mqtt_entry, None)
        self.sensor.entity_id = "sensor.flow"
        import logging
        from datetime import timedelta

        from homeassistant.helpers.entity import EntityPlatformState
        from homeassistant.helpers.entity_platform import EntityPlatform

        platform = EntityPlatform(
            hass=hass,
            logger=logging.getLogger(__name__),
            domain="sensor",
            platform_name="mqtt",
            platform=None,
            scan_interval=timedelta(seconds=30),
            entity_namespace=None,
        )
        self.sensor.add_to_platform_start(hass, platform, None)
        # Offline radio/broker transport: do not subscribe to a network broker.
        # The real MQTT callback, entity writes, registry and evidence remain intact.
        self.sensor._platform_state = EntityPlatformState.ADDED
        import logging

        from homeassistant.helpers import entity_registry as er
        from homeassistant.helpers.entity_component import EntityComponent

        registry = er.async_get(hass)
        if registry.async_get("sensor.flow"):
            registry.async_remove("sensor.flow")
        registered = registry.async_get_or_create(
            "sensor", "mqtt", "hydrus_flow", suggested_object_id="flow"
        )
        self.sensor.registry_entry = registered
        component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
        component._entities[self.sensor.entity_id] = self.sensor
        hass.data["sensor"] = component
        from types import SimpleNamespace

        self.data = MqttData(client=SimpleNamespace(connected=True), config=[])
        self.data.debug_info_entities["sensor.flow"] = {
            "subscriptions": {TOPIC: {"messages": deque(), "count": 0}}
        }
        hass.data[DATA_MQTT] = self.data
        self.total_m3 = 123.456
        self.telegram_id = 0
        total_config = DISCOVERY_SCHEMA(
            {
                "name": "Hydrus total",
                "state_topic": TOPIC,
                "value_template": "{{ value_json.total_m3 }}",
                "unit_of_measurement": "m³",
                "force_update": False,
                "unique_id": "hydrus_total",
                "state_class": "total_increasing",
            }
        )
        self.total_sensor = MqttSensor(hass, total_config, mqtt_entry, None)
        self.total_sensor.entity_id = "sensor.total"
        self.total_sensor.add_to_platform_start(hass, platform, None)
        self.total_sensor._platform_state = EntityPlatformState.ADDED
        self.total_sensor.registry_entry = registry.async_get_or_create(
            "sensor", "mqtt", "hydrus_total", suggested_object_id="total"
        )
        assert self.total_sensor.registry_entry.entity_id == self.total_sensor.entity_id
        component._entities["sensor.total"] = self.total_sensor
        self.data.debug_info_entities["sensor.total"] = {
            "subscriptions": {TOPIC: {"messages": deque(), "count": 0}}
        }
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "total_entity": "sensor.total"}
        )

    async def telegram(self, flow, seconds=60):
        self.clock.advance(seconds)
        self.telegram_id += 1
        self.total_m3 += float(flow) * seconds / 3600
        message = ReceiveMessage(
            TOPIC,
            json.dumps(
                {
                    "flow_m3h": flow,
                    "total_m3": self.total_m3,
                    "telegram_id": self.telegram_id,
                    # Original radio clock is independent of HA UTC rollback.
                    "timestamp": (
                        self.clock.origin + timedelta(seconds=self.clock.seconds)
                    ).isoformat(),
                }
            ),
            0,
            False,
            TOPIC,
            self.clock.utcnow().timestamp(),
        )
        self.sensor._message_callback(
            self.sensor._state_message_received,
            {"_attr_native_value", "_attr_last_reset", "_expired"},
            message,
        )
        self.total_sensor._message_callback(
            self.total_sensor._state_message_received,
            {"_attr_native_value", "_attr_last_reset", "_expired"},
            message,
        )
        self.data.state_write_requests.process_write_state_requests(message)
        await self.hass.async_block_till_done()
        # MQTT catches write errors internally: assert both real HA states so a
        # broken total/flow plumbing cannot silently make this regression pass.
        assert float(self.hass.states.get("sensor.flow").state) == pytest.approx(float(flow))
        assert float(self.hass.states.get("sensor.total").state) == pytest.approx(self.total_m3)


@pytest.mark.parametrize("force_update", [False, True])
async def test_identical_zero_telegrams_real_mqtt_pipeline(
    runtime_hass, runtime_entry, measurement_clock, force_update
):
    transport = HydrusTransport(runtime_hass, runtime_entry, measurement_clock, force_update)
    await transport.telegram(0.250, 0)
    assert runtime_hass.states.get("sensor.flow").state == "0.25"
    manager = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data.setdefault(DOMAIN, {})[runtime_entry.entry_id] = manager
    await manager.async_setup()
    for index in range(30):
        await transport.telegram(0.250 if index % 2 else 0.251)
    low = manager.engine.runtimes[DetectorKind.LOW_FLOW]
    assert low.phase is DetectorPhase.ACTIVE
    event_id = low.event_id
    await transport.telegram(0)
    first_zero = runtime_hass.states.get("sensor.flow").last_reported
    for _ in range(10):
        await transport.telegram(0)
        await manager._async_tick(measurement_clock.utcnow())
    if force_update:
        assert low.phase is DetectorPhase.IDLE
        assert runtime_hass.states.get("sensor.flow").last_reported != first_zero
    else:
        assert low.phase is DetectorPhase.ACTIVE and low.event_id == event_id
        assert runtime_hass.states.get("sensor.flow").last_reported == first_zero


async def running(hass, entry, clock, force=True, period=60):
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "total_entity": "sensor.total"}
    )
    transport = HydrusTransport(hass, entry, clock, force)
    await transport.telegram(0.250, 0)
    manager = WaterLeakManager(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    await manager.async_setup()
    for _ in range((1800 + period - 1) // period):
        await transport.telegram(0.250, period)
    assert manager.engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.ACTIVE
    return transport, manager


@pytest.mark.parametrize("period", [30, 60, 120, 300, 600])
async def test_realistic_periods_valid_zero_can_reset_only_on_completed_reports(
    runtime_hass, runtime_entry, measurement_clock, period
):
    transport, manager = await running(
        runtime_hass, runtime_entry, measurement_clock, period=period
    )
    low = manager.engine.runtimes[DetectorKind.LOW_FLOW]
    await transport.telegram(0, period)
    for _ in range(max(1, (180 + period - 1) // period)):
        await transport.telegram(0, period)
    assert low.phase is DetectorPhase.IDLE
    assert manager.source_max_age_seconds == 0


async def test_missing_radio_and_total_updates_never_advance_quiet(
    runtime_hass, runtime_entry, measurement_clock
):
    transport, manager = await running(runtime_hass, runtime_entry, measurement_clock)
    await transport.telegram(0)
    for _ in range(60):
        measurement_clock.advance(10)
        # Total sensor heartbeat is not a Flow report, regardless of zero volume delta.
        runtime_hass.states.async_set("sensor.total", "123.456", {"unit_of_measurement": "m³"})
        await manager._async_tick(measurement_clock.utcnow())
        await runtime_hass.async_block_till_done()
    assert manager.engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.ACTIVE
    assert manager.source_diagnostics()["low_reset_confirmed_seconds"] == 0
    assert manager.source_diagnostics()["last_valid_observation_age_seconds"] == 600


@pytest.mark.parametrize("invalid", ["unavailable", "unknown", "-1", "nan", "inf"])
async def test_outage_first_return_has_no_retroactive_quiet_credit(
    runtime_hass, runtime_entry, measurement_clock, invalid
):
    transport, manager = await running(runtime_hass, runtime_entry, measurement_clock)
    await transport.telegram(0)
    await transport.telegram(0, 120)
    event_id = manager.engine.runtimes[DetectorKind.LOW_FLOW].event_id
    runtime_hass.states.async_set("sensor.flow", invalid, {"unit_of_measurement": "m³/h"})
    await runtime_hass.async_block_till_done()
    measurement_clock.advance(600)
    await manager._async_tick(measurement_clock.utcnow())
    await transport.telegram(0, 0)
    assert manager.engine.runtimes[DetectorKind.LOW_FLOW].event_id == event_id
    assert manager.source_diagnostics()["low_reset_confirmed_seconds"] == 0
    assert manager._flow_evidence.credited_seconds == 0
    await transport.telegram(0, 179)
    assert manager.engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.ACTIVE
    assert manager.source_diagnostics()["low_reset_confirmed_seconds"] == 179
    await transport.telegram(0, 1)
    assert manager.engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.IDLE


@pytest.mark.parametrize("limit,expected", [(0, False), (30, True), (120, False)])
async def test_explicit_timeout_vs_sixty_second_telegram_cadence(
    runtime_hass, runtime_entry, measurement_clock, limit, expected
):
    transport, manager = await running(runtime_hass, runtime_entry, measurement_clock)
    await manager.async_update_options(
        {
            **runtime_entry.options,
            "source_max_age_seconds": limit,
            "source_gap_policy_explicit": True,
        }
    )
    await transport.telegram(0)
    for _ in range(10):
        await transport.telegram(0)
    assert (
        manager.engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.ACTIVE
    ) == expected
    assert manager.source_diagnostics()["source_max_age_seconds_stored"] == limit


async def test_restart_quiet_must_rebuild_and_duration_excludes_offline_time(
    runtime_hass, runtime_entry, measurement_clock
):
    transport, manager = await running(runtime_hass, runtime_entry, measurement_clock)
    await transport.telegram(0)
    await transport.telegram(0, 179)
    event_id = manager.engine.runtimes[DetectorKind.LOW_FLOW].event_id
    elapsed = manager.event_elapsed_seconds(event_id)
    await manager.async_unload()
    measurement_clock.advance(3600)
    restored = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    await restored.async_setup()
    assert restored.event_elapsed_seconds(event_id) == elapsed
    assert restored.source_diagnostics()["low_reset_confirmed_seconds"] == 0
    # The retained/cached pre-restart zero cannot start the physical quiet chain.
    # A genuinely new post-restart frame first establishes it with zero credit.
    await transport.telegram(0, 0)
    assert restored._flow_evidence.credited_seconds == 0
    await transport.telegram(0, 179)
    assert restored.engine.runtimes[DetectorKind.LOW_FLOW].event_id == event_id
    await transport.telegram(0, 1)
    assert restored.engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.IDLE


async def test_known_mqtt_force_update_warning_is_visible_and_repaired_when_enabled(
    runtime_hass, runtime_entry, measurement_clock
):
    from homeassistant.helpers import issue_registry as ir

    transport = HydrusTransport(runtime_hass, runtime_entry, measurement_clock, False)
    await transport.telegram(0.250, 0)
    manager = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data.setdefault(DOMAIN, {})[runtime_entry.entry_id] = manager
    await manager.async_setup()
    issue_id = f"{runtime_entry.entry_id}_mqtt_identical_reports"
    assert manager.source_diagnostics()["mqtt_identical_reports_may_be_suppressed"]
    assert (DOMAIN, issue_id) in ir.async_get(runtime_hass).issues
    # Apply a validated MQTT configuration just as discovery update would.
    transport.sensor._setup_from_config({**transport.sensor._config, "force_update": True})
    await transport.telegram(0.250)
    assert not manager.source_diagnostics()["mqtt_identical_reports_may_be_suppressed"]
    assert (DOMAIN, issue_id) not in ir.async_get(runtime_hass).issues


async def test_mqtt_expiry_shorter_than_radio_period_repeatedly_breaks_quiet(
    runtime_hass, runtime_entry, measurement_clock
):
    transport, manager = await running(runtime_hass, runtime_entry, measurement_clock)
    transport.sensor._setup_from_config({**transport.sensor._config, "expire_after": 45})
    await transport.telegram(0)
    for _ in range(5):
        measurement_clock.advance(46)
        # Execute MQTT's actual expiry callback at the simulated scheduler deadline.
        transport.sensor._value_is_expired()
        await runtime_hass.async_block_till_done()
        assert not manager.source_available
        await transport.telegram(0, 14)
        assert manager._flow_evidence.credited_seconds == 0
        assert manager.source_diagnostics()["low_reset_confirmed_seconds"] == 0
    assert manager.engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.ACTIVE
    assert manager.source_diagnostics()["mqtt_expire_after_seconds"] == 45
    transport.sensor._setup_from_config({**transport.sensor._config, "expire_after": 150})
    for _ in range(3):
        await transport.telegram(0)
    assert manager.engine.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.IDLE
    if transport.sensor._expiration_trigger:
        transport.sensor._expiration_trigger()
        transport.sensor._expiration_trigger = None


@pytest.mark.parametrize(
    "stored,explicit,effective",
    [(None, False, 0), (30, False, 0), (30, True, 30), (120, True, 120)],
)
async def test_stored_default_and_legacy_source_limit_diagnostics(
    runtime_hass, runtime_entry, stored, explicit, effective
):
    options = {"source_gap_policy_explicit": explicit}
    if stored is not None:
        options["source_max_age_seconds"] = stored
    runtime_hass.config_entries.async_update_entry(runtime_entry, options=options)
    manager = WaterLeakManager(runtime_hass, runtime_entry)
    data = manager.source_diagnostics()
    assert data["source_max_age_seconds_default"] == 0
    assert data["source_max_age_seconds_stored"] == stored
    assert data["source_max_age_seconds_effective"] == effective
