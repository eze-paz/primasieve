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

  // wllama holds at most one model in memory at a time. We key by URL
  // *plus* n_ctx because n_ctx is a load-time parameter — changing it
  // requires a fresh load, not just a fresh chat.
  let _instance = null;
  let _instanceUrl = null;
  let _instanceCtx = 0;
  let _loadingKey = null;

  async function getInstance(modelUrl, onProgress, opts) {
    if (!modelUrl) throw new Error('wllama: modelUrl is required');
    const nCtx = (opts && opts.nCtx) || DEFAULT_N_CTX;
    const key = modelUrl + '|' + nCtx;
    if (_instance && _instanceUrl === modelUrl && _instanceCtx === nCtx) return _instance;
    if (_loadingKey === key) {
      while (_loadingKey === key) await new Promise(r => setTimeout(r, 50));
      if (_instance && _instanceUrl === modelUrl && _instanceCtx === nCtx) return _instance;
    }
    _loadingKey = key;
    try {
      if (_instance) {
        try { await _instance.exit(); } catch (_) {}
        _instance = null;
        _instanceUrl = null;
        _instanceCtx = 0;
      }
      // Fetch the GGUF ourselves and pass a Blob to loadModel(), which
      // skips wllama's ModelManager/CacheManager entirely. We do this
      // instead of loadModelFromUrl({useCache:false}) because that flag
      // is misnamed in the SDK — it forces a fresh download but still
      // writes the bytes to OPFS `cache/`, which sandpie's Dropbox sync
      // then tries to upload (multi-GB → 409s + session-limit blowouts).
      // Trade-off: page reload re-fetches the model. Browser HTTP cache
      // mitigates the worst case; for proof-of-concept this is fine.
      const res = await fetch(modelUrl);
      if (!res.ok) throw new Error(`wllama: model fetch failed (${res.status} ${res.statusText}) for ${modelUrl}`);
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
          });
        } catch (_) {}
      }
      const ggufBlob = new Blob(chunks);

      const { Wllama } = await loadSDK();
      // v3 constructor takes a single `default` WASM path; the worker
      // code is inlined into the SDK bundle so no separate worker URL
      // is needed. WebGPU is auto-enabled when supported.
      const inst = new Wllama({ default: WASM_URL });
      await inst.loadModel([ggufBlob], { n_ctx: nCtx });
      _instance = inst;
      _instanceUrl = modelUrl;
      _instanceCtx = nCtx;
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
   */
  async function streamRound({ modelUrl, messages, tools, signal, onDelta, onProgress, nCtx }) {
    const wllama = await getInstance(modelUrl, onProgress, { nCtx });
    if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');

    let aborted = false;
    const onAbort = () => { aborted = true; };
    if (signal) {
      if (signal.aborted) onAbort();
      else signal.addEventListener('abort', onAbort, { once: true });
    }

    let content = '';
    const toolCalls = [];

    try {
      const stream = await wllama.createChatCompletion({
        messages: adaptMessages(messages),
        max_tokens: 1024,
        temperature: 0.7,
        top_p: 0.9,
        stream: true,
        ...(tools && tools.length ? { tools } : {}),
      });

      for await (const chunk of stream) {
        if (aborted) break;
        const delta = chunk && chunk.choices && chunk.choices[0] && chunk.choices[0].delta;
        if (!delta) continue;
        if (delta.content) {
          content += delta.content;
          try { onDelta && onDelta({ content: delta.content }); } catch (_) {}
        }
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
      }
    } finally {
      if (signal) signal.removeEventListener('abort', onAbort);
    }

    if (aborted) throw new DOMException('aborted', 'AbortError');

    return {
      content,
      tool_calls: toolCalls.filter(tc => tc && tc.id),
    };
  }

  return {
    DEFAULT_MODELS,
    DEFAULT_N_CTX,
    getInstance,
    streamRound,
  };
})();
