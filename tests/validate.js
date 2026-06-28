const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.resolve(__dirname, "..");
let hasFail = false;
function fail(msg) { console.log("FAIL: " + msg); hasFail = true; }
function ok(msg)   { console.log("OK:   " + msg); }

function syntaxCheck() {
  console.log("");
  console.log("=== 1. SYNTAX CHECK ===");
  const files = [
    ["modules/core.js", "script"],
    ["modules/tools.js", "script"],
    ["modules/conversations.js", "module"],
    ["modules/zeroshot.js", "script"],
    ["modules/agents.js", "module"],
    ["sandpie.js", "script"],
    ["modules/providers.js", "script"],
    ["modules/config.js", "script"],
    ["modules/settings.js", "script"],
  ];
  for (const [f, st] of files) {
    const full = path.join(ROOT, f);
    if (!fs.existsSync(full)) { fail(f + " missing"); continue; }
    try {
      require("acorn").parse(fs.readFileSync(full, "utf-8"), { ecmaVersion: "latest", sourceType: st });
      ok(f + " parses as " + st);
    } catch (e) {
      fail(f + " syntax error: " + (e.message || "").split("\n")[0]);
    }
  }
}

function tdzTools() {
  console.log("");
  console.log("=== 2. TDZ REGRESSION (tools.js) ===");
  const lines = fs.readFileSync(path.join(ROOT, "modules/tools.js"), "utf-8").split("\n");
  const sL = lines.findIndex(l => l.includes("schemas()")) + 1;
  const sfL = lines.findIndex(l => l.includes("schemaFor(name)")) + 1;
  const tdL = lines.findIndex(l => /^const toolDefs\s*=/.test(l)) + 1;
  const exL = lines.findIndex(l => l.includes("window.SandpieTools = SandpieTools")) + 1;
  const safe = sL>0 && sfL>0 && exL>0 && tdL>0 && sL<exL && sfL<exL && tdL>exL;
  if (safe) ok("schemas L" + sL + " < export L" + exL + " < toolDefs L" + tdL + " (TDZ-safe)");
  else fail("TDZ RISK: schemas=" + sL + " schemaFor=" + sfL + " export=" + exL + " toolDefs=" + tdL);
}

function runtimeSanity() {
  console.log("");
  console.log("=== 3. RUNTIME SANITY ===");
  const src = fs.readFileSync(path.join(ROOT, "modules/tools.js"), "utf-8");
  const ctx = { window:{}, localStorage:{getItem:()=>"",setItem:()=>{}}, document:{}, URL:URL, Blob:Blob, JSON:JSON, location:{origin:"http://localhost"} };
  ctx.window.localStorage = ctx.localStorage;
  try {
    vm.createContext(ctx);
    vm.runInContext(src, ctx, { filename: "tools.js", timeout: 1000 });
    if (typeof ctx.window.SandpieTools?.schemas === "function") ok("tools.js eval OK; schemas is function");
    else fail("schemas not a function after eval");
  } catch (e) { fail("tools.js threw: " + (e.message||"").split("\n")[0]); }
}

function htmlRefs() {
  console.log("");
  console.log("=== 4. HTML REFS ===");
  const html = fs.readFileSync(path.join(ROOT, "sandpie.html"), "utf-8");
  const matches = html.match(/<script[^>]*src=["']([^"']+?)(?:\?v=\d+)?["']/g);
  if (!matches) { fail("No script refs"); return; }
  for (const m of matches) {
    const inner = m.match(/src=["']([^"']+)/)[1].split("?v=")[0];
    if (inner.startsWith("http") || inner.startsWith("/")) continue;
    if (fs.existsSync(path.join(ROOT, inner))) ok("sandpie.html -> " + inner);
    else fail("sandpie.html missing: " + inner);
  }
}

function zeroshotDeps() {
  console.log("");
  console.log("=== 5. ZEROSHOT DEPS ===");
  const src = fs.readFileSync(path.join(ROOT, "modules/zeroshot.js"), "utf-8");
  let issues = 0;
  if (!src.includes("window.$(")) { fail("window.$() missing"); issues++; }
  const globals = [
    ["addMsg","conv.js"],["buildToolBox","conv.js"],["renderTcDone","conv.js"],
    ["appendToolResult","conv.js"],["SandpieProviders","providers.js"],
    ["saveActiveConv","conv.js"],["ensureActiveConv","conv.js"],
  ];
  for (const [g, sf] of globals) {
    const count = (src.match(new RegExp("\\b" + g + "\\b", "g")) || []).length;
    if (count > 0 && !src.includes("typeof " + g)) {
      fail(g + " from " + sf + " used " + count + "x unguarded"); issues++;
    }
  }
  if (issues === 0) ok("zeroshot.js guards globals properly");
}

syntaxCheck();
tdzTools();
runtimeSanity();
htmlRefs();
zeroshotDeps();
console.log("");
console.log(hasFail ? "VALIDATION FAILED" : "ALL CHECKS PASSED");
process.exit(hasFail ? 1 : 0);
