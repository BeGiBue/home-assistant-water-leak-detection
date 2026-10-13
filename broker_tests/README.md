# Optional real MQTT broker regression tests

Run separately from the default tests/ suite in an isolated test environment with
Home Assistant 2026.9.4, Python 3.14.2 and amqtt==0.11.3. Never install broker
test dependencies into production HA. Requirements and warning logs must be
reported separately from normal CI.

```sh
PYTHONPATH=.:tests python -m pytest -q broker_tests --confcutdir=broker_tests
```

This starts a real loopback TCP broker and uses the actual HA MQTT integration,
retained Discovery, state-topic subscriptions, Paho publisher, normal HA clean
receiver session/reconnect, QoS 0/1/2 and clean/persistent publisher sessions.
No MQTT callback or Discovery result is fabricated. The only connection probe
replaced is automatic MQTT5 migration, because this broker implements 3.1.1 and
the shared fixture executes synchronous executor jobs inline. The actual 3.1.1
connection and all message traffic remain real. Fake time represents complete
30-minute Low and 3-minute Quiet evidence, with configured durations unchanged.
No real radio, Hydrus hardware, MQTT5 or persistent HA receiver-session proof.
