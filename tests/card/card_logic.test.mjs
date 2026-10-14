/*
 * Dependency-free logic tests for the dashboard card (run in CI with plain Node:
 * `node tests/card/card_logic.test.mjs`). A minimal DOM shim loads the real card
 * file; rendering is checked on the generated HTML string, actions through the
 * card's own click handler with fake targets. No browser, no npm packages.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const CARD = path.join(here, "../../custom_components/water_leak_detection/frontend/water-leak-guard-card.js");

/* ------------------------------------------------------------------ DOM shim */
class ShadowRoot {
  constructor() { this.innerHTML = ""; this.activeElement = null; }
  addEventListener() {}
  querySelectorAll() { return []; }
}
class HTMLElement {
  attachShadow() { this.shadowRoot = new ShadowRoot(); return this.shadowRoot; }
  get isConnected() { return Boolean(this.__connected); }
  dispatchEvent(ev) { (globalThis.__events ||= []).push(ev); return true; }
  appendChild() {}
}
const registry = new Map();
globalThis.HTMLElement = HTMLElement;
globalThis.customElements = { get: (n) => registry.get(n), define: (n, c) => registry.set(n, c) };
globalThis.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init?.detail; } };
globalThis.window = globalThis;
globalThis.document = { addEventListener() {}, removeEventListener() {}, visibilityState: "visible", createElement: () => ({}) };
const info = console.info;
console.info = () => {};
vm.runInThisContext(fs.readFileSync(CARD, "utf8"), { filename: CARD });
console.info = info;
const Card = customElements.get("water-leak-guard-card");
assert.ok(Card, "card registered");

/* ------------------------------------------------------------------ mock hass */
const K = {
  status: "sensor.s", leak_alarm: "binary_sensor.a", shutoff_request: "binary_sensor.o",
  hydraulic_monitoring_status: "sensor.m", current_flow: "sensor.f",
  effective_high_threshold: "sensor.h", effective_burst_threshold: "sensor.b",
  slow_leak_detection: "switch.slow", low_flow_detection: "switch.low",
  high_flow_bypass: "switch.bypass", high_flow_bypass_duration: "number.bypass_duration",
  learning_confidence: "sensor.conf", learning_coverage: "sensor.cov",
};
const SWITCHES = [K.slow_leak_detection, K.low_flow_detection, K.high_flow_bypass, K.high_flow_bypass_duration];
const HOME = { paired: true, recipient_id: "phone", recipient_name: "Bea", home: true, tracker_entity: "device_tracker.phone", can_global_ack: true, can_external_reset: true };

