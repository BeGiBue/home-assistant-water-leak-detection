/*
 * Water Leak Guard card for Home Assistant dashboards.
 *
 * Frontend view for the `water_leak_detection` integration. The card is a pure
 * view on the existing entities and services and is not a trust boundary: it
 * never holds recipient tokens or reset nonces, and every safety decision
 * (authorization, Home presence, allowed alarm actions) stays in the backend.
 *
 * Alarm handling today (the card does not call the backend alarm commands yet):
 *   - Personal mute: from the notification on the recipient's own device, anywhere.
 *   - Global acknowledgement: only while that recipient is Home – from the
 *     notification or from Configure → Acknowledgements (admin).
 *   - External reset: from the notification of an authorized device at Home.
 *   - Hydraulic alarms end when the flow meets their quiet/reset condition.
 *     Switching the Slow Leak or Low Flow detector off, or starting the High Flow
 *     bypass, also ends that detector's ACTIVE alarm at once (incl. its share of
 *     the shutoff request) without fixing the cause; the card asks for
 *     confirmation first. Burst Leak can be neither disabled nor bypassed.
 * Acknowledging never ends detection, the alarm or the shutoff request.
 *
 * INTERFACE below names the WebSocket commands the backend registers
 * (websocket.py: session, mute, acknowledge, external_reset). The card does not
 * use them yet (`enabled: false`), so it never offers an action it cannot run.
 *
 * License: AGPL-3.0-only (same as the integration).
 */

const CARD_VERSION = "0.3.1";
const DOMAIN = "water_leak_detection";
const CARD_TAG = "water-leak-guard-card";
const EDITOR_TAG = "water-leak-guard-card-editor";

/**
 * Backend card commands as registered in websocket.py. Kept in one place so the
 * card can be wired to them (stage C) by changing only this object and its call
 * sites. `config_entry_id` is optional in every command (needed with several
 * instances). The card does not use these commands yet.
 */
