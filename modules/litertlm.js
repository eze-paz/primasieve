// sandpie/modules/litertlm.js — Main-thread shim for window.SandpieLiteRTLM,
// backed by a Web Worker (litertlm-worker.js) that runs the actual LiteRT-LM
// (Gemma) WASM+WebGPU engine OFF the main thread.
//
// WHY A WORKER NOW: the LiteRT-LM Web SDK previously ran inline on the main thread,
// so the WASM+WebGPU prefill/decode loop blocked page rendering, input, and scroll
// during generation — visibly janky UX. The Qwen3 backend already runs in a worker
// (webgpu-host.js); this brings Gemma to parity. The SDK is worker-compatible with
// two tricks, both in litertlm-worker.js: a CLASSIC worker (module workers forbid
// the importScripts() the WASM loader uses) and an Emscripten locateFile override
// (so sibling .wasm/.data assets resolve to the CDN, not our origin).
//
// This shim mirrors webgpu-host.js: it forwards runConversation/streamRound/unload
// to the worker, relays the event protocol back, and runs tool calls the worker
// requests through the shared in-page _sandpieWorker. conversations.js / providers.js
// / loop-lab.js call the SAME interface (DEFAULT_MODELS, DEFAULT_N_CTX,
// runConversation, streamRound, unload) unchanged.
//
// TOOL CALLING: the Web SDK has no native tools API; Gemma 4 emits tool calls in
// its text, which the worker parses. See litertlm-worker.js for the parsers.

