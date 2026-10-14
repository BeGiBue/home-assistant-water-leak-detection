"""Config flow for Water Leak Guard."""

from __future__ import annotations

from math import isfinite
from secrets import token_urlsafe
from typing import Any
from uuid import uuid4

import probatio
from homeassistant.auth.models import TOKEN_TYPE_NORMAL, RefreshToken, User
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import translation
from homeassistant.helpers.selector import (
    BooleanSelector,
    DeviceSelector,
    DeviceSelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BURST_DETECTION_SEC,
    CONF_BURST_LEARNED_MULTIPLIER,
    CONF_BURST_RATE_CONFIRM_SEC,
    CONF_BURST_RATE_RISE_LPH_10S,
    CONF_BURST_RESET_LPH,
    CONF_BURST_RESET_SEC,
    CONF_BURST_THRESHOLD_LPH,
    CONF_BYPASS_DEFAULT_MIN,
    CONF_EXTERNAL_SENSORS,
    CONF_FLOW_ENTITY,
    CONF_HIGH_DETECTION_MIN,
    CONF_HIGH_QUIET_LPH,
    CONF_HIGH_RESET_MIN,
    CONF_HIGH_THRESHOLD_LPH,
    CONF_HIGH_VOLUME_L,
    CONF_HYDRAULIC_BURST_FRACTION,
    CONF_LEARNING_WINDOW_DAYS,
    CONF_LOW_DETECTION_MIN,
    CONF_LOW_QUIET_LPH,
    CONF_LOW_RESET_MIN,
    CONF_LOW_STABILITY_ABSOLUTE_LPH,
    CONF_LOW_STABILITY_EARLY_MIN,
    CONF_LOW_STABILITY_ENABLED,
    CONF_LOW_STABILITY_RELATIVE_PERCENT,
    CONF_LOW_STABILITY_REQUIRED_PERCENT,
    CONF_LOW_STABILITY_WINDOW_MIN,
    CONF_LOW_THRESHOLD_LPH,
    CONF_MANUAL_MAX_FLOW_LPH,
    CONF_NOTIFICATION_RECIPIENTS,
    CONF_PIPE_DIAMETER_MM,
    CONF_SHUTOFF_BURST,
    CONF_SHUTOFF_HIGH,
    CONF_SHUTOFF_LOW,
    CONF_SHUTOFF_SLOW,
    CONF_SLOW_DETECTION_MIN,
    CONF_SLOW_RESET_MIN,
    CONF_SLOW_THRESHOLD_LPH,
    CONF_SOURCE_DEVICE,
    CONF_SOURCE_GAP_EXPLICIT,
    CONF_SOURCE_MAX_AGE_SEC,
    CONF_SOURCE_MODE,
    CONF_STATIC_PRESSURE_BAR,
    CONF_TOTAL_ENTITY,
    DEFAULT_BURST_DETECTION_SEC,
    DEFAULT_BURST_LEARNED_MULTIPLIER,
    DEFAULT_BURST_RATE_CONFIRM_SEC,
    DEFAULT_BURST_RATE_RISE_LPH_10S,
    DEFAULT_BURST_RESET_LPH,
    DEFAULT_BURST_RESET_SEC,
    DEFAULT_BURST_THRESHOLD_LPH,
    DEFAULT_BYPASS_DEFAULT_MIN,
    DEFAULT_HIGH_DETECTION_MIN,
    DEFAULT_HIGH_QUIET_LPH,
    DEFAULT_HIGH_RESET_MIN,
    DEFAULT_HIGH_THRESHOLD_LPH,
    DEFAULT_HIGH_VOLUME_L,
    DEFAULT_HYDRAULIC_BURST_FRACTION,
    DEFAULT_LEARNING_WINDOW_DAYS,
    DEFAULT_LOW_DETECTION_MIN,
    DEFAULT_LOW_QUIET_LPH,
    DEFAULT_LOW_RESET_MIN,
    DEFAULT_LOW_STABILITY_ABSOLUTE_LPH,
    DEFAULT_LOW_STABILITY_ENABLED,
    DEFAULT_LOW_STABILITY_RELATIVE_PERCENT,
    DEFAULT_LOW_STABILITY_REQUIRED_PERCENT,
    DEFAULT_LOW_THRESHOLD_LPH,
    DEFAULT_MANUAL_MAX_FLOW_LPH,
    DEFAULT_PIPE_DIAMETER_MM,
    DEFAULT_SHUTOFF_BURST,
    DEFAULT_SHUTOFF_HIGH,
    DEFAULT_SHUTOFF_LOW,
    DEFAULT_SHUTOFF_SLOW,
    DEFAULT_SLOW_DETECTION_MIN,
    DEFAULT_SLOW_RESET_MIN,
    DEFAULT_SLOW_THRESHOLD_LPH,
    DEFAULT_SOURCE_MAX_AGE_SEC,
    DEFAULT_STATIC_PRESSURE_BAR,
    DOMAIN,
    NAME,
    RECIPIENT_ALLOW_EXTERNAL_RESET,
    RECIPIENT_ALLOW_GLOBAL_ACK,
    RECIPIENT_CRITICAL_ENABLED,
    RECIPIENT_ID,
    RECIPIENT_KIND,
    RECIPIENT_KIND_DISPLAY,
    RECIPIENT_NAME,
    RECIPIENT_NOTIFY_SERVICE,
    RECIPIENT_SESSION_TOKEN_ID,
    RECIPIENT_SESSION_USER_ID,
    RECIPIENT_TOKEN,
    RECIPIENT_TRACKER_ENTITY,
    RECIPIENT_TRUSTED_STATIONARY,
    DetectorKind,
)
from .low_flow_options import low_stability_minutes
from .units import is_supported_flow_unit, is_supported_volume_unit

SOURCE_ENTITIES = "entities"
SOURCE_DEVICE = "device"
NO_TOTAL = "__none__"


def _number(minimum: float, maximum: float, step: float, unit: str):
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=NumberSelectorMode.BOX,
        )
    )


# Form field of the dashboard pairing select. Its values are encoded:
# "__none__" (not paired), "user:<user id>" or "token:<refresh token id>".
# Stored is either RECIPIENT_SESSION_USER_ID or RECIPIENT_SESSION_TOKEN_ID.
FORM_SESSION_PAIRING = "session_pairing"
_NO_PAIRING = "__none__"
_PAIR_USER = "user:"
_PAIR_TOKEN = "token:"


def _is_display(raw: dict[str, Any] | None) -> bool:
    """Stationary display recipient (no notify service, no tracker, always Home)."""
    return isinstance(raw, dict) and raw.get(RECIPIENT_KIND) == RECIPIENT_KIND_DISPLAY


def _pairing_value(raw: dict[str, Any] | None) -> str:
    """Encoded select value of a stored recipient pairing (login wins over user)."""
    raw = raw or {}
    token_id = raw.get(RECIPIENT_SESSION_TOKEN_ID)
    if isinstance(token_id, str) and token_id:
        return f"{_PAIR_TOKEN}{token_id}"
    user_id = raw.get(RECIPIENT_SESSION_USER_ID)
    if isinstance(user_id, str) and user_id:
        return f"{_PAIR_USER}{user_id}"
    return _NO_PAIRING


def _recipient_description_placeholders(
    recipients: list[dict[str, Any]],
) -> dict[str, str]:
    """Build a safe, human-readable overview of configured recipients."""
    valid = [recipient for recipient in recipients if isinstance(recipient, dict)]
    if not valid:
        return {
            "recipient_count": "0",
            "configured_recipients": "—",
        }

    lines = [
        f"- **{str(recipient.get(RECIPIENT_NAME) or '—')}**"
        + (" 🖥" if _is_display(recipient) else "")
        for recipient in valid
    ]

    return {
        "recipient_count": str(len(valid)),
        "configured_recipients": "\n".join(lines),
    }


def _validate_source_entities(hass, flow_entity, total_entity):
    """Reject own outputs, including outputs of another instance."""
    errors = {}
    registry = er.async_get(hass)
    for entity_id, field, supported, error in (
        (flow_entity, CONF_FLOW_ENTITY, is_supported_flow_unit, "unsupported_flow_unit"),
        (total_entity, CONF_TOTAL_ENTITY, is_supported_volume_unit, "unsupported_volume_unit"),
    ):
        if not entity_id:
            continue
        registered = registry.async_get(entity_id)
        state = hass.states.get(entity_id)
        if registered is not None and registered.platform == DOMAIN:
            errors[field] = "derived_source"
        elif state is None:
            errors[field] = "entity_not_available"
        elif not supported(state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)):
            errors[field] = error
    if total_entity and total_entity == flow_entity:
        errors[CONF_TOTAL_ENTITY] = "same_source_entity"
    return errors


