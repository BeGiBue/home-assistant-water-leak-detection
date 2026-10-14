/*
 * Water Leak Guard card for Home Assistant dashboards.
 *
 * Frontend view for the `water_leak_detection` integration. The card is a pure
 * view on the existing entities and services and is not a trust boundary: it
 * never holds recipient tokens or reset nonces, and every safety decision
 * (authorization, Home presence, allowed alarm actions) stays in the backend.
 *
 * Alarm actions (stage C): the card asks `water_leak_detection/session` what this
 * device may do and shows only those actions. It asks on connect, when the page
 * becomes visible, when an alarm starts, after each command, when the paired
 * recipient's tracker changes and every 60 s during an alarm – never per render. The device is identified by the
 * backend through the HA login of the connection, paired with one notification
 * recipient; "home" comes only from that recipient's device tracker in the
 * backend. Every action is re-checked by the backend when it is executed.
 *   - Mute: this device only, also away.
 *   - Global acknowledgement: only while that recipient is Home.
 *   - External reset: external leaks only, Home and permission required; asks first.
 *   - Hydraulic alarms have no card command. They end when the flow meets their
 *     quiet/reset condition. Switching the Slow Leak or Low Flow detector off, or
 *     starting the High Flow bypass, also ends that detector's ACTIVE alarm at
 *     once (incl. its share of the shutoff request) without fixing the cause; the
 *     card asks for confirmation first. Burst Leak can be neither disabled nor bypassed.
 *   - Since 0.5.0 the card has no detector switches. "Disable detection" exists
 *     only inside the alarm box while that detector's alarm is ACTIVE, and both
 *     alarm-ending actions (disable, bypass start during a High Flow alarm) are
 *     offered only to a paired device at home – the same rule as every other
 *     action that ends an alarm ("acknowledge from anywhere, clear only from
 *     home"). This is a card rule only: HA entities and services stay unrestricted.
 * Acknowledging and muting never end detection, the alarm or the shutoff request.
 *
 * License: AGPL-3.0-only (same as the integration).
 */

const CARD_VERSION = "0.5.0";
const DOMAIN = "water_leak_detection";
const CARD_TAG = "water-leak-guard-card";
const EDITOR_TAG = "water-leak-guard-card-editor";

/** Backend card commands as registered in websocket.py (`config_entry_id` optional in all). */
const INTERFACE = {
  session: `${DOMAIN}/session`, // { config_entry_id? } -> { paired, recipient_id, home, can_global_ack, can_external_reset, ... }
  mute: `${DOMAIN}/mute`, // { config_entry_id?, event_id }
  acknowledge: `${DOMAIN}/acknowledge`, // { config_entry_id?, event_id }
  externalReset: `${DOMAIN}/external_reset`, // { config_entry_id?, event_id, source_id, source_generation }
  integrationPath: `/config/integrations/integration/${DOMAIN}`,
};

/** Stable error codes of the backend commands, plus HA's own unknown_command. */
const ERROR_CODES = [
  "not_paired",
  "not_home",
  "not_allowed",
  "event_not_active",
  "not_committed",
  "rejected",
  "instance_not_found",
  "unknown_command",
];
const SESSION_MIN_INTERVAL_MS = 5000;
const SESSION_ALARM_INTERVAL_MS = 60000;

const MONITORING_STATES = ["active", "waiting_for_measurement", "blocked"];

const DEFAULT_CONFIG = {
  show_flow: true,
  show_detectors: true,
  show_bypass: true,
  show_external: true,
  show_learning: true,
  show_background: true,
  bypass_presets: [60, 120, 240],
};

