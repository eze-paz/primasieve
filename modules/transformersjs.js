// sandpie/modules/transformersjs.js — In-browser LLM inference via Transformers.js (ONNX Runtime Web + WebGPU)
//
// Loads ONNX-quantized models from the Hugging Face Hub and runs them
// directly in the browser. Uses the Transformers.js v4 API:
//   AutoTokenizer.from_pretrained()  → chat templates (with tools when supported)
//   AutoModelForCausalLM.from_pretrained() → ONNX/WebGPU generation
//   TextStreamer → token-level streaming callback
//
// Tool calling is prompt-driven (no grammar engine like llama.cpp), so we:
//   1. Inject tool schemas into the prompt via apply_chat_template({tools})
//   2. Parse the model's free-text output for <tool_call>…</tool_call> blocks
//   3. Validate JSON and dispatch to the SW tool endpoint
//
// Models are cached by the browser across sessions. Switching models tears
// down the previous one to free GPU memory.

const SandpieTransformersJS = (function () {
  'use strict';

  const PACKAGE_VERSION = '4';
  const ESM_URL = `https://esm.sh/@huggingface/transformers@${PACKAGE_VERSION}`;

  const DEFAULT_N_CTX = 8192;

  // Curated ONNX models from Hugging Face Hub. Some are gated — an HF access
  // token (free account) is needed. Generate one at https://hf.co/settings/tokens
  // and store it in localStorage as 'sandpie-hf-token'.
  // All PUBLIC (no HF token needed). modelId is the BASE repo id — the q4f16 ONNX
  // is chosen via the dtype param at load, NOT a repo-name suffix. ("…-q4f16"
  // repos don't exist and return 401.) Transformers.js can't load gated/private
  // models in the browser regardless (tokens are server-side only), so we curate
  // only public ones.
  const DEFAULT_MODELS = [
    {
      id: 'tinyllama-1.1b-chat-v1.0',
      label: 'TinyLlama 1.1B Chat (~700 MB, no tools)',
      modelId: 'Xenova/TinyLlama-1.1B-Chat-v1.0',
    },
    {
      id: 'qwen2.5-1.5b-instruct',
      label: 'Qwen 2.5 1.5B Instruct — q4f16 (~1.2 GB, tool-calling)',
      modelId: 'onnx-community/Qwen2.5-1.5B-Instruct',
    },
    {
      id: 'qwen2.5-3b-instruct',
      label: 'Qwen 2.5 3B Instruct — q4f16 (~2 GB, tool-calling)',
      modelId: 'onnx-community/Qwen2.5-3B-Instruct',
    },
  ];

  // ============================================================
  // State
  // ============================================================
  let _transformers = null;          // cached imported module
  let _tokenizer = null;
  let _model = null;
  let _currentModelId = null;

  // ============================================================
  // Debug logging (mirror wllama pattern)
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
  // Library import
  // ============================================================
  async function loadTransformers() {
    if (_transformers) return _transformers;
    try {
      _transformers = await import(ESM_URL);
    } catch (e) {
      console.error('[transformersjs] failed to import Transformers.js from', ESM_URL, e);
      throw new Error('Failed to load Transformers.js library: ' + (e.message || e));
    }
    return _transformers;
  }

  // ============================================================
  // Model loading & cache management
  // ============================================================
  async function ensureModel(modelId, onDownloadProgress) {
    if (_currentModelId === modelId && _model && _tokenizer) {
      return { tokenizer: _tokenizer, model: _model };
    }

    // Tear down previous model to free VRAM
    if (_model) {
      try { await _model.dispose?.(); } catch (_) {}
      _model = null;
      _tokenizer = null;
      _currentModelId = null;
    }

    try {
      const { AutoTokenizer, AutoModelForCausalLM } = await loadTransformers();

      const progress_callback = (data) => {
        if (!data) return;
        const p = {
          loaded: data.loaded || 0,
          total: data.total || 0,
          progress: data.progress || (data.total ? data.loaded / data.total : 0),
          fromCache: data.status === 'done' || (data.loaded > 0 && data.loaded === data.total),
        };
        onDownloadProgress && onDownloadProgress(p);
      };

      dbg('loading tokenizer for', modelId);
      const tokenizer = await AutoTokenizer.from_pretrained(modelId, { progress_callback });

      dbg('loading model for', modelId);
      // CPU/WASM ONLY by default. WebGPU is faster but loads the whole model into
      // GPU VRAM — a multi-GB model on a VRAM-limited GPU overflows the driver,
      // which can FREEZE OR CRASH THE WHOLE MACHINE (not just the tab — it crashed
      // a real PC). Never default in-browser inference to the GPU. (A per-provider
      // WebGPU opt-in with a VRAM warning could be added later, like wllama's
      // GPU-layers field — but it must be opt-in, never the default.)
      const model = await AutoModelForCausalLM.from_pretrained(modelId, {
        dtype: 'q4', device: 'wasm', progress_callback,
      });

      _tokenizer = tokenizer;
      _model = model;
      _currentModelId = modelId;

      dbg('model ready', modelId);
      return { tokenizer, model };
    } catch (e) {
      const msg = String(e?.message || e || '');
      if (msg.includes('401') || msg.includes('Unauthorized') || msg.includes('gated')) {
        const wrappedErr = new Error('Model "' + modelId + '" returned 401 — it is private or gated. Transformers.js only loads PUBLIC models in the browser (HF tokens are server-side only), so pick a public model.');
        wrappedErr.original = e;
        throw wrappedErr;
      }
      throw e;
    }
  }

  // ============================================================
  // Prompt building (chat template + manual tool fallback)
  // ============================================================
  async function buildPrompt(tokenizer, messages, tools) {
    // Try native apply_chat_template with tools first
    const nativeTools = (tools || []).filter(t => t && t.type === 'function');
    if (nativeTools.length > 0) {
      try {
        const t = tokenizer;
        if (typeof t.apply_chat_template === 'function') {
          const result = await t.apply_chat_template(messages, {
            add_generation_prompt: true,
            tools: nativeTools,
          });
          if (typeof result === 'string') {
            return result;
          }
          // If it returns an object with text property
          if (result && typeof result.text === 'string') {
            return result.text;
          }
        }
      } catch (e) {
        dbg('apply_chat_template with tools failed, falling back to manual formatting:', e);
      }
    }

    // Fallback A: apply_chat_template without tools
    try {
      const t = tokenizer;
      if (typeof t.apply_chat_template === 'function') {
        const result = await t.apply_chat_template(messages, {
          add_generation_prompt: true,
        });
        if (typeof result === 'string') {
          return injectToolsIntoPrompt(result, nativeTools);
        }
        if (result && typeof result.text === 'string') {
          return injectToolsIntoPrompt(result.text, nativeTools);
        }
      }
    } catch (e) {
      dbg('apply_chat_template failed:', e);
    }

    // Fallback B: manual pipe-separated chat format
    let prompt = '';
    for (const m of messages) {
      if (m.role === 'system') prompt += m.content + '\n\n';
      else if (m.role === 'user') prompt += 'User: ' + m.content + '\n\n';
      else if (m.role === 'assistant') prompt += 'Assistant: ' + (m.content || '') + '\n\n';
      else if (m.role === 'tool') prompt += 'Tool result: ' + m.content + '\n\n';
    }
    prompt += 'Assistant:';
    return injectToolsIntoPrompt(prompt, nativeTools);
  }

  function injectToolsIntoPrompt(prompt, tools) {
    if (!tools || tools.length === 0) return prompt;
    const toolBlock = tools.map(t => {
      const fn = t.function || {};
      return `## ${fn.name}\nDescription: ${fn.description || ''}\nParameters: ${JSON.stringify(fn.parameters || {})}`;
    }).join('\n\n');

    return prompt + '\n\nYou have access to the following tools:\n\n' + toolBlock +
           '\n\nWhen you need to use a tool, output exactly:\n<tool_call>{"name": "<tool_name>", "arguments": {...}}</tool_call>\n\n';
  }

  // ============================================================
  // Tool-call parsing ( accommodates multiple model conventions )
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
  // Streaming generation
  // ============================================================
  async function streamRound({
    modelUrl,            // HF model ID (e.g. onnx-community/Qwen2.5-1.5B-Instruct-q4f16)
    messages,
    tools,
    signal,
    onDelta,
    onProgress,
    nCtx,
    maxTokens,
    temperature,
    topP,
    topK,
    frequencyPenalty,
    seed,
  }) {
    const { tokenizer, model } = await ensureModel(modelUrl, onProgress);

    const promptText = await buildPrompt(tokenizer, messages, tools);
    dbg('prompt length (chars):', promptText.length);

    // Tokenize
    let inputs;
    try {
      inputs = tokenizer(promptText, { return_tensors: true, padding: false });
    } catch (e) {
      // Fallback for tokenizer signature differences
      inputs = await tokenizer(promptText, { return_tensors: true });
    }

    let content = '';
    let firstTokenSeen = false;

    // Best-effort streaming: TextStreamer may not be available in all ESM builds.
    let streamer = null;
    try {
      const { TextStreamer } = await loadTransformers();
      if (TextStreamer) {
        streamer = new TextStreamer(tokenizer, {
          skip_prompt: true,
          skip_special_tokens: true,
          callback_function: (tokenText) => {
            if (!tokenText) return;
            if (!firstTokenSeen) {
              firstTokenSeen = true;
              if (onProgress) onProgress({ done: true });
            }
            content += tokenText;
            if (onDelta) onDelta({ content: tokenText });
          },
        });
      }
    } catch (_) {}

    const generateOpts = {
      ...inputs,
      max_new_tokens: maxTokens || 2048,
      do_sample: true,
    };

    if (streamer) generateOpts.streamer = streamer;

    if (temperature != null) generateOpts.temperature = temperature;
    if (topP != null) generateOpts.top_p = topP;
    if (topK != null) generateOpts.top_k = topK;
    if (frequencyPenalty != null) generateOpts.repetition_penalty = 1 + frequencyPenalty;
    if (seed != null) generateOpts.seed = seed;

    dbg('generate opts:', Object.keys(generateOpts).filter(k => k !== 'input_ids' && k !== 'attention_mask'));

    try {
      await model.generate(generateOpts);
    } catch (e) {
      dbg('generation error:', e);
      throw e;
    }

    // Parse tool calls out of the raw generated text
    const tool_calls = parseToolCalls(content);

    // Strip tool call XML tags from displayed content
    let cleanContent = content
      .replace(/<tool_call>[\s\S]*?<\/tool_call>/g, '')
      .replace(/```json\s*[\s\S]*?```/g, '')
      .replace(/<\|.*?>\n?/g, '')
      .trim();

    // Remove any dangling "Assistant:" prefix if the manual format leaked in
    cleanContent = cleanContent.replace(/^Assistant:\s*/i, '');

    return { content: cleanContent, tool_calls };
  }

  // ============================================================
  // Agentic conversation loop (mirrors wllama runConversation)
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
    const onDownloadProgress = (p) => {
      if (!firstToken && p.progress >= 0.999) {
        firstToken = true;
        emit({ type: 'info', message: null });
      }
    };

    const sample = {
      nCtx: (provider.contextWindow | 0) || DEFAULT_N_CTX,
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
