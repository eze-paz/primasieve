/**
 * Zero-Shot Recursive Agent for Sandpie.
 *
 * Small models fail on multi-turn because context bloats and errors compound.
 * This replaces the normal streaming agent with a recursive zero-shot loop where
 * every turn is a fresh single-shot prompt:
 *
 *   TASK + STATE -> PLANNER  -> RAW PLAN
 *   PLAN + TOOLS + STATE -> COMPRESSOR -> EXECUTION BRIEF
 *   BRIEF + TOOLS -> ACTOR   -> ONE JSON TOOL CALL
 *   OBSERVATION + STATE -> EVALUATOR -> (DONE? NEW STATE)
 *   If not done, loop with NEW STATE.
 *
 * Each sub-agent talks once; its reasoning is shown in the UI but never
 * fed back into the LLM context on the next turn. This keeps every forward
 * pass short and clean -- exactly where small models shine.
 *
 * Usage: <script type="module" src="modules/zeroshot.js?v=1"></script>
 */

const K_ACTIVE       = 'sandpie:zeroshot:active';
const K_MAX_TURNS    = 'sandpie:zeroshot:maxTurns';
const K_PLANNER_TEMP = 'sandpie:zeroshot:plannerTemp';
const K_ACTOR_TEMP   = 'sandpie:zeroshot:actorTemp';
const K_FAILURE_TEMP = 'sandpie:zeroshot:failureTemp';

const DEFAULTS = {
  active: false, maxTurns: 10, plannerTemp: 0.7, actorTemp: 0.2, failureTemp: 0.9,
};

/* ---- config helpers (same pattern as mindframe.js) -------------------- */
function getBool(key, def) {
  const v = localStorage.getItem(key);
  return v === null ? def : v === '1';
}
function setBool(key, v) { localStorage.setItem(key, v ? '1' : '0'); }
function getNum(key, def, min, max) {
  const n = parseFloat(localStorage.getItem(key) || '');
  return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : def;
}
function setNum(key, v) { localStorage.setItem(key, String(v)); }
function cfg() {
  return {
    active:       getBool(K_ACTIVE, DEFAULTS.active),
    maxTurns:     getNum(K_MAX_TURNS, DEFAULTS.maxTurns, 1, 50),
    plannerTemp:  getNum(K_PLANNER_TEMP, DEFAULTS.plannerTemp, 0, 2),
    actorTemp:    getNum(K_ACTOR_TEMP, DEFAULTS.actorTemp, 0, 2),
    failureTemp:  getNum(K_FAILURE_TEMP, DEFAULTS.failureTemp, 0, 2),
  };
}

/* ---- runtime state ---------------------------------------------------- */
let _running = null;   // { convId, turn, state, ctrl }
let _abortCtrl = null;
const _nextId = () => 'zs-' + Math.random().toString(36).slice(2, 11);

/* ---- non-streaming LLM helper --------------------------------------- */
function _buildUrl(endpoint, path) {
  const ep = String(endpoint || '').replace(/\/$/, '');
  const proxy = window.$('proxyUrl') ? window.$('proxyUrl').value : '';
  const full = ep + path;
  if (proxy) {
    try { const u = new URL(proxy); u.searchParams.set('url', full); return u.href; } catch (_) {}
  }
  try { return new URL(full, location.href).href; } catch (_) { return full; }
}

