// sandpie/modules/webllm.js — In-browser inference via WebLLM (MLC-LLM, WebGPU)
//
// WebLLM (https://github.com/mlc-ai/web-llm) is MLC's TVM-compiled, WebGPU-only
// inference engine. It exposes an OpenAI-compatible `chat.completions.create`
// API — including native `tools` / `tool_choice` — so for tool-capable models
// (Qwen 2.5/3/3.5, Hermes-3, Llama-3.1/3.2, Phi) function-calling is handled by
// the engine's grammar, exactly like the wllama path. For models MLC doesn't
// declare function-calling for (e.g. Gemma), we fall back to the same prompt-
// injection + <tool_call> parsing the litertlm/transformersjs backends use.
//
// THINKING: reasoning models (Qwen3 / Qwen3.5 / DeepSeek-R1-distill) emit their
// chain-of-thought as a <think>…</think> block in the content. We split that out
// live → the reasoning channel (delta.reasoning) so conversations.js renders the
// "Thinking…" box and never replays it to the model. The Qwen3 /think|/no_think
// soft-switch is applied to the latest user turn (working copy only), same as
// wllama. If a future model surfaces reasoning as delta.reasoning_content, that's
// routed straight through too.
//
// CONTRACT: this module mirrors litertlm.js / wllama.js — an IIFE that exports a
// `window.SandpieWebLLM` global with DEFAULT_MODELS / streamRound / runConversation,
// so providers.js, agents.js and conversations.js route to it unchanged.
//
// WebGPU-ONLY: like litertlm, there is no CPU/WASM fallback — gated on navigator.gpu.
// Model weights are cached by WebLLM in the Cache Storage API (NOT OPFS), so the
// Dropbox sync (which walks OPFS) never sees the multi-GB downloads.

