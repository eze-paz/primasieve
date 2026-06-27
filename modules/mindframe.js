/**
 * Mindframe Module for Sandpie — a harness-enforced problem-solving frame.
 *
 * A "mindframe" forces the model through an explicit frame before it acts,
 * appended to the system prompt (via the SandpieMindframe.systemBlock hook in
 * conversations.buildSystemPrompt). It works identically across every backend
 * (cloud, WebGPU, LiteRT-LM) because it only shapes the system prompt, and it
 * returns '' when off so there is zero behavior change when disabled.
 *
 * Two parts, kept deliberately small:
 *
 *   STEP 1 — AWARENESS: split the request into NOUNS (things → confidence 1–10 +
 *            definition) and VERBS (actions → an exit check), then classify the
 *            task MODE: RESEARCH (facts), DERIVE (math/logic/code), or MIXED.
 *
 *   STEP 2 — GROUNDING (one rule): never assert; ground. Every claim is tagged
 *            [cite: source] (facts → a real file/URL you can open),
 *            [check: how]  (math/code → something you ran or derived), or
 *            [known]       (common knowledge / a reasoning step).
 *            This is what guards non-research tasks: a computation is PROVEN
 *            with [check], never cited — you don't cite the web for 2+2.
 *
 * Usage: <script type="module" src="modules/mindframe.js?v=2"></script>
 */

/* -------------------------------------------------------------------------- */
/*  config (raw localStorage — same approach as tunnels.js)                    */
/* -------------------------------------------------------------------------- */
const K_ACTIVE    = 'sandpie:mindframe:active';
const K_THRESHOLD = 'sandpie:mindframe:threshold';
const K_GROUNDING = 'sandpie:mindframe:grounding';
const K_SCANONLY  = 'sandpie:mindframe:scanonly';

const DEFAULTS = { active: false, threshold: 6, grounding: true, scanOnly: false };

function getBool(key, def) {
  const v = localStorage.getItem(key);
  return v === null ? def : v === '1';
}
function setBool(key, v) { localStorage.setItem(key, v ? '1' : '0'); }

const cfg = {
  get active()     { return getBool(K_ACTIVE, DEFAULTS.active); },
  set active(v)    { setBool(K_ACTIVE, v); },
  get grounding()  { return getBool(K_GROUNDING, DEFAULTS.grounding); },
  set grounding(v) { setBool(K_GROUNDING, v); },
  get scanOnly()   { return getBool(K_SCANONLY, DEFAULTS.scanOnly); },
  set scanOnly(v)  { setBool(K_SCANONLY, v); },
  get threshold()  {
    const n = parseInt(localStorage.getItem(K_THRESHOLD) || '', 10);
    return Number.isFinite(n) ? Math.min(10, Math.max(1, n)) : DEFAULTS.threshold;
  },
  set threshold(v) { localStorage.setItem(K_THRESHOLD, String(Math.min(10, Math.max(1, v | 0)))); },
};

/* -------------------------------------------------------------------------- */
/*  the directive — this is the "mindframe"                                     */
/* -------------------------------------------------------------------------- */
function buildDirective() {
  const t = cfg.threshold;

  const awareness = `STEP 1 — AWARENESS. Split the user's request into its parts:
- NOUNS (the things it is about): for each, rate 1–10 how sure you are you know what it refers to, and give a one-line definition. Proper names, product/library names, version numbers, acronyms, and anything dated after your training cutoff → score LOW. Do not inflate scores. A noun you cannot define in one clean line is a noun you do not know.
- VERBS (the actions asked of you): for each, state how you would CHECK that it was done correctly (its exit test).
Then classify the task MODE:
- RESEARCH — the answer depends on facts about the world or specific entities (look-up-able)
- DERIVE   — the answer is computed or provable: math, logic, code (NOT look-up-able)
- MIXED    — both

Output exactly:
=== AWARENESS ===
NOUNS:
- "<noun>" — <N>/10 — <one-line definition>
VERBS:
- "<verb>" — check: <how you would verify it is done>
MODE: <RESEARCH | DERIVE | MIXED>
=== END ===`;

  const grounding = `
STEP 2 — GROUNDING (one rule): never assert; ground. Tag EVERY claim in your answer with exactly one of:
- [cite: <full URL or workspace file path>] — a REAL, SPECIFIC source you actually opened: a workspace file (read it with read_file) or a web PAGE you fetched and read (run_python + pyodide \`pyfetch\`). Use for RESEARCH facts. For any noun you scored ${t}/10 or below you MUST fetch the source now — never answer from memory. The citation must be a complete locator that points at the page containing the claim and resolves to content you have actually seen. FORBIDDEN — treated as NO citation at all: a bare domain or homepage with no path (e.g. "example.com"); "via search", "search results", or a search-engine snippet you did not open; a URL you did not actually fetch; or any guessed/invented link. If the best you have is a search hit, OPEN it and cite that page. If you cannot open a real source for a claim, do not assert it — mark it "(unverified)" or say you are unsure.
- [check: <what you ran>] — a verification you ACTUALLY performed: code you executed (run_python), a worked-out derivation, or a test that passed. Use for DERIVE answers. Do NOT cite the web for math or code — PROVE it by running or deriving it. This is how non-research tasks are grounded: with a check, never a citation.
- [known] — textbook common knowledge or a pure reasoning step that needs no source. Use sparingly; it is not an excuse to skip a real [cite] or [check].
If a claim fits none of the three, do not make it — say you are unsure instead.
End your answer with a "Sources" list of every [cite] you used.`;

  const stop = `
STOP after STEP 1. Do NOT answer the request yet — this run checks AWARENESS only. Output the scan and nothing after it.`;

  let body = `

================ MINDFRAME (MANDATORY) ================
Before you answer, plan, or call any tool for the user's LATEST message, work
through this frame. You are not allowed to start the task until STEP 1 is fully
filled in. Skipping it, abbreviating it, or answering first is a failure.

${awareness}`;

  if (cfg.scanOnly) {
    body += `\n${stop}`;
  } else if (cfg.grounding) {
    body += `\n${grounding}`;
  }
  body += `\n=======================================================\n`;
  return body;
}