function hass({ alarm, monitoring = "active", tracker = "home", session = HOME, confidence = "reliable", lang = "de", statusState, storage = false, sourceAvailable, externalOffline = false } = {}) {
  const st = (id, state, attributes = {}) => [id, { entity_id: id, state, attributes, last_updated: "x" }];
  const detectors = { slow_leak: "idle", low_flow: "idle", high_flow: "idle", burst_leak: "idle" };
  const hydraulic = {};
  const notif = {};
  if (alarm) {
    detectors[alarm] = "active";
    hydraulic[alarm] = { phase: "active", event_id: `ev_${alarm}` };
    notif[`ev_${alarm}`] = { globally_acknowledged: false, muted_recipients: [] };
  }
  const states = Object.fromEntries([
    st(K.status, statusState || alarm || "idle", {
      aggregate_alarm_active: Boolean(alarm), aggregate_shutoff_request: Boolean(alarm), active_detector: alarm,
      active_event_id: alarm ? `ev_${alarm}` : null, detectors, hydraulic_detectors: hydraulic, notification_events: notif,
      storage_recovery_required: storage, ...(sourceAvailable === undefined ? {} : { source_available: sourceAvailable }),
      external_sources: externalOffline ? [{ source_id: "x", source_generation: "g", source_name: "Keller", source_entity: "binary_sensor.cellar", phase: "ARMED" }] : [],
    }),
    st(K.leak_alarm, alarm ? "on" : "off"), st(K.shutoff_request, alarm ? "on" : "off"),
    ...(monitoring === "missing" ? [] : [st(K.hydraulic_monitoring_status, monitoring)]), st(K.current_flow, "0"),
    st(K.effective_high_threshold, "1200"), st(K.effective_burst_threshold, "3500"),
    st(K.slow_leak_detection, "on"), st(K.low_flow_detection, "on"), st(K.high_flow_bypass, "off"),
    st(K.high_flow_bypass_duration, "90"), st(K.learning_confidence, confidence, { sample_count: 10 }),
    st(K.learning_coverage, "30", { window_days: 30 }), st("device_tracker.phone", tracker),
  ]);
  const entities = Object.fromEntries(Object.entries(K).filter(([key]) => !(monitoring === "missing" && key === "hydraulic_monitoring_status")).map(([key, id]) => [id, { entity_id: id, platform: "water_leak_detection", translation_key: key, device_id: "d" }]));
  const calls = [];
  return {
    language: lang, locale: { language: lang }, user: { is_admin: true }, states, entities, devices: { d: { name: "WLG" } }, calls,
    callWS: async (msg) => { calls.push({ ws: msg.type }); if (msg.type.endsWith("/session")) return session; if (msg.type.endsWith("entity_registry/get")) return { config_entry_id: "e" }; return {}; },
    callService: async (domain, service, data) => { calls.push({ service: `${domain}.${service}`, data }); },
  };
}

async function mount(opts = {}, config = {}) {
  const card = new Card();
  card.setConfig({ type: "custom:water-leak-guard-card", entity: K.status, ...config });
  card.hass = hass(opts);
  card.__connected = true;
  card.connectedCallback();
  await new Promise((r) => setTimeout(r, 0)); // session answer
  await new Promise((r) => setTimeout(r, 0));
  return card;
}
const html = (card) => card.shadowRoot.innerHTML.replace(/<style>[\s\S]*?<\/style>/, ""); // markup only
const target = (dataset, disabled = false) => ({ closest: () => ({ dataset, hasAttribute: (a) => a === "disabled" && disabled }) });
/** Opening tag of the first button with this data-action (attributes only). */
const tag = (h, action) => {
  const i = h.indexOf(`data-action="${action}"`);
  assert.ok(i >= 0, `${action} rendered`);
  return h.slice(h.lastIndexOf("<button", i), h.indexOf(">", i));
};
const services = (card) => card._hass.calls.filter((c) => c.service);
let confirmAnswer = true;
const confirms = [];
globalThis.confirm = (msg) => { confirms.push(msg); return confirmAnswer; };

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

/* ------------------------------------------------------------------ tests */
test("idle: no switch controls, no links to switch entities", async () => {
  const card = await mount();
  const h = html(card);
  assert.ok(!/role="switch"|ha-switch|data-action="toggle"|data-action="disable-detection"/.test(h));
  for (const id of SWITCHES) assert.ok(!h.includes(`data-entity="${id}"`), id);
  assert.match(h, /class="tiles"/);
  assert.ok(!/class="tile[^"]*"[^>]*data-action/.test(h), "tiles not clickable");
  card.disconnectedCallback();
});

const expandedOf = (h, key) => h.match(new RegExp(`data-section="${key}"[^>]*aria-expanded="(true|false)"`))?.[1];

test("sections: expanded by default; toggle survives hass updates", async () => {
  const card = await mount();
  assert.equal(expandedOf(html(card), "bypass"), "true");
  assert.equal(expandedOf(html(card), "learning"), "true");
  assert.equal((html(card).match(/class="sec-body"/g) || []).length, 2);
  card._onClick({ target: target({ action: "toggle-section", section: "learning" }) });
  assert.equal(expandedOf(html(card), "learning"), "false");
  card.hass = { ...hass(), states: { ...hass().states, [K.current_flow]: { entity_id: K.current_flow, state: "12", attributes: {}, last_updated: "y" } } };
  assert.equal(expandedOf(html(card), "learning"), "false", "toggle kept after hass update");
  assert.equal(expandedOf(html(card), "bypass"), "true");
  // Re-applying the same config (e.g. an unrelated editor change) keeps the toggles.
  card.setConfig({ type: "custom:water-leak-guard-card", entity: K.status, title: "X" });
  assert.equal(expandedOf(html(card), "learning"), "false");
  card.disconnectedCallback();
});

