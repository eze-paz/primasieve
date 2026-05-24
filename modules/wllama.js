// sandpie/modules/wllama.js — In-browser GGUF inference via llama.cpp (WASM)
//
// wllama (https://github.com/ngxson/wllama) is a WebAssembly port of
// llama.cpp. CPU-only — no WebGPU — which means it runs everywhere
// (including iOS Safari) but is slower than WebLLM on capable hardware.
// The trade-off is worth it when:
//   - the user is on iOS or a device without WebGPU,
//   - you want to load any GGUF from Hugging Face directly (no MLC
//     compilation pipeline),
//   - reliable tool-calling matters: llama.cpp has grammar/JSON-schema
//     constraints that can pin the output shape (we leave that as a
//     future enhancement; v1 uses the Hermes <tool_call> tag format).
//
// This module:
//   - lazy-loads the wllama SDK + WASM artifacts from a CDN,
//   - swaps the single loaded model when the active provider changes
//     (wllama only holds one model in memory at a time),
//   - exposes streamRound() with the same delta shape the OpenAI-compat
//     agent loop emits, so the page-side agent code in sandpie-wllama.html
//     reuses RoundRenderer / dispatchAgentEvent without changes,
//   - injects a Hermes/Qwen-style tool-calling preamble into the system
//     message when tools are present and parses <tool_call>…</tool_call>
//     blocks out of the assistant's text into proper tool_calls entries.

