// sandpie/modules/stt-worker.js — on-device speech-to-text (Whisper) worker.
//
// Loaded as a MODULE worker: new Worker('modules/stt-worker.js', { type:'module' })
//
// WHY A WORKER: Transformers.js model load + inference must NOT run on the page
// main thread (WebGPU can destabilize the UI; WASM fights the UI for memory).
// In a dedicated worker the model gets its own memory context and compute is
// off the main thread.
//
// FULLY ON-DEVICE: microphone audio NEVER leaves the tab. The only network
// traffic is the one-time model download from the HF CDN (cached by the
// browser afterwards).
//
// Message protocol —
//   page → worker:
//     { type:'load', modelId, dtype? }                       // preload / switch
//     { type:'transcribe', id, modelId, audio:Float32Array, lang?, dtype? }  // 16 kHz mono
//   worker → page:
//     { type:'progress', data:{loaded,total,progress} }
//     { type:'ready', modelId }
//     { type:'result', id, text }
//     { type:'error', id?, message }

const ESM_URL = 'https://esm.sh/@huggingface/transformers@3';

let _lib = null;                 // cached imported module
let _transcriber = null;         // ASR pipeline
let _currentModelId = null;

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

// Load (and cache) the ASR pipeline. WebGPU first (encoder fp32 for accuracy,
// decoder q4 for size/speed — the combo the official whisper-webgpu example
// uses); CPU/WASM fallback with q8 to stay under the heap. Switching models
// disposes the previous one to free memory.
async function ensureModel(modelId, dtype) {
  if (_currentModelId === modelId && _transcriber) return;
  if (_transcriber) { try { await _transcriber.dispose?.(); } catch (_) {} _transcriber = null; _currentModelId = null; }

  const { pipeline } = await lib();
  const progress_callback = postProgress;

  let transcriber;
  try {
    transcriber = await pipeline('automatic-speech-recognition', modelId, {
      device: 'webgpu',
      dtype: dtype || { encoder_model: 'fp32', decoder_model_merged: 'q4' },
      progress_callback,
    });
  } catch (e) {
    console.warn('[stt-worker] webgpu unavailable, falling back to wasm:', e && e.message);
    transcriber = await pipeline('automatic-speech-recognition', modelId, {
      device: 'wasm',
      dtype: 'q8',
      progress_callback,
    });
  }
  _transcriber = transcriber;
  _currentModelId = modelId;
  self.postMessage({ type: 'ready', modelId });
}

// Whisper generates hallucinated repeats on silence; trim them here.
function cleanText(t) {
  return (t || '').replace(/\s+/g, ' ').trim();
}

self.onmessage = async (msg) => {
  const d = msg.data || {};
  try {
    if (d.type === 'load') {
      await ensureModel(d.modelId, d.dtype);
      return;
    }
    if (d.type === 'transcribe') {
      await ensureModel(d.modelId, d.dtype);   // no-op if already loaded
      const out = await _transcriber(d.audio, {
        language: d.lang && d.lang !== 'auto' ? d.lang : undefined,
        task: 'transcribe',
        chunk_length_s: 30,
        stride_length_s: 5,
        return_timestamps: false,
      });
      self.postMessage({ type: 'result', id: d.id, text: cleanText(out && out.text) });
      return;
    }
  } catch (e) {
    self.postMessage({ type: 'error', id: d.id, message: (e && e.message) || String(e) });
  }
};