const INTERFACE = {
  enabled: false, // switch on only together with the stage C frontend wiring and its tests
  session: `${DOMAIN}/session`, // { config_entry_id? }
  mute: `${DOMAIN}/mute`, // { config_entry_id?, event_id }
  acknowledge: `${DOMAIN}/acknowledge`, // { config_entry_id?, event_id }
  externalReset: `${DOMAIN}/external_reset`, // { config_entry_id?, event_id, source_id, source_generation }
  integrationPath: `/config/integrations/integration/${DOMAIN}`,
};

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
    acknowledge: "Quittieren",
    acknowledge_hint: "Quittieren stoppt nur Benachrichtigungen. Erkennung, Alarm und Absperranforderung bleiben bestehen.",
    muted_count: "Auf {n} Gerät(en) stummgeschaltet",
    how_mute: "Stummschalten: über die Benachrichtigung auf dem eigenen Gerät – auch unterwegs, gilt nur für dieses Gerät.",
    how_global_ack: "Global quittieren: nur zuhause – über die Benachrichtigung oder unter Konfigurieren → Quittierung.",
    how_external_reset: "Zurücksetzen: über die Benachrichtigung eines dafür berechtigten Geräts, das zuhause ist. Der Sensor wird erst wieder scharf, wenn er trocken meldet.",
    open_integration: "Zur Integration",
    clear_alarm: "Alarm löschen",
    clear_requires_home: "Nur von zuhause möglich",
    clear_presence_unknown: "Deinem Benutzer ist keine Person zugeordnet – Anwesenheit unbekannt",
    hydraulic_clears_itself: "Endet, sobald der Durchfluss die Ruhe-/Rücksetzbedingung erfüllt. Slow Leak und Low Flow enden auch beim Ausschalten ihres Detektors, High Flow beim Start des Bypass – die Ursache wird dadurch nicht behoben. Burst Leak endet nur physisch.",
    ends_slow_low: "Endet, sobald der Durchfluss die Ruhe-/Rücksetzbedingung erfüllt. Ausschalten dieses Detektors beendet den Alarm ebenfalls sofort – die Ursache (z. B. ein offener Hahn oder ein Leck) wird dadurch nicht behoben.",
    ends_high: "Endet, sobald der Durchfluss die Ruhe-/Rücksetzbedingung erfüllt. Der Start des High-Flow-Bypass beendet den Alarm ebenfalls sofort – die Ursache (z. B. ein offener Hahn oder ein Leck) wird dadurch nicht behoben.",
    ends_burst: "Endet nur physisch: sobald der Durchfluss die Ruhe-/Rücksetzbedingung erfüllt. Burst Leak lässt sich weder ausschalten noch per Bypass überbrücken.",
    confirm_disable: "Ein Alarm „{kind}“ läuft. Ausschalten des Detektors beendet diesen Alarm und seinen Beitrag zur Absperranforderung sofort. Die Ursache (z. B. ein offener Hahn oder ein Leck) wird dadurch nicht behoben. Der Burst-Leak-Schutz bleibt aktiv.\n\nDetektor trotzdem ausschalten?",
    confirm_bypass: "Ein High-Flow-Alarm läuft. Der Start des Bypass beendet diesen Alarm und seinen Beitrag zur Absperranforderung sofort. Die Ursache (z. B. ein offener Hahn oder ein Leck) wird dadurch nicht behoben. Der Burst-Leak-Schutz bleibt aktiv.\n\nBypass trotzdem starten?",
    storage_paused_hint: "Laufzeitspeicher beschädigt – der Zustand der Erkennung ist nicht gesichert.",
    external_offline_banner: "Ein externer Lecksensor ist nicht erreichbar. Ein Leck an dieser Stelle würde nicht erkannt.",
    action_unavailable: "Diese Aktion wird vom Backend noch nicht angeboten.",
    action_failed: "Aktion abgelehnt: {msg}",
    integration_unavailable: "Die Integration liefert keinen Status. Die Anzeige ist nicht aktuell.",
    sensor_unavailable: "Nicht verfügbar",
    flow: "Durchfluss",
    flow_unavailable: "Kein Messwert",
    high: "High",
    burst: "Burst",
    detectors: "Erkennung",
    always_on: "nicht abschaltbar",
    bypass: "High-Flow-Bypass",
    bypass_off: "Aus – High Flow wird überwacht",
    bypass_on: "Aktiv – noch {left}",
    bypass_until: "bis {time}",
    bypass_stop: "Beenden",
    bypass_default: "Standard",
    bypass_note: "Burst-Leak-Schutz bleibt immer aktiv.",
    external: "Externe Lecksensoren",
    external_phase: { ARMED: "Trocken", ACTIVE: "Leck", RESET_WAITING_FOR_OFF: "Wartet auf trocken" },
    external_conflict: "Identitätskonflikt",
    contributes_shutoff: "Löst Absperrung aus",
    learning: "Lernmodell",
    confidence: { insufficient: "Unzureichend", learning: "Lernt", reliable: "Zuverlässig" },
    coverage: "Abdeckung",
    days: "{n} von {w} Tagen",
    learned_max: "Normalspitze",
    long_term_max: "Langzeitmaximum",
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
    acknowledge: "Acknowledge",
    acknowledge_hint: "Acknowledging only stops notifications. Detection, alarm and shutoff request stay active.",
    muted_count: "Muted on {n} device(s)",
    how_mute: "Mute: from the notification on your own device – also away, only for that device.",
    how_global_ack: "Acknowledge globally: only at home – from the notification or via Configure → Acknowledgements.",
    how_external_reset: "Reset: from the notification of an authorized device at home. The sensor re-arms only after it reports dry.",
    open_integration: "Open integration",
    clear_alarm: "Clear alarm",
    clear_requires_home: "Only possible from home",
    clear_presence_unknown: "No person is linked to your user – presence unknown",
    hydraulic_clears_itself: "Ends once the flow meets its quiet/reset condition. Slow Leak and Low Flow also end when their detector is switched off, High Flow when the bypass is started – without fixing the cause. Burst Leak ends only physically.",
    ends_slow_low: "Ends once the flow meets its quiet/reset condition. Switching this detector off also ends the alarm at once – without fixing the cause (e.g. an open tap or a leak).",
    ends_high: "Ends once the flow meets its quiet/reset condition. Starting the High Flow bypass also ends the alarm at once – without fixing the cause (e.g. an open tap or a leak).",
    ends_burst: "Ends only physically: once the flow meets its quiet/reset condition. Burst Leak can be neither switched off nor bypassed.",
    confirm_disable: "A {kind} alarm is running. Switching the detector off ends this alarm and its contribution to the shutoff request immediately. The cause (e.g. an open tap or a leak) is not fixed. Burst Leak protection stays active.\n\nSwitch the detector off anyway?",
    confirm_bypass: "A High Flow alarm is running. Starting the bypass ends this alarm and its contribution to the shutoff request immediately. The cause (e.g. an open tap or a leak) is not fixed. Burst Leak protection stays active.\n\nStart the bypass anyway?",
    storage_paused_hint: "Runtime store damaged – the detection state is not reliable.",
    external_offline_banner: "An external leak sensor is unreachable. A leak at that spot would not be detected.",
    action_unavailable: "The backend does not offer this action yet.",
    action_failed: "Action rejected: {msg}",
    integration_unavailable: "The integration reports no status. The display is not current.",
    sensor_unavailable: "Unavailable",
    flow: "Flow",
    flow_unavailable: "No reading",
    high: "High",
    burst: "Burst",
    detectors: "Detection",
    always_on: "cannot be disabled",
    bypass: "High Flow bypass",
    bypass_off: "Off – High Flow is monitored",
    bypass_on: "Active – {left} left",
    bypass_until: "until {time}",
    bypass_stop: "Stop",
    bypass_default: "Default",
    bypass_note: "Burst Leak protection always stays active.",
    external: "External leak sensors",
    external_phase: { ARMED: "Dry", ACTIVE: "Leak", RESET_WAITING_FOR_OFF: "Waiting for dry" },
    external_conflict: "Identity conflict",
    contributes_shutoff: "Triggers shutoff",
    learning: "Learning",
    confidence: { insufficient: "Insufficient", learning: "Learning", reliable: "Reliable" },
    coverage: "Coverage",
    days: "{n} of {w} days",
    learned_max: "Normal peak",
    long_term_max: "Long-term maximum",
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