class _NavigationSchema(probatio.Schema):
    """Back navigation also accepts unfinished or invalid form contents."""

    def __call__(self, data):
        if isinstance(data, dict) and data.get("go_back") is True:
            return {"go_back": True}
        return super().__call__(data)


class _NavigationForms:
    """Allow leaving a form without validating/saving unfinished required fields."""

    _form_parents: dict[str, str] = {}

    def async_show_form(self, *, step_id, data_schema=None, **kwargs):
        if not hasattr(self, "_navigation_forms"):
            self._navigation_forms = {}
        required = set()
        if step_id in self._form_parents and data_schema is not None:
            fields = {}
            for marker, validator in data_schema.schema.items():
                if isinstance(marker, probatio.Required):
                    required.add(marker.schema)
                    marker = probatio.Optional(
                        marker.schema, default=marker.default, description=marker.description
                    )
                if (
                    isinstance(marker, probatio.Optional)
                    and marker.default is not probatio.UNDEFINED
                    and marker.default() is None
                ):
                    # Empty optional entity selectors must stay omitted on save.
                    marker = probatio.Optional(marker.schema, description=marker.description)
                fields[marker] = validator
            fields[probatio.Optional("go_back", default=False)] = BooleanSelector()
            data_schema = _NavigationSchema(fields)
        result = super().async_show_form(step_id=step_id, data_schema=data_schema, **kwargs)
        self._navigation_forms[step_id] = (required, result)
        return result

    def _navigation_error(self, step_id, user_input):
        if user_input is None or user_input.get("go_back"):
            return None
        required, form = self._navigation_forms.get(step_id, (set(), None))
        if required - user_input.keys():
            return {**form, "errors": {"base": "required_fields_missing"}}
        user_input.pop("go_back", None)
        return None