async function _llmCall({ system, user, temperature = null, tools = null, maxTokens = null, signal }) {
  const prov = (typeof SandpieProviders !== 'undefined') ? SandpieProviders.getActive() : null;
  const endpoint = (window.$('endpoint') ? window.$('endpoint').value : '');
  const model = (window.$('model') ? window.$('model').value : (prov && prov.model) || '');
  if (!endpoint || !model) throw new Error('No provider endpoint or model selected.');

  const url = _buildUrl(endpoint, '/chat/completions');
  const messages = [];
  if (system) messages.push({ role: 'system', content: system });
  messages.push({ role: 'user', content: user });

  const body = {
    model,
    messages,
    stream: false,
    max_tokens: maxTokens || (prov && prov.maxTokens) || 8192,
    temperature: temperature != null ? temperature : ((prov && prov.temperature != null) ? prov.temperature : 0.7),
  };
  if (tools && tools.length) body.tools = tools;

  const headers = {
    'Content-Type': 'application/json',
    Authorization: 'Bearer ' + ((window.$('apiKey') ? window.$('apiKey').value : '') || ''),
  };

  const res = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body), signal });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error('HTTP ' + res.status + ' -- ' + text.slice(0, 300));
  }
  const data = await res.json();
  if (data.error) throw new Error(String(data.error.message || JSON.stringify(data.error)));
  const msg = data.choices && data.choices[0] && data.choices[0].message ? data.choices[0].message : {};
  if (!msg.content && Array.isArray(msg.tool_calls) && msg.tool_calls.length) {
    const tc = msg.tool_calls[0];
    try { msg.content = JSON.stringify({ tool: tc.function && tc.function.name, arguments: tc.function && tc.function.arguments ? JSON.parse(tc.function.arguments) : {} }); } catch (_) {}
  }
  return msg;
}

/* ---- tool runner via sandpie-worker --------------------------------- */
function _runToolViaWorker(name, args, convFileName, signal) {
  return new Promise((resolve, reject) => {
    const sw = window._sandpieWorker;
    if (!sw) { reject(new Error('sandpie-worker not ready')); return; }
    const id = _nextId();
    let settled = false;

    const onMsg = (e) => {
      const r = e.data || {};
      if (r.id !== id || r.type !== 'tool_result') return;
      finish(r.result || '');
    };
    const onErr = () => finish('', 'worker crashed');
    const onAbort = () => finish('', 'Aborted');

    function finish(result, err) {
      if (settled) return;
      settled = true;
      cleanup();
      if (err) reject(new Error(err));
      else resolve(result);
    }
    function cleanup() {
      try { sw.removeEventListener('message', onMsg); } catch (_) {}
      try { sw.removeEventListener('error', onErr); } catch (_) {}
      if (signal) try { signal.removeEventListener('abort', onAbort); } catch (_) {}
    }

    try { sw.addEventListener('message', onMsg); } catch (_) {}
    try { sw.addEventListener('error', onErr); } catch (_) {}
    if (signal) signal.addEventListener('abort', onAbort, { once: true });

    sw.postMessage({
      type: 'tool', id, name, args,
      conversation_file_name: convFileName || 'unknown',
      localterm: {
        token: localStorage.getItem('sandpie:localterm:token') || '',
        port: +(localStorage.getItem('sandpie:localterm:port')) || 8771,
      },
    });
    setTimeout(() => finish('', 'tool timed out (120s)'), 120000);
  });
}

/* ---- prompt builders -------------------------------------------------- */
function _plannerPrompt(task, state) {
  return {
    system: `You are the PLANNER. Look at the task and current state. Decide the SINGLE most logical next concrete step. Output ONLY a <PLAN> block. No filler. No tool calls. No greetings.`,
    user: `TASK:\n${task}\n\nCURRENT STATE:\n${typeof state === 'string' ? state : JSON.stringify(state, null, 2)}\n\nAVAILABLE TOOL CATEGORIES:\n- file: read_file, write_file, edit_file, list_files, search\n- web: web_search, read_url\n- compute: run_python\n- artifact: show_artifact\n\nOutput ONLY:\n<PLAN>\nStep: <single concrete next step>\nTool needed: <tool name or none>\nExpected outcome: <what success looks like for this step>\n</PLAN>`,
  };
}