const SandpieWllama = (function() {
  'use strict';

  // CDN-hosted ESM build of the wllama SDK + its WASM artifacts.
  // Pinned by major; the wllama API has stabilised at 2.x.
  const SDK_URL  = 'https://esm.run/@wllama/wllama@2';
  const WASM_ST  = 'https://cdn.jsdelivr.net/npm/@wllama/wllama@2/src/single-thread/wllama.wasm';
  const WASM_MT  = 'https://cdn.jsdelivr.net/npm/@wllama/wllama@2/src/multi-thread/wllama.wasm';

  // Curated GGUF catalog. Each entry's `url` points at a HuggingFace
  // direct-download URL (resolve/main/<file>.gguf). The dropdown also
  // offers a free-text "Custom" option so users can paste any GGUF URL.
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

  // wllama holds at most one model in memory at a time — switching
  // providers tears the previous instance down. We key by URL because
  // that's the identity (curated id → canonical URL, custom → as typed).
  let _instance = null;
  let _instanceUrl = null;
  let _loadingFor = null;

  /**
   * Get (loading if necessary) the wllama instance for the given GGUF URL.
   * Tears down a previously-loaded different model first.
   */
  async function getInstance(modelUrl, onProgress) {
    if (!modelUrl) throw new Error('wllama: modelUrl is required');
    if (_instance && _instanceUrl === modelUrl) return _instance;
    if (_loadingFor === modelUrl) {
      // Concurrent loader request — wait until the in-flight one finishes.
      while (_loadingFor === modelUrl) await new Promise(r => setTimeout(r, 50));
      if (_instance && _instanceUrl === modelUrl) return _instance;
    }
    _loadingFor = modelUrl;
    try {
      if (_instance) {
        try { await _instance.exit(); } catch (_) {}
        _instance = null;
        _instanceUrl = null;
      }
      const { Wllama } = await loadSDK();
      const inst = new Wllama({
        'single-thread/wllama.wasm': WASM_ST,
        'multi-thread/wllama.wasm':  WASM_MT,
      });
      await inst.loadModelFromUrl(modelUrl, {
        progressCallback: ({ loaded, total }) => {
          try {
            onProgress && onProgress({
              loaded, total,
              progress: total ? loaded / total : 0,
            });
          } catch (_) {}
        },
      });
      _instance = inst;
      _instanceUrl = modelUrl;
      return inst;
    } finally {
      if (_loadingFor === modelUrl) _loadingFor = null;
    }
  }

  // ============================================================
  // Tool-call format adapter (Hermes / Qwen style)
  // ============================================================

  /**
   * Build the system-message addition that tells the model what tools
   * are available and how to invoke them. Matches the format Hermes-3
   * and Qwen 2.5 are trained on — those models reliably emit
   * <tool_call>{json}</tool_call> blocks when the schema is given this way.
   */
  function buildToolsPreamble(tools) {
    if (!tools || !tools.length) return '';
    const schemas = tools.map(t => t.function).filter(Boolean);
    if (!schemas.length) return '';
    return `

# Available tools

You have access to the following functions. Call them by emitting JSON inside <tool_call> tags.

<tools>
${schemas.map(s => JSON.stringify(s)).join('\n')}
</tools>

To call a function, emit one JSON object per call, each wrapped in <tool_call></tool_call> exactly like this:

<tool_call>
{"name": "<function_name>", "arguments": <arguments_object>}
</tool_call>

You may emit multiple <tool_call> blocks in one turn. After the call(s), you'll see one <tool_response> block per call with the result. Then continue normally — if no more tools are needed, just respond to the user in plain text without any <tool_call> tags.`;
  }

  /**
   * Parse <tool_call>…</tool_call> blocks out of a raw model response.
   * Returns the OpenAI-style tool_calls array (with synthesised ids
   * since the model doesn't supply them).
   */
  function parseToolCallsFromText(text) {
    const calls = [];
    if (!text) return calls;
    const re = /<tool_call>\s*([\s\S]*?)\s*<\/tool_call>/g;
    let m, i = 0;
    while ((m = re.exec(text)) !== null) {
      const raw = m[1].trim();
      try {
        const obj = JSON.parse(raw);
        if (!obj || !obj.name) continue;
        calls.push({
          id: 'tc_wllama_' + Date.now().toString(36) + '_' + (i++),
          type: 'function',
          function: {
            name: String(obj.name),
            arguments: typeof obj.arguments === 'string'
              ? obj.arguments
              : JSON.stringify(obj.arguments || {}),
          },
        });
      } catch (_) {
        // Malformed JSON — skip silently. The model might recover next turn.
      }
    }
    return calls;
  }

  /** Strip <tool_call> blocks from text so the user-visible content is clean. */
  function stripToolCalls(text) {
    return (text || '').replace(/<tool_call>[\s\S]*?<\/tool_call>/g, '').trim();
  }

  /**
   * Convert sandpie's OpenAI-shape messages into the shape wllama's
   * createChatCompletion expects:
   *   - role:tool → folded into the next user turn as a <tool_response> block
   *     (wllama / most local chat templates don't carry role:tool natively)
   *   - tools[] → inlined into the system message as a Hermes-style preamble
   *   - multimodal content (image_url parts) → dropped with a "[image]"
   *     placeholder since wllama is text-only
   */
  function adaptMessages(messages, tools) {
    const out = [];
    let sawSystem = false;
    for (const m of messages) {
      if (m.role === 'system') {
        sawSystem = true;
        out.push({ role: 'system', content: (m.content || '') + buildToolsPreamble(tools) });
        continue;
      }
      if (m.role === 'tool') {
        const block = `<tool_response>\n${m.content}\n</tool_response>`;
        // Try to attach to the previous user turn if we just emitted one;
        // otherwise create a fresh user turn carrying the response.
        const last = out[out.length - 1];
        if (last && last.role === 'user') last.content += '\n' + block;
        else out.push({ role: 'user', content: block });
        continue;
      }
      // user / assistant
      let content = '';
      if (Array.isArray(m.content)) {
        for (const part of m.content) {
          if (part && part.type === 'text' && part.text) content += (content ? '\n' : '') + part.text;
          else if (part && part.type === 'image_url') content += (content ? '\n' : '') + '[image attachment — wllama is text-only and cannot view this]';
        }
      } else {
        content = m.content || '';
      }
      out.push({ role: m.role, content });
    }
    if (!sawSystem && tools && tools.length) {
      out.unshift({ role: 'system', content: 'You are a helpful assistant.' + buildToolsPreamble(tools) });
    }
    return out;
  }

  // ============================================================
  // Streaming round
  // ============================================================

  /**
   * Run one chat-completion round. Streams text tokens via onDelta
   * (delta.content carries the incremental piece), parses tool_calls
   * out of the final text, and returns { content, tool_calls } so the
   * page-side agent loop can stay shape-compatible with the SW path.
   */
  async function streamRound({ modelUrl, messages, tools, signal, onDelta, onProgress }) {
    const wllama = await getInstance(modelUrl, onProgress);
    if (signal && signal.aborted) throw new DOMException('aborted', 'AbortError');

    const wMessages = adaptMessages(messages, tools);

    let acc = '';
    let aborted = false;
    const onAbort = () => { aborted = true; };
    if (signal) {
      if (signal.aborted) onAbort();
      else signal.addEventListener('abort', onAbort, { once: true });
    }

    try {
      // wllama's createChatCompletion accepts onNewToken; we synthesise
      // OpenAI-style delta events from the incremental currentText so
      // the page-side dispatcher gets the same shape as the SW path.
      // (Stripping <tool_call> blocks happens *after* the round — while
      // streaming we let raw tokens through so the user sees progress
      // even if the model wraps something in tags mid-stream.)
      await wllama.createChatCompletion(wMessages, {
        nPredict: 1024,
        sampling: { temp: 0.7, top_p: 0.9 },
        onNewToken: (_token, piece, currentText) => {
          if (aborted) return;
          // Some wllama builds pass piece; others pass currentText. Cover both.
          const next = typeof currentText === 'string' ? currentText : (acc + (piece || ''));
          if (next.length > acc.length) {
            const delta = next.slice(acc.length);
            acc = next;
            try { onDelta && onDelta({ content: delta }); } catch (_) {}
          }
        },
      });
    } finally {
      if (signal) signal.removeEventListener('abort', onAbort);
    }

    if (aborted) throw new DOMException('aborted', 'AbortError');

    const toolCalls = parseToolCallsFromText(acc);
    const content = stripToolCalls(acc);
    return { content, tool_calls: toolCalls };
  }

  return {
    DEFAULT_MODELS,
    getInstance,
    streamRound,
  };
})();
