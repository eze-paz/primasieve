/**
 * Loop Lab — a sandboxed playground for building and testing harness loops
 * (small-model agent loops with systematized scratchpads) inside sandpie.
 *
 * DESIGN: zero blast radius.
 *   - Does NOT intercept handleSubmit, does NOT write to conversations/streams,
 *     does NOT touch Dropbox sync. Runs entirely in its own overlay panel.
 *   - READS shared services only: SandpieProviders.getActive() (which model),
 *     SandpieTools.schemas() (tool defs), window._sandpieWorker (per-tool RPC),
 *     SandpieQwen3/SandpieLiteRTLM.runConversation (local single-shot calls).
 *   - Own storage: localStorage 'sandpie:looplab:*' only.
 *
 * A loop is a JSON spec executed turn by turn:
 *   { name, maxTurns, scratchpad: {...initial...}, stopWhen: "<js expr>",
 *     stages: [
 *       { name, type: "llm",  system, user, parse: "text"|"json"|"block:TAG",
 *         temperature?, maxTokens?, saveAs?, mergeScratchpad? },
 *       { name, type: "tool", argsFrom: "<var>", saveAs? },
 *       { name, type: "js",   code: "<body of function(ctx)>" },
 *       { name, type: "foreach", items: "<js expr over vars/scratchpad returning array>",
 *         stage: {<inner llm|tool|js stage>}, saveAs? },
 *     ] }
 *
 * foreach runs its inner stage once per item; inner templates additionally see
 * ${item} and ${itemIndex}; outer saveAs collects the per-item results array.
 *
 * Any top-level stage may carry when: "<js expr over vars/scratchpad/turn>" —
 * falsy skips the stage for this turn (e.g. frame-once, act-only-if-picked).
 *
 * Template variables in system/user strings: ${task} ${turn} ${scratchpad}
 * ${toolSchemas} plus any ${var} saved by an earlier stage via saveAs.
 * "js" stages get ctx = { vars, scratchpad, turn, task, log(msg) } and may
 * mutate scratchpad/vars or return { stop: true } — the harness escape hatch
 * for verification, retrieval, and typed-write gating.
 */