/* -------------------------------------------------------------------------- */
/*  host hook — appended to the system prompt by conversations.buildSystemPrompt */
/* -------------------------------------------------------------------------- */
window.SandpieMindframe = {
  isActive() { return cfg.active; },
  systemBlock(/* convMessages */) { return cfg.active ? buildDirective() : ''; },
};

/* -------------------------------------------------------------------------- */
/*  sidebar UI                                                                  */
/* -------------------------------------------------------------------------- */
const SECTION_ID = 'mindframeSection';

function badge() { return cfg.active ? 'ON' : 'off'; }

function render() {
  const host = document.getElementById('mindframeBody');
  if (!host) return;
  const on = cfg.active;

  host.innerHTML = `
    <p style="color:var(--sp-text-dim);font-size:0.72rem;line-height:1.4;margin:0 0 0.55rem;">
      Forces a frame before the model acts: <strong>scan</strong> the message into nouns
      (rated 1–10) and verbs, then <strong>ground</strong> every claim — facts get a
      <code>[cite]</code>, math/code get a <code>[check]</code>. You don't cite the web for a
      computation; you prove it.
    </p>

    <button id="mfToggle" style="
      width:100%;display:flex;align-items:center;justify-content:space-between;gap:0.5rem;
      padding:0.45rem 0.6rem;border:1px solid ${on ? 'var(--sp-accent,#3fb950)' : 'var(--sp-border)'};
      border-radius:6px;background:${on ? 'rgba(63,185,80,0.12)' : 'transparent'};
      color:var(--sp-text);cursor:pointer;font-size:0.8rem;">
      <span><strong>Mindframe</strong></span>
      <span style="font-size:0.72rem;color:${on ? '#3fb950' : 'var(--sp-text-dim)'};">
        ${on ? '● ACTIVE' : '○ off'}
      </span>
    </button>

    <div style="margin-top:0.6rem;display:flex;flex-direction:column;gap:0.5rem;${on ? '' : 'opacity:0.45;pointer-events:none;'}">
      <label style="display:flex;align-items:center;gap:0.5rem;font-size:0.74rem;color:var(--sp-text-dim);">
        <span style="white-space:nowrap;">Must fetch source at/below</span>
        <input id="mfThreshold" type="range" min="1" max="10" step="1" value="${cfg.threshold}" style="flex:1;">
        <span id="mfThreshVal" style="min-width:2.4em;text-align:right;color:var(--sp-text);">${cfg.threshold}/10</span>
      </label>

      <label style="display:flex;align-items:center;gap:0.5rem;font-size:0.74rem;color:var(--sp-text-dim);cursor:pointer;">
        <input id="mfGrounding" type="checkbox" ${cfg.grounding ? 'checked' : ''}>
        <span>Require grounding (cite facts, prove computations)</span>
      </label>

      <label style="display:flex;align-items:center;gap:0.5rem;font-size:0.74rem;color:var(--sp-text-dim);cursor:pointer;">
        <input id="mfScanOnly" type="checkbox" ${cfg.scanOnly ? 'checked' : ''}>
        <span>Scan only — stop after awareness (don't answer)</span>
      </label>
    </div>
  `;

  document.getElementById('mfToggle').onclick = () => {
    cfg.active = !cfg.active;
    SandpieMenu.updateBadge(SECTION_ID, badge());
    render();
  };

  const slider = document.getElementById('mfThreshold');
  if (slider) slider.oninput = (e) => {
    cfg.threshold = parseInt(e.target.value, 10);
    document.getElementById('mfThreshVal').textContent = cfg.threshold + '/10';
  };

  const g = document.getElementById('mfGrounding');
  if (g) g.onchange = (e) => { cfg.grounding = e.target.checked; };

  const s = document.getElementById('mfScanOnly');
  if (s) s.onchange = (e) => { cfg.scanOnly = e.target.checked; };
}

/* -------------------------------------------------------------------------- */
/*  init                                                                        */
/* -------------------------------------------------------------------------- */
function init() {
  if (typeof SandpieMenu === 'undefined') { setTimeout(init, 500); return; }
  SandpieMenu.add(SECTION_ID, {
    title: 'Mindframe',
    badge: badge(),
    open: false,
    html: '<div id="mindframeBody" style="font-size:0.75rem;line-height:1.4;"></div>',
    onRender() { render(); },
  });
  console.log('[mindframe] module registered (active=' + cfg.active + ')');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