const SandpieWebLLM = (function () {
  'use strict';

  // Pinned deliberately (a silent "latest" is what bit wllama). 0.2.84 is the build
  // whose bundled prebuiltAppConfig ships Qwen3.5 / Qwen3 / Gemma-3 / Phi-4-mini.
  // Bump = edit here AND re-check the curated modelIds below still exist (or load
  // listModels() in DevTools to see the live catalog).
  const PACKAGE_VERSION = '0.2.84';
  const ESM_URL = `https://cdn.jsdelivr.net/npm/@mlc-ai/web-llm@${PACKAGE_VERSION}/+esm`;

  // 0 = use each model's own trained context_window_size (MLC bakes one in). We only
  // pass an override to the engine when the provider explicitly sets one — raising
  // n_ctx past the trained size degrades quality / can OOM the GPU.
  const DEFAULT_N_CTX = 0;

  // Curated subset of WebLLM's prebuilt catalog. `modelId` is the exact MLC id handed
  // to the engine; `id` becomes the provider's display name. The FULL, always-current
  // list is webllm.prebuiltAppConfig.model_list — call listModels() to dump it — and
  // the picker's "Custom model_id…" option accepts any id from it. Sizes are rough
  // download/VRAM ballparks; q4f16 needs a WebGPU device with enough memory.
  const DEFAULT_MODELS = [
    { id: 'qwen2.5-1.5b-instruct', label: 'Qwen 2.5 1.5B Instruct (~1.2 GB, fast, tools)', modelId: 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC' },
    { id: 'qwen2.5-3b-instruct',   label: 'Qwen 2.5 3B Instruct (~2.2 GB, tools)',          modelId: 'Qwen2.5-3B-Instruct-q4f16_1-MLC' },
    { id: 'qwen2.5-7b-instruct',   label: 'Qwen 2.5 7B Instruct (~5 GB, tools)',             modelId: 'Qwen2.5-7B-Instruct-q4f16_1-MLC' },
    { id: 'qwen3-8b',              label: 'Qwen 3 8B (~5.5 GB, tools + thinking)',           modelId: 'Qwen3-8B-q4f16_1-MLC' },
    { id: 'qwen3.5-9b',            label: 'Qwen 3.5 9B (~6 GB, tools + thinking, newest)',   modelId: 'Qwen3.5-9B-q4f32_1-MLC' },
    { id: 'hermes-3-llama-3.1-8b', label: 'Hermes 3 Llama 3.1 8B (~5.5 GB, best tool-calling)', modelId: 'Hermes-3-Llama-3.1-8B-q4f16_1-MLC' },
    { id: 'llama-3.2-3b-instruct', label: 'Llama 3.2 3B Instruct (~2.3 GB, tools)',          modelId: 'Llama-3.2-3B-Instruct-q4f16_1-MLC' },
    { id: 'llama-3.1-8b-instruct', label: 'Llama 3.1 8B Instruct (~5.5 GB, tools)',          modelId: 'Llama-3.1-8B-Instruct-q4f16_1-MLC' },
    { id: 'phi-4-mini-instruct',   label: 'Phi 4 mini Instruct (~2.5 GB, tools)',            modelId: 'Phi-4-mini-instruct-q4f16_1-MLC' },
    { id: 'gemma-2-9b-it',         label: 'Gemma 2 9B-it (~6 GB, prompt-parsed tools)',      modelId: 'gemma-2-9b-it-q4f32_1-MLC' },
    { id: 'gemma-3-1b-it',         label: 'Gemma 3 1B-it (~1 GB, small)',                    modelId: 'Gemma-3-1b-it-q4f16_1-MLC' },
    { id: 'smollm2-1.7b-instruct', label: 'SmolLM2 1.7B Instruct (~1.2 GB, tiny)',           modelId: 'SmolLM2-1.7B-Instruct-q4f32_1-MLC' },
  ];

  // ============================================================
  // Debug logging — localStorage.setItem('sandpie-webllm-debug','1') then reload.
  // window.__webllmLastRound always holds the last round's payloads regardless.
  // ============================================================
  const DEBUG_KEY = 'sandpie-webllm-debug';
  function isDebug() { try { return localStorage.getItem(DEBUG_KEY) === '1'; } catch (_) { return false; } }
  function dbg(...a) { if (isDebug()) console.log('[webllm]', ...a); }

  function hasWebGPU() { return typeof navigator !== 'undefined' && !!navigator.gpu; }

  // ============================================================
  // SDK + engine singletons. One cached engine per (modelId, ctx); WebLLM holds a
  // single model resident, so switching models unloads the previous one.
  // ============================================================
  let _lib = null;
  async function loadLib() {
    if (_lib) return _lib;
    dbg('importing WebLLM from', ESM_URL);
    try { _lib = await import(ESM_URL); }
    catch (e) { console.error('[webllm] failed to import WebLLM from', ESM_URL, e); throw e; }
    return _lib;
  }

  // The live catalog — handy from DevTools (await SandpieWebLLM.listModels()) when the
  // curated list drifts behind a version bump.
  async function listModels() {
    try { const w = await loadLib(); return ((w.prebuiltAppConfig && w.prebuiltAppConfig.model_list) || []).map(m => m.model_id); }
    catch (_) { return []; }
  }

  let _engine = null, _engineModel = null, _engineCtx = 0;
  async function ensureEngine(modelId, nCtx, onProgress) {
    const ctx = (nCtx | 0) || 0;
    if (_engine && _engineModel === modelId && _engineCtx === ctx) return _engine;
    if (!hasWebGPU()) {
      throw new Error('WebLLM needs WebGPU, which this browser/profile does not expose (navigator.gpu is missing). Use Chrome/Edge with WebGPU enabled, or pick a wllama (CPU) model instead.');
    }
    const webllm = await loadLib();
    // Tear down a stale engine before loading a different model (frees GPU memory).
    if (_engine) { try { await _engine.unload(); } catch (_) {} _engine = null; _engineModel = null; _engineCtx = 0; }
    const engineConfig = { initProgressCallback: (r) => { try { onProgress && onProgress(r); } catch (_) {} } };
    // chatOpts override only when the provider set a context window; otherwise the
    // model's own context_window_size is used.
    const chatOpts = ctx > 0 ? { context_window_size: ctx } : undefined;
    dbg('CreateMLCEngine', modelId, 'ctx', ctx || '(model default)');
    _engine = await webllm.CreateMLCEngine(modelId, engineConfig, chatOpts);
    _engineModel = modelId;
    _engineCtx = ctx;
    return _engine;
  }

  // ============================================================
  // Messages adapter — WebLLM is OpenAI-compatible, so system/user/assistant/tool
  // roles + assistant.tool_calls + tool.tool_call_id pass straight through. We only
  // flatten array content to text (the catalog is text-only; strip image parts).
  // ============================================================
  function norm(m) {
    let c = m.content;
    if (Array.isArray(c)) c = c.filter(p => p && p.type === 'text').map(p => p.text || '').join('\n');
    else if (c != null && typeof c !== 'string') c = String(c);
    const out = { role: m.role, content: c == null ? '' : c };
    if (m.tool_calls) out.tool_calls = m.tool_calls;
    if (m.tool_call_id) out.tool_call_id = m.tool_call_id;
    return out;
  }
  function adaptMessages(messages) {
    const out = [];
    for (const m of (messages || [])) { if (m && m.role) out.push(norm(m)); }
    return out;
  }

  // Qwen3-style soft reasoning switch: append /think or /no_think to the LAST user
  // turn (working copy only — never the stored message). 'auto' leaves the default.
  function applySoftSwitch(messages, think) {
    if (think !== 'think' && think !== 'no_think') return;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        messages[i] = { ...messages[i], content: ((messages[i].content || '') + ' ' + (think === 'think' ? '/think' : '/no_think')).trim() };
        break;
      }
    }
  }

  function buildSampling(provider, fallbackMaxTokens) {
    const p = provider || {};
    const s = {};
    if (p.temperature != null) s.temperature = p.temperature;
    if (p.topP != null) s.top_p = p.topP;
    if (p.frequencyPenalty != null) s.frequency_penalty = p.frequencyPenalty;
    if (p.presencePenalty != null) s.presence_penalty = p.presencePenalty;
    if (p.seed != null) s.seed = p.seed | 0;
    const mt = (p.maxTokens | 0) || (fallbackMaxTokens | 0) || 0;
    if (mt > 0) s.max_tokens = mt;
    // NOTE: top_k / min_p aren't in WebLLM's OpenAI surface, so they're intentionally
    // dropped here (passing them would be ignored at best).
    return s;
  }

  // ============================================================
  // Live <think>…</think> splitter. Thought text → onReasoning, the rest → onContent.
  // Holds back a short tail so a marker straddling two chunks is never mis-emitted.
  // Degrades safely: with no markers, everything is content (a few chars of lag,
  // flushed at the end). Mirrors litertlm's makeThoughtSplitter, retargeted to <think>.
  // ============================================================
  function makeThinkSplitter(onReasoning, onContent) {
    const OPEN = '<think>', CLOSE = '</think>', HOLD = CLOSE.length - 1;
    let buf = '', mode = 'pre';
    const self = { answer: '', reasoning: '' };
    function out(t, isR) {
      if (!t) return;
      if (isR) { self.reasoning += t; try { onReasoning && onReasoning(t); } catch (_) {} }
      else { self.answer += t; try { onContent && onContent(t); } catch (_) {} }
    }
    function run(final) {
      for (;;) {
        if (mode === 'pre') {
          const i = buf.indexOf(OPEN);
          if (i === -1) { const safe = final ? buf.length : Math.max(0, buf.length - HOLD); if (safe > 0) { out(buf.slice(0, safe), false); buf = buf.slice(safe); } return; }
          if (i > 0) out(buf.slice(0, i), false);
          buf = buf.slice(i + OPEN.length); mode = 'think'; continue;
        }
        if (mode === 'think') {
          const i = buf.indexOf(CLOSE);
          if (i === -1) { const safe = final ? buf.length : Math.max(0, buf.length - HOLD); if (safe > 0) { out(buf.slice(0, safe), true); buf = buf.slice(safe); } return; }
          if (i > 0) out(buf.slice(0, i), true);
          buf = buf.slice(i + CLOSE.length); mode = 'post'; continue;
        }
        const safe = final ? buf.length : Math.max(0, buf.length - HOLD);
        if (safe > 0) { out(buf.slice(0, safe), false); buf = buf.slice(safe); }
        return;
      }
    }
    self.push = (t) => { if (t) { buf += t; run(false); } };
    self.flush = () => run(true);
    return self;
  }

  // ============================================================
  // Prompt-based tool fallback (only used when the model has no native FC). The
  // preamble + parser are intentionally the same shape as litertlm/transformersjs.
  // ============================================================
  function buildToolPreamble(tools) {
    const fns = (tools || []).filter(t => t && t.type === 'function').map(t => t.function).filter(Boolean);
    if (!fns.length) return '';
    const specs = fns.map(f => `- ${f.name}: ${f.description || ''}\n  arguments (JSON schema): ${JSON.stringify(f.parameters || {})}`).join('\n');
    return [
      'When you need a tool, emit a call as <tool_call>{"name":"<fn>","arguments":{...}}</tool_call> and nothing else; otherwise answer normally.',
      'Available tools:',
      specs,
    ].join('\n');
  }
  function normalizeToolCall(raw) {
    if (!raw) return null;
    const name = raw.name || (raw.function && raw.function.name);
    if (!name) return null;
    let args = raw.arguments || (raw.function && raw.function.arguments) || raw.params || raw.parameters || {};
    if (typeof args === 'string') { try { args = JSON.parse(args); } catch (_) { args = {}; } }
    return { id: 'call_' + Math.random().toString(36).slice(2, 11), type: 'function', function: { name, arguments: typeof args === 'string' ? args : JSON.stringify(args) } };
  }
  function parseToolCalls(text) {
    const calls = [], seen = new Set();
    const rx = /<tool_call>([\s\S]*?)<\/tool_call>/g;
    let m;
    while ((m = rx.exec(text)) !== null) {
      if (seen.has(m[1])) continue; seen.add(m[1]);
      try { const tc = normalizeToolCall(JSON.parse(m[1].trim())); if (tc) calls.push(tc); } catch (_) { dbg('bad <tool_call> JSON:', m[1]); }
    }
    const rxJson = /```json\s*([\s\S]*?)```/g;
    while ((m = rxJson.exec(text)) !== null) {
      try { const parsed = JSON.parse(m[1].trim()); for (const it of (Array.isArray(parsed) ? parsed : [parsed])) { const tc = normalizeToolCall(it); if (tc && !seen.has(m[1])) { seen.add(m[1]); calls.push(tc); } } } catch (_) {}
    }
    return calls.map((tc, i) => ({ ...tc, index: i }));
  }
  function cleanContent(text) {
    return (text || '')
      .replace(/<think>[\s\S]*?<\/think>\s*/gi, '')
      .replace(/<tool_call>[\s\S]*?<\/tool_call>/g, '')
      .replace(/```json\s*[\s\S]*?```/g, '')
      .replace(/^\s+/, '');
  }
  function safeParse(s) { try { return JSON.parse(s || '{}'); } catch (_) { return {}; } }

  // Rewrite the OAI history for prompt-based tools: fold the preamble into the system
  // turn, render assistant tool_calls + tool results as plain text the model can read.
  function toTextToolsMessages(work, toolList) {
    const pre = buildToolPreamble(toolList);
    const out = [];
    let hasSystem = false;
    for (const m of work) {
      if (m.role === 'system') { hasSystem = true; out.push({ role: 'system', content: m.content + (pre ? '\n\n' + pre : '') }); }
      else if (m.role === 'tool') { out.push({ role: 'user', content: 'Tool result' + (m.tool_call_id ? ' (' + m.tool_call_id + ')' : '') + ': ' + (m.content || '') }); }
      else if (m.role === 'assistant' && m.tool_calls && m.tool_calls.length) {
        const calls = m.tool_calls.map(tc => `<tool_call>${JSON.stringify({ name: tc.function && tc.function.name, arguments: safeParse(tc.function && tc.function.arguments) })}</tool_call>`).join('\n');
        out.push({ role: 'assistant', content: (m.content || '') + (m.content ? '\n' : '') + calls });
      } else out.push({ role: m.role, content: m.content });
    }
    if (pre && !hasSystem) out.unshift({ role: 'system', content: pre });
    return out;
  }

  // ============================================================
  // One-shot completion (agents.js runPrompt). Stateless: stream once, return the
  // answer (reasoning stripped). agents.js passes tools:[] so the tool path is dormant.
  // ============================================================
  async function streamRound({ modelUrl, messages, tools, signal, onDelta, onProgress, nCtx, temperature, topP, maxTokens, reasoning }) {
    const engine = await ensureEngine(modelUrl, (nCtx | 0) || 0, onProgress);
    if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');

    const msgs = adaptMessages(messages);
    applySoftSwitch(msgs, reasoning);

    const sampling = {};
    if (temperature != null) sampling.temperature = temperature;
    if (topP != null) sampling.top_p = topP;
    sampling.max_tokens = (maxTokens | 0) || 1024;

    const splitter = makeThinkSplitter(null, (ct) => { try { onDelta && onDelta({ content: ct }); } catch (_) {} });
    const toolCalls = [];
    const req = { messages: msgs, stream: true, ...sampling };
    if (tools && tools.length) { req.tools = tools; req.tool_choice = 'auto'; }

    const stream = await engine.chat.completions.create(req);
    for await (const chunk of stream) {
      if (signal && signal.aborted) { try { engine.interruptGenerate(); } catch (_) {} throw new DOMException('aborted', 'AbortError'); }
      const delta = chunk && chunk.choices && chunk.choices[0] && chunk.choices[0].delta;
      if (!delta) continue;
      if (delta.content) splitter.push(delta.content);
      if (delta.tool_calls) {
        for (const tc of delta.tool_calls) {
          const i = tc.index || 0;
          if (!toolCalls[i]) toolCalls[i] = { id: '', type: 'function', function: { name: '', arguments: '' } };
          if (tc.id) toolCalls[i].id = tc.id;
          if (tc.function && tc.function.name) toolCalls[i].function.name += tc.function.name;
          if (tc.function && tc.function.arguments) toolCalls[i].function.arguments += tc.function.arguments;
        }
        try { onDelta && onDelta({ tool_calls: delta.tool_calls }); } catch (_) {}
      }
    }
    splitter.flush();
    return { content: splitter.answer, tool_calls: toolCalls.filter(tc => tc && tc.id) };
  }

  // ============================================================
  // Agentic conversation loop — emits the SAME event protocol conversations.js
  // expects (identical to wllama / litertlm); tool calls run via /sandpie-tool.
  //
  // WebLLM keeps its own prefix/KV cache across create() calls, so we re-send the
  // full working history each round (like wllama) and let the engine reuse the
  // shared prefix — no manual conversation handle needed.
  // ============================================================
  async function runConversation({ provider, messages, systemPrompt, tools, convId, signal }, emit) {
    const modelId = provider && (provider.endpoint || '').trim();
    if (!modelId) { emit({ type: 'error', message: 'webllm: this provider has no model id — pick a WebLLM model in Settings.' }); emit({ type: 'agent_done' }); return; }
    if (!hasWebGPU()) { emit({ type: 'error', message: 'webllm: WebGPU is unavailable (navigator.gpu missing). Use Chrome/Edge, or pick a wllama (CPU) model.' }); emit({ type: 'agent_done' }); return; }

    const sysContent = systemPrompt ? (typeof systemPrompt === 'string' ? systemPrompt : (systemPrompt.content != null ? String(systemPrompt.content) : '')) : '';
    const toolList = Array.isArray(tools) ? tools.filter(t => t && t.type === 'function') : [];

    // Working history, mutated across tool rounds.
    const work = [];
    if (sysContent) work.push({ role: 'system', content: sysContent });
    for (const m of (messages || [])) { if (m && m.role) work.push(norm(m)); }
    applySoftSwitch(work, provider.reasoning || 'auto');

    const sampling = buildSampling(provider);
    const nCtx = (provider.contextWindow | 0) || 0;

    // Load (download + compile). WebLLM's initProgressCallback streams a descriptive
    // `text` and a 0–1 `progress`; surface it as the status line until the first token.
    let firstToken = false, _lastInfo = '';
    const clearFirst = () => { if (!firstToken) { firstToken = true; emit({ type: 'info', message: null }); } };
    const progressCb = (r) => {
      if (firstToken || !r) return;
      const msg = r.text ? r.text : (r.progress != null ? `Loading model… ${Math.round(r.progress * 100)}%` : 'Loading model…');
      if (msg !== _lastInfo) { _lastInfo = msg; emit({ type: 'info', message: msg }); }
    };

    let engine;
    try {
      emit({ type: 'info', message: 'Loading WebLLM model (WebGPU)… first run downloads it (cached after).' });
      engine = await ensureEngine(modelId, nCtx, progressCb);
    } catch (e) {
      emit({ type: 'info', message: null });
      if (e && e.name === 'AbortError') throw e;
      emit({ type: 'error', message: 'webllm: ' + ((e && e.message) || e) });
      emit({ type: 'agent_done' });
      return;
    }
    if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');

    // Flips to true if the model rejects native function-calling — thereafter we feed
    // tools via the prompt and parse <tool_call> blocks from the text.
    let useTextTools = false;

    const MAX_ROUNDS = 8;
    for (let round = 0; round < MAX_ROUNDS; round++) {
      if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');
      emit({ type: 'round_start' });

      const splitter = makeThinkSplitter(
        (rz) => { clearFirst(); emit({ type: 'delta', delta: { reasoning: rz } }); },
        (ct) => { clearFirst(); emit({ type: 'delta', delta: { content: ct } }); }
      );
      const toolCalls = [];
      let finishReason = null, usage = null;

      // Build + open the stream, transparently falling back to prompt-tools if the
      // model has no native FC. create() is awaited before any token streams, so the
      // retry happens cleanly within this round (round_start already emitted once).
      let stream;
      try {
        const open = async (textMode) => {
          const reqMessages = textMode ? toTextToolsMessages(work, toolList) : work;
          const req = { messages: reqMessages, stream: true, stream_options: { include_usage: true }, ...sampling };
          if (!textMode && toolList.length) { req.tools = toolList; req.tool_choice = 'auto'; }
          return engine.chat.completions.create(req);
        };
        if (useTextTools) stream = await open(true);
        else {
          try { stream = await open(false); }
          catch (e) {
            if (toolList.length && /function call|tool|does not support/i.test(String((e && e.message) || e))) {
              dbg('native function-calling unsupported → prompt-tool fallback:', (e && e.message) || e);
              useTextTools = true;
              stream = await open(true);
            } else throw e;
          }
        }

        for await (const chunk of stream) {
          if (signal && signal.aborted) { try { engine.interruptGenerate(); } catch (_) {} throw new DOMException('aborted', 'AbortError'); }
          if (chunk && chunk.usage) usage = chunk.usage;
          const choice = chunk && chunk.choices && chunk.choices[0];
          if (choice && choice.finish_reason) finishReason = choice.finish_reason;
          const delta = choice && choice.delta;
          if (!delta) continue;
          // Some builds surface reasoning on a dedicated field — route it straight to
          // the Thinking box. Otherwise the <think> splitter handles inline reasoning.
          if (delta.reasoning_content) { clearFirst(); emit({ type: 'delta', delta: { reasoning: delta.reasoning_content } }); }
          if (delta.content) splitter.push(delta.content);
          if (delta.tool_calls) {
            for (const tc of delta.tool_calls) {
              const i = tc.index || 0;
              if (!toolCalls[i]) toolCalls[i] = { id: '', type: 'function', function: { name: '', arguments: '' } };
              if (tc.id) toolCalls[i].id = tc.id;
              if (tc.function && tc.function.name) toolCalls[i].function.name += tc.function.name;
              if (tc.function && tc.function.arguments) toolCalls[i].function.arguments += tc.function.arguments;
            }
            clearFirst();
            emit({ type: 'delta', delta: { tool_calls: delta.tool_calls } });
          }
        }
        splitter.flush();
      } catch (e) {
        if (e && e.name === 'AbortError') throw e;
        emit({ type: 'info', message: null });
        emit({ type: 'error', message: 'webllm: ' + ((e && e.message) || e) });
        emit({ type: 'agent_done' });
        return;
      }
      emit({ type: 'info', message: null });
      if (usage) emit({ type: 'usage', usage });

      let calls = toolCalls.filter(tc => tc && tc.id);
      let answer = splitter.answer;
      // Prompt-tool mode: the calls live in the text — parse them and synthesize the
      // streaming delta so conversations.js builds the tool-call bubbles (it looks them
      // up by id later, exactly like litertlm does for prompt-parsed calls).
      if (!calls.length && useTextTools && toolList.length) {
        const parsed = parseToolCalls(answer);
        if (parsed.length) {
          emit({ type: 'delta', delta: { tool_calls: parsed.map((tc, i) => ({ index: tc.index != null ? tc.index : i, id: tc.id, type: 'function', function: { name: tc.function.name, arguments: tc.function.arguments } })) } });
          calls = parsed;
        }
      }
      const cleanAnswer = useTextTools ? cleanContent(answer) : answer;

      try {
        self.__webllmLastRound = { ts: new Date().toISOString(), round, useTextTools, finish_reason: finishReason, usage, content: cleanAnswer, reasoning: splitter.reasoning, tool_calls: calls };
      } catch (_) {}
      dbg(`← round ${round}: ${finishReason || '(none)'} · content ${cleanAnswer.length} · reasoning ${splitter.reasoning.length} · tool_calls ${calls.length}${useTextTools ? ' (prompt-tools)' : ''}`);

      emit({ type: 'round_end', content: cleanAnswer });
      const asst = { role: 'assistant', content: cleanAnswer };
      if (calls.length) asst.tool_calls = calls;
      work.push(asst);
      emit({ type: 'message_added', message: asst });
      if (!calls.length) break;   // no tools → turn complete

      for (const tc of calls) {
        if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');
        emit({ type: 'tool_started', tc });
        let args = {};
        try { args = JSON.parse((tc.function && tc.function.arguments) || '{}'); } catch (_) {}
        let out;
        try {
          const res = await fetch('./sandpie-tool', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: tc.function && tc.function.name, args, conversation_file_name: convId }),
            signal,
          });
          out = res.ok ? await res.json() : { result: 'Error: tool endpoint ' + res.status + ' — service worker not ready (reload once).' };
        } catch (e) {
          if (e && e.name === 'AbortError') throw e;
          out = { result: 'Error: ' + ((e && e.message) || e) };
        }
        const toolResult = (out && out.result != null) ? out.result : '';
        emit({ type: 'tool_result', id: tc.id, result: toolResult, artifacts: out && out.artifacts });
        const toolMsg = { role: 'tool', tool_call_id: tc.id, content: toolResult };
        work.push(toolMsg);
        emit({ type: 'message_added', message: toolMsg });
      }
    }

    emit({ type: 'agent_done' });
  }

  return { DEFAULT_MODELS, DEFAULT_N_CTX, streamRound, runConversation, listModels };
})();

if (typeof window !== 'undefined') window.SandpieWebLLM = SandpieWebLLM;
