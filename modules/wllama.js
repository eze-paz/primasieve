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

  // wllama is pinned by patch and loaded via its explicit esm/index.min.js path
  // (the package `main` field historically 404'd on CDN `@N` redirects; the
  // explicit path stays reliable across versions). Bumping = explicit edit here.
  //
  // wllama 3.5.x: GPU offload (n_gpu_layers > 0) still crashes the WASM worker
  // ("unreachable") on several common GGUFs when ALL layers are offloaded. We
  // keep n_gpu_layers defaulting to 0 (pure CPU) and make GPU offload opt-in
  // per provider. Flash attention, however, is safe on CPU (the crash is in the
  // WebGPU kernel path, which is never entered when n_gpu_layers=0), so we
  // default flash_attn to TRUE for CPU-only mode — it gives ~20-50% faster
  // prefill and ~30% less KV cache memory with zero quality loss.
  const WLLAMA_VERSION = '3.5.1';
  const SDK_URL  = `https://cdn.jsdelivr.net/npm/@wllama/wllama@${WLLAMA_VERSION}/esm/index.min.js`;
  const WASM_URL = `https://cdn.jsdelivr.net/npm/@wllama/wllama@${WLLAMA_VERSION}/esm/wasm/wllama.wasm`;

  // Curated GGUF catalog. URLs point at HuggingFace direct downloads.
  // The dropdown also offers a "Custom" free-text option for any GGUF URL.
  const DEFAULT_MODELS = [
    // Gemma 4 E2B — the SAME model the litertlm backend runs, but as a GGUF on CPU
    // (llama.cpp / WASM) instead of WebGPU. This is the PocketPal-equivalent path: it
    // sidesteps the WebGPU GPU-process memory ceiling that crashes litertlm on phones
    // ("Aw, Snap!"), trading it for single-thread WASM speed — a good deal on mobile,
    // where the GPU path is fragile. From unsloth (ggml-org ships only Q8_0/bf16). The
    // GGUF's embedded Gemma chat template handles formatting. NOTE: relies on wllama
    // 3.5.1's bundled llama.cpp carrying the gemma3n/gemma4 graph — ggml-org publishes
    // this GGUF, so llama.cpp supports it; if it fails to load in-tab the arch isn't
    // compiled into this WASM build (fall back to the litertlm/WebGPU Gemma entry).
    {
      id: 'gemma-4-e2b-it-q4_k_m',
      label: 'Gemma 4 E2B-it — Q4_K_M (~3.1 GB, CPU, mobile-stable alt to WebGPU/LiteRT)',
      url: 'https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/resolve/main/gemma-4-E2B-it-Q4_K_M.gguf',
    },
    // Qwen 3.5 — the hybrid Gated-DeltaNet family. The GGUF declares arch
    // "qwen35": most layers are SSM / linear-attention (a fixed-size recurrent
    // state, so decode cost is O(1) per token with no growing KV cache) with a
    // periodic full-attention layer. These need a wllama whose bundled llama.cpp
    // carries the qwen35 graph + delta_net / gated_delta / linear_attn ops — those
    // are present in the WASM (verified ≥3.4.1). DENSE variants only: small enough
    // for the browser. The MoE Qwen3.5 (35B-A3B and up) won't fit in a tab.
    {
      id: 'qwen3.5-0.8b-q4_k_m',
      label: 'Qwen 3.5 0.8B — Q4_K_M (~0.5 GB, DeltaNet, reasoning + tools)',
      url: 'https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF/resolve/main/Qwen3.5-0.8B-Q4_K_M.gguf',
    },
    {
      id: 'qwen3.5-2b-q4_k_m',
      label: 'Qwen 3.5 2B — Q4_K_M (~1.2 GB, DeltaNet, reasoning + tools)',
      url: 'https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf',
    },
    {
      id: 'qwen3.5-4b-q4_k_m',
      label: 'Qwen 3.5 4B — Q4_K_M (~2.6 GB, DeltaNet, reasoning + tools)',
      url: 'https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf',
    },
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
    {
      // RWKV-7 "G1" is a recurrent (RNN-style) reasoning model, NOT a transformer.
      // It takes a dedicated code path (see isRwkvUrl / streamRoundRwkv): raw
      // completion with a hand-built "User:/Assistant:" prompt and a `<think`
      // prefill, because G1 only reasons when its reply is seeded with `<think`
      // and it is not an OpenAI-style tool-caller. Detection is by URL substring
      // 'rwkv', so any custom RWKV GGUF URL also gets this path.
      id: 'rwkv7-g1g-1.5b-q4_k_m',
      label: 'RWKV7 G1g 1.5B — Q4_K_M (~1 GB, reasoning, no tools)',
      url: 'https://huggingface.co/shoumenchougou/RWKV7-G1g-1.5B-GGUF/resolve/main/rwkv7-g1g-1.5b-Q4_K_M.gguf',
    },
  ];

  // RWKV models (recurrent architecture) need the dedicated raw-completion path
  // below rather than createChatCompletion. RWKV GGUFs always carry 'rwkv' in
  // the filename, so a URL substring test covers both the catalog entry and any
  // custom RWKV GGUF URL the user pastes in.
  function isRwkvUrl(url) {
    return /rwkv/i.test(String(url || ''));
  }

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
    const blob = new Blob(chunks);
    // Release the chunk array references so GC can reclaim the typed-array
    // views sooner on memory-constrained devices (the Blob itself doesn't copy).
    chunks.length = 0;
    return blob;
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
  // n_ctx, flash_attn, n_gpu_layers, cache_type_k, cache_type_v, and n_threads
  // — all load-time parameters that require a fresh model load when changed.
  //
  // flash_attn defaults to TRUE for CPU-only mode (n_gpu_layers=0). The crash
  // that prompted disabling it ("RuntimeError: unreachable") happens in the
  // WebGPU kernel path, which is only entered when n_gpu_layers > 0. On CPU,
  // flash attention is a mathematically exact reformulation that gives
  // ~20-50% faster prefill and ~30% less KV cache memory. When GPU offload
  // is active, flash_attn is disabled (the WebGPU crash).
  let _instance = null;
  let _instanceUrl = null;
  let _instanceCtx = 0;
  let _instanceFlashAttn = false;
  let _instanceGpuLayers = 0;
  let _instanceThreads = 0;
  let _instanceBatch = 0;
  let _instanceCacheK = null;
  let _instanceCacheV = null;
  let _loadingKey = null;
  // After a worker error/timeout, the slot's KV cache may hold a partial token
  // sequence the engine can't reconcile. This flag forces ONE clean prefill
  // (cache_prompt:false) on the next chat round, then reuse resumes. Normal
  // edits/rewinds need no flag — the engine truncates to the common prefix.
  let _kvDirty = false;

  // Hard timeout guard for the streaming round.  If the wllama worker
  // crashes (the "unreachable" wasm trap), the async iterator never
  // yields another chunk and never rejects.  Without a guard the user
  // sits on an eternal spinner.  10 min is generous even for a slow
  // CPU-only run.
  const STREAM_TIMEOUT_MS = 10 * 60 * 1000;

  // Default CPU thread count when the provider doesn't set one: HALF the logical
  // cores (matching wllama's own default). Using ALL cores regresses on hybrid
  // P/E-core CPUs and big.LITTLE phones — the slow cores create contention and
  // memory bandwidth becomes the bottleneck. Half is the sweet spot: it picks
  // the faster cores on most architectures. This only has effect where the page
  // is cross-origin isolated (COOP/COEP → SharedArrayBuffer); otherwise wllama
  // runs single-threaded regardless and the value is ignored.
  function defaultThreads() {
    return (typeof navigator !== 'undefined' && navigator.hardwareConcurrency)
      ? Math.max(1, Math.floor(navigator.hardwareConcurrency / 2))
      : 2;
  }

  async function getInstance(modelUrl, onProgress, opts) {
    if (!modelUrl) throw new Error('wllama: modelUrl is required');
    const nCtx = (opts && opts.nCtx) || DEFAULT_N_CTX;
    // GPU offload layer count. Default 0 (pure CPU): we MUST pass this
    // explicitly because wllama otherwise defaults to 99999 (offload every
    // layer to WebGPU), which crashes the worker. Opt in per provider via the
    // "GPU layers" field. Load-time param ⇒ part of the instance key.
    const nGpuLayers = (opts && opts.nGpuLayers != null) ? (opts.nGpuLayers | 0) : 0;
    // Flash attention: default TRUE for CPU-only mode (n_gpu_layers=0). The
    // "unreachable" crash is in the WebGPU kernel path, never entered on CPU.
    // On CPU, flash_attn gives ~20-50% faster prefill + ~30% less KV memory
    // with zero quality loss. When GPU offload is active, default FALSE (crash).
    const flashAttn = (opts && opts.flashAttn != null)
      ? (opts.flashAttn === true)
      : (nGpuLayers === 0);
    // CPU threads (load-time). Default = half the logical cores (matching
    // wllama's own default); effective only when cross-origin isolated.
    const nThreads = (opts && opts.nThreads != null) ? (opts.nThreads | 0) : defaultThreads();
    // Prefill batch size (load-time). 0 = leave wllama's default; a bigger value
    // speeds prompt processing at some memory cost. Opt-in per provider.
    const nBatch = (opts && opts.nBatch != null) ? (opts.nBatch | 0) : 0;
    // KV cache quantization (load-time). q8_0 halves KV cache memory with
    // negligible quality loss, enabling larger contexts in the same memory.
    // Default 'q8_0' for CPU-only; f16 when GPU offloading (q8 on GPU is slower).
    // Override per provider via cacheTypeK / cacheTypeV.
    const cacheK = (opts && opts.cacheTypeK) || (nGpuLayers === 0 ? 'q8_0' : 'f16');
    const cacheV = (opts && opts.cacheTypeV) || (nGpuLayers === 0 ? 'q8_0' : 'f16');
    const key = modelUrl + '|' + nCtx + '|fa:' + flashAttn + '|gpu:' + nGpuLayers + '|th:' + nThreads + '|nb:' + nBatch + '|ck:' + cacheK + '|cv:' + cacheV;
    if (_instance && _instanceUrl === modelUrl && _instanceCtx === nCtx && _instanceFlashAttn === flashAttn && _instanceGpuLayers === nGpuLayers && _instanceThreads === nThreads && _instanceBatch === nBatch && _instanceCacheK === cacheK && _instanceCacheV === cacheV) return _instance;
    if (_loadingKey === key) {
      while (_loadingKey === key) await new Promise(r => setTimeout(r, 50));
      if (_instance && _instanceUrl === modelUrl && _instanceCtx === nCtx && _instanceFlashAttn === flashAttn && _instanceGpuLayers === nGpuLayers && _instanceThreads === nThreads && _instanceBatch === nBatch && _instanceCacheK === cacheK && _instanceCacheV === cacheV) return _instance;
    }
    _loadingKey = key;
    try {
      if (_instance) {
        try { await _instance.exit(); } catch (_) {}
        _instance = null;
        _instanceUrl = null;
        _instanceCtx = 0;
        _instanceFlashAttn = false;
        _instanceGpuLayers = 0;
        _instanceThreads = 0;
        _instanceBatch = 0;
        _instanceCacheK = null;
        _instanceCacheV = null;
        _kvDirty = false;
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
      // code is inlined into the SDK bundle so no separate worker URL is
      // needed. We pass n_gpu_layers explicitly (default 0 = CPU) to override
      // wllama's offload-everything default — see the WLLAMA_VERSION note.
      const inst = new Wllama({ default: WASM_URL });
      // n_threads is effective only when cross-origin isolated (COOP/COEP); it's
      // harmless otherwise (wllama stays single-threaded). n_batch only sent when
      // overridden (>0), else wllama keeps its own default.
      // flash_attn: true on CPU (faster prefill, less memory, exact reformulation).
      // cache_type_k/v: q8_0 on CPU (halves KV memory, negligible quality loss).
      const loadOpts = {
        n_ctx: nCtx,
        flash_attn: flashAttn,
        n_gpu_layers: nGpuLayers,
        n_threads: nThreads,
        cache_type_k: cacheK,
        cache_type_v: cacheV,
      };
      if (nBatch > 0) loadOpts.n_batch = nBatch;
      dbg('loadModel opts:', JSON.stringify(loadOpts));
      await inst.loadModel([ggufBlob], loadOpts);
      _instance = inst;
      _instanceUrl = modelUrl;
      _instanceCtx = nCtx;
      _instanceFlashAttn = flashAttn;
      _instanceGpuLayers = nGpuLayers;
      _instanceThreads = nThreads;
      _instanceBatch = nBatch;
      _instanceCacheK = cacheK;
      _instanceCacheV = cacheV;
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
   *   temperature — sampling temperature (0 = greedy)
   *   topP        — nucleus sampling threshold
   */
  async function streamRound({ modelUrl, messages, tools, signal, onDelta, onProgress, nCtx, flashAttn, nGpuLayers, nThreads, nBatch, cacheTypeK, cacheTypeV, maxTokens, temperature, topP, frequencyPenalty, presencePenalty, reasoning }) {
    const wllama = await getInstance(modelUrl, onProgress, { nCtx, flashAttn, nGpuLayers, nThreads, nBatch, cacheTypeK, cacheTypeV });
    if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');

    // RWKV is a recurrent reasoning model, not a transformer chat model. Route it
    // to the raw-completion path (manual prompt + `<think` prefill, reasoning split
    // out as reasoning_content, no tools). `tools` is intentionally ignored here.
    if (isRwkvUrl(modelUrl)) {
      return streamRoundRwkv({ wllama, messages, signal, onDelta, reasoning, maxTokens, frequencyPenalty, presencePenalty });
    }

    let aborted = false;
    const onAbort = () => { aborted = true; };
    if (signal) {
      if (signal.aborted) onAbort();
      else signal.addEventListener('abort', onAbort, { once: true });
    }

    let content = '';
    let reasoningText = '';
    const toolCalls = [];
    let finishReason = null;
    const t0 = (typeof performance !== 'undefined' ? performance.now() : Date.now());

    const adaptedMessages = adaptMessages(messages);
    // Reuse the KV cache across rounds (cache_prompt:true). wllama embeds
    // llama.cpp's single-slot server core, so on every call it finds the longest
    // common TOKEN prefix between this prompt and the slot's cached tokens, removes
    // the divergent suffix from the KV (the `kv cache rm [n, end)` line in
    // llama-server logs), then prefills only from the divergence point. Edits,
    // rewinds, branch/conversation switches — and the <think> stripping in
    // runConversation, which makes a replayed assistant turn diverge from the raw
    // tokens still cached — are therefore reconciled INSIDE the engine. No app-side
    // prefix tracking is needed; the earlier 200-char message digest that tried it
    // was itself the prod-breakage cause (collisions mislabeled divergent prompts
    // as extensions, and a coarse digest can't drive token-level truncation anyway).
    // The only state the engine can't recover is a partial KV left by a worker
    // error/timeout, so we force one clean prefill after those (see _kvDirty).
    const useCache = !_kvDirty;
    _kvDirty = false;

    const request = {
      modelUrl,
      messages: adaptedMessages,
      max_tokens: maxTokens || 2048,
      tools: tools && tools.length ? tools : undefined,
    };
    // Optional sampling / penalty params (top-level; llama.cpp + OAI names). Only
    // sent when set, so wllama keeps its own defaults otherwise.
    if (temperature != null) request.temperature = temperature;
    if (topP != null) request.top_p = topP;
    if (frequencyPenalty != null) request.frequency_penalty = frequencyPenalty;
    if (presencePenalty != null) request.presence_penalty = presencePenalty;
    dbg(`→ round: ${request.messages.length} msgs, ${tools ? tools.length : 0} tools, last role: ${request.messages.length ? request.messages[request.messages.length - 1].role : '(none)'}`);

    // Watchdog: if the wllama worker crashes (wasm unreachable) the async
    // iterator simply stalls — no more chunks, no rejection.  We arm a
    // timer that fires if no chunk arrives before STREAM_TIMEOUT_MS.  A
    // real inference run will keep resetting the timer on every chunk.
    let watchdog = null;
    let watchdogFired = false;
    const armWatchdog = () => {
      if (watchdog) clearTimeout(watchdog);
      watchdog = setTimeout(() => {
        watchdogFired = true;
        aborted = true;
      }, STREAM_TIMEOUT_MS);
    };
    const disarmWatchdog = () => { if (watchdog) { clearTimeout(watchdog); watchdog = null; } };

    dbg(`→ round cache: ${useCache ? 'HIT (reusing KV cache)' : 'MISS (full prefill)'}`);

    try {
      const stream = await wllama.createChatCompletion({
        messages: request.messages,
        max_tokens: request.max_tokens,
        ...(request.temperature != null ? { temperature: request.temperature } : {}),
        ...(request.top_p != null ? { top_p: request.top_p } : {}),
        ...(request.frequency_penalty != null ? { frequency_penalty: request.frequency_penalty } : {}),
        ...(request.presence_penalty != null ? { presence_penalty: request.presence_penalty } : {}),
        stream: true,
        // Reuse the KV cache; the engine truncates to the common prefix on any
        // divergence (see the useCache note above). Held false for one round only
        // after a worker error/timeout, via _kvDirty.
        cache_prompt: useCache,
        // tool_choice:'auto' is REQUIRED for wllama to render the tools into the chat
        // template — passing `tools` alone leaves them out of the prompt, so the model
        // reports having no tools. (Matches wllama's own tools example.)
        ...(request.tools ? { tools: request.tools, tool_choice: 'auto' } : {}),
      });

      armWatchdog();
      for await (const chunk of stream) {
        if (aborted) break;
        armWatchdog();
        const choice = chunk && chunk.choices && chunk.choices[0];
        const delta = choice && choice.delta;
        // finish_reason lands on the LAST chunk for that choice — capture
        // it so we can surface length-clipping vs natural stop in logs.
        if (choice && choice.finish_reason) finishReason = choice.finish_reason;
        if (!delta) continue;
        if (delta.content) content += delta.content;
        // Reasoning models (e.g. Qwen 3.5 / arch "qwen35") emit their <think>
        // stream as reasoning_content, which llama.cpp keeps OUT of content.
        // Capture it and forward it below so the page shows it live in the
        // "Thinking…" box (conversations.js applyDelta reads reasoning_content).
        // Without this, an all-thinking turn looks like an empty reply.
        if (delta.reasoning_content) reasoningText += delta.reasoning_content;
        if (delta.tool_calls) {
          // Accumulate by index — same approach as the SW path.  Some
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
        if (delta.content || delta.tool_calls || delta.reasoning_content) {
          try { onDelta && onDelta(delta); } catch (_) {}
        }
      }
      disarmWatchdog();
      // If the watchdog fired we broke out of the loop with no finish_reason.
      if (watchdogFired && !finishReason && !content && !toolCalls.length) {
        throw new Error('Model timed out — the inference worker appears to have crashed. Try reloading the page or selecting a different model.');
      }
    } catch (err) {
      // A worker error/timeout can leave a partial sequence in the KV cache;
      // force one clean (cache_prompt:false) prefill on the next round.
      _kvDirty = true;
      throw err;
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
        response: { content, reasoning: reasoningText, tool_calls: keptToolCalls, finish_reason: finishReason, duration_ms: dtMs },
      };
    } catch (_) {}

    dbg(`← finish: ${finishReason || '(none)'} · content: ${content.length} chars · tool_calls: ${keptToolCalls.length} · ${dtMs}ms`);
    if (isDebug() && keptToolCalls.length) {
      for (const tc of keptToolCalls) dbg(`  tool: ${tc.function.name} args: ${tc.function.arguments}`);
    }

    return { content, tool_calls: keptToolCalls };
  }

  // ============================================================
  // RWKV raw-completion path (recurrent reasoning models)
  // ============================================================
  // RWKV-7 "G1" doesn't speak the OpenAI chat-completion format and doesn't emit
  // <think> on its own — its reasoning is triggered by PREFILLING the assistant
  // turn with `<think` (BlinkDL's official template). So we bypass
  // createChatCompletion and build the prompt by hand:
  //
  //   System: …\n\nUser: …\n\nAssistant: <think>
  //
  // then stream raw tokens via createCompletion. Everything the model writes
  // inside <think>…</think> is forwarded as reasoning_content (the page renders a
  // Thinking box and never replays it to the model); everything after </think> is
  // the answer (content). We stop at the next "\n\nUser:" because RWKV will
  // otherwise happily hallucinate the user's next turn.

  // Flatten the working history into RWKV's "Role: text" turn format (turns joined
  // by \n\n). tool messages are dropped — RWKV G1 isn't a tool-caller. promptPrefill
  // seeds the new assistant turn (e.g. ' <think>').
  function buildRwkvPrompt(messages, promptPrefill) {
    const turns = [];
    for (const m of (messages || [])) {
      if (!m || !m.role) continue;
      let c = m.content;
      if (Array.isArray(c)) c = c.filter(p => p && p.type === 'text').map(p => p.text || '').join('\n');
      c = (c == null ? '' : String(c)).trim();
      if (m.role === 'system') turns.push('System: ' + c);
      else if (m.role === 'user') turns.push('User: ' + c);
      else if (m.role === 'assistant') turns.push('Assistant: ' + c);
      // role 'tool' → skipped: RWKV has no tools.
    }
    return turns.join('\n\n') + '\n\nAssistant:' + promptPrefill;
  }

  async function streamRoundRwkv({ wllama, messages, signal, onDelta, reasoning, maxTokens, frequencyPenalty, presencePenalty }) {
    // Reasoning toggle → assistant prefill:
    //   no_think → seed a closed, empty block ("fake thinking, fast" per BlinkDL)
    //   think / auto → seed an open `<think>` so the model reasons (G1's default).
    // We seed the full `<think>` (with '>') rather than BlinkDL's shorthand `<think`
    // so the splitter never depends on the model emitting the closing '>' itself.
    const mode = (reasoning === 'no_think') ? 'no_think' : 'think';
    const promptPrefill = mode === 'no_think' ? ' <think>\n</think>' : ' <think>';
    const parsePrefill = promptPrefill.slice(1); // same text minus the leading space, for the splitter
    const prompt = buildRwkvPrompt(messages, promptPrefill);

    let aborted = false;
    const onAbort = () => { aborted = true; };
    if (signal) {
      if (signal.aborted) onAbort();
      else signal.addEventListener('abort', onAbort, { once: true });
    }

    // Incremental <think>…</think> splitter. We recompute over the full buffer each
    // token (reasoning output is tiny relative to inference cost) and emit only the
    // newly-grown tail, holding back the last few chars while still inside the block
    // so a partial "</think>" never leaks into the Thinking box.
    let gen = '';
    let emittedReasoning = '';
    let emittedContent = '';
    const CLOSE = '</think>';
    const RESERVE = CLOSE.length;
    const split = (isFinal) => {
      const combined = parsePrefill + gen;
      const openIdx = combined.indexOf('<think');
      const gtIdx = openIdx >= 0 ? combined.indexOf('>', openIdx) : -1;
      const rStart = gtIdx >= 0 ? gtIdx + 1 : -1;            // first char of reasoning
      const closeIdx = rStart >= 0 ? combined.indexOf(CLOSE, rStart) : -1;
      // Reasoning (inside the think block). The leading-whitespace trim is stable
      // as the string grows, so emittedReasoning stays a prefix of disp.
      if (rStart >= 0) {
        let raw = closeIdx >= 0 ? combined.slice(rStart, closeIdx) : combined.slice(rStart);
        if (closeIdx < 0 && !isFinal) raw = raw.slice(0, Math.max(0, raw.length - RESERVE));
        const disp = raw.replace(/^\s+/, '');
        if (disp.length > emittedReasoning.length && disp.startsWith(emittedReasoning)) {
          const tail = disp.slice(emittedReasoning.length);
          emittedReasoning = disp;
          if (tail) { try { onDelta && onDelta({ reasoning_content: tail }); } catch (_) {} }
        }
      }
      // Answer (after </think>). The first content delta collapses the Thinking box.
      if (closeIdx >= 0) {
        const disp = combined.slice(closeIdx + CLOSE.length).replace(/^\s+/, '');
        if (disp.length > emittedContent.length && disp.startsWith(emittedContent)) {
          const tail = disp.slice(emittedContent.length);
          emittedContent = disp;
          if (tail) { try { onDelta && onDelta({ content: tail }); } catch (_) {} }
        }
      }
    };

    // Watchdog: a crashed worker stalls the iterator without rejecting (same trap
    // the chat path guards against).
    let watchdog = null, watchdogFired = false;
    const armWatchdog = () => {
      if (watchdog) clearTimeout(watchdog);
      watchdog = setTimeout(() => { watchdogFired = true; aborted = true; }, STREAM_TIMEOUT_MS);
    };
    const disarmWatchdog = () => { if (watchdog) { clearTimeout(watchdog); watchdog = null; } };

    let finishReason = null;
    let lastTimings = null;
    let genTokens = 0;
    const maxOut = maxTokens || 2048;
    const t0 = (typeof performance !== 'undefined' ? performance.now() : Date.now());

    // BlinkDL's recommended G1 reasoning: presence/frequency penalty 0.5 to curb
    // RWKV repetition, unless the provider overrides. top_p AND temperature options
    // removed — RWKV now uses llama.cpp's defaults for those.
    // cache_prompt stays FALSE here — unlike the transformer chat path, which now
    // reuses the KV. RWKV is recurrent: its "cache" is one evolving state with no
    // per-token positions, so the engine can't reconcile a diverged prefix by
    // removing a suffix (the chat path's trick). Re-prefilling each round is the
    // safe choice. The flag isn't in the public RawCompletionParams type but is
    // read by the shared completion impl; harmless if ignored. Abort is handled by
    // the `aborted` flag + break (no abortSignal, to avoid throwing mid-stream).
    const params = {
      prompt,
      stream: true,
      cache_prompt: false,
      max_tokens: maxOut,
      presence_penalty: presencePenalty != null ? presencePenalty : 0.5,
      frequency_penalty: frequencyPenalty != null ? frequencyPenalty : 0.5,
      stop: ['\n\nUser:'],
    };

    dbg(`→ rwkv round (${mode}): prompt ${prompt.length} chars`);

    try {
      const stream = await wllama.createCompletion(params);
      armWatchdog();
      for await (const chunk of stream) {
        if (aborted) break;
        armWatchdog();
        const choice = chunk && chunk.choices && chunk.choices[0];
        if (chunk && chunk.timings) lastTimings = chunk.timings;
        if (!choice) continue;
        if (choice.finish_reason) finishReason = choice.finish_reason;
        if (choice.text) { gen += choice.text; genTokens++; split(false); }
        // Hard output-token cap. wllama's raw createCompletion doesn't reliably
        // honor max_tokens on this path, so enforce the configured limit here —
        // otherwise a reasoning model like G1 generates until EOS / context-full,
        // ignoring the "max output tokens" setting. Prefer wllama's own
        // predicted-token counter; fall back to counting streamed chunks.
        if (((lastTimings && lastTimings.predicted_n) || genTokens) >= maxOut) {
          finishReason = finishReason || 'length';
          break;
        }
      }
      disarmWatchdog();
      split(true); // flush the held-back reserve + any trailing tail
      if (watchdogFired && !finishReason && !emittedContent && !emittedReasoning) {
        throw new Error('Model timed out — the inference worker appears to have crashed. Try reloading the page or selecting a different model.');
      }
    } finally {
      if (signal) signal.removeEventListener('abort', onAbort);
    }

    if (aborted) throw new DOMException('aborted', 'AbortError');

    const dtMs = Math.round((typeof performance !== 'undefined' ? performance.now() : Date.now()) - t0);
    try {
      self.__wllamaLastRound = {
        ts: new Date().toISOString(),
        request: { rwkv: true, mode, prompt, max_tokens: params.max_tokens },
        response: { content: emittedContent, reasoning: emittedReasoning, finish_reason: finishReason, duration_ms: dtMs, timings: lastTimings },
      };
    } catch (_) {}
    dbg(`← rwkv finish: ${finishReason || '(none)'} · reasoning ${emittedReasoning.length} · content ${emittedContent.length} · ${dtMs}ms${lastTimings ? ' · ' + (lastTimings.predicted_per_second || 0).toFixed(1) + ' tok/s' : ''}`);

    // No tool_calls — RWKV G1 isn't a tool-caller; the agent loop ends this turn.
    return { content: emittedContent, tool_calls: [] };
  }

  // ============================================================
  // Conversation driver (page-side agent loop)
  // ============================================================
  // Emits the SAME agent-event protocol the service worker's runAgent
  // emits, so conversations.js can swap the event SOURCE (SW fetch ↔ this
  // page-side loop) at one seam and reuse its renderer, message
  // persistence, token accounting, abort handling, and generation:complete
  // lifecycle unchanged. Runs an agentic tool loop — tool calls execute via the
  // SW's /sandpie-tool endpoint, which reuses the exact tool implementations.
  //
  // onEvent receives objects shaped exactly like conversations.js's
  // dispatchAgentEvent cases:
  //   { type:'round_start' } { type:'delta', delta } { type:'round_end', content }
  //   { type:'message_added', message } { type:'info', message } (null clears it)
  //   { type:'error', message } { type:'agent_done' }
  async function runConversation({ provider, messages, systemPrompt, tools, convId, signal }, onEvent) {
    const emit = (ev) => { try { onEvent && onEvent(ev); } catch (_) {} };
    // Single active local backend: free the OTHER local LLMs' GPU/WASM contexts
    // before we run, so two WebGPU runtimes never share the (weak) GPU and
    // device-loss each other. (A backend never unloads itself.)
    try { await window.SandpieTransformersJS?.unload?.(); } catch (_) {}
    try { await window.SandpieLiteRTLM?.unload?.(); } catch (_) {}
    try { await window.SandpieQwen35?.unload?.(); } catch (_) {}
    const modelUrl = provider && (provider.endpoint || '').trim();
    if (!modelUrl) {
      emit({ type: 'error', message: 'wllama: this provider has no model URL — set the GGUF URL in Settings.' });
      emit({ type: 'agent_done' });
      return;
    }
    const isRwkv = isRwkvUrl(modelUrl);

    // systemPrompt arrives as the SW's system *message object* { role, content }
    // (what buildAgentConfig produces), not a bare string — pull its text out.
    const sysContent = systemPrompt
      ? (typeof systemPrompt === 'string' ? systemPrompt : (systemPrompt.content != null ? String(systemPrompt.content) : ''))
      : '';
    const toolList = Array.isArray(tools) ? tools : [];

    // Working history, mutated across tool rounds. Flatten content to a string
    // (wllama rejects an object content) but KEEP tool_calls / tool results so
    // the agentic loop can carry them.
    const norm = (m) => {
      let c = m.content;
      if (Array.isArray(c)) c = c.filter(p => p && p.type === 'text').map(p => p.text || '').join('\n');
      else if (c != null && typeof c !== 'string') c = String(c);
      const out = { role: m.role, content: c == null ? '' : c };
      if (m.tool_calls) out.tool_calls = m.tool_calls;
      if (m.tool_call_id) out.tool_call_id = m.tool_call_id;
      return out;
    };
    const work = [];
    if (sysContent) work.push({ role: 'system', content: sysContent });
    for (const m of (messages || [])) { if (m && m.role) work.push(norm(m)); }

    // Reasoning ("thinking") soft switch for Qwen3-style models: append /think or
    // /no_think to the latest user turn — in our WORKING copy only, so the shown/
    // persisted message is untouched. 'auto' leaves the model's own default.
    const think = provider.reasoning || 'auto';
    // RWKV gets its reasoning from the <think> prefill in streamRoundRwkv, so the
    // Qwen3 /think soft-switch (which RWKV wouldn't understand) is skipped for it.
    if (!isRwkv && (think === 'think' || think === 'no_think')) {
      for (let i = work.length - 1; i >= 0; i--) {
        if (work[i].role === 'user') {
          work[i] = { ...work[i], content: ((work[i].content || '') + ' ' + (think === 'think' ? '/think' : '/no_think')).trim() };
          break;
        }
      }
    }

    // Loading indicator (round 0 only — the model loads on the first streamRound).
    // Downloaded + WASM-compiled before any token streams; the compile step has no
    // progress callback, so show a status line, update it with download bytes/%,
    // switch to "initializing", and clear it on the first token.
    const fmtMB = (b) => (b >= 10485760 ? (b / 1048576).toFixed(0) : (b / 1048576).toFixed(1)) + ' MB';
    let firstToken = false, lastMsg = '', lastPct = -1, lastLoaded = 0;
    const status = (msg) => { if (msg === lastMsg) return; lastMsg = msg; emit({ type: 'info', message: msg }); };
    // Only announce loading when the model isn't already resident — getInstance
    // returns the cached instance instantly on later messages, so nothing should
    // flash then. Keys must match getInstance's (url + n_ctx + flash_attn + gpu +
    // threads + batch + cache types).
    const _nCtxWant = (provider.contextWindow | 0) || DEFAULT_N_CTX;
    const _glWant = provider.nGpuLayers != null ? (provider.nGpuLayers | 0) : 0;
    const _faWant = provider.flashAttn != null ? (provider.flashAttn === true) : (_glWant === 0);
    const _thrWant = provider.nThreads != null ? (provider.nThreads | 0) : defaultThreads();
    const _nbWant = provider.nBatch != null ? (provider.nBatch | 0) : 0;
    const _ckWant = provider.cacheTypeK || (_glWant === 0 ? 'q8_0' : 'f16');
    const _cvWant = provider.cacheTypeV || (_glWant === 0 ? 'q8_0' : 'f16');
    const _alreadyLoaded = _instance && _instanceUrl === modelUrl && _instanceCtx === _nCtxWant && _instanceFlashAttn === _faWant && _instanceGpuLayers === _glWant && _instanceThreads === _thrWant && _instanceBatch === _nbWant && _instanceCacheK === _ckWant && _instanceCacheV === _cvWant;
    if (!_alreadyLoaded) status('Loading local model… first run downloads it (cached after) — this can take a while.');
    const onProgress = (p) => {
      if (!p || firstToken) return;
      if (p.total && p.progress >= 0.999) {
        status('Initializing model… (compiling into memory)');
      } else if (p.total) {
        const pct = Math.round(p.progress * 100);
        if (pct === lastPct) return;
        lastPct = pct;
        status(`${p.fromCache ? 'Loading' : 'Downloading'} model… ${fmtMB(p.loaded)} / ${fmtMB(p.total)} (${pct}%)`);
      } else if (p.loaded - lastLoaded >= 4194304) {
        lastLoaded = p.loaded;
        status(`${p.fromCache ? 'Loading' : 'Downloading'} model… ${fmtMB(p.loaded)}`);
      }
    };

    const sample = {
      nCtx: (provider.contextWindow | 0) || DEFAULT_N_CTX,
      flashAttn: provider.flashAttn != null ? (provider.flashAttn === true) : undefined,
      nGpuLayers: provider.nGpuLayers != null ? (provider.nGpuLayers | 0) : undefined,
      nThreads: provider.nThreads != null ? (provider.nThreads | 0) : undefined,
      nBatch: provider.nBatch != null ? (provider.nBatch | 0) : undefined,
      cacheTypeK: provider.cacheTypeK || undefined,
      cacheTypeV: provider.cacheTypeV || undefined,
      maxTokens: provider.maxTokens || undefined,
      temperature: provider.temperature != null ? provider.temperature : undefined,
      topP: provider.topP != null ? provider.topP : undefined,
      frequencyPenalty: provider.frequencyPenalty != null ? provider.frequencyPenalty : undefined,
      presencePenalty: provider.presencePenalty != null ? provider.presencePenalty : undefined,
    };

    // Agentic loop, mirroring the SW's runAgent: stream a round, append the
    // assistant turn, run any tool_calls via the SW's /sandpie-tool endpoint
    // (which reuses the exact tool implementations), append results, repeat.
    // Capped so a confused local model can't loop forever.
    const MAX_ROUNDS = 8;
    for (let round = 0; round < MAX_ROUNDS; round++) {
      if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');
      emit({ type: 'round_start' });
      let result;
      try {
        result = await streamRound({
          modelUrl, messages: work, tools: isRwkv ? [] : toolList, signal, reasoning: think,
          onProgress: round === 0 ? onProgress : undefined,
          ...sample,
          onDelta: (delta) => {
            if (!firstToken) { firstToken = true; emit({ type: 'info', message: null }); }
            emit({ type: 'delta', delta });
          },
        });
      } catch (e) {
        if (e && e.name === 'AbortError') throw e;     // let conversations.js show "Stopped."
        emit({ type: 'info', message: null });
        emit({ type: 'error', message: 'wllama: ' + ((e && e.message) || e) });
        emit({ type: 'agent_done' });
        return;
      }
      emit({ type: 'info', message: null });
      // Strip any <think>…</think> reasoning from the stored/displayed content so
      // it's neither replayed to the model nor left as raw tags. (If wllama
      // surfaced reasoning as reasoning_content instead, there's nothing here.)
      const cleanContent = (result.content || '').replace(/<think>[\s\S]*?<\/think>\s*/gi, '').replace(/^\s+/, '');
      emit({ type: 'round_end', content: cleanContent });

      const asst = { role: 'assistant', content: cleanContent };
      if (result.tool_calls && result.tool_calls.length) asst.tool_calls = result.tool_calls;
      work.push(asst);
      emit({ type: 'message_added', message: asst });

      if (!result.tool_calls || !result.tool_calls.length) break;   // no tools → turn complete

      for (const tc of result.tool_calls) {
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

  // Free this backend's wllama instance + its WebGPU/WASM context. Called by the
  // OTHER local backends (and applyActiveProvider) so only one local LLM is ever
  // resident — two WebGPU runtimes on one weak GPU device-loss each other.
  // Idempotent; the model lazily reloads via getInstance on next use.
  async function unload() {
    if (!_instance) return;
    try { await _instance.exit(); } catch (_) {}
    _instance = null;
    _instanceUrl = null;
    _instanceCtx = 0;
    _instanceFlashAttn = false;
    _instanceGpuLayers = 0;
    _instanceThreads = 0;
    _instanceBatch = 0;
    _instanceCacheK = null;
    _instanceCacheV = null;
    _kvDirty = false;
  }

  return {
    DEFAULT_MODELS,
    DEFAULT_N_CTX,
    getInstance,
    unload,
    streamRound,
    runConversation,
  };
})();

if (typeof window !== 'undefined') window.SandpieWllama = SandpieWllama;
