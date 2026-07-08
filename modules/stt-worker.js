// sandpie/modules/stt-worker.js — on-device speech-to-text (Whisper) inside a
// dedicated Web Worker. Loaded as a MODULE worker:
//   new Worker('modules/stt-worker.js', { type: 'module' })
//
// WHY A WORKER: same reason as transformersjs-worker.js — Transformers.js model
// load + inference must NOT run on the page main thread (WebGPU crashed the
// machine, WASM hit std::bad_alloc when the model fought the UI for memory). In a
// worker the model gets its own memory context and the compute is off the main
// thread. WebGPU first (model → VRAM, fast); CPU/WASM fallback for devices with
// no usable WebGPU adapter.
//
// FULLY ON-DEVICE: the microphone audio NEVER leaves the tab. The only network
// traffic is the one-time model download from the HF CDN (then cached by the
// browser). This is what lets sandpie keep its "nothing escapes the tab" promise
// while still offering speech input.
//
// Message protocol —
//   page → worker:
//     { type:'load', modelId, dtype? }                          // preload / switch model
//     { type:'transcribe', id, modelId, audio:Float32Array, lang?, dtype? }  // audio = 16kHz mono
//   worker → page:
//     { type:'progress', data:{loaded,total,progress} }         // model download
//     { type:'ready', modelId }                                 // model loaded + warmed
//     { type:'partial', id, text }                              // streaming transcript (per token)
//     { type:'result', id, text }                               // transcript, done
//     { type:'error', id?, message }

const ESM_URL = 'https://esm.sh/@huggingface/transformers@4';

let _lib = null;                 // cached imported module
let _transcriber = null;         // the ASR pipeline
let _currentModelId = null;
let _device = null;              // 'webgpu' | 'wasm' — which backend actually loaded

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

// Load (and cache) the ASR pipeline. WebGPU first; CPU/WASM fallback. Switching
// models disposes the previous one to free memory. On WebGPU we keep the encoder
// at fp32 (accuracy) and quantise the decoder to q4 (size/speed) — the combo the
// official whisper-webgpu example uses; on WASM we go q8 to stay under the heap.
async function ensureModel(modelId, dtype) {
  if (_currentModelId === modelId && _transcriber) return;
  if (_transcriber) { try { await _transcriber.dispose?.(); } catch (_) {} _transcriber = null; _currentModelId = null; }

  const { pipeline } = await lib();
  const progress_callback = postProgress;

  let transcriber = null;
  // WebGPU dtype ladder. fp16 encoder is ~2× faster than fp32 on adapters with
  // f16 (Iris Xe gen-12, most modern GPUs) and halves memory bandwidth — the
  // encoder is a FIXED ~30s cost per call, so this is the single biggest speed
  // lever. Fall back to fp32 if the fp16 shaders fail to compile on this adapter.
  const gpuDtypes = dtype ? [dtype] : [
    { encoder_model: 'fp16', decoder_model_merged: 'q4' },
    { encoder_model: 'fp32', decoder_model_merged: 'q4' },
  ];
  for (const dt of gpuDtypes) {
    try {
      transcriber = await pipeline('automatic-speech-recognition', modelId, { device: 'webgpu', dtype: dt, progress_callback });
      _device = 'webgpu';
      break;
    } catch (gpuErr) {
      console.warn('[stt-worker] webgpu dtype failed:', JSON.stringify(dt), (gpuErr && gpuErr.message) || gpuErr);
    }
  }
  if (!transcriber) {
    // No usable WebGPU adapter — CPU/WASM fallback (q8 to fit the ~2 GB heap).
    // This path is MUCH slower; the device is reported on 'ready' so the UI/user
    // can tell they're on CPU (the usual cause of "STT is really slow").
    transcriber = await pipeline('automatic-speech-recognition', modelId, { device: 'wasm', dtype: 'q8', progress_callback });
    _device = 'wasm';
  }
  console.log('[stt-worker] model ready on', _device);

  _transcriber = transcriber;
  _currentModelId = modelId;

  // WARMUP — compile the WebGPU shaders with a short silent buffer FIRST, so the
  // first real transcription doesn't compile every shader AND run inference in
  // one sustained GPU burst (which can trip the OS GPU watchdog → driver reset →
  // whole-machine freeze). A throwaway 1s run compiles the shaders cheaply; the
  // real run reuses them. Best-effort — mirrors transformersjs-worker.js.
  try {
    const silent = new Float32Array(16000); // 1s of silence @16kHz
    await _transcriber(silent, { chunk_length_s: 30, return_timestamps: false });
  } catch (err) {
    console.warn('[stt-worker] warmup failed (continuing):', (err && err.message) || err);
  }
}

// Whisper's multilingual checkpoints want a full language NAME ('english'), or
// the option omitted entirely to auto-detect. (English-only ".en" checkpoints are
// deliberately kept out of the page-side catalog so passing a language is always
// valid here.)
const LANG_NAMES = {
  auto: null, en: 'english', es: 'spanish', ca: 'catalan', fr: 'french', de: 'german',
  it: 'italian', pt: 'portuguese', nl: 'dutch', ru: 'russian', zh: 'chinese',
  ja: 'japanese', ko: 'korean', ar: 'arabic', hi: 'hindi',
};

async function transcribe(id, audio, lang) {
  if (!_transcriber) throw new Error('model not loaded');
  // chunk_length_s + stride lets whisper handle utterances longer than its 30s
  // receptive field by sliding a window with overlap and stitching the text.
  const opts = { chunk_length_s: 30, stride_length_s: 5, return_timestamps: false, task: 'transcribe' };
  const langName = LANG_NAMES[lang || 'auto'];
  if (langName) opts.language = langName;

  // Token-level streaming: emit partial text as the decoder produces each token,
  // so the composer fills in smoothly instead of jumping only when the whole
  // window finishes decoding. Best-effort — if the runtime ignores `streamer`
  // (older builds), we simply fall back to the final 'result' below. The page
  // guards partials to only move forward, so a re-transcribe never rewinds text.
  try {
    const { TextStreamer } = await lib();
    if (TextStreamer && _transcriber.tokenizer) {
      let streamed = '';
      opts.streamer = new TextStreamer(_transcriber.tokenizer, {
        skip_prompt: true,
        skip_special_tokens: true,
        callback_function: (t) => {
          if (!t) return;
          streamed += t;
          self.postMessage({ type: 'partial', id, text: streamed.trim() });
        },
      });
    }
  } catch (_) { /* streaming optional */ }

  const out = await _transcriber(audio, opts);
  let text = '';
  if (out && typeof out.text === 'string') text = out.text;
  else if (Array.isArray(out)) text = out.map(o => (o && o.text) || '').join(' ');
  self.postMessage({ type: 'result', id, text: text.trim() });
}

self.addEventListener('message', async (e) => {
  const msg = e.data || {};
  try {
    if (msg.type === 'load') {
      await ensureModel(msg.modelId, msg.dtype);
      self.postMessage({ type: 'ready', modelId: msg.modelId, device: _device });   // always reply to a load, even when already cached
      return;
    }
    if (msg.type === 'transcribe') {
      await ensureModel(msg.modelId, msg.dtype);   // no-op if already loaded
      await transcribe(msg.id, msg.audio, msg.lang);
      return;
    }
  } catch (err) {
    self.postMessage({ type: 'error', id: msg.id, message: String((err && err.message) || err) });
  }
});