const SandpieLiteRTLM = (function () {
  'use strict';

  const WORKER_URL = 'modules/litertlm-worker.js?v=1';
  const DEFAULT_N_CTX = 4096;

  // Curated, web-converted Gemma 4 (the "-web.litertlm" builds from the official
  // litert-community org). modelId is the direct file URL handed to the engine.
  // KEEP IN SYNC with any model logic in the worker (there is none — the worker takes
  // the URL as provider.endpoint), so this list is the single source of truth.
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
    // NOTE: community Qwen 3.5 / VibeThinker .litertlm builds were tried and REMOVED
    // (2026-06-18): the LiteRT-LM web SDK aborts on their HF/BPE tokenizer ("Streaming
    // HF_Tokenizer_Zlib section is not supported yet") — it parses only SentencePiece
    // (what Gemma ships). Re-add only once the web SDK gains HF-tokenizer support.
    // Users can still paste such a URL via the "Custom" option.
  ];

  const DEBUG_KEY = 'sandpie-litertlm-debug';
  function isDebug() { try { return localStorage.getItem(DEBUG_KEY) === '1'; } catch (_) { return false; } }

  // ============================================================
  // sp-decoding: while local inference runs, add body.sp-decoding so shared CSS kills
  // GPU-compositor work (backdrop-filter blur recompute, infinite animations) that
  // competes with the WebGPU decode loop for the shared GPU. Ref-counted. (The engine
  // now runs in a worker, but the compositor contention is on the SAME GPU, so this
  // still matters — identical to webgpu-host.js setBusy.)
  // ============================================================
  let _busy = 0;
  function setBusy(on) {
    try {
      const b = (typeof document !== 'undefined') && document.body; if (!b) return;
      if (on) { if (_busy++ === 0) b.classList.add('sp-decoding'); }
      else { _busy = Math.max(0, _busy - 1); if (_busy === 0) b.classList.remove('sp-decoding'); }
    } catch (_) {}
  }
  const _busyOff = () => setBusy(false);

  // ============================================================
  // Worker lifecycle + run registry.
  // ============================================================
  let _worker = null, _seq = 0;
  const _runs = new Map();          // id -> { emit, resolve, reject, isRound }
  const _unloadWaiters = new Map(); // ackId -> resolve

  // Run a tool the worker requested by routing it through the SHARED in-page
  // _sandpieWorker (the same Web Worker the cloud loop + WebGPU backend use — it reads
  // OPFS directly and handles every tool incl. load_skill), then reply to the engine
  // worker. Mirrors webgpu-host.js runTool.
  let _toolReqSeq = 0;
  const TOOL_TIMEOUT_MS = 5 * 60 * 1000;
  function runTool(m) {
    const reply = (result, artifacts) => {
      try { _worker && _worker.postMessage({ t: 'toolResult', reqId: m.reqId, result, artifacts: artifacts || null }); } catch (_) {}
    };
    const sw = window._sandpieWorker;
    if (!sw) { reply('Error: sandpie-worker not ready — reload the page.', null); return; }
    const id = 'lt-' + (++_toolReqSeq);
    let settled = false;
    const finish = (result, artifacts) => { if (settled) return; settled = true; cleanup(); reply(result, artifacts); };
    const onMsg = (e) => { const r = e.data || {}; if (r.id !== id || r.type !== 'tool_result') return; finish(r.result || '', r.artifacts || null); };
    const onErr = () => finish('Error: sandpie-worker crashed — retry (it restarts automatically).', null);
    const timer = setTimeout(() => finish('Error: tool timed out after ' + (TOOL_TIMEOUT_MS / 1000) + 's — the worker may be stuck.', null), TOOL_TIMEOUT_MS);
    function cleanup() { clearTimeout(timer); sw.removeEventListener('message', onMsg); sw.removeEventListener('error', onErr); }
    sw.addEventListener('message', onMsg);
    sw.addEventListener('error', onErr);
    sw.postMessage({ type: 'tool', id, name: m.name, args: m.args, conversation_file_name: m.convId });
  }

  function worker() {
    if (_worker) return _worker;
    _worker = new Worker(WORKER_URL);   // CLASSIC worker — see litertlm-worker.js header
    _worker.onmessage = (e) => {
      const m = e.data || {};
      if (m.t === 'tool') { runTool(m); return; }
      if (m.t === 'unloadDone') { const f = _unloadWaiters.get(m.ackId); if (f) f(); return; }
      const r = _runs.get(m.id);
      if (!r) return;
      if (m.t === 'emit') { try { r.emit(m.ev); } catch (_) {} return; }
      if (m.t === 'done') { _runs.delete(m.id); r.resolve(); return; }
      if (m.t === 'roundDone') { _runs.delete(m.id); r.resolve(m.result); return; }
      if (m.t === 'err') {
        _runs.delete(m.id);
        const err = (m.name === 'AbortError')
          ? new DOMException('aborted', 'AbortError')
          : Object.assign(new Error(m.message || 'LiteRT-LM worker error'), { name: m.name || 'Error' });
        r.reject(err);
      }
    };
    _worker.onerror = (ev) => { console.error('[litertlm] worker error', (ev && ev.message) || ev); };
    return _worker;
  }

  // Strip the non-serializable AbortSignal + callbacks before postMessage.
  function serializableConfig(config) {
    return {
      provider: config.provider,
      messages: config.messages,
      systemPrompt: config.systemPrompt,
      tools: config.tools,
      convId: config.convId,
      modelUrl: config.modelUrl,   // streamRound
      nCtx: config.nCtx,           // streamRound
    };
  }

  // Post a run to the worker, relay emit events, resolve/reject via the registry.
  // isRound=true resolves with the {content, tool_calls} result (streamRound).
  function _dispatch(kind, config, emit, isRound) {
    const w = worker();
    const id = ++_seq;
    const signal = config && config.signal;
    const cfg = serializableConfig(config);
    const p = new Promise((resolve, reject) => {
      _runs.set(id, { emit: emit || (function () {}), resolve, reject, isRound });
      if (signal) {
        signal.addEventListener('abort', () => { try { w.postMessage({ t: 'abort', id }); } catch (_) {} }, { once: true });
      }
      w.postMessage({ t: kind, id, config: cfg, debug: isDebug() });
      if (signal && signal.aborted) { try { w.postMessage({ t: 'abort', id }); } catch (_) {} }
    });
    setBusy(true);
    p.then(_busyOff, _busyOff);
    return p;
  }

  // ============================================================
  // Public interface (unchanged for conversations.js / providers.js / loop-lab.js).
  // ============================================================
  async function runConversation(config, emit) {
    // Single active local backend: free the OTHER local LLMs' GPU first so only one
    // holds a WebGPU device at a time. Cheap no-ops if not loaded.
    try { await window.SandpieQwen3?.unload?.(); } catch (_) {}
    try { await window.SandpieQwen35?.unload?.(); } catch (_) {}
    try { await window.SandpieWllama?.unload?.(); } catch (_) {}
    try { await window.SandpieTransformersJS?.unload?.(); } catch (_) {}
    return _dispatch('run', config, emit, false);
  }

  // One-shot completion. Preserves the old callback signature: onDelta/onProgress are
  // fed from the worker's delta/progress emit events; resolves with {content, tool_calls}.
  async function streamRound(config) {
    const onDelta = config && config.onDelta;
    const onProgress = config && config.onProgress;
    const emit = (ev) => {
      if (!ev) return;
      if (ev.type === 'delta' && onDelta) { try { onDelta(ev.delta); } catch (_) {} }
      else if (ev.type === 'progress' && onProgress) { try { onProgress(ev.p); } catch (_) {} }
    };
    return _dispatch('streamRound', config, emit, true);
  }

  // Deep-free the worker's engine (and its WebGPU device), resolving once the worker
  // acks. No-op if the worker was never created. 4s timeout so it can't hang.
  function unload() {
    const w = _worker;
    if (!w) return Promise.resolve();
    return new Promise((resolve) => {
      const ackId = ++_seq;
      let done = false;
      const finish = () => { if (done) return; done = true; _unloadWaiters.delete(ackId); resolve(); };
      _unloadWaiters.set(ackId, finish);
      setTimeout(finish, 4000);
      try { w.postMessage({ t: 'unload', ackId }); } catch (_) { finish(); }
    });
  }

  return { DEFAULT_MODELS, DEFAULT_N_CTX, unload, streamRound, runConversation, _viaWorker: true };
})();

if (typeof window !== 'undefined') window.SandpieLiteRTLM = SandpieLiteRTLM;
