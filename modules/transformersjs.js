// sandpie/modules/transformersjs.js — In-browser LLM via Transformers.js, run in
// a dedicated Web Worker (see modules/transformersjs-worker.js).
//
// WHY A WORKER: the model load + generation must NOT run on the page main thread.
// There they crashed the machine on WebGPU and hit std::bad_alloc on WASM, because
// the model fought the whole app for memory and ran GPU/compute on the UI thread.
// Every working HF Space runs Transformers.js in a worker; this mirrors that, so
// the worker uses WebGPU (model → VRAM, which is what makes the bigger models run)
// with a CPU/WASM fallback.
//
// This page-side module owns the curated catalog, spawns + talks to the worker,
// drives the agentic tool loop (tool calls hit the SW's /sandpie-tool), and parses
// tool calls out of the model's text. Tool-calling is prompt-driven (no grammar
// engine like llama.cpp), so we parse <tool_call> blocks from the output.

const SandpieTransformersJS = (function () {
  'use strict';

  const DEFAULT_N_CTX = 8192;

  // All PUBLIC (no HF token needed). modelId is the BASE repo id; the quant is
  // chosen via the dtype param in the worker (q4f16 on WebGPU, q4 on WASM), NOT a
  // repo-name suffix ("…-q4f16" repos don't exist and 401). Gated/private models
  // can't load in the browser at all (tokens are server-side only), so we curate
  // public ones. On WebGPU the bigger models fit (VRAM); on the WASM fallback the
  // ~2 GB heap limits you to ~1B-and-under.
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
  // Worker — model load + generation run OFF the main thread.
  // ============================================================
  // Bump ?v when editing the worker file so the browser refetches it (it isn't a
  // <script> in the HTML, so the page cache-buster doesn't cover it).
  const WORKER_URL = 'modules/transformersjs-worker.js?v=3';
  let _worker = null;
  let _reqSeq = 0;
  function getWorker() {
    if (!_worker) _worker = new Worker(WORKER_URL, { type: 'module' });
    return _worker;
  }

  // ============================================================
  // Tool-call parsing (page-side, pure text — accommodates several conventions)
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
  // One generation round — delegated to the worker, tokens relayed back.
  // Resolves { content, tool_calls } (tool calls parsed page-side from the text).
  // ============================================================
  function streamRound({ modelUrl, messages, tools, signal, onDelta, onProgress, maxTokens, temperature, topP, topK, frequencyPenalty, seed }) {
    const worker = getWorker();
    const id = ++_reqSeq;
    let acc = '';

    return new Promise((resolve, reject) => {
      const cleanup = () => {
        worker.removeEventListener('message', onMsg);
        worker.removeEventListener('error', onErr);
        if (signal) signal.removeEventListener('abort', onAbort);
      };
      const onMsg = (e) => {
        const m = e.data || {};
        if (m.type === 'progress') { try { onProgress && onProgress(m.data); } catch (_) {} return; }
        if (m.id !== id) return;  // a message from a different (stale) round
        if (m.type === 'delta') { acc += (m.text || ''); try { onDelta && onDelta({ content: m.text }); } catch (_) {} return; }
        if (m.type === 'complete') { cleanup(); resolve(m.content != null ? m.content : acc); return; }
        if (m.type === 'error') { cleanup(); reject(new Error(m.message || 'transformersjs worker error')); return; }
      };
      const onErr = (ev) => { cleanup(); reject(new Error('transformersjs worker crashed: ' + ((ev && ev.message) || 'unknown'))); };
      const onAbort = () => { try { worker.postMessage({ type: 'stop' }); } catch (_) {} };

      if (signal && signal.aborted) { reject(new DOMException('aborted', 'AbortError')); return; }
      worker.addEventListener('message', onMsg);
      worker.addEventListener('error', onErr);
      if (signal) signal.addEventListener('abort', onAbort, { once: true });

      dbg('→ generate round', id, 'model', modelUrl, 'msgs', (messages || []).length, 'tools', (tools || []).length);
      try {
        const _dtype = (DEFAULT_MODELS.find(m => m.modelId === modelUrl) || {}).dtype;
        worker.postMessage({
          type: 'generate', id, modelId: modelUrl, dtype: _dtype,
          messages: messages, tools: (tools || []),
          params: { maxTokens, temperature, topP, topK, frequencyPenalty, seed },
        });
      } catch (e) { cleanup(); reject(e); }
    }).then((fullText) => {
      const tool_calls = parseToolCalls(fullText || '');
      const cleanContent = (fullText || '')
        .replace(/<tool_call>[\s\S]*?<\/tool_call>/g, '')
        .replace(/```json\s*[\s\S]*?```/g, '')
        .replace(/<\|.*?>\n?/g, '')
        .trim()
        .replace(/^Assistant:\s*/i, '');
      return { content: cleanContent, tool_calls };
    });
  }

  // ============================================================
  // Agentic conversation loop (mirrors wllama runConversation). Emits the same
  // event protocol conversations.js expects; tool calls run via /sandpie-tool.
  // ============================================================
  async function runConversation(
    { provider, messages, systemPrompt, tools, convId, signal },
    emit
  ) {
    const MAX_ROUNDS = 8;
    const work = [];

    const sysText = systemPrompt && typeof systemPrompt === 'object' ? (systemPrompt.content || '') : systemPrompt;
    if (sysText) work.push({ role: 'system', content: sysText });
    work.push(...messages);

    const toolList = (tools || []).filter(t => t && t.type === 'function');

    let firstToken = false;
    let announced = false;
    // Worker streams download progress before the first token. Show a single
    // "loading" line (cleared on the first token); the per-file % is too noisy
    // to surface meaningfully.
    const onDownloadProgress = (p) => {
      if (firstToken || announced || !p) return;
      announced = true;
      emit({ type: 'info', message: 'Loading local model… first run downloads it (cached after) — this can take a while.' });
    };

    const sample = {
      maxTokens: provider.maxTokens || 2048,
      temperature: provider.temperature != null ? provider.temperature : undefined,
      topP: provider.topP != null ? provider.topP : undefined,
      topK: provider.topK != null ? provider.topK : undefined,
      frequencyPenalty: provider.frequencyPenalty != null ? provider.frequencyPenalty : undefined,
      seed: provider.seed != null ? provider.seed : undefined,
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
    streamRound,
    runConversation,
  };

  return api;
})();

if (typeof window !== 'undefined') window.SandpieTransformersJS = SandpieTransformersJS;
