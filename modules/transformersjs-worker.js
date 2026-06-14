// sandpie/modules/transformersjs-worker.js — Transformers.js inference inside a
// dedicated Web Worker. Loaded as a MODULE worker:
//   new Worker('modules/transformersjs-worker.js', { type: 'module' })
//
// WHY THIS EXISTS: running Transformers.js on the page main thread crashed the
// machine on WebGPU and hit std::bad_alloc on WASM, because the model competed
// with the whole app for memory and ran GPU work on the UI thread. Every working
// HF Space runs the model in a worker. Here the model gets its own memory context
// and the GPU/compute is off the main thread — so we can use WebGPU (model → VRAM,
// which is what lets the bigger models run) with a CPU/WASM fallback.
//
// Message protocol —
//   page → worker:
//     { type:'generate', id, modelId, messages, tools, params:{maxTokens,temperature,topP,topK,frequencyPenalty,seed} }
//     { type:'stop' }                              // interrupt the running generation
//   worker → page:
//     { type:'progress', data:{loaded,total,progress} }   // model download
//     { type:'delta', id, text }                   // one streamed chunk
//     { type:'complete', id, content }             // full generated text, done
//     { type:'error', id, message }

const ESM_URL = 'https://esm.sh/@huggingface/transformers@4';

let _lib = null;                                   // cached imported module
let _tokenizer = null, _model = null, _currentModelId = null;
let _stopping = null;                              // InterruptableStoppingCriteria for the active run

async function lib() {
  if (!_lib) _lib = await import(ESM_URL);
  return _lib;
}

function postProgress(d) {
  if (!d) return;
  self.postMessage({ type: 'progress', data: {
    loaded: d.loaded || 0,
    total: d.total || 0,
    progress: d.progress || (d.total ? d.loaded / d.total : 0),
  } });
}

// Load (and cache) the tokenizer + model. WebGPU first (model → VRAM, fits the
// bigger models, fast); fall back to CPU/WASM for devices without a usable
// WebGPU adapter. Switching models tears down the previous to free memory.
async function ensureModel(modelId) {
  if (_currentModelId === modelId && _model && _tokenizer) return;
  if (_model) { try { await _model.dispose?.(); } catch (_) {} _model = null; _tokenizer = null; _currentModelId = null; }

  const { AutoTokenizer, AutoModelForCausalLM } = await lib();
  const progress_callback = postProgress;

  const tokenizer = await AutoTokenizer.from_pretrained(modelId, { progress_callback });

  let model;
  try {
    model = await AutoModelForCausalLM.from_pretrained(modelId, { dtype: 'q4f16', device: 'webgpu', progress_callback });
  } catch (gpuErr) {
    // No usable WebGPU adapter — fall back to CPU/WASM (q4). Note the WASM heap
    // caps ~2 GB, so big models can still std::bad_alloc here; that's a device
    // limit, not a bug.
    model = await AutoModelForCausalLM.from_pretrained(modelId, { dtype: 'q4', device: 'wasm', progress_callback });
  }

  _tokenizer = tokenizer;
  _model = model;
  _currentModelId = modelId;
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

async function generate(id, payload) {
  const { messages, tools, params } = payload || {};
  const p = params || {};
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
        self.postMessage({ type: 'delta', id, text: txt });
      },
    });
  }

  _stopping = InterruptableStoppingCriteria ? new InterruptableStoppingCriteria() : null;

  const opts = { ...inputs, max_new_tokens: p.maxTokens || 2048, do_sample: true };
  if (streamer) opts.streamer = streamer;
  if (_stopping) opts.stopping_criteria = _stopping;
  if (p.temperature != null) opts.temperature = p.temperature;
  if (p.topP != null) opts.top_p = p.topP;
  if (p.topK != null) opts.top_k = p.topK;
  if (p.frequencyPenalty != null) opts.repetition_penalty = 1 + p.frequencyPenalty;
  if (p.seed != null) opts.seed = p.seed;

  await _model.generate(opts);
  return content;
}

self.addEventListener('message', async (e) => {
  const msg = e.data || {};

  if (msg.type === 'stop') {
    try { _stopping && _stopping.interrupt(); } catch (_) {}
    return;
  }

  if (msg.type !== 'generate') return;
  const { id, modelId } = msg;
  try {
    await ensureModel(modelId);
    const content = await generate(id, msg);
    self.postMessage({ type: 'complete', id, content });
  } catch (err) {
    self.postMessage({ type: 'error', id, message: String((err && err.message) || err) });
  }
});
