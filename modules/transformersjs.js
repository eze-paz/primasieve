// sandpie/modules/transformersjs.js — In-browser LLM via Transformers.js, run
// INLINE on the page main thread (no Web Worker), as a FAITHFUL MIRROR of the
// working HF Space webml-community/Qwen3.5-WebGPU (transformers.js@4.2.0).
//
// This module is deliberately kept as close to that Space's index.js as possible
// because that Space WORKS and our earlier divergences did not. Specifically we
// match the Space on every load/generation decision:
//   • import @huggingface/transformers@4.2.0 from jsdelivr, NO env overrides
//     (no wasmPaths override, no numThreads — the Space sets none, and forcing
//     the threaded ORT WASM without cross-origin isolation mis-loads).
//   • AutoProcessor + Qwen3_5ForConditionalGeneration, per-component dtype map,
//     device:'webgpu' ONLY (no WASM fallback).
//   • NO warmup (a failed warmup corrupts the WebGPU device → every later
//     generate() fails on invalid buffers).
//   • Manual ChatML prompt (<|im_start|>…<think>…) — NOT apply_chat_template;
//     the Space hand-builds the prompt because that is what its KV-cache reuse
//     (past_key_values across turns) requires.
//   • generate(): max_new_tokens 2048/512 by thinking, do_sample:true,
//     return_dict_in_generate:true; TextStreamer skip_special_tokens:!thinking.
//   • KV-cache reuse: keep past_key_values + the decoded prompt history and feed
//     them back on the next turn so only the new tokens are prefilled.
//
// The Space is a single-purpose chat demo: NO tool-calling, NO agentic loop. We
// keep only a thin sandpie adapter on top — runConversation emits the host event
// protocol (reasoning → reasoning_content, answer → content), and streamRound is
// the stateless one-shot used by agents.js for utility prompts (titles, etc.).

