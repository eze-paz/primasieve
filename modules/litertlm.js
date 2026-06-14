// sandpie/modules/litertlm.js — In-browser Gemma inference via Google AI Edge
// LiteRT-LM (WebGPU). Runs the curated Gemma 4 ".litertlm" models fully on-device.
//
// WHY LiteRT-LM: it's Google's first-party edge runtime for its own Gemma models,
// so the model+runtime pairing is curated and tested — no arbitrary-quant roulette.
// It is WebGPU-ONLY (no CPU/WASM fallback), so this backend is gated on
// navigator.gpu and surfaces a clear message when WebGPU is absent.
//
// TOOL CALLING: the LiteRT-LM *Web* SDK does NOT expose a native tools/function API
// yet (that's Python/Kotlin/Swift only). Gemma 4 still emits tool calls in its text
// (function calling is trained in), so — exactly like transformersjs.js — we render
// the tool list into the system prompt and PARSE <tool_call> blocks out of the
// output. The agent loop, dispatch event protocol, and /sandpie-tool wiring are
// identical to the other local backends, so conversations.js / agents.js route to
// it unchanged.

const SandpieLiteRTLM = (function () {
  'use strict';

  // Pinned on purpose (v0.12 is the web-preview release that added the JS API). Bump
  // deliberately, not automatically — a silent "latest" default is what broke wllama.
  // If this 404s on the CDN, drop the "@<ver>" to track latest, or check npm for the
  // current web-preview version of @litert-lm/core.
  const PACKAGE_VERSION = '0.12';
  const ESM_URL = `https://cdn.jsdelivr.net/npm/@litert-lm/core@${PACKAGE_VERSION}/+esm`;

  const DEFAULT_N_CTX = 4096;

  // Curated, web-converted Gemma 4 (the "-web.litertlm" builds from the official
  // litert-community org). modelId is the direct file URL handed to
  // Engine.create({ model }). Large one-time downloads, browser-cached afterward.
  const HF = 'https://huggingface.co/litert-community';
  const DEFAULT_MODELS = [
    {
      id: 'gemma-4-e2b-it',
      label: 'Gemma 4 E2B-it (~2.0 GB, tools, WebGPU)',
      modelId: `${HF}/gemma-4-E2B-it-litert-lm/resolve/main/gemma-4-E2B-it-web.litertlm`,
    },
    {
      id: 'gemma-4-e4b-it',
      label: 'Gemma 4 E4B-it (~3.0 GB, tools, WebGPU — more capable)',
      modelId: `${HF}/gemma-4-E4B-it-litert-lm/resolve/main/gemma-4-E4B-it-web.litertlm`,
    },
  ];

  // ============================================================
  // Debug logging
  // ============================================================
  const DEBUG_KEY = 'sandpie-litertlm-debug';
  function isDebug() { try { return localStorage.getItem(DEBUG_KEY) === '1'; } catch (_) { return false; } }
  function dbg(...a) { if (isDebug()) console.log('[litertlm]', ...a); }

  function hasWebGPU() { return typeof navigator !== 'undefined' && !!navigator.gpu; }

  // ============================================================
  // Runtime + engine — one cached engine per (model URL, context size).
  // ============================================================
  let _lib = null, _engine = null, _engineModel = null, _engineCtx = 0;

  async function loadLib() {
    if (_lib) return _lib;
    dbg('importing LiteRT-LM from', ESM_URL);
    try { _lib = await import(ESM_URL); }
    catch (e) { console.error('[litertlm] failed to import LiteRT-LM from', ESM_URL, e); throw e; }
    return _lib;
  }

  async function ensureEngine(modelUrl, nCtx, onProgress) {
    const ctx = (nCtx | 0) || DEFAULT_N_CTX;
    if (_engine && _engineModel === modelUrl && _engineCtx === ctx) return _engine;
    if (!hasWebGPU()) {
      throw new Error('LiteRT-LM needs WebGPU, which this browser/profile does not expose (navigator.gpu is missing). Use Chrome/Edge with WebGPU enabled, or pick a wllama (CPU) model instead.');
    }
    // Tear down a stale engine before loading a different model.
    if (_engine) { try { await _engine.delete(); } catch (_) {} _engine = null; _engineModel = null; _engineCtx = 0; }
    // The Web SDK exposes no download-progress callback — surface a single tick so
    // the UI can show a "loading" line before the (multi-GB, slow) first load.
    try { onProgress && onProgress({ status: 'loading' }); } catch (_) {}
    const { Engine } = await loadLib();
    // Per the docs, Engine.create sets up the WASM runtime + WebGPU device itself.
    // If a future SDK build needs explicit init, the module also exports
    // loadLiteRtLm() / getOrLoadGlobalLiteRtLm() / setupDefaultWebGpuDevice().
    dbg('Engine.create', modelUrl, 'maxNumTokens', ctx);
    _engine = await Engine.create({ model: modelUrl, mainExecutorSettings: { maxNumTokens: ctx } });
    _engineModel = modelUrl;
    _engineCtx = ctx;
    return _engine;
  }

  // ============================================================
  // Tool plumbing — prompt-based (the Web SDK has no native tools API).
  // We instruct the model to emit <tool_call>{...}</tool_call>, which parseToolCalls
  // below extracts. parseToolCalls / normalizeToolCall are intentionally identical to
  // transformersjs.js so both local backends behave the same.
  // ============================================================
  function buildToolPreamble(tools) {
    const fns = (tools || []).filter(t => t && t.type === 'function').map(t => t.function).filter(Boolean);
    if (!fns.length) return '';
    const specs = fns.map(f => `- ${f.name}: ${f.description || ''}\n  arguments (JSON schema): ${JSON.stringify(f.parameters || {})}`).join('\n');
    // Gemma 4 has a trained function-calling format (<|tool_call>call:name{...}<tool_call|>)
    // and emits it when it knows the tools — so we just describe them and let it use its
    // native format. parseGemmaToolCalls() reads that format (JSON/<tool_call> is the fallback).
    return [
      'You can call tools using your function-calling format when one is needed; otherwise just answer normally.',
      'Available tools:',
      specs,
    ].join('\n');
  }

  function parseToolCalls(text) {
    const tool_calls = [];
    const seen = new Set();

    // Pattern 1: <tool_call>{"name":"...", "arguments":{...}}</tool_call>
    const rxToolCall = /<tool_call>([\s\S]*?)<\/tool_call>/g;
    let m;
    while ((m = rxToolCall.exec(text)) !== null) {
      if (seen.has(m[1])) continue;
      seen.add(m[1]);
      try { tool_calls.push(normalizeToolCall(JSON.parse(m[1].trim()))); }
      catch (e) { dbg('failed to parse <tool_call> JSON:', m[1]); }
    }

    // Pattern 2: ```json fenced block holding a tool call (or array of them)
    const rxJsonBlock = /```json\s*([\s\S]*?)```/g;
    while ((m = rxJsonBlock.exec(text)) !== null) {
      try {
        const parsed = JSON.parse(m[1].trim());
        const items = Array.isArray(parsed) ? parsed : [parsed];
        for (const item of items) {
          const tc = normalizeToolCall(item);
          if (tc && !seen.has(m[1])) { seen.add(m[1]); tool_calls.push(tc); }
        }
      } catch (e) { dbg('failed to parse JSON block:', m[1]); }
    }

    // Pattern 3: a bare JSON object/array on its own line that looks like a tool call
    const rxBare = /(^|\n)\s*(\[[\s\S]*?\]|\{[\s\S]*?\})\s*(\n|$)/g;
    while ((m = rxBare.exec(text)) !== null) {
      try {
        const parsed = JSON.parse(m[2].trim());
        const items = Array.isArray(parsed) ? parsed : [parsed];
        for (const item of items) {
          const tc = normalizeToolCall(item);
          if (tc && !seen.has(m[2])) { seen.add(m[2]); tool_calls.push(tc); }
        }
      } catch (e) { /* not JSON — skip */ }
    }

    return tool_calls.map((tc, idx) => ({ ...tc, index: idx }));
  }

  function normalizeToolCall(raw) {
    if (!raw) return null;
    const name = raw.name || (raw.function && raw.function.name);
    if (!name) return null;
    let args = raw.arguments || raw.arguments_text || (raw.function && raw.function.arguments) || raw.params || raw.parameters || {};
    if (typeof args === 'string') { try { args = JSON.parse(args); } catch (_) { args = {}; } }
    return {
      id: 'call_' + Math.random().toString(36).slice(2, 11),
      type: 'function',
      function: { name, arguments: typeof args === 'string' ? args : JSON.stringify(args) },
    };
  }

  // Gemma 4's NATIVE function-calling format (read from the model's own metadata):
  //   <|tool_call>call:NAME{key:<|"|>value<|"|>, ...}<tool_call|>
  // String values are wrapped in the <|"|> quote token so embedded quotes/commas/newlines
  // (e.g. file content) don't break parsing. The start fence is sometimes stripped from the
  // streamed text, so we anchor on `call:NAME{...}` + the end fence.
  function parseGemmaToolCalls(text) {
    const calls = [];
    const rx = /(?:<\|tool_call>)?\s*call:\s*([A-Za-z_][\w.]*)\s*\{([\s\S]*?)\}\s*<tool_call\|>/g;
    let m;
    while ((m = rx.exec(text)) !== null) {
      calls.push({
        id: 'call_' + Math.random().toString(36).slice(2, 11),
        type: 'function',
        function: { name: m[1], arguments: JSON.stringify(parseGemmaArgs(m[2])) },
      });
    }
    return calls.map((tc, idx) => ({ ...tc, index: idx }));
  }

  function parseGemmaArgs(body) {
    const args = {};
    let m, any = false;
    // Preferred: Gemma's <|"|> string delimiter — robust to embedded quotes/commas.
    const rxTok = /([A-Za-z_][\w.]*)\s*:\s*<\|"\|>([\s\S]*?)<\|"\|>/g;
    while ((m = rxTok.exec(body)) !== null) { args[m[1]] = m[2]; any = true; }
    if (any) return args;
    // Fallback: plain "double quotes" (closing quote = the one before ", nextKey:" or end —
    // tolerates quotes inside the value, e.g. code).
    const rxStr = /([A-Za-z_][\w.]*)\s*:\s*"([\s\S]*?)"\s*(?=,\s*[A-Za-z_][\w.]*\s*:|\}?\s*$)/g;
    while ((m = rxStr.exec(body)) !== null) { args[m[1]] = m[2]; any = true; }
    if (any) return args;
    // Last resort: bare scalars (numbers / booleans) — key: value
    const rxScalar = /([A-Za-z_][\w.]*)\s*:\s*([^,{}]+?)\s*(?=,|\}?\s*$)/g;
    while ((m = rxScalar.exec(body)) !== null) {
      let v = m[2].trim();
      if (/^-?\d+(?:\.\d+)?$/.test(v)) v = Number(v);
      else if (v === 'true' || v === 'false') v = (v === 'true');
      args[m[1]] = v;
    }
    return args;
  }

  function cleanContent(text) {
    return (text || '')
      .replace(/<\|tool_call>[\s\S]*?<tool_call\|>/g, '')   // Gemma 4 fenced tool call
      .replace(/<tool_call>[\s\S]*?<\/tool_call>/g, '')
      .replace(/```json\s*[\s\S]*?```/g, '')
      .replace(/<tool_call\|>|<\|tool_call>|<\|"\|>/g, '')   // stray Gemma tokens
      .replace(/<\|.*?>\n?/g, '')
      .trim()
      .replace(/^Assistant:\s*/i, '');
  }

  // Map sandpie message roles → LiteRT-LM roles. The Web SDK has no 'tool' role, so
  // tool outputs are fed back as a plainly-labelled user turn.
  function mapRole(role) { return role === 'assistant' ? 'assistant' : role === 'system' ? 'system' : 'user'; }
  function mapContent(m) {
    if (m.role === 'tool') return 'Tool result' + (m.tool_call_id ? ' (' + m.tool_call_id + ')' : '') + ': ' + (m.content || '');
    return m.content || '';
  }

  // ============================================================
  // Low-level: stream one send over an ALREADY-created Conversation. Accumulates the
  // text, relays each chunk to onText, honors abort (cancels the stream).
  // ============================================================
  async function streamInto(conv, input, signal, onText) {
    let full = '';
    const stream = conv.sendMessageStreaming(input || '');
    for await (const chunk of stream) {
      if (signal && signal.aborted) { try { conv.cancel(); } catch (_) {} throw new DOMException('aborted', 'AbortError'); }
      for (const item of (chunk && chunk.content) || []) {
        if (item && item.type === 'text' && item.text) { full += item.text; try { onText && onText(item.text); } catch (_) {} }
      }
    }
    return full;
  }

  // Gemma 4's native FC format first; generic JSON / <tool_call> parser as fallback.
  function splitToolCalls(full) {
    let tool_calls = parseGemmaToolCalls(full);
    if (!tool_calls.length) tool_calls = parseToolCalls(full);
    return { content: cleanContent(full), tool_calls };
  }

  // ============================================================
  // One-shot completion (used by agents.js runPrompt). Stateless: a throwaway
  // conversation seeded with the messages, single send. Returns {content, tool_calls}.
  // ============================================================
  async function streamRound({ modelUrl, messages, tools, signal, onDelta, onProgress, nCtx }) {
    const engine = await ensureEngine(modelUrl, nCtx, onProgress);
    if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');

    const mapped = (messages || []).map(m => ({ role: mapRole(m.role), content: mapContent(m) }));
    const preamble = buildToolPreamble(tools);
    if (preamble) {
      const sys = mapped.find(m => m.role === 'system');
      if (sys) sys.content += '\n\n' + preamble;
      else mapped.unshift({ role: 'system', content: preamble });
    }
    const last = mapped.length ? mapped[mapped.length - 1] : { content: '' };
    const preface = mapped.slice(0, -1);

    const conv = await engine.createConversation(preface.length ? { preface: { messages: preface } } : undefined);
    let full = '';
    try {
      full = await streamInto(conv, last.content, signal, (t) => { try { onDelta && onDelta({ content: t }); } catch (_) {} });
    } finally {
      try { if (conv && conv.delete) await conv.delete(); } catch (_) {}
    }
    dbg('raw model output:', full);
    return splitToolCalls(full);
  }

  // ============================================================
  // Agentic conversation loop — emits the SAME event protocol conversations.js
  // expects (identical to wllama / transformersjs); tool calls run via /sandpie-tool.
  //
  // Reuses ONE Conversation across all rounds (the LiteRT-LM-recommended pattern): the
  // engine keeps its environment + accelerators + KV cache, so each round only prefills
  // the NEW turn (the tool results) instead of re-creating the conversation and
  // re-prefilling the whole history every round.
  // ============================================================
  async function runConversation({ provider, messages, systemPrompt, tools, convId, signal }, emit) {
    const MAX_ROUNDS = 8;
    const toolList = (tools || []).filter(t => t && t.type === 'function');
    const nCtx = (provider.contextWindow | 0) || DEFAULT_N_CTX;

    // System text + tool descriptions (Gemma emits its native FC format from these).
    let sysText = (systemPrompt && typeof systemPrompt === 'object') ? (systemPrompt.content || '') : (systemPrompt || '');
    const preamble = buildToolPreamble(toolList);
    if (preamble) sysText = sysText ? (sysText + '\n\n' + preamble) : preamble;

    // Seed the conversation with system + all prior turns; the latest user turn is the
    // first thing we actually send. Later rounds send ONLY the new content (tool
    // results) — the conversation's own history/KV cache carries the rest.
    const hist = (messages || []).slice();
    let lastUserIdx = -1;
    for (let i = hist.length - 1; i >= 0; i--) { if (hist[i].role === 'user') { lastUserIdx = i; break; } }
    const preface = [];
    if (sysText) preface.push({ role: 'system', content: sysText });
    hist.forEach((m, i) => { if (i !== lastUserIdx) preface.push({ role: mapRole(m.role), content: mapContent(m) }); });
    let input = lastUserIdx >= 0 ? (hist[lastUserIdx].content || '') : '';

    let firstToken = false, engine, conv;
    try {
      emit({ type: 'info', message: 'Loading Gemma locally (WebGPU)… the first run downloads the model (cached after) — this can take a while.' });
      engine = await ensureEngine(provider.endpoint, nCtx);
      conv = await engine.createConversation(preface.length ? { preface: { messages: preface } } : undefined);
    } catch (e) {
      emit({ type: 'info', message: null });
      if (e && e.name === 'AbortError') throw e;
      emit({ type: 'error', message: 'litertlm: ' + ((e && e.message) || e) });
      emit({ type: 'agent_done' });
      return;
    }

    try {
      for (let round = 0; round < MAX_ROUNDS; round++) {
        if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');
        emit({ type: 'round_start' });

        const full = await streamInto(conv, input, signal, (t) => {
          if (!firstToken) { firstToken = true; emit({ type: 'info', message: null }); }
          emit({ type: 'delta', delta: { content: t } });
        });
        emit({ type: 'info', message: null });
        dbg('raw model output:', full);

        const { content, tool_calls } = splitToolCalls(full);
        emit({ type: 'round_end', content });
        const asst = { role: 'assistant', content };
        if (tool_calls.length) asst.tool_calls = tool_calls;
        emit({ type: 'message_added', message: asst });
        if (!tool_calls.length) break;

        let feedback = '';
        for (const tc of tool_calls) {
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
            out = res.ok ? await res.json() : { result: 'Error: tool endpoint ' + res.status + ' — service worker not ready.' };
          } catch (e) {
            if (e && e.name === 'AbortError') throw e;
            out = { result: 'Error: ' + ((e && e.message) || e) };
          }
          const toolResult = (out && out.result != null) ? out.result : '';
          emit({ type: 'tool_result', id: tc.id, result: toolResult, artifacts: out && out.artifacts });
          emit({ type: 'message_added', message: { role: 'tool', tool_call_id: tc.id, content: toolResult } });
          feedback += (tc.function && tc.function.name ? tc.function.name : 'tool') + ' result: ' + toolResult + '\n';
        }
        input = feedback;   // continue the SAME conversation with the tool output
      }
    } catch (e) {
      if (e && e.name === 'AbortError') throw e;   // finally cleans up; conversations.js handles abort
      emit({ type: 'info', message: null });
      emit({ type: 'error', message: 'litertlm: ' + ((e && e.message) || e) });
    } finally {
      try { if (conv && conv.delete) await conv.delete(); } catch (_) {}
    }
    emit({ type: 'agent_done' });
  }

  // ============================================================
  // Exports
  // ============================================================
  return { DEFAULT_MODELS, DEFAULT_N_CTX, streamRound, runConversation };
})();

if (typeof window !== 'undefined') window.SandpieLiteRTLM = SandpieLiteRTLM;