test("sections: collapsed: true starts collapsed; changing the option resets to its default", async () => {
  const card = await mount({}, { collapsed: true });
  assert.equal(expandedOf(html(card), "bypass"), "false");
  assert.equal(expandedOf(html(card), "learning"), "false");
  assert.ok(!html(card).includes('class="sec-body"'));
  card._onClick({ target: target({ action: "toggle-section", section: "bypass" }) });
  assert.equal(expandedOf(html(card), "bypass"), "true");
  card.hass = hass();
  assert.equal(expandedOf(html(card), "bypass"), "true", "toggle kept after hass update");
  card.setConfig({ type: "custom:water-leak-guard-card", entity: K.status, collapsed: false });
  assert.equal(expandedOf(html(card), "bypass"), "true");
  assert.equal(expandedOf(html(card), "learning"), "true");
  card.setConfig({ type: "custom:water-leak-guard-card", entity: K.status, collapsed: true });
  assert.equal(expandedOf(html(card), "bypass"), "false");
  assert.equal(expandedOf(html(card), "learning"), "false");
  card.disconnectedCallback();
});

test("editor offers the collapsed option with DE/EN labels", async () => {
  const Editor = customElements.get("water-leak-guard-card-editor");
  const editor = new Editor();
  editor._hass = hass();
  const grid = editor._schema().find((f) => f.type === "grid");
  assert.ok(grid.schema.some((f) => f.name === "collapsed" && f.selector.boolean));
});

const DISPLAY = { paired: true, kind: "display", recipient_id: "wall", recipient_name: "Flur", home: true, tracker_entity: null, can_mute: false, can_global_ack: true, can_external_reset: true };

test("display session: no mute, home actions available, never 'only at home'", async () => {
  for (const alarm of ["burst_leak", "low_flow", "high_flow"]) {
    // The phone tracker is away; a display has no tracker and is always home.
    const card = await mount({ alarm, tracker: "not_home", session: DISPLAY });
    const h = html(card);
    assert.ok(!h.includes('data-action="mute"') && !h.includes("stummgeschaltet"), `${alarm}: no mute`);
    assert.equal(tag(h, "acknowledge").includes(" disabled"), false, `${alarm}: ack enabled`);
    assert.ok(!h.includes("Nur zuhause möglich"), `${alarm}: no home hint`);
    if (alarm === "low_flow") assert.equal(tag(h, "disable-detection").includes(" disabled"), false);
    if (alarm === "high_flow") assert.equal(tag(h, "bypass-start").includes(" disabled"), false);
    card.disconnectedCallback();
  }
  // Without the acknowledge permission there is no acknowledge button.
  const card = await mount({ alarm: "burst_leak", session: { ...DISPLAY, can_global_ack: false } });
  assert.ok(!html(card).includes('data-action="acknowledge"'));
  card.disconnectedCallback();
});

test("mute is hidden by either signal: kind display or can_mute false", async () => {
  for (const session of [{ ...HOME, kind: "display" }, { ...HOME, can_mute: false }]) {
    const card = await mount({ alarm: "burst_leak", session });
    assert.ok(!html(card).includes('data-action="mute"'), JSON.stringify(session));
    card.disconnectedCallback();
  }
  const card = await mount({ alarm: "burst_leak", session: { ...HOME, kind: "mobile", can_mute: true } });
  assert.ok(html(card).includes('data-action="mute"'));
  card.disconnectedCallback();
});

