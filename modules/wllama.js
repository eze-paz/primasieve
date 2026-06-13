// sandpie/modules/wllama.js — In-browser GGUF inference via wllama (llama.cpp WASM + WebGPU)
//
// wllama (https://github.com/ngxson/wllama) is a WebAssembly port of
// llama.cpp. As of v3 it supports WebGPU when available (with CPU/WASM
// fallback so it still runs on every device including iOS Safari), and
// it exposes a fully OpenAI-compatible chat completions API including
// `tools`, `tool_choice`, and `response_format: json_schema` — meaning
// tool-calling is handled natively by the underlying llama.cpp grammar
// engine rather than us prompting the model and parsing free-form text.
//
// This module:
//   - lazy-loads the wllama SDK + its WASM artifact from a CDN
//     (pinned to a specific version because the package's `main` field
//     points at a path that's missing on disk; we have to import the
//     explicit esm/index.min.js to dodge the publication quirk),
//   - keeps at most one model in memory (wllama only holds one at a
//     time), tearing down the previous when switching,
//   - passes messages / tools straight through to createChatCompletion
//     and just unrolls the OAI-shape streaming chunks.
//
// We still strip multimodal image_url parts from messages because the
// curated catalog is text-only (vision-capable GGUFs exist but they're
// not on offer here).

