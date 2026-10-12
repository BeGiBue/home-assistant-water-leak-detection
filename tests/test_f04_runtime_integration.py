"""Production F04 wiring, real HA registries/Store and conservative fault boundaries."""

import asyncio
import json
from pathlib import Path

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from test_config_runtime import config_flow, options_flow
from test_external_reset_runtime import action, configured
from test_manager_runtime import report, start_manager

from custom_components.water_leak_detection import async_setup
from custom_components.water_leak_detection.const import (
    CONF_EXTERNAL_SENSORS,
    CONF_FLOW_ENTITY,
    DOMAIN,
    DetectorKind,
    DetectorPhase,
)
from custom_components.water_leak_detection.external_leaks import ExternalPhase
from custom_components.water_leak_detection.manager import WaterLeakManager
from custom_components.water_leak_detection.repairs import reconcile_legacy_repair


async def test_two_concurrent_reset_actions_only_one_commits(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    payload = action(manager)
    assert sorted(
        await asyncio.gather(
            manager.async_external_reset(payload), manager.async_external_reset(payload)
        )
    ) == [False, True]
    assert manager.external.sources["a"].phase is ExternalPhase.RESET_WAITING_FOR_OFF
    assert not manager.shutoff_request


async def test_home_rechecked_after_waiting_for_writer(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    payload = action(manager)
    async with manager._state_lock:
        pending = asyncio.create_task(manager.async_external_reset(payload))
        await asyncio.sleep(0)
        runtime_hass.states.async_set("device_tracker.phone", "away")
    assert not await pending
    assert manager.alarm_active and manager.shutoff_request


async def test_active_remove_and_replace_blocked_waiting_removal_allowed(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    before = dict(runtime_entry.options)
    with pytest.raises(ValueError):
        await manager.async_update_options({**before, CONF_EXTERNAL_SENSORS: []})
    with pytest.raises(ValueError):
        await manager.async_update_options(
            {
                **before,
                CONF_EXTERNAL_SENSORS: [{"id": "a", "entity_id": "binary_sensor.replacement"}],
            }
        )
    assert dict(runtime_entry.options) == before
    assert await manager.async_external_reset(action(manager))
    await manager.async_update_options({**before, CONF_EXTERNAL_SENSORS: []})
    assert not manager.external.all_sources()


@pytest.mark.parametrize("offline", [False, True])
async def test_registry_rename_preserves_flow_generation(
    runtime_hass, runtime_entry, measurement_clock, offline
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    generation = manager.measurement_source.generation
    if offline:
        await manager.async_unload()
    registry = er.async_get(runtime_hass)
    registry.async_update_entity("sensor.flow", new_entity_id="sensor.renamed_flow")
    runtime_hass.states.async_set("sensor.renamed_flow", "0", {"unit_of_measurement": "L/h"})
    await runtime_hass.async_block_till_done()
    if offline:
        manager = WaterLeakManager(runtime_hass, runtime_entry)
        runtime_hass.data[DOMAIN][runtime_entry.entry_id] = manager
        await manager.async_setup()
    assert manager.measurement_source.generation == generation
    assert manager.flow_entity_id == runtime_entry.data[CONF_FLOW_ENTITY] == "sensor.renamed_flow"


@pytest.mark.parametrize("offline", [False, True])
async def test_external_rename_preserves_waiting_generation(
    runtime_hass, runtime_entry, measurement_clock, offline
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    assert await manager.async_external_reset(action(manager))
    generation = manager.external.sources["a"].identity.generation
    if offline:
        await manager.async_unload()
    er.async_get(runtime_hass).async_update_entity(
        "binary_sensor.kitchen", new_entity_id="binary_sensor.renamed_kitchen"
    )
    runtime_hass.states.async_set("binary_sensor.renamed_kitchen", "on")
    await runtime_hass.async_block_till_done()
    if offline:
        manager = WaterLeakManager(runtime_hass, runtime_entry)
        runtime_hass.data[DOMAIN][runtime_entry.entry_id] = manager
        await manager.async_setup()
    source = manager.external.sources["a"]
    assert source.identity.generation == generation
    assert source.phase is ExternalPhase.RESET_WAITING_FOR_OFF
    assert source.identity.entity_id == "binary_sensor.renamed_kitchen"
    assert not manager.alarm_active


async def test_replacement_retains_old_alarm_as_separate_tombstone(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    old = action(manager)
    registry = er.async_get(runtime_hass)
    registry.async_remove("binary_sensor.kitchen")
    registry.async_get_or_create(
        "binary_sensor", "test", "different_hardware", suggested_object_id="kitchen"
    )
    await runtime_hass.async_block_till_done()
    assert manager.external.sources["a"].identity.generation != old["source_generation"]
    assert manager.external.sources["a"].phase is ExternalPhase.ARMED
    assert old["event_id"] in manager.active_events() and manager.shutoff_request
    await manager._async_external_changed("binary_sensor.kitchen", "off")
    assert old["event_id"] in manager.active_events()
    # A still-current authorized old-generation action targets only the tombstone.
    assert await manager.async_external_reset(old)
    assert not manager.alarm_active


async def test_failed_on_write_preserves_alarm_identity_and_retries(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    real = manager._store.async_save

    async def failure(data):
        raise OSError("write failed")

    monkeypatch.setattr(manager._store, "async_save", failure)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    event_id = manager.external.sources["a"].event_id
    assert event_id and manager.shutoff_request
    await runtime_hass.async_block_till_done()
    assert event_id in manager.notifications.acknowledgements
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    assert manager.external.sources["a"].event_id == event_id
    monkeypatch.setattr(manager._store, "async_save", real)
    await manager._async_save()
    assert (
        json.loads(Path(manager._store.path).read_text())["data"]["external_sources"][0]["event_id"]
        == event_id
    )


@pytest.mark.parametrize("contribution", [False, True])
async def test_external_alarm_blocks_both_learning_channels_waiting_does_not(
    runtime_hass, runtime_entry, measurement_clock, contribution
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    source = manager.external.sources["a"]
    source.contributes_to_shutoff = contribution
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    assert manager.alarm_active
    for flow in (300, 0, 300, 0):
        measurement_clock.advance(10)
        report(runtime_hass, measurement_clock, flow)
        await manager.async_refresh()
    assert manager.learner.samples == []
    assert manager.long_term_learner.pending_high_candidates == []
    assert await manager.async_external_reset(action(manager))
    for flow in (*([0] * 14), 300, *([0] * 13)):
        measurement_clock.advance(10)
        report(runtime_hass, measurement_clock, flow)
        await manager.async_refresh()
    assert not manager.alarm_active
    assert manager.learner.samples


async def test_real_manager_legacy_migration_preserves_active_ack_options_and_repair(
    runtime_hass, runtime_entry, measurement_clock
):
    await ir.async_load(runtime_hass)
    runtime_hass.config_entries.async_update_entry(runtime_entry, options={"shutoff_high": True})
    manager = await start_manager(runtime_hass, runtime_entry, measurement_clock, 0)
    active = manager.engine.runtimes[DetectorKind.HIGH_FLOW]
    active.phase = DetectorPhase.ACTIVE
    active.event_id = "confirmed_alarm"
    active.started_at = active.utc_started_at = measurement_clock.utcnow()
    raw = manager._serialize()
    raw.pop("learning_schema_version")
    raw["learning"] = {
        "samples": [{"timestamp": measurement_clock.utcnow().isoformat(), "peak_lph": 4900}],
        "pending_high_candidates": [None],
        "confirmed_high_history": [None],
    }
    raw["acknowledgements"]["confirmed_alarm"] = {"globally_acknowledged": True}
    options = dict(runtime_entry.options)
    await manager.async_unload(save=False)
    await Store(runtime_hass, 1, manager._store.key).async_save(raw)
    restored = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    await restored.async_setup()
    assert restored.engine.runtimes[DetectorKind.HIGH_FLOW].event_id == "confirmed_alarm"
    assert restored.shutoff_request
    assert restored.notifications.acknowledgements["confirmed_alarm"].globally_acknowledged
    assert (
        restored.learner.samples == []
        and not restored.long_term_learner.confirmed_long_term_normal_max_lph
    )
    assert dict(runtime_entry.options) == options
    registry = ir.async_get(runtime_hass)
    issue_id = restored.legacy_learning_migration["repair_id"]
    assert (DOMAIN, issue_id) in registry.issues
    registry.async_ignore(DOMAIN, issue_id, True)
    dismissed = registry.issues[(DOMAIN, issue_id)].dismissed_version
    reconcile_legacy_repair(runtime_hass, runtime_entry, restored.legacy_learning_migration)
    assert registry.issues[(DOMAIN, issue_id)].dismissed_version == dismissed
    disk = json.loads(Path(restored._store.path).read_text())
    assert disk["version"] == 2 and "learning" not in disk["data"]


async def test_initial_external_setup_and_options_back_navigation(runtime_hass, runtime_entry):
    runtime_hass.states.async_set("binary_sensor.kitchen", "off")
    flow = config_flow(runtime_hass)
    form = await flow.async_step_add_initial_external_sensor()
    assert (await flow.async_step_add_initial_external_sensor({"go_back": True}))[
        "step_id"
    ] == "notifications"
    values = form["data_schema"](
        {"entity_id": "binary_sensor.kitchen", "contributes_to_shutoff": True}
    )
    assert (await flow.async_step_add_initial_external_sensor(values))["step_id"] == "notifications"
    assert flow._initial_external_sources[0]["contributes_to_shutoff"] is True
    options = options_flow(runtime_hass, runtime_entry)
    assert "external_sensors" in (await options.async_step_init())["menu_options"]


async def test_long_term_threshold_uncapped_and_never_enters_rolling(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = WaterLeakManager(runtime_hass, runtime_entry)
    manager.long_term_learner.confirmed_long_term_normal_max_lph = 3300
    thresholds = manager.adaptive_thresholds(measurement_clock.utcnow())
    assert thresholds.effective_burst_lph == 3960
    assert thresholds.effective_high_lph == 600
    assert manager.learner.samples == []
    assert manager.engine.settings.burst_threshold_lph == 3500


async def test_real_service_rejects_reset_without_all_bindings(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await async_setup(runtime_hass, {})
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    from homeassistant.exceptions import HomeAssistantError

    payload = action(manager)
    payload["reset_nonce"] = "old"
    with pytest.raises(HomeAssistantError):
        await runtime_hass.services.async_call(DOMAIN, "external_reset", payload, blocking=True)
    assert manager.shutoff_request


@pytest.mark.parametrize("field", ["recipient_token", "reset_nonce"])
@pytest.mark.parametrize("value", ["ä", None, [], {}, True])
async def test_malformed_mobile_binding_fails_closed_without_exception(
    runtime_hass, runtime_entry, measurement_clock, field, value
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    payload = action(manager)
    payload[field] = value
    assert not await manager.async_external_reset(payload)
    assert manager.alarm_active and manager.shutoff_request


@pytest.mark.parametrize("language", ["de", "en"])
async def test_restart_ack_preserved_fresh_action_requested_and_authorized(
    runtime_hass, runtime_entry, measurement_clock, language
):
    from homeassistant import loader

    import custom_components
    from custom_components.water_leak_detection.notifications import EventAcknowledgement

    loader.async_setup(runtime_hass)
    runtime_hass.config.language = language
    runtime_hass.data[loader.DATA_INTEGRATIONS][DOMAIN] = loader.Integration.resolve_from_root(
        runtime_hass, custom_components, DOMAIN
    )
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    old = action(manager)
    manager.notifications.acknowledgements[old["event_id"]] = EventAcknowledgement(
        globally_acknowledged=True, muted_recipients={"phone"}
    )
    runtime_hass.states.async_set("binary_sensor.kitchen", "on")
    await runtime_hass.async_block_till_done()
    await manager.async_unload()
    restored = WaterLeakManager(runtime_hass, runtime_entry)
    runtime_hass.data[DOMAIN][runtime_entry.entry_id] = restored
    await restored.async_setup()
    calls = []

    async def notify(call):
        calls.append(call.data)

    runtime_hass.services.async_register("notify", "mobile_app_phone", notify)
    assert await restored.async_request_external_reset_action("a", "phone")
    assert len(calls) == 1
    state = restored.notifications.acknowledgements[old["event_id"]]
    assert state.globally_acknowledged and "phone" in state.muted_recipients
    actions = calls[0]["data"]["actions"]
    assert any("EXTERNAL_RESET" in item["action"] for item in actions)
    assert not await restored.async_external_reset(old)
    assert await restored.async_external_reset(action(restored))


async def test_actual_mobile_ack_and_mute_never_release_external_safety(
    runtime_hass, runtime_entry, measurement_clock
):
    from homeassistant.core import Event

    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    await runtime_hass.async_block_till_done()
    source = manager.external.sources["a"]
    for kind in ("MUTE", "ACK_ALL"):
        await manager.notifications._async_mobile_action(
            Event(
                "mobile_app_notification_action",
                {
                    "action": (f"WLD|{kind}|{runtime_entry.entry_id}|{source.event_id}"
                               "|phone|recipient_token")
                },
            )
        )
        assert manager.alarm_active and manager.shutoff_request
        assert source.phase is ExternalPhase.ACTIVE


async def test_options_ui_cannot_remove_active_and_can_edit_contribution(
    runtime_hass, runtime_entry, measurement_clock
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    flow = options_flow(runtime_hass, runtime_entry)
    await flow.async_step_remove_external_sensor()
    result = await flow.async_step_remove_external_sensor({"id": "a"})
    assert result["errors"]["base"] == "external_source_active"
    assert manager.alarm_active
    flow._editing_external_id = "a"
    form = await flow.async_step_edit_external_sensor_details()
    result = await flow.async_step_edit_external_sensor_details(
        form["data_schema"](
            {
                "entity_id": "binary_sensor.kitchen",
                "name": "Kitchen",
                "contributes_to_shutoff": False,
            }
        )
    )
    assert result["step_id"] == "external_sensors"
    assert manager.alarm_active and not manager.shutoff_request
    assert runtime_entry.options[CONF_EXTERNAL_SENSORS][0]["contributes_to_shutoff"] is False


async def test_store_failed_options_do_not_publish_shutoff_release(
    runtime_hass, runtime_entry, measurement_clock, monkeypatch
):
    manager = await configured(runtime_hass, runtime_entry, measurement_clock)
    await manager._async_external_changed("binary_sensor.kitchen", "on")
    options = dict(runtime_entry.options)
    proposed = {
        **options,
        CONF_EXTERNAL_SENSORS: [
            {**item, "contributes_to_shutoff": False} for item in options[CONF_EXTERNAL_SENSORS]
        ],
    }

    def fail(*args):
        from homeassistant.util.file import WriteError

        raise WriteError("controlled atomic write failure")

    with monkeypatch.context() as patch:
        patch.setattr(manager._store, "_write_prepared_data", fail)
        with pytest.raises(Exception, match="controlled atomic write failure"):
            await manager.async_update_options(proposed)
    assert dict(runtime_entry.options) == options
    assert manager.alarm_active and manager.shutoff_request