test("mute_not_applicable has a localized message", async () => {
  const card = await mount();
  const t = (k) => card._errorText((key) => ({ "error.mute_not_applicable": "X" })[key] ?? key, { code: k });
  assert.equal(t("mute_not_applicable"), "X");
  card.disconnectedCallback();
});

const PILL = 'class="pill pill-ok mon-ok"';
const headline = (h) => h.match(/class="headline">([^<]*)</)?.[1];
const toneOf = (h) => h.match(/<ha-card class="tone-(\w+)"/)?.[1];

test("hydraulics pill: one positive case (flow row, and header without flow)", async () => {
  let card = await mount();
  assert.ok(html(card).includes(PILL) && html(card).includes("Hydraulik aktiv"));
  assert.ok(!html(card).includes('class="monitor '), "no separate row");
  assert.equal(toneOf(html(card)), "ok");
  card.disconnectedCallback();
  card = await mount({}, { show_flow: false });
  assert.match(html(card), /class="flags">[^]*mon-ok/);
  card.disconnectedCallback();
});

const NO_PILL = {
  storage_recovery_required: { storage: true },
  source_unavailable: { statusState: "source_unavailable" },
  "source_available false": { sourceAvailable: false },
  "status unavailable": { statusState: "unavailable" },
  "status unknown": { statusState: "unknown" },
  "monitoring blocked": { monitoring: "blocked" },
  "monitoring waiting": { monitoring: "waiting_for_measurement" },
  "monitoring unavailable": { monitoring: "unavailable" },
  "monitoring unknown": { monitoring: "unknown" },
  "monitoring missing": { monitoring: "missing" },
  "external sensor offline": { externalOffline: true },
};
for (const [name, opts] of Object.entries(NO_PILL)) {
  for (const show_flow of [true, false]) {
    test(`no green hydraulics pill: ${name} (show_flow ${show_flow})`, async () => {
      const card = await mount(opts, { show_flow });
      const h = html(card);
      assert.ok(!h.includes("mon-ok"), "pill rendered");
      assert.notEqual(toneOf(h), "ok", "card is green");
      assert.ok(!["Alles ruhig"].includes(headline(h)), `headline ${headline(h)}`);
      card.disconnectedCallback();
    });
  }
}

test("impaired monitoring: warn tone and 'Überwachung eingeschränkt', alarm keeps priority", async () => {
  for (const opts of [{ storage: true }, { statusState: "source_unavailable" }, { sourceAvailable: false }]) {
    let card = await mount(opts);
    assert.equal(toneOf(html(card)), "warn", JSON.stringify(opts));
    assert.equal(headline(html(card)), "Überwachung eingeschränkt", JSON.stringify(opts));
    card.disconnectedCallback();
    card = await mount({ ...opts, lang: "en" });
    assert.equal(headline(html(card)), "Monitoring impaired");
    card.disconnectedCallback();
    card = await mount({ ...opts, alarm: "low_flow" });
    assert.equal(toneOf(html(card)), "alarm");
    assert.equal(headline(html(card)), "Low Flow");
    card.disconnectedCallback();
  }
  // Storage recovery with an alarm of unknown kind keeps the generic alarm headline.
  const card = await mount({ storage: true });
  card._hass.states[K.status].attributes.aggregate_alarm_active = true;
  card._signature = "";
  card._render();
  assert.equal(headline(html(card)), "Leckalarm");
  card.disconnectedCallback();
});

test("_monitoringOk guards each input on its own (defense in depth)", async () => {
  const card = await mount();
  const okStatus = { state: "idle", attributes: {} };
  const okMon = { state: "active", entity: { state: "active" } };
  assert.equal(card._monitoringOk(okMon, okStatus), true);
  assert.equal(card._monitoringOk(okMon, undefined), false, "status missing");
  assert.equal(card._monitoringOk(okMon, { state: "unavailable", attributes: {} }), false, "status unavailable");
  assert.equal(card._monitoringOk({ state: "active", entity: undefined }, okStatus), false, "monitoring entity missing");
  assert.equal(card._monitoringOk({ state: "active", entity: { state: "unavailable" } }, okStatus), false, "monitoring entity unavailable");
  assert.equal(card._monitoringOk({ state: "active", entity: { state: "unknown" } }, okStatus), false, "monitoring entity unknown");
  assert.equal(card._monitoringOk(okMon, okStatus, true), false, "external offline");
  card.disconnectedCallback();
});

