
// SandpieWebLLM - WebLLM integration for sandpie
// This module wraps the @mlc-ai/web-llm library

import * as webllm from 'https://cdn.jsdelivr.net/npm/@mlc-ai/web-llm@0.2.83/+esm';

// Default models list - curated models that work well with WebLLM
export const DEFAULT_MODELS = [
  { id: 'Llama-3.1-8B-Instruct-q4f16_1-MLC', label: 'Llama 3.1 8B Instruct (q4f16)' },
  { id: 'Llama-3.1-8B-Instruct-q4f32_1-MLC', label: 'Llama 3.1 8B Instruct (q4f32)' },
  { id: 'Hermes-3-Llama-3.1-8B-q4f16_1-MLC', label: 'Hermes 3 Llama 3.1 8B (q4f16)' },
  { id: 'Hermes-3-Llama-3.1-8B-q4f32_1-MLC', label: 'Hermes 3 Llama 3.1 8B (q4f32)' },
  { id: 'Hermes-2-Pro-Llama-3-8B-q4f16_1-MLC', label: 'Hermes 2 Pro Llama 3 8B (q4f16)' },
  { id: 'Hermes-2-Pro-Llama-3-8B-q4f32_1-MLC', label: 'Hermes 2 Pro Llama 3 8B (q4f32)' },
  { id: 'Hermes-2-Pro-Mistral-7B-q4f16_1-MLC', label: 'Hermes 2 Pro Mistral 7B (q4f16)' },
  { id: 'Qwen2.5-7B-Instruct-q4f16_1-MLC', label: 'Qwen 2.5 7B Instruct (q4f16)' },
  { id: 'Qwen2.5-3B-Instruct-q4f16_1-MLC', label: 'Qwen 2.5 3B Instruct (q4f16)' },
  { id: 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC', label: 'Qwen 2.5 1.5B Instruct (q4f16)' },
  { id: 'Gemma-2-9B-it-q4f16_1-MLC', label: 'Gemma 2 9B (q4f16)' },
  { id: 'Phi-3.5-mini-instruct-q4f16_1-MLC', label: 'Phi 3.5 Mini (q4f16)' },
];

// Engine cache - reuse the same engine across requests
let engine = null;
let currentModel = null;

// Initialize or get the WebLLM engine
async function getEngine(modelId, initProgressCallback) {
  if (engine && currentModel === modelId) {
    return engine;
  }

  // Unload previous model if different
  if (engine && currentModel !== modelId) {
    await engine.unload();
    engine = null;
  }

  // Create new engine
  engine = new webllm.CreateMLCEngine(
    modelId,
    { initProgressCallback: initProgressCallback }
  );
  currentModel = modelId;

  return engine;
}

// Stream a round of chat completion
export async function streamRound({ model, messages, tools, signal, onProgress, onDelta }) {
  const initProgressCallback = (report) => {
    onProgress(report);
  };

  const eng = await getEngine(model, initProgressCallback);

  const messagesArray = messages.map(m => ({
    role: m.role,
    content: m.content
  }));

  const request = {
    messages: messagesArray,
    stream: true,
  };

  // Only add tools if the model supports them and tools are provided
  if (tools && tools.length > 0) {
    request.tools = tools;
  }

  const chunks = [];
  const toolCalls = [];

  const chatCompletion = await eng.chat.completions.create(request);

  let content = '';

  for await (const chunk of chatCompletion) {
    if (signal && signal.aborted) {
      await eng.interruptGenerate();
      throw new DOMException('Aborted', 'AbortError');
    }

    const delta = chunk.choices[0]?.delta;

    if (delta?.content) {
      content += delta.content;
      onDelta({ content: delta.content });
    }

    if (delta?.tool_calls) {
      for (const tc of delta.tool_calls) {
        const existing = toolCalls.find(t => t.index === tc.index);
        if (existing) {
          if (tc.function?.name) existing.function.name = tc.function.name;
          if (tc.function?.arguments) existing.function.arguments += tc.function.arguments;
        } else {
          toolCalls.push({
            index: tc.index,
            id: tc.id,
            type: tc.type,
            function: {
              name: tc.function?.name || '',
              arguments: tc.function?.arguments || ''
            }
          });
        }
        onDelta({ tool_calls: [tc] });
      }
    }
  }

  return {
    content,
    tool_calls: toolCalls
  };
}

// Export the SandpieWebLLM object
const SandpieWebLLM = {
  DEFAULT_MODELS,
  streamRound,
};

export default SandpieWebLLM;
