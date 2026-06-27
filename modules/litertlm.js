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

  // Pinned on purpose. Bumped 0.12 → 0.13.1 (latest, 2026-06-03): 0.13.x brings the
  // current Gemma 4 WASM runtime + Multi-token Prediction (~2× faster decode) and bug
  // fixes. The web-crash threads (mediapipe#6270) point at stale/old .wasm as a cause,
  // so the current build is the lever for getting thinking to run without aborting.
  // API verified compatible with this module (EngineSettings.model ReadableStream,
  // sendMessageStreaming→ReadableStream<Message> with channels, ConversationConfig/
  // SessionConfig fields). Bump deliberately — a silent "latest" is what broke wllama.
  const PACKAGE_VERSION = '0.13.1';
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
    // NOTE: community Qwen 3.5 / VibeThinker .litertlm builds were added here and
    // then REMOVED (2026-06-18). The LiteRT-LM *web* SDK (@litert-lm/core 0.13.1,
    // the latest published) cannot load them — it aborts with
    //   "Streaming HF_Tokenizer_Zlib section is not supported yet".
    // Qwen-family models carry a HuggingFace/BPE tokenizer (stored zlib-compressed),
    // and the web runtime currently parses ONLY SentencePiece tokenizers (what Gemma
    // ships). A "-web" filename doesn't change the tokenizer type, and no SDK version
    // fixes this yet. For Qwen 3.5 in-browser, use the wllama backend instead (it runs
    // the dense GGUF builds). Re-add a LiteRT Qwen here ONLY once the web SDK gains
    // HF-tokenizer support. Users can still paste such a URL via the "Custom" option.
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

  // ============================================================
  // WebGPU device — fp32-forced (no shader-f16).
  //
  // The LiteRT-LM SDK's createDefaultWebGpuDevice() requests 'shader-f16' if the
  // adapter supports it. When the feature is present, the SDK's WGSL shaders use
  // f16 types for matmuls, reductions, and softmax — which is fine for most models
  // but CATASTROPHIC for Gemma. Gemma's architecture (RMSNorm scale = 1.0, tight
  // softmax temperatures) loses meaningful precision in fp16: the logits drift
  // off-distribution, dense non-English tokens (Chinese, Tamil) leak through, and
  // with no repetition penalty the model locks into infinite loops. This is a
  // well-documented, architecture-level fp16 intolerance.
  //
  // On desktop GPUs the corruption is often mild enough to go unnoticed (larger
  // registers, better fp16 accumulation). On mobile GPUs — where fp16 is the norm
  // and accumulators are narrower — the corruption is severe and immediate.
  //
  // FIX: create the WebGPU device ourselves WITHOUT 'shader-f16'. Its absence
  // forces the SDK's shaders to use f32 everywhere, keeping Gemma's logits clean.
  // We set this as preinitializedWebGPUDevice on the WASM module BEFORE
  // Engine.create(), so the SDK's internal setupDefaultWebGpuDevice() sees a
  // device is already set and skips its own (fp16-enabling) creation.
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
    // 'subgroups' is a thread-cooperation feature (not precision-related); keep it
    // if available for performance.
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

    // Sanity check: confirm shader-f16 is NOT enabled on the device. If the
    // browser granted it despite our not requesting it (shouldn't happen, but
    // defend against it), warn — the SDK may use fp16 shaders and corrupt Gemma.
    if (device.features.has('shader-f16')) {
      console.warn('[litertlm] WARNING: WebGPU device has shader-f16 despite not requesting it. '
        + 'The SDK may use fp16 shaders — Gemma output may be corrupted (non-English tokens, '
        + 'repetition loops) on this device. Consider using a wllama (CPU) model instead.');
    }

    dbg('WebGPU device created (fp32-forced, shader-f16 excluded). Features:', requiredFeatures);
    return device;
  }

  // ============================================================
  // Model cache (Cache Storage API — NOT OPFS, so Dropbox sync can't see it).
  // The LiteRT-LM Web SDK fetches the .litertlm URL itself with no persistent
  // cache, so a 2–3 GB model re-downloads on every load. We fetch it through the
  // Cache Storage API (same approach as wllama) and hand Engine.create the cached
  // byte stream — EngineSettings.model accepts a ReadableStream<Uint8Array>.
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
      // Stash a clone in Cache Storage in the background (clone BEFORE the body is
      // read). Best-effort: a quota/write failure just means a re-download next time.
      if (cache) cache.put(url, net.clone()).catch(e => console.warn('[litertlm] cache.put failed:', e && e.message));
      res = net;
    }
    if (!res.body) return null;   // fall back to the URL (handled by caller)

    // Wrap the body so we can report byte progress for the (multi-GB) load.
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
    // Tear down a stale engine before loading a different model.
    if (_engine) { try { await _engine.delete(); } catch (_) {} _engine = null; _engineModel = null; _engineCtx = 0; }
    // The Web SDK exposes no download-progress callback — surface a single tick so
    // the UI can show a "loading" line before the (multi-GB, slow) first load.
    try { onProgress && onProgress({ status: 'loading' }); } catch (_) {}
    const { Engine } = await loadLib();
    // Engine.create() internally calls setupDefaultWebGpuDevice(), but we pre-set
    // our own fp32-forced device (below) so it skips its fp16-enabling creation.
    dbg('Engine.create', modelUrl, 'maxNumTokens', ctx);
    // Hand the SDK the CACHED byte stream (Cache Storage) instead of the URL, so the
    // multi-GB model is downloaded once and reused across loads. Falls back to the
    // URL if the body isn't streamable. EngineSettings.model accepts a ReadableStream.
    const modelSource = (await fetchModelStream(modelUrl, onProgress)) || modelUrl;

    // Pre-set an fp32-forced WebGPU device on the WASM module BEFORE Engine.create.
    // Engine.create() internally calls setupDefaultWebGpuDevice(), which checks
    // preinitializedWebGPUDevice — if already set, it skips its own device creation
    // (which would request shader-f16 and enable fp16 shaders). By pre-setting ours
    // (no shader-f16), we force the SDK's WGSL shaders to use f32 everywhere,
    // keeping Gemma's logits clean on mobile GPUs where fp16 corrupts them.
    const lib = await loadLib();
    let litertlm = null;
    try {
      // getOrLoadGlobalLiteRtLm() loads the WASM module (one-time) and returns the
      // singleton LiteRtLm instance whose .liteRtLmWasm holds the WASM bindings.
      litertlm = await lib.getOrLoadGlobalLiteRtLm();
    } catch (e) {
      throw new Error('LiteRT-LM: Failed to load WASM runtime: ' + ((e && e.message) || e));
    }
    if (litertlm && litertlm.liteRtLmWasm && !litertlm.liteRtLmWasm.preinitializedWebGPUDevice) {
      try {
        const device = await createFp32WebGpuDevice();
        litertlm.liteRtLmWasm.preinitializedWebGPUDevice = device;
        dbg('Pre-set fp32 WebGPU device on WASM module');
      } catch (e) {
        // If we can't create an fp32 device, surface the error clearly — running
        // with the SDK's default (fp16) device will corrupt Gemma on mobile.
        throw e;
      }
    }

    _engine = await lib.Engine.create({ model: modelSource, mainExecutorSettings: { maxNumTokens: ctx } });
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

    // Pattern 1: <tool_call>{"name":"...","arguments":{...}}</tool_call> — fences are
    // fuzzy: small models mix the HTML-style <tool_call>…</tool_call> with Gemma's native
    // <|tool_call>…<tool_call|>, so accept any open/close combo (incl. the hybrid).
    const rxToolCall = /<\|?tool_call>\s*([\s\S]*?)\s*(?:<\/tool_call>|<tool_call\|>)/g;
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
    let args = raw.arguments || raw.arguments_text || (raw.function && raw.function.arguments) || raw.params || raw.parameters || raw.args || {};
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
    // FIRST: treat the body as a JS-object body and JSON-parse it. This is the ONLY path
    // that handles array/object values — e.g. run_python's args: ["query","10"]. The
    // regex tiers below only do flat string/scalar values and silently DROP an array arg
    // (the model emits the call correctly, but the parsed arguments lose `args`, so
    // run_python runs with no query). Quote bare keys + convert Gemma's <|"|>…<|"|> string
    // token to a JSON string, then JSON.parse({…}). Falls back to the tiers on any failure.
    try {
      const j = body
        .replace(/<\|"\|>([\s\S]*?)<\|"\|>/g, (_, s) => JSON.stringify(s))
        .replace(/(^|[,{]\s*)([A-Za-z_][\w.]*)\s*:/g, '$1"$2":');
      const obj = JSON.parse('{' + j + '}');
      if (obj && typeof obj === 'object' && !Array.isArray(obj)) return obj;
    } catch (_) { /* not clean JSON — fall back to the tolerant regex tiers below */ }

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
      .replace(/<\|channel>thought[\s\S]*?<channel\|>/gi, '')  // Gemma 4 reasoning ("thought") channel
      .replace(/<\|channel>[a-z]*\r?\n?/gi, '')                // stray channel headers (e.g. final)
      .replace(/<channel\|>/g, '')                             // stray channel close
      .replace(/<\|?tool_call>[\s\S]*?(?:<tool_call\|>|<\/tool_call>)/g, '')   // tool call: native, HTML, or hybrid fences
      .replace(/```json\s*[\s\S]*?```/g, '')
      .replace(/<tool_call\|>|<\|tool_call>|<\|"\|>/g, '')   // stray Gemma tokens
      .replace(/<\|.*?>\n?/g, '')
      .trim()
      .replace(/^Assistant:\s*/i, '');
  }

  // Map sandpie message roles → LiteRT-LM roles. The Web SDK has no 'tool' role, so
  // tool outputs are fed back as a plainly-labelled user turn.
  function mapRole(role) { return role === 'assistant' ? 'assistant' : role === 'system' ? 'system' : 'user'; }
  // Render a message to text for the re-prefilled history. For an assistant turn that
  // made tool calls we MUST reconstruct them (cleanContent strips the native tokens from
  // .content, and we re-prefill a fresh conversation every round with no live KV cache),
  // or the model never sees its OWN calls and loops re-issuing them. CRUCIAL: reconstruct
  // in Gemma 4's NATIVE format — the exact shape the model emits unprompted (round 0 of
  // window.__litertlmPrompts). An earlier version used <tool_call>{json}</tool_call>; the
  // model IMITATED that instead of its native format, then drifted into a broken hybrid
  // (<tool_call>{json}<tool_call|>) no parser caught. Mirroring native keeps it on rails.
  // Preface-only — never re-parsed by us (splitToolCalls runs on model OUTPUT, not this).
  function gemmaToolCallText(tc) {
    const name = (tc.function && tc.function.name) || '';
    let args = {};
    try { args = JSON.parse((tc.function && tc.function.arguments) || '{}'); } catch (_) {}
    const body = Object.keys(args || {}).map(k => {
      const v = args[k];
      // Strings → Gemma's <|"|> delimiter (robust to embedded quotes/commas). Everything
      // else (number, boolean, array, object) → bare JSON, matching the shape the model
      // itself emits for arrays (e.g. args: ["q","10"]) so the reconstruction round-trips.
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
  // Sampling + conversation config. The LiteRT-LM Web SDK takes sampling on the
  // SessionConfig: no samplerParams anymore (temperature removed — LiteRT uses its
  // built-in sampling defaults); only the per-response cap as
  // sessionConfig.maxOutputTokens — NOT on sendMessage.
  // ============================================================
  function buildSamplerParams() {
    // No configurable sampler params → null lets LiteRT use its defaults.
    return null;
  }

  function buildConvConfig(provider, prefaceMsgs) {
    const cfg = {};
    if (prefaceMsgs && prefaceMsgs.length) cfg.preface = { messages: prefaceMsgs };
    const sampler = buildSamplerParams(provider);
    const maxOut = ((provider && provider.maxTokens) | 0) || 0;
    const sess = {};
    if (sampler) sess.samplerParams = sampler;
    if (maxOut > 0) sess.maxOutputTokens = maxOut;
    if (Object.keys(sess).length) cfg.sessionConfig = sess;
    // NOTE: filterChannelContentFromKvCache is intentionally NOT set. It asks the SDK to
    // excise the thought-channel span from the LIVE KV cache between sends — an in-place
    // GPU-cache mutation that hard-crashes the tab in the v0.12 web-preview SDK. We don't
    // need it: runConversation rebuilds a fresh conversation from thought-free history
    // each round (cleanContent already strips thoughts), so Gemma 4's "thoughts must not
    // precede the next turn" rule holds without ever editing a live cache.
    return Object.keys(cfg).length ? cfg : undefined;
  }

  // ============================================================
  // Gemma 4 streams its reasoning in a "thought" channel:
  //   <|channel>thought\n  …reasoning…  <channel|>  …final answer…
  // (Thinking is enabled by a <|think|> token at the start of the system prompt; when
  // off the thought channel is empty.) The Web SDK relays these channel tokens as
  // plain text, so we split the stream live: thought-channel text → onReasoning (the
  // live "Thinking…" box), everything else → onContent (the answer). Markers can
  // straddle streamed chunks, so we hold back a short tail until a marker is
  // unambiguous. If no markers ever appear, everything is content — i.e. it degrades
  // safely to the old raw passthrough.
  // ============================================================
  function makeThoughtSplitter(onReasoning, onContent) {
    const OPEN = '<|channel>thought', CLOSE = '<channel|>', HOLD = OPEN.length - 1;
    const stripStray = (s) => s.replace(/<\|channel>[a-z]*\r?\n?/gi, '').replace(/<channel\|>/g, '');
    let buf = '', mode = 'pre';
    const self = { answer: '', reasoning: '' };
    function out(text, reasoning) {
      const t = stripStray(text);
      if (!t) return;
      if (reasoning) { self.reasoning += t; try { onReasoning && onReasoning(t); } catch (_) {} }
      else { self.answer += t; try { onContent && onContent(t); } catch (_) {} }
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
    self.push = (t) => { if (t) { buf += t; run(false); } };
    self.flush = () => run(true);
    return self;
  }

  // ============================================================
  // Low-level: stream one send over an ALREADY-created Conversation. Accumulates the
  // text, relays each chunk to onText, honors abort (cancels the stream).
  // ============================================================
  async function streamInto(conv, input, signal, onText, onThought) {
    let full = '', thoughtAcc = '';
    const stream = conv.sendMessageStreaming(input || '');
    for await (const chunk of stream) {
      if (signal && signal.aborted) { try { conv.cancel(); } catch (_) {} throw new DOMException('aborted', 'AbortError'); }
      // Gemma 4 streams its reasoning in the STRUCTURED 'thought' channel (per the
      // LiteRT-LM Web API: chunk.channels.thought), NOT as inline text — so the
      // answer text never carries thought markers and we must read the channel
      // directly. Auto-detect cumulative-vs-incremental delivery: emit only the
      // newly-grown tail (if the new value extends what we have, send the suffix;
      // otherwise treat it as an incremental piece and append).
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
      // Capture the first few raw chunks so the SDK's exact shape is inspectable
      // from DevTools (window.__litertlmChunks) if channel/format ever drifts.
      try { if (!self.__litertlmChunks) self.__litertlmChunks = []; if (self.__litertlmChunks.length < 5) self.__litertlmChunks.push(chunk); } catch (_) {}
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
  // Pyodide in a dedicated PAGE-OWNED worker (EXPERIMENTAL, LiteRT-only).
  // ============================================================
  // run_python is routed here instead of the service worker. The SW hard-aborts on
  // Pyodide — a WASM abort terminates the SW thread (uncatchable; sandpie.js:37) and
  // OPFS sync access handles are fragile there — so the page's awaited tool fetch
  // never resolves and the UI freezes. A dedicated worker is isolated, has reliable
  // sync access handles, and the timeout below turns a hung/crashed worker into a
  // recoverable error instead of a freeze. See modules/pyodide-worker.js.
  const PY_TIMEOUT_MS = 5 * 60 * 1000;
  let _toolReqSeq = 0;

  // Route any tool call through the shared sandpie-worker.js Web Worker.
  // Handles both run_python and all other OPFS/file tools uniformly.
  function toolViaWorker(name, args, convId, signal) {
    return new Promise((resolve, reject) => {
      const worker = window._sandpieWorker;
      if (!worker) { resolve({ result: 'Error: sandpie-worker not ready — reload the page.' }); return; }
      const id = 'lt-' + (++_toolReqSeq);
      let settled = false;
      const finish = (fn, v) => { if (settled) return; settled = true; cleanup(); fn(v); };
      const onMsg = (e) => {
        const m = e.data || {};
        if (m.id !== id || m.type !== 'tool_result') return;
        finish(resolve, { result: m.result || '', artifacts: m.artifacts || null });
      };
      const onErr = () => finish(resolve, { result: 'Error: sandpie-worker crashed — retry (worker restarts automatically).' });
      const onAbort = () => finish(reject, new DOMException('aborted', 'AbortError'));
      const timer = setTimeout(() => {
        finish(resolve, { result: 'Error: tool timed out after ' + (PY_TIMEOUT_MS / 1000) + 's — the worker may be stuck.' });
      }, PY_TIMEOUT_MS);
      function cleanup() { clearTimeout(timer); worker.removeEventListener('message', onMsg); worker.removeEventListener('error', onErr); if (signal) signal.removeEventListener('abort', onAbort); }
      worker.addEventListener('message', onMsg);
      worker.addEventListener('error', onErr);
      if (signal) { if (signal.aborted) { onAbort(); return; } signal.addEventListener('abort', onAbort, { once: true }); }
      worker.postMessage({ type: 'tool', id, name, args, conversation_file_name: convId, localterm: { token: localStorage.getItem('sandpie:localterm:token') || '', port: 8771 } });
    });
  }

  // ============================================================
  // Agentic conversation loop — emits the SAME event protocol conversations.js
  // expects (identical to wllama / transformersjs); tool calls run via /sandpie-tool.
  //
  // Creates a FRESH Conversation every round, re-prefilling the full history each time —
  // we deliberately do NOT reuse one Conversation across rounds. The old reuse approach
  // sent a SECOND time into a live KV cache after the first tool call; that path is
  // fragile in the v0.12 web-preview SDK (and with thinking it forces an in-place
  // filterChannelContentFromKvCache excision of the thought span — an uncatchable
  // WASM/WebGPU abort that takes the tab down). Re-prefilling clean history each round
  // (wllama/transformersjs and the MediaPipe LlmInference chat samples do the same) never
  // edits a live cache. cleanContent already strips prior thoughts from stored content,
  // so Gemma 4's "thoughts must not precede the next turn" rule holds with no KV surgery
  // and no need for filterChannelContentFromKvCache.
  // ============================================================
  // While local inference runs, add body.sp-decoding so the shared CSS rule suppresses
  // GPU-compositor work (backdrop-filter:blur recompute per streamed token, infinite CSS
  // animations) that otherwise starves the WebGPU decode loop for the shared GPU — the
  // same focused-tab slowdown fixed for the Qwen3 backend (webgpu-host.js). LiteRT runs
  // on the main thread, so it can toggle the class directly. Ref-counted + try/finally so
  // it always clears (runConversation can exit via return / normal end / thrown abort).
  let _decoding = 0;
  function _setDecoding(on) {
    try {
      const b = (typeof document !== 'undefined') && document.body; if (!b) return;
      if (on) { if (_decoding++ === 0) b.classList.add('sp-decoding'); }
      else { _decoding = Math.max(0, _decoding - 1); if (_decoding === 0) b.classList.remove('sp-decoding'); }
    } catch (_) {}
  }
  async function runConversation({ provider, messages, systemPrompt, tools, convId, signal }, emit) {
    _setDecoding(true);
    try {
    // Single active local backend: free the OTHER local LLMs' GPU/WASM contexts
    // first, so only one local runtime holds a WebGPU device at a time.
    try { await window.SandpieWllama?.unload?.(); } catch (_) {}
    try { await window.SandpieTransformersJS?.unload?.(); } catch (_) {}
    // Deep-free the Qwen3 WebGPU worker (buffers + device) and WAIT, so switching
    // Qwen3 → Gemma never leaves two backends holding GPU. (Qwen35 is the old removed
    // fork — keep the call as a harmless no-op in case an old build lingers.)
    try { await window.SandpieQwen3?.unload?.(); } catch (_) {}
    try { await window.SandpieQwen35?.unload?.(); } catch (_) {}
    const MAX_ROUNDS = 8;
    const toolList = (tools || []).filter(t => t && t.type === 'function');
    const nCtx = (provider.contextWindow | 0) || DEFAULT_N_CTX;

    // System text + tool descriptions (Gemma emits its native FC format from these).
    let sysText = (systemPrompt && typeof systemPrompt === 'object') ? (systemPrompt.content || '') : (systemPrompt || '');
    const preamble = buildToolPreamble(toolList);
    if (preamble) sysText = sysText ? (sysText + '\n\n' + preamble) : preamble;

    // Gemma 4 reasoning: a <|think|> token at the START of the system prompt turns on
    // step-by-step thinking. DISABLED BY DEFAULT: enabling it crashes LiteRT-LM's
    // WebGPU/WASM runtime mid-generation — a known, still-OPEN upstream bug ("memory
    // access out of bounds" / delegate buffer overflow: google-ai-edge/gallery#703,
    // mediapipe#6270). The crash is an uncatchable WASM abort, so sendMessageStreaming
    // never resolves → the agent loop hangs → UI freeze (and run_python never reaches
    // its worker, since the crash is in round-0 generation, before the tool loop). So
    // thinking is OPT-IN now: only the provider's Thinking dropdown set to "on (/think)"
    // injects <|think|>. Re-enable by default once upstream ships a fix (try SDK 0.13.1+).
    const wantThink = (provider.reasoning === 'think');
    if (wantThink) sysText = '<|think|>' + (sysText ? '\n' + sysText : '');

    // Working history, re-mapped into a FRESH conversation each round (see header). Grows
    // by the assistant turn + each tool result; the last mapped turn is the one we send,
    // everything before it is the preface.
    const work = [];
    if (sysText) work.push({ role: 'system', content: sysText });
    for (const m of (messages || [])) { if (m && m.role) work.push(m); }

    // DEBUG: expose the EXACT prompt the model sees each round — `system` is the full
    // system prompt WITH the tool descriptions (buildToolPreamble is folded into sysText
    // above), plus the mapped `preface` history, the `sent` turn, and the raw output.
    // Reset per send so it holds just this turn's rounds. Inspect from DevTools:
    //   copy(window.__litertlmPrompts)   — every round of this turn
    //   copy(window.__litertlmPrompt)    — the latest round only
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

    try {
      for (let round = 0; round < MAX_ROUNDS; round++) {
        if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');
        emit({ type: 'round_start' });

        // Fresh conversation seeded with the full history; the last turn is the send,
        // everything before it is the (thought-free) preface. Deleted right after the
        // stream so no live KV cache is ever carried into the next round.
        const mapped = work.map(m => ({ role: mapRole(m.role), content: mapContent(m) }));
        const last = mapped.length ? mapped[mapped.length - 1] : { content: '' };
        const preface = mapped.slice(0, -1);
        // DEBUG capture (see the __litertlmPrompts note above): the full prompt for this round.
        const _cap = { round, system: sysText, preface, sent: last.content, rawOutput: null, answer: null, tool_calls: null };
        try { self.__litertlmPrompts.push(_cap); self.__litertlmPrompt = _cap; } catch (_) {}
        const conv = await engine.createConversation(buildConvConfig(provider, preface));

        // Split the stream: thought-channel text → live "Thinking…" box (delta.reasoning,
        // which the renderer shows but never replays to the model), the rest → the answer.
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
            // Structured thought channel → live "Thinking…" box (delta.reasoning, which
            // conversations.js renders but never replays to the model).
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
        // Gemma emits tool calls as TEXT we parse post-hoc, so — unlike wllama's native
        // streaming — the renderer never saw a tool_calls delta and never built the
        // tool-call bubbles, leaving tool_started/tool_result with nothing to update
        // (they look the bubble up by id and bail). Synthesize the OAI-streaming delta
        // here so conversations.js creates the bubbles before we run the tools. The
        // renderer appends name/arguments, so one complete chunk per call is correct.
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
            out = await toolViaWorker(tc.function && tc.function.name, args, convId, signal);
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
    } catch (e) {
      if (e && e.name === 'AbortError') throw e;   // each round deletes its own conv; conversations.js handles abort
      emit({ type: 'info', message: null });
      emit({ type: 'error', message: 'litertlm: ' + ((e && e.message) || e) });
    }
    emit({ type: 'agent_done' });
    } finally { _setDecoding(false); }
  }

  // ============================================================
  // Exports
  // ============================================================
  // Free the LiteRT engine + its WebGPU device. Called by the other local backends
  // (and applyActiveProvider) so only one local LLM holds a GPU context at a time.
  // ensureEngine() lazily recreates it on next use.
  async function unload() {
    if (!_engine) return;
    try { await _engine.delete(); } catch (_) {}
    _engine = null; _engineModel = null; _engineCtx = 0;
  }

  return { DEFAULT_MODELS, DEFAULT_N_CTX, unload, streamRound, runConversation };
})();

if (typeof window !== 'undefined') window.SandpieLiteRTLM = SandpieLiteRTLM;