const section = (h, cls) => h.split(`class="${cls}`)[1]?.split("</section>")[0] ?? "";
const tilePills = (h) => [...section(h, "block detectors").matchAll(/class="pill pill-(\w+)">([^<]*)</g)].map((m) => `${m[1]}:${m[2]}`);

for (const [name, opts] of Object.entries({ storage_recovery_required: { storage: true }, source_unavailable: { statusState: "source_unavailable" }, "source_available false": { sourceAvailable: false } })) {
  test(`impaired (${name}): row shows warning "Eingeschränkt", tiles paused, never green`, async () => {
    let card = await mount(opts);
    const row = section(html(card), "monitor ");
    assert.ok(row, "full monitoring row rendered");
    assert.match(row, /class="pill pill-warn">Eingeschränkt</);
    assert.ok(!row.includes("pill-ok"), "row not green");
    assert.deepEqual(tilePills(html(card)), ["paused:Pausiert", "paused:Pausiert", "paused:Pausiert", "paused:Pausiert"]);
    // The tooltip names the reason: damaged store vs. no valid measurement.
    const tips = [...section(html(card), "block detectors").matchAll(/class="tile [^"]*" title="([^"]*)"/g)].map((m) => m[1]);
    const expected = opts.storage ? "Laufzeitspeicher beschädigt" : "Ohne gültige Messung wird nicht ausgewertet";
    assert.ok(tips.length === 4 && tips.every((tip) => tip.includes(expected)), tips.join(" | "));
    card.disconnectedCallback();
    card = await mount({ ...opts, lang: "en" });
    assert.match(section(html(card), "monitor "), /class="pill pill-warn">Impaired</);
    card.disconnectedCallback();
    // An active alarm stays an alarm on its tile.
    card = await mount({ ...opts, alarm: "low_flow" });
    const pills = tilePills(html(card));
    assert.equal(pills[1], "active:Alarm");
    assert.ok(pills.every((p) => !p.startsWith("idle") && !p.startsWith("ok")), pills.join(","));
    card.disconnectedCallback();
  });
}

test("healthy active monitoring with the full row (external sensor offline): green Aktiv, tiles Bereit", async () => {
  const card = await mount({ externalOffline: true });
  assert.match(section(html(card), "monitor "), /class="pill pill-ok">Aktiv</);
  assert.deepEqual(tilePills(html(card)), ["idle:Bereit", "idle:Bereit", "idle:Bereit", "idle:Bereit"]);
  card.disconnectedCallback();
});

test("full monitoring row whenever the pill is not shown", async () => {
  for (const monitoring of ["blocked", "waiting_for_measurement"]) {
    const card = await mount({ monitoring });
    assert.ok(html(card).includes('class="monitor '), monitoring);
    card.disconnectedCallback();
  }
});

test("disable detection: only during the detector's alarm, only paired and at home", async () => {
  let card = await mount({ alarm: "low_flow" });
  assert.equal(tag(html(card), "disable-detection").includes(" disabled"), false);
  confirmAnswer = true;
  confirms.length = 0;
  card._onClick({ target: target({ action: "disable-detection", kind: "low_flow" }) });
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(confirms.length, 1);
  assert.deepEqual(services(card), [{ service: "switch.turn_off", data: { entity_id: K.low_flow_detection } }]);
  card.disconnectedCallback();

  card = await mount({ alarm: "low_flow", tracker: "not_home", session: { ...HOME, home: false } });
  assert.equal(tag(html(card), "disable-detection").includes(" disabled"), true);
  confirms.length = 0;
  card._onClick({ target: target({ action: "disable-detection", kind: "low_flow" }) }); // forced click
  assert.equal(confirms.length, 0);
  assert.equal(services(card).length, 0);
  card.disconnectedCallback();

  card = await mount({ alarm: "low_flow", session: { paired: false } });
  assert.ok(!html(card).includes("disable-detection"));
  card.disconnectedCallback();

  card = await mount({ alarm: "burst_leak" });
  assert.ok(!html(card).includes("disable-detection"), "never for Burst Leak");
  card.disconnectedCallback();
});

test("bypass start during High Flow alarm needs canClear and confirmation", async () => {
  let card = await mount({ alarm: "high_flow", tracker: "not_home", session: { ...HOME, home: false } });
  confirms.length = 0;
  card._onClick({ target: target({ action: "bypass-start" }) });
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(confirms.length, 0);
  assert.equal(services(card).length, 0);
  card.disconnectedCallback();

  card = await mount({ alarm: "high_flow" });
  confirmAnswer = false;
  card._onClick({ target: target({ action: "bypass-start" }) });
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(services(card).length, 0);
  confirmAnswer = true;
  card._onClick({ target: target({ action: "bypass-start" }) });
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(services(card)[0]?.service, "water_leak_detection.start_high_flow_bypass");
  card.disconnectedCallback();

  // Without an alarm presets need neither pairing nor confirmation.
  card = await mount({ session: { paired: false } });
  confirms.length = 0;
  card._onClick({ target: target({ action: "bypass-start", minutes: "60" }) });
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(confirms.length, 0);
  assert.equal(services(card)[0]?.data?.duration_minutes, 60);
  card.disconnectedCallback();
});

test("more-info guard blocks detector switches always, bypass during High Flow", async () => {
  globalThis.__events = [];
  let card = await mount();
  for (const id of [K.slow_leak_detection, K.low_flow_detection]) card._onClick({ target: target({ action: "more-info", entity: id }) });
  card._onClick({ target: target({ action: "more-info", entity: K.current_flow }) });
  assert.deepEqual(globalThis.__events.filter((e) => e.type === "hass-more-info").map((e) => e.detail.entityId), [K.current_flow]);
  card.disconnectedCallback();
  globalThis.__events = [];
  card = await mount({ alarm: "high_flow" });
  card._onClick({ target: target({ action: "more-info", entity: K.high_flow_bypass }) });
  assert.equal(globalThis.__events.filter((e) => e.type === "hass-more-info").length, 0);
  card.disconnectedCallback();
});

test("mute names the paired recipient, escaped, with fallback", async () => {
  let card = await mount({ alarm: "burst_leak" });
  assert.match(html(card), /Für Bea stummschalten/);
  card.disconnectedCallback();
  card = await mount({ alarm: "burst_leak", lang: "en", session: { ...HOME, recipient_name: "<i>x</i>" } });
  assert.match(html(card), /Mute for &lt;i&gt;x&lt;\/i&gt;/);
  assert.ok(!html(card).includes("<i>x</i>"));
  card.disconnectedCallback();
  card = await mount({ alarm: "burst_leak", session: { ...HOME, recipient_name: undefined } });
  assert.match(html(card), /Für dieses Gerät stummschalten/);
  card.disconnectedCallback();
});

test("learning: only a reliable model is green", async () => {
  for (const [confidence, cls] of [["insufficient", "pill-off"], ["learning", "pill-monitoring"], ["reliable", "pill-ok"], ["unavailable", "pill-unknown"]]) {
    const card = await mount({ confidence });
    const sum = html(card).split('class="block coll learning"')[1];
    assert.ok(sum.includes(`pill ${cls}`), `${confidence} -> ${cls}`);
    card.disconnectedCallback();
  }
});

let failed = 0;
for (const [name, fn] of tests) {
  try {
    await fn();
    console.log(`ok - ${name}`);
  } catch (err) {
    failed += 1;
    console.log(`not ok - ${name}\n${err.stack}`);
  }
}
console.log(`${tests.length - failed}/${tests.length} card logic tests passed`);
process.exit(failed ? 1 : 0);
