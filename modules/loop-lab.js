/**
 * Loop Lab — the RALPH loop, and nothing else.
 *
 * One hardcoded pipeline per turn: PLAN → WORK → SCRIBE → (VERIFY when done-claimed).
 * State = one PROGRESS.md per run (OPFS ralph/<runId>/PROGRESS.md); each turn is
 * fresh-context. No spec editor, no JSON interpreter, no alternate loops — every
 * feature that isn't ralph is a place for a gotcha.
 *
 * The SCRIBE never touches a tool: it emits the ENTIRE new PROGRESS.md as plain text
 * and the HARNESS writes it (a structure guard rejects damaged output and keeps the
 * old file). No edit_file for the model to fight — the cannon that kills that bug class.
 *
 * Kept hard-won fixes: SSE streaming (defeats proxy 504s), retry-forever on transient
 * HTTP, per-stage reasoning off for the scribe, dynamic tool-RPC timeout (no 120s
 * guillotine on long shells), progress structure guard, steering, resume. Tool-result truncation (8kB head+tail) applies ONLY to noisy tools —
 * read_file is NEVER truncated (the harness reads the whole progress file each turn).
 */
(function () {
  'use strict';

  const K_TASK = 'sandpie:looplab:lastTask';

  /* ============ prompts (keep ~3 sentences each) ============ */
  // NO PLANNER LLM. The plan IS the file: the single most important next action, so the "planner" is pure code — read that
  // single most important next action, so the "planner" is pure code — read that
  // section and do it. All boxes checked → verify. Any unchecked item → work on it.
  function sectionBody(body, heading) {
    const re = new RegExp('^##\\s*' + heading + '[^\\n]*$', 'mi');
    const m = String(body || '').match(re);
    if (!m) return '';
    const start = m.index + m[0].length;
    const next = body.indexOf('\n## ', start);
    return body.slice(start, next >= 0 ? next : body.length).trim();
  }
  function planFromFile(body) {
    const checklist = sectionBody(body, 'Checklist');
    const items = checklist.split('\n').filter(l => /^\s*-\s*\[[ xX]\]/.test(l));
    const unchecked = items.filter(l => /\[ \]/.test(l));
    const checked   = items.filter(l => /\[[xX]\]/.test(l));
    const allDone = unchecked.length === 0 && checked.length > 0;
    if (allDone) return { allDone: true, next: '' };
    const firstUnchecked = unchecked[0];
    const next = firstUnchecked ? firstUnchecked.replace(/^-\s*\[ \]\s*/, '').trim() : '';
    return { allDone: false, next: next || 'Explore the codebase relevant to the task and draft a real, concrete checklist of remaining work.' };
  }
  // Prompt TEMPLATES — user-editable in the panel ("Prompts ✎"), persisted in
  // localStorage, filled with ${placeholder}s at call time. Defaults below.
  // Placeholders: ${appSystemPrompt} ${progress} ${planNext} ${ralphFile} ${task}
  const K_PROMPTS = 'sandpie:looplab:prompts';
  const DEFAULT_PROMPTS = {
    work: [
      'You are the WORKER. Do EXACTLY the one action below and verify it actually worked (read files back, run code) — nothing more; do not try to finish the whole task. Use `shell` for the real project on disk (/home/..., absolute paths); read_file/write_file/edit_file are a SEPARATE browser sandbox that cannot see the project, so never use them for real files. You do NOT update any progress file — just do the action and report concretely what you changed and what you verified.',
      '', 'ENVIRONMENT (durable facts — trust unless you observe otherwise):', '${appSystemPrompt}',
      '', 'CURRENT PROGRESS FILE:', '${progress}',
      '', 'THE ONE ACTION:', '${planNext}',
    ].join('\n'),
    scribe: [
      'You are the SCRIBE. OUTPUT THE ENTIRE UPDATED PROGRESS FILE — the full markdown, start ("# PROGRESS") to end, and NOTHING else (no preamble, no code fences, no commentary). The harness overwrites the file with exactly your output, so anything you omit is DELETED. Copy the current content below verbatim, then fold in this iteration: it truthfully reflects the work, stays lean and duplicate-free.',
      'Keep these sections, each exactly once, in this order: "# PROGRESS", "## Task", "## Checklist", "## Lessons" (plus "## Steering" only when it has entries).',
      'The ## Checklist contains ONLY unchecked items (- [ ]). Any item the worker completed this turn is REMOVED from the checklist. If a completed item produced a verifiable, reusable fact, move that fact to ## Lessons as a new bullet. Do NOT keep checked items in the checklist — they bloat the file with stale premises.',
      'Record a fact in ## Lessons ONLY if a tool RESULT shows it (in the trace "→" lines are results = ground truth; the "Final note" is the worker\'s own claim, NOT evidence). A load-bearing claim with no supporting result becomes a new unchecked checklist item instead.',
      'FIRST ITERATION ONLY: copy the environment memories in the user message relevant to THIS task into "## Lessons" as "- [inherited] <fact>" lines. Prefix a lesson [MEMORY] ONLY (rare) for a cross-task environment gotcha NOT recoverable from the repo — never for paths, commands, or addresses.',
      '', 'CURRENT CONTENT (copy this, then apply your update — do NOT shrink it by dropping sections):', '${progress}',
    ].join('\n'),
    verify: [
      'You are the VERIFIER: the planner claims this task is COMPLETE — distrust it and find what is missing, broken, or unverified. Spot-check with tools (`shell` builds/runs/tests the real project on disk; read the files it claims it changed), trusting the strongest evidence over the prose. End with exactly ONE line: "VERDICT: PASS" or "VERDICT: FAIL — <one concrete reason>" (no verdict line = FAIL).',
      '', 'ENVIRONMENT (durable facts — trust unless your checks contradict):', '${appSystemPrompt}',
      '', 'PROGRESS FILE (the claim):', '${progress}',
    ].join('\n'),
  };
  function loadPrompts() {
    try { return Object.assign({}, DEFAULT_PROMPTS, JSON.parse(localStorage.getItem(K_PROMPTS) || '{}')); }
    catch (_) { return Object.assign({}, DEFAULT_PROMPTS); }
  }
  function savePrompt(key, text) {
    const cur = (() => { try { return JSON.parse(localStorage.getItem(K_PROMPTS) || '{}'); } catch (_) { return {}; } })();
    if (text === DEFAULT_PROMPTS[key]) delete cur[key]; else cur[key] = text;
    localStorage.setItem(K_PROMPTS, JSON.stringify(cur));
  }
  function fill(tpl, v) { return String(tpl).replace(/\$\{(\w+)\}/g, (_, k) => (v[k] !== undefined ? String(v[k]) : '')); }
  const P_WORK = (v) => fill(loadPrompts().work, v);
  const P_SCRIBE = (v) => fill(loadPrompts().scribe, v);
  const P_VERIFY = (v) => fill(loadPrompts().verify, v);

  /* ============ LLM plumbing ============ */
  function stripThink(s) {
    s = String(s || '').replace(/<think>[\s\S]*?<\/think>/g, '');
    const i = s.lastIndexOf('</think>');            // Kimi: bare trailing close tag
    return (i >= 0 ? s.slice(i + 8) : s).trim();
  }
  function contentToText(c) {
    if (typeof c === 'string') return c;
    if (Array.isArray(c)) return c.map(p => (p && (p.text || '')) || '').join('');
    return String(c == null ? '' : c);
  }
  function sleepAbortable(ms, signal) {
    return new Promise((res, rej) => {
      const t = setTimeout(() => { cleanup(); res(); }, ms);
      const onAbort = () => { cleanup(); rej(new DOMException('aborted', 'AbortError')); };
      function cleanup() { clearTimeout(t); if (signal) try { signal.removeEventListener('abort', onAbort); } catch (_) {} }
      if (signal) signal.addEventListener('abort', onAbort, { once: true });
    });
  }
  // Retry transient failures (network, 5xx incl. 504, 429) forever with backoff.
  async function fetchRetry(url, init, signal) {
    for (let attempt = 1; ; attempt++) {
      if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');
      let res = null, netErr = null;
      try { res = await fetch(url, init); } catch (e) { if (e.name === 'AbortError') throw e; netErr = e; }
      if (!netErr && res && res.ok) return res;
      if (!netErr && ![408, 409, 425, 429, 500, 502, 503, 504, 522, 524].includes(res.status)) {
        throw new Error('HTTP ' + res.status + ' — ' + (await res.text().catch(() => '')).slice(0, 300));
      }
      const wait = Math.floor(Math.min(30000, 1000 * Math.pow(2, Math.min(attempt - 1, 5))) * (0.5 + Math.random() * 0.5));
      if (_ui) _ui.note('⏳ ' + (netErr ? 'network error' : 'HTTP ' + res.status) + ' — retry #' + attempt + ' in ' + (wait / 1000).toFixed(1) + 's');
      await sleepAbortable(wait, signal);
    }
  }
  function llmUrlAuth() {
    const endpoint = ($('endpoint') ? $('endpoint').value : '').replace(/\/$/, '');
    const model = $('model') ? $('model').value : '';
    if (!endpoint || !model) throw new Error('No provider endpoint or model selected.');
    let url = endpoint + '/chat/completions';
    const proxy = $('proxyUrl') ? $('proxyUrl').value : '';
    if (proxy) { try { const u = new URL(proxy); u.searchParams.set('url', url); url = u.href; } catch (_) {} }
    return { url, model, auth: 'Bearer ' + (($('apiKey') ? $('apiKey').value : '') || '') };
  }
  // SSE streaming keeps the connection warm (the 504 fix). Assembles content +
  // index-keyed tool_call fragments; reasoning streams to onDelta but isn't returned.
  async function consumeStream(res, onDelta, signal) {
    if (!res.body || !res.body.getReader) {           // buffering proxy fallback
      const data = await res.json();
      if (data.error) throw new Error(String(data.error.message || JSON.stringify(data.error)));
      const msg = (data.choices && data.choices[0] && data.choices[0].message) || {};
      return { content: contentToText(msg.content || ''), tool_calls: msg.tool_calls || [] };
    }
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = '', content = ''; const tc = [];
    for (;;) {
      if (signal && signal.aborted) { try { reader.cancel(); } catch (_) {} throw new DOMException('aborted', 'AbortError'); }
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1);
        if (!line.startsWith('data:')) continue;
        const payload = line.slice(5).trim();
        if (payload === '[DONE]') continue;
        let j; try { j = JSON.parse(payload); } catch (_) { continue; }
        if (j.error) throw new Error(String(j.error.message || JSON.stringify(j.error)));
        const d = j.choices && j.choices[0] && j.choices[0].delta;
        if (!d) continue;
        if (d.reasoning_content && onDelta) onDelta(d.reasoning_content);
        if (d.reasoning && onDelta) onDelta(d.reasoning);
        if (d.content) { content += d.content; if (onDelta) onDelta(d.content); }
        for (const p of (d.tool_calls || [])) {
          const slot = tc[p.index || 0] || (tc[p.index || 0] = { id: '', type: 'function', function: { name: '', arguments: '' } });
          if (p.id) slot.id = p.id;
          if (p.function && p.function.name) slot.function.name += p.function.name;
          if (p.function && p.function.arguments) slot.function.arguments += p.function.arguments;
        }
      }
    }
    return { content, tool_calls: tc.filter(Boolean) };
  }
  function applyReasoning(body, r) {
    if (r === 'off') {
      body.chat_template_kwargs = { enable_thinking: false };
      body.reasoning_effort = 'minimal';
      body.enable_thinking = false;
    }
  }
  /* ============ tools ============ */
  function runTool(name, args, signal, convId) {
    return new Promise((resolve, reject) => {
      const sw = window._sandpieWorker;
      if (!sw) return reject(new Error('sandpie-worker not ready — reload the page.'));
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
      // Never shorter than the tool's own timeout, or long shells get guillotined.
      let ms = 120000;
      const reqT = args && Number(args.timeout);
      if (isFinite(reqT) && reqT > 0) ms = Math.min(330000, Math.max(ms, (reqT + 30) * 1000));
      const timer = setTimeout(() => finish('', 'tool RPC timed out after ' + Math.round(ms / 1000) + 's (background long jobs: `setsid <cmd> >/tmp/job.log 2>&1 & echo $!` then poll)'), ms);
      sw.addEventListener('message', onMsg);
      if (signal) signal.addEventListener('abort', onAbort, { once: true });
      sw.postMessage({ type: 'tool', id, name, args, conversation_file_name: convId });
    });
  }
  // Head+tail truncation for NOISY tools only (the crash/exit lives at the tail).
  // read_file / edit_file / write_file are EXEMPT: the harness reads the whole
  // progress file each turn (load + bulletproof pre-write readback), and truncating
  // that would corrupt the state it writes back.
  const RESULT_CAP = 8 * 1024, NEVER_TRUNCATE = new Set(['read_file', 'edit_file', 'write_file']);
  function capResult(name, result) {
    const s = String(result == null ? '' : result);
    if (NEVER_TRUNCATE.has(name) || s.length <= RESULT_CAP) return s;
    const head = Math.floor(RESULT_CAP * 0.25);
    return s.slice(0, head) + '\n\n…[' + Math.round((s.length - RESULT_CAP) / 1024) + 'kB elided — head+tail kept; the crash/exit is usually at the tail below]…\n\n' + s.slice(-(RESULT_CAP - head));
  }
  function toolSchemas(only) {
    let all = [];
    try { all = SandpieTools.schemas() || []; } catch (_) {}
    return only ? all.filter(t => only.includes(t.function && t.function.name)) : all;
  }

  // Agent turn: OpenAI tool loop. Returns { text, trace } — trace = tool calls+results.
  async function agentTurn({ system, user, tools, maxRounds, reasoning, signal, convId, onDelta, onTool }) {
    const { url, model, auth } = llmUrlAuth();
    const messages = [{ role: 'system', content: system }, { role: 'user', content: user }];
    const trace = [];
    let text = '';
    for (let r = 0; r < (maxRounds || 12); r++) {
      if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');
      const body = { model, messages, stream: true, stream_options: { include_usage: true }, max_tokens: 4096, tools: tools.length ? tools : undefined, tool_choice: tools.length ? 'auto' : undefined };
      applyReasoning(body, reasoning);
      const res = await fetchRetry(url, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: auth }, body: JSON.stringify(body), signal }, signal);
      const { content, tool_calls } = await consumeStream(res, onDelta, signal);
      messages.push({ role: 'assistant', content: content || '', tool_calls: tool_calls.length ? tool_calls : undefined });
      if (content) text += contentToText(content) + '\n';
      if (!tool_calls.length) break;
      for (const tc of tool_calls) {
        const nm = tc.function && tc.function.name;
        let args = {}; try { args = JSON.parse(tc.function.arguments || '{}'); } catch (_) {}
        if (onTool) onTool('call', nm, tc.function.arguments || '{}');
        let result;
        try { result = await runTool(nm, args, signal, convId); } catch (e) { result = 'Error: ' + (e.message || e); }
        result = capResult(nm, result);
        if (onTool) onTool('result', nm, result);
        trace.push('· ' + nm + ' ' + (tc.function.arguments || '{}') + '\n  → ' + result);
        messages.push({ role: 'tool', tool_call_id: tc.id, content: result });
      }
    }
    return { text: stripThink(text), trace: trace.join('\n') };
  }

  /* ============ progress file ============ */
  function bootstrapMd(task) {
    return '# PROGRESS\n\n## Task\n' + task + '\n\n## Checklist\n- [ ] Explore the codebase relevant to the task and draft a real, concrete checklist of remaining work\n\n## Lessons\n(none yet)\n';
  }
  function checkStructure(body) {
    const s = String(body || '');
    if (!s.trim()) return 'file is empty';
    if (!/^# PROGRESS\s*$/m.test(s)) return 'missing "# PROGRESS" title';
    for (const h of ['## Task', '## Checklist', '## Lessons']) {
      const c = (s.match(new RegExp('^' + h + '\s*$', 'gm')) || []).length;
      if (c === 0) return 'missing "' + h + '"';
      if (c > 1) return '"' + h + '" appears ' + c + ' times';
    }
    return null;
  }
  // read_file returns "<path> — N lines, X bytes" then "n\tline" rows; strip both.
  function stripReadFile(res) {
    const s = String(res || '');
    if (/^Error/i.test(s)) return null;
    const lines = s.split('\n');
    if (lines.length && /—\s*\d+\s*lines?,/.test(lines[0])) lines.shift();
    return lines.map(l => l.replace(/^\s*\d+\t/, '')).join('\n');
  }
  async function listRuns() {
    const out = [];
    try {
      const root = await navigator.storage.getDirectory();
      const ralph = await root.getDirectoryHandle('ralph');
      for await (const [name, handle] of ralph.entries()) {
        if (handle.kind !== 'directory') continue;
        try {
          const f = await (await handle.getFileHandle('PROGRESS.md')).getFile();
          const txt = await f.text();
          const m = txt.match(/##\s*Task\s*\r?\n+([^\r\n]+)/i);
          out.push({ runId: name, mtime: f.lastModified || 0, task: (m && m[1] || '').trim() });
        } catch (_) {}
      }
    } catch (_) {}
    return out.sort((a, b) => b.mtime - a.mtime);
  }

  /* ============ the ralph loop ============ */
  let _run = null;               // { ctrl }
  let _steerQueue = [];
  let _transcript = [];
  const rec = (s) => { _transcript.push(String(s)); if (_transcript.length > 400) _transcript.splice(0, 100); };
  let _ui = null;

  async function runRalph(task, ui, resumeRunId) {
    if (_run) throw new Error('A loop is already running.');
    const ctrl = new AbortController();
    _run = { ctrl };
    _ui = ui;
    const runId = resumeRunId || ('r' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6));
    const ralphFile = 'ralph/' + runId + '/PROGRESS.md';
    const signal = ctrl.signal;
    let body = null, stale = 0, done = false;
    ui.setRunning(true);
    ui.note((resumeRunId ? 'RESUMING ' : 'run ') + runId + ' → ' + ralphFile);

    const readProgress = async () => stripReadFile(await runTool('read_file', { path: ralphFile }, signal, runId));

    try {
      for (let turn = 1; !done; turn++) {
        if (signal.aborted) break;
        rec('--- TURN ' + turn + ' ---');
        const host = ui.addTurn(turn);

        // Load (or bootstrap) the progress file.
        try { body = await readProgress(); } catch (_) { body = null; }
        if (body == null) {
          body = bootstrapMd(task);
          await runTool('write_file', { path: ralphFile, content: body }, signal, runId);
          ui.note('progress file created: ' + ralphFile);
        }

        // Fold queued steering into the file (harness-owned write → old_str always matches).
        let steering = '(none)';
        if (_steerQueue.length) {
          const dirs = _steerQueue.splice(0);
          ui.updateSteerCount();
          steering = dirs.map(d => '- ' + d).join('\n');
          const heading = '## Steering (user directives)';
          const updated = body.includes(heading)
            ? body.replace(heading + '\n', heading + '\n' + steering + '\n')
            : body.replace(/^## Checklist$/m, heading + '\n' + steering + '\n\n## Checklist');
          try { await runTool('edit_file', { path: ralphFile, old_str: body, new_str: updated }, signal, runId); body = updated; ui.note('🧭 steering folded in (' + dirs.length + ')'); } catch (e) { ui.note('steering write failed: ' + e.message); }
          rec('[steering] ' + dirs.join(' | '));
        }

        // App system prompt (durable memories). buildSystemPrompt may return a string
        // or {role,content} — unwrap; never inject "[object Object]".
        let appSystemPromptFull = '';
        try {
          const r = await SandpieConversations.buildSystemPrompt([]);
          appSystemPromptFull = typeof r === 'string' ? r : String((r && (r.content || r.text)) || '');
          if (appSystemPromptFull === '[object Object]') appSystemPromptFull = '';
        } catch (_) {}
        // TOKEN DIET: the full environment prompt (all memories, skills index) goes to
        // plan/work ONLY on turn 1 — the scribe copies the relevant facts into
        // "## Lessons" as [inherited] lines, and the progress file carries them from
        // then on. Re-injecting it every turn multiplied every call's input cost.
        const appSystemPrompt = turn === 1 ? appSystemPromptFull : '(provided on turn 1 — see [inherited] lessons in the progress file)';
        const v = { task, ralphFile, progress: body, steering, appSystemPrompt, planNext: '' };

        // 1. PLAN — pure code, zero tokens: the first unchecked item in "## Checklist" IS the plan.
        // Fresh steering overrides the queued action for this turn (it is also folded
        // into the file above, so the scribe carries it forward).
        const plan = planFromFile(body);
        if (steering !== '(none)') { plan.allDone = false; plan.next = 'USER STEERING (highest priority — do this first):\n' + steering + '\n\nThen, if fully addressed, continue with: ' + (plan.next || 'the checklist'); }
        v.planNext = plan.next;
        rec('[plan] ' + (plan.allDone ? 'all checklist items done — verifying' : plan.next));
        ui.note('▶ plan: ' + (plan.allDone ? 'all done — verifying' : plan.next.slice(0, 160)));

        if (plan.allDone) {
          // 4. VERIFY
          ui.stageStart(host, 'verify');
          const { text: verdict } = await agentTurn({
            system: P_VERIFY(v), user: 'TASK:\n' + task + '\n\nVerify the completion claim now.',
            tools: toolSchemas(), maxRounds: 12, signal, convId: runId,
            onDelta: (c) => ui.stageStream(host, 'verify', c), onTool: (k, n, x) => ui.tool(host, k, n, x),
          });
          rec('[verify] ' + verdict);
          if (/VERDICT:\s*PASS/i.test(verdict)) {
            done = true;
            ui.stageDone(host, 'verify', '✅ PASS — task complete after ' + turn + ' turn(s)');
          } else {
            const m = verdict.match(/VERDICT:\s*FAIL\s*[—-]*\s*(.*)/i);
            const reason = (m && m[1]) || 'no explicit verdict';
            ui.stageDone(host, 'verify', '❌ FAIL — ' + reason);
            // Surface the objection as a new checklist item and return to the work-scribe loop.
            let onDisk = body;
            try { const d = await readProgress(); if (d != null) onDisk = d; } catch (_) {}
            const failureItem = '- [ ] Verifier objection (turn ' + turn + '): ' + reason.replace(/\s+/g, ' ').slice(0, 300);
            const updated = onDisk.replace(/^## Checklist$/m, '## Checklist\n' + failureItem);
            try { await runTool('edit_file', { path: ralphFile, old_str: onDisk, new_str: updated }, signal, runId); body = updated; } catch (_) {}
          }
          continue;
        }

        // 2. WORK
        ui.stageStart(host, 'work');
        const work = await agentTurn({
          system: P_WORK(v), user: 'Do this one action now:\n' + v.planNext,
          tools: toolSchemas(), maxRounds: 24, signal, convId: runId,
          onDelta: (c) => ui.stageStream(host, 'work', c), onTool: (k, n, x) => ui.tool(host, k, n, x),
        });
        rec('[work trace]\n' + work.trace + '\n[work note] ' + work.text);
        ui.stageDone(host, 'work', work.text || '(tool calls only)');

        // 3. SCRIBE — FULL REWRITE. The scribe never touches a tool: it emits the
        // ENTIRE new file as plain text (no edit_file to fight), and the HARNESS
        // writes it. tools:[] + maxRounds:1 → one completion, .text is the whole file.
        ui.stageStart(host, 'scribe');
        const workTrace = (work.trace || '(no tool calls made)') + (work.text ? '\n\nFinal note: ' + work.text : '');
        const scribe = await agentTurn({
          system: P_SCRIBE(v),
          user: 'ENVIRONMENT MEMORIES (first iteration only — promote the relevant ones as [inherited] lessons):\n' + (turn === 1 ? appSystemPrompt : '(provided on turn 1 — see [inherited] lessons)') + '\n\nPLANNED ACTION THIS ITERATION:\n' + v.planNext + '\n\nWHAT THE WORKER ACTUALLY DID (tool trace):\n' + workTrace + '\n\nOutput the ENTIRE updated ' + ralphFile + ' now — full markdown, nothing else.',
          tools: [], maxRounds: 1, reasoning: 'off', signal, convId: runId,
          onDelta: (c) => ui.stageStream(host, 'scribe', c),
        });
        // Strip stray ```markdown fences and any preamble before "# PROGRESS".
        let next = String(scribe.text || '').trim().replace(/^```(?:markdown|md)?\s*/i, '').replace(/\s*```$/, '').trim();
        const h = next.indexOf('# PROGRESS');
        if (h > 0) next = next.slice(h);
        // Guard: empty or NEW structural damage → keep the old body, count stale.
        // Otherwise the harness overwrites the file with the scribe's full output
        // (old_str = body, which only the harness writes → the match is guaranteed).
        const err = checkStructure(next), baseErr = checkStructure(body);
        if (!next || (err && !baseErr)) {
          stale++;
          ui.note('⚠ scribe output ' + (!next ? 'was empty' : 'DAMAGED structure (' + err + ')') + ' — kept previous file (stale ×' + stale + ')');
          rec('[scribe REJECTED] ' + (err || 'empty') + '\noutput was:\n' + next.slice(0, 1000));
        } else if (next === body) {
          stale++;
          ui.note('⚠ scribe made no change (stale ×' + stale + ')');
        } else {
          // Overwrite via edit_file (write_file is create-only). old_str MUST equal
          // the exact on-disk bytes; read them back rather than trusting `body`, so a
          // drift can't make the match fail. write_file bootstrap ran turn 1, so the
          // file exists.
          let onDisk = body;
          try { const d = await readProgress(); if (d != null) onDisk = d; } catch (_) {}
          try {
            await runTool('edit_file', { path: ralphFile, old_str: onDisk, new_str: next }, signal, runId);
            body = next; stale = 0;
            ui.stageDone(host, 'scribe', '✓ progress rewritten (' + next.length + ' B)');
          } catch (e) { stale++; ui.note('⚠ harness write failed: ' + e.message + ' (stale ×' + stale + ')'); }
        }
        if (stale >= 3) { ui.note('STALLED: 3 turns without a progress update — stopping (resume from ' + ralphFile + ').'); break; }
      }
    } catch (e) {
      if (e.name !== 'AbortError') ui.note('Loop error: ' + (e.message || e));
    } finally {
      _run = null; _ui = null;
      ui.setRunning(false);
      ui.note(signal.aborted ? 'Stopped by user.' : done ? 'Loop finished.' : 'Loop ended.');
    }
  }

  /* ============ UI ============ */
  let _panel = null;
  const CSS = `
    #loopLabOverlay { position:fixed; inset:0; z-index:9000; display:flex; align-items:center; justify-content:center; }
    #loopLabOverlay .ll-backdrop { position:absolute; inset:0; background:rgba(0,0,0,0.55); }
    #loopLabOverlay .ll-modal { position:relative; width:min(900px,94vw); height:92vh; display:flex; flex-direction:column;
      background:var(--sp-bg,#0d1117); border:1px solid var(--sp-border,#30363d); border-radius:10px; overflow:hidden; }
    #loopLabOverlay .ll-head { display:flex; align-items:center; gap:0.6rem; padding:0.7rem 1rem; border-bottom:1px solid var(--sp-border,#30363d); }
    #loopLabOverlay .ll-row { display:flex; gap:0.4rem; align-items:center; padding:0.4rem 0.6rem; }
    #loopLabOverlay textarea, #loopLabOverlay input[type=text], #loopLabOverlay select {
      background:var(--sp-panel,#161b22); color:var(--sp-text,#e6edf3); border:1px solid var(--sp-border,#30363d); border-radius:6px; font-size:0.78rem; }
    #loopLabOverlay .ll-task { flex:1; padding:0.45rem; resize:none; height:3.2rem; }
    #loopLabOverlay .ll-btn { padding:0.4rem 0.8rem; border:1px solid var(--sp-border,#30363d); border-radius:6px; background:var(--sp-panel,#161b22);
      color:var(--sp-text,#e6edf3); cursor:pointer; font-size:0.78rem; }
    #loopLabOverlay .ll-btn.primary { border-color:var(--sp-accent,#58a6ff); color:var(--sp-accent,#58a6ff); }
    #loopLabOverlay .ll-trace { flex:1; overflow-y:auto; padding:0.5rem; font-size:0.78rem; }
    #loopLabOverlay .ll-turn { border:1px solid var(--sp-border,#30363d); border-radius:8px; margin-bottom:0.5rem; padding:0.35rem 0.5rem; }
    #loopLabOverlay .ll-turn-title { font-weight:600; font-size:0.72rem; color:var(--sp-text-dim,#8b949e); margin-bottom:0.25rem; }
    #loopLabOverlay details { margin:0.2rem 0; }
    #loopLabOverlay details summary { cursor:pointer; font-size:0.74rem; }
    #loopLabOverlay details pre { margin:0.3rem 0; padding:0.4rem; background:var(--sp-panel,#161b22); border-radius:6px;
      white-space:pre-wrap; word-break:break-word; font-size:0.72rem; max-height:300px; overflow:auto; }
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
          <strong style="font-size:0.9rem;">Ralph</strong>
          <span id="llStatus" style="font-size:0.72rem;color:var(--sp-text-dim,#8b949e);"></span>
          <button class="ll-btn" id="llCopy" style="margin-left:auto;">⧉ Copy run</button>
          <button class="ll-btn" id="llClose">✕</button>
        </div>
        <div class="ll-row"><textarea id="llTask" class="ll-task" placeholder="Task…"></textarea></div>
        <div class="ll-row">
          <select id="llResume" style="flex:1;padding:0.35rem;min-width:0;"></select>
          <button class="ll-btn primary" id="llRun">▶ Run</button>
          <button class="ll-btn" id="llStop" style="display:none;">■ Stop</button>
        </div>
        <div class="ll-row">
          <input type="text" id="llSteer" placeholder="Steer the running loop… (Enter)" style="flex:1;padding:0.4rem;" disabled>
          <span id="llSteerN" class="ll-note"></span>
        </div>
        <details id="llPrompts" style="margin:0 0.6rem;">
          <summary style="cursor:pointer;font-size:0.74rem;color:var(--sp-text-dim,#8b949e);">Prompts ✎ <span id="llPromptsMod"></span></summary>
          <div id="llPromptEditors"></div>
        </details>
        <div class="ll-trace" id="llTrace"></div>
      </div>`;
    document.body.appendChild(root);
    _panel = root;
    const $id = (i) => root.querySelector('#' + i);

    async function refreshResume() {
      const sel = $id('llResume');
      const runs = await listRuns();
      sel.innerHTML = '<option value="">↻ Resume: (fresh run)</option>' + runs.map(r =>
        '<option value="' + r.runId + '">' + r.runId + (r.task ? ' — ' + r.task.slice(0, 48).replace(/</g, '&lt;') : '') + ' · ' + new Date(r.mtime).toLocaleString() + '</option>').join('');
    }
    // Prompt editors: one textarea per stage, auto-saved to localStorage on input
    // (applies from the NEXT stage call — prompts are re-read at call time, so you
    // can tune mid-run). "reset" restores the shipped default.
    (function buildPromptEditors() {
      const wrap = $id('llPromptEditors');
      const modBadge = () => {
        let saved = {}; try { saved = JSON.parse(localStorage.getItem(K_PROMPTS) || '{}'); } catch (_) {}
        const mods = Object.keys(saved);
        $id('llPromptsMod').textContent = mods.length ? '(modified: ' + mods.join(', ') + ')' : '';
      };
      const cur = loadPrompts();
      for (const key of Object.keys(DEFAULT_PROMPTS)) {
        const row = document.createElement('div');
        row.innerHTML = '<div class="ll-note" style="display:flex;align-items:center;gap:0.5rem;margin-top:0.3rem;"><strong>' + key + '</strong>'
          + '<span style="opacity:0.7;">placeholders: ${appSystemPrompt} ${progress} ${planNext} ${ralphFile} ${task}</span>'
          + '<button class="ll-btn" data-reset="' + key + '" style="margin-left:auto;padding:0.1rem 0.5rem;font-size:0.68rem;">reset</button></div>';
        const ta = document.createElement('textarea');
        ta.value = cur[key];
        ta.style.cssText = 'width:100%;height:7rem;padding:0.4rem;font-family:ui-monospace,monospace;font-size:0.7rem;resize:vertical;';
        ta.oninput = () => { savePrompt(key, ta.value); modBadge(); };
        row.querySelector('[data-reset]').onclick = () => { ta.value = DEFAULT_PROMPTS[key]; savePrompt(key, ta.value); modBadge(); };
        row.appendChild(ta);
        wrap.appendChild(row);
      }
      modBadge();
    })();

    $id('llResume').onchange = async () => {
      const id = $id('llResume').value;
      if (!id || $id('llTask').value.trim()) return;
      try {
        const root2 = await navigator.storage.getDirectory();
        const f = await (await (await (await root2.getDirectoryHandle('ralph')).getDirectoryHandle(id)).getFileHandle('PROGRESS.md')).getFile();
        const m = (await f.text()).match(/##\s*Task\s*\r?\n+([\s\S]*?)(?:\r?\n\s*##|$)/i);
        if (m) $id('llTask').value = m[1].trim();
      } catch (_) {}
    };

    const ui = {
      addTurn(n) {
        const d = document.createElement('div');
        d.className = 'll-turn';
        d.innerHTML = '<div class="ll-turn-title">TURN ' + n + '</div>';
        const t = $id('llTrace');
        t.appendChild(d);
        const turns = t.querySelectorAll('.ll-turn');
        for (let i = 0; i < turns.length - 5; i++) turns[i].remove();   // bound the DOM
        this._scroll();
        return d;
      },
      _scroll() { const t = $id('llTrace'); if (t && (t.scrollHeight - t.scrollTop - t.clientHeight) < 120) t.scrollTop = t.scrollHeight; },
      _live(host, name) {
        let d = host.querySelector('details[data-live]');
        if (!d || d.dataset.name !== name) {
          if (d) delete d.dataset.live;
          d = document.createElement('details');
          d.dataset.live = '1'; d.dataset.name = name; d.dataset.chars = '0';
          d.innerHTML = '<summary>▶ ' + name + ' (generating…)</summary>';
          host.appendChild(d);
        }
        return d;
      },
      stageStart(host, name) { this._live(host, name); this._scroll(); },
      stageStream(host, name, chunk) {
        const d = this._live(host, name);
        d.dataset.chars = (+d.dataset.chars) + chunk.length;
        d.querySelector('summary').textContent = '▶ ' + name + ' (generating… ' + Math.ceil((+d.dataset.chars) / 4) + ')';
        let pre = d.lastElementChild;
        if (!pre || pre.tagName !== 'PRE') { pre = document.createElement('pre'); d.appendChild(pre); }
        pre.appendChild(document.createTextNode(chunk));
        this._scroll();
      },
      tool(host, kind, name, payload) {
        const d = this._live(host, host.querySelector('details[data-live]') ? host.querySelector('details[data-live]').dataset.name : '?');
        const box = document.createElement('details');
        box.innerHTML = '<summary>' + (kind === 'call' ? '⚙ ' : '↩ ') + name + ' · ' + String(payload).length + ' chars</summary>';
        const pre = document.createElement('pre');
        pre.textContent = String(payload).slice(0, 4000);
        box.appendChild(pre);
        d.appendChild(box);
        this._scroll();
      },
      stageDone(host, name, out) {
        const d = host.querySelector('details[data-live]');
        if (d && d.dataset.name === name) {
          delete d.dataset.live;
          const toks = Math.ceil((+d.dataset.chars || 0) / 4);
          d.querySelector('summary').textContent = '✔ ' + name + (toks ? ' · ' + toks + ' tok' : '') + (out ? ' — ' + String(out).slice(0, 120) : '');
        }
        rec('[' + name + ' done] ' + out);
        this._scroll();
      },
      note(msg) {
        rec('· ' + msg);
        const el = document.createElement('div');
        el.className = 'll-note';
        el.textContent = msg;
        $id('llTrace').appendChild(el);
        this._scroll();
      },
      setRunning(on) {
        $id('llRun').style.display = on ? 'none' : '';
        $id('llStop').style.display = on ? '' : 'none';
        $id('llStatus').textContent = on ? 'Running…' : '';
        $id('llSteer').disabled = !on;
        if (!on) { _steerQueue = []; this.updateSteerCount(); refreshResume(); }
      },
      updateSteerCount() { $id('llSteerN').textContent = _steerQueue.length ? 'queued ' + _steerQueue.length : ''; },
    };

    $id('llRun').onclick = async () => {
      if (_run) return;
      const task = $id('llTask').value.trim();
      if (!task) { $id('llStatus').textContent = 'Enter a task first.'; return; }
      localStorage.setItem(K_TASK, task);
      $id('llTrace').innerHTML = '';
      _transcript = ['=== RALPH · ' + new Date().toISOString() + ' ===', 'TASK:\n' + task];
      try { await runRalph(task, ui, $id('llResume').value || null); } catch (e) { ui.note('Fatal: ' + (e.message || e)); ui.setRunning(false); }
    };
    $id('llStop').onclick = () => { if (_run) _run.ctrl.abort(); };
    $id('llSteer').addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      const t = $id('llSteer').value.trim();
      if (t && _run) { _steerQueue.push(t); $id('llSteer').value = ''; ui.updateSteerCount(); ui.note('🧭 steering queued: ' + t); }
    });
    $id('llCopy').onclick = async () => {
      try { await navigator.clipboard.writeText(_transcript.join('\n\n')); $id('llCopy').textContent = '✓ Copied'; }
      catch (_) { $id('llCopy').textContent = '✕ failed'; }
      setTimeout(() => { $id('llCopy').textContent = '⧉ Copy run'; }, 1500);
    };
    $id('llClose').onclick = close;
    root.querySelector('.ll-backdrop').onclick = close;
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && root.style.display !== 'none') close(); });
    $id('llTask').value = localStorage.getItem(K_TASK) || '';
    refreshResume();
    return root;
  }

  function open() { buildPanel().style.display = 'flex'; }
  function close() {
    if (!_panel) return;
    if (_run && !confirm('A loop is running — close anyway? (It keeps running.)')) return;
    _panel.style.display = 'none';
  }
  function steer(text) {
    const t = String(text || '').trim();
    if (!t || !_run) return false;
    _steerQueue.push(t);
    return true;
  }

  if (typeof SandpieCommands !== 'undefined') {
    SandpieCommands.register({ name: 'loop-lab', module: 'loop-lab', help: 'Open the Ralph loop panel', usage: '>>> loop-lab', run() { open(); return 'Ralph opened.'; } });
  }
  window.SandpieLoopLab = { open, close, steer, get running() { return !!_run; }, get transcript() { return _transcript.join('\n\n'); } };
})();
