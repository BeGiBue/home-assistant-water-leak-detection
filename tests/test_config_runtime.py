"""Real OptionsFlow schemas and ConfigEntry/registry regression coverage."""

import json
import tomllib
from pathlib import Path
from unittest.mock import patch

import probatio
import pytest
from homeassistant.helpers import entity_registry as er
from test_notification_runtime import recipient

from custom_components.water_leak_detection import const as c
from custom_components.water_leak_detection.config_flow import (
    WaterLeakConfigFlow,
    WaterLeakOptionsFlow,
)
from custom_components.water_leak_detection.manager import WaterLeakManager


def options_flow(hass, entry):
    flow = WaterLeakOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id
    flow.flow_id = "regression"
    return flow


def config_flow(hass):
    flow = WaterLeakConfigFlow()
    flow.hass = hass
    flow.handler = c.DOMAIN
    flow.flow_id = "regression"
    return flow


@pytest.mark.parametrize("field", [c.CONF_LOW_QUIET_LPH, c.CONF_HIGH_QUIET_LPH,
                                    c.CONF_BURST_RESET_LPH])
async def test_f09_zero_reset_limit_rejected_and_legacy_load_repaired(
    runtime_hass, runtime_entry, field
):
    flow = options_flow(runtime_hass, runtime_entry)
    form = await flow.async_step_expert()
    values = form["data_schema"]({})
    values[field] = 0
    with pytest.raises(probatio.Invalid):
        form["data_schema"](values)
    assert flow._validate_expert_options(values)
    runtime_hass.config_entries.async_update_entry(runtime_entry, options={field: 0})
    manager = WaterLeakManager(runtime_hass, runtime_entry)
    setting = {c.CONF_LOW_QUIET_LPH: "low_quiet_lph", c.CONF_HIGH_QUIET_LPH: "high_quiet_lph",
               c.CONF_BURST_RESET_LPH: "burst_reset_lph"}[field]
    assert getattr(manager.engine.settings, setting) > 0


@pytest.mark.parametrize("step,parent", list(WaterLeakOptionsFlow._form_parents.items()))
async def test_f18_options_back_ignores_invalid_data_and_saves_nothing(
    runtime_hass, runtime_entry, step, parent
):
    async def notify(call):
        pass
    runtime_hass.services.async_register("notify", "mobile_app_phone", notify)
    raw = recipient("phone")
    runtime_hass.config_entries.async_update_entry(
        runtime_entry, options={c.CONF_NOTIFICATION_RECIPIENTS: [raw],
                               c.CONF_EXTERNAL_SENSORS: [{"id": "kitchen_source",
                                                         "entity_id": "binary_sensor.kitchen"}]}
    )
    flow = options_flow(runtime_hass, runtime_entry)
    flow._editing_recipient_id = raw[c.RECIPIENT_ID]
    flow._editing_external_id = "kitchen_source"
    form = await getattr(flow, "async_step_" + step)()
    assert form["type"] == "form"
    before = dict(runtime_entry.options), dict(runtime_entry.data)
    payload = form["data_schema"]({"go_back": True, "invalid": object()})
    result = await getattr(flow, "async_step_" + step)(payload)
    assert result["step_id"] == parent
    assert (dict(runtime_entry.options), dict(runtime_entry.data)) == before


@pytest.mark.parametrize("step,parent", [("entities", "user"), ("device", "user"),
                                         ("add_initial_recipient", "notifications")])
async def test_f18_config_back_preserves_unsaved_state(runtime_hass, step, parent):
    async def notify(call):
        pass
    runtime_hass.services.async_register("notify", "mobile_app_phone", notify)
    flow = config_flow(runtime_hass)
    form = await getattr(flow, "async_step_" + step)()
    result = await getattr(flow, "async_step_" + step)(
        form["data_schema"]({"go_back": True})
    )
    assert result["step_id"] == parent
    assert flow._entry_data == {}
    assert flow._initial_recipients == []


async def test_f18_back_does_not_remove_required_save_validation(runtime_hass, runtime_entry):
    flow = options_flow(runtime_hass, runtime_entry)
    await flow.async_step_sources()
    result = await flow.async_step_sources({})
    assert result["errors"] == {"base": "required_fields_missing"}
    assert runtime_entry.data[c.CONF_FLOW_ENTITY] == "sensor.flow"


