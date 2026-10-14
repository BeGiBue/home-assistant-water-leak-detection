/*
 * Water Leak Guard card (Wasserwächter-Karte) for Home Assistant dashboards.
 *
 * Prepared frontend for the `water_leak_detection` integration. The card is a
 * pure view on the existing entities and services; it never holds recipient
 * tokens or reset nonces. Safety decisions stay in the backend:
 *
 *   - Acknowledge (silence notifications) is offered from anywhere.
 *   - Clear alarm is only offered while the viewer's person entity is `home`.
 *     This is a UI hint only; the backend must re-check Home authorization.
 *
 * Both actions call proposed WebSocket commands (see INTERFACE below). Until
 * the backend implements them, the card falls back to the existing, protected
 * Configure dialog of the integration.
 *
 * License: AGPL-3.0-only (same as the integration).
 */

const CARD_VERSION = "0.1.0";
const DOMAIN = "water_leak_detection";
const CARD_TAG = "water-leak-guard-card";
const EDITOR_TAG = "water-leak-guard-card-editor";

/**
 * Proposed backend interface. Kept in one place so the later interface
 * documentation can be adopted by changing only this object.
 */
const INTERFACE = {
  acknowledge: `${DOMAIN}/acknowledge`, // { config_entry_id, event_id }
  clearAlarm: `${DOMAIN}/clear_alarm`, // { config_entry_id, event_id, source_id?, source_generation? }
  fallbackPath: `/config/integrations/integration/${DOMAIN}`,
};

const DEFAULT_CONFIG = {
  show_flow: true,
  show_detectors: true,
  show_bypass: true,
  show_external: true,
  show_learning: true,
  bypass_presets: [60, 120, 240],
};

const I18N = {
  de: {
    title: "Wasserwächter",
    not_found: "Keine Wasserwächter-Instanz gefunden. Bitte im Karteneditor die Status-Entität wählen.",
    status: {
      source_unavailable: "Messquelle nicht verfügbar",
      idle: "Alles ruhig",
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
      burst_leak: "Rohrbruch – immer aktiv",
    },
    phase: { idle: "Bereit", monitoring: "Prüft", active: "Alarm", off: "Aus", bypass: "Bypass" },
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
    acknowledge_hint: "Stoppt Benachrichtigungen. Alarm und Absperranforderung bleiben bestehen.",
    clear_alarm: "Alarm löschen",
    clear_requires_home: "Nur von zuhause möglich",
    clear_presence_unknown: "Deinem Benutzer ist keine Person zugeordnet – Anwesenheit unbekannt",
    hydraulic_clears_itself: "Endet automatisch, sobald der Durchfluss die Ruhebedingung erfüllt.",
    fallback_opened: "Diese Aktion ist im Backend noch nicht verfügbar – der Konfigurationsdialog wurde geöffnet.",
    action_failed: "Aktion abgelehnt: {msg}",
    flow: "Durchfluss",
    flow_unavailable: "Kein Messwert",
    high: "High",
    burst: "Burst",
    detectors: "Erkennung",
    always_on: "immer aktiv",
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
    },
  },
  en: {
    title: "Water Leak Guard",
    not_found: "No Water Leak Guard instance found. Pick the status entity in the card editor.",
    status: {
      source_unavailable: "Source unavailable",
      idle: "All quiet",
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
      burst_leak: "Pipe failure – always on",
    },
    phase: { idle: "Ready", monitoring: "Checking", active: "Alarm", off: "Off", bypass: "Bypass" },
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
    acknowledge_hint: "Stops notifications. Alarm and shutoff request stay active.",
    clear_alarm: "Clear alarm",
    clear_requires_home: "Only possible from home",
    clear_presence_unknown: "No person is linked to your user – presence unknown",
    hydraulic_clears_itself: "Ends automatically once the flow meets its quiet condition.",
    fallback_opened: "This action is not available in the backend yet – the configuration dialog was opened.",
    action_failed: "Action rejected: {msg}",
    flow: "Flow",
    flow_unavailable: "No reading",
    high: "High",
    burst: "Burst",
    detectors: "Detection",
    always_on: "always on",
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
    },
  },
};