const SandpieTransformersJS = (function () {
  'use strict';

  const DEFAULT_N_CTX = 8192;

  // Kill-switch for cross-turn KV-cache reuse. ON mirrors the Space (faster
  // multi-turn). If it ever produces garbled continuations on some model/lib
  // combo, flip to false to force a full cold prefill every turn (always
  // correct, just slower) without touching the rest of the logic.
  const ENABLE_KV_CACHE = true;

  // Per-component quant — IDENTICAL to the Space. NOTE q4 (NOT q4f16): fp16
  // WebGPU kernels freeze Intel iGPUs (TDR → driver reset).
  const QWEN35_DTYPE = {
    embed_tokens: 'q4',
    vision_encoder: 'fp16',
    decoder_model_merged: 'q4',
  };

  // Exactly the Space's dropdown option values (its <select id="modelSelect">).
  const DEFAULT_MODELS = [
    {
      id: 'qwen3.5-0.8b',
      label: 'Qwen 3.5 0.8B (~0.8 GB, smallest, fastest)',
      modelId: 'onnx-community/Qwen3.5-0.8B-ONNX-OPT',
    },
    {
      id: 'qwen3.5-2b',
      label: 'Qwen 3.5 2B (~2 GB, balanced)',
      modelId: 'onnx-community/Qwen3.5-2B-ONNX-OPT',
    },
    {
      id: 'qwen3.5-4b',
      label: 'Qwen 3.5 4B (~4 GB, most capable)',
      modelId: 'onnx-community/Qwen3.5-4B-ONNX-OPT',
    },
  ];

  // The EXACT CDN + version the Space imports. Pin a SPECIFIC version — NEVER
  // float ('@4'/'latest'); bump deliberately to a TESTED version.
  const LIB_URL = 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.2.0';

  // ============================================================
  // Debug logging
  // ============================================================
  const DEBUG_KEY = 'sandpie-transformersjs-debug';
  function isDebug() {
    try { return localStorage.getItem(DEBUG_KEY) === '1'; }
    catch (_) { return false; }
  }
  function dbg(...args) {
    if (isDebug()) console.log('[transformersjs]', ...args);
  }

  // ============================================================
  // Module state (model + the cross-turn KV cache)
  // ============================================================
  let _lib = null;
  let _processor = null, _model = null, _currentModelId = null;

  // KV-cache state — mirrors the Space's pastKeyValues/promptHistory, scoped to a
  // conversation so we only reuse the cache on a verified clean append.
  let _pastKeyValues = null;     // the model's KV cache from the last generation
  let _promptHistory = '';       // full decoded sequence the cache corresponds to
  let _kvConvId = null;          // which conversation the cache belongs to
  let _consumedSig = null;       // signature of the messages already baked into the cache
  let _consumedCount = 0;        // how many messages are baked in

  // Import the library. NO env overrides — the Space sets none and works; letting
  // onnxruntime-web auto-pick its backend (single-threaded when there's no
  // SharedArrayBuffer) is exactly what the Space relies on.
  async function lib() {
    if (!_lib) _lib = await import(LIB_URL);
    return _lib;
  }

  // Dispose the KV cache tensors and clear all cache bookkeeping. Use only when we
  // OWN the cache and are discarding it (cold start / model switch / unload).
  function disposeKv() {
    if (_pastKeyValues) {
      try { for (const t of Object.values(_pastKeyValues)) t && t.dispose && t.dispose(); } catch (_) {}
    }
    resetKvRefs();
  }
  // Drop our references WITHOUT disposing (used after errors, to avoid a possible
  // double-free if the library already freed mid-failure).
  function resetKvRefs() {
    _pastKeyValues = null;
    _promptHistory = '';
    _kvConvId = null;
    _consumedSig = null;
    _consumedCount = 0;
  }

  // Load (and cache) the processor + model, exactly like the Space:
  // AutoProcessor + Qwen3_5ForConditionalGeneration, dtype map, device:'webgpu',
  // NO warmup. Switching models tears down the previous one (and its KV cache,
  // whose tensors belong to the old model).
  async function ensureModel(modelId, onProgress) {
    if (_currentModelId === modelId && _model && _processor) return;
    if (_model) { try { await _model.dispose?.(); } catch (_) {} }
    disposeKv();
    _model = null; _processor = null; _currentModelId = null;

    const { AutoProcessor, Qwen3_5ForConditionalGeneration } = await lib();
    const progress_callback = onProgress || undefined;

    const processor = await AutoProcessor.from_pretrained(modelId, { progress_callback });
    const model = await Qwen3_5ForConditionalGeneration.from_pretrained(modelId, {
      dtype: QWEN35_DTYPE,
      device: 'webgpu',
      progress_callback,
    });

    _processor = processor;
    _model = model;
    _currentModelId = modelId;
    // No warmup — see header. The first real generate compiles shaders itself.
  }

  // Free the model + its WebGPU device. Called by the other local backends (and
  // applyActiveProvider) so only one local LLM holds a GPU context at a time.
  async function unload() {
    if (_model) { try { await _model.dispose?.(); } catch (_) {} }
    disposeKv();
    _model = null; _processor = null; _currentModelId = null;
  }

  // ============================================================
  // Prompt construction — manual ChatML, mirroring the Space.
  // ============================================================
  // Flatten a message's content (string or OpenAI-style parts array) to text.
  // Image parts are dropped: this is the Space's text path (vision isn't wired).
  function textOf(content) {
    if (typeof content === 'string') return content;
    if (Array.isArray(content)) {
      return content.map(p => {
        if (typeof p === 'string') return p;
        if (p && p.type === 'text') return p.text || '';
        return '';
      }).join('');
    }
    return content == null ? '' : String(content);
  }

  function imBlock(role, text) {
    return `<|im_start|>${role}\n${text}<|im_end|>\n`;
  }
  // The assistant generation opener — IDENTICAL to the Space. With thinking the
  // model continues inside an open <think>; without, the block is pre-closed.
  function assistantOpen(enableThinking) {
    return enableThinking
      ? `<|im_start|>assistant\n<think>\n`
      : `<|im_start|>assistant\n<think>\n\n</think>\n\n`;
  }
  // Render a list of messages as consecutive ChatML blocks (no trailing
  // assistant opener). tool messages (none in this backend) map to user blocks.
  function renderHistory(msgs) {
    let p = '';
    for (const m of msgs || []) {
      const role = (m.role === 'system' || m.role === 'user' || m.role === 'assistant') ? m.role : 'user';
      p += imBlock(role, textOf(m.content));
    }
    return p;
  }
  // Stable signature of a message slice, to detect a clean append vs an edit.
  function sig(msgs) {
    return JSON.stringify((msgs || []).map(m => [m.role, textOf(m.content)]));
  }
  function decodeSeq(result) {
    const dec = (_processor && _processor.batch_decode) ? _processor : (_processor && _processor.tokenizer);
    try { return dec.batch_decode(result.sequences, { skip_special_tokens: false })[0] || ''; }
    catch (_) { return ''; }
  }

  // ============================================================
  // Core generation — one inline generate(), streamed. Mirrors the Space:
  // processor(promptText) → generate({...inputs, [past_key_values], max_new_tokens,
  // do_sample, streamer, stopping_criteria, return_dict_in_generate}). When
  // thinking, skip_special_tokens is OFF so we can split on </think> and route the
  // chain-of-thought to onReasoning and the answer to onContent.
  // ============================================================
  async function generate({ modelId, promptText, pastKeyValues, maxTokens, enableThinking, signal, onReasoning, onContent, onProgress }) {
    await ensureModel(modelId, onProgress);
    if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');

    const { TextStreamer, InterruptableStoppingCriteria } = await lib();

    const inputs = await _processor(promptText);
    const generateArgs = pastKeyValues ? { ...inputs, past_key_values: pastKeyValues } : { ...inputs };

    // Single accumulating buffer; on each token we recompute the reasoning/content
    // split and emit only the new tail (idempotent, handles the </think> boundary
    // crossing a token).
    let raw = '', prevReason = '', prevContent = '';
    const split = () => {
      let reason = '', content = '';
      if (enableThinking) {
        const idx = raw.indexOf('</think>');
        if (idx === -1) { reason = raw; }
        else { reason = raw.slice(0, idx); content = raw.slice(idx + '</think>'.length); }
      } else {
        content = raw;
      }
      content = content.replace(/<\|im_end\|>[\s\S]*$/, '').replace(/^\n+/, '');
      reason = reason.replace(/^\n+/, '');
      return { reason, content };
    };

    const streamer = new TextStreamer(_processor.tokenizer || _processor, {
      skip_prompt: true,
      skip_special_tokens: !enableThinking,
      callback_function: (token) => {
        if (!token) return;
        raw += token;
        const { reason, content } = split();
        if (reason.length > prevReason.length) { const d = reason.slice(prevReason.length); prevReason = reason; try { onReasoning && onReasoning(d); } catch (_) {} }
        if (content.length > prevContent.length) { const d = content.slice(prevContent.length); prevContent = content; try { onContent && onContent(d); } catch (_) {} }
      },
    });

    const stopping = InterruptableStoppingCriteria ? new InterruptableStoppingCriteria() : null;
    const onAbort = () => { try { stopping && stopping.interrupt(); } catch (_) {} };
    if (signal) signal.addEventListener('abort', onAbort, { once: true });

    let result;
    try {
      const opts = {
        ...generateArgs,
        max_new_tokens: maxTokens || (enableThinking ? 2048 : 512),
        do_sample: true,
        streamer,
        return_dict_in_generate: true,
      };
      if (stopping) opts.stopping_criteria = stopping;
      dbg('→ generate', modelId, 'cache', !!pastKeyValues, 'thinking', enableThinking);
      result = await _model.generate(opts);
    } finally {
      if (signal) signal.removeEventListener('abort', onAbort);
    }

    const { reason, content } = split();
    return { content: content.trim(), reasoning: reason.trim(), result };
  }

  // ============================================================
  // streamRound — stateless one-shot used by agents.js (titles/distill etc.).
  // Never touches the conversation KV cache; thinking off for a fast direct
  // answer. Returns { content, tool_calls:[] } (no tools in this backend).
  // ============================================================
  async function streamRound({ modelUrl, messages, signal, onDelta, onProgress, maxTokens }) {
    if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');
    const promptText = renderHistory(messages) + assistantOpen(false);
    const { content } = await generate({
      modelId: modelUrl,
      promptText,
      pastKeyValues: null,
      maxTokens: maxTokens || 512,
      enableThinking: false,
      signal,
      onProgress,
      onContent: (d) => { try { onDelta && onDelta({ content: d }); } catch (_) {} },
    });
    return { content, tool_calls: [] };
  }

  // ============================================================
  // Agentic-shaped adapter for the host (conversations.js). No tools/rounds —
  // one generation per user turn — but emits the same event protocol so the
  // renderer (incl. the Thinking box via reasoning_content) is reused unchanged.
  // ============================================================
  async function runConversation(
    { provider, messages, systemPrompt, tools, convId, signal },
    emit
  ) {
    // Single active local backend: free the OTHER local LLMs' GPU/WASM contexts
    // first, so only one local runtime holds a WebGPU device at a time.
    try { await window.SandpieWllama?.unload?.(); } catch (_) {}
    try { await window.SandpieLiteRTLM?.unload?.(); } catch (_) {}
    try { await window.SandpieQwen35?.unload?.(); } catch (_) {}

    const modelId = provider.endpoint;
    const reasoning = (provider.reasoning || 'auto');
    const enableThinking = reasoning !== 'off' && reasoning !== 'none' && reasoning !== 'no_think';
    const maxTokens = provider.maxTokens || (enableThinking ? 2048 : 512);

    const sysText = systemPrompt && typeof systemPrompt === 'object' ? (systemPrompt.content || '') : systemPrompt;
    const work = [];
    if (sysText) work.push({ role: 'system', content: sysText });
    work.push(...(messages || []));

    // Loading line. A CACHED load fires NO download-progress events, so show this
    // up front, refine with the % when a download happens, clear on first token.
    let firstToken = false;
    let lastPct = -1;
    const alreadyLoaded = (_currentModelId === modelId && _model && _processor);
    if (!alreadyLoaded) {
      emit({ type: 'info', message: 'Loading local model… first run downloads it (cached after) — this can take a while.' });
    }
    const onProgress = (p) => {
      if (firstToken || alreadyLoaded || !p || p.status !== 'progress') return;
      const pct = Math.round(p.progress != null ? p.progress : (p.total ? (p.loaded / p.total) * 100 : -1));
      if (pct >= 0 && pct <= 100 && pct !== lastPct) {
        lastPct = pct;
        emit({ type: 'info', message: `Downloading local model… ${pct}%` });
      }
    };

    emit({ type: 'round_start' });

    // Cold prefill vs KV-cache continuation. Continue ONLY when this is a verified
    // clean append to the same conversation we cached (same convId, the cached
    // prefix is byte-identical, and there's at least one new message). Any doubt →
    // cold prefill, which is always correct.
    let promptText, usingCache = false;
    const canContinue = ENABLE_KV_CACHE
      && _kvConvId === convId && _pastKeyValues && _promptHistory
      && work.length > _consumedCount
      && sig(work.slice(0, _consumedCount)) === _consumedSig;
    if (canContinue) {
      const newMsgs = work.slice(_consumedCount);
      promptText = _promptHistory + '\n' + renderHistory(newMsgs) + assistantOpen(enableThinking);
      usingCache = true;
    } else {
      disposeKv();
      promptText = renderHistory(work) + assistantOpen(enableThinking);
    }

    let res;
    try {
      res = await generate({
        modelId,
        promptText,
        pastKeyValues: usingCache ? _pastKeyValues : null,
        maxTokens,
        enableThinking,
        signal,
        onProgress,
        onReasoning: (d) => {
          if (!firstToken) { firstToken = true; emit({ type: 'info', message: null }); }
          emit({ type: 'delta', delta: { reasoning_content: d } });
        },
        onContent: (d) => {
          if (!firstToken) { firstToken = true; emit({ type: 'info', message: null }); }
          emit({ type: 'delta', delta: { content: d } });
        },
      });
    } catch (e) {
      emit({ type: 'info', message: null });
      resetKvRefs();   // next turn starts clean (avoid double-free on a mid-failure cache)
      if (e && e.name === 'AbortError') throw e;
      emit({ type: 'error', message: 'transformersjs: ' + ((e && e.message) || e) });
      emit({ type: 'agent_done' });
      return;
    }

    emit({ type: 'info', message: null });
    emit({ type: 'round_end', content: res.content });

    const asst = { role: 'assistant', content: res.content };
    emit({ type: 'message_added', message: asst });

    // Update the KV cache for the next turn. Mirror the Space: just reassign
    // past_key_values (the library extends/owns it — do NOT dispose here, or we'd
    // free tensors the new cache reuses). Record the snapshot of everything baked
    // in (= work + the assistant we just produced) so next turn can verify a clean
    // append before reusing the cache.
    if (ENABLE_KV_CACHE && res.result && res.result.past_key_values) {
      _pastKeyValues = res.result.past_key_values;
      _promptHistory = decodeSeq(res.result);
      _kvConvId = convId;
      const snap = [...work, asst];
      _consumedSig = sig(snap);
      _consumedCount = snap.length;
    } else {
      resetKvRefs();
    }

    emit({ type: 'agent_done' });
  }

  // ============================================================
  // Exports
  // ============================================================
  const api = {
    DEFAULT_MODELS,
    DEFAULT_N_CTX,
    unload,
    streamRound,
    runConversation,
  };

  return api;
})();

if (typeof window !== 'undefined') window.SandpieTransformersJS = SandpieTransformersJS;