class WaterLeakConfigFlow(_NavigationForms, ConfigFlow, domain=DOMAIN):
    """Handle configuration."""

    _form_parents = {
        "entities": "user",
        "device": "user",
        "device_entities": "device",
        "add_initial_recipient": "notifications",
        "add_initial_external_sensor": "notifications",
        "reconfigure": "reconfigure_menu",
    }
    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._source_device: str | None = None
        self._entry_data: dict[str, Any] = {}
        self._initial_recipients: list[dict[str, Any]] = []
        self._initial_external_sources: list[dict[str, Any]] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose whether data sources are selected by entities or by device."""
        if user_input is not None:
            if user_input[CONF_SOURCE_MODE] == SOURCE_DEVICE:
                return await self.async_step_device()
            return await self.async_step_entities()

        return self.async_show_form(
            step_id="user",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_SOURCE_MODE, default=SOURCE_ENTITIES): SelectSelector(
                        SelectSelectorConfig(
                            options=[SOURCE_ENTITIES, SOURCE_DEVICE],
                            translation_key=CONF_SOURCE_MODE,
                        )
                    )
                }
            ),
        )

    async def async_step_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select source entities directly."""
        if user_input is not None and user_input.get("go_back"):
            return await self.async_step_user()
        if error := self._navigation_error("entities", user_input):
            return error
        errors: dict[str, str] = {}
        if user_input is not None:
            flow_entity = user_input[CONF_FLOW_ENTITY]
            total_entity = user_input.get(CONF_TOTAL_ENTITY) or None
            errors = self._validate_sources(flow_entity, total_entity)
            if not errors:
                return await self._prepare_source_entry(flow_entity, total_entity, None)

        return self.async_show_form(
            step_id="entities",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_FLOW_ENTITY): EntitySelector(
                        EntitySelectorConfig(domain="sensor", multiple=False)
                    ),
                    probatio.Optional(CONF_TOTAL_ENTITY): EntitySelector(
                        EntitySelectorConfig(domain="sensor", multiple=False)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Select a HA device and discover compatible source entities on it."""
        if user_input is not None and user_input.get("go_back"):
            return await self.async_step_user()
        if error := self._navigation_error("device", user_input):
            return error
        if user_input is not None:
            self._source_device = user_input[CONF_SOURCE_DEVICE]
            return await self.async_step_device_entities()

        return self.async_show_form(
            step_id="device",
            data_schema=probatio.Schema(
                {probatio.Required(CONF_SOURCE_DEVICE): DeviceSelector(DeviceSelectorConfig())}
            ),
        )

    async def async_step_device_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm compatible sensors discovered on the selected device."""
        if user_input is not None and user_input.get("go_back"):
            return await self.async_step_device()
        if error := self._navigation_error("device_entities", user_input):
            return error
        if self._source_device is None:
            return await self.async_step_device()

        flow_candidates, total_candidates = self._device_candidates(self._source_device)
        if not flow_candidates:
            return self.async_abort(reason="device_has_no_flow_sensor")

        errors: dict[str, str] = {}
        if user_input is not None:
            flow_entity = user_input[CONF_FLOW_ENTITY]
            total_raw = user_input.get(CONF_TOTAL_ENTITY, NO_TOTAL)
            total_entity = None if total_raw == NO_TOTAL else total_raw
            errors = self._validate_sources(flow_entity, total_entity)
            if not errors:
                return await self._prepare_source_entry(
                    flow_entity, total_entity, self._source_device
                )

        flow_options = [
            SelectOptionDict(
                value=entity_id,
                label=self._entity_label(entity_id),
            )
            for entity_id in flow_candidates
        ]
        total_options = [
            SelectOptionDict(
                value=entity_id,
                label=self._entity_label(entity_id),
            )
            for entity_id in total_candidates
        ]

        schema: dict[Any, Any] = {
            probatio.Required(
                CONF_FLOW_ENTITY,
                default=flow_candidates[0],
            ): SelectSelector(SelectSelectorConfig(options=flow_options))
        }
        if total_options:
            schema[probatio.Optional(CONF_TOTAL_ENTITY)] = SelectSelector(
                SelectSelectorConfig(options=total_options)
            )

        return self.async_show_form(
            step_id="device_entities",
            data_schema=probatio.Schema(schema),
            errors=errors,
        )

    def _device_candidates(self, device_id: str) -> tuple[list[str], list[str]]:
        registry = er.async_get(self.hass)
        flow: list[str] = []
        total: list[str] = []
        for entry in er.async_entries_for_device(registry, device_id):
            if entry.domain != "sensor" or entry.disabled_by is not None:
                continue
            state = self.hass.states.get(entry.entity_id)
            if state is None:
                continue
            unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            if is_supported_flow_unit(unit):
                flow.append(entry.entity_id)
            if is_supported_volume_unit(unit):
                total.append(entry.entity_id)
        return sorted(flow), sorted(total)

    def _entity_label(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        if state is None:
            return entity_id
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        return f"{state.name} ({unit})" if unit else state.name

    def _validate_sources(self, flow_entity: str, total_entity: str | None) -> dict[str, str]:
        return _validate_source_entities(self.hass, flow_entity, total_entity)

    async def _prepare_source_entry(
        self,
        flow_entity: str,
        total_entity: str | None,
        device_id: str | None,
    ) -> ConfigFlowResult:
        """Store source configuration and continue to notification recipients."""
        for entry in self._async_current_entries():
            if entry.data.get(CONF_FLOW_ENTITY) == flow_entity:
                return self.async_abort(reason="already_configured")

        self._entry_data = {CONF_FLOW_ENTITY: flow_entity}
        if total_entity:
            self._entry_data[CONF_TOTAL_ENTITY] = total_entity
        if device_id:
            self._entry_data[CONF_SOURCE_DEVICE] = device_id
        return await self.async_step_notifications()

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow notification recipients to be configured during setup."""
        menu_options = ["add_initial_external_sensor", "finish_setup", "back_to_sources"]
        if self._mobile_notify_services():
            menu_options.insert(0, "add_initial_recipient")
        return self.async_show_menu(
            step_id="notifications",
            menu_options=menu_options,
            description_placeholders=_recipient_description_placeholders(self._initial_recipients),
        )

    async def async_step_back_to_sources(self, user_input=None):
        """Return to source choice without discarding recipients."""
        return await self.async_step_user()

    async def async_step_reconfigure_menu(self, user_input=None):
        """Keep reconfiguration open when the source form is left."""
        return self.async_show_menu(step_id="reconfigure_menu", menu_options=["reconfigure"])

    async def async_step_add_initial_recipient(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add one Companion recipient during initial setup."""
        if user_input is not None and user_input.get("go_back"):
            return await self.async_step_notifications()
        if error := self._navigation_error("add_initial_recipient", user_input):
            return error
        notify_services = self._mobile_notify_services()
        if not notify_services:
            return await self.async_step_notifications()

        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input[RECIPIENT_NAME]).strip()
            notify_service = str(user_input[RECIPIENT_NOTIFY_SERVICE])
            if not name:
                errors["base"] = "recipient_name_required"
            elif any(
                raw.get(RECIPIENT_NOTIFY_SERVICE) == notify_service
                for raw in self._initial_recipients
            ):
                errors["base"] = "recipient_notify_service_exists"
            else:
                self._initial_recipients.append(
                    {
                        RECIPIENT_ID: uuid4().hex[:10],
                        RECIPIENT_NAME: name,
                        RECIPIENT_NOTIFY_SERVICE: notify_service,
                        RECIPIENT_TRACKER_ENTITY: str(user_input[RECIPIENT_TRACKER_ENTITY]),
                        RECIPIENT_CRITICAL_ENABLED: bool(user_input[RECIPIENT_CRITICAL_ENABLED]),
                        RECIPIENT_ALLOW_EXTERNAL_RESET: user_input.get(
                            RECIPIENT_ALLOW_EXTERNAL_RESET, False
                        )
                        is True,
                        RECIPIENT_ALLOW_GLOBAL_ACK: bool(user_input[RECIPIENT_ALLOW_GLOBAL_ACK]),
                        RECIPIENT_TRUSTED_STATIONARY: bool(
                            user_input[RECIPIENT_TRUSTED_STATIONARY]
                        ),
                        RECIPIENT_TOKEN: token_urlsafe(12),
                    }
                )
                return await self.async_step_notifications()

        return self.async_show_form(
            step_id="add_initial_recipient",
            data_schema=self._recipient_schema(notify_services),
            errors=errors,
            description_placeholders=_recipient_description_placeholders(self._initial_recipients),
        )

    async def async_step_add_initial_external_sensor(self, user_input=None):
        if user_input is not None and user_input.get("go_back"):
            return await self.async_step_notifications()
        if error := self._navigation_error("add_initial_external_sensor", user_input):
            return error
        errors = {}
        if user_input is not None:
            entity_id = user_input["entity_id"]
            registered = er.async_get(self.hass).async_get(entity_id)
            if registered and registered.platform == DOMAIN:
                errors["base"] = "derived_source"
            elif self.hass.states.get(entity_id) is None:
                errors["base"] = "entity_not_available"
            elif any(item["entity_id"] == entity_id for item in self._initial_external_sources):
                errors["base"] = "duplicate_external_source"
            else:
                self._initial_external_sources.append(
                    {
                        "id": uuid4().hex,
                        "entity_id": entity_id,
                        "name": user_input.get("name", ""),
                        "contributes_to_shutoff": user_input["contributes_to_shutoff"] is True,
                    }
                )
                return await self.async_step_notifications()
        return self.async_show_form(
            step_id="add_initial_external_sensor",
            data_schema=WaterLeakOptionsFlow._external_schema(),
            errors=errors,
            description_placeholders={
                "configured_external_sources": "\n".join(
                    item.get("name") or item["entity_id"] for item in self._initial_external_sources
                )
                or "—"
            },
        )

    async def async_step_finish_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the config entry after source and recipient setup."""
        translations = await translation.async_get_translations(
            self.hass,
            self.hass.config.language,
            "title",
            [DOMAIN],
            config_flow=True,
        )
        title = translations.get(f"component.{DOMAIN}.title", NAME)
        return self.async_create_entry(
            title=title,
            data=self._entry_data,
            options={
                CONF_NOTIFICATION_RECIPIENTS: self._initial_recipients,
                CONF_EXTERNAL_SENSORS: self._initial_external_sources,
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow source sensors to be changed after setup."""
        if user_input is not None and user_input.get("go_back"):
            return await self.async_step_reconfigure_menu()
        if error := self._navigation_error("reconfigure", user_input):
            return error
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            flow_entity = str(user_input[CONF_FLOW_ENTITY])
            total_entity = user_input.get(CONF_TOTAL_ENTITY) or None
            errors = self._validate_sources(flow_entity, total_entity)
            if not errors:
                for current in self._async_current_entries():
                    if (
                        current.entry_id != entry.entry_id
                        and current.data.get(CONF_FLOW_ENTITY) == flow_entity
                    ):
                        return self.async_abort(reason="already_configured")
                data = dict(entry.data)
                data[CONF_FLOW_ENTITY] = flow_entity
                if total_entity:
                    data[CONF_TOTAL_ENTITY] = total_entity
                else:
                    data.pop(CONF_TOTAL_ENTITY, None)
                data.pop(CONF_SOURCE_DEVICE, None)
                manager = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
                if manager:
                    await manager.async_update_sources(data)
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        CONF_FLOW_ENTITY,
                        default=entry.data[CONF_FLOW_ENTITY],
                    ): EntitySelector(EntitySelectorConfig(domain="sensor", multiple=False)),
                    probatio.Optional(
                        CONF_TOTAL_ENTITY,
                        default=entry.data.get(CONF_TOTAL_ENTITY),
                    ): EntitySelector(EntitySelectorConfig(domain="sensor", multiple=False)),
                }
            ),
            errors=errors,
        )

    def _mobile_notify_services(self) -> list[str]:
        """Return currently registered Companion mobile notification services."""
        services = self.hass.services.async_services().get("notify", {})
        return sorted(
            f"notify.{service}" for service in services if service.startswith("mobile_app_")
        )

    @staticmethod
    def _recipient_schema(
        notify_services: list[str],
        *,
        current: dict[str, Any] | None = None,
        sessions: list[SelectOptionDict] | None = None,
    ) -> probatio.Schema:
        """Build the recipient configuration form.

        ``sessions`` adds the optional dashboard device pairing (options flow only).
        """
        current = current or {}
        schema: dict[Any, Any] = {
            probatio.Required(
                RECIPIENT_NAME,
                default=current.get(RECIPIENT_NAME, ""),
            ): TextSelector(),
            probatio.Required(
                RECIPIENT_NOTIFY_SERVICE,
                default=current.get(
                    RECIPIENT_NOTIFY_SERVICE,
                    notify_services[0],
                ),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=service, label=service)
                        for service in notify_services
                    ]
                )
            ),
            probatio.Required(
                RECIPIENT_CRITICAL_ENABLED,
                default=bool(current.get(RECIPIENT_CRITICAL_ENABLED, True)),
            ): BooleanSelector(),
            probatio.Required(
                RECIPIENT_ALLOW_GLOBAL_ACK,
                default=bool(current.get(RECIPIENT_ALLOW_GLOBAL_ACK, True)),
            ): BooleanSelector(),
            probatio.Optional(
                RECIPIENT_ALLOW_EXTERNAL_RESET,
                default=current.get(RECIPIENT_ALLOW_EXTERNAL_RESET) is True,
            ): BooleanSelector(),
            probatio.Required(
                RECIPIENT_TRUSTED_STATIONARY,
                default=bool(current.get(RECIPIENT_TRUSTED_STATIONARY, False)),
            ): BooleanSelector(),
        }
        tracker_default = current.get(RECIPIENT_TRACKER_ENTITY)
        tracker_key = (
            probatio.Required(
                RECIPIENT_TRACKER_ENTITY,
                default=tracker_default,
            )
            if tracker_default
            else probatio.Required(RECIPIENT_TRACKER_ENTITY)
        )
        schema[tracker_key] = EntitySelector(
            EntitySelectorConfig(
                domain="device_tracker",
                multiple=False,
            )
        )
        if sessions is not None:
            paired = _pairing_value(current)
            values = {option["value"] for option in sessions}
            schema[
                probatio.Optional(
                    FORM_SESSION_PAIRING,
                    default=paired if paired in values else _NO_PAIRING,
                )
            ] = SelectSelector(SelectSelectorConfig(options=sessions))
        return probatio.Schema(schema)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlowWithReload:
        """Create options flow."""
        return WaterLeakOptionsFlow()


