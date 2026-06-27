/**
 * Mindframe Module for Sandpie — Stage 0: AWARENESS.
 *
 * A "mindframe" forces the model through an explicit problem-solving frame
 * before it acts. This module ships ONLY Stage 0 — the AWARENESS scan — so we
 * can test, in isolation, how well large vs small models ground themselves
 * before answering.
 *
 * When active, a directive is appended to the system prompt (via the
 * SandpieMindframe.systemBlock hook in conversations.buildSystemPrompt). The
 * directive forces the model to first split the user's message into:
 *   - NOUNS  (the things the task is about)  → rate confidence 1–10, define each
 *   - VERBS  (the actions being asked for)   → state capability + an exit check
 * and to research (or at minimum flag) every noun scored at/below a threshold.
 *
 * Enforcement is prompt-level: it works identically across every backend
 * (cloud, WebGPU, LiteRT-LM) because it only shapes the system prompt. Whether a
 * given model actually obeys is exactly the thing we want to observe.
 *
 * Usage: <script type="module" src="modules/mindframe.js?v=1"></script>
 */

/* -------------------------------------------------------------------------- */
/*  config (raw localStorage — same approach as tunnels.js)                    */
/* -------------------------------------------------------------------------- */
const K_ACTIVE    = 'sandpie:mindframe:active';
const K_THRESHOLD = 'sandpie:mindframe:threshold';
const K_RESEARCH  = 'sandpie:mindframe:research';
const K_SCANONLY  = 'sandpie:mindframe:scanonly';

const DEFAULTS = { active: false, threshold: 6, research: true, scanOnly: true };

function getBool(key, def) {
  const v = localStorage.getItem(key);
  return v === null ? def : v === '1';
}
function setBool(key, v) { localStorage.setItem(key, v ? '1' : '0'); }

const cfg = {
  get active()    { return getBool(K_ACTIVE, DEFAULTS.active); },
  set active(v)   { setBool(K_ACTIVE, v); },
  get research()  { return getBool(K_RESEARCH, DEFAULTS.research); },
  set research(v) { setBool(K_RESEARCH, v); },
  get scanOnly()  { return getBool(K_SCANONLY, DEFAULTS.scanOnly); },
  set scanOnly(v) { setBool(K_SCANONLY, v); },
  get threshold() {
    const n = parseInt(localStorage.getItem(K_THRESHOLD) || '', 10);
    return Number.isFinite(n) ? Math.min(10, Math.max(1, n)) : DEFAULTS.threshold;
  },
  set threshold(v) { localStorage.setItem(K_THRESHOLD, String(Math.min(10, Math.max(1, v | 0)))); },
};

