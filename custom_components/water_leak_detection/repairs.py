"""Idempotent post-commit legacy-learning repair reconciliation."""

from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN
from .storage import LEGACY_MIGRATION_ID


def reconcile_legacy_repair(hass, entry, marker) -> None:
    """A stable registry ID preserves dismissal, including after a partial crash."""
    if not isinstance(marker, dict) or marker.get("legacy_learning_quarantined") is not True:
        return
    ir.async_create_issue(
        hass, DOMAIN, f"{entry.entry_id}_{LEGACY_MIGRATION_ID}",
        is_fixable=False, is_persistent=True, severity=ir.IssueSeverity.WARNING,
        translation_key="legacy_learning_quarantined",
        translation_placeholders={"name": entry.title},
    )
