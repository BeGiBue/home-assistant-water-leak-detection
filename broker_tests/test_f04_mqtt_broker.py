import asyncio
import json
import socket

import paho.mqtt.client as paho
import pytest
from amqtt.broker import Broker
from homeassistant import loader
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er

import custom_components
from custom_components.water_leak_detection.const import DOMAIN, DetectorKind, DetectorPhase
from custom_components.water_leak_detection.manager import WaterLeakManager


@pytest.mark.asyncio
@pytest.mark.parametrize("qos", [0, 1, 2])
@pytest.mark.parametrize("clean_session", [False, True])
async def test_real_broker_discovery_reconnect_retained_qos(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch, qos, clean_session
):
    hass = runtime_hass
    from pathlib import Path

    Path(hass.config.path("configuration.yaml")).write_text("{}\n")
    from homeassistant.auth import auth_manager_from_config as setup_auth

    hass.auth = await setup_auth(hass, [{"type": "homeassistant"}], [])
    port_sock = socket.socket()
    port_sock.bind(("127.0.0.1", 0))
    port = port_sock.getsockname()[1]
    port_sock.close()
    broker = Broker(
        {
            "listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{port}"}},
            "plugins": {
                "amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True}
            },
        }
    )
    await broker.start()
    print("Broker ready", flush=True)
    publisher = paho.Client(
        paho.CallbackAPIVersion.VERSION2,
        client_id="f04-radio-publisher",
        protocol=paho.MQTTv311,
        clean_session=clean_session,
    )
    print("Publisher connecting", flush=True)
    publisher.connect("127.0.0.1", port)
    publisher.loop_start()
    entry = ConfigEntry(
        domain="mqtt",
        title="Actual test broker",
        data={"broker": "127.0.0.1", "port": port, "protocol": "3.1.1"},
        options={"discovery": True},
        version=2,
        minor_version=1,
        source="user",
        unique_id=None,
        discovery_keys={},
        subentries_data=[],
    )
    hass.config_entries._entries[entry.entry_id] = entry
    loader.async_setup(hass)
    hass.data[loader.DATA_INTEGRATIONS][DOMAIN] = loader.Integration.resolve_from_root(
        hass, custom_components, DOMAIN
    )
    # The fixture's inline executor cannot execute a synchronous protocol probe
    # against its own async broker. The actual 3.1.1 connection and traffic stay real.
    monkeypatch.setattr("homeassistant.components.mqtt.try_connection", lambda *_: False)
    manager = None

    async def eventually(predicate):
        async with asyncio.timeout(10):
            while not predicate():
                await asyncio.sleep(0.01)

    async def publish(topic, packet, retain=False):
        previous_state = hass.states.get("sensor.review_flow")
        info = publisher.publish(topic, json.dumps(packet), qos=qos, retain=retain)
        await eventually(info.is_published)
        if topic == "review/hydrus":
            # Wait for actual receiver/HA processing, not a guessed network delay.
            await eventually(lambda: hass.states.get("sensor.review_flow") is not previous_state)
        await hass.async_block_till_done()

    try:
        print("HA MQTT setup", flush=True)
        assert await hass.config_entries.async_setup(entry.entry_id)
        print("HA MQTT setup done", flush=True)
        await eventually(lambda: hass.data["mqtt"].client.connected)
        await publish(
            "homeassistant/sensor/review_flow/config",
            {
                "name": "Review flow",
                "unique_id": "review_flow",
                "state_topic": "review/hydrus",
                "value_template": "{{ value_json.flow_m3h }}",
                "unit_of_measurement": "m³/h",
                "force_update": True,
                "qos": qos,
            },
            True,
        )
        await eventually(lambda: er.async_get(hass).async_get("sensor.review_flow") is not None)
        await eventually(lambda: bool(broker._subscriptions.get("review/hydrus")))
        hass.config_entries.async_update_entry(
            runtime_entry, data={"flow_entity": "sensor.review_flow"}, options={"shutoff_low": True}
        )
        await publish(
            "review/hydrus", {"flow_m3h": 0.25, "timestamp": measurement_clock.utcnow().isoformat()}
        )
        manager = WaterLeakManager(hass, runtime_entry)
        hass.data.setdefault(DOMAIN, {})[runtime_entry.entry_id] = manager
        await manager.async_setup()
        for _ in range(30):
            measurement_clock.advance(60)
            await publish(
                "review/hydrus",
                {"flow_m3h": 0.25, "timestamp": measurement_clock.utcnow().isoformat()},
            )
        low = manager.engine.runtimes[DetectorKind.LOW_FLOW]
        assert low.phase is DetectorPhase.ACTIVE and manager.shutoff_request
        old = {"flow_m3h": 0, "timestamp": "2026-10-06T00:00:00Z"}
        for _ in range(4):
            measurement_clock.advance(60)
            await publish("review/hydrus", old, True)
        assert low.phase is DetectorPhase.ACTIVE and manager.shutoff_request
        # Unload/reconnect MQTT: retained discovery and stale retained measurement
        # are delivered by the real broker, not fabricated callback messages.
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await eventually(lambda: hass.data["mqtt"].client.connected)
        await eventually(lambda: bool(broker._subscriptions.get("review/hydrus")))
        await asyncio.sleep(0.1)
        await hass.async_block_till_done()
        assert low.phase is DetectorPhase.ACTIVE and manager.shutoff_request
        publisher.disconnect()
        publisher.loop_stop()
        publisher.reconnect()
        publisher.loop_start()
        await eventually(publisher.is_connected)
        for _ in range(4):
            measurement_clock.advance(60)
            await publish(
                "review/hydrus",
                {"flow_m3h": 0, "timestamp": measurement_clock.utcnow().isoformat()},
            )
        assert low.phase is DetectorPhase.IDLE and not manager.shutoff_request
    finally:
        import sys

        print("Cleanup, original exception:", sys.exc_info(), flush=True)
        publisher.disconnect()
        publisher.loop_stop()
        if manager:
            await manager.async_unload()
        if entry.state.value == "loaded":
            await hass.config_entries.async_unload(entry.entry_id)
        await asyncio.wait_for(broker.shutdown(), 3)