/* -------------------------------------------------------------------------- */
/*  the directive (Stage 0: AWARENESS) — this is the "mindframe"               */
/* -------------------------------------------------------------------------- */
function buildDirective() {
  const t = cfg.threshold;

  const researchClause = cfg.research
    ? `You MUST research every UNKNOWN noun before you continue. Use the tools available to you — e.g. run_python with pyodide's \`pyfetch\` to fetch a reference page (Wikipedia, docs, the project's own files via read_file/search) — find out what the term actually refers to, then revise its score. If you genuinely have no tool that can look a term up, say so explicitly on that line instead of guessing.`
    : `Flag every UNKNOWN noun clearly (mark it RESEARCH) so the user can see exactly what you are unsure of. Do not silently guess.`;

  const stopClause = cfg.scanOnly
    ? `STOP after the scan. Do NOT answer the request yet — this run is an awareness check only. Output the scan and nothing after it.`
    : `Then proceed to address the request, using what the scan revealed (a low-confidence noun means you do the lookup first; the verbs and their checks become your plan).`;

  return `

================ MINDFRAME · STAGE 0: AWARENESS (MANDATORY) ================
Before you answer, plan, or call any tool for the user's LATEST message, you must
run an AWARENESS SCAN. You are not allowed to leave this stage until the rubric
below is fully filled in. Skipping it, abbreviating it, or starting the task
first is a failure.

Every request is made of THINGS and ACTIONS, so the scan has two columns:

1. NOUNS — the things the request is about. For each noun, rate 1–10 how sure you
   are you actually know what it refers to, and write the one-line definition you
   would use. A noun you cannot define cleanly in one line is a noun you do not
   know — score it low. Treat proper names, product/library names, version
   numbers, acronyms, and anything dated after your training cutoff as low
   confidence by default. Do not inflate scores.

2. VERBS — the actions you are being asked to perform. For each, state whether you
   have the capability/tools to do it, and how you would CHECK that the action was
   done correctly (its exit test).

A noun scored ${t}/10 or below is UNKNOWN. ${researchClause}

Output the scan in EXACTLY this format:

=== AWARENESS SCAN ===
NOUNS:
- "<noun>" — <N>/10 — <one-line definition>
VERBS:
- "<verb>" — capable: <yes/no> — check: <how you would verify it is done>
UNKNOWN (<=${t}/10): <comma-separated nouns, or "none">
=== END SCAN ===

${stopClause}
===========================================================================
`;
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
      Forces the model to scan your message into <strong>nouns</strong> (rated 1–10 for
      confidence) and <strong>verbs</strong> (with an exit check) before it acts.
      Stage 0 of the mindframe loop — run on its own to see how a model grounds itself.
    </p>

    <button id="mfToggle" style="
      width:100%;display:flex;align-items:center;justify-content:space-between;gap:0.5rem;
      padding:0.45rem 0.6rem;border:1px solid ${on ? 'var(--sp-accent,#3fb950)' : 'var(--sp-border)'};
      border-radius:6px;background:${on ? 'rgba(63,185,80,0.12)' : 'transparent'};
      color:var(--sp-text);cursor:pointer;font-size:0.8rem;">
      <span><strong>Awareness scan</strong></span>
      <span style="font-size:0.72rem;color:${on ? '#3fb950' : 'var(--sp-text-dim)'};">
        ${on ? '● ACTIVE' : '○ off'}
      </span>
    </button>

    <div style="margin-top:0.6rem;display:flex;flex-direction:column;gap:0.5rem;${on ? '' : 'opacity:0.45;pointer-events:none;'}">
      <label style="display:flex;align-items:center;gap:0.5rem;font-size:0.74rem;color:var(--sp-text-dim);">
        <span style="white-space:nowrap;">Unknown at/below</span>
        <input id="mfThreshold" type="range" min="1" max="10" step="1" value="${cfg.threshold}" style="flex:1;">
        <span id="mfThreshVal" style="min-width:2.4em;text-align:right;color:var(--sp-text);">${cfg.threshold}/10</span>
      </label>

      <label style="display:flex;align-items:center;gap:0.5rem;font-size:0.74rem;color:var(--sp-text-dim);cursor:pointer;">
        <input id="mfResearch" type="checkbox" ${cfg.research ? 'checked' : ''}>
        <span>Force research on unknown nouns (else just flag them)</span>
      </label>

      <label style="display:flex;align-items:center;gap:0.5rem;font-size:0.74rem;color:var(--sp-text-dim);cursor:pointer;">
        <input id="mfScanOnly" type="checkbox" ${cfg.scanOnly ? 'checked' : ''}>
        <span>Scan only — stop after the scan (don't answer)</span>
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

  const r = document.getElementById('mfResearch');
  if (r) r.onchange = (e) => { cfg.research = e.target.checked; };

  const s = document.getElementById('mfScanOnly');
  if (s) s.onchange = (e) => { cfg.scanOnly = e.target.checked; };
}

/* -------------------------------------------------------------------------- */
/*  init                                                                        */
/* -------------------------------------------------------------------------- */
function init() {
  if (typeof SandpieMenu === 'undefined') { setTimeout(init, 500); return; }
  SandpieMenu.add(SECTION_ID, {
    title: '🧠 Mindframe',
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
