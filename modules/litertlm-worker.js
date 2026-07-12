// sandpie/modules/litertlm-worker.js — LiteRT-LM (Gemma) inference in a CLASSIC
// Web Worker, off the main thread. The main-thread shim (litertlm.js) forwards
// runConversation/streamRound here and relays the event protocol back, so page
// rendering can't be blocked by the WASM+WebGPU decode loop (the old design ran
// the engine inline on the main thread → janky UI during generation).
//
// WHY A CLASSIC WORKER (not type:'module'): the LiteRT-LM WASM runtime loads its
// glue via importScripts(), which MODULE workers forbid. A classic worker supports
// both importScripts() AND dynamic import() (modern Chrome), so we import the ESM
// SDK dynamically here.
//
// WHY self.Module.locateFile (set below, before any import): the Emscripten WASM
// glue resolves its sibling .wasm/.data assets relative to the script directory.
// On the main thread that's document-based and lands on the CDN; in a worker there
// is no document, so it falls back to self.location (our own origin) and 404s —
// fetching our SPA's index.html instead of the .wasm (WebAssembly magic-word error
// "found 3c 21 44 4f" = "<!DO…"). Overriding locateFile pins every sibling asset to
// the CDN wasm dir, which is how the runtime loads cleanly off the main thread.

'use strict';

