"""Release/UI metadata tests."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from homeassistant.config_entries import OptionsFlowWithReload

from custom_components.water_leak_detection.config_flow import (
    WaterLeakConfigFlow,
    WaterLeakOptionsFlow,
)
from custom_components.water_leak_detection.const import NAME, VERSION

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "water_leak_detection"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_is_normal_service_integration() -> None:
    manifest = _load_json(INTEGRATION / "manifest.json")

    assert manifest["integration_type"] == "service"
    assert manifest["config_flow"] is True
    assert manifest["version"] == VERSION
    assert manifest["name"] == "Water Leak Guard"
    assert NAME == "Water Leak Guard"


def test_runtime_translations_exist_for_english_and_german() -> None:
    english = _load_json(INTEGRATION / "translations" / "en.json")
    german = _load_json(INTEGRATION / "translations" / "de.json")

    hacs = _load_json(ROOT / "hacs.json")

    assert hacs["name"] == "Water Leak Guard"
    assert english["title"] == "Water Leak Guard"
    assert english["device"]["water_leak_detection"]["name"] == "Water Leak Guard"
    assert german["title"] == "Wasserwächter"
    assert german["device"]["water_leak_detection"]["name"] == "Wasserwächter"


def test_all_exposed_entity_translation_keys_have_german_names() -> None:
    german = _load_json(INTEGRATION / "translations" / "de.json")

    expected = {
        "sensor": {
            "status",
            "current_flow",
            "active_event_duration",
            "active_event_volume",
            "high_flow_bypass_remaining",
            "learned_maximum_flow",
            "learning_confidence",
            "learning_coverage",
            "hydraulic_reference_flow",
            "effective_high_threshold",
            "effective_burst_threshold",
        },
        "binary_sensor": {"leak_alarm", "shutoff_request"},
        "switch": {
            "slow_leak_detection",
            "low_flow_detection",
            "high_flow_bypass",
        },
        "number": {"high_flow_bypass_duration"},
    }

    for platform, keys in expected.items():
        translated = german["entity"][platform]
        for key in keys:
            assert translated[key]["name"]


def test_setup_and_options_recipient_translations_exist() -> None:
    german = _load_json(INTEGRATION / "translations" / "de.json")

    config_steps = german["config"]["step"]
    option_steps = german["options"]["step"]

    assert "notifications" in config_steps
    assert "add_initial_recipient" in config_steps
    assert "reconfigure" in config_steps
    assert "notifications" in option_steps
    assert option_steps["init"]["menu_options"]["notifications"]


def test_options_flow_reloads_integration_after_changes() -> None:
    assert issubclass(WaterLeakOptionsFlow, OptionsFlowWithReload)


def test_custom_integration_uses_runtime_translation_files_only() -> None:
    assert not (INTEGRATION / "strings.json").exists()
    assert (INTEGRATION / "translations" / "en.json").is_file()
    assert (INTEGRATION / "translations" / "de.json").is_file()


def test_configure_menu_covers_all_runtime_configuration() -> None:
    german = _load_json(INTEGRATION / "translations" / "de.json")
    menu = german["options"]["step"]["init"]["menu_options"]

    assert set(menu) == {
        "sources",
        "external_sensors",
        "notifications",
        "acknowledgements",
        "expert",
    }
    assert menu["sources"] == "Messquellen"
    assert menu["notifications"] == "Benachrichtigungsempfänger"
    assert menu["expert"] == "Experteneinstellungen"


def test_initial_setup_supports_notification_recipients() -> None:
    assert hasattr(WaterLeakConfigFlow, "async_step_notifications")
    assert hasattr(WaterLeakConfigFlow, "async_step_add_initial_recipient")
    assert hasattr(WaterLeakConfigFlow, "async_step_finish_setup")


def test_existing_entries_can_be_reconfigured() -> None:
    assert hasattr(WaterLeakConfigFlow, "async_step_reconfigure")
    assert hasattr(WaterLeakOptionsFlow, "async_step_sources")
    assert hasattr(WaterLeakOptionsFlow, "async_step_notifications")
    assert hasattr(WaterLeakOptionsFlow, "async_step_expert")


def test_german_selector_and_learning_states_are_translated() -> None:
    german = _load_json(INTEGRATION / "translations" / "de.json")

    source_options = german["selector"]["source_mode"]["options"]
    assert source_options["entities"] == "Einzelne Entitäten auswählen"
    assert source_options["device"] == "Home-Assistant-Gerät auswählen"

    learning_states = german["entity"]["sensor"]["learning_confidence"]["state"]
    assert learning_states == {
        "insufficient": "Unzureichend gelernt",
        "learning": "Lernen aktiv",
        "reliable": "Zuverlässig gelernt",
    }


def test_all_service_actions_have_german_translations() -> None:
    german = _load_json(INTEGRATION / "translations" / "de.json")

    assert set(german["services"]) == {
        "start_high_flow_bypass",
        "cancel_high_flow_bypass",
        "reset_learning",
        "external_reset",
        "request_external_reset_action",
        "acknowledge_event",
    }
    for service in german["services"].values():
        assert service["name"]
        assert service["description"]


def test_entity_platforms_do_not_hardcode_visible_names() -> None:
    for filename in (
        "sensor.py",
        "binary_sensor.py",
        "switch.py",
        "number.py",
    ):
        source = (INTEGRATION / filename).read_text(encoding="utf-8")
        assert "_attr_name =" not in source


def test_configure_translations_do_not_contain_literal_newline_escapes() -> None:
    def assert_clean(value) -> None:
        if isinstance(value, str):
            assert "\\\\n" not in value
        elif isinstance(value, dict):
            for nested in value.values():
                assert_clean(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_clean(nested)

    for language in ("de", "en"):
        translation = _load_json(INTEGRATION / "translations" / f"{language}.json")
        assert_clean(translation["config"])
        assert_clean(translation["options"])


def test_configure_navigation_labels_are_translated() -> None:
    german = _load_json(INTEGRATION / "translations" / "de.json")
    english = _load_json(INTEGRATION / "translations" / "en.json")

    assert (
        german["options"]["step"]["notifications"]["menu_options"]["back_to_main"]
        == "Zurück zur Konfiguration"
    )
    assert (
        english["options"]["step"]["notifications"]["menu_options"]["back_to_main"]
        == "Back to configuration"
    )

    assert german["options"]["step"]["sources"]["submit"] == "Speichern und zurück"
    assert german["options"]["step"]["expert"]["submit"] == "Speichern und zurück"
    assert german["options"]["step"]["add_recipient"]["submit"] == "Hinzufügen und zurück"


def test_repository_license_metadata() -> None:
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert license_text.startswith("GNU AFFERO GENERAL PUBLIC LICENSE")
    assert "Version 3, 19 November 2007" in license_text
    assert pyproject["project"]["version"] == VERSION
    assert pyproject["project"]["license"] == "AGPL-3.0-only"


def test_shutoff_request_icon_follows_its_state() -> None:
    """Valve open while no shutoff is requested, closed while one is requested."""
    from types import SimpleNamespace

    from custom_components.water_leak_detection.binary_sensor import ShutoffRequestBinarySensor

    icons = _load_json(INTEGRATION / "icons.json")
    shutoff = icons["entity"]["binary_sensor"][ShutoffRequestBinarySensor._attr_translation_key]
    assert shutoff["state"] == {"off": "mdi:valve-open", "on": "mdi:valve-closed"}
    # Unavailable/unknown fall back to the neutral valve.
    assert shutoff["default"] == "mdi:valve"
    # A fixed entity icon would override the state-dependent icon translation.
    assert "_attr_icon" not in vars(ShutoffRequestBinarySensor)
    for requested in (False, True):
        manager = SimpleNamespace(
            entry=SimpleNamespace(entry_id="entry"), shutoff_request=requested
        )
        entity = ShutoffRequestBinarySensor(manager)
        assert entity.is_on is requested
        assert entity.icon is None