function _compressorPrompt(rawPlan, toolSchemas, state) {
  const needed = toolSchemas.filter(t =>
    rawPlan.toLowerCase().includes(t.function.name.toLowerCase()) ||
    ['read_file','write_file','edit_file','search','list_files','run_python'].includes(t.function.name)
  );
  const seen = new Set();
  const uniq = needed.filter(t => { if (seen.has(t.function.name)) return false; seen.add(t.function.name); return true; });
  const selected = uniq.length ? uniq : toolSchemas.slice(0, 5);
  return {
    system: `You are the COMPRESSOR. Distill the raw plan into a tight Execution Brief containing ONLY the relevant tool schemas and a spec for the actor. Output ONLY a <BRIEF> block. No chat.`,
    user: `RAW PLAN:\n${rawPlan}\n\nCURRENT STATE:\n${typeof state === 'string' ? state : JSON.stringify(state, null, 2)}\n\nSELECTED TOOL SCHEMAS:\n${JSON.stringify(selected, null, 2)}\n\nOutput ONLY:\n<BRIEF>\ngoal: <one-line sub-goal>\ntool: <exact tool name>\nparameters: <key=value guidance>\nconstraints: <known constraints>\n</BRIEF>`,
  };
}

function _actorPrompt(brief, selectedTools) {
  return {
    system: `You are the ACTOR. Emit EXACTLY ONE valid JSON object representing a tool call.\nRules:\n- Output ONLY the JSON object. No markdown, no explanation, no thinking tags.\n- Must match the tool schema exactly.\n- If no tool is needed, output {"tool":"none","arguments":{}}`,
    user: `EXECUTION BRIEF:\n${brief}\n\nTOOL SCHEMAS:\n${JSON.stringify(selectedTools, null, 2)}\n\nProduce EXACTLY ONE JSON object:\n{\n  "tool": "<tool_name>",\n  "arguments": { ... }\n}`,
  };
}

function _evaluatorPrompt(task, brief, observation, state) {
  return {
    system: `You are the EVALUATOR. Review the tool result and task. Output ONLY a JSON object with this exact shape:\n{"done":true|false,"state":{"goal":"...","progress":"...","next":"...","errors":[]},"reasoning":"..."}\nNo markdown outside the JSON.`,
    user: `ORIGINAL TASK: ${task}\n\nPREVIOUS STATE:\n${typeof state === 'string' ? state : JSON.stringify(state, null, 2)}\n\nEXECUTION BRIEF:\n${brief}\n\nTOOL RESULT (first 4000 chars):\n${String(observation).slice(0, 4000)}\n\nYour JSON output:`,
  };
}