(function () {
  'use strict';

  const K_LOOPS  = 'sandpie:looplab:loops';     // { [name]: specJSONstring }
  const K_LAST   = 'sandpie:looplab:lastLoop';
  const K_TASK   = 'sandpie:looplab:lastTask';

  /* ================= default example loop ================= */
  const EXAMPLE = {
    name: 'scratchpad-v1',
    maxTurns: 8,
    scratchpad: { goal: '', facts: [], todo: [], last_error: '', done: false },
    stopWhen: 'scratchpad.done === true',
    stages: [
      {
        name: 'planner', type: 'llm', parse: 'block:PLAN', temperature: 0.7, saveAs: 'plan',
        system: 'You are the PLANNER. Given the task and the scratchpad, decide the SINGLE most useful next step. Output ONLY a <PLAN> block.',
        user: 'TASK:\n${task}\n\nSCRATCHPAD:\n${scratchpad}\n\nTOOLS:\n${toolSchemas}\n\nOutput ONLY:\n<PLAN>\nStep: <one concrete step>\nTool: <tool name or none>\n</PLAN>'
      },
      {
        name: 'actor', type: 'llm', parse: 'json', temperature: 0.2, saveAs: 'call',
        system: 'You are the ACTOR. Emit EXACTLY ONE JSON object for a tool call: {"tool":"<name>","arguments":{...}}. If no tool is needed, {"tool":"none","arguments":{}}. Output ONLY the JSON.',
        user: 'PLAN:\n${plan}\n\nTOOLS:\n${toolSchemas}\n\nYour JSON:'
      },
      { name: 'execute', type: 'tool', argsFrom: 'call', saveAs: 'observation' },
      {
        name: 'scribe', type: 'llm', parse: 'json', temperature: 0.1, mergeScratchpad: true,
        system: 'You are the SCRIBE. Update the scratchpad from the observation. Output ONLY a JSON object with the SAME keys as the scratchpad (goal, facts, todo, last_error, done). facts must be short verifiable claims; set done=true only if the TASK is fully complete.',
        user: 'TASK:\n${task}\n\nSCRATCHPAD:\n${scratchpad}\n\nPLAN:\n${plan}\n\nOBSERVATION (truncated):\n${observation}\n\nNew scratchpad JSON:'
      }
    ]
  };

  /* ---- decision-matrix example: propose k options → foreach-score each on
     fixed criteria → js stage aggregates (the arithmetic and decision rule are
     CODE, so the model can't fudge the aggregation). Single-pass. ---- */
  const MATRIX = {
    name: 'decision-matrix',
    maxTurns: 2,
    scratchpad: { options: [], scores: [], decision: null, done: false },
    stopWhen: 'scratchpad.done === true',
    stages: [
      {
        name: 'propose', type: 'llm', parse: 'json', temperature: 0.8, mergeScratchpad: true,
        system: 'You are the PROPOSER. Produce exactly 3 genuinely different approaches to the task — different strategies, not variations of one idea. Output ONLY JSON: {"options":[{"id":"A","summary":"..."},{"id":"B","summary":"..."},{"id":"C","summary":"..."}]}',
        user: 'TASK:\n${task}\n\nJSON:'
      },
      {
        name: 'score', type: 'foreach', items: 'scratchpad.options', saveAs: 'scores',
        stage: {
          name: 'judge', type: 'llm', parse: 'json', temperature: 0.2,
          system: 'You are the JUDGE. Score ONE option on three criteria, integer 1-5 (5=best): correctness (likely to actually solve the task), cost (5 = cheap and simple to do), verifiability (5 = easy to check it worked). Justify in one line. Identical scores across all criteria are almost always lazy — differentiate unless truly warranted. Output ONLY JSON: {"id":"<option id>","correctness":n,"cost":n,"verifiability":n,"why":"..."}',
          user: 'TASK:\n${task}\n\nOPTION TO SCORE (judge this one only):\n${item}\n\nJSON:'
        }
      },
      {
        name: 'aggregate', type: 'js',
        code: "const rows = ctx.vars.scores || [];\nconst totals = rows.filter(Boolean).map(r => ({ id: r.id, total: (r.correctness||0)+(r.cost||0)+(r.verifiability||0), why: r.why }));\ntotals.sort((a,b) => b.total - a.total);\nconst flat = rows.filter(Boolean).every(r => r.correctness === r.cost && r.cost === r.verifiability);\nctx.scratchpad.scores = rows;\nctx.scratchpad.decision = { winner: totals[0] ? totals[0].id : null, margin: totals.length > 1 ? totals[0].total - totals[1].total : null, ranking: totals, suspicious_uniform_scores: flat };\nctx.scratchpad.done = true;\nctx.log('winner: ' + (totals[0] ? totals[0].id + ' (total ' + totals[0].total + ')' : 'none') + (flat ? ' — WARNING: uniform scores, judge may be lazy' : ''));"
      }
    ]
  };

  /* ---- general-agent: the task-agnostic cycle. The model never plans freely —
     it fills narrow cells (frame subgoals / propose 3 options / judge one option
     / evaluate one observation) and code enforces the guarantees: the novelty
     filter makes repeating a past attempt unrepresentable, and a subgoal is only
     marked done when the evaluator's evidence quote literally appears in the
     observation (hallucinated success fails to verify). ---- */
  const GENERAL = {
    name: 'general-agent',
    maxTurns: 12,
    scratchpad: { framed: false, subgoals: [], facts: [], attempts: [], done: false },
    stopWhen: 'scratchpad.done === true',
    stages: [
      {
        name: 'frame', type: 'llm', parse: 'json', temperature: 0.4, mergeScratchpad: true,
        when: '!scratchpad.framed',
        system: 'You are the FRAMER. Break the task into 2-5 concrete subgoals, ordered, each verifiable from a tool observation. For each, "check" states what evidence in an observation would PROVE it is met. Output ONLY JSON: {"framed":true,"subgoals":[{"id":"g1","desc":"...","check":"..."}]}',
        user: 'TASK:\n${task}\n\nAVAILABLE TOOLS (names only matter here):\n${toolSchemas}\n\nJSON:'
      },
      {
        name: 'focus', type: 'js',
        code: "const sp = ctx.scratchpad;\n(sp.subgoals || []).forEach(g => { if (!g.status) g.status = 'open'; });\nconst open = (sp.subgoals || []).filter(g => g.status === 'open');\nif (!open.length) { sp.done = true; ctx.log('all subgoals done'); return { stop: true }; }\nctx.vars.subgoal = open[0];\nctx.log('focus: ' + open[0].id + ' — ' + open[0].desc);"
      },
      {
        name: 'options', type: 'llm', parse: 'json', temperature: 0.8, saveAs: 'options',
        when: 'vars.subgoal',
        system: 'You are the OPTION GENERATOR. Propose exactly 3 candidate next actions for the CURRENT SUBGOAL, using at least 2 different tools. You MUST NOT repeat anything in ATTEMPTS SO FAR (same tool with same arguments). args must match the tool schema. Output ONLY JSON: {"options":[{"id":"o1","tool":"<name>","args":{...},"rationale":"one line"}]}',
        user: 'TASK:\n${task}\n\nCURRENT SUBGOAL:\n${subgoal}\n\nSCRATCHPAD (facts + attempts so far — do not repeat attempts):\n${scratchpad}\n\nTOOLS:\n${toolSchemas}\n\nJSON:'
      },
      {
        name: 'sanitize', type: 'js', when: 'vars.options',
        code: "const v = ctx.vars, sp = ctx.scratchpad;\nconst opts = ((v.options && v.options.options) || []).filter(o => o && typeof o.tool === 'string');\nconst tried = new Set((sp.attempts || []).map(a => a.tool + '|' + a.args));\nlet names = [];\ntry { names = JSON.parse(v.toolSchemas).map(t => t.function.name); } catch (e) {}\nv.surviving = opts.filter(o => {\n  const key = o.tool + '|' + JSON.stringify(o.args || {}).slice(0, 120);\n  if (tried.has(key)) return false;                 // novelty filter: repeats are unrepresentable\n  if (names.length && !names.includes(o.tool)) return false;  // hallucinated tool\n  return true;\n});\nctx.log(opts.length + ' proposed, ' + v.surviving.length + ' survive (repeat/unknown-tool filtered)');"
      },
      {
        name: 'judge', type: 'foreach', items: 'vars.surviving', saveAs: 'scores',
        when: 'vars.surviving && vars.surviving.length > 1',
        stage: {
          name: 'judge1', type: 'llm', parse: 'json', temperature: 0.1,
          system: 'You are the JUDGE. Score ONE candidate action for the current subgoal: progress (1-5, how much closer it likely gets us) and risk (1-5, chance it fails or wastes the turn). Output ONLY JSON: {"id":"<option id>","progress":n,"risk":n,"why":"one line"}',
          user: 'SUBGOAL:\n${subgoal}\n\nCANDIDATE ACTION (judge this one only):\n${item}\n\nKNOWN FACTS:\n${scratchpad}\n\nJSON:'
        }
      },
      {
        name: 'pick', type: 'js', when: 'vars.surviving && vars.surviving.length',
        code: "const v = ctx.vars;\nconst scores = (v.scores || []).filter(Boolean);\nlet best = null;\nfor (const s of scores) { const t = (s.progress || 0) - (s.risk || 0); if (!best || t > best.t) best = { t, id: s.id }; }\nconst chosen = (best && v.surviving.find(o => o.id === best.id)) || v.surviving[0];\nv.call = { tool: chosen.tool, arguments: chosen.args || {} };\nctx.log('pick: ' + chosen.tool + (best ? ' (score ' + best.t + ')' : ' (only viable option)'));"
      },
      { name: 'act', type: 'tool', argsFrom: 'call', saveAs: 'observation', when: 'vars.call' },
      {
        name: 'evaluate', type: 'llm', parse: 'json', temperature: 0.1, saveAs: 'evaluation',
        when: 'vars.call',
        system: 'You are the EVALUATOR. Decide if the observation satisfies the check of the subgoal. "evidence" MUST be an exact substring copied verbatim from the observation (it is machine-checked; paraphrase = rejected). Output ONLY JSON: {"met":true|false,"evidence":"<verbatim quote or empty>","fact":"one short useful fact learned","hint":"if not met, what to try next"}',
        user: 'SUBGOAL:\n${subgoal}\n\nOBSERVATION:\n${observation}\n\nJSON:'
      },
      {
        name: 'commit', type: 'js', when: 'vars.call',
        code: "const v = ctx.vars, sp = ctx.scratchpad;\nconst ev = v.evaluation || {};\nconst obs = String(v.observation || '');\nconst verified = !!(ev.met && ev.evidence && obs.includes(ev.evidence));   // the write barrier\nconst g = (sp.subgoals || []).find(g => g.id === (v.subgoal && v.subgoal.id));\nif (verified && g) { g.status = 'done'; g.evidence = String(ev.evidence).slice(0, 200); }\nif (ev.fact) sp.facts.push(String(ev.fact).slice(0, 200));\nif (sp.facts.length > 15) sp.facts = sp.facts.slice(-15);\nsp.attempts.push({ turn: ctx.turn, subgoal: v.subgoal ? v.subgoal.id : '?', tool: v.call.tool, args: JSON.stringify(v.call.arguments || {}).slice(0, 120), met: verified, hint: verified ? '' : String(ev.hint || '').slice(0, 150) });\nif (sp.attempts.length > 12) sp.attempts = sp.attempts.slice(-12);\nctx.log(verified ? 'subgoal ' + g.id + ' VERIFIED done' : (ev.met ? 'REJECTED: evidence quote not found verbatim in observation' : 'not met — ' + (ev.hint || 'no hint')));"
      }
    ]
  };

  /* ---- ralph: the REAL "Ralph Wiggum" loop (Geoffrey Huntley) for long-running SWE
     tasks, DECOMPOSED into role subagents so no single step can crowd out the others
     (a single all-in-one agent kept exploring and NEVER recorded progress). Each turn:
       1. PLAN   (llm)   — read the injected progress file, pick the ONE next action
                           (or declare allDone). Cheap, focused.
       2. WORK   (agent) — do that ONE action with tools. Its tool-call trace is
                           captured (its final text is usually empty).
       3. SCRIBE (llm)   — rewrite the FULL progress file from {old file + work trace};
                           the HARNESS writes it (persistProgress) so it CANNOT be
                           skipped — the repeated real-world failure we saw.
       4. VERIFY (agent) — only when PLAN says allDone: a skeptic re-checks with tools.
       5. VERDICT(js)    — PASS → done; FAIL → reopen + inject the objection.
     Two filesystems: `shell` runs on the REAL machine; read_file/write_file/edit_file
     are browser OPFS (separate disk). The harness owns the OPFS progress file entirely,
     so the model never has to touch it. maxRounds is a harness guardrail (official Ralph
     has none); cloud honors it, local backends cap at their internal 8. ---- */
  const RALPH = {
    name: 'ralph',
    maxTurns: 40,
    memory: { file: '${ralphFile}' },
    scratchpad: { iteration: 0, done: false, allDone: false, lessons: [], recentPaths: [], log: [] },
    stopWhen: 'scratchpad.done === true',
    stages: [
      {
        // 1. PLAN — decide the single next action from the current progress file.
        name: 'plan', type: 'llm', saveAs: 'planRaw', temperature: 0.2,
        system: [
          'You are the PLANNER for one iteration of a long software task. You have NO memory; the progress file below is the whole state. Pick the SINGLE next concrete action — small and verifiable. Do NOT do the work; just decide it.',
          '',
          'PROGRESS FILE:',
          '${progress}',
          '',
          'HARNESS NOTES (recent paths, verifier objections):',
          '${memory}',
          '',
          'If the file is still the bootstrap skeleton, the next action is to explore the codebase and draft the real checklist. Set "allDone" true ONLY if every checklist item is complete AND there are no unresolved verifier objections above.',
          'Output ONLY JSON: {"allDone": false, "next": "<one concrete action, imperative, one sentence>", "why": "<one line>"}',
        ].join('\n'),
        user: 'TASK:\n${task}\n\nJSON:',
      },
      {
        // Extract the action + allDone defensively (a JSON hiccup must not waste a turn).
        name: 'pick', type: 'js',
        code: "const raw = String(ctx.vars.planRaw || '');\nlet p = {};\ntry { const s = raw.indexOf('{'), e = raw.lastIndexOf('}'); if (s >= 0 && e > s) p = JSON.parse(raw.slice(s, e + 1)); } catch (_) {}\nctx.vars.planNext = (p.next && String(p.next).trim()) || 'Explore the codebase relevant to the task and draft or refine the concrete checklist.';\nctx.scratchpad.allDone = !!p.allDone;\nctx.scratchpad.iteration = ctx.turn;\nctx.scratchpad.log.push('T' + ctx.turn + ': ' + (p.allDone ? '[claims done] ' : '') + ctx.vars.planNext.slice(0, 110));\nif (ctx.scratchpad.log.length > 20) ctx.scratchpad.log = ctx.scratchpad.log.slice(-20);\nctx.log(p.allDone ? 'planner claims DONE — verifying' : 'next: ' + ctx.vars.planNext.slice(0, 80));",
      },
      {
        // 2. WORK — execute that ONE action. Trace captured for the scribe.
        name: 'work', type: 'agent', saveAs: 'workOut', traceAs: 'workTrace', maxRounds: 24,
        when: '!scratchpad.allDone',
        system: [
          'You are the WORKER for one iteration of a long software task. Do EXACTLY the ONE action below — nothing more. Verify it actually worked (read files back, run code). Do not try to finish the whole task.',
          '',
          'THE ACTION FOR THIS ITERATION:',
          '${planNext}',
          '',
          'CONTEXT — the current progress file:',
          '${progress}',
          '',
          'IMPORTANT — two separate filesystems:',
          '- `shell` runs on the REAL machine (where the project source lives, e.g. /home/...). Use it to explore, build, run, and test real code. Prefer absolute paths.',
          '- `read_file`/`write_file`/`edit_file` are a SEPARATE browser sandbox (OPFS) and will NOT see /home paths — do not use them to read the project. Use `shell` (cat/sed/grep) for real files.',
          '- You do NOT need to update any progress file — a separate step records your work. Just do the action and report what you did.',
          '',
          'Scratch space (if you need it) is the shell working area. Report concretely what you changed and what you verified.',
        ].join('\n'),
        user: 'Do this one action now:\n${planNext}',
      },
      {
        // 3. SCRIBE — rewrite the full progress file; the HARNESS persists it
        // (saveAs progressUpdate → runLoop.persistProgress). Cannot be skipped.
        name: 'scribe', type: 'llm', saveAs: 'progressUpdate', temperature: 0.1,
        when: '!scratchpad.allDone',
        system: [
          'You are the SCRIBE. Produce the UPDATED progress file for a long software task, so the next fresh-context iteration inherits an accurate plan. Output ONLY the file content (Markdown) — no commentary, no code fences.',
          '',
          'Keep the structure: "# PROGRESS", "## Task", "## Checklist" (- [ ] / - [x]), "## Lessons", "## Next".',
          'Update it truthfully from what the worker just did: check off ONLY genuinely-completed+verified items, add concrete facts/paths and any lesson/gotcha, and rewrite "## Next" with the single most important next action. Preserve everything still relevant; do not invent progress.',
        ].join('\n'),
        user: 'CURRENT PROGRESS FILE:\n${progress}\n\nPLANNED ACTION THIS ITERATION:\n${planNext}\n\nWHAT THE WORKER ACTUALLY DID (tool trace):\n${workTrace}\n\nOutput the full updated progress file now:',
      },
      {
        // 4. VERIFY — skeptic gate, only when the planner declared completion.
        name: 'verify', type: 'agent', saveAs: 'verdictOut', maxRounds: 12,
        when: 'scratchpad.allDone === true && scratchpad.done !== true',
        system: [
          'You are the VERIFIER. The planner claims this software task is COMPLETE. Distrust it — find what is missing, broken, or unverified. `shell` runs the REAL machine (build/run/test there); read_file/edit_file are a separate OPFS sandbox.',
          '',
          'PROGRESS FILE (the claim):',
          '${progress}',
          '',
          'Spot-check with tools: build/run/test the real code where possible; read the files it says it changed. Check the strongest evidence, not the prose.',
          'End with exactly ONE line: "VERDICT: PASS" if genuinely complete and verified, else "VERDICT: FAIL — <one concrete reason>". No verdict line = FAIL.',
        ].join('\n'),
        user: 'TASK:\n${task}\n\nVerify the completion claim now.',
      },
      {
        // 5. VERDICT — apply the verifier's ruling.
        name: 'verdict', type: 'js',
        when: 'scratchpad.allDone === true && scratchpad.done !== true',
        code: "const v = String(ctx.vars.verdictOut || '');\nconst sp = ctx.scratchpad;\nsp.iteration = ctx.turn;\nif (/VERDICT:\\s*PASS/i.test(v)) { sp.done = true; ctx.log('\\u2705 verifier PASSED — task complete after ' + ctx.turn + ' iteration(s)'); }\nelse {\n  const m = v.match(/VERDICT:\\s*FAIL\\s*[\\u2014-]*\\s*(.*)/i);\n  const reason = ((m && m[1]) || 'no explicit verdict — treated as FAIL').slice(0, 200);\n  sp.allDone = false;\n  sp.lessons.push('Verifier REJECTED completion at iteration ' + ctx.turn + ': ' + reason);\n  if (sp.lessons.length > 12) sp.lessons = sp.lessons.slice(-12);\n  ctx.log('\\u274c verifier rejected: ' + reason);\n}",
      },
    ],
  };

  const EXAMPLES = [EXAMPLE, MATRIX, GENERAL, RALPH];

  /* ================= persistence ================= */
  function loadLoops() {
    try { return JSON.parse(localStorage.getItem(K_LOOPS) || '{}'); } catch (_) { return {}; }
  }
  function saveLoops(loops) { localStorage.setItem(K_LOOPS, JSON.stringify(loops)); }
  // Safe in-place upgrades: overwrite a stored example ONLY when it is provably an
  // unmodified older shipped version (so a user's own edits are never clobbered).
  // ralph: the pre-per-run-file version hardcoded `ralph/PROGRESS.md` and had no
  // `${ralphFile}` var → upgrade it to the per-run-isolated prompt.
  const UPGRADES = {
    // Upgrade any shipped ralph that predates the decomposed pipeline (no scribe stage).
    // Matched by the injected ${progress} var (all shipped ralphs since per-run had it)
    // AND absence of the scribe. A user who removed ${progress} (heavy rewrite) is left
    // untouched.
    ralph: (s) => s.includes('${progress}') && !s.includes('SCRIBE'),
  };
  // Seed each example once (per-name flag), so a user deleting one doesn't get
  // it resurrected on every open.
  function ensureExample() {
    const loops = loadLoops();
    let changed = false;
    for (const ex of EXAMPLES) {
      const flag = 'sandpie:looplab:seeded:' + ex.name;
      if (!loops[ex.name] && !localStorage.getItem(flag)) {
        loops[ex.name] = JSON.stringify(ex, null, 2);
        changed = true;
      } else if (loops[ex.name] && UPGRADES[ex.name]) {
        try { if (UPGRADES[ex.name](loops[ex.name])) { loops[ex.name] = JSON.stringify(ex, null, 2); changed = true; } } catch (_) {}
      }
      localStorage.setItem(flag, '1');
    }
    if (changed) saveLoops(loops);
    return loops;
  }

  /* ================= LLM adapter (single-shot) ================= */
  function isDenseWebgpu(prov) {
    return prov && prov.type === 'webgpu'
      && typeof SandpieQwen3 !== 'undefined' && SandpieQwen3.DEFAULT_MODELS
      && SandpieQwen3.DEFAULT_MODELS.some(m => m.modelId === prov.endpoint);
  }

  function contentToText(c) {
    if (typeof c === 'string') return c;
    if (Array.isArray(c)) return c.map(p => (p && (p.text || '')) || '').join('');
    return String(c ?? '');
  }
  function stripThink(t) { return String(t).replace(/<think>[\s\S]*?<\/think>/g, '').trim(); }

  // Local backends run the whole agent loop in-worker; with tools:[] that is one
  // assistant message → agent_done, i.e. a single-shot completion.
  async function localOnce(engine, prov, { system, user, signal, onDelta }) {
    let out = '';
    await engine.runConversation(
      { provider: prov, messages: [{ role: 'user', content: user }], systemPrompt: system || '', tools: [], convId: 'loop-lab', signal },
      (ev) => {
        if (!ev) return;
        // Live tokens: content + reasoning deltas → onDelta (so the UI streams).
        if (ev.type === 'delta' && ev.delta && onDelta) {
          if (ev.delta.reasoning) onDelta(ev.delta.reasoning);
          if (ev.delta.content) onDelta(ev.delta.content);
        }
        if (ev.type === 'message_added' && ev.message && ev.message.role === 'assistant') {
          out += contentToText(ev.message.content);
        }
      },
    );
    return stripThink(out);
  }

  async function httpOnce({ system, user, temperature, maxTokens, signal }) {
    const prov = (typeof SandpieProviders !== 'undefined') ? SandpieProviders.getActive() : null;
    const endpoint = (window.$('endpoint') ? window.$('endpoint').value : '').replace(/\/$/, '');
    const model = (window.$('model') ? window.$('model').value : (prov && prov.model) || '');
    if (!endpoint || !model) throw new Error('No provider endpoint or model selected.');
    let url = endpoint + '/chat/completions';
    const proxy = window.$('proxyUrl') ? window.$('proxyUrl').value : '';
    if (proxy) { try { const u = new URL(proxy); u.searchParams.set('url', url); url = u.href; } catch (_) {} }

    const messages = [];
    if (system) messages.push({ role: 'system', content: system });
    messages.push({ role: 'user', content: user });
    const body = {
      model, messages, stream: false,
      max_tokens: maxTokens || 4096,
      temperature: temperature != null ? temperature : 0.7,
    };
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + ((window.$('apiKey') ? window.$('apiKey').value : '') || '') },
      body: JSON.stringify(body), signal,
    });
    if (!res.ok) throw new Error('HTTP ' + res.status + ' — ' + (await res.text().catch(() => '')).slice(0, 300));
    const data = await res.json();
    if (data.error) throw new Error(String(data.error.message || JSON.stringify(data.error)));
    const msg = (data.choices && data.choices[0] && data.choices[0].message) || {};
    return stripThink(contentToText(msg.content || ''));
  }

  async function llmOnce(opts) {
    const prov = (typeof SandpieProviders !== 'undefined') ? SandpieProviders.getActive() : null;
    if (isDenseWebgpu(prov)) return localOnce(SandpieQwen3, prov, opts);
    if (prov && prov.type === 'litertlm' && typeof SandpieLiteRTLM !== 'undefined' && SandpieLiteRTLM.runConversation) {
      return localOnce(SandpieLiteRTLM, prov, opts);
    }
    const out = await httpOnce(opts);
    if (opts && opts.onDelta && out) { try { opts.onDelta(out); } catch (_) {} }   // cloud is non-streaming → show the full text once
    return out;
  }

  /* ================= agent adapter (full tool-calling turn) ================= */
  // Unlike llmOnce (single completion, no tools), an agent turn runs the WHOLE
  // multi-round tool loop on ONE prompt, so the model can autonomously read/write
  // OPFS files and do real work — the unit a Ralph iteration needs. Fresh context
  // every call (messages rebuilt from system+user); durable state lives in files.

  // Local backends run the agent loop in-worker already; pass the real tools + a
  // STABLE convId so any conversation-scoped OPFS area persists across iterations.
  async function localAgent(engine, prov, { system, user, tools, signal, onEvent, onDelta, convId }) {
    let out = '';
    const names = {};   // tool_call_id → name (tool_result carries only the id)
    await engine.runConversation(
      { provider: prov, messages: [{ role: 'user', content: user }], systemPrompt: system || '', tools: tools || [], convId: convId || 'loop-lab-ralph', signal },
      (ev) => {
        if (!ev) return;
        // Live tokens (content + reasoning) so the UI streams during the agent turn.
        if (ev.type === 'delta' && ev.delta && onDelta) {
          if (ev.delta.reasoning) onDelta(ev.delta.reasoning);
          if (ev.delta.content) onDelta(ev.delta.content);
        }
        // Structured tool activity → onEvent (the UI renders full args, result body, images).
        if (ev.type === 'tool_started' && ev.tc) {
          const nm = ev.tc.function && ev.tc.function.name;
          if (ev.tc.id) names[ev.tc.id] = nm;
          if (onEvent) onEvent({ kind: 'toolCall', name: nm, args: (ev.tc.function && ev.tc.function.arguments) || '{}' });
        }
        if (ev.type === 'tool_result' && onEvent) {
          onEvent({ kind: 'toolResult', name: names[ev.id] || '', result: ev.result, artifacts: ev.artifacts });
        }
        if (ev.type === 'message_added' && ev.message && ev.message.role === 'assistant') out += contentToText(ev.message.content) + '\n';
      },
    );
    return stripThink(out);
  }

  // Cloud: a compact, self-contained OpenAI-style tool loop (kept here, not routed
  // through conversations.js, to preserve Loop Lab's zero-blast-radius contract).
  async function httpAgent({ system, user, tools, maxRounds, signal, onEvent, onDelta, convId }) {
    const prov = (typeof SandpieProviders !== 'undefined') ? SandpieProviders.getActive() : null;
    const endpoint = (window.$('endpoint') ? window.$('endpoint').value : '').replace(/\/$/, '');
    const model = (window.$('model') ? window.$('model').value : (prov && prov.model) || '');
    if (!endpoint || !model) throw new Error('No provider endpoint or model selected.');
    let url = endpoint + '/chat/completions';
    const proxy = window.$('proxyUrl') ? window.$('proxyUrl').value : '';
    if (proxy) { try { const u = new URL(proxy); u.searchParams.set('url', url); url = u.href; } catch (_) {} }
    const auth = 'Bearer ' + ((window.$('apiKey') ? window.$('apiKey').value : '') || '');

    const messages = [];
    if (system) messages.push({ role: 'system', content: system });
    messages.push({ role: 'user', content: user });
    const hasTools = !!(tools && tools.length);
    const rounds = Math.max(1, Math.min(40, maxRounds || 12));
    let text = '';
    for (let r = 0; r < rounds; r++) {
      if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');
      const body = {
        model, messages, stream: false, max_tokens: 4096,
        tools: hasTools ? tools : undefined,
        tool_choice: hasTools ? 'auto' : undefined,
      };
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: auth },
        body: JSON.stringify(body), signal,
      });
      if (!res.ok) throw new Error('HTTP ' + res.status + ' — ' + (await res.text().catch(() => '')).slice(0, 300));
      const data = await res.json();
      if (data.error) throw new Error(String(data.error.message || JSON.stringify(data.error)));
      const msg = (data.choices && data.choices[0] && data.choices[0].message) || {};
      messages.push(msg);
      if (msg.content) { text += contentToText(msg.content) + '\n'; if (onDelta) onDelta(contentToText(msg.content) + '\n'); }
      const calls = msg.tool_calls || [];
      if (!calls.length) break;   // no more tools → turn complete
      for (const tc of calls) {
        const nm = tc.function && tc.function.name;
        let args = {};
        try { args = JSON.parse((tc.function && tc.function.arguments) || '{}'); } catch (_) {}
        if (onEvent) onEvent({ kind: 'toolCall', name: nm, args: (tc.function && tc.function.arguments) || '{}' });
        let result;
        try { result = await runTool(nm, args, signal, convId); }
        catch (e) { result = 'Error: ' + (e.message || e); }
        if (onEvent) onEvent({ kind: 'toolResult', name: nm, result });
        messages.push({ role: 'tool', tool_call_id: tc.id, content: String(result).slice(0, 8000) });
      }
    }
    return stripThink(text);
  }

  async function agentTurn(opts) {
    const prov = (typeof SandpieProviders !== 'undefined') ? SandpieProviders.getActive() : null;
    if (isDenseWebgpu(prov)) return localAgent(SandpieQwen3, prov, opts);
    if (prov && prov.type === 'litertlm' && typeof SandpieLiteRTLM !== 'undefined' && SandpieLiteRTLM.runConversation) {
      return localAgent(SandpieLiteRTLM, prov, opts);
    }
    return httpAgent(opts);
  }

  /* ================= tool runner (shared worker RPC) ================= */
  function runTool(name, args, signal, convId) {
    return new Promise((resolve, reject) => {
      const sw = window._sandpieWorker;
      if (!sw) { reject(new Error('sandpie-worker not ready — reload the page.')); return; }
      const id = 'll-' + Math.random().toString(36).slice(2, 11);
      let settled = false;
      const finish = (result, err) => {
        if (settled) return; settled = true;
        clearTimeout(timer);
        try { sw.removeEventListener('message', onMsg); } catch (_) {}
        if (signal) try { signal.removeEventListener('abort', onAbort); } catch (_) {}
        err ? reject(new Error(err)) : resolve(result);
      };
      const onMsg = (e) => { const r = e.data || {}; if (r.id === id && r.type === 'tool_result') finish(r.result || ''); };
      const onAbort = () => finish('', 'Aborted');
      const timer = setTimeout(() => finish('', 'tool timed out (120s)'), 120000);
      sw.addEventListener('message', onMsg);
      if (signal) signal.addEventListener('abort', onAbort, { once: true });
      sw.postMessage({ type: 'tool', id, name, args, conversation_file_name: convId || 'loop-lab' });
    });
  }

  /* ================= parsing helpers ================= */
  function parseJSON(raw) {
    const text = String(raw || '').trim();
    const m = text.match(/```(?:json)?\s*([\s\S]*?)```/);
    if (m) { try { return JSON.parse(m[1].trim()); } catch (_) {} }
    const s = text.indexOf('{'); const e = text.lastIndexOf('}');
    if (s !== -1 && e > s) { try { return JSON.parse(text.slice(s, e + 1)); } catch (_) {} }
    return null;
  }
  function parseBlock(raw, tag) {
    const m = String(raw || '').match(new RegExp('<' + tag + '>\\s*([\\s\\S]*?)\\s*</' + tag + '>', 'i'));
    return m ? m[1].trim() : String(raw || '').trim();
  }
  function fill(template, vars) {
    return String(template || '').replace(/\$\{([^}]+)\}/g, (_, key) => {
      const v = vars[key.trim()];
      if (v === undefined) return '';
      return typeof v === 'string' ? v : JSON.stringify(v, null, 2);
    });
  }

  /* ================= harness-owned memory (Ralph & any spec.memory loop) ================= */
  // Pull file paths out of a tool call's arguments so the harness can auto-track which
  // paths the agent touched (recentPaths) — model-independent, so it can't be skipped.
  function extractPaths(args) {
    let a = args;
    if (typeof a === 'string') { try { a = JSON.parse(a); } catch (_) { return []; } }
    if (!a || typeof a !== 'object') return [];
    const out = [];
    if (typeof a.path === 'string') out.push(a.path);
    if (Array.isArray(a.paths)) for (const p of a.paths) if (typeof p === 'string') out.push(p);
    return out;
  }
  // MRU push (dedupe, cap) — used for recentPaths.
  function pushMru(list, item, cap) {
    if (!item) return;
    const i = list.indexOf(item);
    if (i >= 0) list.splice(i, 1);
    list.push(item);
    if (list.length > cap) list.splice(0, list.length - cap);
  }
  // The harness-notes block INJECTED into the agent prompt each turn (${memory}):
  // auto-tracked warnings/objections + recent paths + a short iteration log. The
  // MODEL-owned progress file is injected separately as ${progress}.
  function renderMemoryForPrompt(sp) {
    const L = [];
    L.push('Iterations so far: ' + (sp.iteration || 0));
    L.push('Warnings & verifier notes:' + (sp.lessons && sp.lessons.length ? '\n' + sp.lessons.map(x => '  - ' + x).join('\n') : ' (none)'));
    L.push('Recent paths touched (auto-tracked):' + (sp.recentPaths && sp.recentPaths.length ? '\n' + sp.recentPaths.slice(-10).map(x => '  - ' + x).join('\n') : ' (none yet)'));
    if (sp.log && sp.log.length) L.push('Recent iteration log:\n' + sp.log.slice(-6).map(x => '  ' + x).join('\n'));
    return L.join('\n');
  }
  // The skeleton the harness pre-creates at ${ralphFile} before turn 1, so the model
  // only ever edit_file's the file (write_file is create-only and refuses overwrites —
  // the trap that used to eat progress updates). The model replaces this with its plan.
  function bootstrapMd(task) {
    return [
      '# PROGRESS',
      '',
      '## Task',
      task,
      '',
      '## Checklist',
      '- [ ] (plan not written yet — explore the codebase and replace this with a real, concrete checklist)',
      '',
      '## Lessons',
      '(none yet)',
      '',
      '## Next',
      'Study the codebase relevant to the task, then rewrite this file: real checklist under "## Checklist", first concrete step here under "## Next".',
      '',
    ].join('\n');
  }

  /* ================= run engine ================= */
  let _run = null;          // { ctrl, stats }
  // Transcript = the Copy-run record. To keep RAM bounded on long runs, only a small
  // TAIL is held in memory; the rest is flushed to an OPFS file (looplab-runs/<runId>.log).
  // Copy = file contents (flushed prefix) + the in-RAM tail (suffix) — no overlap.
  let _transcript = [];
  let _transcriptBytes = 0, _transcriptPath = null, _transcriptFlushed = false;
  const rec = (s) => { s = String(s); _transcript.push(s); _transcriptBytes += s.length + 2; };
  const TRANSCRIPT_LIMIT = 128000, TRANSCRIPT_TAIL_BYTES = 32000;   // flush RAM>128KB, keep ~32KB tail

  // Page-side OPFS append (createWritable + write-at-end). Batched per turn, so the
  // per-write overhead is negligible. Path is relative to the OPFS root.
  async function opfsAppend(path, text) {
    const parts = path.split('/');
    let dir = await navigator.storage.getDirectory();
    for (let i = 0; i < parts.length - 1; i++) dir = await dir.getDirectoryHandle(parts[i], { create: true });
    const fh = await dir.getFileHandle(parts[parts.length - 1], { create: true });
    const size = (await fh.getFile()).size;
    const w = await fh.createWritable({ keepExistingData: true });
    await w.write({ type: 'write', position: size, data: text });
    await w.close();
  }
  async function opfsReadText(path) {
    const parts = path.split('/');
    let dir = await navigator.storage.getDirectory();
    for (let i = 0; i < parts.length - 1; i++) dir = await dir.getDirectoryHandle(parts[i]);
    const fh = await dir.getFileHandle(parts[parts.length - 1]);
    return await (await fh.getFile()).text();
  }
  // Move everything beyond the tail from RAM → OPFS. Best-effort: on failure the
  // entries stay in RAM and are retried next flush (memory just grows meanwhile).
  async function flushTranscript() {
    if (!_transcriptPath || _transcriptBytes < TRANSCRIPT_LIMIT) return;
    // Keep a BYTE-bounded tail in RAM (entries are few-but-huge, so an entry-count
    // tail could keep everything). Walk back from the end until ~TAIL_BYTES; flush
    // the earlier entries.
    let tailBytes = 0, keepFrom = _transcript.length;
    while (keepFrom > 0 && tailBytes < TRANSCRIPT_TAIL_BYTES) { keepFrom--; tailBytes += _transcript[keepFrom].length + 2; }
    if (keepFrom <= 0) return;   // whole buffer fits the tail budget
    const batch = _transcript.slice(0, keepFrom).join('\n\n') + '\n\n';
    try {
      await opfsAppend(_transcriptPath, batch);
      _transcript = _transcript.slice(keepFrom);
      _transcriptBytes = tailBytes;
      _transcriptFlushed = true;
    } catch (_) { /* keep in RAM; retry next turn */ }
  }
  // Full transcript for Copy = flushed file prefix + in-RAM tail.
  async function fullTranscript() {
    let head = '';
    if (_transcriptFlushed && _transcriptPath) { try { head = await opfsReadText(_transcriptPath); } catch (_) {} }
    const tail = _transcript.join('\n\n');
    return (head ? head + tail : tail) || '(no run yet)';
  }

  function validateStage(st, inner) {
    if (!st || !st.name) return 'Every stage needs a "name".';
    const types = inner ? ['llm', 'tool', 'js'] : ['llm', 'tool', 'js', 'foreach', 'agent'];
    if (!types.includes(st.type)) return 'Stage "' + st.name + '": type must be ' + types.join(' | ') + '.';
    if (st.type === 'tool' && !st.argsFrom) return 'Tool stage "' + st.name + '" needs "argsFrom" (a var holding {tool, arguments}).';
    if (st.type === 'js' && typeof st.code !== 'string') return 'JS stage "' + st.name + '" needs a "code" string.';
    if (st.type === 'foreach') {
      if (typeof st.items !== 'string') return 'foreach stage "' + st.name + '" needs "items" (a JS expr over vars/scratchpad returning an array).';
      if (!st.stage || typeof st.stage !== 'object') return 'foreach stage "' + st.name + '" needs an inner "stage".';
      return validateStage(st.stage, true);
    }
    return null;
  }
  function validateSpec(spec) {
    if (!spec || typeof spec !== 'object') return 'Spec is not an object.';
    if (!Array.isArray(spec.stages) || !spec.stages.length) return 'Spec needs a non-empty "stages" array.';
    for (const st of spec.stages) { const e = validateStage(st, false); if (e) return e; }
    return null;
  }

  // Execute one stage. ctx = { vars, scratchpad, turnHost, ui, ctrl, stats }.
  // Returns the stage's output value. saveAs/mergeScratchpad are handled here so
  // foreach inner stages get the same semantics (merge runs once per item).
  async function execStage(st, ctx, depth) {
    const { vars, scratchpad, turnHost, ui, ctrl, stats } = ctx;
    const t0 = Date.now();

    if (st.type === 'llm') {
      stats.llmCalls++;
      ui.stageStart(turnHost, st.name, 'llm');
      const sys = fill(st.system, vars), usr = fill(st.user, vars);
      rec('[' + st.name + ' · llm]\nSYSTEM:\n' + sys + '\nUSER:\n' + usr);
      const raw = await llmOnce({ system: sys, user: usr, temperature: st.temperature, maxTokens: st.maxTokens, signal: ctrl.signal, onDelta: (c) => ui.stageStream(turnHost, st.name, c) });
      let out = raw;
      if (st.parse === 'json') {
        out = parseJSON(raw);
        if (out === null) throw new Error('stage "' + st.name + '": model output is not valid JSON:\n' + raw.slice(0, 400));
      } else if (st.parse && st.parse.startsWith('block:')) {
        out = parseBlock(raw, st.parse.slice(6));
      }
      rec('OUTPUT (' + st.name + '):\n' + (typeof out === 'string' ? out : JSON.stringify(out, null, 2)));
      if (st.saveAs) vars[st.saveAs] = out;
      if (st.mergeScratchpad && out && typeof out === 'object' && !Array.isArray(out)) Object.assign(scratchpad, out);
      ui.stageDone(turnHost, st.name, out, Date.now() - t0);
      return out;
    }

    if (st.type === 'agent') {
      stats.llmCalls++;
      ui.stageStart(turnHost, st.name, 'agent');
      const sys = fill(st.system, vars), usr = fill(st.user, vars);
      const tools = (typeof SandpieTools !== 'undefined' && SandpieTools.schemas) ? SandpieTools.schemas() : [];
      rec('[' + st.name + ' · agent] tools=' + tools.length + '\nSYSTEM:\n' + sys + '\nUSER:\n' + usr);
      const trace = [];   // compact record of what the agent DID (its final text is often empty)
      const out = await agentTurn({
        system: sys, user: usr, tools, maxRounds: st.maxRounds, signal: ctrl.signal, convId: ctx.convId,
        onDelta: (c) => ui.stageStream(turnHost, st.name, c),
        onEvent: (e) => {
          if (!e) return;
          if (e.kind === 'toolCall') {
            stats.toolCalls++;
            ui.agentToolCall(turnHost, e.name, e.args);
            rec('[tool call] ' + e.name + ' ' + (typeof e.args === 'string' ? e.args : JSON.stringify(e.args)));
            if (Array.isArray(scratchpad.recentPaths)) for (const p of extractPaths(e.args)) pushMru(scratchpad.recentPaths, p, 15);
            const as = typeof e.args === 'string' ? e.args : JSON.stringify(e.args || {});
            trace.push('· ' + e.name + ' ' + as.slice(0, 160));
          } else if (e.kind === 'toolResult') {
            ui.agentToolResult(turnHost, e.name, e.result);
            const r = String(e.result == null ? '' : e.result);
            rec('[tool result] ' + (e.name || '') + ': ' + r.slice(0, 600));
            if (trace.length) trace[trace.length - 1] += '  → ' + r.replace(/\s+/g, ' ').slice(0, 220);
          }
        },
      });
      rec('OUTPUT (' + st.name + '):\n' + out);
      if (st.saveAs) vars[st.saveAs] = out;
      if (st.traceAs) vars[st.traceAs] = (trace.join('\n') + (out ? '\n\nFinal note: ' + out : '')).slice(0, 6000) || '(no tool calls made)';
      ui.agentDone(turnHost, st.name, Date.now() - t0);
      return out;
    }

    if (st.type === 'tool') {
      const call = vars[st.argsFrom];
      if (!call || typeof call !== 'object' || !call.tool) throw new Error('stage "' + st.name + '": var "' + st.argsFrom + '" does not hold {tool, arguments}.');
      if (call.tool === 'none' || call.tool === 'done') {
        if (st.saveAs) vars[st.saveAs] = '(no tool needed)';
        rec('[' + st.name + ' · tool] none — skipped');
        ui.stageDone(turnHost, st.name, '(no tool needed — skipped)', Date.now() - t0);
        return null;
      }
      stats.toolCalls++;
      ui.stageStart(turnHost, st.name, 'tool ' + call.tool);
      rec('[' + st.name + ' · tool ' + call.tool + ']\nARGS:\n' + JSON.stringify(call.arguments || {}, null, 2));
      const result = await runTool(call.tool, call.arguments || {}, ctrl.signal, ctx.convId);
      const clipped = String(result).slice(0, st.maxChars || 4000);
      rec('RESULT (' + st.name + ', first ' + clipped.length + ' chars):\n' + clipped);
      if (st.saveAs) vars[st.saveAs] = clipped;
      ui.stageDone(turnHost, st.name + ' (' + call.tool + ')', clipped, Date.now() - t0);
      return clipped;
    }

    if (st.type === 'js') {
      ui.stageStart(turnHost, st.name, 'js');
      const logs = [];
      const fn = new Function('ctx', st.code);
      const ret = fn({ vars, scratchpad, turn: ctx.turn, task: ctx.task, log: (m) => logs.push(String(m)) });
      rec('[' + st.name + ' · js]\n' + (logs.join('\n') || '(no log output)'));
      ui.stageDone(turnHost, st.name, (logs.join('\n') || '(ok)') + (ret && ret.stop ? '\n→ stop requested' : ''), Date.now() - t0);
      return ret;
    }

    if (st.type === 'foreach') {
      if (depth > 0) throw new Error('stage "' + st.name + '": nested foreach is not supported.');
      let items;
      try { items = new Function('vars', 'scratchpad', 'return (' + st.items + ');')(vars, scratchpad); }
      catch (e) { throw new Error('foreach "' + st.name + '": items expression failed — ' + e.message); }
      if (!Array.isArray(items)) throw new Error('foreach "' + st.name + '": items expression did not return an array.');
      rec('[' + st.name + ' · foreach × ' + items.length + ' over ' + st.items + ']');
      const results = [];
      for (let i = 0; i < items.length; i++) {
        if (ctrl.signal.aborted) break;
        // Prototype chain: the inner stage sees all outer vars plus item/itemIndex;
        // its own saveAs writes stay per-item (discarded after the iteration).
        const subVars = Object.create(vars);
        subVars.item = items[i];
        subVars.itemIndex = i;
        const inner = { ...st.stage, name: (st.stage.name || st.name) + '[' + i + ']' };
        results.push(await execStage(inner, { ...ctx, vars: subVars }, depth + 1));
      }
      if (st.saveAs) vars[st.saveAs] = results;
      return results;
    }

    throw new Error('Unknown stage type: ' + st.type);
  }

  async function runLoop(spec, task, ui) {
    const ctrl = new AbortController();
    const stats = { llmCalls: 0, toolCalls: 0, started: Date.now() };
    _run = { ctrl, stats };
    ui.setRunning(true);

    const scratchpad = JSON.parse(JSON.stringify(spec.scratchpad || {}));
    const maxTurns = Math.max(1, Math.min(100, spec.maxTurns || 10));
    const toolSchemas = (typeof SandpieTools !== 'undefined' && SandpieTools.schemas) ? SandpieTools.schemas() : [];
    let stopped = false, error = null;

    // Per-RUN identity so runs never collide on shared durable state (Ralph &
    // friends). Generated ONCE and stable across this run's turns (so turn 2 reads
    // what turn 1 wrote), but unique between runs. Exposed as ${runId} / ${ralphDir}
    // / ${ralphFile} template vars, and as the tool convId (conversation_file_name),
    // so file paths AND any conversation-scoped tool state are isolated per run.
    const runId = 'r' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    const ralphDir = 'ralph/' + runId;
    const ralphFile = ralphDir + '/PROGRESS.md';
    ui.note('run ' + runId + ' — durable state: ' + ralphFile + '  (vars: ${runId} ${ralphDir} ${ralphFile})');

    // Offload the transcript to OPFS so RAM stays bounded on long runs (see rec/flush).
    _transcriptPath = 'looplab-runs/' + runId + '.log';
    _transcriptFlushed = false;
    _transcriptBytes = _transcript.reduce((n, s) => n + s.length + 2, 0);

    // Progress file (opt-in via spec.memory). The MODEL never touches it — a dedicated
    // scribe stage emits the full updated content and the HARNESS writes it, so a
    // persist can't be skipped (the repeated failure we saw). At turn start we read +
    // inject it (${progress}); after the turn we write the scribe's output ourselves.
    let _curBody = null, _progressBody = '', _stale = 0;
    const PROGRESS_CLAMP = 8000;
    // read_file returns "<path> — N lines, X bytes" then "n\tline" rows; strip both.
    function stripReadFile(res) {
      const s = String(res || '');
      if (/^Error/i.test(s)) return null;
      const lines = s.split('\n');
      if (lines.length && /—\s*\d+\s*lines?,/.test(lines[0])) lines.shift();
      return lines.map(l => l.replace(/^\s*\d+\t/, '')).join('\n');
    }
    function clampForPrompt(body) {
      return body.length > PROGRESS_CLAMP
        ? body.slice(0, PROGRESS_CLAMP - 1500) + '\n…[middle clipped — file is ' + body.length + ' chars]…\n' + body.slice(-1400)
        : body;
    }
    // START of turn: read the file (bootstrap if missing) and stage it for ${progress}.
    async function loadProgress() {
      let body = null;
      try { body = stripReadFile(await runTool('read_file', { path: ralphFile }, ctrl.signal, runId)); } catch (_) {}
      if (body === null) {
        body = bootstrapMd(task);
        try { await runTool('write_file', { path: ralphFile, content: body }, ctrl.signal, runId); ui.note('progress file created (bootstrap): ' + ralphFile); }
        catch (e) { ui.note('progress bootstrap failed: ' + ((e && e.message) || e)); }
      }
      _curBody = body;
      _progressBody = clampForPrompt(body);
    }
    // END of turn: write the scribe's new content ourselves (edit_file with old_str =
    // the exact current body, which only the harness writes → guaranteed match).
    // Returns false when the run has stalled (3 turns producing no progress update).
    async function persistProgress(nextRaw, turn) {
      let next = (typeof nextRaw === 'string' ? nextRaw : '').trim();
      next = next.replace(/^```(?:markdown|md)?\s*/i, '').replace(/\s*```$/, '').trim();   // strip stray fences
      if (!next) {
        _stale++;
        ui.note('⚠ no progress update produced this turn (stale ×' + _stale + ')');
        return _stale < 3;
      }
      if (next === _curBody) { _stale = 0; ui.note('progress unchanged this turn'); return true; }
      try {
        await runTool('edit_file', { path: ralphFile, old_str: _curBody, new_str: next }, ctrl.signal, runId);
        _curBody = next; _stale = 0;
        ui.note('✓ progress persisted by harness (' + next.length + ' B)');
      } catch (e) { ui.note('progress persist failed: ' + ((e && e.message) || e)); }
      return true;
    }

    try {
      for (let turn = 1; turn <= maxTurns && !stopped; turn++) {
        if (ctrl.signal.aborted) break;
        // ENFORCED protocol (spec.memory): read + inject the progress file BEFORE the
        // turn; the scribe stage's output is persisted by the harness AFTER (below).
        if (spec.memory) await loadProgress();
        rec('--- TURN ' + turn + ' ---');
        const turnHost = ui.addTurn(turn);
        const vars = {
          task, turn, runId, ralphDir, ralphFile,
          get scratchpad() { return JSON.stringify(scratchpad, null, 2); },
          get memory() { return renderMemoryForPrompt(scratchpad); },
          get progress() { return _progressBody; },
          toolSchemas: JSON.stringify(toolSchemas, null, 2),
        };
        const ctx = { vars, scratchpad, turnHost, ui, ctrl, stats, turn, task, convId: runId };

        for (const st of spec.stages) {
          if (ctrl.signal.aborted) { stopped = true; break; }
          if (stopped) break;   // a js stage requested stop mid-turn
          if (st.when) {
            let go = false;
            try { go = !!(new Function('vars', 'scratchpad', 'turn', 'return (' + st.when + ');')(vars, scratchpad, turn)); }
            catch (e) { ui.stageError(turnHost, st.name, 'when-expr error: ' + e.message); rec('[' + st.name + ' · when ERROR] ' + e.message); break; }
            if (!go) { rec('[' + st.name + ' · skipped] when: ' + st.when); continue; }
          }
          try {
            const ret = await execStage(st, ctx, 0);
            if (st.type === 'js' && ret && ret.stop) stopped = true;
          } catch (e) {
            if (e && e.name === 'AbortError') { stopped = true; break; }
            ui.stageError(turnHost, st.name, e.message || String(e));
            rec('[' + st.name + ' · ERROR]\n' + (e.message || String(e)));
            scratchpad.last_error = String(e.message || e).slice(0, 500);
            break;   // abandon this turn's remaining stages, let the next turn recover
          }
          ui.setScratchpad(scratchpad);
          ui.setStats(stats);
        }
        rec('SCRATCHPAD after turn ' + turn + ':\n' + JSON.stringify(scratchpad, null, 2));

        // GUARANTEED persist: the harness writes the scribe's updated progress file
        // (vars.progressUpdate). Can't be skipped by the model. Stall-stop after 3
        // turns with no update produced.
        if (spec.memory && !ctrl.signal.aborted && !stopped) {
          const alive = await persistProgress(vars.progressUpdate, turn);
          if (!alive) { ui.note('STALLED: 3 turns without a progress update — stopping (rerun to resume from ' + ralphFile + ').'); break; }
        }

        if (spec.stopWhen && !stopped) {
          try {
            if (new Function('scratchpad', 'turn', 'return (' + spec.stopWhen + ');')(scratchpad, turn)) {
              ui.note('stopWhen satisfied at turn ' + turn + '.');
              stopped = true;
            }
          } catch (e) { ui.note('stopWhen eval error: ' + e.message); }
        }

        await flushTranscript();   // offload the turn's transcript to OPFS (bounds RAM)
      }
    } catch (e) {
      error = e;
    } finally {
      _run = null;
      ui.setRunning(false);
      ui.setScratchpad(scratchpad);
      ui.setStats(stats, true);
      if (ctrl.signal.aborted) ui.note('Stopped by user.');
      else if (error) ui.note('Loop error: ' + (error.message || error));
      else if (!stopped) ui.note('Max turns (' + maxTurns + ') reached.');
      else ui.note('Loop finished.');
    }
    return scratchpad;
  }

  /* ================= UI (own overlay, own DOM) ================= */
  let _panel = null;

  const CSS = `
    #loopLabOverlay { position:fixed; inset:0; z-index:9000; display:flex; align-items:center; justify-content:center; }
    #loopLabOverlay .ll-backdrop { position:absolute; inset:0; background:rgba(0,0,0,0.55); }
    #loopLabOverlay .ll-modal { position:relative; width:min(1200px,94vw); height:min(780px,92vh); display:flex; flex-direction:column;
      background:var(--sp-bg,#0d1117); border:1px solid var(--sp-border,#30363d); border-radius:10px; overflow:hidden; }
    #loopLabOverlay .ll-head { display:flex; align-items:center; gap:0.6rem; padding:0.7rem 1rem; border-bottom:1px solid var(--sp-border,#30363d); }
    #loopLabOverlay .ll-body { flex:1; display:flex; min-height:0; }
    #loopLabOverlay .ll-left { flex:0 0 44%; display:flex; flex-direction:column; border-right:1px solid var(--sp-border,#30363d); min-width:0; }
    #loopLabOverlay .ll-right { flex:1; display:flex; flex-direction:column; min-width:0; }
    #loopLabOverlay textarea, #loopLabOverlay input[type=text], #loopLabOverlay select {
      background:var(--sp-panel,#161b22); color:var(--sp-text,#e6edf3); border:1px solid var(--sp-border,#30363d); border-radius:6px; font-size:0.78rem; }
    #loopLabOverlay .ll-spec { flex:1; margin:0.5rem; padding:0.5rem; font-family:ui-monospace,monospace; resize:none; white-space:pre; overflow:auto; }
    #loopLabOverlay .ll-task { margin:0 0.5rem; padding:0.45rem; font-family:inherit; resize:none; height:3.4rem; }
    #loopLabOverlay .ll-row { display:flex; gap:0.4rem; align-items:center; padding:0.5rem; flex-wrap:wrap; }
    #loopLabOverlay .ll-btn { padding:0.4rem 0.8rem; border:1px solid var(--sp-border,#30363d); border-radius:6px; background:var(--sp-panel,#161b22);
      color:var(--sp-text,#e6edf3); cursor:pointer; font-size:0.78rem; }
    #loopLabOverlay .ll-btn.primary { border-color:var(--sp-accent,#58a6ff); color:var(--sp-accent,#58a6ff); }
    #loopLabOverlay .ll-btn.danger { border-color:#f85149; color:#f85149; }
    #loopLabOverlay .ll-trace { flex:1; overflow-y:auto; padding:0.5rem; font-size:0.78rem; }
    #loopLabOverlay .ll-turn { border:1px solid var(--sp-border,#30363d); border-radius:8px; margin-bottom:0.5rem; padding:0.35rem 0.5rem; }
    #loopLabOverlay .ll-turn > .ll-turn-title { font-weight:600; font-size:0.72rem; color:var(--sp-text-dim,#8b949e); margin-bottom:0.25rem; }
    #loopLabOverlay details.ll-stage { margin:0.2rem 0; }
    #loopLabOverlay details.ll-stage summary { cursor:pointer; font-size:0.74rem; color:var(--sp-text,#e6edf3); }
    #loopLabOverlay details.ll-stage pre { margin:0.3rem 0 0.2rem; padding:0.4rem; background:var(--sp-panel,#161b22);
      border-radius:6px; white-space:pre-wrap; word-break:break-word; max-height:260px; overflow-y:auto; font-size:0.72rem; }
    #loopLabOverlay .ll-stage.err summary { color:#f85149; }
    #loopLabOverlay .ll-pad { flex:0 0 34%; display:flex; flex-direction:column; border-top:1px solid var(--sp-border,#30363d); min-height:0; }
    #loopLabOverlay .ll-pad-title { padding:0.35rem 0.6rem; font-size:0.72rem; font-weight:600; color:var(--sp-text-dim,#8b949e); display:flex; justify-content:space-between; }
    #loopLabOverlay .ll-pad pre { flex:1; margin:0 0.5rem 0.5rem; padding:0.45rem; overflow:auto; background:var(--sp-panel,#161b22);
      border-radius:6px; font-size:0.72rem; white-space:pre-wrap; }
    #loopLabOverlay .ll-note { color:var(--sp-text-dim,#8b949e); font-size:0.72rem; padding:0.15rem 0.2rem; }
    #loopLabOverlay .ll-live-body { display:flex; flex-direction:column; gap:0.25rem; }
    #loopLabOverlay pre.ll-text { margin:0.2rem 0; padding:0.4rem; background:var(--sp-panel,#161b22); border-radius:6px;
      white-space:pre-wrap; word-break:break-word; max-height:260px; overflow-y:auto; font-size:0.72rem; }
    #loopLabOverlay details.ll-tc summary { color:var(--sp-accent,#58a6ff); }
    #loopLabOverlay details.ll-tr summary { color:var(--sp-text-dim,#8b949e); }
    #loopLabOverlay details.ll-tc pre, #loopLabOverlay details.ll-tr pre { margin:0.25rem 0; padding:0.4rem;
      background:var(--sp-panel,#161b22); border-radius:6px; white-space:pre-wrap; word-break:break-word;
      max-height:240px; overflow-y:auto; font-size:0.72rem; }
    #loopLabOverlay .ll-tr-img { margin:0.25rem 0; }
    #loopLabOverlay .ll-tr-cap { font-size:0.7rem; color:var(--sp-text-dim,#8b949e); margin-bottom:0.15rem; word-break:break-all; }
    #loopLabOverlay img.ll-img { max-width:100%; max-height:320px; border:1px solid var(--sp-border,#30363d); border-radius:6px; display:block; }
  `;

  function buildPanel() {
    if (_panel) return _panel;
    const style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);

    const root = document.createElement('div');
    root.id = 'loopLabOverlay';
    root.style.display = 'none';
    root.innerHTML = `
      <div class="ll-backdrop"></div>
      <div class="ll-modal">
        <div class="ll-head">
          <strong style="font-size:0.9rem;">Loop Lab</strong>
          <span id="llProvider" style="font-size:0.72rem;color:var(--sp-text-dim,#8b949e);"></span>
          <span id="llStats" style="margin-left:auto;font-size:0.72rem;color:var(--sp-text-dim,#8b949e);"></span>
          <button class="ll-btn" id="llCopy" title="Copy the full run output — all turns, filled prompts, stage outputs, scratchpad snapshots">⧉ Copy run</button>
          <button class="ll-btn" id="llClose" title="Close (Esc)">✕</button>
        </div>
        <div class="ll-body">
          <div class="ll-left">
            <div class="ll-row">
              <select id="llSelect" style="flex:1;padding:0.35rem;"></select>
              <button class="ll-btn" id="llNew" title="New loop from the example template">New</button>
              <button class="ll-btn" id="llSave" title="Save spec under its name">Save</button>
              <button class="ll-btn danger" id="llDelete" title="Delete selected loop">Del</button>
            </div>
            <textarea id="llSpec" class="ll-spec" spellcheck="false"></textarea>
            <div class="ll-note" style="padding:0 0.6rem;">Stages: llm | tool | js | foreach (inner sees \${item} \${itemIndex}) · per-stage when: skip-guard (JS expr) · vars: \${task} \${turn} \${scratchpad} \${toolSchemas} + saveAs vars · stopWhen: JS expr over scratchpad</div>
            <textarea id="llTask" class="ll-task" placeholder="Task for the loop, e.g. 'List the files in /, read the most interesting one, record 3 facts about it.'"></textarea>
            <div class="ll-row">
              <button class="ll-btn primary" id="llRun">▶ Run</button>
              <button class="ll-btn danger" id="llStop" style="display:none;">■ Stop</button>
              <span id="llStatus" class="ll-note"></span>
            </div>
          </div>
          <div class="ll-right">
            <div class="ll-trace" id="llTrace"></div>
            <div class="ll-pad">
              <div class="ll-pad-title"><span>SCRATCHPAD (live)</span><span id="llPadSize"></span></div>
              <pre id="llPad">{}</pre>
            </div>
          </div>
        </div>
      </div>`;
    document.body.appendChild(root);
    _panel = root;

    const $id = (i) => root.querySelector('#' + i);

    /* loop list */
    function refreshList(selectName) {
      const loops = ensureExample();
      const sel = $id('llSelect');
      sel.innerHTML = '';
      for (const name of Object.keys(loops).sort()) {
        const o = document.createElement('option');
        o.value = o.textContent = name;
        sel.appendChild(o);
      }
      const want = selectName || localStorage.getItem(K_LAST) || sel.options[0]?.value;
      if (want && loops[want]) sel.value = want;
      loadSelected();
    }
    function loadSelected() {
      const loops = loadLoops();
      const name = $id('llSelect').value;
      if (name && loops[name]) {
        $id('llSpec').value = loops[name];
        localStorage.setItem(K_LAST, name);
      }
    }
    $id('llSelect').onchange = loadSelected;
    $id('llNew').onclick = () => {
      const name = prompt('Loop name:', 'my-loop-' + Object.keys(loadLoops()).length);
      if (!name) return;
      const loops = loadLoops();
      const spec = JSON.parse(JSON.stringify(EXAMPLE));
      spec.name = name;
      loops[name] = JSON.stringify(spec, null, 2);
      saveLoops(loops);
      refreshList(name);
    };
    $id('llSave').onclick = () => {
      let spec;
      try { spec = JSON.parse($id('llSpec').value); } catch (e) { $id('llStatus').textContent = 'Invalid JSON: ' + e.message; return; }
      const err = validateSpec(spec);
      if (err) { $id('llStatus').textContent = err; return; }
      const loops = loadLoops();
      loops[spec.name || $id('llSelect').value] = JSON.stringify(spec, null, 2);
      saveLoops(loops);
      refreshList(spec.name);
      $id('llStatus').textContent = 'Saved.';
    };
    $id('llDelete').onclick = () => {
      const name = $id('llSelect').value;
      if (!name || !confirm('Delete loop "' + name + '"?')) return;
      const loops = loadLoops();
      delete loops[name];
      saveLoops(loops);
      refreshList();
    };

    /* run UI adapter */
    const MAX_DOM_TURNS = 5;   // keep only the last N turns in the DOM (rest → Copy run)
    const ui = {
      _atBottom: true,
      _scrollRAF: 0,
      // Coalesced autoscroll: at most once per frame, and only if the user is already
      // near the bottom (so scrolling up to read isn't yanked back). Sets scrollTop
      // directly — far cheaper than scrollIntoView (no forced full-document layout).
      _scroll() {
        if (this._atBottom === false || this._scrollRAF) return;
        this._scrollRAF = requestAnimationFrame(() => {
          this._scrollRAF = 0;
          const t = $id('llTrace'); if (t) t.scrollTop = t.scrollHeight;
        });
      },
      addTurn(n) {
        const trace = $id('llTrace');
        const d = document.createElement('div');
        d.className = 'll-turn';
        d.innerHTML = '<div class="ll-turn-title">TURN ' + n + '</div>';
        trace.appendChild(d);
        // Bound DOM growth: drop the oldest turns beyond MAX_DOM_TURNS. This is the
        // fix for the loop getting slower over time — the trace no longer accumulates
        // thousands of nodes. Full history is preserved in the Copy-run transcript.
        const turns = trace.querySelectorAll('.ll-turn');
        if (turns.length > MAX_DOM_TURNS) {
          for (let i = 0; i < turns.length - MAX_DOM_TURNS; i++) turns[i].remove();
          if (!this._pruned) {
            this._pruned = true;
            const b = document.createElement('div');
            b.className = 'll-note';
            b.textContent = '(older turns hidden to keep the UI fast — full detail in ⧉ Copy run)';
            trace.insertBefore(b, trace.firstChild);
          }
        }
        this._scroll();
        return d;
      },
      stageStart(turnHost, name, kind) {
        const el = document.createElement('div');
        el.className = 'll-note';
        el.dataset.pending = name;
        el.textContent = '⏳ ' + name + ' (' + kind + ')…';
        turnHost.appendChild(el);
        this._scroll();
      },
      // The live element for the currently-running stage: an open <details> whose
      // body holds interleaved blocks (streamed text <pre>, tool-call/result boxes,
      // images) in arrival order. Created lazily on first output; agentDone() freezes
      // it in place (keeping all blocks), _finish() replaces it (text-only stages).
      _liveBody(turnHost, name) {
        let live = turnHost.querySelector('details.ll-live');
        if (!live) {
          const pending = turnHost.querySelector('[data-pending]');
          if (pending) pending.remove();
          live = document.createElement('details');
          live.className = 'll-stage ll-live';
          live.open = true;
          const sum = document.createElement('summary');
          sum.textContent = '▶ ' + name + ' (generating…)';
          const bodyEl = document.createElement('div');
          bodyEl.className = 'll-live-body';
          live.appendChild(sum); live.appendChild(bodyEl);
          turnHost.appendChild(live);
        }
        return live.querySelector('.ll-live-body');
      },
      // Streamed text tokens → the trailing text <pre> (a new one starts after any
      // tool block, so text and tool activity stay in order).
      stageStream(turnHost, name, chunk) {
        if (!chunk) return;
        const body = this._liveBody(turnHost, name);
        let pre = body.lastElementChild;
        if (!pre || !pre.classList || !pre.classList.contains('ll-text')) {
          pre = document.createElement('pre'); pre.className = 'll-text'; body.appendChild(pre);
        }
        // Append a text node (O(1)) rather than `textContent +=` (which re-serializes
        // the whole node every token → O(n²) over a long stream).
        pre.appendChild(document.createTextNode(chunk));
        this._scroll();
      },
      // A tool call: collapsible box with the tool name + full arguments (pretty JSON).
      agentToolCall(turnHost, name, args) {
        const body = this._liveBody(turnHost, name);
        const d = document.createElement('details');
        d.className = 'll-tc';
        const s = document.createElement('summary');
        s.textContent = '⚙ ' + (name || 'tool');
        const pre = document.createElement('pre');
        let a = args;
        try { a = JSON.stringify(typeof args === 'string' ? JSON.parse(args) : args, null, 2); } catch (_) { a = String(args); }
        pre.textContent = a;
        d.appendChild(s); d.appendChild(pre); body.appendChild(d);
        this._scroll();
      },
      // A tool result: image:PATH → inline <img> (resolved from OPFS, same convention
      // as the main chat); artifact:PATH → labelled path; otherwise the result body.
      agentToolResult(turnHost, name, result) {
        const body = this._liveBody(turnHost, name);
        const txt = String(result == null ? '' : result);
        if (txt.startsWith('image:')) {
          const path = txt.slice(6);
          const wrap = document.createElement('div'); wrap.className = 'll-tr-img';
          const cap = document.createElement('div'); cap.className = 'll-tr-cap'; cap.textContent = '🖼 ' + (name || 'image') + ' → ' + path;
          const img = document.createElement('img'); img.className = 'll-img'; img.alt = path;
          wrap.appendChild(cap); wrap.appendChild(img); body.appendChild(wrap);
          try {
            if (typeof SandpieImages !== 'undefined' && SandpieImages.dataUrlFromPath) {
              SandpieImages.dataUrlFromPath(path).then(u => { if (u) img.src = u; else cap.textContent += ' (not found)'; }).catch(() => { cap.textContent += ' (load failed)'; });
            } else { cap.textContent += ' (image renderer unavailable)'; }
          } catch (_) {}
          this._scroll();
          return;
        }
        const d = document.createElement('details');
        d.className = 'll-tr';
        const s = document.createElement('summary');
        const isArtifact = txt.startsWith('artifact:');
        s.textContent = (isArtifact ? '📄 artifact ' : '↩ result ') + (name || '') + ' · ' + txt.length + ' chars';
        const pre = document.createElement('pre');
        pre.textContent = txt.length > 4000 ? txt.slice(0, 4000) + '\n…(' + (txt.length - 4000) + ' more chars)' : txt;
        d.appendChild(s); d.appendChild(pre); body.appendChild(d);
        this._scroll();
      },
      // Freeze the agent stage's live element in place (do NOT discard — it holds the
      // tool-call/result/image blocks the user wants to keep). Falls back to a plain
      // done entry if nothing streamed (e.g. empty output).
      agentDone(turnHost, name, ms) {
        const pending = turnHost.querySelector('[data-pending]');
        if (pending) pending.remove();
        const live = turnHost.querySelector('details.ll-live');
        if (!live) { this.stageDone(turnHost, name, '(no output)', ms); return; }
        live.classList.remove('ll-live');
        const sum = live.querySelector('summary');
        if (sum) sum.textContent = '✔ ' + name + ' · ' + (ms / 1000).toFixed(1) + 's';
      },
      _finish(turnHost, name, cls, summaryText, body) {
        const pending = turnHost.querySelector('[data-pending]');
        if (pending) pending.remove();
        const live = turnHost.querySelector('details.ll-live');   // drop the live stream; the clean final details replaces it
        if (live) live.remove();
        const det = document.createElement('details');
        det.className = 'll-stage' + (cls ? ' ' + cls : '');
        const sum = document.createElement('summary');
        sum.textContent = summaryText;
        const pre = document.createElement('pre');
        pre.textContent = typeof body === 'string' ? body : JSON.stringify(body, null, 2);
        det.appendChild(sum); det.appendChild(pre);
        turnHost.appendChild(det);
        this._scroll();
      },
      stageDone(turnHost, name, out, ms) {
        this._finish(turnHost, name, '', '✔ ' + name + ' · ' + (ms / 1000).toFixed(1) + 's', out ?? '(empty)');
      },
      stageError(turnHost, name, msg) {
        this._finish(turnHost, name, 'err', '✖ ' + name + ' — error', msg);
      },
      note(msg) {
        rec('· ' + msg);
        const el = document.createElement('div');
        el.className = 'll-note';
        el.textContent = msg;
        $id('llTrace').appendChild(el);
        this._scroll();
      },
      setScratchpad(sp) {
        const json = JSON.stringify(sp, null, 2);
        $id('llPad').textContent = json;
        $id('llPadSize').textContent = json.length + ' chars';
      },
      setStats(s, final) {
        const secs = ((Date.now() - s.started) / 1000).toFixed(0);
        $id('llStats').textContent = s.llmCalls + ' LLM calls · ' + s.toolCalls + ' tools · ' + secs + 's' + (final ? ' · done' : '');
      },
      setRunning(on) {
        $id('llRun').style.display = on ? 'none' : '';
        $id('llStop').style.display = on ? '' : 'none';
        $id('llStatus').textContent = on ? 'Running…' : '';
        $id('llSpec').disabled = on;
      },
    };

    // Track whether the user is near the bottom so autoscroll only follows when they
    // haven't scrolled up to read. Programmatic scrollTop writes also fire this and
    // keep _atBottom true. Reset to bottom-follow at the start of each run.
    $id('llTrace').addEventListener('scroll', () => {
      const t = $id('llTrace'); if (!t) return;
      ui._atBottom = (t.scrollHeight - t.scrollTop - t.clientHeight) < 80;
    }, { passive: true });

    $id('llRun').onclick = async () => {
      if (_run) return;
      let spec;
      try { spec = JSON.parse($id('llSpec').value); } catch (e) { $id('llStatus').textContent = 'Invalid JSON: ' + e.message; return; }
      const err = validateSpec(spec);
      if (err) { $id('llStatus').textContent = err; return; }
      const task = $id('llTask').value.trim();
      if (!task) { $id('llStatus').textContent = 'Enter a task first.'; return; }
      localStorage.setItem(K_TASK, task);
      $id('llTrace').innerHTML = '';
      ui._atBottom = true; ui._pruned = false;   // fresh run: follow the bottom again
      _transcript = ['=== LOOP "' + (spec.name || '?') + '" · ' + new Date().toISOString() + ' ===', 'TASK:\n' + task];
      ui.setScratchpad(spec.scratchpad || {});
      try { await runLoop(spec, task, ui); } catch (e) { ui.note('Fatal: ' + (e.message || e)); ui.setRunning(false); }
    };
    $id('llStop').onclick = () => { if (_run) _run.ctrl.abort(); };
    $id('llCopy').onclick = async () => {
      const btn = $id('llCopy');
      const text = await fullTranscript();   // OPFS-flushed prefix + in-RAM tail
      let ok = false;
      try { await navigator.clipboard.writeText(text); ok = true; } catch (_) {
        // clipboard API can be denied — fall back to a hidden textarea
        try {
          const ta = document.createElement('textarea');
          ta.value = text; document.body.appendChild(ta); ta.select();
          ok = document.execCommand('copy'); ta.remove();
        } catch (_) {}
      }
      btn.textContent = ok ? '✓ Copied' : '✕ Copy failed';
      setTimeout(() => { btn.textContent = '⧉ Copy run'; }, 1500);
    };

    $id('llClose').onclick = close;
    root.querySelector('.ll-backdrop').onclick = close;
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && root.style.display !== 'none') close();
    });

    $id('llTask').value = localStorage.getItem(K_TASK) || '';
    refreshList();
    return root;
  }

  function open() {
    const p = buildPanel();
    const prov = (typeof SandpieProviders !== 'undefined') ? SandpieProviders.getActive() : null;
    const label = prov ? ((prov.type || 'api') + ' · ' + (prov.model || prov.endpoint || '?')) : 'no provider';
    p.querySelector('#llProvider').textContent = label;
    p.style.display = 'flex';
  }
  function close() {
    if (!_panel) return;
    if (_run && !confirm('A loop is running — close anyway? (It keeps running.)')) return;
    _panel.style.display = 'none';
  }

  /* Loop Lab: access via >>> loop-lab command */

  if (typeof SandpieCommands !== 'undefined') {
    SandpieCommands.register({
      name: 'loop-lab',
      module: 'loop-lab',
      help: 'Open the Loop Lab panel',
      usage: '>>> loop-lab',
      run() { open(); return 'Loop Lab opened.'; },
    });
  }

  window.SandpieLoopLab = { open, close, runLoop, fullTranscript, get running() { return !!_run; }, get transcript() { return _transcript.join('\n\n'); } };
})();