const HYDRAULIC_KINDS = ["slow_leak", "low_flow", "high_flow", "burst_leak"];

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

/** Presence of the logged-in viewer, derived from the person linked to the HA user. */
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
    const parts = ids.map((id) => {
      const s = this._hass.states[id];
      return s ? `${id}:${s.state}:${s.last_updated}` : `${id}:-`;
    });
    const presence = viewerPresence(this._hass);
    parts.push(`p:${presence.known}:${presence.home}`, `l:${lang(this._hass)}`, `a:${this._hass.user?.is_admin}`);
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

  /** Call a proposed backend command; fall back to the Configure dialog if unknown. */
  async _proposed(command, payload) {
    try {
      await this._hass.callWS({ type: command, ...payload });
    } catch (err) {
      if (err && (err.code === "unknown_command" || err.code === "not_found")) {
        fire(this, "hass-notification", { message: translator(this._hass)("fallback_opened") });
        navigate(INTERFACE.fallbackPath);
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
      case "toggle": {
        const entityId = target.dataset.entity;
        const on = this._hass.states[entityId]?.state === "on";
        this._run(`toggle:${entityId}`, () =>
          this._hass.callService("switch", on ? "turn_off" : "turn_on", { entity_id: entityId })
        );
        break;
      }
      case "bypass-start": {
        const minutes = num(target.dataset.minutes);
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
        this._run(`ack:${target.dataset.event}`, async () =>
          this._proposed(INTERFACE.acknowledge, await this._serviceData({ event_id: target.dataset.event }))
        );
        break;
      case "clear": {
        const payload = { event_id: target.dataset.event };
        if (target.dataset.source) payload.source_id = target.dataset.source;
        if (target.dataset.generation) payload.source_generation = target.dataset.generation;
        this._run(`clear:${target.dataset.event}`, async () =>
          this._proposed(INTERFACE.clearAlarm, await this._serviceData(payload))
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
    const alarm = attrs.aggregate_alarm_active ?? this._state(map, "leak_alarm")?.state === "on";
    const shutoff = attrs.aggregate_shutoff_request ?? this._state(map, "shutoff_request")?.state === "on";
    const tone = alarm
      ? "alarm"
      : status.state === "source_unavailable"
        ? "warn"
        : String(status.state).endsWith("_monitoring")
          ? "watch"
          : "ok";

    const sections = [
      this._renderHeader(t, status, tone, alarm, shutoff),
      this._renderBanners(t, status),
      alarm ? this._renderAlarm(t, map, status) : "",
      this._config.show_flow ? this._renderFlow(t, map) : "",
      this._config.show_detectors ? this._renderDetectors(t, map, status) : "",
      this._config.show_bypass ? this._renderBypass(t, map) : "",
      this._config.show_external ? this._renderExternal(t, status) : "",
      this._config.show_learning ? this._renderLearning(t, map) : "",
    ];

    this.shadowRoot.innerHTML = `<style>${STYLES}</style>
      <ha-card class="tone-${tone}">${sections.join("")}</ha-card>`;
  }

  _renderHeader(t, status, tone, alarm, shutoff) {
    const title = this._config.title || t("title");
    const icon = {
      alarm: "mdi:water-alert",
      warn: "mdi:water-off",
      watch: "mdi:water-sync",
      ok: "mdi:water-check",
    }[tone];
    return `
      <header class="head">
        <button class="orb" data-action="more-info" data-entity="${esc(status.entity_id)}" aria-label="${esc(title)}">
          <ha-icon icon="${icon}"></ha-icon>
        </button>
        <div class="head-text">
          <div class="eyebrow">${esc(title)}</div>
          <div class="headline">${esc(t(`status.${status.state}`) || status.state)}</div>
        </div>
        <div class="flags">
          ${alarm ? `<span class="flag flag-alarm"><ha-icon icon="mdi:pipe-leak"></ha-icon>${esc(t("alarm"))}</span>` : ""}
          ${shutoff ? `<span class="flag flag-shutoff"><ha-icon icon="mdi:valve-closed"></ha-icon>${esc(t("shutoff"))}</span>` : ""}
        </div>
      </header>`;
  }

  _renderBanners(t, status) {
    const a = status.attributes || {};
    const out = [];
    if (a.storage_recovery_required) {
      out.push(`<div class="banner banner-alarm"><ha-icon icon="mdi:database-alert"></ha-icon><span>${esc(t("storage_recovery"))}</span></div>`);
    }
    if (status.state === "source_unavailable" || a.source_available === false) {
      out.push(`<div class="banner banner-warn"><ha-icon icon="mdi:access-point-network-off"></ha-icon><span>${esc(t("source_unavailable_banner"))}</span></div>`);
    }
    return out.join("");
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

        let clearHtml;
        if (ev.external) {
          const blocked = !presence.home;
          const reason = !presence.known ? t("clear_presence_unknown") : t("clear_requires_home");
          clearHtml = `
            <button class="btn btn-danger" data-action="clear" data-event="${esc(ev.event_id)}"
              data-source="${esc(ev.source_id)}" data-generation="${esc(ev.source_generation)}"
              ${blocked || this._busy.has(clearKey) ? "disabled" : ""}
              title="${esc(blocked ? reason : t("clear_alarm"))}">
              <ha-icon icon="${blocked ? "mdi:home-lock" : "mdi:broom"}"></ha-icon>${esc(t("clear_alarm"))}
            </button>
            ${blocked ? `<div class="note">${esc(reason)}</div>` : ""}`;
        } else {
          clearHtml = `<div class="note">${esc(t("hydraulic_clears_itself"))}</div>`;
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
            <div class="event-actions">
              ${acked ? "" : `
                <button class="btn btn-primary" data-action="acknowledge" data-event="${esc(ev.event_id)}"
                  ${this._busy.has(ackKey) ? "disabled" : ""} title="${esc(t("acknowledge_hint"))}">
                  <ha-icon icon="mdi:bell-check"></ha-icon>${esc(t("acknowledge"))}
                </button>`}
              ${clearHtml}
            </div>
          </div>`;
      })
      .join("");

    return `<section class="alarm">${rows}<div class="note subtle">${esc(t("acknowledge_hint"))}</div></section>`;
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

  _renderDetectors(t, map, status) {
    const a = status.attributes || {};
    const phases = a.detectors || {};
    const bypass = this._state(map, "high_flow_bypass")?.state === "on";
    const switches = { slow_leak: map.slow_leak_detection, low_flow: map.low_flow_detection };

    const rows = HYDRAULIC_KINDS.map((kind) => {
      const switchId = switches[kind];
      const enabled = switchId ? this._hass.states[switchId]?.state === "on" : true;
      let phase = phases[kind] || "idle";
      if (!enabled) phase = "off";
      else if (kind === "high_flow" && bypass && phase !== "active") phase = "bypass";
      const busy = switchId && this._busy.has(`toggle:${switchId}`);
      const control = switchId
        ? `<button class="switch ${enabled ? "on" : ""}" role="switch" aria-checked="${enabled}"
             aria-label="${esc(t(`detector.${kind}`))}" data-action="toggle" data-entity="${esc(switchId)}" ${busy ? "disabled" : ""}>
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
          <span class="pill pill-${phase}">${esc(t(`phase.${phase}`))}</span>
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
        const phaseClass = s.identity_conflict ? "warn" : s.phase === "ACTIVE" ? "active" : s.phase === "ARMED" ? "idle" : "monitoring";
        const label = s.identity_conflict ? t("external_conflict") : t(`external_phase.${s.phase}`);
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
  .pill-off { background: var(--wlg-soft); color: var(--wlg-muted); }

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
        schema: ["show_flow", "show_detectors", "show_bypass", "show_external", "show_learning"].map(
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

if (!customElements.get(CARD_TAG)) customElements.define(CARD_TAG, WaterLeakGuardCard);
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