/* ---- content extractors --------------------------------------------- */
function extractJSON(raw) {
  const text = String(raw || '').trim();
  const m = text.match(/\`\`\`(?:json)?\s*([\s\S]*?)\`\`\`/);
  if (m) { try { return JSON.parse(m[1].trim()); } catch (_) {} }
  const s = text.indexOf('{');
  const e = text.lastIndexOf('}');
  if (s !== -1 && e > s) { try { return JSON.parse(text.slice(s, e + 1)); } catch (_) {} }
  return null;
}
function extractBlock(raw, tag) {
  const text = String(raw || '');
  const re = new RegExp(`<${tag}>\\s*([\\s\\S]*?)\\s*</${tag}>`, 'i');
  const m = text.match(re);
  return m ? m[1].trim() : text.trim();
}

/* ---- UI helpers ------------------------------------------------------ */
function _addInfo(text, host = null)  { if (typeof addMsg !== 'function') return null; try { return addMsg('info', text, host); } catch (_) { return null; } }
function _addAsst(text, host = null)  { if (typeof addMsg !== 'function') return null; try { return addMsg('assistant', text, host); } catch (_) { return null; } }
function _addErr(text, host = null)   { if (typeof addMsg !== 'function') return null; try { return addMsg('err', text, host); } catch (_) { return null; } }
function _addUser(text, host = null)  { if (typeof addMsg !== 'function') return null; try { return addMsg('user', text, host); } catch (_) { return null; } }

function _tcDiv(tool, args, host = null) {
  if (typeof addMsg !== 'function') return null;
  try {
    const d = addMsg('tool-call', '', host);
    if (!d) return null;
    d.dataset.fname = tool;
    d.dataset.tcId = _nextId();
    const exp = d.querySelector('.tc-expanded');
    if (exp) {
      exp.innerHTML = '';
      try { if (typeof buildToolBox === 'function') { const b = buildToolBox(JSON.stringify(args || {}), tool); if (b) exp.appendChild(b); } } catch (_) {}
    }
    if (typeof renderTcDone === 'function') renderTcDone(d, tool);
    return d;
  } catch (_) { return null; }
}
function _tcResult(div, text) {
  if (!div) return;
  try { if (typeof appendToolResult === 'function') appendToolResult(div.dataset.tcId || '', String(text).slice(0, 8000), null); } catch (_) {}
}

/* ---- main zero-shot loop -------------------------------------------- */
async function runLoop(convId, task, allTools, stream = null) {
  const c = cfg();
  const ctrl = new AbortController();
  _abortCtrl = ctrl;

  let state = { goal: task, progress: 'Starting zero-shot loop.', next: 'Analyze the task and choose the first tool.', errors: [] };
  _running = { convId, turn: 0, state, ctrl };

  const host = stream && stream.host ? stream.host : null;

  /* Tie zeroshot abort to stream abort */
  if (stream && stream.abort && stream.abort.signal) {
    stream.abort.signal.addEventListener('abort', () => ctrl.abort(), { once: true });
  }

  const pushMsg = (role, content) => {
    if (!stream || !stream.messages) return;
    const msg = { role, content };
    stream.messages.push(msg);
    return msg;
  };

  _addInfo('Zero-shot agent ON -- max ' + c.maxTurns + ' turns', host);

  let done = false;
  let lastErr = null;

  try {
    for (let turn = 1; turn <= c.maxTurns; turn++) {
      if (ctrl.signal.aborted) { _addInfo('Zero-shot agent stopped by user.', host); break; }
      _running.turn = turn;
      _running.state = state;
      state.errors = [];

      /* 1. PLANNER */
      _addInfo('Turn ' + turn + ' > Planner', host);
      let planRaw;
      try { planRaw = await _llmCall({ ..._plannerPrompt(task, state), temperature: c.plannerTemp, signal: ctrl.signal }); }
      catch (e) { lastErr = 'Planner: ' + e.message; break; }
      const plan = extractBlock((planRaw.content || planRaw), 'PLAN');
      _addAsst('**Planner:**\n\n```\n' + plan + '\n```', host);
      pushMsg('assistant', '[Planner]\n\n' + plan);

      /* 2. COMPRESSOR */
      let briefRaw;
      try { briefRaw = await _llmCall({ ..._compressorPrompt(plan, allTools, state), temperature: 0.2, signal: ctrl.signal }); }
      catch (e) { lastErr = 'Compressor: ' + e.message; break; }
      const brief = extractBlock((briefRaw.content || briefRaw), 'BRIEF');
      _addAsst('**Brief:**\n\n```\n' + brief + '\n```', host);
      pushMsg('assistant', '[Brief]\n\n' + brief);

      /* Select tools actually needed for this turn */
      const bLow = brief.toLowerCase();
      const relevant = allTools.filter(t =>
        bLow.includes(t.function.name.toLowerCase()) ||
        ['read_file','write_file','edit_file','search','list_files','run_python'].includes(t.function.name)
      );
      const seen = new Set();
      const dedup = [];
      for (const t of relevant) { if (!seen.has(t.function.name)) { seen.add(t.function.name); dedup.push(t); } }
      const actorTools = dedup.length ? dedup : allTools.slice(0, 5);

      /* 3. ACTOR */
      let toolCall = null;
      let aTemp = c.actorTemp;
      let attempts = 0;
      const MAXA = 3;
      while (attempts < MAXA && !toolCall && !ctrl.signal.aborted) {
        attempts++;
        let aRaw;
        try { aRaw = await _llmCall({ ..._actorPrompt(brief, actorTools), temperature: aTemp, tools: actorTools, signal: ctrl.signal }); }
        catch (e) { lastErr = 'Actor: ' + e.message; break; }
        toolCall = extractJSON(aRaw.content || aRaw);
        if (!toolCall || !toolCall.tool) {
          toolCall = null;
          aTemp = Math.min(2.0, aTemp + ((c.failureTemp - c.actorTemp) / 2));
          if (attempts < MAXA) _addInfo('Actor retry ' + attempts + ' (temp=' + aTemp.toFixed(2) + ')', host);
        }
      }
      if (!toolCall || !toolCall.tool) { lastErr = 'Actor failed after ' + MAXA + ' attempts.'; break; }

      const tcd = _tcDiv(toolCall.tool, toolCall.arguments || {}, host);

      pushMsg('assistant', '[Actor]\n\nTool: ' + toolCall.tool + '\nArgs: ' + JSON.stringify(toolCall.arguments || {}));

      /* 4. EXECUTE */
      let obs;
      if (toolCall.tool === 'none' || toolCall.tool === 'done') {
        obs = 'No tool needed; task may be complete.';
        done = true;
        pushMsg('assistant', '[Actor]\n\nTool: none\nTask complete.');
      } else {
        try {
          obs = await _runToolViaWorker(toolCall.tool, toolCall.arguments || {}, convId, ctrl.signal);
          _tcResult(tcd, obs);
          pushMsg('tool', JSON.stringify({ name: toolCall.tool, result: obs }, null, 2));
        } catch (e) {
          obs = 'Error: ' + e.message;
          state.errors.push(obs);
          _tcResult(tcd, obs);
          pushMsg('tool', JSON.stringify({ name: toolCall.tool, error: obs }, null, 2));
        }
      }

      /* 5. EVALUATOR */
      let evalRaw;
      try { evalRaw = await _llmCall({ ..._evaluatorPrompt(task, brief, obs, state), temperature: 0.1, signal: ctrl.signal }); }
      catch (e) { lastErr = 'Evaluator: ' + e.message; break; }
      const ev = extractJSON(evalRaw.content || evalRaw);
      if (ev) {
        if (ev.done) done = true;
        if (ev.state) state = { ...state, ...ev.state };
        if (ev.reasoning) {
          _addAsst('**Evaluator:** ' + ev.reasoning, host);
          pushMsg('assistant', '[Evaluator]\n\n' + ev.reasoning);
        }
      }

      /* Detect repeated identical errors and inject escape hint */
      if (state.errors.length >= 2 && state.errors[state.errors.length - 1] === state.errors[state.errors.length - 2]) {
        _addInfo('Repeated error detected -- forcing a different approach.', host);
        state.next = 'Try a completely different approach; the current one is failing.';
      }

      if (done) {
        _addAsst('Task completed in ' + turn + ' turn(s).', host);
        pushMsg('assistant', '[System] Task completed in ' + turn + ' turn(s).');
        break;
      }
    }
  } finally {
    _running = null;
    _abortCtrl = null;
  }

  if (!done && !lastErr && !ctrl.signal.aborted) {
    _addErr('Max turns (' + c.maxTurns + ') reached without completion.', host);
    pushMsg('assistant', '[System] Max turns (' + c.maxTurns + ') reached without completion.');
  } else if (lastErr) {
    _addErr('Zero-shot error: ' + lastErr, host);
    pushMsg('assistant', '[System] Error: ' + lastErr);
  }
}

/* ---- public API ------------------------------------------------------ */
const Zeroshot = {
  isActive() { return getBool(K_ACTIVE, DEFAULTS.active); },

  get runningLoop() {
    return _running ? { convId: _running.convId, turn: _running.turn, state: JSON.parse(JSON.stringify(_running.state)) } : null;
  },

  async start(convId, task, tools) {
    if (_running) throw new Error('A zero-shot loop is already running.');
    return runLoop(convId, task, tools);
  },

  stop() {
    if (_abortCtrl) { _abortCtrl.abort(); return true; }
    return false;
  },
};
window.SandpieZeroshot = Zeroshot;

/* ---- handleSubmit interception -------------------------------------- */
let _intercepted = false;
function intercept() {
  if (_intercepted) return;
  const orig = window.handleSubmit;
  if (!orig) { setTimeout(intercept, 600); return; }
  _intercepted = true;
  console.log('[zeroshot] handleSubmit intercepted');

  window.handleSubmit = async function() {
    if (!Zeroshot.isActive()) return orig.apply(this, arguments);

    /* While running, Send acts as Stop */
    if (Zeroshot.runningLoop) {
      _addInfo('Stopping zero-shot agent...');
      Zeroshot.stop();
      return;
    }

    const text = window.$('input') ? (window.$('input').value || '').trim() : '';
    if (!text && !(typeof SandpieImages !== 'undefined' && SandpieImages.hasAttachment && SandpieImages.hasAttachment())) return;

    /* Respect image attachments exactly like normal handleSubmit */
    const content = (typeof SandpieImages !== 'undefined' && SandpieImages.buildContent)
      ? await SandpieImages.buildContent(text)
      : text;
    if (typeof SandpieImages !== 'undefined' && SandpieImages.hasAttachment && SandpieImages.hasAttachment()) {
      SandpieImages.clear();
    }

    window.$('input').value = '';
    window.$('input').style.height = 'auto';

    const m = window.$('messages');
    if (m) { lockScroll(m); m.scrollTop = m.scrollHeight; }

    /* Integrate with stream lifecycle */
    if (typeof ensureActiveConv === 'function') await ensureActiveConv();
    const convId = activeConvId;
    const s = ensureStream(convId);
    if (s.host.parentNode !== window.$('messages')) mountConv(convId);

    /* Push user message to the stream (the real source of truth) */
    const userMsg = { role: 'user', content: content };
    s.messages.push(userMsg);
    bindBubble(addMsg('user', typeof content === 'string' ? content : text, s.host), userMsg);
    await saveConv(convId);

    /* Set UI to 'sending' so button shows Stop */
    setStreamSending(s, true);
    s.abort = new AbortController();

    const tools = (typeof SandpieTools !== 'undefined' && SandpieTools.schemas)
      ? SandpieTools.schemas() : [];

    try {
      await runLoop(convId, text, tools, s);
    } catch (e) {
      console.error('[zeroshot]', e);
      _addErr('Zero-shot error: ' + (e.message || e), s.host);
    } finally {
      setStreamSending(s, false);
      s.abort = null;
      await saveConv(convId);
      Sandpie.events.emit('generation:complete', { convId, aborted: false });
      try { await Sandpie.sync(); } catch (e) { console.warn('sync failed:', e); }
    }
  };
}

/* ---- sidebar UI (mindframe.js pattern) ------------------------------ */
const SECTION_ID = 'zeroshotSection';

function badge() {
  const r = Zeroshot.runningLoop;
  if (r) return 'T' + r.turn;
  return Zeroshot.isActive() ? 'ON' : 'off';
}

function render() {
  const host = document.getElementById('zeroshotBody');
  if (!host) return;
  const on = Zeroshot.isActive();
  const loop = Zeroshot.runningLoop;
  const c = cfg();
  const canCfg = on && !loop;

  host.innerHTML = `
    <p style="color:var(--sp-text-dim);font-size:0.72rem;line-height:1.4;margin:0 0 0.55rem;">
      <strong>Zero-shot recursive agent.</strong> Every turn is fresh context:
      Planner &rarr; Compressor &rarr; Actor &rarr; Evaluator. Built for small models that choke
      on multi-turn history.
    </p>
    <button id="zsToggle" style="
      width:100%;display:flex;align-items:center;justify-content:space-between;gap:0.5rem;
      padding:0.45rem 0.6rem;border:1px solid ${on ? 'var(--sp-accent,#3fb950)' : 'var(--sp-border)'};
      border-radius:6px;background:${on ? 'rgba(63,185,80,0.12)' : 'transparent'};
      color:var(--sp-text);cursor:pointer;font-size:0.8rem;">
      <span><strong>Zero-shot Loop</strong></span>
      <span style="font-size:0.72rem;color:${on ? '#3fb950' : 'var(--sp-text-dim)'}">${on ? '&#9679; ACTIVE' : '&#9675; off'}${loop ? ' (turn ' + loop.turn + ')' : ''}</span>
    </button>
    <div style="margin-top:0.6rem;display:flex;flex-direction:column;gap:0.5rem;${canCfg ? '' : 'opacity:0.45;pointer-events:none;'}">
      <label style="display:flex;align-items:center;gap:0.5rem;font-size:0.74rem;color:var(--sp-text-dim);">
        <span style="white-space:nowrap">Max turns</span>
        <input id="zsMax" type="number" min="1" max="50" value="${c.maxTurns}" style="flex:1;width:40px;background:transparent;color:var(--sp-text);border:1px solid var(--sp-border);border-radius:4px;padding:0.15rem;">
      </label>
      <label style="display:flex;align-items:center;gap:0.5rem;font-size:0.74rem;color:var(--sp-text-dim);">
        <span style="white-space:nowrap">Planner temp</span>
        <input id="zsPT" type="number" min="0" max="2" step="0.1" value="${c.plannerTemp.toFixed(1)}" style="flex:1;width:40px;background:transparent;color:var(--sp-text);border:1px solid var(--sp-border);border-radius:4px;padding:0.15rem;">
      </label>
      <label style="display:flex;align-items:center;gap:0.5rem;font-size:0.74rem;color:var(--sp-text-dim);">
        <span style="white-space:nowrap">Actor temp</span>
        <input id="zsAT" type="number" min="0" max="2" step="0.1" value="${c.actorTemp.toFixed(1)}" style="flex:1;width:40px;background:transparent;color:var(--sp-text);border:1px solid var(--sp-border);border-radius:4px;padding:0.15rem;">
      </label>
      <label style="display:flex;align-items:center;gap:0.5rem;font-size:0.74rem;color:var(--sp-text-dim);">
        <span style="white-space:nowrap">Failure temp</span>
        <input id="zsFT" type="number" min="0" max="2" step="0.1" value="${c.failureTemp.toFixed(1)}" style="flex:1;width:40px;background:transparent;color:var(--sp-text);border:1px solid var(--sp-border);border-radius:4px;padding:0.15rem;">
      </label>
    </div>
    ${loop ? '<button id="zsStop" class="ghost" style="margin-top:0.5rem;width:100%;padding:0.45rem;background:rgba(248,81,73,0.12);border-color:var(--sp-err);color:var(--sp-err);font-size:0.8rem;">&#9949; Stop (turn ' + loop.turn + ')</button>' : ''}
  `;

  document.getElementById('zsToggle').onclick = () => {
    setBool(K_ACTIVE, !getBool(K_ACTIVE, DEFAULTS.active));
    SandpieMenu.updateBadge(SECTION_ID, badge());
    render();
  };

  const bind = (id, key) => { const el = document.getElementById(id); if (el) el.onchange = (e) => setNum(key, parseFloat(e.target.value)); };
  bind('zsMax', K_MAX_TURNS);
  bind('zsPT', K_PLANNER_TEMP);
  bind('zsAT', K_ACTOR_TEMP);
  bind('zsFT', K_FAILURE_TEMP);

  const stopBtn = document.getElementById('zsStop');
  if (stopBtn) stopBtn.onclick = () => { Zeroshot.stop(); setTimeout(render, 200); };

  if (loop) setTimeout(() => { if (Zeroshot.runningLoop) { SandpieMenu.updateBadge(SECTION_ID, badge()); render(); } }, 2500);
}

function init() {
  if (typeof SandpieMenu === 'undefined') { setTimeout(init, 400); return; }
  SandpieMenu.add(SECTION_ID, {
    title: 'Zero-shot',
    badge: badge(),
    open: false,
    html: '<div id="zeroshotBody" style="font-size:0.75rem;line-height:1.4;"></div>',
    onRender() { render(); },
  });
  intercept();
  console.log('[zeroshot] loaded (active=' + Zeroshot.isActive() + ')');
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();
