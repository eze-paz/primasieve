// sandpie/modules/transformersjs.js — In-browser LLM via Transformers.js, run
// INLINE on the page main thread (no Web Worker), exactly like the working HF
// Spaces (webml-community/Qwen3.5-WebGPU, transformers.js-examples/qwen3-webgpu):
// those load + generate on the main thread and do NOT crash. We previously ran it
// in a worker; that added a second WebGPU instance whose teardown raced the GPU
// process ("A valid external Instance reference no longer exists") and never solved
// the underlying iGPU issue (that was the fp16 dtype, now q4). wllama and litertlm
// already load their libs on the main thread too, so this is consistent.
//
// This module owns the curated catalog, loads the model, drives the agentic tool
// loop (tool calls hit the SW's /sandpie-tool), and parses tool calls out of the
// model's text. Tool-calling is prompt-driven (no grammar engine), so we parse
// <tool_call> blocks from the output.

const SandpieTransformersJS = (function () {
  'use strict';

  const DEFAULT_N_CTX = 8192;

  // All PUBLIC (no HF token needed). modelId is the BASE repo id; the quant is
  // chosen via the dtype param (q4 default; Bonsai needs q1), NOT a repo-name
  // suffix ("…-q4f16" repos don't exist and 401). Gated/private models can't load
  // in the browser at all (tokens are server-side only), so we curate public ones.
  const DEFAULT_MODELS = [
    {
      id: 'qwen2.5-0.5b-instruct',
      label: 'Qwen 2.5 0.5B Instruct (~0.5 GB, tools — smallest, safest)',
      modelId: 'onnx-community/Qwen2.5-0.5B-Instruct',
    },
    {
      id: 'tinyllama-1.1b-chat-v1.0',
      label: 'TinyLlama 1.1B Chat (~0.7 GB, no tools)',
      modelId: 'Xenova/TinyLlama-1.1B-Chat-v1.0',
    },
    {
      id: 'qwen2.5-1.5b-instruct',
      label: 'Qwen 2.5 1.5B Instruct (~1.2 GB on WebGPU, tools)',
      modelId: 'onnx-community/Qwen2.5-1.5B-Instruct',
    },
    {
      // 1-bit (ternary) model — needs dtype 'q1', which is WebGPU-only (there's no
      // CPU/WASM q1 kernel), so it won't run on the WASM fallback. It's a base
      // model, so it completes text rather than chatting/tool-calling cleanly.
      id: 'bonsai-1.7b',
      label: 'Bonsai 1.7B — 1-bit (WebGPU only, experimental, base model)',
      modelId: 'onnx-community/Bonsai-1.7B-ONNX',
      dtype: 'q1',
    },
  ];

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
  // Model — load + generation run INLINE on the main thread.
  // ============================================================
  // Loaded from jsdelivr — the EXACT CDN the working webml-community/Qwen3.5-WebGPU
  // Space imports from. We were on esm.sh, which re-resolves transformers.js's
  // onnxruntime-web to a DEV build (1.26.0-dev) whose WASM traps mid-generation with
  // "operation does not support unaligned accesses"; jsdelivr serves the ORT build
  // transformers.js actually ships (what the Space runs). jsdelivr is also already
  // in the app CSP (marked/dompurify load from it). Pin a SPECIFIC version — NEVER
  // float ('@4' / "latest"); bump deliberately to a TESTED version.
  const LIB_URL = 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.2.0';

  // STABLE ORT WASM binaries. transformers.js 4.2.0 bundles onnxruntime-web
  // 1.26.0-dev.20260416-b7804b056c (a DEV build) and sets wasmPaths to that dev
  // version's files on jsdelivr during init. The dev build's
  // ort-wasm-simd-threaded.asyncify.wasm has an alignment bug that traps with
  // "RuntimeError: operation does not support unaligned accesses" during Qwen2.5's
  // forward pass (the matmul / attention ops hit an unaligned WASM memory access).
  // Setting numThreads=1 does NOT fix this — the threaded binary is still loaded,
  // it just runs with 1 worker; the buggy code paths are still executed.
  //
  // FIX: override wasmPaths to point at the STABLE onnxruntime-web@1.26.0 release
  // (different binary, 4,759,682 vs 4,732,131 bytes — the alignment bug is fixed).
  // Must be set BEFORE any model loads (ORT reads wasmPaths once during
  // initializeWebAssembly, which happens on the first InferenceSession creation).
  const ORT_STABLE_VERSION = '1.26.0';
  const ORT_STABLE_BASE = `https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_STABLE_VERSION}/dist/`;
  const ORT_STABLE_WASM_PATHS = {
    mjs: `${ORT_STABLE_BASE}ort-wasm-simd-threaded.asyncify.mjs`,
    wasm: `${ORT_STABLE_BASE}ort-wasm-simd-threaded.asyncify.wasm`,
  };

  let _lib = null;                                  // cached imported module
  let _tokenizer = null, _model = null, _currentModelId = null;
  let _stopping = null;                             // InterruptableStoppingCriteria for the active run

  async function lib() {
    if (!_lib) {
      _lib = await import(LIB_URL);
      // Override the DEV-build WASM paths with STABLE ORT 1.26.0 binaries BEFORE any
      // model loads. This must happen before the first InferenceSession.create() call
      // (which triggers initializeWebAssembly and reads wasmPaths). See the comment
      // above ORT_STABLE_WASM_PATHS for why the dev build's WASM traps.
      try {
        _lib.env.backends.onnx.wasm.wasmPaths = ORT_STABLE_WASM_PATHS;
      } catch (e) {
        console.warn('[transformersjs] Failed to override ORT wasmPaths — may use dev build:', e && e.message);
      }
      // Force onnxruntime-web SINGLE-THREADED. Our prod page is cross-origin isolated
      // (COOP/COEP, on for wllama), so SharedArrayBuffer exists and ORT would pick the
      // MULTI-THREADED WASM build. With the stable binaries the alignment trap is fixed,
      // but single-threaded still matches the HF Qwen3.5-WebGPU Space (which isn't
      // cross-origin isolated) and avoids worker-spawn overhead. WebGPU compute is
      // unaffected (runs on the GPU); this only bounds ORT's WASM orchestration.
      try { _lib.env.backends.onnx.wasm.numThreads = 1; } catch (_) {}
    }
    return _lib;
  }

  // Load (and cache) the tokenizer + model. WebGPU first (q4 — NOT q4f16: fp16
  // WebGPU kernels freeze Intel iGPUs), CPU/WASM fallback for no usable adapter.
  // Switching models tears down the previous to free memory + the WebGPU device.
  async function ensureModel(modelId, dtype, onProgress) {
    if (_currentModelId === modelId && _model && _tokenizer) return;
    if (_model) { try { await _model.dispose?.(); } catch (_) {} _model = null; _tokenizer = null; _currentModelId = null; }

    const { AutoTokenizer, AutoModelForCausalLM } = await lib();
    const progress_callback = onProgress || undefined;

    const tokenizer = await AutoTokenizer.from_pretrained(modelId, { progress_callback });

    let model;
    try {
      model = await AutoModelForCausalLM.from_pretrained(modelId, { dtype: dtype || 'q4', device: 'webgpu', progress_callback });
    } catch (gpuErr) {
      // No usable WebGPU adapter — fall back to CPU/WASM (q4). The WASM heap caps
      // ~2 GB, so big models can still std::bad_alloc here; that's a device limit.
      dbg('webgpu load failed, falling back to wasm:', (gpuErr && gpuErr.message) || gpuErr);
      model = await AutoModelForCausalLM.from_pretrained(modelId, { dtype: 'q4', device: 'wasm', progress_callback });
    }

    _tokenizer = tokenizer;
    _model = model;
    _currentModelId = modelId;

    // WARMUP — compile the WebGPU shaders with a 1-token dummy generation first, so
    // the first real generate doesn't compile every shader AND run a long burst in
    // one sustained GPU submission (which can trip the OS GPU watchdog). Mirrors the
    // HF demos' load(). Best-effort.
    try {
      const warm = await _tokenizer('a');
      await _model.generate({ ...warm, max_new_tokens: 1 });
    } catch (err) {
      dbg('warmup failed (continuing):', (err && err.message) || err);
    }
  }

  // Free the model + its WebGPU device. Called by the other local backends (and
  // applyActiveProvider) so only one local LLM holds a GPU context at a time.
  // ensureModel lazily reloads on next use.
  async function unload() {
    if (_model) { try { await _model.dispose?.(); } catch (_) {} }
    _model = null; _tokenizer = null; _currentModelId = null;
  }

  // Build the prompt with the tokenizer's chat template (tools when supported),
  // falling back to a manual format. Tool-calling is prompt-driven.
  async function buildPrompt(messages, tools) {
    const t = _tokenizer;
    const nativeTools = (tools || []).filter(x => x && x.type === 'function');

    if (t && typeof t.apply_chat_template === 'function') {
      // Native chat template WITH tools.
      if (nativeTools.length) {
        try {
          const r = await t.apply_chat_template(messages, { add_generation_prompt: true, tools: nativeTools });
          if (typeof r === 'string') return r;
          if (r && typeof r.text === 'string') return r.text;
        } catch (_) {}
      }
      // Native chat template WITHOUT tools (+ manual tool injection).
      try {
        const r = await t.apply_chat_template(messages, { add_generation_prompt: true });
        if (typeof r === 'string') return injectTools(r, nativeTools);
        if (r && typeof r.text === 'string') return injectTools(r.text, nativeTools);
      } catch (_) {}
    }

    // Manual fallback.
    let p = '';
    for (const m of messages) {
      if (m.role === 'system') p += m.content + '\n\n';
      else if (m.role === 'user') p += 'User: ' + m.content + '\n\n';
      else if (m.role === 'assistant') p += 'Assistant: ' + (m.content || '') + '\n\n';
      else if (m.role === 'tool') p += 'Tool result: ' + m.content + '\n\n';
    }
    return injectTools(p + 'Assistant:', nativeTools);
  }

  function injectTools(prompt, tools) {
    if (!tools || !tools.length) return prompt;
    const block = tools.map(t => {
      const fn = t.function || {};
      return `## ${fn.name}\nDescription: ${fn.description || ''}\nParameters: ${JSON.stringify(fn.parameters || {})}`;
    }).join('\n\n');
    return prompt + '\n\nYou have access to the following tools:\n\n' + block +
      '\n\nWhen you need to use a tool, output exactly:\n<tool_call>{"name": "<tool_name>", "arguments": {...}}</tool_call>\n\n';
  }

  // ============================================================
  // Tool-call parsing (pure text — accommodates several conventions)
  // ============================================================
  function parseToolCalls(text) {
    const tool_calls = [];
    const seen = new Set(); // dedupe by raw text

    // Pattern 1: <tool_call>{"name":"...", "arguments":{...}}</tool_call>
    const rxToolCall = /<tool_call>([\s\S]*?)<\/tool_call>/g;
    let m;
    while ((m = rxToolCall.exec(text)) !== null) {
      if (seen.has(m[1])) continue;
      seen.add(m[1]);
      try {
        const parsed = JSON.parse(m[1].trim());
        tool_calls.push(normalizeToolCall(parsed));
      } catch (e) {
        dbg('failed to parse <tool_call> JSON:', m[1]);
      }
    }

    // Pattern 2: markdown code block ```json [{"name":"...",...}]
    const rxJsonBlock = /```json\s*([\s\S]*?)```/g;
    while ((m = rxJsonBlock.exec(text)) !== null) {
      try {
        const parsed = JSON.parse(m[1].trim());
        if (Array.isArray(parsed)) {
          for (const item of parsed) {
            const tc = normalizeToolCall(item);
            if (tc && !seen.has(m[1])) {
              seen.add(m[1]);
              tool_calls.push(tc);
            }
          }
        } else {
          const tc = normalizeToolCall(parsed);
          if (tc && !seen.has(m[1])) {
            seen.add(m[1]);
            tool_calls.push(tc);
          }
        }
      } catch (e) {
        dbg('failed to parse JSON block:', m[1]);
      }
    }

    // Pattern 3: bare JSON array/object on its own line that looks like a tool call
    const rxBare = /(^|\n)\s*(\[[\s\S]*?\]|\{[\s\S]*?\})\s*(\n|$)/g;
    while ((m = rxBare.exec(text)) !== null) {
      try {
        const parsed = JSON.parse(m[2].trim());
        if (Array.isArray(parsed)) {
          for (const item of parsed) {
            const tc = normalizeToolCall(item);
            if (tc && !seen.has(m[2])) {
              seen.add(m[2]);
              tool_calls.push(tc);
            }
          }
        } else {
          const tc = normalizeToolCall(parsed);
          if (tc && !seen.has(m[2])) {
            seen.add(m[2]);
            tool_calls.push(tc);
          }
        }
      } catch (e) {
        // Not valid JSON, skip
      }
    }

    return tool_calls.map((tc, idx) => ({
      ...tc,
      index: idx,
    }));
  }

  function normalizeToolCall(raw) {
    if (!raw) return null;
    const name = raw.name || raw.function?.name;
    if (!name) return null;
    let args = raw.arguments || raw.arguments_text || raw.function?.arguments || raw.params || raw.parameters || {};
    if (typeof args === 'string') {
      try { args = JSON.parse(args); } catch (_) { args = {}; }
    }
    return {
      id: 'call_' + Math.random().toString(36).slice(2, 11),
      type: 'function',
      function: {
        name,
        arguments: typeof args === 'string' ? args : JSON.stringify(args),
      },
    };
  }

  // ============================================================
  // One generation round — loads the model if needed, generates inline, streams
  // tokens via onDelta. Resolves { content, tool_calls } (parsed from the text).
  // ============================================================
  async function streamRound({ modelUrl, messages, tools, signal, onDelta, onProgress, maxTokens, frequencyPenalty }) {
    if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');

    const dtype = (DEFAULT_MODELS.find(m => m.modelId === modelUrl) || {}).dtype;
    await ensureModel(modelUrl, dtype, onProgress);
    if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');

    const { TextStreamer, InterruptableStoppingCriteria } = await lib();
    const promptText = await buildPrompt(messages, tools);

    let inputs;
    try { inputs = _tokenizer(promptText, { return_tensors: true, padding: false }); }
    catch (_) { inputs = await _tokenizer(promptText, { return_tensors: true }); }

    let content = '';
    let streamer = null;
    if (TextStreamer) {
      streamer = new TextStreamer(_tokenizer, {
        skip_prompt: true,
        skip_special_tokens: true,
        callback_function: (txt) => {
          if (!txt) return;
          content += txt;
          try { onDelta && onDelta({ content: txt }); } catch (_) {}
        },
      });
    }

    _stopping = InterruptableStoppingCriteria ? new InterruptableStoppingCriteria() : null;
    const onAbort = () => { try { _stopping && _stopping.interrupt(); } catch (_) {} };
    if (signal) signal.addEventListener('abort', onAbort, { once: true });

    const opts = { ...inputs, max_new_tokens: maxTokens || 2048, do_sample: true };
    if (streamer) opts.streamer = streamer;
    if (_stopping) opts.stopping_criteria = _stopping;
    // temperature/top_p/top_k intentionally omitted — always use the model's defaults.
    if (frequencyPenalty != null) opts.repetition_penalty = 1 + frequencyPenalty;

    dbg('→ generate', modelUrl, 'msgs', (messages || []).length, 'tools', (tools || []).length);
    try {
      await _model.generate(opts);
    } finally {
      if (signal) signal.removeEventListener('abort', onAbort);
    }

    const tool_calls = parseToolCalls(content || '');
    const cleanContent = (content || '')
      .replace(/<tool_call>[\s\S]*?<\/tool_call>/g, '')
      .replace(/```json\s*[\s\S]*?```/g, '')
      .replace(/<\|.*?>\n?/g, '')
      .trim()
      .replace(/^Assistant:\s*/i, '');
    return { content: cleanContent, tool_calls };
  }

  // ============================================================
  // Agentic conversation loop (mirrors wllama runConversation). Emits the same
  // event protocol conversations.js expects; tool calls run via /sandpie-tool.
  // ============================================================
  async function runConversation(
    { provider, messages, systemPrompt, tools, convId, signal },
    emit
  ) {
    // Single active local backend: free the OTHER local LLMs' GPU/WASM contexts
    // first, so only one local runtime holds a WebGPU device at a time.
    try { await window.SandpieWllama?.unload?.(); } catch (_) {}
    try { await window.SandpieLiteRTLM?.unload?.(); } catch (_) {}

    const MAX_ROUNDS = 8;
    const work = [];

    const sysText = systemPrompt && typeof systemPrompt === 'object' ? (systemPrompt.content || '') : systemPrompt;
    if (sysText) work.push({ role: 'system', content: sysText });
    work.push(...messages);

    const toolList = (tools || []).filter(t => t && t.type === 'function');

    // Loading line. A CACHED load fires NO download-progress events, so we must
    // show this up front (waiting on a progress callback was the bug where it never
    // appeared) — then refine with the download % when a download does happen, and
    // clear it on the first generated token.
    let firstToken = false;
    let lastPct = -1;
    const alreadyLoaded = (_currentModelId === provider.endpoint && _model && _tokenizer);
    if (!alreadyLoaded) {
      emit({ type: 'info', message: 'Loading local model… first run downloads it (cached after) — this can take a while.' });
    }
    const onDownloadProgress = (p) => {
      if (firstToken || alreadyLoaded || !p || p.status !== 'progress') return;
      const pct = Math.round(p.progress != null ? p.progress : (p.total ? (p.loaded / p.total) * 100 : -1));
      if (pct >= 0 && pct <= 100 && pct !== lastPct) {
        lastPct = pct;
        emit({ type: 'info', message: `Downloading local model… ${pct}%` });
      }
    };

    const sample = {
      maxTokens: provider.maxTokens || 2048,
      frequencyPenalty: provider.frequencyPenalty != null ? provider.frequencyPenalty : undefined,
    };

    for (let round = 0; round < MAX_ROUNDS; round++) {
      if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');
      emit({ type: 'round_start' });

      let result;
      try {
        result = await streamRound({
          modelUrl: provider.endpoint,
          messages: work,
          tools: toolList,
          signal,
          onProgress: round === 0 ? onDownloadProgress : undefined,
          ...sample,
          onDelta: (delta) => {
            if (!firstToken) {
              firstToken = true;
              emit({ type: 'info', message: null });
            }
            emit({ type: 'delta', delta });
          },
        });
      } catch (e) {
        if (e && e.name === 'AbortError') throw e;
        emit({ type: 'info', message: null });
        emit({ type: 'error', message: 'transformersjs: ' + ((e && e.message) || e) });
        emit({ type: 'agent_done' });
        return;
      }

      emit({ type: 'info', message: null });
      // Parsed (non-streamed) tool calls need a synthetic OAI-streaming delta so the
      // renderer builds the tool-call bubbles; without it tool_started/tool_result
      // no-op (they find the bubble by id and bail). Same fix as litertlm.js.
      if (result.tool_calls && result.tool_calls.length) {
        emit({ type: 'delta', delta: { tool_calls: result.tool_calls.map((tc, i) => ({
          index: tc.index != null ? tc.index : i,
          id: tc.id,
          type: 'function',
          function: { name: (tc.function && tc.function.name) || '', arguments: (tc.function && tc.function.arguments) || '' },
        })) } });
      }
      emit({ type: 'round_end', content: result.content });

      const asst = { role: 'assistant', content: result.content };
      if (result.tool_calls && result.tool_calls.length) asst.tool_calls = result.tool_calls;
      work.push(asst);
      emit({ type: 'message_added', message: asst });

      if (!result.tool_calls || !result.tool_calls.length) break;

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
            body: JSON.stringify({
              name: tc.function && tc.function.name,
              args,
              conversation_file_name: convId,
            }),
            signal,
          });
          out = res.ok
            ? await res.json()
            : { result: 'Error: tool endpoint ' + res.status + ' — service worker not ready.' };
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