/** First status sensor of this integration, for auto-configuration. */
function findStatusEntity(hass) {
  const registry = hass?.entities || {};
  const match = Object.values(registry).find(
    (e) => e.platform === DOMAIN && e.translation_key === "status"
  );
  return match ? match.entity_id : undefined;
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

/**
 * Presence of the logged-in viewer, derived from the person linked to the HA user.
 * Display hint only; it affects the rendering only when INTERFACE.enabled. Under the backend contract
 * the backend decides Home from the device tracker of the paired recipient; the
 * card's person-based guess never authorizes anything.
 */
function viewerPresence(hass) {
  const userId = hass?.user?.id;
  if (!userId) return { known: false, home: false };
  const person = Object.values(hass.states || {}).find(
    (s) => s.entity_id.startsWith("person.") && s.attributes?.user_id === userId
  );
  if (!person) return { known: false, home: false };
  return { known: true, home: person.state === "home", entity_id: person.entity_id };
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
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
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
    this._config = { ...DEFAULT_CONFIG, ...config };
    this._signature = "";
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const signature = this._computeSignature();
    if (signature !== this._signature) {
      this._signature = signature;
      this._render();
    }
  }

  get hass() {
    return this._hass;
  }

  getCardSize() {
    return 9;
  }

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
    const status = this._hass.states[this._statusEntity];
    for (const src of status?.attributes?.external_sources || []) {
      if (src?.source_entity) ids.push(src.source_entity);
    }
    const parts = ids.map((id) => {
      const s = this._hass.states[id];
      return s ? `${id}:${s.state}:${s.last_updated}` : `${id}:-`;
    });
    const presence = viewerPresence(this._hass);
    parts.push(
      `p:${presence.known}:${presence.home}`,
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
    const entryId = await this._entryId(this._statusEntity);
    return entryId ? { config_entry_id: entryId, ...extra } : { ...extra };
  }

  /* -------------------------------------------------------------- actions */

  /** Current phase of one hydraulic detector, read fresh from the status sensor. */
  _detectorPhase(kind) {
    const status = this._hass?.states?.[this._statusEntity];
    return status?.attributes?.detectors?.[kind];
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

  /** Call a backend alarm command. Only reachable when INTERFACE.enabled is true. */
  async _proposed(command, payload) {
    try {
      await this._hass.callWS({ type: command, ...payload });
    } catch (err) {
      if (err && (err.code === "unknown_command" || err.code === "not_found")) {
        // Never pretend: an unknown command is reported, nothing else is opened.
        fire(this, "hass-notification", { message: translator(this._hass)("action_unavailable") });
        return;
      }
      throw err;
    }
  }

  _onClick(ev) {
    const target = ev.target.closest("[data-action]");
    if (!target || target.hasAttribute("disabled")) return;
    const { action } = target.dataset;
    const t = translator(this._hass);

    switch (action) {
      case "more-info":
        fire(this, "hass-more-info", { entityId: target.dataset.entity });
        break;
      case "open-integration":
        navigate(INTERFACE.integrationPath);
        break;
      case "toggle": {
        const entityId = target.dataset.entity;
        const on = this._hass.states[entityId]?.state === "on";
        const kind = target.dataset.kind;
        // Switching off ends this detector's ACTIVE alarm at once (backend:
        // apply_controls -> IDLE). Ask first; switching on never asks.
        if (
          on &&
          (kind === "slow_leak" || kind === "low_flow") &&
          this._detectorPhase(kind) === "active" &&
          !window.confirm(t("confirm_disable", { kind: t(`detector.${kind}`) }))
        ) {
          return;
        }
        this._run(`toggle:${entityId}`, () =>
          this._hass.callService("switch", on ? "turn_off" : "turn_on", { entity_id: entityId })
        );
        break;
      }
      case "bypass-start": {
        const minutes = num(target.dataset.minutes);
        // Starting the bypass ends an ACTIVE High Flow alarm at once. Ask first.
        if (this._detectorPhase("high_flow") === "active" && !window.confirm(t("confirm_bypass"))) {
          return;
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
      case "acknowledge":
        if (!INTERFACE.enabled) return;
        this._run(`ack:${target.dataset.event}`, async () =>
          this._proposed(INTERFACE.acknowledge, await this._serviceData({ event_id: target.dataset.event }))
        );
        break;
      case "external-reset": {
        if (!INTERFACE.enabled) return;
        // Schema of water_leak_detection/external_reset: all three fields required, strings.
        const payload = {
          event_id: target.dataset.event,
          source_id: target.dataset.source,
          source_generation: target.dataset.generation,
        };
        if (!payload.event_id || !payload.source_id || !payload.source_generation) return;
        this._run(`clear:${target.dataset.event}`, async () =>
          this._proposed(INTERFACE.externalReset, await this._serviceData(payload))
        );
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
    const tone = alarm
      ? "alarm"
      : statusUnavailable
        ? "neutral"
        : extOffline || monitoring.state === "blocked" || (monitoring.state === "missing" && status.state === "source_unavailable")
          ? "warn"
          : monitoring.state !== "active"
            ? "neutral"
            : String(status.state).endsWith("_monitoring")
              ? "watch"
              : "ok";

    const header = this._renderHeader(t, status, tone, alarm, shutoff, monitoring, statusUnavailable, extOffline);
    if (statusUnavailable) {
      this.shadowRoot.innerHTML = `<style>${STYLES}</style>
        <ha-card class="tone-${tone}">${header}
          <div class="banner banner-warn"><ha-icon icon="mdi:alert-circle-outline"></ha-icon><span>${esc(t("integration_unavailable"))}</span></div>
        </ha-card>`;
      return;
    }

    const sections = [
      header,
      this._renderBanners(t, status, monitoring, extOffline),
      this._renderMonitoring(t, map, monitoring),
      alarm ? this._renderAlarm(t, map, status) : "",
      this._config.show_flow ? this._renderFlow(t, map) : "",
      this._config.show_detectors ? this._renderDetectors(t, map, status, monitoring) : "",
      this._config.show_bypass ? this._renderBypass(t, map) : "",
      this._config.show_external ? this._renderExternal(t, status) : "",
      this._config.show_learning ? this._renderLearning(t, map) : "",
    ];

    this.shadowRoot.innerHTML = `<style>${STYLES}</style>
      <ha-card class="tone-${tone}">${sections.join("")}</ha-card>`;
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
    // A configured external sensor that is unreachable: no alarm, but not "all quiet".
    if (extOffline && status.state === "idle") return t("status.idle");
    if (status.state === "source_unavailable") {
      // With the monitoring entity, its own row explains the source problem.
      return monitoring.state === "missing" ? label("source_unavailable") : t("status.idle");
    }
    if (status.state === "idle") return monitoring.state === "active" ? t("status.all_quiet") : t("status.idle");
    return label(status.state);
  }

  _renderHeader(t, status, tone, alarm, shutoff, monitoring, statusUnavailable, extOffline) {
    const title = this._config.title || deviceName(this._hass, status.entity_id) || t("title");
    const icon = {
      alarm: "mdi:water-alert",
      warn: "mdi:water-off",
      watch: "mdi:water-sync",
      neutral: "mdi:water-outline",
      ok: "mdi:water-check",
    }[tone];
    return `
      <header class="head${this._config.show_background ? " has-motif" : ""}">
        ${this._config.show_background ? BACKGROUND_MOTIF : ""}
        <button class="orb" data-action="more-info" data-entity="${esc(status.entity_id)}" aria-label="${esc(title)}">
          <ha-icon icon="${icon}"></ha-icon>
        </button>
        <div class="head-text">
          <div class="eyebrow">${esc(title)}</div>
          <div class="headline">${esc(this._headline(t, status, monitoring, statusUnavailable, alarm, extOffline))}</div>
        </div>
        <div class="flags">
          ${alarm ? `<span class="flag flag-alarm"><ha-icon icon="mdi:pipe-leak"></ha-icon>${esc(t("alarm"))}</span>` : ""}
          ${shutoff ? `<span class="flag flag-shutoff"><ha-icon icon="mdi:valve-closed"></ha-icon>${esc(t("shutoff"))}</span>` : ""}
        </div>
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
    const presence = viewerPresence(this._hass);
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
        const isDisplay = ev.event_id === a.active_event_id;
        const duration = isDisplay
          ? durationAttrs[`duration_human_${lang(this._hass)}`] || durationAttrs.duration_human
          : ev.seconds != null
            ? formatSeconds(ev.seconds)
            : "";
        const label = ev.external ? `${t("detector.external_leak")} · ${ev.name || ev.source_id}` : t(`detector.${ev.kind}`);
        const ackKey = `ack:${ev.event_id}`;
        const clearKey = `clear:${ev.event_id}`;

        const muted = Array.isArray(ack.muted_recipients) ? ack.muted_recipients.length : 0;
        const how = [];
        if (!acked) how.push(t("how_mute"), t("how_global_ack"));
        how.push(this._endHint(t, ev));

        let clearHtml = "";
        if (!INTERFACE.enabled) {
          clearHtml = "";
        } else if (ev.external) {
          const blocked = !presence.home;
          const reason = !presence.known ? t("clear_presence_unknown") : t("clear_requires_home");
          clearHtml = `
            <button class="btn btn-danger" data-action="external-reset" data-event="${esc(ev.event_id)}"
              data-source="${esc(ev.source_id)}" data-generation="${esc(ev.source_generation)}"
              ${blocked || this._busy.has(clearKey) ? "disabled" : ""}
              title="${esc(blocked ? reason : t("clear_alarm"))}">
              <ha-icon icon="${blocked ? "mdi:home-lock" : "mdi:broom"}"></ha-icon>${esc(t("clear_alarm"))}
            </button>
            ${blocked ? `<div class="note">${esc(reason)}</div>` : ""}`;
        }

        return `
          <div class="event">
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
            ${muted && !acked ? `<div class="note">${esc(t("muted_count", { n: muted }))}</div>` : ""}
            <ul class="how">${how.map((line) => `<li>${esc(line)}</li>`).join("")}</ul>
            ${INTERFACE.enabled ? `<div class="event-actions">
              ${acked ? "" : `
                <button class="btn btn-primary" data-action="acknowledge" data-event="${esc(ev.event_id)}"
                  ${this._busy.has(ackKey) ? "disabled" : ""} title="${esc(t("acknowledge_hint"))}">
                  <ha-icon icon="mdi:bell-check"></ha-icon>${esc(t("acknowledge"))}
                </button>`}
              ${clearHtml}
            </div>` : ""}
          </div>`;
      })
      .join("");

    const anyOpen = events.some((ev) => !ackStates[ev.event_id]?.globally_acknowledged);
    const adminLink = this._hass.user?.is_admin && anyOpen && !INTERFACE.enabled
      ? `<div class="event-actions"><button class="btn btn-ghost" data-action="open-integration">
           <ha-icon icon="mdi:cog-outline"></ha-icon>${esc(t("open_integration"))}</button></div>`
      : "";
    return `<section class="alarm">${rows}${adminLink}<div class="note subtle">${esc(t("acknowledge_hint"))}</div></section>`;
  }

  _renderFlow(t, map) {
    const flowState = this._state(map, "current_flow");
    const flow = flowState && flowState.state !== "unavailable" ? num(flowState.state) : null;
    const high = num(this._state(map, "effective_high_threshold")?.state);
    const burst = num(this._state(map, "effective_burst_threshold")?.state);
    const max = Math.max((burst || 3500) * 1.15, flow || 0, 1);
    // Log scale: a 3 L/h trickle and a 3,500 L/h burst both stay readable.
    const pos = (v) => Math.min(100, Math.max(0, (Math.log10(1 + v) / Math.log10(1 + max)) * 100));
    const level = flow == null ? "none" : burst && flow >= burst ? "alarm" : high && flow >= high ? "warn" : flow > 0 ? "flow" : "none";

    return `
      <section class="block">
        <div class="block-head">
          <span>${esc(t("flow"))}</span>
          <button class="link" data-action="more-info" data-entity="${esc(map.current_flow || "")}" ${map.current_flow ? "" : "disabled"}>
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

  _renderDetectors(t, map, status, monitoring) {
    const a = status.attributes || {};
    const phases = a.detectors || {};
    const bypass = this._state(map, "high_flow_bypass")?.state === "on";
    const switches = { slow_leak: map.slow_leak_detection, low_flow: map.low_flow_detection };

    const rows = HYDRAULIC_KINDS.map((kind) => {
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
      const busy = switchId && this._busy.has(`toggle:${switchId}`);
      const control = switchId
        ? `<button class="switch ${enabled ? "on" : ""}" role="switch" aria-checked="${enabled}"
             aria-label="${esc(t(`detector.${kind}`))}" data-action="toggle" data-kind="${esc(kind)}" data-entity="${esc(switchId)}" ${busy ? "disabled" : ""}>
             <span class="knob"></span></button>`
        : kind === "burst_leak"
          ? `<span class="fixed">${esc(t("always_on"))}</span>`
          : `<span class="fixed"></span>`;
      return `
        <div class="row">
          <div class="row-text">
            <div class="row-title">${esc(t(`detector.${kind}`))}</div>
            <div class="row-sub">${esc(t(`detector_hint.${kind}`))}</div>
          </div>
          <span class="pill pill-${pillClass || phase}" ${phase === "paused" ? `title="${esc(t(pausedHint))}"` : ""}>${esc(t(`phase.${phase}`))}</span>
          ${control}
        </div>`;
    }).join("");

    return `<section class="block"><div class="block-head"><span>${esc(t("detectors"))}</span></div>${rows}</section>`;
  }

  _renderBypass(t, map) {
    const sw = this._state(map, "high_flow_bypass");
    if (!sw) return "";
    const active = sw.state === "on";
    const remaining = num(this._state(map, "high_flow_bypass_remaining")?.state) ?? num(sw.attributes?.remaining_seconds) ?? 0;
    const finishes = sw.attributes?.finishes_at;
    const defaultMinutes = num(this._state(map, "high_flow_bypass_duration")?.state);
    const busy = this._busy.has("bypass");
    const presets = (this._config.bypass_presets || [])
      .map(num)
      .filter((m) => m && m >= 1 && m <= 1440);

    const presetButtons = presets
      .map((m) => `<button class="btn btn-ghost" data-action="bypass-start" data-minutes="${m}" ${busy ? "disabled" : ""}>${m % 60 === 0 ? `${m / 60} h` : `${m} min`}</button>`)
      .join("");

    return `
      <section class="block">
        <div class="block-head">
          <span>${esc(t("bypass"))}</span>
          <button class="link" data-action="more-info" data-entity="${esc(sw.entity_id)}">
            ${active
              ? `${esc(t("bypass_on", { left: formatSeconds(remaining) }))}${finishes ? ` <span class="muted">${esc(t("bypass_until", { time: formatClock(this._hass, finishes) }))}</span>` : ""}`
              : `<span class="muted">${esc(t("bypass_off"))}</span>`}
          </button>
        </div>
        <div class="actions">
          ${active
            ? `<button class="btn btn-primary" data-action="bypass-stop" ${busy ? "disabled" : ""}><ha-icon icon="mdi:stop-circle-outline"></ha-icon>${esc(t("bypass_stop"))}</button>`
            : `${presetButtons}
               <button class="btn btn-ghost" data-action="bypass-start" ${busy ? "disabled" : ""}>${esc(t("bypass_default"))}${defaultMinutes ? ` · ${esc(formatSeconds(defaultMinutes * 60))}` : ""}</button>`}
        </div>
        <div class="note subtle">${esc(t("bypass_note"))}</div>
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
    const tone = { reliable: "ok", learning: "monitoring", insufficient: "idle" }[conf.state] || "idle";

    return `
      <section class="block">
        <div class="block-head">
          <span>${esc(t("learning"))}</span>
          <span class="pill pill-${tone}">${esc(t(`confidence.${conf.state}`))}</span>
        </div>
        <div class="progress"><div style="width:${pct.toFixed(1)}%"></div></div>
        <div class="stats">
          <button class="stat" data-action="more-info" data-entity="${esc(cov?.entity_id || conf.entity_id)}">
            <span>${esc(t("coverage"))}</span><b>${esc(t("days", { n: days, w: windowDays }))}</b>
          </button>
          <button class="stat" data-action="more-info" data-entity="${esc(learned?.entity_id || conf.entity_id)}">
            <span>${esc(t("learned_max"))}</span><b>${learnedVal == null ? "–" : `${esc(formatNumber(this._hass, learnedVal))} L/h`}</b>
          </button>
          ${longTerm ? `<button class="stat" data-action="more-info" data-entity="${esc(longTerm.entity_id)}">
            <span>${esc(t("long_term_max"))}</span><b>${longVal == null ? "–" : `${esc(formatNumber(this._hass, longVal))} L/h`}</b>
          </button>` : ""}
          <div class="stat"><span>${esc(t("samples"))}</span><b>${samples ?? "–"}</b></div>
        </div>
        ${isAdmin ? `<div class="actions end">
          <button class="btn btn-quiet" data-action="reset-learning" ${this._busy.has("learning") ? "disabled" : ""}>
            <ha-icon icon="mdi:restore"></ha-icon>${esc(t("reset_learning"))}
          </button></div>` : ""}
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
  }
  ha-card { overflow: hidden; padding-bottom: 8px; }

  /* Shield + water motif: sits in the header and is cut off at its lower edge,
     so it never runs behind the readings below. */
  .head { position: relative; isolation: isolate; overflow: hidden; }
  .head.has-motif { min-height: 140px; box-sizing: border-box; align-content: center; padding-right: 120px; }
  .head > :not(.motif) { position: relative; z-index: 1; }
  .motif {
    position: absolute; z-index: 0; top: 12px; right: 16px; width: 98px; height: 118px;
    pointer-events: none; color: var(--tone);
  }
  .motif .shield-fill { fill: currentColor; opacity: .06; }
  .motif .shield-line { fill: none; stroke: currentColor; stroke-width: 3; opacity: .22; }
  .motif .shield-line.inner { stroke-width: 1.5; opacity: .14; }
  .motif .wave { fill: var(--wlg-water); }
  .motif .wave-back { opacity: .12; animation: wlg-drift 9s linear infinite; }
  .motif .wave-front { opacity: .2; animation: wlg-drift 6s linear infinite reverse; }
  .motif .drop { fill: var(--wlg-alarm); opacity: 0; transform-box: fill-box; transform-origin: center; }
  .tone-alarm .motif .wave { fill: var(--wlg-alarm); }
  /* No reassuring blue water while monitoring is not confirmed active. */
  .tone-neutral .motif .wave { fill: var(--wlg-muted); }
  .tone-warn .motif .wave { fill: var(--wlg-warn); }
  .tone-alarm .motif .shield-line { opacity: .35; }
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
  }
  @media (max-width: 380px) { .motif { width: 80px; height: 96px; right: 10px; } .head.has-motif { min-height: 120px; padding-right: 96px; } }

  ha-card.tone-alarm { box-shadow: inset 0 3px 0 var(--wlg-alarm), var(--ha-card-box-shadow, none); }
  ha-card.tone-warn { box-shadow: inset 0 3px 0 var(--wlg-warn), var(--ha-card-box-shadow, none); }
  ha-icon { --mdc-icon-size: 18px; display: inline-flex; }
  button { font: inherit; color: inherit; }
  .empty { padding: 16px; color: var(--wlg-muted); }

  .head { display: flex; align-items: center; gap: 12px; padding: 16px 16px 12px; flex-wrap: wrap; }
  .orb {
    width: 44px; height: 44px; border-radius: 50%; border: 0; cursor: pointer; flex: none;
    display: grid; place-items: center; --mdc-icon-size: 24px;
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
  .head-text { flex: 1; min-width: 140px; }
  .eyebrow { font-size: 12px; color: var(--wlg-muted); letter-spacing: .02em; }
  .headline { font-size: 20px; font-weight: 500; line-height: 1.25; }
  .flags { display: flex; gap: 6px; flex-wrap: wrap; }
  .flag {
    display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px 4px 8px; border-radius: 999px;
    font-size: 12px; font-weight: 500; --mdc-icon-size: 16px;
  }
  .flag-alarm { background: var(--wlg-alarm); color: var(--text-primary-color, #fff); }
  .flag-shutoff { background: color-mix(in srgb, var(--wlg-alarm) 16%, transparent); color: var(--wlg-alarm); }

  .banner {
    display: flex; gap: 10px; align-items: flex-start; margin: 0 16px 12px; padding: 10px 12px;
    border-radius: 10px; font-size: 13px; line-height: 1.4;
  }
  .banner ha-icon { flex: none; margin-top: 1px; }
  .banner-alarm { background: color-mix(in srgb, var(--wlg-alarm) 14%, transparent); color: var(--primary-text-color); }
  .banner-alarm ha-icon { color: var(--wlg-alarm); }
  .banner-warn { background: color-mix(in srgb, var(--wlg-warn) 16%, transparent); color: var(--primary-text-color); }
  .banner-warn ha-icon { color: var(--wlg-warn); }

  .alarm {
    margin: 0 16px 8px; padding: 12px; border-radius: 12px;
    background: color-mix(in srgb, var(--wlg-alarm) 9%, transparent);
    border: 1px solid color-mix(in srgb, var(--wlg-alarm) 30%, transparent);
  }
  .event + .event { margin-top: 12px; padding-top: 12px; border-top: 1px solid color-mix(in srgb, var(--wlg-alarm) 22%, transparent); }
  .event-top { display: flex; justify-content: space-between; gap: 8px; align-items: flex-start; flex-wrap: wrap; }
  .event-kind { font-weight: 500; font-size: 15px; }
  .event-meta { font-size: 13px; color: var(--wlg-muted); margin-top: 2px; }
  .event-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 10px; }

  .block { padding: 12px 16px 4px; border-top: 1px solid var(--wlg-line); }
  .block-head {
    display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap;
    font-size: 13px; font-weight: 500; color: var(--wlg-muted); margin-bottom: 8px;
  }
  .big { font-size: 22px; font-weight: 500; color: var(--primary-text-color); font-variant-numeric: tabular-nums; }
  .muted { color: var(--wlg-muted); font-weight: 400; }

  .meter { position: relative; height: 10px; border-radius: 999px; background: var(--wlg-soft); margin: 6px 0 8px; }
  .meter-fill { height: 100%; border-radius: inherit; transition: width .6s ease; background: var(--wlg-water); }
  .meter-fill.level-warn { background: var(--wlg-warn); }
  .meter-fill.level-alarm { background: var(--wlg-alarm); }
  .tick { position: absolute; top: -3px; bottom: -3px; width: 2px; background: var(--wlg-warn); transform: translateX(-1px); }
  .tick-burst { background: var(--wlg-alarm); }
  .legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 11px; color: var(--wlg-muted); margin-bottom: 10px; font-variant-numeric: tabular-nums; }
  .legend span { display: inline-flex; align-items: center; gap: 5px; }
  .key { width: 2px; height: 10px; background: var(--wlg-warn); display: inline-block; }
  .key-burst { background: var(--wlg-alarm); }

  .row { display: flex; align-items: center; gap: 10px; padding: 8px 0; }
  .row + .row { border-top: 1px dashed var(--wlg-line); }
  .row-text { flex: 1; min-width: 0; }
  .row-title { font-size: 14px; }
  .row-sub { font-size: 12px; color: var(--wlg-muted); display: flex; align-items: center; gap: 4px; }
  .mini { --mdc-icon-size: 14px; }
  .fixed { min-width: 40px; font-size: 11px; color: var(--wlg-muted); text-align: right; white-space: nowrap; }

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

  .monitor { margin: 0 16px 10px; padding: 2px 12px; border-radius: 12px; background: var(--wlg-soft); }
  .monitor-warn { background: color-mix(in srgb, var(--wlg-warn) 14%, transparent); }
  .monitor-monitoring { background: color-mix(in srgb, var(--wlg-watch) 10%, transparent); }
  .monitor .row-title { font-weight: 500; }
  .details { padding: 0 0 10px; font-size: 13px; }
  .details summary { cursor: pointer; color: var(--wlg-muted); font-size: 12px; padding: 2px 0 6px; }
  .details dl { display: grid; grid-template-columns: max-content 1fr; gap: 4px 12px; margin: 0; }
  .details dt { color: var(--wlg-muted); }
  .details dd { margin: 0; overflow-wrap: anywhere; }
  .details code { font-size: 11px; color: var(--wlg-muted); background: none; }
  .linkish { color: var(--primary-color, #03a9f4); font-size: inherit; }
  .how { margin: 8px 0 0; padding-left: 18px; font-size: 12px; color: var(--wlg-muted); line-height: 1.45; }
  .how li + li { margin-top: 2px; }

  .switch {
    position: relative; width: 40px; height: 22px; border-radius: 999px; border: 0; cursor: pointer; flex: none;
    background: color-mix(in srgb, var(--primary-text-color, #212121) 22%, transparent); transition: background .2s;
  }
  .switch .knob {
    position: absolute; top: 3px; left: 3px; width: 16px; height: 16px; border-radius: 50%;
    background: var(--card-background-color, #fff); transition: transform .2s; box-shadow: 0 1px 2px rgba(0,0,0,.3);
  }
  .switch.on { background: var(--switch-checked-track-color, var(--primary-color, #03a9f4)); }
  .switch.on .knob { transform: translateX(18px); }

  .actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 4px 0 8px; }
  .actions.end { justify-content: flex-end; }
  .btn {
    display: inline-flex; align-items: center; gap: 6px; min-height: 36px; padding: 0 14px; border-radius: 999px;
    border: 1px solid transparent; cursor: pointer; font-size: 14px; font-weight: 500; --mdc-icon-size: 18px;
  }
  .btn[disabled] { opacity: .5; cursor: not-allowed; }
  .btn-primary { background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff); }
  .btn-danger { background: var(--wlg-alarm); color: var(--text-primary-color, #fff); }
  .btn-ghost { background: transparent; border-color: var(--wlg-line); }
  .btn-ghost:hover:not([disabled]) { background: var(--wlg-soft); }
  .btn-quiet { background: transparent; color: var(--wlg-muted); padding: 0 8px; }
  .btn-quiet:hover:not([disabled]) { color: var(--wlg-alarm); }
  .btn:focus-visible, .switch:focus-visible, .link:focus-visible, .stat:focus-visible, .orb:focus-visible {
    outline: 2px solid var(--primary-color, #03a9f4); outline-offset: 2px;
  }

  .link, .link-plain, .stat { background: none; border: 0; padding: 0; cursor: pointer; text-align: left; }
  .link { color: var(--primary-text-color); font-size: 14px; }
  .link[disabled] { cursor: default; }
  .note { font-size: 12px; color: var(--wlg-muted); line-height: 1.4; }
  .note.subtle { margin: 6px 0 4px; }
  .alarm .note.subtle { margin-top: 10px; }

  .progress { height: 6px; border-radius: 999px; background: var(--wlg-soft); overflow: hidden; }
  .progress div { height: 100%; background: var(--primary-color, #03a9f4); border-radius: inherit; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 8px; margin: 10px 0 4px; }
  .stat { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border-radius: 10px; background: var(--wlg-soft); }
  .stat span { font-size: 11px; color: var(--wlg-muted); }
  .stat b { font-size: 14px; font-weight: 500; font-variant-numeric: tabular-nums; }
`;

/* ------------------------------------------------------------------- editor */

class WaterLeakGuardCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
    else this._render();
  }

  _schema() {
    return [
      { name: "entity", selector: { entity: { filter: { integration: DOMAIN, domain: "sensor" } } } },
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
