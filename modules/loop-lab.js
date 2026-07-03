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
 *     ] }
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

  /* ================= persistence ================= */
  function loadLoops() {
    try { return JSON.parse(localStorage.getItem(K_LOOPS) || '{}'); } catch (_) { return {}; }
  }
  function saveLoops(loops) { localStorage.setItem(K_LOOPS, JSON.stringify(loops)); }
  function ensureExample() {
    const loops = loadLoops();
    if (!Object.keys(loops).length) {
      loops[EXAMPLE.name] = JSON.stringify(EXAMPLE, null, 2);
      saveLoops(loops);
    }
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
  async function localOnce(engine, prov, { system, user, signal }) {
    let out = '';
    await engine.runConversation(
      { provider: prov, messages: [{ role: 'user', content: user }], systemPrompt: system || '', tools: [], convId: 'loop-lab', signal },
      (ev) => {
        if (ev && ev.type === 'message_added' && ev.message && ev.message.role === 'assistant') {
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
    return httpOnce(opts);
  }

  /* ================= tool runner (shared worker RPC) ================= */
  function runTool(name, args, signal) {
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
      sw.postMessage({ type: 'tool', id, name, args, conversation_file_name: 'loop-lab' });
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

  /* ================= run engine ================= */
  let _run = null;   // { ctrl, stats }

  function validateSpec(spec) {
    if (!spec || typeof spec !== 'object') return 'Spec is not an object.';
    if (!Array.isArray(spec.stages) || !spec.stages.length) return 'Spec needs a non-empty "stages" array.';
    for (const st of spec.stages) {
      if (!st.name) return 'Every stage needs a "name".';
      if (!['llm', 'tool', 'js'].includes(st.type)) return 'Stage "' + st.name + '": type must be llm | tool | js.';
      if (st.type === 'tool' && !st.argsFrom) return 'Tool stage "' + st.name + '" needs "argsFrom" (a var holding {tool, arguments}).';
      if (st.type === 'js' && typeof st.code !== 'string') return 'JS stage "' + st.name + '" needs a "code" string.';
    }
    return null;
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

    try {
      for (let turn = 1; turn <= maxTurns && !stopped; turn++) {
        if (ctrl.signal.aborted) break;
        const turnHost = ui.addTurn(turn);
        const vars = {
          task, turn,
          get scratchpad() { return JSON.stringify(scratchpad, null, 2); },
          toolSchemas: JSON.stringify(toolSchemas, null, 2),
        };

        for (const st of spec.stages) {
          if (ctrl.signal.aborted) { stopped = true; break; }
          const t0 = Date.now();
          try {
            if (st.type === 'llm') {
              stats.llmCalls++;
              ui.stageStart(turnHost, st.name, 'llm');
              const raw = await llmOnce({
                system: fill(st.system, vars), user: fill(st.user, vars),
                temperature: st.temperature, maxTokens: st.maxTokens, signal: ctrl.signal,
              });
              let out = raw;
              if (st.parse === 'json') {
                out = parseJSON(raw);
                if (out === null) throw new Error('stage "' + st.name + '": model output is not valid JSON:\n' + raw.slice(0, 400));
              } else if (st.parse && st.parse.startsWith('block:')) {
                out = parseBlock(raw, st.parse.slice(6));
              }
              if (st.saveAs) vars[st.saveAs] = out;
              if (st.mergeScratchpad && out && typeof out === 'object' && !Array.isArray(out)) Object.assign(scratchpad, out);
              ui.stageDone(turnHost, st.name, out, Date.now() - t0);
            } else if (st.type === 'tool') {
              const call = vars[st.argsFrom];
              if (!call || typeof call !== 'object' || !call.tool) throw new Error('stage "' + st.name + '": var "' + st.argsFrom + '" does not hold {tool, arguments}.');
              if (call.tool === 'none' || call.tool === 'done') {
                if (st.saveAs) vars[st.saveAs] = '(no tool needed)';
                ui.stageDone(turnHost, st.name, '(no tool needed — skipped)', Date.now() - t0);
              } else {
                stats.toolCalls++;
                ui.stageStart(turnHost, st.name, 'tool ' + call.tool);
                const result = await runTool(call.tool, call.arguments || {}, ctrl.signal);
                if (st.saveAs) vars[st.saveAs] = String(result).slice(0, st.maxChars || 4000);
                ui.stageDone(turnHost, st.name + ' (' + call.tool + ')', String(result).slice(0, 4000), Date.now() - t0);
              }
            } else if (st.type === 'js') {
              ui.stageStart(turnHost, st.name, 'js');
              const logs = [];
              const fn = new Function('ctx', st.code);
              const ret = fn({ vars, scratchpad, turn, task, log: (m) => logs.push(String(m)) });
              if (ret && ret.stop) stopped = true;
              ui.stageDone(turnHost, st.name, (logs.join('\n') || '(ok)') + (ret && ret.stop ? '\n→ stop requested' : ''), Date.now() - t0);
            }
          } catch (e) {
            if (e && e.name === 'AbortError') { stopped = true; break; }
            ui.stageError(turnHost, st.name, e.message || String(e));
            scratchpad.last_error = String(e.message || e).slice(0, 500);
            break;   // abandon this turn's remaining stages, let the next turn recover
          }
          ui.setScratchpad(scratchpad);
          ui.setStats(stats);
        }

        if (spec.stopWhen && !stopped) {
          try {
            if (new Function('scratchpad', 'turn', 'return (' + spec.stopWhen + ');')(scratchpad, turn)) {
              ui.note('stopWhen satisfied at turn ' + turn + '.');
              stopped = true;
            }
          } catch (e) { ui.note('stopWhen eval error: ' + e.message); }
        }
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
            <div class="ll-note" style="padding:0 0.6rem;">Stages: llm | tool | js · vars: \${task} \${turn} \${scratchpad} \${toolSchemas} + saveAs vars · stopWhen: JS expr over scratchpad</div>
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
    const ui = {
      addTurn(n) {
        const d = document.createElement('div');
        d.className = 'll-turn';
        d.innerHTML = '<div class="ll-turn-title">TURN ' + n + '</div>';
        $id('llTrace').appendChild(d);
        d.scrollIntoView({ block: 'end' });
        return d;
      },
      stageStart(turnHost, name, kind) {
        const el = document.createElement('div');
        el.className = 'll-note';
        el.dataset.pending = name;
        el.textContent = '⏳ ' + name + ' (' + kind + ')…';
        turnHost.appendChild(el);
        el.scrollIntoView({ block: 'end' });
      },
      _finish(turnHost, name, cls, summaryText, body) {
        const pending = turnHost.querySelector('[data-pending]');
        if (pending) pending.remove();
        const det = document.createElement('details');
        det.className = 'll-stage' + (cls ? ' ' + cls : '');
        const sum = document.createElement('summary');
        sum.textContent = summaryText;
        const pre = document.createElement('pre');
        pre.textContent = typeof body === 'string' ? body : JSON.stringify(body, null, 2);
        det.appendChild(sum); det.appendChild(pre);
        turnHost.appendChild(det);
        det.scrollIntoView({ block: 'end' });
      },
      stageDone(turnHost, name, out, ms) {
        this._finish(turnHost, name, '', '✔ ' + name + ' · ' + (ms / 1000).toFixed(1) + 's', out ?? '(empty)');
      },
      stageError(turnHost, name, msg) {
        this._finish(turnHost, name, 'err', '✖ ' + name + ' — error', msg);
      },
      note(msg) {
        const el = document.createElement('div');
        el.className = 'll-note';
        el.textContent = msg;
        $id('llTrace').appendChild(el);
        el.scrollIntoView({ block: 'end' });
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
      ui.setScratchpad(spec.scratchpad || {});
      try { await runLoop(spec, task, ui); } catch (e) { ui.note('Fatal: ' + (e.message || e)); ui.setRunning(false); }
    };
    $id('llStop').onclick = () => { if (_run) _run.ctrl.abort(); };

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

  /* ================= sidebar entry ================= */
  function initMenu() {
    if (typeof SandpieMenu === 'undefined') { setTimeout(initMenu, 400); return; }
    SandpieMenu.add('loopLabSection', {
      title: 'Loop Lab',
      badge: null,
      open: false,
      html: `<div style="font-size:0.75rem;line-height:1.45;">
        <p style="color:var(--sp-text-dim);margin:0 0 0.5rem;">Build and test harness loops (small model + systematized scratchpad) in an isolated playground. Nothing here touches conversations or sync.</p>
        <button class="ghost" id="loopLabOpenBtn" style="width:100%;padding:0.45rem;">Open Loop Lab</button>
      </div>`,
      onRender() {
        const b = document.getElementById('loopLabOpenBtn');
        if (b) b.onclick = open;
      },
    });
    console.log('[loop-lab] loaded');
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initMenu);
  else initMenu();

  window.SandpieLoopLab = { open, close, runLoop, get running() { return !!_run; } };
})();
