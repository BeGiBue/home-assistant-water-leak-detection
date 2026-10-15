/*
 * Runs the generated Lovelace loader resource (argv[2]: its JavaScript source) in
 * a fake page and prints what it imported, as JSON. Used by
 * tests/test_card_registration.py. `import(` is mapped to a recorder, timers run
 * instantly in order.
 */
import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync(process.argv[2], "utf8").replace("import(u.href)", "__import(u.href)");

async function scenario({ definedWithinGrace = false, running = false, failures = Infinity }) {
  const imports = [];
  const timers = [];
  let defined = false;
  let resolveDefined;
  const whenDefined = new Promise((r) => { resolveDefined = r; });
  const context = {
    URL,
    location: { origin: "http://ha.local:8123" },
    document: { querySelector: () => ({ hass: { config: { state: running ? "RUNNING" : "NOT_RUNNING" } } }) },
    customElements: { get: () => (defined ? class {} : undefined), whenDefined: () => whenDefined },
    setTimeout: (fn, ms) => timers.push({ fn, ms }),
    Promise,
    Math,
    String,
    __import: (url) => {
      imports.push(url);
      if (imports.length > failures) { defined = true; return Promise.resolve({}); }
      return Promise.reject(new Error("404"));
    },
  };
  vm.runInNewContext(source, context);
  if (definedWithinGrace) { defined = true; resolveDefined(); }
  const delays = [];
  for (let i = 0; i < 100; i++) {
    await new Promise((r) => setImmediate(r));
    const next = timers.shift();
    if (!next) break;
    delays.push(next.ms);
    next.fn();
  }
  await new Promise((r) => setImmediate(r));
  return { imports, delays };
}

console.log(JSON.stringify({
  defined_within_grace: await scenario({ definedWithinGrace: true }),
  served_after_two_failures: await scenario({ failures: 2 }),
  files_missing_ha_running: await scenario({ running: true }),
  files_missing_ha_starting: await scenario({ running: false }),
}));
