"""Idempotent post-commit legacy-learning repair reconciliation."""

from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN
from .storage import LEGACY_MIGRATION_ID


def reconcile_legacy_repair(hass, entry, marker) -> None:
    """A stable registry ID preserves dismissal, including after a partial crash."""
    if not isinstance(marker, dict) or marker.get("legacy_learning_quarantined") is not True:
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"{entry.entry_id}_{LEGACY_MIGRATION_ID}",
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="legacy_learning_quarantined",
        translation_placeholders={"name": entry.title},
    )


def reconcile_mqtt_reports_repair(hass, entry, warning: bool) -> None:
    """Require actual repeated MQTT reports; never synthesize them from ticks."""
    issue_id = f"{entry.entry_id}_mqtt_identical_reports"
    if not warning:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="mqtt_identical_reports",
        translation_placeholders={"entity_id": entry.data["flow_entity"]},
    )


def reconcile_mqtt_provenance_repair(hass, entry, rejected: bool) -> None:
    """A blocked stream needs upstream origin data, never synthetic zero reports."""
    issue_id = f"{entry.entry_id}_mqtt_measurement_provenance"
    if not rejected:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key="mqtt_measurement_provenance",
        translation_placeholders={"entity_id": entry.data["flow_entity"]},
    )


def reconcile_runtime_recovery(hass, entry, required: bool) -> None:
    """A safety quarantine needs operator recovery, never an automatic reset."""
    issue_id = f"{entry.entry_id}_runtime_safety_recovery"
    if not required:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.ERROR,
        translation_key="runtime_safety_recovery",
        translation_placeholders={"name": entry.title},
    )