class WaterLeakOptionsFlow(_NavigationForms, OptionsFlowWithReload):
    """Options for detector settings and Companion recipients."""

    _form_parents = {
        "sources": "init",
        "expert": "init",
        "add_recipient": "notifications",
        "edit_recipient": "notifications",
        "edit_recipient_details": "edit_recipient",
        "add_display": "notifications",
        "edit_display_details": "edit_recipient",
        "remove_recipient": "notifications",
        "add_external_sensor": "external_sensors",
        "edit_external_sensor": "external_sensors",
        "edit_external_sensor_details": "edit_external_sensor",
        "remove_external_sensor": "external_sensors",
        "acknowledgements": "init",
    }

    def __init__(self) -> None:
        """Initialize options flow state."""
        super().__init__()
        self._editing_recipient_id: str | None = None
        self._editing_external_id: str | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "sources",
                "external_sensors",
                "notifications",
                "acknowledgements",
                "expert",
            ],
        )

    async def async_step_acknowledgements(self, user_input=None):
        """Admin Configure UI acknowledges an exact event as an authorized recipient."""
        if user_input is not None and user_input.get("go_back"):
            return await self.async_step_init()
        if error := self._navigation_error("acknowledgements", user_input):
            return error
        manager = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        errors = {}
        if manager is not None and user_input is not None:
            raw = next(
                (
                    item
                    for item in self._raw_recipients()
                    if item.get(RECIPIENT_ID) == user_input["recipient_id"]
                    and not _is_display(item)
                ),
                None,
            )
            try:
                accepted = raw is not None and await manager.async_acknowledge_event(
                    user_input["event_id"], user_input["recipient_id"], raw.get(RECIPIENT_TOKEN)
                )
            except Exception:
                errors["base"] = "acknowledgement_persistence_failed"
            else:
                if accepted:
                    return await self.async_step_init()
                errors["base"] = "acknowledgement_rejected"
        events = manager.active_events() if manager is not None else {}
        choices = []
        for event_id, kind in events.items():
            name = (
                kind.value.replace("_", " ").title()
                if isinstance(kind, DetectorKind)
                else kind.name
            )
            state = manager.notifications.state_for(event_id)
            marker = "✓" if state and state.globally_acknowledged else "—"
            choices.append(
                SelectOptionDict(value=event_id, label=f"{name} · {event_id} · {marker}")
            )
        return self.async_show_form(
            step_id="acknowledgements",
            errors=errors,
            data_schema=probatio.Schema(
                {
                    probatio.Required("event_id"): SelectSelector(
                        SelectSelectorConfig(options=choices)
                    ),
                    probatio.Required("recipient_id"): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(
                                    value=raw[RECIPIENT_ID],
                                    label=str(raw.get(RECIPIENT_NAME, raw[RECIPIENT_ID])),
                                )
                                for raw in self._raw_recipients()
                                if raw.get(RECIPIENT_ID) and not _is_display(raw)
                            ]
                        )
                    ),
                }
            ),
        )

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit measurement sources from the normal Configure dialog."""
        if user_input is not None and user_input.get("go_back"):
            return await self.async_step_init()
        if error := self._navigation_error("sources", user_input):
            return error
        errors: dict[str, str] = {}
        entry = self.config_entry

        if user_input is not None:
            flow_entity = str(user_input[CONF_FLOW_ENTITY])
            total_entity = user_input.get(CONF_TOTAL_ENTITY) or None
            errors = self._validate_sources(flow_entity, total_entity)

            if not errors:
                for current in self.hass.config_entries.async_entries(DOMAIN):
                    if (
                        current.entry_id != entry.entry_id
                        and current.data.get(CONF_FLOW_ENTITY) == flow_entity
                    ):
                        errors["base"] = "already_configured"
                        break

            if not errors:
                data = dict(entry.data)
                data[CONF_FLOW_ENTITY] = flow_entity
                if total_entity:
                    data[CONF_TOTAL_ENTITY] = total_entity
                else:
                    data.pop(CONF_TOTAL_ENTITY, None)
                data.pop(CONF_SOURCE_DEVICE, None)
                manager = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
                changed = (
                    await manager.async_update_sources(data)
                    if manager
                    else self.hass.config_entries.async_update_entry(entry, data=data)
                )
                if changed:
                    self.hass.config_entries.async_schedule_reload(entry.entry_id)
                return await self.async_step_init()

        return self.async_show_form(
            step_id="sources",
            last_step=False,
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        CONF_FLOW_ENTITY,
                        default=entry.data[CONF_FLOW_ENTITY],
                    ): EntitySelector(EntitySelectorConfig(domain="sensor", multiple=False)),
                    probatio.Optional(
                        CONF_TOTAL_ENTITY,
                        default=entry.data.get(CONF_TOTAL_ENTITY),
                    ): EntitySelector(EntitySelectorConfig(domain="sensor", multiple=False)),
                }
            ),
            errors=errors,
        )

    def _validate_sources(
        self,
        flow_entity: str,
        total_entity: str | None,
    ) -> dict[str, str]:
        """Validate measurement sources in the options flow."""
        return _validate_source_entities(self.hass, flow_entity, total_entity)

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage notification recipients."""
        recipients = self._raw_recipients()
        menu_options = ["add_recipient", "add_display"]
        if recipients:
            menu_options.extend(["edit_recipient", "remove_recipient"])
        menu_options.append("back_to_main")
        return self.async_show_menu(
            step_id="notifications",
            menu_options=menu_options,
            description_placeholders=_recipient_description_placeholders(recipients),
        )

    async def async_step_back_to_main(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Return from a submenu to the main Configure menu."""
        return await self.async_step_init()

    def _external_sources(self) -> list[dict]:
        raw = self.config_entry.options.get(CONF_EXTERNAL_SENSORS, [])
        return (
            [
                item
                for item in raw
                if isinstance(item, dict)
                and isinstance(item.get("id"), str)
                and isinstance(item.get("entity_id"), str)
            ]
            if isinstance(raw, list)
            else []
        )

    def _external_description(self) -> dict[str, str]:
        manager = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        lines = []
        for item in self._external_sources():
            source = manager.external.sources.get(item["id"]) if manager else None
            phase = source.phase.value if source else "—"
            lines.append(f"- {item.get('name') or item.get('entity_id')} · {phase}")
        if manager:
            lines.extend(
                f"- {source.name} · ACTIVE ({source.identity.generation})"
                for source in manager.external.tombstones.values()
            )
        return {"configured_external_sources": "\n".join(lines) or "—"}

    async def async_step_external_sensors(self, user_input=None):
        menu = ["add_external_sensor"]
        if self._external_sources():
            menu.extend(["edit_external_sensor", "remove_external_sensor"])
        menu.append("back_to_main")
        return self.async_show_menu(
            step_id="external_sensors",
            menu_options=menu,
            description_placeholders=self._external_description(),
        )

    @staticmethod
    def _external_schema(current=None):
        current = current or {}
        return probatio.Schema(
            {
                probatio.Required("entity_id", default=current.get("entity_id")): EntitySelector(
                    EntitySelectorConfig(domain="binary_sensor", multiple=False)
                ),
                probatio.Optional("name", default=current.get("name", "")): TextSelector(),
                probatio.Required(
                    "contributes_to_shutoff", default=current.get("contributes_to_shutoff", True)
                ): BooleanSelector(),
            }
        )

    async def _save_external_sources(self, sources):
        registry = er.async_get(self.hass)
        seen = set()
        for item in sources:
            entity_id = item.get("entity_id")
            if not isinstance(entity_id, str) or not entity_id.startswith("binary_sensor."):
                raise ValueError("invalid_external_source")
            registered = registry.async_get(entity_id)
            if registered and registered.platform == DOMAIN:
                raise ValueError("derived_source")
            if self.hass.states.get(entity_id) is None:
                raise ValueError("entity_not_available")
            key = registered.id if registered else entity_id
            if key in seen:
                raise ValueError("duplicate_external_source")
            seen.add(key)
        manager = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        if manager is None and self._external_sources() and sources != self._external_sources():
            raise ValueError("external_manager_unavailable")
        await self._persist_options({**self.config_entry.options, CONF_EXTERNAL_SENSORS: sources})

    async def async_step_add_external_sensor(self, user_input=None):
        if user_input and user_input.get("go_back"):
            return await self.async_step_external_sensors()
        if error := self._navigation_error("add_external_sensor", user_input):
            return error
        errors = {}
        if user_input is not None:
            record = {key: value for key, value in user_input.items() if key != "go_back"}
            try:
                await self._save_external_sources(
                    [*self._external_sources(), {**record, "id": uuid4().hex}]
                )
            except ValueError as err:
                errors["base"] = str(err)
            except Exception:
                errors["base"] = "external_persistence_failed"
            else:
                return await self.async_step_external_sensors()
        return self.async_show_form(
            step_id="add_external_sensor",
            data_schema=self._external_schema(),
            errors=errors,
            description_placeholders=self._external_description(),
        )

    def _external_select_schema(self):
        return probatio.Schema(
            {
                probatio.Required("id"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=item["id"], label=str(item.get("name") or item["entity_id"])
                            )
                            for item in self._external_sources()
                        ]
                    )
                )
            }
        )

    async def async_step_edit_external_sensor(self, user_input=None):
        if user_input and user_input.get("go_back"):
            return await self.async_step_external_sensors()
        if error := self._navigation_error("edit_external_sensor", user_input):
            return error
        if user_input is not None:
            self._editing_external_id = user_input["id"]
            return await self.async_step_edit_external_sensor_details()
        return self.async_show_form(
            step_id="edit_external_sensor", data_schema=self._external_select_schema()
        )

    async def async_step_edit_external_sensor_details(self, user_input=None):
        if user_input and user_input.get("go_back"):
            return await self.async_step_edit_external_sensor()
        if error := self._navigation_error("edit_external_sensor_details", user_input):
            return error
        current = next(
            (
                item
                for item in self._external_sources()
                if item.get("id") == self._editing_external_id
            ),
            None,
        )
        if current is None:
            return await self.async_step_external_sensors()
        errors = {}
        if user_input is not None:
            record = {key: value for key, value in user_input.items() if key != "go_back"}
            records = [
                {**record, "id": current["id"]} if item["id"] == current["id"] else item
                for item in self._external_sources()
            ]
            try:
                await self._save_external_sources(records)
            except ValueError as err:
                errors["base"] = str(err)
            except Exception:
                errors["base"] = "external_persistence_failed"
            else:
                return await self.async_step_external_sensors()
        return self.async_show_form(
            step_id="edit_external_sensor_details",
            data_schema=self._external_schema(current),
            errors=errors,
        )

    async def async_step_remove_external_sensor(self, user_input=None):
        if user_input and user_input.get("go_back"):
            return await self.async_step_external_sensors()
        if error := self._navigation_error("remove_external_sensor", user_input):
            return error
        errors = {}
        if user_input is not None:
            try:
                await self._save_external_sources(
                    [item for item in self._external_sources() if item["id"] != user_input["id"]]
                )
            except ValueError as err:
                errors["base"] = str(err)
            except Exception:
                errors["base"] = "external_persistence_failed"
            else:
                return await self.async_step_external_sensors()
        return self.async_show_form(
            step_id="remove_external_sensor",
            data_schema=self._external_select_schema(),
            errors=errors,
        )

    async def async_step_expert(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit expert detector settings."""
        if user_input is not None and user_input.get("go_back"):
            return await self.async_step_init()
        if error := self._navigation_error("expert", user_input):
            return error
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate_expert_options(user_input)
            if not errors:
                updated = dict(self.config_entry.options)
                updated.update(user_input)
                if CONF_SOURCE_MAX_AGE_SEC in user_input:
                    updated[CONF_SOURCE_GAP_EXPLICIT] = True
                await self._persist_options(updated)
                return await self.async_step_init()

        options = self.config_entry.options
        values = user_input if user_input is not None else options
        early_minutes, window_minutes = low_stability_minutes(values)
        schema = probatio.Schema(
            {
                probatio.Optional(
                    CONF_SOURCE_MAX_AGE_SEC,
                    default=(
                        DEFAULT_SOURCE_MAX_AGE_SEC
                        if user_input is None
                        and values.get(CONF_SOURCE_MAX_AGE_SEC) == 30
                        and not options.get(CONF_SOURCE_GAP_EXPLICIT)
                        else values.get(CONF_SOURCE_MAX_AGE_SEC, DEFAULT_SOURCE_MAX_AGE_SEC)
                    ),
                ): _number(0, 3600, 1, "s"),
                probatio.Required(
                    CONF_SLOW_THRESHOLD_LPH,
                    default=values.get(
                        CONF_SLOW_THRESHOLD_LPH,
                        DEFAULT_SLOW_THRESHOLD_LPH,
                    ),
                ): _number(1, 500, 1, "L/h"),
                probatio.Required(
                    CONF_SLOW_DETECTION_MIN,
                    default=values.get(
                        CONF_SLOW_DETECTION_MIN,
                        DEFAULT_SLOW_DETECTION_MIN,
                    ),
                ): _number(1, 1440, 1, "min"),
                probatio.Required(
                    CONF_SLOW_RESET_MIN,
                    default=values.get(
                        CONF_SLOW_RESET_MIN,
                        DEFAULT_SLOW_RESET_MIN,
                    ),
                ): _number(1, 180, 1, "min"),
                probatio.Required(
                    CONF_LOW_THRESHOLD_LPH,
                    default=values.get(
                        CONF_LOW_THRESHOLD_LPH,
                        DEFAULT_LOW_THRESHOLD_LPH,
                    ),
                ): _number(1, 5000, 1, "L/h"),
                probatio.Required(
                    CONF_LOW_DETECTION_MIN,
                    default=values.get(
                        CONF_LOW_DETECTION_MIN,
                        DEFAULT_LOW_DETECTION_MIN,
                    ),
                ): _number(1, 1440, 1, "min"),
                probatio.Required(
                    CONF_LOW_QUIET_LPH,
                    default=values.get(
                        CONF_LOW_QUIET_LPH,
                        DEFAULT_LOW_QUIET_LPH,
                    ),
                ): _number(1, 1000, 1, "L/h"),
                probatio.Required(
                    CONF_LOW_RESET_MIN,
                    default=values.get(
                        CONF_LOW_RESET_MIN,
                        DEFAULT_LOW_RESET_MIN,
                    ),
                ): _number(1, 180, 1, "min"),
                probatio.Required(
                    CONF_LOW_STABILITY_ENABLED,
                    default=values.get(CONF_LOW_STABILITY_ENABLED, DEFAULT_LOW_STABILITY_ENABLED),
                ): BooleanSelector(),
                probatio.Required(
                    CONF_LOW_STABILITY_EARLY_MIN,
                    default=early_minutes,
                ): _number(0.1, 1440, 0.1, "min"),
                probatio.Required(
                    CONF_LOW_STABILITY_WINDOW_MIN,
                    default=window_minutes,
                ): _number(0.1, 1440, 0.1, "min"),
                probatio.Required(
                    CONF_LOW_STABILITY_RELATIVE_PERCENT,
                    default=values.get(
                        CONF_LOW_STABILITY_RELATIVE_PERCENT, DEFAULT_LOW_STABILITY_RELATIVE_PERCENT
                    ),
                ): _number(0.1, 100, 0.1, "%"),
                probatio.Required(
                    CONF_LOW_STABILITY_ABSOLUTE_LPH,
                    default=values.get(
                        CONF_LOW_STABILITY_ABSOLUTE_LPH, DEFAULT_LOW_STABILITY_ABSOLUTE_LPH
                    ),
                ): _number(0.1, 5000, 0.1, "L/h"),
                probatio.Required(
                    CONF_LOW_STABILITY_REQUIRED_PERCENT,
                    default=values.get(
                        CONF_LOW_STABILITY_REQUIRED_PERCENT, DEFAULT_LOW_STABILITY_REQUIRED_PERCENT
                    ),
                ): _number(0.1, 100, 0.1, "%"),
                probatio.Required(
                    CONF_HIGH_THRESHOLD_LPH,
                    default=values.get(
                        CONF_HIGH_THRESHOLD_LPH,
                        DEFAULT_HIGH_THRESHOLD_LPH,
                    ),
                ): _number(1, 10000, 10, "L/h"),
                probatio.Required(
                    CONF_HIGH_DETECTION_MIN,
                    default=values.get(
                        CONF_HIGH_DETECTION_MIN,
                        DEFAULT_HIGH_DETECTION_MIN,
                    ),
                ): _number(1, 1440, 1, "min"),
                probatio.Required(
                    CONF_HIGH_VOLUME_L,
                    default=values.get(
                        CONF_HIGH_VOLUME_L,
                        DEFAULT_HIGH_VOLUME_L,
                    ),
                ): _number(1, 50000, 10, "L"),
                probatio.Required(
                    CONF_HIGH_QUIET_LPH,
                    default=values.get(
                        CONF_HIGH_QUIET_LPH,
                        DEFAULT_HIGH_QUIET_LPH,
                    ),
                ): _number(1, 5000, 1, "L/h"),
                probatio.Required(
                    CONF_HIGH_RESET_MIN,
                    default=values.get(
                        CONF_HIGH_RESET_MIN,
                        DEFAULT_HIGH_RESET_MIN,
                    ),
                ): _number(1, 180, 1, "min"),
                probatio.Required(
                    CONF_BURST_THRESHOLD_LPH,
                    default=values.get(
                        CONF_BURST_THRESHOLD_LPH,
                        DEFAULT_BURST_THRESHOLD_LPH,
                    ),
                ): _number(100, 50000, 10, "L/h"),
                probatio.Required(
                    CONF_BURST_DETECTION_SEC,
                    default=values.get(
                        CONF_BURST_DETECTION_SEC,
                        DEFAULT_BURST_DETECTION_SEC,
                    ),
                ): _number(1, 600, 1, "s"),
                probatio.Required(
                    CONF_BURST_RESET_LPH,
                    default=values.get(
                        CONF_BURST_RESET_LPH,
                        DEFAULT_BURST_RESET_LPH,
                    ),
                ): _number(1, 10000, 1, "L/h"),
                probatio.Required(
                    CONF_BURST_RESET_SEC,
                    default=values.get(
                        CONF_BURST_RESET_SEC,
                        DEFAULT_BURST_RESET_SEC,
                    ),
                ): _number(1, 1800, 1, "s"),
                probatio.Required(
                    CONF_BYPASS_DEFAULT_MIN,
                    default=values.get(
                        CONF_BYPASS_DEFAULT_MIN,
                        DEFAULT_BYPASS_DEFAULT_MIN,
                    ),
                ): _number(1, 1440, 1, "min"),
                probatio.Required(
                    CONF_LEARNING_WINDOW_DAYS,
                    default=values.get(
                        CONF_LEARNING_WINDOW_DAYS,
                        DEFAULT_LEARNING_WINDOW_DAYS,
                    ),
                ): _number(7, 90, 1, "d"),
                probatio.Required(
                    CONF_MANUAL_MAX_FLOW_LPH,
                    default=values.get(
                        CONF_MANUAL_MAX_FLOW_LPH,
                        DEFAULT_MANUAL_MAX_FLOW_LPH,
                    ),
                ): _number(0, 50000, 10, "L/h"),
                probatio.Required(
                    CONF_PIPE_DIAMETER_MM,
                    default=values.get(
                        CONF_PIPE_DIAMETER_MM,
                        DEFAULT_PIPE_DIAMETER_MM,
                    ),
                ): _number(10, 100, 1, "mm"),
                probatio.Required(
                    CONF_STATIC_PRESSURE_BAR,
                    default=values.get(
                        CONF_STATIC_PRESSURE_BAR,
                        DEFAULT_STATIC_PRESSURE_BAR,
                    ),
                ): _number(0.5, 12, 0.1, "bar"),
                probatio.Required(
                    CONF_BURST_LEARNED_MULTIPLIER,
                    default=values.get(
                        CONF_BURST_LEARNED_MULTIPLIER,
                        DEFAULT_BURST_LEARNED_MULTIPLIER,
                    ),
                ): _number(1.1, 5.0, 0.05, "×"),
                probatio.Required(
                    CONF_HYDRAULIC_BURST_FRACTION,
                    default=values.get(
                        CONF_HYDRAULIC_BURST_FRACTION,
                        DEFAULT_HYDRAULIC_BURST_FRACTION,
                    ),
                ): _number(0.2, 1.0, 0.05, "×"),
                probatio.Required(
                    CONF_BURST_RATE_RISE_LPH_10S,
                    default=values.get(
                        CONF_BURST_RATE_RISE_LPH_10S,
                        DEFAULT_BURST_RATE_RISE_LPH_10S,
                    ),
                ): _number(100, 20000, 100, "L/h / 10 s"),
                probatio.Required(
                    CONF_BURST_RATE_CONFIRM_SEC,
                    default=values.get(
                        CONF_BURST_RATE_CONFIRM_SEC,
                        DEFAULT_BURST_RATE_CONFIRM_SEC,
                    ),
                ): _number(1, 60, 1, "s"),
                probatio.Required(
                    CONF_SHUTOFF_SLOW,
                    default=values.get(
                        CONF_SHUTOFF_SLOW,
                        DEFAULT_SHUTOFF_SLOW,
                    ),
                ): BooleanSelector(),
                probatio.Required(
                    CONF_SHUTOFF_LOW,
                    default=values.get(
                        CONF_SHUTOFF_LOW,
                        DEFAULT_SHUTOFF_LOW,
                    ),
                ): BooleanSelector(),
                probatio.Required(
                    CONF_SHUTOFF_HIGH,
                    default=values.get(
                        CONF_SHUTOFF_HIGH,
                        DEFAULT_SHUTOFF_HIGH,
                    ),
                ): BooleanSelector(),
                probatio.Required(
                    CONF_SHUTOFF_BURST,
                    default=values.get(
                        CONF_SHUTOFF_BURST,
                        DEFAULT_SHUTOFF_BURST,
                    ),
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="expert",
            last_step=False,
            data_schema=schema,
            errors=errors,
        )

    async def async_step_add_recipient(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add one Companion notification recipient."""
        if user_input is not None and user_input.get("go_back"):
            return await self.async_step_notifications()
        if error := self._navigation_error("add_recipient", user_input):
            return error
        notify_services = self._mobile_notify_services()
        if not notify_services:
            return self.async_abort(reason="no_mobile_app_notify_services")

        existing = self._raw_recipients()
        sessions, session_options = await self._session_choices(existing, None)
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input[RECIPIENT_NAME]).strip()
            notify_service = str(user_input[RECIPIENT_NOTIFY_SERVICE])
            tracker_entity = str(user_input[RECIPIENT_TRACKER_ENTITY])
            session_id = user_input.get(FORM_SESSION_PAIRING)

            if not name:
                errors["base"] = "recipient_name_required"
            elif any(raw.get(RECIPIENT_NOTIFY_SERVICE) == notify_service for raw in existing):
                errors["base"] = "recipient_notify_service_exists"
            elif session_id is not None and (
                session_error := self._session_error(str(session_id), sessions, existing, None)
            ):
                errors["base"] = session_error
            else:
                recipient = {
                    RECIPIENT_ID: uuid4().hex[:10],
                    RECIPIENT_NAME: name,
                    RECIPIENT_NOTIFY_SERVICE: notify_service,
                    RECIPIENT_TRACKER_ENTITY: tracker_entity,
                    RECIPIENT_CRITICAL_ENABLED: bool(user_input[RECIPIENT_CRITICAL_ENABLED]),
                    RECIPIENT_ALLOW_EXTERNAL_RESET: user_input.get(
                        RECIPIENT_ALLOW_EXTERNAL_RESET, False
                    )
                    is True,
                    RECIPIENT_ALLOW_GLOBAL_ACK: bool(user_input[RECIPIENT_ALLOW_GLOBAL_ACK]),
                    RECIPIENT_TRUSTED_STATIONARY: bool(user_input[RECIPIENT_TRUSTED_STATIONARY]),
                    RECIPIENT_TOKEN: token_urlsafe(12),
                }
                recipient = self._apply_session(
                    recipient, str(session_id) if session_id is not None else None
                )
                updated = dict(self.config_entry.options)
                updated[CONF_NOTIFICATION_RECIPIENTS] = [*existing, recipient]
                await self._persist_options(updated)
                return await self.async_step_notifications()

        return self.async_show_form(
            step_id="add_recipient",
            last_step=False,
            data_schema=WaterLeakConfigFlow._recipient_schema(
                notify_services, sessions=session_options
            ),
            errors=errors,
            description_placeholders=_recipient_description_placeholders(existing),
        )

    async def async_step_edit_recipient(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a configured notification recipient to edit."""
        if user_input is not None and user_input.get("go_back"):
            return await self.async_step_notifications()
        if error := self._navigation_error("edit_recipient", user_input):
            return error
        recipients = self._raw_recipients()
        if not recipients:
            return self.async_abort(reason="no_recipients_configured")

        if user_input is not None:
            self._editing_recipient_id = str(user_input[RECIPIENT_ID])
            editing = self._editing_recipient_id
            chosen = next((r for r in recipients if str(r.get(RECIPIENT_ID, "")) == editing), None)
            # The kind is fixed after creation: a display has its own form.
            if _is_display(chosen):
                return await self.async_step_edit_display_details()
            return await self.async_step_edit_recipient_details()

        options = [
            SelectOptionDict(
                value=str(raw[RECIPIENT_ID]),
                label=str(raw.get(RECIPIENT_NAME, raw[RECIPIENT_ID])),
            )
            for raw in recipients
            if raw.get(RECIPIENT_ID)
        ]
        return self.async_show_form(
            step_id="edit_recipient",
            last_step=False,
            data_schema=probatio.Schema(
                {
                    probatio.Required(RECIPIENT_ID): SelectSelector(
                        SelectSelectorConfig(options=options)
                    )
                }
            ),
            description_placeholders=_recipient_description_placeholders(recipients),
        )

    async def async_step_edit_recipient_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit one Companion notification recipient."""
        if user_input is not None and user_input.get("go_back"):
            return await self.async_step_edit_recipient()
        if error := self._navigation_error("edit_recipient_details", user_input):
            return error
        recipient_id = self._editing_recipient_id
        recipients = self._raw_recipients()
        current = next(
            (raw for raw in recipients if str(raw.get(RECIPIENT_ID, "")) == recipient_id),
            None,
        )
        if current is None:
            return self.async_abort(reason="recipient_not_found")
        if _is_display(current):
            return await self.async_step_edit_display_details()

        notify_services = self._mobile_notify_services()
        current_service = str(current.get(RECIPIENT_NOTIFY_SERVICE, ""))
        if current_service and current_service not in notify_services:
            notify_services.append(current_service)
            notify_services.sort()

        sessions, session_options = await self._session_choices(recipients, recipient_id, current)
        current_pairing = _pairing_value(current)
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input[RECIPIENT_NAME]).strip()
            notify_service = str(user_input[RECIPIENT_NOTIFY_SERVICE])
            session_id = user_input.get(FORM_SESSION_PAIRING)
            if not name:
                errors["base"] = "recipient_name_required"
            elif any(
                str(raw.get(RECIPIENT_ID, "")) != recipient_id
                and raw.get(RECIPIENT_NOTIFY_SERVICE) == notify_service
                for raw in recipients
            ):
                errors["base"] = "recipient_notify_service_exists"
            elif (
                session_id is not None
                and session_id != current_pairing
                and (
                    session_error := self._session_error(
                        str(session_id), sessions, recipients, recipient_id
                    )
                )
            ):
                errors["base"] = session_error
            else:
                replacement = {
                    RECIPIENT_ID: str(current[RECIPIENT_ID]),
                    RECIPIENT_NAME: name,
                    RECIPIENT_NOTIFY_SERVICE: notify_service,
                    RECIPIENT_TRACKER_ENTITY: str(user_input[RECIPIENT_TRACKER_ENTITY]),
                    RECIPIENT_CRITICAL_ENABLED: bool(user_input[RECIPIENT_CRITICAL_ENABLED]),
                    RECIPIENT_ALLOW_EXTERNAL_RESET: user_input.get(
                        RECIPIENT_ALLOW_EXTERNAL_RESET,
                        current.get(RECIPIENT_ALLOW_EXTERNAL_RESET, False),
                    )
                    is True,
                    RECIPIENT_ALLOW_GLOBAL_ACK: bool(user_input[RECIPIENT_ALLOW_GLOBAL_ACK]),
                    RECIPIENT_TRUSTED_STATIONARY: bool(user_input[RECIPIENT_TRUSTED_STATIONARY]),
                    RECIPIENT_TOKEN: str(current[RECIPIENT_TOKEN]),
                }
                # Without a changed choice an existing pairing is kept unchanged.
                for key in (RECIPIENT_SESSION_TOKEN_ID, RECIPIENT_SESSION_USER_ID):
                    if isinstance(current.get(key), str):
                        replacement[key] = current[key]
                if session_id is not None and session_id != current_pairing:
                    replacement = self._apply_session(replacement, str(session_id))
                updated = dict(self.config_entry.options)
                updated[CONF_NOTIFICATION_RECIPIENTS] = [
                    replacement if str(raw.get(RECIPIENT_ID, "")) == recipient_id else raw
                    for raw in recipients
                ]
                await self._persist_options(updated)
                self._editing_recipient_id = None
                return await self.async_step_notifications()

        return self.async_show_form(
            step_id="edit_recipient_details",
            last_step=False,
            data_schema=WaterLeakConfigFlow._recipient_schema(
                notify_services,
                current=current,
                sessions=session_options,
            ),
            errors=errors,
            description_placeholders=_recipient_description_placeholders(recipients),
        )

    def _display_schema(
        self, session_options: list[SelectOptionDict], current: dict[str, Any] | None = None
    ) -> probatio.Schema:
        """Form of a stationary display: name, required pairing, permissions only.

        A display has no notify service, no device tracker and no notification
        settings; it is always treated as Home. "—" (no pairing) is not offered.
        """
        current = current or {}
        options = [o for o in session_options if o["value"] != _NO_PAIRING]
        paired = _pairing_value(current)
        pairing_key = (
            probatio.Required(FORM_SESSION_PAIRING, default=paired)
            if paired != _NO_PAIRING and paired in {o["value"] for o in options}
            else probatio.Required(FORM_SESSION_PAIRING)
        )
        return probatio.Schema(
            {
                probatio.Required(
                    RECIPIENT_NAME, default=current.get(RECIPIENT_NAME, "")
                ): TextSelector(),
                pairing_key: SelectSelector(SelectSelectorConfig(options=options)),
                probatio.Required(
                    RECIPIENT_ALLOW_GLOBAL_ACK,
                    default=current.get(RECIPIENT_ALLOW_GLOBAL_ACK, False) is True,
                ): BooleanSelector(),
                probatio.Required(
                    RECIPIENT_ALLOW_EXTERNAL_RESET,
                    default=current.get(RECIPIENT_ALLOW_EXTERNAL_RESET) is True,
                ): BooleanSelector(),
            }
        )

    async def async_step_add_display(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a stationary wall display (e.g. TouchKio): no push, always Home."""
        if user_input is not None and user_input.get("go_back"):
            return await self.async_step_notifications()
        if error := self._navigation_error("add_display", user_input):
            return error
        existing = self._raw_recipients()
        sessions, session_options = await self._session_choices(existing, None)
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input[RECIPIENT_NAME]).strip()
            session_id = str(user_input.get(FORM_SESSION_PAIRING) or _NO_PAIRING)
            if not name:
                errors["base"] = "recipient_name_required"
            elif session_id == _NO_PAIRING:
                errors["base"] = "display_pairing_required"
            elif session_error := self._session_error(session_id, sessions, existing, None):
                errors["base"] = session_error
            else:
                display = self._apply_session(
                    {
                        RECIPIENT_ID: uuid4().hex[:10],
                        RECIPIENT_KIND: RECIPIENT_KIND_DISPLAY,
                        RECIPIENT_NAME: name,
                        RECIPIENT_ALLOW_GLOBAL_ACK: user_input.get(RECIPIENT_ALLOW_GLOBAL_ACK)
                        is True,
                        RECIPIENT_ALLOW_EXTERNAL_RESET: user_input.get(
                            RECIPIENT_ALLOW_EXTERNAL_RESET
                        )
                        is True,
                        RECIPIENT_TOKEN: token_urlsafe(12),
                    },
                    session_id,
                )
                updated = dict(self.config_entry.options)
                updated[CONF_NOTIFICATION_RECIPIENTS] = [*existing, display]
                await self._persist_options(updated)
                return await self.async_step_notifications()

        return self.async_show_form(
            step_id="add_display",
            last_step=False,
            data_schema=self._display_schema(session_options),
            errors=errors,
            description_placeholders=_recipient_description_placeholders(existing),
        )

    async def async_step_edit_display_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit a stationary display; its kind, id and token stay unchanged."""
        if user_input is not None and user_input.get("go_back"):
            return await self.async_step_edit_recipient()
        if error := self._navigation_error("edit_display_details", user_input):
            return error
        recipient_id = self._editing_recipient_id
        recipients = self._raw_recipients()
        current = next(
            (raw for raw in recipients if str(raw.get(RECIPIENT_ID, "")) == recipient_id),
            None,
        )
        if current is None:
            return self.async_abort(reason="recipient_not_found")
        if not _is_display(current):
            # The kind is fixed: a mobile recipient keeps its own form.
            return await self.async_step_edit_recipient_details()
        sessions, session_options = await self._session_choices(recipients, recipient_id, current)
        current_pairing = _pairing_value(current)
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input[RECIPIENT_NAME]).strip()
            session_id = str(user_input.get(FORM_SESSION_PAIRING) or _NO_PAIRING)
            if not name:
                errors["base"] = "recipient_name_required"
            elif session_id == _NO_PAIRING:
                errors["base"] = "display_pairing_required"
            elif session_id != current_pairing and (
                session_error := self._session_error(session_id, sessions, recipients, recipient_id)
            ):
                errors["base"] = session_error
            else:
                replacement = {
                    RECIPIENT_ID: str(current[RECIPIENT_ID]),
                    RECIPIENT_KIND: RECIPIENT_KIND_DISPLAY,
                    RECIPIENT_NAME: name,
                    RECIPIENT_ALLOW_GLOBAL_ACK: user_input.get(RECIPIENT_ALLOW_GLOBAL_ACK) is True,
                    RECIPIENT_ALLOW_EXTERNAL_RESET: user_input.get(RECIPIENT_ALLOW_EXTERNAL_RESET)
                    is True,
                    RECIPIENT_TOKEN: str(current[RECIPIENT_TOKEN]),
                }
                for key in (RECIPIENT_SESSION_TOKEN_ID, RECIPIENT_SESSION_USER_ID):
                    if isinstance(current.get(key), str):
                        replacement[key] = current[key]
                if session_id != current_pairing:
                    replacement = self._apply_session(replacement, session_id)
                updated = dict(self.config_entry.options)
                updated[CONF_NOTIFICATION_RECIPIENTS] = [
                    replacement if str(raw.get(RECIPIENT_ID, "")) == recipient_id else raw
                    for raw in recipients
                ]
                await self._persist_options(updated)
                self._editing_recipient_id = None
                return await self.async_step_notifications()

        return self.async_show_form(
            step_id="edit_display_details",
            last_step=False,
            data_schema=self._display_schema(session_options, current),
            errors=errors,
            description_placeholders=_recipient_description_placeholders(recipients),
        )

    async def _pairable_users(self) -> dict[str, User]:
        """Active, non-system HA users (people, not integrations or add-ons)."""
        auth = getattr(self.hass, "auth", None)
        if auth is None:
            return {}
        return {
            user.id: user
            for user in await auth.async_get_users()
            if user.is_active and not user.system_generated
        }

    async def _pairable_sessions(self) -> dict[str, RefreshToken]:
        """Normal app/browser logins of active, non-system users."""
        sessions: dict[str, RefreshToken] = {}
        for user in (await self._pairable_users()).values():
            for token in user.refresh_tokens.values():
                if token.token_type == TOKEN_TYPE_NORMAL:
                    sessions[token.id] = token
        return sessions

    async def _session_choices(
        self,
        recipients: list[dict[str, Any]],
        editing_id: str | None,
        current: dict[str, Any] | None = None,
    ) -> tuple[dict[str, str], list[SelectOptionDict]]:
        """Selectable pairings for the recipient form; "—" means not paired.

        Returns the valid encoded values (value -> "user"/"token") and the
        select options: first every HA user (the default kind of pairing: every
        normal login of that user, also after a new login), then every single
        login (for one user with several devices that need different rights). A
        stored pairing that is no longer selectable stays offered for the
        edited recipient, so saving the form unchanged never drops it.
        """
        # Labels are language-neutral (the options flow cannot know the viewer's
        # language): 👤 = HA user, 🔑 = one single login. The field description
        # in the translations explains both symbols.
        user_word, login_word = "👤", "🔑"
        users = await self._pairable_users()
        sessions = await self._pairable_sessions()
        paired_by = {
            _pairing_value(raw): str(raw.get(RECIPIENT_NAME, raw.get(RECIPIENT_ID)))
            for raw in recipients
            if _pairing_value(raw) != _NO_PAIRING
            and str(raw.get(RECIPIENT_ID, "")) != (editing_id or "")
        }

        def linked(value: str) -> str:
            return f" · 🔗 {paired_by[value]}" if value in paired_by else ""

        choices: dict[str, str] = {}
        options = [SelectOptionDict(value=_NO_PAIRING, label="—")]
        for user in sorted(users.values(), key=lambda u: (u.name or "").casefold()):
            value = f"{_PAIR_USER}{user.id}"
            choices[value] = "user"
            options.append(
                SelectOptionDict(
                    value=value, label=f"{user_word} {user.name or user.id}{linked(value)}"
                )
            )
        for token in sorted(
            sessions.values(),
            key=lambda t: t.last_used_at or t.created_at,
            reverse=True,
        ):
            value = f"{_PAIR_TOKEN}{token.id}"
            used = token.last_used_at or token.created_at
            label = (
                f"{login_word} {token.user.name or '?'}"
                f" – {token.client_name or token.client_id or 'Browser'}"
                f" · {dt_util.as_local(used).strftime('%d.%m.%Y %H:%M') if used else '–'}"
                + (f" · {token.last_used_ip}" if token.last_used_ip else "")
                + linked(value)
            )
            choices[value] = "token"
            options.append(SelectOptionDict(value=value, label=label))
        stored = _pairing_value(current)
        if stored != _NO_PAIRING and stored not in choices:
            word = user_word if stored.startswith(_PAIR_USER) else login_word
            short = stored.split(":", 1)[1][:8]
            options.append(SelectOptionDict(value=stored, label=f"{word} ⚠ ({short}…)"))
        return choices, options

    @staticmethod
    def _session_error(
        session_id: str,
        choices: dict[str, str],
        recipients: list[dict[str, Any]],
        editing_id: str | None,
    ) -> str | None:
        """Validate a changed pairing: it must exist and belong to no other recipient."""
        if session_id == _NO_PAIRING:
            return None
        if session_id.startswith(_PAIR_USER):
            if choices.get(session_id) != "user":
                return "session_user_not_found"
            already = "session_user_already_paired"
        elif session_id.startswith(_PAIR_TOKEN):
            if choices.get(session_id) != "token":
                return "session_not_found"
            already = "session_already_paired"
        else:
            return "session_not_found"
        if any(
            _pairing_value(raw) == session_id
            and str(raw.get(RECIPIENT_ID, "")) != (editing_id or "")
            for raw in recipients
        ):
            return already
        return None

    @staticmethod
    def _apply_session(recipient: dict[str, Any], session_id: str | None) -> dict[str, Any]:
        """Set or clear only the pairing; every alarm setting stays as given.

        Exactly one of user or login is stored, never both.
        """
        if session_id is None:
            return recipient
        recipient = dict(recipient)
        recipient.pop(RECIPIENT_SESSION_TOKEN_ID, None)
        recipient.pop(RECIPIENT_SESSION_USER_ID, None)
        if session_id.startswith(_PAIR_TOKEN):
            recipient[RECIPIENT_SESSION_TOKEN_ID] = session_id.removeprefix(_PAIR_TOKEN)
        elif session_id.startswith(_PAIR_USER):
            recipient[RECIPIENT_SESSION_USER_ID] = session_id.removeprefix(_PAIR_USER)
        return recipient

    async def async_step_remove_recipient(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove one configured notification recipient."""
        if user_input is not None and user_input.get("go_back"):
            return await self.async_step_notifications()
        if error := self._navigation_error("remove_recipient", user_input):
            return error
        recipients = self._raw_recipients()
        if not recipients:
            return self.async_abort(reason="no_recipients_configured")

        if user_input is not None:
            remove_id = str(user_input[RECIPIENT_ID])
            updated = dict(self.config_entry.options)
            updated[CONF_NOTIFICATION_RECIPIENTS] = [
                raw for raw in recipients if str(raw.get(RECIPIENT_ID, "")) != remove_id
            ]
            await self._persist_options(updated)
            return await self.async_step_notifications()

        options = [
            SelectOptionDict(
                value=str(raw[RECIPIENT_ID]),
                label=str(raw.get(RECIPIENT_NAME, raw[RECIPIENT_ID])),
            )
            for raw in recipients
            if raw.get(RECIPIENT_ID)
        ]
        return self.async_show_form(
            step_id="remove_recipient",
            last_step=False,
            data_schema=probatio.Schema(
                {
                    probatio.Required(RECIPIENT_ID): SelectSelector(
                        SelectSelectorConfig(options=options)
                    )
                }
            ),
            description_placeholders=_recipient_description_placeholders(recipients),
        )

    async def _persist_options(self, updated: dict[str, Any]) -> None:
        """Save options immediately while keeping the Configure flow open."""
        manager = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        if manager is not None and not manager._closed:
            await manager.async_update_options(updated)
        else:
            self.hass.config_entries.async_update_entry(self.config_entry, options=updated)

    def _raw_recipients(self) -> list[dict[str, Any]]:
        """Return valid raw recipient option dictionaries."""
        raw = self.config_entry.options.get(CONF_NOTIFICATION_RECIPIENTS, [])
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, dict)]

    def _mobile_notify_services(self) -> list[str]:
        """Return currently registered Companion mobile notification services."""
        services = self.hass.services.async_services().get("notify", {})
        return sorted(
            f"notify.{service}" for service in services if service.startswith("mobile_app_")
        )

    @staticmethod
    def _validate_expert_options(values: dict[str, Any]) -> dict[str, str]:
        """Validate relationships between expert thresholds."""
        slow = float(values[CONF_SLOW_THRESHOLD_LPH])
        low = float(values[CONF_LOW_THRESHOLD_LPH])
        high = float(values[CONF_HIGH_THRESHOLD_LPH])
        burst = float(values[CONF_BURST_THRESHOLD_LPH])
        if not slow < low < high < burst:
            return {"base": "invalid_threshold_order"}
        if not 0 < float(values[CONF_LOW_QUIET_LPH]) < low:
            return {"base": "invalid_low_quiet_threshold"}
        if not 0 < float(values[CONF_HIGH_QUIET_LPH]) < high:
            return {"base": "invalid_high_quiet_threshold"}
        if not 0 < float(values[CONF_BURST_RESET_LPH]) < burst:
            return {"base": "invalid_burst_reset_threshold"}
        early, window = low_stability_minutes(values)
        enabled = values.get(CONF_LOW_STABILITY_ENABLED, DEFAULT_LOW_STABILITY_ENABLED)
        relative = float(
            values.get(CONF_LOW_STABILITY_RELATIVE_PERCENT, DEFAULT_LOW_STABILITY_RELATIVE_PERCENT)
        )
        absolute = float(
            values.get(CONF_LOW_STABILITY_ABSOLUTE_LPH, DEFAULT_LOW_STABILITY_ABSOLUTE_LPH)
        )
        required = float(
            values.get(CONF_LOW_STABILITY_REQUIRED_PERCENT, DEFAULT_LOW_STABILITY_REQUIRED_PERCENT)
        )
        # Disabled stability retains saved times without enforcing their relation.
        if enabled and (
            not all(isfinite(value) for value in (early, window))
            or not 0 < window <= early
            or early >= float(values.get(CONF_LOW_DETECTION_MIN, DEFAULT_LOW_DETECTION_MIN))
        ):
            return {"base": "invalid_low_stability"}
        if (
            not all(isfinite(value) for value in (relative, absolute, required))
            or relative <= 0
            or absolute <= 0
            or not 0 < required <= 100
        ):
            return {"base": "invalid_low_stability"}
        return {}
