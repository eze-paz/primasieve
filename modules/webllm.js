// sandpie/modules/webllm.js — WebLLM in-browser inference provider
//
// WebLLM runs LLMs directly in the browser via WebGPU + WebAssembly. No
// server, no API key, no token billing. Models are downloaded on first
// use and cached by the browser; subsequent loads are near-instant.
//
// This module:
//   - lazy-loads the WebLLM SDK from a CDN (so users on the OpenAI-compat
//     path don't pay the ~500 KB download cost),
//   - caches a single MLCEngine instance per modelId,
//   - exposes streamRound() — a streaming chat-completion wrapper that
//     yields the same delta shape as the OpenAI-compat agent loop, so
//     the page-side agent code in sandpie-webllm.html can stay shape-
//     compatible with the SW agent in modules-free sandpie.
//
// Constraints driving the architecture:
//   - WebGPU isn't reliably available in service workers, so inference
//     runs on the PAGE (not in the SW). The agent loop also moves to the
//     page for WebLLM providers; the SW continues to handle tools like
//     run_python via the existing /sandpie-py endpoint.
//   - Model downloads can take a long time (multi-GB on first load).
//     onProgress passes through to the UI so the user knows the page
//     isn't hung.
//
// Curated default model list. The picker in sandpie-webllm.html offers
// these plus a free-text override, so users who want a specific MLC
// model ID can paste it without us having to maintain a full registry.

const SandpieWebLLM = (function() {
  'use strict';

  // CDN-hosted ESM build. Pinned by major to avoid surprise breakages.
  const SDK_URL = 'https://esm.run/@mlc-ai/web-llm@0.2';

  const DEFAULT_MODELS = [
    { id: 'Llama-3.2-1B-Instruct-q4f32_1-MLC',         label: 'Llama 3.2 1B (small, fast)' },
    { id: 'Llama-3.2-3B-Instruct-q4f32_1-MLC',         label: 'Llama 3.2 3B (balanced)' },
    { id: 'Phi-3.5-mini-instruct-q4f16_1-MLC',         label: 'Phi 3.5 mini (~3.8B)' },
    { id: 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC',         label: 'Qwen 2.5 1.5B (multilingual)' },
    { id: 'Hermes-3-Llama-3.1-8B-q4f32_1-MLC',         label: 'Hermes 3 Llama 3.1 8B (tool-calling)' },
  ];

  // ============================================================
  // SDK + engine cache
  // ============================================================

  let _sdkPromise = null;
  function loadSDK() {
    if (!_sdkPromise) _sdkPromise = import(SDK_URL);
    return _sdkPromise;
  }

  // engineByModel maps modelId -> Promise<MLCEngine>. Cached so switching
  // back and forth between conversations doesn't re-download or re-init.
  // The MLCEngine itself is a singleton-ish: WebLLM only supports one
  // active inference at a time, so the underlying GPU resource is shared.
  const _enginesByModel = new Map();

  /**
   * Get (and lazily build) an MLCEngine for the given model.
   * @param {string} modelId — MLC model id (e.g. 'Llama-3.2-1B-Instruct-q4f32_1-MLC')
   * @param {(progress: {progress?:number, text?:string, timeElapsed?:number}) => void} [onProgress]
   * @returns {Promise<object>}  the engine
   */
  async function getEngine(modelId, onProgress) {
    if (!modelId) throw new Error('WebLLM: modelId is required');
    let p = _enginesByModel.get(modelId);
    if (p) return p;
    p = (async () => {
      const { CreateMLCEngine } = await loadSDK();
      return await CreateMLCEngine(modelId, {
        initProgressCallback: (report) => {
          try { onProgress && onProgress(report); } catch (_) {}
        },
      });
    })();
    _enginesByModel.set(modelId, p);
    try {
      return await p;
    } catch (e) {
      // Don't pin a rejected promise — let the user retry.
      _enginesByModel.delete(modelId);
      throw e;
    }
  }

  /**
   * Run a single LLM round, streaming tokens back via onDelta. Yields the
   * same shape as the OpenAI-compat agent loop:
   *   onDelta({ content?, tool_calls? })
   * Returns { content, tool_calls } when the round finishes.
   *
   * @param {object} opts
   * @param {string} opts.model
   * @param {Array}  opts.messages  — full message array including system
   * @param {Array}  [opts.tools]   — OpenAI-style tool schemas (forwarded to capable models)
   * @param {AbortSignal} [opts.signal]
   * @param {(delta:object) => void} [opts.onDelta]
   * @param {(report:object) => void} [opts.onProgress] — model-load progress
   */
  async function streamRound({ model, messages, tools, signal, onDelta, onProgress }) {
    const engine = await getEngine(model, onProgress);
    if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');

    const req = {
      messages,
      stream: true,
    };
    // WebLLM forwards tools[] for models with function-calling support.
    // For models that don't, including tools is harmless — they just
    // ignore the schema and generate text.
    if (tools && tools.length) req.tools = tools;

    // engine.chat.completions.create with stream:true returns an async
    // iterable of OpenAI-style chunk objects. Shape parity is the whole
    // point of using WebLLM here — the page-side agent loop's delta
    // accumulation logic stays identical to the SW path.
    const stream = await engine.chat.completions.create(req);

    let content = '';
    const toolCalls = [];

    // Hook abort: interrupt WebLLM's generation if the user hits Stop.
    let aborted = false;
    const onAbort = () => {
      aborted = true;
      try { engine.interruptGenerate && engine.interruptGenerate(); } catch (_) {}
    };
    if (signal) {
      if (signal.aborted) onAbort();
      else signal.addEventListener('abort', onAbort, { once: true });
    }

    try {
      for await (const chunk of stream) {
        if (aborted) break;
        const delta = chunk && chunk.choices && chunk.choices[0] && chunk.choices[0].delta;
        if (!delta) continue;
        if (delta.content) content += delta.content;
        if (delta.tool_calls) {
          // Accumulate by index, same as the SW's streamOneRound. Some
          // models emit the function name/arguments in multiple deltas.
          for (const tc of delta.tool_calls) {
            const i = tc.index || 0;
            if (!toolCalls[i]) toolCalls[i] = { id: '', type: 'function', function: { name: '', arguments: '' } };
            if (tc.id) toolCalls[i].id = tc.id;
            if (tc.function && tc.function.name) toolCalls[i].function.name += tc.function.name;
            if (tc.function && tc.function.arguments) toolCalls[i].function.arguments += tc.function.arguments;
          }
        }
        try { onDelta && onDelta(delta); } catch (_) {}
      }
    } finally {
      if (signal) signal.removeEventListener('abort', onAbort);
    }

    if (aborted) throw new DOMException('aborted', 'AbortError');
    // Filter incomplete tool_calls (no id yet) — matches the SW's behaviour.
    return { content, tool_calls: toolCalls.filter(tc => tc && tc.id) };
  }

  return {
    DEFAULT_MODELS,
    getEngine,
    streamRound,
  };
})();