const I18N = {
  de: {
    title: "Wasserwächter",
    not_found: "Keine Instanz der Integration gefunden. Bitte im Karteneditor die Status-Entität wählen.",
    status: {
      unavailable: "Status nicht verfügbar",
      source_unavailable: "Messquelle nicht verfügbar",
      idle: "Kein Alarm",
      all_quiet: "Alles ruhig",
      impaired: "Überwachung eingeschränkt",
      slow_leak_monitoring: "Slow Leak wird geprüft",
      low_flow_monitoring: "Low Flow wird geprüft",
      high_flow_monitoring: "High Flow wird geprüft",
      burst_leak_monitoring: "Burst Leak wird geprüft",
      slow_leak: "Slow Leak",
      low_flow: "Low Flow",
      high_flow: "High Flow",
      burst_leak: "Burst Leak",
      external_leak: "Externes Leck",
    },
    detector: {
      slow_leak: "Slow Leak",
      low_flow: "Low Flow",
      high_flow: "High Flow",
      burst_leak: "Burst Leak",
      external_leak: "Externer Sensor",
    },
    detector_hint: {
      slow_leak: "Sehr kleiner Dauerverlust",
      low_flow: "Mäßiger Durchfluss über lange Zeit",
      high_flow: "Anhaltend hoher Verbrauch",
      burst_leak: "Rohrbruch",
    },
    phase: { idle: "Bereit", monitoring: "Prüft", active: "Alarm", off: "Aus", bypass: "Bypass", paused: "Pausiert" },
    paused_hint: "Ohne gültige Messung wird nicht ausgewertet. Laufender Fortschritt bleibt erhalten.",
    monitoring: {
      label: "Hydraulische Überwachung",
      active: "Aktiv",
      waiting_for_measurement: "Warte auf Messung",
      blocked: "Gesperrt",
      unavailable: "Nicht verfügbar",
      missing: "Unbekannt",
    },
    monitoring_hint: {
      active: "Der Durchfluss wird ausgewertet.",
      waiting_for_measurement: "Seit dem Start liegt noch keine gültige Messung vor. Die Leckerkennung wertet noch nichts aus.",
      blocked: "Messwerte werden zurzeit nicht ausgewertet. Bestehende Alarme bleiben bestehen.",
      unavailable: "Die Entität ist nicht verfügbar. Der Überwachungszustand ist unbekannt.",
      missing: "Diese Version der Integration meldet ihren Überwachungszustand nicht (ab 1.2.0-beta.3). Ob ausgewertet wird, ist unbekannt.",
    },
    monitoring_details: "Grund und Messherkunft",
    monitoring_ok: "Hydraulik aktiv",
    detail: {
      reason: "Grund",
      source: "Messquelle",
      provenance: "MQTT-Messherkunft",
      last_measurement: "Letzte gültige Messung",
      age: "Alter",
    },
    reason: {
      verified_measurement: "Gültige Messung",
      waiting_for_measurement: "Noch keine Messung seit dem Start",
      source_unavailable: "Messquelle meldet keinen gültigen Zustand",
      source_missing: "Messquellen-Entität fehlt",
      source_timeout: "Zu lange keine neue Messung (Expertengrenze überschritten)",
      invalid_flow_measurement: "Ungültiger Messwert",
      provenance_persistence_failed: "Messherkunft konnte nicht gespeichert werden",
      awaiting_original_measurement: "Warte auf originale Messzeit des Zählers",
      startup_not_initialized: "Start noch nicht abgeschlossen",
      unsupported_mqtt_adapter: "MQTT-Quelle wird nicht unterstützt",
      original_measurement_missing: "Originale Messzeit fehlt im MQTT-Telegramm (Feld timestamp)",
      retained_or_unbound_message: "Gespeicherte (retained) oder nicht zuordenbare MQTT-Nachricht",
      out_of_order_original_message: "MQTT-Nachricht in falscher Reihenfolge",
      pre_startup_measurement: "Messung stammt von vor dem Start",
      unbound_rendered_state: "Zustand ohne zugehörige MQTT-Messung",
      invalid_original_identity: "Ungültige Messkennung",
      replayed_or_out_of_order_measurement: "Wiederholte oder veraltete Messung",
      future_measurement: "Messzeit liegt in der Zukunft",
      stale_measurement: "Messung ist zu alt",
      verified_original_measurement: "Originale Messzeit geprüft",
      not_mqtt: "Keine MQTT-Quelle",
    },
    alarm: "Leckalarm",
    shutoff: "Absperrung angefordert",
    no_shutoff: "Keine Absperrung",
    since: "seit",
    duration: "Dauer",
    volume: "Volumen",
    acknowledged: "Quittiert",
    acknowledged_by: "Quittiert von {who}",
    not_acknowledged: "Nicht quittiert",
    acknowledge: "Global quittieren",
    acknowledge_hint: "Quittieren stoppt nur Benachrichtigungen. Erkennung, Alarm und Absperranforderung bleiben bestehen.",
    mute: "Für dieses Gerät stummschalten",
    mute_hint: "Stoppt Benachrichtigungen nur für dieses Gerät. Erkennung, Alarm und Absperranforderung bleiben bestehen.",
    muted_here: "Auf diesem Gerät stummgeschaltet",
    mute_for: "Für {name} stummschalten",
    mute_hint_for: "Stoppt Benachrichtigungen nur für {name}. Erkennung, Alarm und Absperranforderung bleiben bestehen.",
    muted_for: "Bei {name} stummgeschaltet",
    muted_count: "Auf {n} Gerät(en) stummgeschaltet",
    requires_home: "Nur zuhause möglich",
    external_reset: "Externes Leck zurücksetzen",
    external_reset_confirm: "Externes Leck „{name}“ zurücksetzen?\n\nDer Alarm dieses Sensors und sein Beitrag zur Absperranforderung enden sofort. Das Wasser am Sensor wird dadurch nicht beseitigt. Der Sensor wird erst wieder scharf, wenn er trocken meldet.",
    how_external_reset: "Endet durch „Externes Leck zurücksetzen“ – nur zuhause und mit Berechtigung, hier oder in der Benachrichtigung. Der Sensor wird erst wieder scharf, wenn er trocken meldet.",
    session_unpaired: "Dieses Gerät ist nicht gekoppelt – nur Anzeige.",
    session_pair_hint: "Koppeln: Konfigurieren → Benachrichtigungsempfänger → Empfänger bearbeiten → Kopplung für die Dashboard-Karte (Benutzer oder einzelne Anmeldung).",
    session_no_backend: "Dieses Backend bietet keine Kartenaktionen an.",
    session_failed: "Kartenaktionen sind gerade nicht verfügbar.",
    success: {
      mute: "Auf diesem Gerät stummgeschaltet. Der Alarm bleibt bestehen.",
      mute_for: "Für {name} stummgeschaltet. Der Alarm bleibt bestehen.",
      acknowledge: "Global quittiert. Alarm und Absperranforderung bleiben bestehen.",
      external_reset: "Externes Leck zurückgesetzt. Der Sensor wird wieder scharf, sobald er trocken meldet.",
    },
    error: {
      not_paired: "Dieses Gerät ist nicht (mehr) gekoppelt.",
      not_home: "Nur zuhause möglich: Dieses Gerät ist laut Device Tracker nicht zuhause.",
      not_allowed: "Diese Aktion ist für dieses Gerät nicht freigegeben.",
      event_not_active: "Das Ereignis ist nicht mehr aktiv.",
      not_committed: "Konnte nicht dauerhaft gespeichert werden. Es wurde nichts geändert.",
      rejected: "Vom Backend abgelehnt.",
      instance_not_found: "Instanz nicht gefunden oder mehrdeutig. Bitte die Status-Entität der Karte prüfen.",
      unknown_command: "Dieses Backend bietet keine Kartenaktionen an.",
      unknown: "Aktion fehlgeschlagen: {msg}",
    },
    open_integration: "Zur Integration",
    hydraulic_clears_itself: "Endet, sobald der Durchfluss die Ruhe-/Rücksetzbedingung erfüllt. Slow Leak und Low Flow enden auch beim Ausschalten ihres Detektors, High Flow beim Start des Bypass – die Ursache wird dadurch nicht behoben. Burst Leak endet nur physisch.",
    ends_slow_low: "Endet, sobald der Durchfluss die Ruhe-/Rücksetzbedingung erfüllt. „Erkennung abschalten“ beendet den Alarm ebenfalls sofort – die Ursache (z. B. ein offener Hahn oder ein Leck) wird dadurch nicht behoben.",
    ends_high: "Endet, sobald der Durchfluss die Ruhe-/Rücksetzbedingung erfüllt. Der Start des High-Flow-Bypass beendet den Alarm ebenfalls sofort – die Ursache (z. B. ein offener Hahn oder ein Leck) wird dadurch nicht behoben.",
    ends_burst: "Endet nur physisch: sobald der Durchfluss die Ruhe-/Rücksetzbedingung erfüllt. Burst Leak lässt sich weder ausschalten noch per Bypass überbrücken.",
    confirm_disable: "Ein Alarm „{kind}“ läuft. Ausschalten des Detektors beendet diesen Alarm und seinen Beitrag zur Absperranforderung sofort. Die Ursache (z. B. ein offener Hahn oder ein Leck) wird dadurch nicht behoben. Der Burst-Leak-Schutz bleibt aktiv.\n\nDetektor trotzdem ausschalten?",
    confirm_bypass: "Ein High-Flow-Alarm läuft. Der Start des Bypass beendet diesen Alarm und seinen Beitrag zur Absperranforderung sofort. Die Ursache (z. B. ein offener Hahn oder ein Leck) wird dadurch nicht behoben. Der Burst-Leak-Schutz bleibt aktiv.\n\nBypass trotzdem starten?",
    storage_paused_hint: "Laufzeitspeicher beschädigt – der Zustand der Erkennung ist nicht gesichert.",
    external_offline_banner: "Ein externer Lecksensor ist nicht erreichbar. Ein Leck an dieser Stelle würde nicht erkannt.",
    action_failed: "Aktion abgelehnt: {msg}",
    integration_unavailable: "Die Integration liefert keinen Status. Die Anzeige ist nicht aktuell.",
    sensor_unavailable: "Nicht verfügbar",
    flow: "Durchfluss",
    flow_unavailable: "Kein Messwert",
    high: "High",
    burst: "Burst",
    detectors: "Erkennung",
    disable_detection: "Erkennung abschalten",
    disable_detection_hint: "Schaltet diesen Detektor aus und beendet damit seinen Alarm. Wieder einschalten über die Geräteseite der Integration.",
    bypass_start_alarm: "Bypass starten",
    bypass: "High-Flow-Bypass",
    bypass_off: "Aus – High Flow wird überwacht",
    bypass_on: "Aktiv – noch {left}",
    bypass_until: "bis {time}",
    bypass_presets: "Dauer wählen",
    bypass_stop: "Beenden",
    bypass_default: "Standard",
    bypass_note: "Burst-Leak-Schutz bleibt immer aktiv.",
    external: "Externe Lecksensoren",
    external_phase: { ARMED: "Trocken", ACTIVE: "Leck", RESET_WAITING_FOR_OFF: "Wartet auf trocken" },
    external_conflict: "Identitätskonflikt",
    contributes_shutoff: "Löst Absperrung aus",
    learning: "Lernmodell",
    confidence: { insufficient: "Unzureichend", learning: "Lernt", reliable: "Zuverlässig", unknown: "Unbekannt" },
    coverage: "Abdeckung",
    coverage_short: "{n}/{w} Tage",
    days: "{n} von {w} Tagen",
    days_unit: "Tage",
    learned_max: "Normalspitze",
    long_term_max: "Langzeit-Max.",
    long_term_max_long: "Langzeitmaximum",
    samples: "Lernwerte",
    reset_learning: "Lernmodell zurücksetzen",
    reset_learning_confirm: "Alle gelernten Werte löschen? Detektoreinstellungen und aktive Alarme bleiben unverändert.",
    storage_recovery: "Laufzeitspeicher beschädigt – Alarm und Absperrung bleiben aus Sicherheitsgründen aktiv. Bitte Backup wiederherstellen.",
    source_unavailable_banner: "Die Messquelle liefert keine gültigen Werte. Laufende Alarme bleiben bestehen.",
    editor: {
      entity: "Status-Entität",
      title: "Titel (optional)",
      show_flow: "Durchfluss",
      show_detectors: "Erkennung",
      show_bypass: "Bypass",
      show_external: "Externe Sensoren",
      show_learning: "Lernmodell",
      show_background: "Hintergrundmotiv",
      title_hint: "Ohne Titel wird der Gerätename aus Home Assistant verwendet.",
    },
  },
  en: {
    title: "Water Leak Guard",
    not_found: "No Water Leak Guard instance found. Pick the status entity in the card editor.",
    status: {
      unavailable: "Status unavailable",
      source_unavailable: "Source unavailable",
      idle: "No alarm",
      all_quiet: "All quiet",
      impaired: "Monitoring impaired",
      slow_leak_monitoring: "Checking Slow Leak",
      low_flow_monitoring: "Checking Low Flow",
      high_flow_monitoring: "Checking High Flow",
      burst_leak_monitoring: "Checking Burst Leak",
      slow_leak: "Slow Leak",
      low_flow: "Low Flow",
      high_flow: "High Flow",
      burst_leak: "Burst Leak",
      external_leak: "External leak",
    },
    detector: {
      slow_leak: "Slow Leak",
      low_flow: "Low Flow",
      high_flow: "High Flow",
      burst_leak: "Burst Leak",
      external_leak: "External sensor",
    },
    detector_hint: {
      slow_leak: "Very small continuous loss",
      low_flow: "Moderate flow lasting too long",
      high_flow: "Sustained high consumption",
      burst_leak: "Pipe failure",
    },
    phase: { idle: "Ready", monitoring: "Checking", active: "Alarm", off: "Off", bypass: "Bypass", paused: "Paused" },
    paused_hint: "Nothing is evaluated without a valid measurement. Existing progress is kept.",
    monitoring: {
      label: "Hydraulic monitoring",
      active: "Active",
      waiting_for_measurement: "Waiting for measurement",
      blocked: "Blocked",
      unavailable: "Unavailable",
      missing: "Unknown",
    },
    monitoring_hint: {
      active: "Flow is being evaluated.",
      waiting_for_measurement: "No valid measurement since startup yet. Leak detection is not evaluating anything yet.",
      blocked: "Measurements are currently not evaluated. Existing alarms stay active.",
      unavailable: "The entity is unavailable. The monitoring state is unknown.",
      missing: "This integration version does not report its monitoring state (available from 1.2.0-beta.3). Whether it is evaluating is unknown.",
    },
    monitoring_details: "Reason and measurement provenance",
    monitoring_ok: "Hydraulics active",
    detail: {
      reason: "Reason",
      source: "Source",
      provenance: "MQTT provenance",
      last_measurement: "Last valid measurement",
      age: "Age",
    },
    reason: {
      verified_measurement: "Valid measurement",
      waiting_for_measurement: "No measurement since startup yet",
      source_unavailable: "Source reports no valid state",
      source_missing: "Source entity is missing",
      source_timeout: "No new measurement for too long (expert limit exceeded)",
      invalid_flow_measurement: "Invalid measurement",
      provenance_persistence_failed: "Measurement provenance could not be saved",
      awaiting_original_measurement: "Waiting for the meter's original measurement time",
      startup_not_initialized: "Startup not finished yet",
      unsupported_mqtt_adapter: "Unsupported MQTT source",
      original_measurement_missing: "Original measurement time missing in MQTT message (timestamp field)",
      retained_or_unbound_message: "Retained or unbound MQTT message",
      out_of_order_original_message: "MQTT message out of order",
      pre_startup_measurement: "Measurement predates startup",
      unbound_rendered_state: "State without a matching MQTT measurement",
      invalid_original_identity: "Invalid measurement identity",
      replayed_or_out_of_order_measurement: "Replayed or outdated measurement",
      future_measurement: "Measurement time lies in the future",
      stale_measurement: "Measurement is too old",
      verified_original_measurement: "Original measurement time verified",
      not_mqtt: "Not an MQTT source",
    },
    alarm: "Leak alarm",
    shutoff: "Shutoff requested",
    no_shutoff: "No shutoff",
    since: "since",
    duration: "Duration",
    volume: "Volume",
    acknowledged: "Acknowledged",
    acknowledged_by: "Acknowledged by {who}",
    not_acknowledged: "Not acknowledged",
    acknowledge: "Acknowledge globally",
    acknowledge_hint: "Acknowledging only stops notifications. Detection, alarm and shutoff request stay active.",
    mute: "Mute on this device",
    mute_hint: "Stops notifications for this device only. Detection, alarm and shutoff request stay active.",
    muted_here: "Muted on this device",
    mute_for: "Mute for {name}",
    mute_hint_for: "Stops notifications for {name} only. Detection, alarm and shutoff request stay active.",
    muted_for: "Muted for {name}",
    muted_count: "Muted on {n} device(s)",
    requires_home: "Only possible at home",
    external_reset: "Reset external leak",
    external_reset_confirm: "Reset external leak “{name}”?\n\nThis sensor's alarm and its contribution to the shutoff request end immediately. The water at the sensor is not removed. The sensor re-arms only after it reports dry.",
    how_external_reset: "Ends with “Reset external leak” – only at home and with permission, here or from the notification. The sensor re-arms only after it reports dry.",
    session_unpaired: "This device is not paired – view only.",
    session_pair_hint: "To pair: Configure → Notification recipients → Edit recipient → Pairing for the dashboard card (user or single login).",
    session_no_backend: "This backend does not offer card actions.",
    session_failed: "Card actions are currently unavailable.",
    success: {
      mute: "Muted on this device. The alarm stays active.",
      mute_for: "Muted for {name}. The alarm stays active.",
      acknowledge: "Acknowledged globally. Alarm and shutoff request stay active.",
      external_reset: "External leak reset. The sensor re-arms once it reports dry.",
    },
    error: {
      not_paired: "This device is not (or no longer) paired.",
      not_home: "Only possible at home: this device's tracker is not home.",
      not_allowed: "This action is not permitted for this device.",
      event_not_active: "The event is no longer active.",
      not_committed: "Could not be saved durably. Nothing was changed.",
      rejected: "Rejected by the backend.",
      instance_not_found: "Instance not found or ambiguous. Please check the card's status entity.",
      unknown_command: "This backend does not offer card actions.",
      unknown: "Action failed: {msg}",
    },
    open_integration: "Open integration",
    hydraulic_clears_itself: "Ends once the flow meets its quiet/reset condition. Slow Leak and Low Flow also end when their detector is switched off, High Flow when the bypass is started – without fixing the cause. Burst Leak ends only physically.",
    ends_slow_low: "Ends once the flow meets its quiet/reset condition. “Disable detection” also ends the alarm at once – without fixing the cause (e.g. an open tap or a leak).",
    ends_high: "Ends once the flow meets its quiet/reset condition. Starting the High Flow bypass also ends the alarm at once – without fixing the cause (e.g. an open tap or a leak).",
    ends_burst: "Ends only physically: once the flow meets its quiet/reset condition. Burst Leak can be neither switched off nor bypassed.",
    confirm_disable: "A {kind} alarm is running. Switching the detector off ends this alarm and its contribution to the shutoff request immediately. The cause (e.g. an open tap or a leak) is not fixed. Burst Leak protection stays active.\n\nSwitch the detector off anyway?",
    confirm_bypass: "A High Flow alarm is running. Starting the bypass ends this alarm and its contribution to the shutoff request immediately. The cause (e.g. an open tap or a leak) is not fixed. Burst Leak protection stays active.\n\nStart the bypass anyway?",
    storage_paused_hint: "Runtime store damaged – the detection state is not reliable.",
    external_offline_banner: "An external leak sensor is unreachable. A leak at that spot would not be detected.",
    action_failed: "Action rejected: {msg}",
    integration_unavailable: "The integration reports no status. The display is not current.",
    sensor_unavailable: "Unavailable",
    flow: "Flow",
    flow_unavailable: "No reading",
    high: "High",
    burst: "Burst",
    detectors: "Detection",
    disable_detection: "Disable detection",
    disable_detection_hint: "Switches this detector off and so ends its alarm. Switch it back on from the integration's device page.",
    bypass_start_alarm: "Start bypass",
    bypass: "High Flow bypass",
    bypass_off: "Off – High Flow is monitored",
    bypass_on: "Active – {left} left",
    bypass_until: "until {time}",
    bypass_presets: "Choose duration",
    bypass_stop: "Stop",
    bypass_default: "Default",
    bypass_note: "Burst Leak protection always stays active.",
    external: "External leak sensors",
    external_phase: { ARMED: "Dry", ACTIVE: "Leak", RESET_WAITING_FOR_OFF: "Waiting for dry" },
    external_conflict: "Identity conflict",
    contributes_shutoff: "Triggers shutoff",
    learning: "Learning",
    confidence: { insufficient: "Insufficient", learning: "Learning", reliable: "Reliable", unknown: "Unknown" },
    coverage: "Coverage",
    coverage_short: "{n}/{w} days",
    days: "{n} of {w} days",
    days_unit: "days",
    learned_max: "Normal peak",
    long_term_max: "Long-term max",
    long_term_max_long: "Long-term maximum",
    samples: "Samples",
    reset_learning: "Reset learning",
    reset_learning_confirm: "Delete all learned values? Detector settings and active alarms stay unchanged.",
    storage_recovery: "Runtime store damaged – alarm and shutoff stay active for safety. Please restore a backup.",
    source_unavailable_banner: "The measurement source reports no valid values. Running alarms stay active.",
    editor: {
      entity: "Status entity",
      title: "Title (optional)",
      show_flow: "Flow",
      show_detectors: "Detection",
      show_bypass: "Bypass",
      show_external: "External sensors",
      show_learning: "Learning",
      show_background: "Background motif",
      title_hint: "Without a title the Home Assistant device name is used.",
    },
  },
};