const PACKAGE_VERSION = '0.13.1';
const ESM_URL = `https://cdn.jsdelivr.net/npm/@litert-lm/core@${PACKAGE_VERSION}/+esm`;
// The Emscripten glue's sibling-asset directory. Matches LiteRtLm.DEFAULT_WASM_PATH
// in the SDK; pinned to the same version as ESM_URL on purpose.
const WASM_BASE = `https://cdn.jsdelivr.net/npm/@litert-lm/core@${PACKAGE_VERSION}/wasm/`;
// Pin sibling .wasm/.data fetches to the CDN (see header). Set BEFORE the SDK import
// so it's in place when getOrLoadGlobalLiteRtLm() instantiates the module.
self.Module = { locateFile: (p) => (/^https?:\/\//.test(p) ? p : WASM_BASE + p) };

const DEFAULT_N_CTX = 4096;

// ============================================================
// Debug logging — workers have no localStorage; the host passes the debug flag in.
// ============================================================
let _debug = false;
function dbg(...a) { if (_debug) console.log('[litertlm-worker]', ...a); }

function hasWebGPU() { return typeof navigator !== 'undefined' && !!navigator.gpu; }

// ============================================================
// Runtime + engine — one cached engine per (model URL, context size).
// ============================================================
let _lib = null, _engine = null, _engineModel = null, _engineCtx = 0;

async function loadLib() {
  if (_lib) return _lib;
  dbg('importing LiteRT-LM from', ESM_URL);
  try { _lib = await import(ESM_URL); }
  catch (e) { console.error('[litertlm-worker] failed to import LiteRT-LM from', ESM_URL, e); throw e; }
  return _lib;
}

// ============================================================
// WebGPU device — fp32-forced (no shader-f16). See litertlm.js history: Gemma's
// architecture (RMSNorm scale 1.0, tight softmax) loses meaningful precision in
// fp16 → off-distribution logits, non-English token leakage, repetition loops. We
// create the device WITHOUT 'shader-f16' so the SDK's WGSL shaders use f32
// everywhere, then pre-set it on the WASM module so the SDK skips its own
// (fp16-enabling) device creation. WebGPU device creation works in a worker.
// ============================================================
async function createFp32WebGpuDevice() {
  const adapter = await navigator.gpu.requestAdapter({ powerPreference: 'high-performance' });
  if (!adapter) {
    throw new Error(
      'LiteRT-LM: No WebGPU adapter found. WebGPU is required for in-browser Gemma inference. '
      + 'Use Chrome/Edge with WebGPU enabled, or pick a wllama (CPU) model instead.'
    );
  }
  // Deliberately do NOT request 'shader-f16'. Its absence forces fp32 shaders.
  const requiredFeatures = [];
  if (adapter.features.has('subgroups')) requiredFeatures.push('subgroups');
  const requiredLimits = {
    maxBufferSize: adapter.limits.maxBufferSize,
    maxStorageBufferBindingSize: adapter.limits.maxStorageBufferBindingSize,
    maxStorageBuffersPerShaderStage: adapter.limits.maxStorageBuffersPerShaderStage,
    maxTextureDimension2D: adapter.limits.maxTextureDimension2D,
  };
  let device;
  try {
    device = await adapter.requestDevice({ requiredFeatures, requiredLimits });
  } catch (e) {
    throw new Error(
      'LiteRT-LM: Failed to create a WebGPU device (fp32 mode). '
      + 'The GPU adapter was found but device creation failed: '
      + ((e && e.message) || e)
      + '. Try closing other GPU-heavy tabs or use a wllama (CPU) model instead.'
    );
  }
  if (device.features.has('shader-f16')) {
    console.warn('[litertlm-worker] WARNING: WebGPU device has shader-f16 despite not requesting it. '
      + 'The SDK may use fp16 shaders — Gemma output may be corrupted (non-English tokens, '
      + 'repetition loops) on this device.');
  }
  dbg('WebGPU device created (fp32-forced, shader-f16 excluded). Features:', requiredFeatures);
  return device;
}

// ============================================================
// Model cache (Cache Storage API — available in workers). The SDK fetches the
// .litertlm URL itself with no persistent cache, so we fetch it through Cache
// Storage and hand Engine.create the cached byte stream.
// ============================================================
const MODEL_CACHE_NAME = 'sandpie-litertlm-models';
const fmtMB = (b) => (b >= 10485760 ? (b / 1048576).toFixed(0) : (b / 1048576).toFixed(1)) + ' MB';

async function fetchModelStream(url, onProgress) {
  let cache = null;
  try { cache = await caches.open(MODEL_CACHE_NAME); }
  catch (e) { dbg('Cache Storage unavailable, direct fetch:', e && e.message); }

  let res = null, fromCache = false;
  if (cache) {
    const hit = await cache.match(url);
    if (hit) { dbg('cache hit:', url); res = hit; fromCache = true; }
  }
  if (!res) {
    dbg('cache miss → fetching:', url);
    const net = await fetch(url);
    if (!net.ok) throw new Error(`litertlm: model fetch failed (${net.status} ${net.statusText}) for ${url}`);
    if (cache) cache.put(url, net.clone()).catch(e => console.warn('[litertlm-worker] cache.put failed:', e && e.message));
    res = net;
  }
  if (!res.body) return null;

  const total = parseInt(res.headers.get('content-length') || '0', 10);
  let loaded = 0;
  const reader = res.body.getReader();
  return new ReadableStream({
    async pull(controller) {
      const { done, value } = await reader.read();
      if (done) { controller.close(); return; }
      loaded += value.byteLength;
      try { onProgress && onProgress({ loaded, total, progress: total ? loaded / total : 0, fromCache }); } catch (_) {}
      controller.enqueue(value);
    },
    cancel(reason) { try { reader.cancel(reason); } catch (_) {} },
  });
}

async function ensureEngine(modelUrl, nCtx, onProgress) {
  const ctx = (nCtx | 0) || DEFAULT_N_CTX;
  if (_engine && _engineModel === modelUrl && _engineCtx === ctx) return _engine;
  if (!hasWebGPU()) {
    throw new Error('LiteRT-LM needs WebGPU, which this browser/profile does not expose (navigator.gpu is missing). Use Chrome/Edge with WebGPU enabled, or pick a wllama (CPU) model instead.');
  }
  if (_engine) { try { await _engine.delete(); } catch (_) {} _engine = null; _engineModel = null; _engineCtx = 0; }
  try { onProgress && onProgress({ status: 'loading' }); } catch (_) {}
  const lib = await loadLib();
  dbg('Engine.create', modelUrl, 'maxNumTokens', ctx);
  const modelSource = (await fetchModelStream(modelUrl, onProgress)) || modelUrl;

  // Pre-set an fp32-forced WebGPU device BEFORE Engine.create so the SDK skips its
  // own fp16-enabling device creation (see createFp32WebGpuDevice header).
  let litertlm = null;
  try { litertlm = await lib.getOrLoadGlobalLiteRtLm(); }
  catch (e) { throw new Error('LiteRT-LM: Failed to load WASM runtime: ' + ((e && e.message) || e)); }
  if (litertlm && litertlm.liteRtLmWasm && !litertlm.liteRtLmWasm.preinitializedWebGPUDevice) {
    const device = await createFp32WebGpuDevice();
    litertlm.liteRtLmWasm.preinitializedWebGPUDevice = device;
    dbg('Pre-set fp32 WebGPU device on WASM module');
  }

  _engine = await lib.Engine.create({ model: modelSource, mainExecutorSettings: { maxNumTokens: ctx } });
  _engineModel = modelUrl;
  _engineCtx = ctx;
  return _engine;
}

// ============================================================
// Tool plumbing — prompt-based (the Web SDK has no native tools API). Identical to
// the pre-migration litertlm.js so behavior is unchanged.
// ============================================================
function buildToolPreamble(tools) {
  const fns = (tools || []).filter(t => t && t.type === 'function').map(t => t.function).filter(Boolean);
  if (!fns.length) return '';
  const specs = fns.map(f => `- ${f.name}: ${f.description || ''}\n  arguments (JSON schema): ${JSON.stringify(f.parameters || {})}`).join('\n');
  return [
    'You can call tools using your function-calling format when one is needed; otherwise just answer normally.',
    'Available tools:',
    specs,
  ].join('\n');
}

function parseToolCalls(text) {
  const tool_calls = [];
  const seen = new Set();

  const rxToolCall = /<\|?tool_call>\s*([\s\S]*?)\s*(?:<\/tool_call>|<tool_call\|>)/g;
  let m;
  while ((m = rxToolCall.exec(text)) !== null) {
    if (seen.has(m[1])) continue;
    seen.add(m[1]);
    try { tool_calls.push(normalizeToolCall(JSON.parse(m[1].trim()))); }
    catch (e) { dbg('failed to parse <tool_call> JSON:', m[1]); }
  }

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
  let args = raw.arguments || raw.arguments_text || (raw.function && raw.function.arguments) || raw.params || raw.parameters || raw.args || {};
  if (typeof args === 'string') { try { args = JSON.parse(args); } catch (_) { args = {}; } }
  return {
    id: 'call_' + Math.random().toString(36).slice(2, 11),
    type: 'function',
    function: { name, arguments: typeof args === 'string' ? args : JSON.stringify(args) },
  };
}

// Gemma 4's NATIVE function-calling format:
//   <|tool_call>call:NAME{key:<|"|>value<|"|>, ...}<tool_call|>
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
  try {
    const j = body
      .replace(/<\|"\|>([\s\S]*?)<\|"\|>/g, (_, s) => JSON.stringify(s))
      .replace(/(^|[,{]\s*)([A-Za-z_][\w.]*)\s*:/g, '$1"$2":');
    const obj = JSON.parse('{' + j + '}');
    if (obj && typeof obj === 'object' && !Array.isArray(obj)) return obj;
  } catch (_) { /* fall through to tolerant tiers */ }

  const args = {};
  let m, any = false;
  const rxTok = /([A-Za-z_][\w.]*)\s*:\s*<\|"\|>([\s\S]*?)<\|"\|>/g;
  while ((m = rxTok.exec(body)) !== null) { args[m[1]] = m[2]; any = true; }
  if (any) return args;
  const rxStr = /([A-Za-z_][\w.]*)\s*:\s*"([\s\S]*?)"\s*(?=,\s*[A-Za-z_][\w.]*\s*:|\}?\s*$)/g;
  while ((m = rxStr.exec(body)) !== null) { args[m[1]] = m[2]; any = true; }
  if (any) return args;
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
    .replace(/<\|channel>thought[\s\S]*?<channel\|>/gi, '')
    .replace(/<\|channel>[a-z]*\r?\n?/gi, '')
    .replace(/<channel\|>/g, '')
    .replace(/<\|?tool_call>[\s\S]*?(?:<tool_call\|>|<\/tool_call>)/g, '')
    .replace(/```json\s*[\s\S]*?```/g, '')
    .replace(/<tool_call\|>|<\|tool_call>|<\|"\|>/g, '')
    .replace(/<\|.*?>\n?/g, '')
    .trim()
    .replace(/^Assistant:\s*/i, '');
}

function mapRole(role) { return role === 'assistant' ? 'assistant' : role === 'system' ? 'system' : 'user'; }

function gemmaToolCallText(tc) {
  const name = (tc.function && tc.function.name) || '';
  let args = {};
  try { args = JSON.parse((tc.function && tc.function.arguments) || '{}'); } catch (_) {}
  const body = Object.keys(args || {}).map(k => {
    const v = args[k];
    if (typeof v === 'string') return `${k}: <|"|>${v}<|"|>`;
    return `${k}: ${JSON.stringify(v)}`;
  }).join(', ');
  return `<|tool_call>call:${name}{${body}}<tool_call|>`;
}
function mapContent(m) {
  if (m.role === 'tool') return 'Tool result' + (m.tool_call_id ? ' (' + m.tool_call_id + ')' : '') + ': ' + (m.content || '');
  let s = m.content || '';
  if (m.role === 'assistant' && Array.isArray(m.tool_calls) && m.tool_calls.length) {
    const trace = m.tool_calls.map(gemmaToolCallText).join('\n');
    s = s ? (s + '\n' + trace) : trace;
  }
  return s;
}

// ============================================================
// Sampling + conversation config.
// ============================================================
function buildSamplerParams() { return null; }

function buildConvConfig(provider, prefaceMsgs) {
  const cfg = {};
  if (prefaceMsgs && prefaceMsgs.length) cfg.preface = { messages: prefaceMsgs };
  const sampler = buildSamplerParams(provider);
  const maxOut = ((provider && provider.maxTokens) | 0) || 0;
  const sess = {};
  if (sampler) sess.samplerParams = sampler;
  if (maxOut > 0) sess.maxOutputTokens = maxOut;
  if (Object.keys(sess).length) cfg.sessionConfig = sess;
  return Object.keys(cfg).length ? cfg : undefined;
}

// ============================================================
// Live thought/answer splitter (fallback for inline channel markers).
// ============================================================
function makeThoughtSplitter(onReasoning, onContent) {
  const OPEN = '<|channel>thought', CLOSE = '<channel|>', HOLD = OPEN.length - 1;
  const stripStray = (s) => s.replace(/<\|channel>[a-z]*\r?\n?/gi, '').replace(/<channel\|>/g, '');
  let buf = '', mode = 'pre';
  const self2 = { answer: '', reasoning: '' };
  function out(text, reasoning) {
    const t = stripStray(text);
    if (!t) return;
    if (reasoning) { self2.reasoning += t; try { onReasoning && onReasoning(t); } catch (_) {} }
    else { self2.answer += t; try { onContent && onContent(t); } catch (_) {} }
  }
  function run(final) {
    for (;;) {
      if (mode === 'pre') {
        const i = buf.indexOf(OPEN);
        if (i === -1) {
          const safe = final ? buf.length : Math.max(0, buf.length - HOLD);
          if (safe > 0) { out(buf.slice(0, safe), false); buf = buf.slice(safe); }
          return;
        }
        if (i > 0) out(buf.slice(0, i), false);
        buf = buf.slice(i + OPEN.length).replace(/^\r?\n/, '');
        mode = 'thought';
        continue;
      }
      if (mode === 'thought') {
        const i = buf.indexOf(CLOSE);
        if (i === -1) {
          const safe = final ? buf.length : Math.max(0, buf.length - HOLD);
          if (safe > 0) { out(buf.slice(0, safe), true); buf = buf.slice(safe); }
          return;
        }
        if (i > 0) out(buf.slice(0, i), true);
        buf = buf.slice(i + CLOSE.length);
        mode = 'answer';
        continue;
      }
      const safe = final ? buf.length : Math.max(0, buf.length - HOLD);
      if (safe > 0) { out(buf.slice(0, safe), false); buf = buf.slice(safe); }
      return;
    }
  }
  self2.push = (t) => { if (t) { buf += t; run(false); } };
  self2.flush = () => run(true);
  return self2;
}

// ============================================================
// Low-level: stream one send over an ALREADY-created Conversation.
// ============================================================
async function streamInto(conv, input, signal, onText, onThought) {
  let full = '', thoughtAcc = '';
  const stream = conv.sendMessageStreaming(input || '');
  for await (const chunk of stream) {
    if (signal && signal.aborted) { try { conv.cancel(); } catch (_) {} throw new DOMException('aborted', 'AbortError'); }
    const th = chunk && chunk.channels && chunk.channels.thought;
    if (typeof th === 'string' && th) {
      let delta;
      if (th.startsWith(thoughtAcc)) { delta = th.slice(thoughtAcc.length); thoughtAcc = th; }
      else { delta = th; thoughtAcc += th; }
      if (delta && onThought) { try { onThought(delta); } catch (_) {} }
    }
    for (const item of (chunk && chunk.content) || []) {
      if (item && item.type === 'text' && item.text) { full += item.text; try { onText && onText(item.text); } catch (_) {} }
    }
    try { if (!self.__litertlmChunks) self.__litertlmChunks = []; if (self.__litertlmChunks.length < 5) self.__litertlmChunks.push(chunk); } catch (_) {}
  }
  return full;
}

function splitToolCalls(full) {
  let tool_calls = parseGemmaToolCalls(full);
  if (!tool_calls.length) tool_calls = parseToolCalls(full);
  return { content: cleanContent(full), tool_calls };
}

// ============================================================
// Tool RPC — ask the main thread (host shim) to run the tool via the shared
// _sandpieWorker, and await its reply. Mirrors webgpu-worker's tool bridge.
// ============================================================
let _toolReqSeq = 0;
const _toolWaiters = new Map();   // reqId -> resolve({result, artifacts})
function toolViaHost(name, args, convId, signal) {
  return new Promise((resolve, reject) => {
    const reqId = 'lt-' + (++_toolReqSeq);
    const onAbort = () => { _toolWaiters.delete(reqId); reject(new DOMException('aborted', 'AbortError')); };
    if (signal) {
      if (signal.aborted) { onAbort(); return; }
      signal.addEventListener('abort', onAbort, { once: true });
    }
    _toolWaiters.set(reqId, (payload) => {
      if (signal) signal.removeEventListener('abort', onAbort);
      resolve(payload);
    });
    self.postMessage({ t: 'tool', reqId, name, args, convId });
  });
}
function onToolResult(reqId, result, artifacts) {
  const f = _toolWaiters.get(reqId);
  if (!f) return;
  _toolWaiters.delete(reqId);
  f({ result: result || '', artifacts: artifacts || null });
}

// ============================================================
// One-shot completion (streamRound) — stateless throwaway conversation.
// onDelta/onProgress become emit messages back to the host.
// ============================================================
async function streamRound({ modelUrl, messages, tools, signal, nCtx }, emit) {
  const engine = await ensureEngine(modelUrl, nCtx, (p) => emit({ type: 'progress', p }));
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
    full = await streamInto(conv, last.content, signal, (t) => emit({ type: 'delta', delta: { content: t } }));
  } finally {
    try { if (conv && conv.delete) await conv.delete(); } catch (_) {}
  }
  dbg('raw model output:', full);
  return splitToolCalls(full);
}

// ============================================================
// Agentic conversation loop — emits the SAME event protocol conversations.js
// expects; tool calls are RPC'd to the host. Structurally identical to the
// pre-migration litertlm.js runConversation, minus the sp-decoding toggle (now
// done by the host shim) and with toolViaHost in place of toolViaWorker.
// ============================================================
async function runConversation({ provider, messages, systemPrompt, tools, convId, signal }, emit) {
  const MAX_ROUNDS = 8;
  const toolList = (tools || []).filter(t => t && t.type === 'function');
  const nCtx = (provider.contextWindow | 0) || DEFAULT_N_CTX;

  let sysText = (systemPrompt && typeof systemPrompt === 'object') ? (systemPrompt.content || '') : (systemPrompt || '');
  const preamble = buildToolPreamble(toolList);
  if (preamble) sysText = sysText ? (sysText + '\n\n' + preamble) : preamble;

  // Gemma 4 reasoning: <|think|> at the START of the system prompt enables it.
  // OPT-IN — enabling it can crash LiteRT-LM's runtime mid-generation (upstream
  // bug). Only the provider's Thinking dropdown set to 'think' injects it.
  const wantThink = (provider.reasoning === 'think');
  if (wantThink) sysText = '<|think|>' + (sysText ? '\n' + sysText : '');

  const work = [];
  if (sysText) work.push({ role: 'system', content: sysText });
  for (const m of (messages || [])) { if (m && m.role) work.push(m); }

  try { self.__litertlmPrompts = []; } catch (_) {}

  let firstToken = false, engine;
  try {
    emit({ type: 'info', message: 'Loading Gemma locally (WebGPU)… first run downloads the model (cached after).' });
    let _lastPct = -1, _lastLoaded = 0;
    engine = await ensureEngine(provider.endpoint, nCtx, (p) => {
      if (!p || p.status === 'loading') return;
      if (p.total) {
        const pct = Math.round(p.progress * 100);
        if (pct === _lastPct) return; _lastPct = pct;
        emit({ type: 'info', message: `${p.fromCache ? 'Loading cached' : 'Downloading'} Gemma… ${fmtMB(p.loaded)} / ${fmtMB(p.total)} (${pct}%)` });
      } else if (p.loaded - _lastLoaded >= 8388608) {
        _lastLoaded = p.loaded;
        emit({ type: 'info', message: `${p.fromCache ? 'Loading cached' : 'Downloading'} Gemma… ${fmtMB(p.loaded)}` });
      }
    });
  } catch (e) {
    emit({ type: 'info', message: null });
    if (e && e.name === 'AbortError') throw e;
    emit({ type: 'error', message: 'litertlm: ' + ((e && e.message) || e) });
    emit({ type: 'agent_done' });
    return;
  }

  for (let round = 0; round < MAX_ROUNDS; round++) {
    if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');
    emit({ type: 'round_start' });

    const mapped = work.map(m => ({ role: mapRole(m.role), content: mapContent(m) }));
    const last = mapped.length ? mapped[mapped.length - 1] : { content: '' };
    const preface = mapped.slice(0, -1);
    const _cap = { round, system: sysText, preface, sent: last.content, rawOutput: null, answer: null, tool_calls: null };
    try { self.__litertlmPrompts.push(_cap); self.__litertlmPrompt = _cap; } catch (_) {}
    const conv = await engine.createConversation(buildConvConfig(provider, preface));

    const splitter = makeThoughtSplitter(
      (rz) => emit({ type: 'delta', delta: { reasoning: rz } }),
      (ct) => emit({ type: 'delta', delta: { content: ct } })
    );
    let full = '';
    try {
      full = await streamInto(conv, last.content, signal, (t) => {
        if (!firstToken) { firstToken = true; emit({ type: 'info', message: null }); }
        splitter.push(t);
      }, (rz) => {
        if (!firstToken) { firstToken = true; emit({ type: 'info', message: null }); }
        emit({ type: 'delta', delta: { reasoning: rz } });
      });
    } finally {
      try { if (conv && conv.delete) await conv.delete(); } catch (_) {}
    }
    splitter.flush();
    emit({ type: 'info', message: null });
    dbg('raw model output:', full);

    const { content, tool_calls } = splitToolCalls(splitter.answer);
    try { _cap.rawOutput = full; _cap.answer = splitter.answer; _cap.tool_calls = tool_calls; } catch (_) {}
    if (tool_calls.length) {
      emit({ type: 'delta', delta: { tool_calls: tool_calls.map((tc, i) => ({
        index: tc.index != null ? tc.index : i,
        id: tc.id,
        type: 'function',
        function: { name: (tc.function && tc.function.name) || '', arguments: (tc.function && tc.function.arguments) || '' },
      })) } });
    }
    emit({ type: 'round_end', content });
    const asst = { role: 'assistant', content };
    if (tool_calls.length) asst.tool_calls = tool_calls;
    work.push(asst);
    emit({ type: 'message_added', message: asst });
    if (!tool_calls.length) break;

    for (const tc of tool_calls) {
      if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');
      emit({ type: 'tool_started', tc });
      let args = {};
      try { args = JSON.parse((tc.function && tc.function.arguments) || '{}'); } catch (_) {}
      let out;
      try {
        out = await toolViaHost(tc.function && tc.function.name, args, convId, signal);
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

async function unload() {
  if (!_engine) return;
  try { await _engine.delete(); } catch (_) {}
  _engine = null; _engineModel = null; _engineCtx = 0;
}

// ============================================================
// Message protocol with the host shim (litertlm.js). Mirrors webgpu-worker.js:
//   host→worker: run / streamRound / abort / unload / toolResult
//   worker→host: emit / done / roundDone / err / tool / unloadDone
// ============================================================
const _aborters = new Map();   // run id -> AbortController

self.onmessage = async (e) => {
  const m = e.data || {};
  if (typeof m.debug === 'boolean') _debug = m.debug;

  if (m.t === 'toolResult') { onToolResult(m.reqId, m.result, m.artifacts); return; }

  if (m.t === 'abort') { const ac = _aborters.get(m.id); if (ac) { try { ac.abort(); } catch (_) {} } return; }

  if (m.t === 'unload') {
    try { await unload(); } catch (_) {}
    self.postMessage({ t: 'unloadDone', ackId: m.ackId });
    return;
  }

  if (m.t === 'run' || m.t === 'streamRound') {
    const id = m.id;
    const ac = new AbortController();
    _aborters.set(id, ac);
    const emit = (ev) => { try { self.postMessage({ t: 'emit', id, ev }); } catch (_) {} };
    try {
      if (m.t === 'run') {
        const cfg = m.config || {};
        cfg.signal = ac.signal;
        await runConversation(cfg, emit);
        self.postMessage({ t: 'done', id });
      } else {
        const cfg = m.config || {};
        cfg.signal = ac.signal;
        const result = await streamRound(cfg, emit);
        self.postMessage({ t: 'roundDone', id, result });
      }
    } catch (err) {
      self.postMessage({ t: 'err', id, name: (err && err.name) || 'Error', message: (err && err.message) || String(err) });
    } finally {
      _aborters.delete(id);
    }
  }
};