async def test_f12_multiple_recipients_persist_and_reopen_without_reload(
    runtime_hass, runtime_entry
):
    async def notify(call):
        pass
    for phone in ("one", "two"):
        runtime_hass.services.async_register("notify", "mobile_app_" + phone, notify)
    flow = options_flow(runtime_hass, runtime_entry)
    with patch.object(runtime_hass.config_entries, "async_schedule_reload") as reload:
        for phone in ("one", "two"):
            form = await flow.async_step_add_recipient()
            values = form["data_schema"]({
                c.RECIPIENT_NAME: phone,
                c.RECIPIENT_NOTIFY_SERVICE: "notify.mobile_app_" + phone,
                c.RECIPIENT_TRACKER_ENTITY: "device_tracker." + phone,
            })
            result = await flow.async_step_add_recipient(values)
            assert result["step_id"] == "notifications"
        reload.assert_not_called()
    stored = runtime_entry.options[c.CONF_NOTIFICATION_RECIPIENTS]
    assert len(stored) == 2
    reopened = options_flow(runtime_hass, runtime_entry)
    assert reopened._raw_recipients() == stored
    reopened._editing_recipient_id = stored[0][c.RECIPIENT_ID]
    form = await reopened.async_step_edit_recipient_details()
    values = form["data_schema"]({})
    assert values[c.RECIPIENT_NAME] == "one"
    assert values[c.RECIPIENT_NOTIFY_SERVICE] == "notify.mobile_app_one"
    assert stored[0][c.RECIPIENT_TOKEN] != stored[1][c.RECIPIENT_TOKEN]


@pytest.mark.parametrize("flow_type", [WaterLeakConfigFlow, WaterLeakOptionsFlow])
async def test_f22_own_derived_source_rejected_from_any_entry(
    runtime_hass, runtime_entry, flow_type
):
    registered = er.async_get(runtime_hass).async_get_or_create(
        "sensor", c.DOMAIN, "other-instance-flow", suggested_object_id="derived",
        config_entry=runtime_entry,
    )
    runtime_hass.states.async_set(registered.entity_id, "5", {"unit_of_measurement": "L/h"})
    flow = config_flow(runtime_hass) if flow_type is WaterLeakConfigFlow else options_flow(
        runtime_hass, runtime_entry
    )
    assert flow._validate_sources(registered.entity_id, None) == {
        c.CONF_FLOW_ENTITY: "derived_source"
    }


def test_f20_release_validation_and_target_use_same_commit():
    source = Path(".github/workflows/release.yml").read_text()
    assert "uses: ./.github/workflows/validate.yml" in source
    assert "needs: validate" in source
    assert "ref: ${{ github.sha }}" in source
    assert '--target "$GITHUB_SHA"' in source
    assert "ref: main" not in source
    assert '--target "main"' not in source
    assert not list(Path(".github/workflows").glob("release-*.yml"))
    assert "workflow_call:" in Path(".github/workflows/validate.yml").read_text()


def test_f21_versions_and_current_operational_documentation_agree():
    manifest = json.loads(Path("custom_components/water_leak_detection/manifest.json").read_text())
    project = tomllib.loads(Path("pyproject.toml").read_text())
    assert manifest["version"] == project["project"]["version"] == c.VERSION
    readme = Path("README.md").read_text()
    assert f"**Current release:** {c.VERSION}" in readme
    assert "last_reported" in readme
    assert "F04 V3" in readme
    assert "3,500 L/h" in readme
    assert "F04 and F08 remain" not in readme
    for language in ("de", "en"):
        translated = json.loads(Path(
            "custom_components/water_leak_detection/translations/" + language + ".json"
        ).read_text())
        for section, flow_type in (("config", WaterLeakConfigFlow),
                                   ("options", WaterLeakOptionsFlow)):
            for step in flow_type._form_parents:
                assert translated[section]["step"][step]["data"]["go_back"]


async def test_f18_reconfigure_back_keeps_entry_sources(runtime_hass, runtime_entry):
    flow = config_flow(runtime_hass)
    flow.context = {"source": "reconfigure", "entry_id": runtime_entry.entry_id}
    form = await flow.async_step_reconfigure()
    result = await flow.async_step_reconfigure(form["data_schema"]({"go_back": True}))
    assert result["step_id"] == "reconfigure_menu"
    assert runtime_entry.data[c.CONF_FLOW_ENTITY] == "sensor.flow"
    result = await flow.async_step_device_entities({"go_back": True})
    assert result["step_id"] == "device"


async def test_source_form_accepts_omitted_optional_total(runtime_hass, runtime_entry):
    flow = options_flow(runtime_hass, runtime_entry)
    form = await flow.async_step_sources()
    values = form["data_schema"]({c.CONF_FLOW_ENTITY: "sensor.flow"})
    assert values[c.CONF_FLOW_ENTITY] == "sensor.flow"