const HYDRAULIC_KINDS = ["slow_leak", "low_flow", "high_flow", "burst_leak"];
/** Values of `active_detector` / status state that name a real alarm kind. */
const ALARM_KINDS = [...HYDRAULIC_KINDS, "external_leak"];

function isOffline(state) {
  return !state || state.state === "unavailable" || state.state === "unknown";
}

/** A configured, non-ACTIVE external source whose own sensor cannot report "dry". */
function externalOffline(hass, attrs) {
  return (attrs?.external_sources || []).some(
    (s) => s && !s.tombstone && s.phase !== "ACTIVE" && isOffline(hass?.states?.[s.source_entity])
  );
}

/* ------------------------------------------------------------------ helpers */

function lang(hass) {
  const code = (hass?.locale?.language || hass?.language || "en").toLowerCase();
  return code.startsWith("de") ? "de" : "en";
}

function translator(hass) {
  const table = I18N[lang(hass)];
  return (path, vars = {}) => {
    let value = path.split(".").reduce((node, key) => (node == null ? node : node[key]), table);
    if (value == null) value = path.split(".").reduce((node, key) => (node == null ? node : node[key]), I18N.en);
    if (typeof value !== "string") return path;
    return value.replace(/\{(\w+)\}/g, (_, key) => (vars[key] ?? ""));
  };
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function num(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function formatNumber(hass, value, digits = 0) {
  if (value == null) return "–";
  return new Intl.NumberFormat(hass?.locale?.language || hass?.language || "en", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  }).format(value);
}

function formatSeconds(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h} h ${String(m).padStart(2, "0")} min`;
  if (m > 0) return `${m} min`;
  return `${s} s`;
}

function formatClock(hass, iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const sameDay = new Date().toDateString() === date.toDateString();
  return new Intl.DateTimeFormat(hass?.locale?.language || hass?.language || "en", {
    ...(sameDay ? {} : { day: "2-digit", month: "2-digit" }),
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

/** All status sensors of this integration (one per instance). */
function statusEntityIds(hass) {
  return Object.values(hass?.entities || {})
    .filter((e) => e.platform === DOMAIN && e.translation_key === "status")
    .map((e) => e.entity_id);
}

/** First status sensor of this integration, for auto-configuration. */
function findStatusEntity(hass) {
  return statusEntityIds(hass)[0];
}

/** Map translation_key -> entity_id for the device that owns the status sensor. */
function resolveEntities(hass, statusEntityId) {
  const registry = hass?.entities || {};
  const map = { status: statusEntityId };
  const own = registry[statusEntityId];
  if (!own || !own.device_id) return map;
  for (const entry of Object.values(registry)) {
    if (entry.platform === DOMAIN && entry.device_id === own.device_id && entry.translation_key) {
      map[entry.translation_key] = entry.entity_id;
    }
  }
  return map;
}

/** Device name as configured in Home Assistant (respects a user rename). */
function deviceName(hass, statusEntityId) {
  const deviceId = hass?.entities?.[statusEntityId]?.device_id;
  const device = deviceId ? hass?.devices?.[deviceId] : undefined;
  return device?.name_by_user || device?.name || undefined;
}

function fire(node, type, detail = {}) {
  node.dispatchEvent(new CustomEvent(type, { detail, bubbles: true, composed: true }));
}

function navigate(path) {
  window.history.pushState(null, "", path);
  window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
}

/* --------------------------------------------------------------------- card */

class WaterLeakGuardCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._busy = new Set();
    this._signature = "";
    this._configEntryId = undefined;
    this._configEntryLookup = undefined;
    // Session: what this device may do. Never a permission, only what to offer.
    this._session = { state: "pending" };
    this._sessionSeq = 0;
    this._sessionLastAt = -Infinity;
    this._sessionTimer = undefined;
    this._sessionInterval = undefined;
    // Session triggers that are independent of the render signature.
    this._lastAlarm = undefined;
    this._trackerSig = undefined;
    // Collapsible sections: per card instance, survives every re-render.
    this._expanded = { bypass: false, learning: false };
    this._onVisibility = () => {
      // A burst of visibility events needs one answer, not a deferred second one.
      if (document.visibilityState === "visible") this._requestSession({ defer: false });
    };
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
  }

  connectedCallback() {
    document.addEventListener("visibilitychange", this._onVisibility);
    if (!this._sessionInterval) {
      // Poll only while an alarm is active; without an alarm no buttons are shown.
      this._sessionInterval = setInterval(() => {
        if (this.isConnected && this._alarmActive()) this._requestSession({ defer: false });
      }, SESSION_ALARM_INTERVAL_MS);
    }
    // hass may have been set while disconnected: render now.
    this._signature = "";
    this._update();
    this._lastAlarm = this._alarmActive();
    this._requestSession({ defer: false });
  }

  disconnectedCallback() {
    document.removeEventListener("visibilitychange", this._onVisibility);
    clearInterval(this._sessionInterval);
    clearTimeout(this._sessionTimer);
    this._sessionInterval = undefined;
    this._sessionTimer = undefined;
    this._sessionSeq += 1; // answers still in flight are ignored
  }

  static get cardVersion() {
    return CARD_VERSION;
  }

  static getConfigElement() {
    return document.createElement(EDITOR_TAG);
  }

  static getStubConfig(hass) {
    return { type: `custom:${CARD_TAG}`, entity: findStatusEntity(hass) };
  }

  setConfig(config) {
    if (!config || typeof config !== "object") throw new Error("Invalid configuration");
    if (config.bypass_presets !== undefined && !Array.isArray(config.bypass_presets)) {
      throw new Error("bypass_presets must be a list of minutes");
    }
    if (this._config && this._config.entity !== config.entity) {
      // Another instance may be meant: forget its entry id and session.
      this._configEntryId = undefined;
      this._configEntryLookup = undefined;
      this._session = { state: "pending" };
      this._sessionSeq += 1;
      this._sessionLastAt = -Infinity;
      this._trackerSig = undefined;
      this._config = { ...DEFAULT_CONFIG, ...config };
      if (this.isConnected) this._requestSession({ defer: false });
    }
    this._config = { ...DEFAULT_CONFIG, ...config };
    this._signature = "";
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    // A detached card neither renders nor talks to the backend.
    if (!this.isConnected) return;
    this._update();
    // Session triggers (not the render signature): alarm start and tracker change.
    const alarm = this._alarmActive();
    if (alarm && this._lastAlarm === false) this._requestSession();
    this._lastAlarm = alarm;
    const trackerSig = this._trackerState()?.state;
    if (this._trackerSig !== undefined && trackerSig !== this._trackerSig) this._requestSession();
    if (this._sessionTrackerId()) this._trackerSig = trackerSig;
  }

  _update() {
    const signature = this._computeSignature();
    if (signature !== this._signature) {
      this._signature = signature;
      this._render();
    }
  }

  /** The paired recipient's tracker, named by the session (refresh trigger and UI hint only). */
  _sessionTrackerId() {
    const d = this._session.state === "ok" ? this._session.data : {};
    return d.paired === true && typeof d.tracker_entity === "string" ? d.tracker_entity : undefined;
  }

  _trackerState() {
    const id = this._sessionTrackerId();
    return id ? this._hass?.states?.[id] : undefined;
  }

  get hass() {
    return this._hass;
  }

  /**
   * Masonry height hint in 50 px units. The idle card is about 340 px (7 units)
   * in one column with both sections collapsed; an alarm adds the alarm box
   * (about 700 px). Masonry only uses it to balance columns.
   */
  getCardSize() {
    const alarm = this._hass && this._config ? this._alarmActive() : false;
    return alarm ? 14 : 7;
  }

  /**
   * Sections view: full section width by default (two columns inside the card
   * once it is about 600 px wide), never narrower than half a section; the
   * height follows the content.
   */
  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  /* ---------------------------------------------------------------- state */

  get _statusEntity() {
    return this._config?.entity || findStatusEntity(this._hass);
  }

  _computeSignature() {
    if (!this._hass || !this._config) return "";
    const ids = Object.values(resolveEntities(this._hass, this._statusEntity));
    // External sensors are other integrations' entities; their live availability
    // decides between "dry" and "unavailable", so they must trigger a re-render too.
    const status = this._hass.states[this._resolvedStatusId];
    for (const src of status?.attributes?.external_sources || []) {
      if (src?.source_entity) ids.push(src.source_entity);
    }
    const parts = ids.map((id) => {
      const s = this._hass.states[id];
      return s ? `${id}:${s.state}:${s.last_updated}` : `${id}:-`;
    });
    // The tracker only re-renders (home-only buttons); it never grants anything.
    const tracker = this._trackerState();
    parts.push(
      `t:${tracker ? tracker.state : "-"}`,
      `l:${lang(this._hass)}`,
      `a:${this._hass.user?.is_admin}`,
      `d:${deviceName(this._hass, this._statusEntity) || ""}`
    );
    return parts.join("|");
  }

  _state(map, key) {
    const id = map[key];
    return id ? this._hass.states[id] : undefined;
  }

  async _entryId(statusEntity) {
    if (this._configEntryId !== undefined) return this._configEntryId;
    if (!this._configEntryLookup) {
      this._configEntryLookup = this._hass
        .callWS({ type: "config/entity_registry/get", entity_id: statusEntity })
        .then((entry) => (this._configEntryId = entry?.config_entry_id || null))
        .catch(() => (this._configEntryId = null));
    }
    return this._configEntryLookup;
  }

  async _serviceData(extra = {}) {
    const entryId = await this._entryId(this._resolvedStatusId);
    return entryId ? { config_entry_id: entryId, ...extra } : { ...extra };
  }

  /* -------------------------------------------------------------- actions */

  /**
   * The status sensor the card actually renders: resolved via translation_key on
   * the device of the configured entity, so a mis-configured entity (e.g. the
   * flow sensor of the same device) still reaches the real status sensor.
   * Every safety decision must read from this id, never from the raw config.
   */
  get _resolvedStatusId() {
    return resolveEntities(this._hass, this._statusEntity).status;
  }

  /** Current phase of one hydraulic detector, read fresh from the resolved status sensor. */
  _detectorPhase(kind) {
    const status = this._hass?.states?.[this._resolvedStatusId];
    return status?.attributes?.detectors?.[kind];
  }

  /**
   * True if opening this entity's more-info dialog would offer a control the
   * card must not offer: the Slow Leak/Low Flow detector switches never (the
   * card has no switches since 0.5.0; disabling exists only as a confirmed alarm
   * action), the bypass switch/duration during an ACTIVE High Flow alarm.
   * Rendering never links these entities; this is defense in depth.
   */
  _guardedEntity(entityId) {
    if (!entityId) return false;
    const map = resolveEntities(this._hass, this._statusEntity);
    if ([map.slow_leak_detection, map.low_flow_detection].includes(entityId)) return true;
    return (
      [map.high_flow_bypass, map.high_flow_bypass_duration].includes(entityId) &&
      this._detectorPhase("high_flow") === "active"
    );
  }

  async _run(key, job) {
    if (this._busy.has(key)) return;
    this._busy.add(key);
    this._render();
    try {
      await job();
    } catch (err) {
      const t = translator(this._hass);
      fire(this, "hass-notification", { message: t("action_failed", { msg: err?.message || err?.code || err }) });
    } finally {
      this._busy.delete(key);
      this._render();
    }
  }

  _alarmActive() {
    const status = this._hass?.states?.[this._resolvedStatusId];
    return Boolean(status?.attributes?.aggregate_alarm_active);
  }

  /**
   * Ask the backend what this device may do. At most one request per
   * SESSION_MIN_INTERVAL_MS. Inside that window a request is deferred to its end
   * (state changes) or dropped (`defer: false`: connect, periodic poll), because a
   * fresh answer is already on its way. Only the answer to the newest request is
   * used (out-of-order answers are dropped).
   */
  _requestSession({ defer = true } = {}) {
    if (!this.isConnected) return;
    if (!this._hass || !this._config || typeof this._hass.callWS !== "function") return;
    if (!this._resolvedStatusId) return;
    const wait = this._sessionLastAt + SESSION_MIN_INTERVAL_MS - Date.now();
    if (wait > 0) {
      if (defer && !this._sessionTimer) {
        this._sessionTimer = setTimeout(() => {
          this._sessionTimer = undefined;
          this._requestSession();
        }, wait);
      }
      return;
    }
    this._sessionLastAt = Date.now();
    const seq = ++this._sessionSeq;
    (async () => {
      let next;
      try {
        const data = await this._hass.callWS({ type: INTERFACE.session, ...(await this._serviceData()) });
        next = { state: "ok", data: data && typeof data === "object" ? data : {} };
      } catch (err) {
        // Older backend (unknown_command) or any error: view only.
        next = { state: "error", code: err?.code || "unknown", data: {} };
      }
      if (seq !== this._sessionSeq || !this.isConnected) return;
      this._session = next;
      this._trackerSig = this._trackerState()?.state;
      this._signature = "";
      this._update();
    })();
  }

  /** Session view; anything but an explicit `paired: true` means view only. */
  get _perm() {
    const s = this._session;
    const d = s.state === "ok" ? s.data : {};
    const paired = d.paired === true;
    return {
      resolved: s.state !== "pending",
      paired,
      recipientId: paired ? d.recipient_id : undefined,
      // Display only (escaped where rendered): with a user pairing a laptop mutes
      // the paired recipient (e.g. the phone), so the button names it.
      recipientName: paired && typeof d.recipient_name === "string" && d.recipient_name.trim() ? d.recipient_name.trim() : undefined,
      // Home-only buttons need the session's `home` AND, when the tracker state is
      // visible here, a live `home`: a stale session never keeps them enabled.
      home: paired && d.home === true && (!this._trackerState() || this._trackerState().state === "home"),
      canAck: paired && d.can_global_ack === true,
      canReset: paired && d.can_external_reset === true,
      // Ending an alarm (disable detection, bypass start during High Flow) needs
      // the same as the external reset: a paired device at home right now.
      canClear: paired && d.home === true && (!this._trackerState() || this._trackerState().state === "home"),
      error: s.state === "error" ? s.code : undefined,
    };
  }

  _errorText(t, err) {
    const code = err?.code;
    if (ERROR_CODES.includes(code)) return t(`error.${code}`);
    return t("error.unknown", { msg: err?.message || code || String(err) });
  }

  /** Run one backend alarm command; the backend decides, the card reports. */
  async _command(key, command, payload, successKey, successVars = {}) {
    if (this._busy.has(key)) return;
    this._busy.add(key);
    this._render();
    const t = translator(this._hass);
    try {
      await this._hass.callWS({ type: command, ...(await this._serviceData(payload)) });
      fire(this, "hass-notification", { message: t(`success.${successKey}`, successVars) });
    } catch (err) {
      fire(this, "hass-notification", { message: this._errorText(t, err) });
    } finally {
      this._busy.delete(key);
      this._render();
      this._requestSession();
    }
  }

  _onClick(ev) {
    const target = ev.target.closest("[data-action]");
    if (!target || target.hasAttribute("disabled")) return;
    const { action } = target.dataset;
    const t = translator(this._hass);

    switch (action) {
      case "more-info":
        // Defense in depth: rendering already omits these links during an alarm.
        if (this._guardedEntity(target.dataset.entity)) return;
        fire(this, "hass-more-info", { entityId: target.dataset.entity });
        break;
      case "open-integration":
        navigate(INTERFACE.integrationPath);
        break;
      case "toggle-section": {
        const key = target.dataset.section;
        if (!(key in this._expanded)) return;
        this._expanded[key] = !this._expanded[key];
        this._render();
        break;
      }
      case "disable-detection": {
        // Only offered inside the alarm box while this detector's alarm is ACTIVE
        // and this device may end alarms (paired, at home). Re-checked here.
        const kind = target.dataset.kind;
        if (kind !== "slow_leak" && kind !== "low_flow") return;
        const map = resolveEntities(this._hass, this._statusEntity);
        const entityId = map[`${kind}_detection`];
        if (!entityId || this._hass.states[entityId]?.state !== "on") return;
        if (this._detectorPhase(kind) !== "active" || !this._perm.canClear) return;
        // Switching off ends this detector's ACTIVE alarm at once (backend:
        // apply_controls -> IDLE). Ask first.
        if (!window.confirm(t("confirm_disable", { kind: t(`detector.${kind}`) }))) return;
        this._run(`toggle:${entityId}`, () =>
          this._hass.callService("switch", "turn_off", { entity_id: entityId })
        );
        break;
      }
      case "bypass-start": {
        const minutes = num(target.dataset.minutes);
        // Starting the bypass ends an ACTIVE High Flow alarm at once: only a
        // device that may end alarms, and only after confirmation.
        if (this._detectorPhase("high_flow") === "active") {
          if (!this._perm.canClear) return;
          if (!window.confirm(t("confirm_bypass"))) return;
        }
        this._run("bypass", async () =>
          this._hass.callService(
            DOMAIN,
            "start_high_flow_bypass",
            await this._serviceData(minutes ? { duration_minutes: minutes } : {})
          )
        );
        break;
      }
      case "bypass-stop":
        this._run("bypass", async () =>
          this._hass.callService(DOMAIN, "cancel_high_flow_bypass", await this._serviceData())
        );
        break;
      case "reset-learning":
        if (!window.confirm(t("reset_learning_confirm"))) return;
        this._run("learning", async () =>
          this._hass.callService(DOMAIN, "reset_learning", await this._serviceData())
        );
        break;
      case "mute": {
        const eventId = target.dataset.event;
        if (!eventId) return;
        const name = this._perm.recipientName;
        this._command(`mute:${eventId}`, INTERFACE.mute, { event_id: eventId }, name ? "mute_for" : "mute", { name });
        break;
      }
      case "acknowledge": {
        const eventId = target.dataset.event;
        if (!eventId) return;
        this._command(`ack:${eventId}`, INTERFACE.acknowledge, { event_id: eventId }, "acknowledge");
        break;
      }
      case "external-reset": {
        // Schema of water_leak_detection/external_reset: all three fields required, strings.
        const payload = {
          event_id: target.dataset.event,
          source_id: target.dataset.source,
          source_generation: target.dataset.generation,
        };
        if (!payload.event_id || !payload.source_id || !payload.source_generation) return;
        // Ends the external alarm and its shutoff contribution: ask first.
        if (!window.confirm(t("external_reset_confirm", { name: target.dataset.name || payload.source_id }))) return;
        this._command(`reset:${payload.event_id}`, INTERFACE.externalReset, payload, "external_reset");
        break;
      }
      default:
        break;
    }
  }

  /* ------------------------------------------------------------ rendering */

  _render() {
    if (!this.shadowRoot) return;
    if (!this._config || !this._hass) {
      this.shadowRoot.innerHTML = "";
      return;
    }
    const t = translator(this._hass);
    const map = resolveEntities(this._hass, this._statusEntity);
    const status = this._state(map, "status");

    if (!status) {
      this.shadowRoot.innerHTML = `<style>${STYLES}</style>
        <ha-card><div class="empty">${esc(t("not_found"))}</div></ha-card>`;
      return;
    }

    const attrs = status.attributes || {};
    const statusUnavailable = status.state === "unavailable" || status.state === "unknown";
    const alarmEntity = this._state(map, "leak_alarm");
    const shutoffEntity = this._state(map, "shutoff_request");
    const alarm = Boolean(attrs.aggregate_alarm_active ?? alarmEntity?.state === "on");
    const shutoff = Boolean(attrs.aggregate_shutoff_request ?? shutoffEntity?.state === "on");
    const monitoring = this._monitoring(map, status);
    // A configured external sensor that cannot report "dry" makes "all quiet" untrue.
    const extOffline = externalOffline(this._hass, attrs);
    // Alarm state and operating state are independent: "no alarm" never hides a
    // blocked monitoring, and green is reserved for a confirmed active monitoring.
    // Monitoring reports active, but the source or the runtime store is impaired:
    // never green / "All quiet" (the maintainer's rule: show what interrupts monitoring).
    const impaired = !statusUnavailable && this._impaired(status);
    const tone = alarm
      ? "alarm"
      : statusUnavailable
        ? "neutral"
        : extOffline || impaired || monitoring.state === "blocked" || (monitoring.state === "missing" && status.state === "source_unavailable")
          ? "warn"
          : monitoring.state !== "active"
            ? "neutral"
            : String(status.state).endsWith("_monitoring")
              ? "watch"
              : "ok";

    const compactMonitoring = this._monitoringOk(monitoring, status, extOffline);
    const headerPill = !this._config.show_flow && compactMonitoring ? this._monitoringPill(t) : "";
    const header = this._renderHeader(t, status, tone, alarm, shutoff, monitoring, statusUnavailable, extOffline, headerPill);
    if (statusUnavailable) {
      this.shadowRoot.innerHTML = `<style>${STYLES}</style>
        <ha-card class="tone-${tone}">${header}
          <div class="banner banner-warn"><ha-icon icon="mdi:alert-circle-outline"></ha-icon><span>${esc(t("integration_unavailable"))}</span></div>
        </ha-card>`;
      return;
    }

    // One column below ~600 px card width; two columns above (container query).
    // The alarm box always comes right after the header, in both layouts.
    // Confirmed active monitoring without any source/store problem needs no own
    // row: a compact "Monitoring active" pill (in the flow row, else in the
    // header). Every other state keeps the full row with its details.
    const main = [
      header,
      alarm ? this._renderAlarm(t, map, status) : "",
      this._renderBanners(t, status, monitoring, extOffline),
      compactMonitoring ? "" : this._renderMonitoring(t, map, monitoring),
      this._config.show_flow ? this._renderFlow(t, map, compactMonitoring ? this._monitoringPill(t) : "") : "",
    ];
    const side = [
      this._config.show_detectors ? this._renderDetectors(t, map, status, monitoring) : "",
      this._config.show_bypass ? this._renderBypass(t, map, status) : "",
      this._config.show_external ? this._renderExternal(t, status) : "",
      this._config.show_learning ? this._renderLearning(t, map) : "",
    ].join("");

    this._paint(`<style>${STYLES}</style>
      <ha-card class="tone-${tone}"><div class="wlg" lang="${lang(this._hass)}">
        <div class="col col-main">${main.join("")}</div>
        ${side.trim() ? `<div class="col col-side">${side}</div>` : ""}
      </div></ha-card>`);
  }

  /** Replace the card content and keep keyboard focus on the same control. */
  _paint(html) {
    const focused = this.shadowRoot.activeElement?.dataset?.focus;
    this.shadowRoot.innerHTML = html;
    if (focused) {
      const again = [...this.shadowRoot.querySelectorAll("[data-focus]")].find((el) => el.dataset.focus === focused);
      if (again && !again.hasAttribute("disabled")) again.focus();
    }
  }

  /**
   * Summary row of a collapsible section: a real button with aria-expanded.
   * `extra` (e.g. the bypass Stop button) sits next to it, never inside it.
   */
  _summary(key, title, status, extra = "") {
    const open = Boolean(this._expanded[key]);
    return `
      <div class="sum">
        <button class="sum-btn" data-action="toggle-section" data-section="${esc(key)}" data-focus="section:${esc(key)}"
          aria-expanded="${open}" aria-controls="wlg-${esc(key)}">
          <span class="sum-text">
            <span class="sum-title">${esc(title)}</span>
            <span class="sum-status">${status}</span>
          </span>
          <ha-icon class="chev" icon="mdi:chevron-down" aria-hidden="true"></ha-icon>
        </button>
        ${extra}
      </div>`;
  }

  /** Operating state of the hydraulic monitoring, independent of any alarm. */
  _monitoring(map, status) {
    const entity = this._state(map, "hydraulic_monitoring_status");
    if (!entity) {
      // Older backend without the entity: never guess "active".
      return { state: "missing", entity: undefined, attrs: {}, fallbackBlocked: status.attributes?.source_available === false };
    }
    const state = MONITORING_STATES.includes(entity.state) ? entity.state : "unavailable";
    return { state, entity, attrs: entity.attributes || {} };
  }

  /**
   * The headline reports the alarm state only. The backend status reads
   * `source_unavailable` during an outage even while an alarm is ACTIVE, so the
   * alarm kind comes from the attributes and is never hidden by a source problem.
   */
  _headline(t, status, monitoring, statusUnavailable, alarm, extOffline = false) {
    const label = (key) => {
      const text = t(`status.${key}`);
      return text === `status.${key}` ? key : text;
    };
    if (statusUnavailable) return t("status.unavailable");
    const a = status.attributes || {};
    if (alarm) {
      // Only a real alarm kind may name the alarm. Otherwise (e.g. damaged runtime
      // store: alarm active, but status idle and no active_detector) never fall
      // back to a calm status label – show the generic alarm headline.
      const kind = [a.active_detector, status.state].find((k) => ALARM_KINDS.includes(k));
      return kind ? label(kind) : t("alarm");
    }
    // Monitoring active but source or runtime store impaired: say so, never "all quiet".
    if (monitoring.state === "active" && this._impaired(status)) return t("status.impaired");
    // A configured external sensor that is unreachable: no alarm, but not "all quiet".
    if (extOffline && status.state === "idle") return t("status.idle");
    if (status.state === "source_unavailable") {
      // With the monitoring entity, its own row explains the source problem.
      return monitoring.state === "missing" ? label("source_unavailable") : t("status.idle");
    }
    if (status.state === "idle") return monitoring.state === "active" ? t("status.all_quiet") : t("status.idle");
    return label(status.state);
  }

  /** Source or runtime store problem reported by the status sensor. */
  _impaired(status) {
    const a = status?.attributes || {};
    return Boolean(a.storage_recovery_required) || status?.state === "source_unavailable" || a.source_available === false;
  }

  /**
   * True only if the compact "Hydraulics active" pill may replace the monitoring
   * row: status sensor present and available, monitoring entity present and
   * `active`, no source/store problem and no unreachable external sensor.
   */
  _monitoringOk(monitoring, status, extOffline = false) {
    // isOffline() is also true for a missing entity (status or monitoring).
    return (
      !isOffline(status) &&
      !isOffline(monitoring.entity) &&
      monitoring.state === "active" &&
      !this._impaired(status) &&
      !extOffline
    );
  }

  /** Compact status pill that replaces the monitoring row while all is well (never interactive). */
  _monitoringPill(t) {
    return `<span class="pill pill-ok mon-ok" title="${esc(t("monitoring_hint.active"))}">${esc(t("monitoring_ok"))}</span>`;
  }

  _renderHeader(t, status, tone, alarm, shutoff, monitoring, statusUnavailable, extOffline, monitoringPill = "") {
    const title = this._config.title || deviceName(this._hass, status.entity_id) || t("title");
    const icon = {
      alarm: "mdi:water-alert",
      warn: "mdi:water-off",
      watch: "mdi:water-sync",
      neutral: "mdi:water-outline",
      ok: "mdi:water-check",
    }[tone];
    const flags = [
      alarm ? `<span class="flag flag-alarm"><ha-icon icon="mdi:pipe-leak"></ha-icon>${esc(t("alarm"))}</span>` : "",
      shutoff ? `<span class="flag flag-shutoff"><ha-icon icon="mdi:valve-closed"></ha-icon>${esc(t("shutoff"))}</span>` : "",
      monitoringPill,
    ].filter(Boolean);
    return `
      <header class="head${this._config.show_background ? " has-motif" : ""}">
        ${this._config.show_background ? BACKGROUND_MOTIF : ""}
        <button class="orb" data-action="more-info" data-entity="${esc(status.entity_id)}" data-focus="orb" aria-label="${esc(title)}">
          <ha-icon icon="${icon}"></ha-icon>
        </button>
        <div class="head-text">
          <div class="eyebrow">${esc(title)}</div>
          <div class="headline">${esc(this._headline(t, status, monitoring, statusUnavailable, alarm, extOffline))}</div>
        </div>
        ${flags.length ? `<div class="flags">${flags.join("")}</div>` : ""}
      </header>`;
  }

  _renderBanners(t, status, monitoring, extOffline) {
    const a = status.attributes || {};
    const out = [];
    if (a.storage_recovery_required) {
      out.push(`<div class="banner banner-alarm"><ha-icon icon="mdi:database-alert"></ha-icon><span>${esc(t("storage_recovery"))}</span></div>`);
    }
    // The external section shows which sensor; without it, explain the yellow tone here.
    if (extOffline && !this._config.show_external) {
      out.push(`<div class="banner banner-warn"><ha-icon icon="mdi:leak-off"></ha-icon><span>${esc(t("external_offline_banner"))}</span></div>`);
    }
    // With the monitoring entity, its own row explains source problems in detail.
    if (monitoring.state === "missing" && (status.state === "source_unavailable" || a.source_available === false)) {
      out.push(`<div class="banner banner-warn"><ha-icon icon="mdi:access-point-network-off"></ha-icon><span>${esc(t("source_unavailable_banner"))}</span></div>`);
    }
    return out.join("");
  }

  _renderMonitoring(t, map, monitoring) {
    const state = monitoring.state;
    const pillClass = { active: "ok", waiting_for_measurement: "monitoring", blocked: "warn" }[state] || "unknown";
    const a = monitoring.attrs;
    const reasonText = (code) => {
      if (!code) return "–";
      const text = t(`reason.${code}`);
      return text === `reason.${code}` ? code : text;
    };
    let details = "";
    if (state === "blocked" || state === "waiting_for_measurement") {
      const rows = [
        [t("detail.reason"), `${esc(reasonText(a.reason))}${a.reason ? ` <code>${esc(a.reason)}</code>` : ""}`],
        [t("detail.source"), a.source_entity_id
          ? `<button class="link-plain linkish" data-action="more-info" data-entity="${esc(a.source_entity_id)}">${esc(a.source_entity_id)}</button>`
          : "–"],
      ];
      if (a.mqtt_provenance_status && a.mqtt_provenance_status !== "not_mqtt" && a.mqtt_provenance_status !== a.reason) {
        rows.push([t("detail.provenance"), `${esc(reasonText(a.mqtt_provenance_status))} <code>${esc(a.mqtt_provenance_status)}</code>`]);
      }
      rows.push([t("detail.last_measurement"), a.last_valid_measurement ? esc(formatClock(this._hass, a.last_valid_measurement)) : "–"]);
      if (num(a.observation_age_seconds) != null) rows.push([t("detail.age"), esc(formatSeconds(a.observation_age_seconds))]);
      details = `
        <details class="details" ${state === "blocked" ? "open" : ""}>
          <summary>${esc(t("monitoring_details"))}</summary>
          <dl>${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>
        </details>`;
    }
    return `
      <section class="monitor monitor-${pillClass}">
        <div class="row">
          <div class="row-text">
            ${monitoring.entity
              ? `<button class="row-title link-plain" data-action="more-info" data-entity="${esc(monitoring.entity.entity_id)}">${esc(t("monitoring.label"))}</button>`
              : `<div class="row-title">${esc(t("monitoring.label"))}</div>`}
            <div class="row-sub">${esc(t(`monitoring_hint.${state}`))}</div>
          </div>
          <span class="pill pill-${pillClass}">${esc(t(`monitoring.${state}`))}</span>
        </div>
        ${details}
      </section>`;
  }

  /** One row per active physical event: hydraulic detectors and external sources. */
  _activeEvents(status) {
    const a = status.attributes || {};
    const events = [];
    const hydraulic = a.hydraulic_detectors || {};
    for (const kind of HYDRAULIC_KINDS) {
      const d = hydraulic[kind];
      if (d && d.phase === "active" && d.event_id) {
        events.push({
          kind,
          event_id: d.event_id,
          since: d.active_since || d.started_at,
          seconds: d.event_duration_seconds,
          external: false,
        });
      }
    }
    for (const src of a.external_sources || []) {
      if (src.phase === "ACTIVE" && src.event_id && !src.identity_conflict) {
        events.push({
          kind: "external_leak",
          name: src.source_name,
          event_id: src.event_id,
          since: src.started_at,
          external: true,
          source_id: src.source_id,
          source_generation: src.source_generation,
        });
      }
    }
    return events;
  }

  /** How this event ends, specific to its kind (mirrors engine.apply_controls). */
  _endHint(t, ev) {
    if (ev.external || ev.kind === "external_leak") return t("how_external_reset");
    if (ev.kind === "slow_leak" || ev.kind === "low_flow") return t("ends_slow_low");
    if (ev.kind === "high_flow") return t("ends_high");
    if (ev.kind === "burst_leak") return t("ends_burst");
    return t("hydraulic_clears_itself");
  }

  _renderAlarm(t, map, status) {
    const a = status.attributes || {};
    const ackStates = a.notification_events || {};
    const perm = this._perm;
    const volume = num(this._state(map, "active_event_volume")?.state);
    const durationAttrs = this._state(map, "active_event_duration")?.attributes || {};
    const events = this._activeEvents(status);
    if (events.length === 0 && a.active_event_id) {
      events.push({ kind: a.active_detector || "external_leak", event_id: a.active_event_id, external: false });
    }

    const rows = events
      .map((ev) => {
        const ack = ackStates[ev.event_id] || {};
        const acked = Boolean(ack.globally_acknowledged);
        const mutedList = Array.isArray(ack.muted_recipients) ? ack.muted_recipients : [];
        const mutedHere = perm.paired && perm.recipientId != null && mutedList.includes(perm.recipientId);
        const isDisplay = ev.event_id === a.active_event_id;
        const duration = isDisplay
          ? durationAttrs[`duration_human_${lang(this._hass)}`] || durationAttrs.duration_human
          : ev.seconds != null
            ? formatSeconds(ev.seconds)
            : "";
        const label = ev.external ? `${t("detector.external_leak")} · ${ev.name || ev.source_id}` : t(`detector.${ev.kind}`);
        const ackKey = `ack:${ev.event_id}`;
        const muteKey = `mute:${ev.event_id}`;
        const resetKey = `reset:${ev.event_id}`;

        // Only what this device may do now (session); the backend re-checks every action.
        const buttons = [];
        const reasons = [];
        const who = perm.recipientName;
        if (perm.paired && !acked) {
          if (mutedHere) {
            buttons.push(`<span class="pill pill-off"><ha-icon class="mini" icon="mdi:bell-off"></ha-icon>${esc(who ? t("muted_for", { name: who }) : t("muted_here"))}</span>`);
          } else {
            buttons.push(`
              <button class="btn btn-ghost" data-action="mute" data-event="${esc(ev.event_id)}"
                ${this._busy.has(muteKey) ? "disabled" : ""} title="${esc(who ? t("mute_hint_for", { name: who }) : t("mute_hint"))}">
                <ha-icon icon="mdi:bell-off-outline"></ha-icon>${esc(who ? t("mute_for", { name: who }) : t("mute"))}
              </button>`);
          }
        }
        if (perm.canAck && !acked) {
          const away = !perm.home;
          buttons.push(`
            <button class="btn btn-primary" data-action="acknowledge" data-event="${esc(ev.event_id)}"
              ${away || this._busy.has(ackKey) ? "disabled" : ""} title="${esc(away ? t("requires_home") : t("acknowledge_hint"))}">
              <ha-icon icon="${away ? "mdi:home-lock" : "mdi:bell-check"}"></ha-icon>${esc(t("acknowledge"))}
            </button>`);
          if (away) reasons.push(t("requires_home"));
        }
        // Alarm-ending hydraulic actions: only a paired device, enabled only at home.
        // Unpaired devices get none (the session note below explains why).
        const clearAway = !perm.canClear;
        if ((ev.kind === "slow_leak" || ev.kind === "low_flow") && !ev.external && perm.paired) {
          const switchId = map[`${ev.kind}_detection`];
          if (switchId && this._hass.states[switchId]?.state === "on") {
            const busyKey = `toggle:${switchId}`;
            buttons.push(`
              <button class="btn btn-danger-ghost" data-action="disable-detection" data-kind="${esc(ev.kind)}"
                data-focus="disable:${esc(ev.kind)}"
                ${clearAway || this._busy.has(busyKey) ? "disabled" : ""}
                title="${esc(clearAway ? t("requires_home") : t("disable_detection_hint"))}">
                <ha-icon icon="${clearAway ? "mdi:home-lock" : "mdi:power"}"></ha-icon>${esc(t("disable_detection"))}
              </button>`);
            if (clearAway && !reasons.includes(t("requires_home"))) reasons.push(t("requires_home"));
          }
        }
        if (ev.kind === "high_flow" && !ev.external && perm.paired && this._config.show_bypass !== false && map.high_flow_bypass) {
          buttons.push(`
            <button class="btn btn-danger-ghost" data-action="bypass-start" data-focus="bypass-alarm"
              ${clearAway || this._busy.has("bypass") ? "disabled" : ""}
              title="${esc(clearAway ? t("requires_home") : t("bypass_note"))}">
              <ha-icon icon="${clearAway ? "mdi:home-lock" : "mdi:timer-play-outline"}"></ha-icon>${esc(t("bypass_start_alarm"))}
            </button>`);
          if (clearAway && !reasons.includes(t("requires_home"))) reasons.push(t("requires_home"));
        }
        if (ev.external && ev.source_id && ev.source_generation != null && perm.canReset) {
          const away = !perm.home;
          buttons.push(`
            <button class="btn btn-danger" data-action="external-reset" data-event="${esc(ev.event_id)}"
              data-source="${esc(ev.source_id)}" data-generation="${esc(ev.source_generation)}" data-name="${esc(ev.name || ev.source_id)}"
              ${away || this._busy.has(resetKey) ? "disabled" : ""} title="${esc(away ? t("requires_home") : t("external_reset"))}">
              <ha-icon icon="${away ? "mdi:home-lock" : "mdi:broom"}"></ha-icon>${esc(t("external_reset"))}
            </button>`);
          if (away && !reasons.includes(t("requires_home"))) reasons.push(t("requires_home"));
        }

        return `
          <div class="event" data-event-id="${esc(ev.event_id)}">
            <div class="event-top">
              <div>
                <div class="event-kind">${esc(label)}</div>
                <div class="event-meta">
                  ${ev.since ? `${esc(t("since"))} ${esc(formatClock(this._hass, ev.since))}` : ""}
                  ${duration ? ` · ${esc(t("duration"))} ${esc(duration)}` : ""}
                  ${isDisplay && volume != null && !ev.external ? ` · ${esc(t("volume"))} ${esc(formatNumber(this._hass, volume, 1))} L` : ""}
                </div>
              </div>
              <span class="pill ${acked ? "pill-ok" : "pill-alarm"}"
                ${acked && ack.globally_acknowledged_by ? `title="${esc(t("acknowledged_by", { who: ack.globally_acknowledged_by }))}"` : ""}>
                ${esc(acked ? t("acknowledged") : t("not_acknowledged"))}
              </span>
            </div>
            ${mutedList.length && !acked ? `<div class="note">${esc(t("muted_count", { n: mutedList.length }))}</div>` : ""}
            <ul class="how"><li>${esc(this._endHint(t, ev))}</li></ul>
            ${buttons.length ? `<div class="event-actions">${buttons.join("")}</div>` : ""}
            ${reasons.map((r) => `<div class="note reason">${esc(r)}</div>`).join("")}
          </div>`;
      })
      .join("");

    const notes = [];
    if (perm.resolved && !perm.paired) {
      notes.push(t("session_unpaired"));
      if (perm.error === "unknown_command") notes.push(t("session_no_backend"));
      else if (perm.error === "instance_not_found") notes.push(t("error.instance_not_found"));
      else if (perm.error) notes.push(t("session_failed"));
      else if (this._hass.user?.is_admin) notes.push(t("session_pair_hint"));
    }
    const anyOpen = events.some((ev) => !ackStates[ev.event_id]?.globally_acknowledged);
    const adminLink = this._hass.user?.is_admin && anyOpen
      ? `<div class="event-actions"><button class="btn btn-ghost" data-action="open-integration">
           <ha-icon icon="mdi:cog-outline"></ha-icon>${esc(t("open_integration"))}</button></div>`
      : "";
    return `<section class="alarm">${rows}
      ${notes.length ? `<div class="session-note">${notes.map((n) => `<div class="note">${esc(n)}</div>`).join("")}</div>` : ""}
      ${adminLink}<div class="note subtle">${esc(t("acknowledge_hint"))}</div></section>`;
  }

  _renderFlow(t, map, monitoringPill = "") {
    const flowState = this._state(map, "current_flow");
    const flow = flowState && flowState.state !== "unavailable" ? num(flowState.state) : null;
    const high = num(this._state(map, "effective_high_threshold")?.state);
    const burst = num(this._state(map, "effective_burst_threshold")?.state);
    const max = Math.max((burst || 3500) * 1.15, flow || 0, 1);
    // Log scale: a 3 L/h trickle and a 3,500 L/h burst both stay readable.
    const pos = (v) => Math.min(100, Math.max(0, (Math.log10(1 + v) / Math.log10(1 + max)) * 100));
    const level = flow == null ? "none" : burst && flow >= burst ? "alarm" : high && flow >= high ? "warn" : flow > 0 ? "flow" : "none";

    return `
      <section class="block flow">
        <div class="block-head">
          <span class="flow-label">${esc(t("flow"))}${monitoringPill}</span>
          <button class="link" data-action="more-info" data-entity="${esc(map.current_flow || "")}" data-focus="flow" ${map.current_flow ? "" : "disabled"}>
            ${flow == null ? esc(t("flow_unavailable")) : `<b class="big">${esc(formatNumber(this._hass, flow, flow < 10 ? 1 : 0))}</b> L/h`}
          </button>
        </div>
        <div class="meter" role="img" aria-label="${esc(t("flow"))}">
          <div class="meter-fill level-${level}" style="width:${flow == null ? 0 : pos(flow).toFixed(2)}%"></div>
          ${high ? `<div class="tick" style="left:${pos(high).toFixed(2)}%"></div>` : ""}
          ${burst ? `<div class="tick tick-burst" style="left:${pos(burst).toFixed(2)}%"></div>` : ""}
        </div>
        <div class="legend">
          ${high ? `<span><i class="key"></i>${esc(t("high"))} ${esc(formatNumber(this._hass, high))} L/h</span>` : ""}
          ${burst ? `<span><i class="key key-burst"></i>${esc(t("burst"))} ${esc(formatNumber(this._hass, burst))} L/h</span>` : ""}
        </div>
      </section>`;
  }

  /**
   * Compact 2×2 status grid. Status only: no switches and no links – disabling
   * Slow Leak/Low Flow exists only as a confirmed action in the alarm box.
   */
  _renderDetectors(t, map, status, monitoring) {
    const a = status.attributes || {};
    const phases = a.detectors || {};
    const bypass = this._state(map, "high_flow_bypass")?.state === "on";
    const switches = { slow_leak: map.slow_leak_detection, low_flow: map.low_flow_detection };

    const tiles = HYDRAULIC_KINDS.map((kind) => {
      const switchId = switches[kind];
      const enabled = switchId ? this._hass.states[switchId]?.state === "on" : true;
      let phase = phases[kind] || "idle";
      let pillClass = null;
      if (!enabled) phase = "off";
      else if (kind === "high_flow" && bypass && phase !== "active") phase = "bypass";
      // Without an evaluated measurement no detector is "ready"; ACTIVE alarms stay visible.
      // A damaged runtime store makes the detector state unreliable: never reassure.
      let pausedHint = "paused_hint";
      if (phase === "idle" || phase === "monitoring") {
        if (a.storage_recovery_required) {
          phase = "paused";
          pausedHint = "storage_paused_hint";
        } else if (monitoring.state === "missing") {
          if (monitoring.fallbackBlocked) phase = "paused";
          else pillClass = "unknown";
        } else if (monitoring.state !== "active") {
          phase = "paused";
        }
      }
      const tip = [t(`detector_hint.${kind}`), phase === "paused" ? t(pausedHint) : ""].filter(Boolean).join(" – ");
      return `
        <div class="tile tile-${esc(pillClass || phase)}" title="${esc(tip)}">
          <span class="tile-name">${esc(t(`detector.${kind}`))}</span>
          <span class="pill pill-${esc(pillClass || phase)}">${esc(t(`phase.${phase}`))}</span>
        </div>`;
    }).join("");

    return `<section class="block detectors"><div class="block-head"><span>${esc(t("detectors"))}</span></div>
      <div class="tiles">${tiles}</div></section>`;
  }

  _renderBypass(t, map, status) {
    const sw = this._state(map, "high_flow_bypass");
    if (!sw) return "";
    const active = sw.state === "on";
    // Starting the bypass during an ACTIVE High Flow alarm ends that alarm: only
    // a paired device at home may do that from the card (and only after confirmation).
    const highAlarm = status?.attributes?.detectors?.high_flow === "active";
    const perm = this._perm;
    const startBlocked = highAlarm && !perm.canClear;
    const remaining = num(this._state(map, "high_flow_bypass_remaining")?.state) ?? num(sw.attributes?.remaining_seconds) ?? 0;
    const finishes = sw.attributes?.finishes_at;
    const defaultMinutes = num(this._state(map, "high_flow_bypass_duration")?.state);
    const busy = this._busy.has("bypass");
    const presets = (this._config.bypass_presets || [])
      .map(num)
      .filter((m) => m && m >= 1 && m <= 1440);

    const statusText = active
      ? `<span class="on">${esc(t("bypass_on", { left: formatSeconds(remaining) }))}${finishes ? ` (${esc(t("bypass_until", { time: formatClock(this._hass, finishes) }))})` : ""}</span>`
      : esc(t("bypass_off"));
    const stop = active
      ? `<button class="btn btn-primary btn-small" data-action="bypass-stop" data-focus="bypass-stop" ${busy ? "disabled" : ""}>
           <ha-icon icon="mdi:stop-circle-outline"></ha-icon>${esc(t("bypass_stop"))}</button>`
      : "";
    const open = this._expanded.bypass;
    const disabled = busy || startBlocked ? "disabled" : "";
    const reason = startBlocked
      ? `<div class="note reason">${esc(perm.paired ? t("requires_home") : t("session_unpaired"))}</div>`
      : "";
    const body = open
      ? `<div class="sec-body" id="wlg-bypass">
          ${active ? "" : `<div class="actions" role="group" aria-label="${esc(t("bypass_presets"))}">
            ${presets.map((m) => `<button class="btn btn-ghost" data-action="bypass-start" data-minutes="${m}" data-focus="preset:${m}" ${disabled}>${m % 60 === 0 ? `${m / 60} h` : `${m} min`}</button>`).join("")}
            <button class="btn btn-ghost" data-action="bypass-start" data-focus="preset:default" ${disabled}>${esc(t("bypass_default"))}${defaultMinutes ? ` · ${esc(formatSeconds(defaultMinutes * 60))}` : ""}</button>
          </div>${reason}`}
          <div class="note subtle">${esc(t("bypass_note"))}</div>
        </div>`
      : `<div id="wlg-bypass" hidden></div>`;

    return `
      <section class="block coll${active ? " bypass-on" : ""}">
        ${this._summary("bypass", t("bypass"), statusText, stop)}
        ${body}
      </section>`;
  }
  _renderExternal(t, status) {
    const sources = (status.attributes?.external_sources || []).filter((s) => !s.tombstone);
    if (sources.length === 0) return "";
    const rows = sources
      .map((s) => {
        const offline = isOffline(this._hass.states[s.source_entity]);
        let phaseClass = s.identity_conflict ? "warn" : s.phase === "ACTIVE" ? "active" : s.phase === "ARMED" ? "idle" : "monitoring";
        let label = s.identity_conflict ? t("external_conflict") : t(`external_phase.${s.phase}`);
        // A dry reading needs a reachable sensor; an ACTIVE leak always stays visible.
        if (offline && s.phase !== "ACTIVE" && !s.identity_conflict) {
          phaseClass = "unknown";
          label = t("sensor_unavailable");
        }
        return `
          <div class="row">
            <div class="row-text">
              <button class="row-title link-plain" data-action="more-info" data-entity="${esc(s.source_entity)}">${esc(s.source_name || s.source_entity)}</button>
              <div class="row-sub">${s.contributes_to_shutoff ? `<ha-icon class="mini" icon="mdi:valve"></ha-icon>${esc(t("contributes_shutoff"))}` : esc(s.source_entity)}</div>
            </div>
            <span class="pill pill-${phaseClass}">${esc(label)}</span>
          </div>`;
      })
      .join("");
    return `<section class="block"><div class="block-head"><span>${esc(t("external"))}</span></div>${rows}</section>`;
  }

  _renderLearning(t, map) {
    const conf = this._state(map, "learning_confidence");
    if (!conf) return "";
    const cov = this._state(map, "learning_coverage");
    const learned = this._state(map, "learned_maximum_flow");
    const longTerm = this._state(map, "long_term_normal_maximum");
    const days = num(cov?.state) ?? 0;
    const windowDays = num(cov?.attributes?.window_days) ?? num(conf.attributes?.window_days) ?? 30;
    const pct = Math.min(100, Math.max(0, (days / Math.max(1, windowDays)) * 100));
    const samples = num(conf.attributes?.sample_count);
    const learnedVal = num(learned?.state);
    const longVal = num(longTerm?.state);
    const isAdmin = Boolean(this._hass.user?.is_admin);
    // Only a reliable model may look reassuring (green); everything else is neutral.
    const known = ["insufficient", "learning", "reliable"].includes(conf.state);
    const tone = { reliable: "ok", learning: "monitoring", insufficient: "off" }[conf.state] || "unknown";
    const label = t(`confidence.${known ? conf.state : "unknown"}`);
    const fmt = (v) => (v == null ? "–" : esc(formatNumber(this._hass, v)));
    const stat = (entity, key, value, unit, longKey) => {
      const inner = `<span class="stat-label">${esc(t(key))}</span><b>${value}</b><small>${esc(unit)}</small>`;
      const tip = esc(t(longKey || key));
      return entity
        ? `<button class="stat" data-action="more-info" data-entity="${esc(entity)}" data-focus="stat:${esc(key)}" title="${tip}" aria-label="${tip}: ${value} ${esc(unit)}">${inner}</button>`
        : `<div class="stat" title="${tip}">${inner}</div>`;
    };

    const status = `<span class="pill pill-${tone}">${esc(label)}</span><span class="sum-cov">${esc(t("coverage_short", { n: days, w: windowDays }))}</span>`;
    const open = this._expanded.learning;
    const body = open
      ? `<div class="sec-body" id="wlg-learning">
          <div class="progress"><div style="width:${pct.toFixed(1)}%"></div></div>
          <div class="stats">
            ${stat(cov?.entity_id || conf.entity_id, "coverage", `${esc(days)}/${esc(windowDays)}`, t("days_unit"))}
            ${stat(learned?.entity_id || conf.entity_id, "learned_max", fmt(learnedVal), "L/h")}
            ${stat(longTerm?.entity_id, "long_term_max", fmt(longVal), "L/h", "long_term_max_long")}
            ${stat(undefined, "samples", samples == null ? "–" : esc(formatNumber(this._hass, samples)), "")}
          </div>
          ${isAdmin ? `<div class="actions end">
            <button class="btn btn-quiet" data-action="reset-learning" data-focus="reset-learning" ${this._busy.has("learning") ? "disabled" : ""}>
              <ha-icon icon="mdi:restore"></ha-icon>${esc(t("reset_learning"))}
            </button></div>` : ""}
        </div>`
      : `<div id="wlg-learning" hidden></div>`;

    return `
      <section class="block coll learning">
        ${this._summary("learning", t("learning"), status)}
        ${body}
      </section>`;
  }
}

/* --------------------------------------------------------- background motif */

/**
 * Decorative shield filled with moving water, drawn behind the header.
 * Purely visual (aria-hidden, no pointer events); it takes the status tone.
 */
const BACKGROUND_MOTIF = `
  <svg class="motif" viewBox="0 0 200 240" aria-hidden="true" focusable="false">
    <defs>
      <clipPath id="wlg-shield">
        <path d="M100 6 L186 38 V110 C186 168 150 210 100 234 C50 210 14 168 14 110 V38 Z"/>
      </clipPath>
    </defs>
    <path class="shield-fill" d="M100 6 L186 38 V110 C186 168 150 210 100 234 C50 210 14 168 14 110 V38 Z"/>
    <g clip-path="url(#wlg-shield)">
      <g class="slosh">
      <path class="wave wave-back" d="M-200 96 Q-175 85 -150 96 T-100 96 T-50 96 T0 96 T50 96 T100 96 T150 96 T200 96 T250 96 T300 96 T350 96 T400 96 V260 H-200 Z"/>
      <path class="wave wave-front" d="M-200 106 Q-175 117 -150 106 T-100 106 T-50 106 T0 106 T50 106 T100 106 T150 106 T200 106 T250 106 T300 106 T350 106 T400 106 V260 H-200 Z"/>
      </g>
      <circle class="drop" cx="164" cy="62" r="4.5" style="--dx:-14px;--dy:-26px"/>
      <circle class="drop" cx="174" cy="74" r="3.5" style="--dx:-26px;--dy:-14px"/>
      <circle class="drop" cx="156" cy="52" r="3" style="--dx:-6px;--dy:-34px"/>
      <circle class="drop" cx="170" cy="90" r="2.5" style="--dx:-34px;--dy:-6px"/>
      <circle class="drop" cx="178" cy="58" r="2.5" style="--dx:-18px;--dy:-32px"/>
    </g>
    <path class="shield-line" d="M100 6 L186 38 V110 C186 168 150 210 100 234 C50 210 14 168 14 110 V38 Z"/>
    <path class="shield-line inner" d="M100 22 L172 49 V110 C172 160 142 196 100 217 C58 196 28 160 28 110 V49 Z"/>
  </svg>`;

/* ------------------------------------------------------------------- styles */

const STYLES = `
  :host {
    --wlg-alarm: var(--error-color, #db4437);
    --wlg-warn: var(--warning-color, #ffa600);
    --wlg-ok: var(--success-color, #43a047);
    --wlg-watch: var(--info-color, #039be5);
    --wlg-water: var(--state-sensor-volume_flow_rate-color, var(--info-color, #039be5));
    --wlg-muted: var(--secondary-text-color, #727272);
    --wlg-line: var(--divider-color, rgba(127,127,127,.2));
    --wlg-soft: color-mix(in srgb, var(--primary-text-color, #212121) 6%, transparent);
    display: block;
    /* container-type: inline-size makes the card's width independent of its
       content; in a container that sizes to content it would collapse to 0. */
    min-width: 280px;
  }
  /* The card measures itself: two columns once the CARD (not the viewport) is wide enough. */
  ha-card { overflow: hidden; container-type: inline-size; container-name: wlg; }
  .wlg { padding-bottom: 4px; }
  .col { min-width: 0; }
  @container wlg (min-width: 600px) {
    .wlg { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); align-items: start; }
    .col-side { border-left: 1px solid var(--wlg-line); align-self: stretch; }
    .col-side > .block:first-child { border-top: 0; }
    .col-main > .block:last-child { padding-bottom: 6px; }
  }

  /* Shield + water motif: a small badge at the right edge of the header. Text
     never runs under it (padding-right reserves its width). */
  .head { position: relative; isolation: isolate; overflow: hidden; }
  .head.has-motif { min-height: 76px; box-sizing: border-box; align-content: center; padding-right: 72px; }
  .head > :not(.motif) { position: relative; z-index: 1; }
  .motif {
    position: absolute; z-index: 0; top: 50%; right: 12px; width: 50px; height: 60px; margin-top: -30px;
    pointer-events: none; color: var(--tone);
  }
  .motif .shield-fill { fill: currentColor; opacity: .07; }
  .motif .shield-line { fill: none; stroke: currentColor; stroke-width: 4; opacity: .24; }
  .motif .shield-line.inner { stroke-width: 2; opacity: .14; }
  .motif .wave { fill: var(--wlg-water); }
  .motif .wave-back { opacity: .14; animation: wlg-drift 9s linear infinite; }
  .motif .wave-front { opacity: .24; animation: wlg-drift 6s linear infinite reverse; }
  .motif .drop { fill: var(--wlg-alarm); opacity: 0; transform-box: fill-box; transform-origin: center; }
  .tone-alarm .motif .wave { fill: var(--wlg-alarm); }
  /* No reassuring blue water while monitoring is not confirmed active. */
  .tone-neutral .motif .wave { fill: var(--wlg-muted); }
  .tone-warn .motif .wave { fill: var(--wlg-warn); }
  .tone-alarm .motif .shield-line { opacity: .38; }
  /* Alarm: the water runs to the right wall, hits it with spray, and falls back. */
  .tone-alarm .motif .slosh {
    transform-box: view-box; transform-origin: 100px 150px; animation: wlg-slosh 1.5s infinite;
  }
  .tone-alarm .motif .wave-back { animation-duration: 1.5s; }
  .tone-alarm .motif .wave-front { animation-duration: .75s; animation-direction: normal; }
  .tone-alarm .motif .drop { animation: wlg-splash 1.5s infinite; }
  @keyframes wlg-drift { to { transform: translateX(100px); } }
  @keyframes wlg-slosh {
    0% { transform: rotate(7deg); animation-timing-function: cubic-bezier(.55, 0, .9, .5); }
    42% { transform: rotate(-19deg); animation-timing-function: ease-out; }
    52% { transform: rotate(-13deg); animation-timing-function: ease-in-out; }
    60% { transform: rotate(-16deg); animation-timing-function: cubic-bezier(.3, .1, .4, 1); }
    100% { transform: rotate(7deg); }
  }
  @keyframes wlg-splash {
    0%, 38% { opacity: 0; transform: translate(0, 0) scale(.4); }
    44% { opacity: .45; transform: translate(0, 0) scale(1); }
    70% { opacity: .3; }
    80%, 100% { opacity: 0; transform: translate(var(--dx), var(--dy)) scale(.6); }
  }
  @media (prefers-reduced-motion: reduce) {
    .motif .wave, .tone-alarm .motif .slosh, .tone-alarm .motif .drop { animation: none; }
    .chev, .meter-fill { transition: none; }
  }

  ha-card.tone-alarm { box-shadow: inset 0 3px 0 var(--wlg-alarm), var(--ha-card-box-shadow, none); }
  ha-card.tone-warn { box-shadow: inset 0 3px 0 var(--wlg-warn), var(--ha-card-box-shadow, none); }
  ha-icon { --mdc-icon-size: 18px; display: inline-flex; }
  button { font: inherit; color: inherit; }
  .empty { padding: 16px; color: var(--wlg-muted); }

  .head { display: flex; align-items: center; gap: 6px 12px; padding: 10px 16px 8px; flex-wrap: wrap; }
  .orb {
    width: 44px; height: 44px; border-radius: 50%; border: 0; cursor: pointer; flex: none;
    display: grid; place-items: center; --mdc-icon-size: 22px;
    background: color-mix(in srgb, var(--tone) 18%, transparent); color: var(--tone);
  }
  .tone-ok { --tone: var(--wlg-ok); }
  .tone-watch { --tone: var(--wlg-watch); }
  .tone-warn { --tone: var(--wlg-warn); }
  .tone-alarm { --tone: var(--wlg-alarm); }
  .tone-neutral { --tone: var(--wlg-muted); }
  .tone-alarm .orb { animation: pulse 1.6s ease-in-out infinite; }
  @keyframes pulse { 50% { box-shadow: 0 0 0 8px color-mix(in srgb, var(--wlg-alarm) 0%, transparent), 0 0 0 4px color-mix(in srgb, var(--wlg-alarm) 25%, transparent); } }
  @media (prefers-reduced-motion: reduce) { .tone-alarm .orb { animation: none; } }
  .head-text { flex: 1; min-width: 0; }
  .eyebrow { font-size: 12px; color: var(--wlg-muted); letter-spacing: .02em; overflow-wrap: anywhere; }
  .headline { font-size: 19px; font-weight: 500; line-height: 1.2; overflow-wrap: anywhere; }
  .flags { display: flex; gap: 6px; flex-wrap: wrap; flex-basis: 100%; }
  .flags:empty { display: none; }
  .flag {
    display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px 3px 8px; border-radius: 999px;
    font-size: 12px; font-weight: 500; --mdc-icon-size: 16px;
  }
  .flag-alarm { background: var(--wlg-alarm); color: var(--text-primary-color, #fff); }
  .flag-shutoff { background: color-mix(in srgb, var(--wlg-alarm) 16%, transparent); color: var(--wlg-alarm); }

  .banner {
    display: flex; gap: 10px; align-items: flex-start; margin: 0 16px 10px; padding: 8px 12px;
    border-radius: 10px; font-size: 13px; line-height: 1.4;
  }
  .banner ha-icon { flex: none; margin-top: 1px; }
  .banner-alarm { background: color-mix(in srgb, var(--wlg-alarm) 14%, transparent); color: var(--primary-text-color); }
  .banner-alarm ha-icon { color: var(--wlg-alarm); }
  .banner-warn { background: color-mix(in srgb, var(--wlg-warn) 16%, transparent); color: var(--primary-text-color); }
  .banner-warn ha-icon { color: var(--wlg-warn); }

  .alarm {
    margin: 0 16px 10px; padding: 12px; border-radius: 12px;
    background: color-mix(in srgb, var(--wlg-alarm) 9%, transparent);
    border: 1px solid color-mix(in srgb, var(--wlg-alarm) 30%, transparent);
  }
  .event + .event { margin-top: 12px; padding-top: 12px; border-top: 1px solid color-mix(in srgb, var(--wlg-alarm) 22%, transparent); }
  .event-top { display: flex; justify-content: space-between; gap: 8px; align-items: flex-start; flex-wrap: wrap; }
  .event-kind { font-weight: 500; font-size: 15px; overflow-wrap: anywhere; }
  .event-meta { font-size: 13px; color: var(--wlg-muted); margin-top: 2px; }
  .event-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 10px; }

  .block { padding: 8px 16px 2px; border-top: 1px solid var(--wlg-line); }
  .block-head {
    display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap;
    font-size: 13px; font-weight: 500; color: var(--wlg-muted); margin-bottom: 4px;
  }
  .big { font-size: 22px; font-weight: 500; color: var(--primary-text-color); font-variant-numeric: tabular-nums; }
  .muted { color: var(--wlg-muted); font-weight: 400; }

  .flow .block-head { margin-bottom: 0; align-items: center; }
  .flow-label { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .mon-ok { padding: 1px 8px; font-size: 11px; }
  .flags .mon-ok { font-size: 12px; }
  .big { line-height: 1.15; }
  .meter { position: relative; height: 8px; border-radius: 999px; background: var(--wlg-soft); margin: 4px 0 4px; }
  .meter-fill { height: 100%; border-radius: inherit; transition: width .6s ease; background: var(--wlg-water); }
  .meter-fill.level-warn { background: var(--wlg-warn); }
  .meter-fill.level-alarm { background: var(--wlg-alarm); }
  .tick { position: absolute; top: -3px; bottom: -3px; width: 2px; background: var(--wlg-warn); transform: translateX(-1px); }
  .tick-burst { background: var(--wlg-alarm); }
  .legend { display: flex; gap: 4px 14px; flex-wrap: wrap; font-size: 11px; color: var(--wlg-muted); margin-bottom: 4px; font-variant-numeric: tabular-nums; }
  .legend span { display: inline-flex; align-items: center; gap: 5px; }
  .key { width: 2px; height: 10px; background: var(--wlg-warn); display: inline-block; }
  .key-burst { background: var(--wlg-alarm); }

  .row { display: flex; align-items: center; gap: 10px; padding: 6px 0; }
  .row + .row { border-top: 1px dashed var(--wlg-line); }
  .row-text { flex: 1; min-width: 0; }
  .row-title { font-size: 14px; overflow-wrap: anywhere; }
  .row-sub { font-size: 12px; color: var(--wlg-muted); display: flex; align-items: center; gap: 4px; overflow-wrap: anywhere; }
  .mini { --mdc-icon-size: 14px; }

  /* Detectors: compact 2×2 status grid, status only (no switches, no links). */
  .tiles { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 6px; margin-bottom: 6px; }
  .tile {
    display: flex; align-items: center; justify-content: space-between; gap: 6px; min-width: 0;
    padding: 4px 6px 4px 10px; border-radius: 10px; background: var(--wlg-soft);
  }
  .tile-active { background: color-mix(in srgb, var(--wlg-alarm) 12%, transparent); }
  .tile-name { font-size: 13px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tile .pill { padding: 2px 8px; font-size: 11px; flex: none; }

  .pill {
    display: inline-flex; align-items: center; padding: 3px 10px; border-radius: 999px; font-size: 12px;
    font-weight: 500; white-space: nowrap; background: var(--wlg-soft); color: var(--wlg-muted);
  }
  .pill-ok, .pill-idle { background: color-mix(in srgb, var(--wlg-ok) 14%, transparent); color: var(--wlg-ok); }
  .pill-monitoring { background: color-mix(in srgb, var(--wlg-watch) 16%, transparent); color: var(--wlg-watch); }
  .pill-active, .pill-alarm { background: var(--wlg-alarm); color: var(--text-primary-color, #fff); }
  .pill-bypass, .pill-warn { background: color-mix(in srgb, var(--wlg-warn) 18%, transparent); color: var(--wlg-warn); }
  .pill-off, .pill-paused, .pill-unknown { background: var(--wlg-soft); color: var(--wlg-muted); }
  .pill-unknown { border: 1px dashed var(--wlg-line); }

  .monitor { margin: 0 16px 10px; padding: 0 12px; border-radius: 12px; background: var(--wlg-soft); }
  .monitor .row { padding: 6px 0; }
  .monitor-warn { background: color-mix(in srgb, var(--wlg-warn) 14%, transparent); }
  .monitor-monitoring { background: color-mix(in srgb, var(--wlg-watch) 10%, transparent); }
  .monitor .row-title { font-weight: 500; }
  .details { padding: 0 0 10px; font-size: 13px; }
  .details summary { cursor: pointer; color: var(--wlg-muted); font-size: 12px; line-height: 20px; padding: 12px 0; }
  .details dl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 4px 12px; margin: 0; }
  .details dt { color: var(--wlg-muted); }
  .details dd { margin: 0; overflow-wrap: anywhere; }
  .details code { font-size: 11px; color: var(--wlg-muted); background: none; }
  .linkish { color: var(--primary-color, #03a9f4); font-size: inherit; overflow-wrap: anywhere; text-align: left; }
  .how { margin: 8px 0 0; padding-left: 18px; font-size: 12px; color: var(--wlg-muted); line-height: 1.45; }
  .how li + li { margin-top: 2px; }

  /* Collapsible sections: summary row = real button (aria-expanded) + chevron. */
  .coll { padding-top: 0; padding-bottom: 0; }
  .sum { display: flex; align-items: center; gap: 8px; }
  .sum-btn {
    flex: 1; min-width: 0; display: flex; align-items: center; gap: 8px; min-height: 44px; padding: 2px 0;
    background: none; border: 0; cursor: pointer; text-align: left; border-radius: 8px;
  }
  .sum-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 0; }
  .sum-title { font-size: 12px; font-weight: 500; color: var(--wlg-muted); line-height: 1.3; }
  .sum-status { font-size: 14px; line-height: 1.3; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; overflow-wrap: anywhere; }
  .sum-status .pill { padding: 1px 8px; font-size: 12px; }
  .sum-cov { color: var(--wlg-muted); font-variant-numeric: tabular-nums; }
  .bypass-on .sum-status .on { color: var(--wlg-warn); font-weight: 500; }
  .chev { color: var(--wlg-muted); flex: none; transition: transform .2s; }
  .sum-btn[aria-expanded="true"] .chev { transform: rotate(180deg); }
  .sec-body { padding: 2px 0 6px; }

  .actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 4px 0 6px; }
  .actions.end { justify-content: flex-end; }
  .btn {
    display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding: 0 14px; border-radius: 999px;
    border: 1px solid transparent; cursor: pointer; font-size: 14px; font-weight: 500; --mdc-icon-size: 18px;
    max-width: 100%; text-align: left;
  }
  .btn-small { min-height: 44px; padding: 0 12px; font-size: 13px; flex: none; }
  .btn[disabled] { opacity: .5; cursor: not-allowed; }
  .btn-primary { background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff); }
  .btn-danger { background: var(--wlg-alarm); color: var(--text-primary-color, #fff); }
  .btn-danger-ghost { background: transparent; border-color: color-mix(in srgb, var(--wlg-alarm) 45%, transparent); color: var(--wlg-alarm); }
  .btn-danger-ghost:hover:not([disabled]) { background: color-mix(in srgb, var(--wlg-alarm) 10%, transparent); }
  .btn-ghost { background: transparent; border-color: var(--wlg-line); }
  .btn-ghost:hover:not([disabled]) { background: var(--wlg-soft); }
  .btn-quiet { background: transparent; color: var(--wlg-muted); padding: 0 8px; }
  .btn-quiet:hover:not([disabled]) { color: var(--wlg-alarm); }
  .btn:focus-visible, .link:focus-visible, .link-plain:focus-visible, .stat:focus-visible, .orb:focus-visible, .sum-btn:focus-visible {
    outline: 2px solid var(--primary-color, #03a9f4); outline-offset: 2px;
  }

  .link, .link-plain, .stat { background: none; border: 0; padding: 0; cursor: pointer; text-align: left; }
  .link { color: var(--primary-text-color); font-size: 14px; }
  /* Small text links get a 44 px tall hit area without taking layout space. */
  .link, .link-plain { position: relative; }
  .link:not([disabled])::after, .link-plain::after { content: ""; position: absolute; inset: -12px -6px; min-height: 44px; }
  span.link { cursor: default; }
  .link[disabled] { cursor: default; }
  .note { font-size: 12px; color: var(--wlg-muted); line-height: 1.4; }
  .note.subtle { margin: 4px 0 2px; }
  .alarm .note.subtle { margin-top: 10px; }

  .progress { height: 4px; border-radius: 999px; background: var(--wlg-soft); overflow: hidden; margin: 2px 0 8px; }
  .progress div { height: 100%; background: var(--primary-color, #03a9f4); border-radius: inherit; }
  /* Four equal columns that never wrap, down to a 320 px card. */
  .stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; margin: 0 0 4px; }
  .stat {
    display: flex; flex-direction: column; gap: 1px; min-width: 0; padding: 6px 6px; border-radius: 10px;
    background: var(--wlg-soft); text-align: left;
  }
  .stat { justify-content: space-between; }
  .stat-label { font-size: 10.5px; line-height: 1.2; color: var(--wlg-muted); overflow-wrap: anywhere; hyphens: auto; }
  .stat b { font-size: 14px; font-weight: 500; font-variant-numeric: tabular-nums; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .stat small { font-size: 10.5px; color: var(--wlg-muted); min-height: 1.2em; }
`;

/* ------------------------------------------------------------------- editor */

class WaterLeakGuardCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._form) {
      this._render();
      return;
    }
    this._form.hass = hass;
    const key = statusEntityIds(hass).join(",");
    if (key !== this._statusKey) {
      this._statusKey = key;
      this._form.schema = this._schema();
    }
  }

  _schema() {
    // HA's entity selector cannot filter by translation_key (filter keys: integration,
    // domain, device_class, supported_features, unit_of_measurement). include_entities
    // is supported, so offer exactly the status sensors when the registry is loaded.
    const ids = statusEntityIds(this._hass);
    const entity = { filter: { integration: DOMAIN, domain: "sensor" } };
    if (ids.length) entity.include_entities = ids;
    return [
      { name: "entity", selector: { entity } },
      { name: "title", selector: { text: {} } },
      {
        type: "grid",
        name: "",
        schema: ["show_flow", "show_detectors", "show_bypass", "show_external", "show_learning", "show_background"].map(
          (name) => ({ name, selector: { boolean: {} } })
        ),
      },
    ];
  }

  _render() {
    if (!this._hass || !this._config) return;
    const t = translator(this._hass);
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => t(`editor.${s.name}`);
      this._form.computeHelper = (s) => (s.name === "title" ? t("editor.title_hint") : undefined);
      this._form.addEventListener("value-changed", (ev) => {
        this._config = { ...this._config, ...ev.detail.value };
        fire(this, "config-changed", { config: this._config });
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._statusKey = statusEntityIds(this._hass).join(",");
    this._form.schema = this._schema();
    this._form.data = { ...DEFAULT_CONFIG, ...this._config };
  }
}

/* ------------------------------------------------------------- registration */

const loadedCard = customElements.get(CARD_TAG);
if (!loadedCard) {
  customElements.define(CARD_TAG, WaterLeakGuardCard);
} else if (loadedCard.cardVersion !== CARD_VERSION) {
  // Custom elements cannot be redefined: the first loaded copy wins. The
  // integration loads its own copy; a manual dashboard resource is obsolete.
  console.warn(
    `water-leak-guard-card: version ${loadedCard.cardVersion || "≤ 0.2.0"} is already loaded, ` +
      `${CARD_VERSION} is ignored. Remove a manually added dashboard resource ` +
      `(/local/water-leak-guard-card.js) and reload the browser.`
  );
}
if (!customElements.get(EDITOR_TAG)) customElements.define(EDITOR_TAG, WaterLeakGuardCardEditor);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === CARD_TAG)) {
  window.customCards.push({
    type: CARD_TAG,
    name: "Water Leak Guard",
    description: "Status, flow, bypass, learning and external sensors of Water Leak Guard (Wasserwächter).",
    preview: true,
    documentationURL: "https://github.com/BeGiBue/homeassistant-water-leak-detection/blob/main/docs/CARD.md",
  });
}

console.info(`%c WATER-LEAK-GUARD-CARD %c ${CARD_VERSION} `, "color:#fff;background:#039be5;font-weight:600", "color:#039be5");