const SandpieWllama = (function() {
  'use strict';

  // wllama is pinned by patch — esm.run/esm.sh/jsdelivr `@N` redirects
  // currently resolve to a 404 because the package's `main` field points
  // at index.js but only esm/index.min.js actually exists in the publish.
  // Bumping = explicit edit here; trade-off is worth it for reliability.
  const WLLAMA_VERSION = '3.2.3';
  const SDK_URL  = `https://cdn.jsdelivr.net/npm/@wllama/wllama@${WLLAMA_VERSION}/esm/index.min.js`;
  const WASM_URL = `https://cdn.jsdelivr.net/npm/@wllama/wllama@${WLLAMA_VERSION}/esm/wasm/wllama.wasm`;

  // Curated GGUF catalog. URLs point at HuggingFace direct downloads.
  // The dropdown also offers a "Custom" free-text option for any GGUF URL.
  const DEFAULT_MODELS = [
    {
      id: 'qwen2.5-1.5b-instruct-q4_k_m',
      label: 'Qwen 2.5 1.5B Instruct — Q4_K_M (~1 GB, tool-calling)',
      url: 'https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf',
    },
    {
      id: 'qwen2.5-3b-instruct-q4_k_m',
      label: 'Qwen 2.5 3B Instruct — Q4_K_M (~2 GB, tool-calling)',
      url: 'https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf',
    },
    {
      id: 'hermes-3-llama-3.1-8b-q4_k_m',
      label: 'Hermes 3 Llama 3.1 8B — Q4_K_M (~5 GB, best tool-calling)',
      url: 'https://huggingface.co/NousResearch/Hermes-3-Llama-3.1-8B-GGUF/resolve/main/Hermes-3-Llama-3.1-8B.Q4_K_M.gguf',
    },
    {
      id: 'phi-3.5-mini-instruct-q4_k_m',
      label: 'Phi 3.5 mini Instruct — Q4_K_M (~2.4 GB)',
      url: 'https://huggingface.co/bartowski/Phi-3.5-mini-instruct-GGUF/resolve/main/Phi-3.5-mini-instruct-Q4_K_M.gguf',
    },
    {
      id: 'tinyllama-1.1b-chat-q4_k_m',
      label: 'TinyLlama 1.1B Chat — Q4_K_M (~700 MB, fast, no tools)',
      url: 'https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf',
    },
  ];

  // ============================================================
  // Debug logging
  // ============================================================
  // Off by default. Flip via DevTools console:
  //   localStorage.setItem('sandpie-wllama-debug', '1')
  // (then reload) — or just inspect window.__wllamaLastRound which is
  // always populated regardless of the flag. The flag controls noisy
  // per-round console output; the raw payload capture is free.
  const DEBUG_KEY = 'sandpie-wllama-debug';
  function isDebug() {
    try { return localStorage.getItem(DEBUG_KEY) === '1'; }
    catch (_) { return false; }
  }
  function dbg(...args) {
    if (isDebug()) console.log('[wllama]', ...args);
  }

  // ============================================================
  // GGUF cache (Cache Storage API — NOT OPFS, so Dropbox can't see it)
  // ============================================================
  // Cache Storage is a per-origin store the browser manages, separate
  // from OPFS. Survives reloads. Browser may evict under quota pressure
  // but for the curated models (≤5 GB) we'd typically be well under
  // the per-origin quota (~6%+ of disk). Cache key = the GGUF URL.
  const MODEL_CACHE_NAME = 'sandpie-wllama-models';

  /**
   * Fetch a model GGUF, populating Cache Storage on miss. Streams the
   * body chunk-by-chunk so onProgress fires the same way whether we're
   * reading from the network or from the cache.
   *
   * @param {string} url
   * @param {(report:{loaded:number,total:number,progress:number,fromCache:boolean}) => void} [onProgress]
   * @returns {Promise<Blob>}
   */
  async function fetchModelBlob(url, onProgress) {
    let cache = null;
    try { cache = await caches.open(MODEL_CACHE_NAME); }
    catch (e) { dbg('Cache Storage unavailable, falling back to direct fetch:', e && e.message); }

    let res;
    let fromCache = false;
    if (cache) {
      const hit = await cache.match(url);
      if (hit) {
        dbg(`cache hit: ${url}`);
        res = hit;
        fromCache = true;
      }
    }
    if (!res) {
      dbg(`cache miss → fetching: ${url}`);
      const network = await fetch(url);
      if (!network.ok) throw new Error(`wllama: model fetch failed (${network.status} ${network.statusText}) for ${url}`);
      // Stash a clone in Cache Storage in the background. Clone the
      // Response BEFORE we start reading; once a body is read, the
      // clone's body would be locked too. cache.put is best-effort —
      // failures (quota, write race) just mean next reload re-downloads.
      if (cache) {
        cache.put(url, network.clone()).catch(e => console.warn('[wllama] cache.put failed:', e && e.message));
      }
      res = network;
    }

    const total = parseInt(res.headers.get('content-length') || '0', 10);
    const reader = res.body.getReader();
    const chunks = [];
    let loaded = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      loaded += value.byteLength;
      try {
        onProgress && onProgress({
          loaded, total,
          progress: total ? loaded / total : 0,
          fromCache,
        });
      } catch (_) {}
    }
    return new Blob(chunks);
  }

  // ============================================================
  // SDK + model singleton
  // ============================================================

  let _sdkPromise = null;
  function loadSDK() {
    if (!_sdkPromise) _sdkPromise = import(SDK_URL);
    return _sdkPromise;
  }

  // wllama's default n_ctx is 1024 — way too small for sandpie's
  // ~4-5K-token system prompt + tools[]. We default to 8192 which
  // handles a normal first-turn comfortably without blowing memory.
  // The user can override per-provider in the modal.
  const DEFAULT_N_CTX = 8192;

  // wllama holds at most one model in memory at a time. We key by URL,
  // n_ctx, and flash_attn — all are load-time parameters that require a
  // fresh model load when changed.
  let _instance = null;
  let _instanceUrl = null;
  let _instanceCtx = 0;
  let _instanceFlashAttn = true;
  let _loadingKey = null;

  async function getInstance(modelUrl, onProgress, opts) {
    if (!modelUrl) throw new Error('wllama: modelUrl is required');
    const nCtx = (opts && opts.nCtx) || DEFAULT_N_CTX;
    const flashAttn = (opts && opts.flashAttn !== false);
    const key = modelUrl + '|' + nCtx + '|fa:' + flashAttn;
    if (_instance && _instanceUrl === modelUrl && _instanceCtx === nCtx && _instanceFlashAttn === flashAttn) return _instance;
    if (_loadingKey === key) {
      while (_loadingKey === key) await new Promise(r => setTimeout(r, 50));
      if (_instance && _instanceUrl === modelUrl && _instanceCtx === nCtx && _instanceFlashAttn === flashAttn) return _instance;
    }
    _loadingKey = key;
    try {
      if (_instance) {
        try { await _instance.exit(); } catch (_) {}
        _instance = null;
        _instanceUrl = null;
        _instanceCtx = 0;
        _instanceFlashAttn = true;
      }
      // Fetch the GGUF and pass a Blob to loadModel(), which skips
      // wllama's ModelManager/CacheManager entirely (its useCache:false
      // flag is misnamed in the SDK — it forces a fresh download but
      // STILL writes to OPFS `cache/`, which sandpie's Dropbox sync
      // then tries to upload).
      //
      // We persist the fetched bytes in the browser's Cache Storage
      // API. That's a different storage area from OPFS — opfs.list()
      // doesn't walk it, so Dropbox sync never sees it. Survives page
      // reloads; eviction follows the browser's per-origin quota
      // policy. Falls back to a direct fetch when Cache Storage is
      // unavailable (private mode in some browsers, etc).
      const ggufBlob = await fetchModelBlob(modelUrl, onProgress);

      const { Wllama } = await loadSDK();
      // v3 constructor takes a single `default` WASM path; the worker
      // code is inlined into the SDK bundle so no separate worker URL
      // is needed. WebGPU is auto-enabled when supported.
      const inst = new Wllama({ default: WASM_URL });
      await inst.loadModel([ggufBlob], { n_ctx: nCtx, flash_attn: flashAttn });
      _instance = inst;
      _instanceUrl = modelUrl;
      _instanceCtx = nCtx;
      _instanceFlashAttn = flashAttn;
      return inst;
    } finally {
      if (_loadingKey === key) _loadingKey = null;
    }
  }

  // ============================================================
  // Messages adapter
  // ============================================================

  /**
   * wllama's createChatCompletion accepts OAI-shape messages (system /
   * user / assistant / tool) natively. The only thing we strip is image
   * content parts, because the curated catalog is text-only — passing a
   * multimodal content array to a text model would error.
   */
  function adaptMessages(messages) {
    const out = [];
    for (const m of messages) {
      if (!m) continue;
      let content = m.content;
      if (Array.isArray(content)) {
        let text = '';
        for (const part of content) {
          if (part && part.type === 'text' && part.text) {
            text += (text ? '\n' : '') + part.text;
          } else if (part && part.type === 'image_url') {
            text += (text ? '\n' : '') + '[image attachment — text-only model, image not visible]';
          }
        }
        content = text;
      }
      out.push({ role: m.role, content: content || '', ...(m.tool_call_id ? { tool_call_id: m.tool_call_id } : {}), ...(m.tool_calls ? { tool_calls: m.tool_calls } : {}) });
    }
    return out;
  }

  // ============================================================
  // Streaming round
  // ============================================================

  /**
   * Run one chat-completion round. Streams OAI-shape deltas through
   * onDelta, accumulates content + tool_calls, returns
   * { content, tool_calls } when the round finishes.
   *
   * Tools are passed through to wllama; the underlying llama.cpp grammar
   * engine handles the function-calling output format, so we get proper
   * tool_calls entries in the chunks instead of having to parse them
   * out of free-form text.
   *
   * Inference options (all optional, fall back to sensible defaults):
   *   nCtx        — context window in tokens (load-time; triggers reload)
   *   flashAttn   — enable flash attention (load-time; triggers reload)
   *   maxTokens   — max output tokens per round
   *   temperature — sampling temperature (0–2)
   *   topP        — nucleus sampling (0–1)
   */
  async function streamRound({ modelUrl, messages, tools, signal, onDelta, onProgress, nCtx, flashAttn, maxTokens, temperature, topP }) {
    const wllama = await getInstance(modelUrl, onProgress, { nCtx, flashAttn });
    if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');

    let aborted = false;
    const onAbort = () => { aborted = true; };
    if (signal) {
      if (signal.aborted) onAbort();
      else signal.addEventListener('abort', onAbort, { once: true });
    }

    let content = '';
    const toolCalls = [];
    let finishReason = null;
    const t0 = (typeof performance !== 'undefined' ? performance.now() : Date.now());

    const request = {
      modelUrl,
      messages: adaptMessages(messages),
      max_tokens: maxTokens || 2048,
      temperature: temperature != null ? temperature : 0.7,
      top_p: topP != null ? topP : 0.9,
      tools: tools && tools.length ? tools : undefined,
    };
    dbg(`→ round: ${request.messages.length} msgs, ${tools ? tools.length : 0} tools, last role: ${request.messages.length ? request.messages[request.messages.length - 1].role : '(none)'}`);

    try {
      const stream = await wllama.createChatCompletion({
        messages: request.messages,
        max_tokens: request.max_tokens,
        temperature: request.temperature,
        top_p: request.top_p,
        stream: true,
        ...(request.tools ? { tools: request.tools } : {}),
      });

      for await (const chunk of stream) {
        if (aborted) break;
        const choice = chunk && chunk.choices && chunk.choices[0];
        const delta = choice && choice.delta;
        // finish_reason lands on the LAST chunk for that choice — capture
        // it so we can surface length-clipping vs natural stop in logs.
        if (choice && choice.finish_reason) finishReason = choice.finish_reason;
        if (!delta) continue;
        if (delta.content) content += delta.content;
        if (delta.tool_calls) {
          // Accumulate by index — same approach as the SW path. Some
          // models stream the function name/arguments in multiple pieces.
          for (const tc of delta.tool_calls) {
            const i = tc.index || 0;
            if (!toolCalls[i]) toolCalls[i] = { id: '', type: 'function', function: { name: '', arguments: '' } };
            if (tc.id) toolCalls[i].id = tc.id;
            if (tc.function && tc.function.name) toolCalls[i].function.name += tc.function.name;
            if (tc.function && tc.function.arguments) toolCalls[i].function.arguments += tc.function.arguments;
          }
        }
        // Forward the full delta object so the page-side applyDelta can
        // both append content AND build streaming tool-call bubbles.
        // Without delta.tool_calls reaching the renderer, the bubble is
        // never created and the later tool_started / tool_result events
        // silently no-op (markToolStarted looks up an element by tc.id
        // and bails when it can't find one).
        if (delta.content || delta.tool_calls) {
          try { onDelta && onDelta(delta); } catch (_) {}
        }
      }
    } finally {
      if (signal) signal.removeEventListener('abort', onAbort);
    }

    if (aborted) throw new DOMException('aborted', 'AbortError');

    const keptToolCalls = toolCalls.filter(tc => tc && tc.id);
    const dtMs = Math.round((typeof performance !== 'undefined' ? performance.now() : Date.now()) - t0);

    // Always capture the last round's raw payloads on window so users can
    // poke at them in DevTools regardless of whether the debug flag is
    // set. Cheap (one assignment); only the previous round is held.
    try {
      self.__wllamaLastRound = {
        ts: new Date().toISOString(),
        request,
        response: { content, tool_calls: keptToolCalls, finish_reason: finishReason, duration_ms: dtMs },
      };
    } catch (_) {}

    dbg(`← finish: ${finishReason || '(none)'} · content: ${content.length} chars · tool_calls: ${keptToolCalls.length} · ${dtMs}ms`);
    if (isDebug() && keptToolCalls.length) {
      for (const tc of keptToolCalls) dbg(`  tool: ${tc.function.name} args: ${tc.function.arguments}`);
    }

    return { content, tool_calls: keptToolCalls };
  }

  // ============================================================
  // Conversation driver (page-side agent loop)
  // ============================================================
  // Emits the SAME agent-event protocol the service worker's runAgent
  // emits, so conversations.js can swap the event SOURCE (SW fetch ↔ this
  // page-side loop) at one seam and reuse its renderer, message
  // persistence, token accounting, abort handling, and generation:complete
  // lifecycle unchanged. v1 is TEXT-ONLY (single round, no tool loop);
  // page-side tool support is a documented follow-up.
  //
  // onEvent receives objects shaped exactly like conversations.js's
  // dispatchAgentEvent cases:
  //   { type:'round_start' } { type:'delta', delta } { type:'round_end', content }
  //   { type:'message_added', message } { type:'info', message } (null clears it)
  //   { type:'error', message } { type:'agent_done' }
  async function runConversation({ provider, messages, systemPrompt, signal }, onEvent) {
    const emit = (ev) => { try { onEvent && onEvent(ev); } catch (_) {} };
    const modelUrl = provider && (provider.endpoint || '').trim();
    if (!modelUrl) {
      emit({ type: 'error', message: 'wllama: this provider has no model URL — set the GGUF URL in Settings.' });
      emit({ type: 'agent_done' });
      return;
    }

    const msgs = [];
    if (systemPrompt) msgs.push({ role: 'system', content: systemPrompt });
    for (const m of (messages || [])) msgs.push(m);

    emit({ type: 'round_start' });

    let lastPct = -1;
    const onProgress = (p) => {
      if (!p) return;
      const pct = p.total ? Math.round((p.progress || 0) * 100) : 0;
      if (pct === lastPct) return;
      lastPct = pct;
      emit({ type: 'info', message: `Loading model… ${pct}%${p.fromCache ? ' (cache)' : ''}` });
    };

    let result;
    try {
      result = await streamRound({
        modelUrl,
        messages: msgs,
        tools: [],                                   // text-only in v1
        signal,
        onProgress,
        nCtx: (provider.contextWindow | 0) || DEFAULT_N_CTX,
        flashAttn: provider.flashAttn !== false,
        maxTokens: provider.maxTokens || undefined,
        temperature: provider.temperature != null ? provider.temperature : undefined,
        topP: provider.topP != null ? provider.topP : undefined,
        onDelta: (delta) => emit({ type: 'delta', delta }),
      });
    } catch (e) {
      if (e && e.name === 'AbortError') throw e;     // let conversations.js show "Stopped."
      emit({ type: 'info', message: null });          // clear any "Loading…" notice
      emit({ type: 'error', message: 'wllama: ' + ((e && e.message) || e) });
      emit({ type: 'agent_done' });
      return;
    }

    emit({ type: 'info', message: null });            // clear the load notice
    emit({ type: 'round_end', content: result.content });
    emit({ type: 'message_added', message: { role: 'assistant', content: result.content } });
    emit({ type: 'agent_done' });
  }

  return {
    DEFAULT_MODELS,
    DEFAULT_N_CTX,
    getInstance,
    streamRound,
    runConversation,
  };
})();

if (typeof window !== 'undefined') window.SandpieWllama = SandpieWllama;
