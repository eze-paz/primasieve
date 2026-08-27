/* Bergamot on-device translator (classic script — works on the page and, via
   importScripts, inside sandpie-worker.js). English is canonical; this replaces
   the gemini localizer. Fetches the WASM runtime + a per-language model pack
   same-origin, caches each pack in OPFS (download once), and exposes an
   array-in/array-out translate(). Fail-CLOSED to the caller (throws) so each
   call site keeps its existing try/catch -> English on any error. */
(function (g) {
  var S = { wasmUrl: null, runtimeUrl: null, modelBase: null };
  var _svc = null, _M = null, _initP = null;
  var _models = new Map();
  // en->X packs Firefox/Bergamot publishes (target-language codes).
  var SUPPORTED = new Set(['ca','es','fr','de','it','pt','nl','pl','ru','uk','cs','sv',
    'da','fi','el','ro','bg','hu','et','lt','lv','sl','sk','hr','sq','bs','id','ms',
    'vi','tr','ar','he','fa','hi','bn','ta','te','ml','kn','gu','az','be','ja','ko',
    'zh','th','nb','nn','gl','eu']);
  function baseCode(c) { return String(c || '').toLowerCase().split(/[-_]/)[0]; }
  function supports(c) { return SUPPORTED.has(baseCode(c)); }

  function configure(cfg) {
    if (cfg && cfg.wasmUrl) S.wasmUrl = cfg.wasmUrl;
    if (cfg && cfg.runtimeUrl) S.runtimeUrl = cfg.runtimeUrl;
    if (cfg && cfg.modelBase) S.modelBase = cfg.modelBase;
  }

  async function _opfsDir() {
    var root = await navigator.storage.getDirectory();
    return await root.getDirectoryHandle('bergamot', { create: true });
  }
  async function _cacheGet(name) {
    try { var d = await _opfsDir(); var fh = await d.getFileHandle(name); var f = await fh.getFile();
      return new Uint8Array(await f.arrayBuffer()); } catch (_) { return null; }
  }
  async function _cachePut(name, bytes) {
    try { var d = await _opfsDir(); var fh = await d.getFileHandle(name, { create: true });
      var w = await fh.createWritable(); await w.write(bytes); await w.close(); } catch (_) {}
  }
  async function _fetchCached(url, cacheName) {
    var c = await _cacheGet(cacheName); if (c && c.length) return c;
    var r = await fetch(url); if (!r.ok) throw new Error('fetch ' + url + ' -> ' + r.status);
    var b = new Uint8Array(await r.arrayBuffer());
    await _cachePut(cacheName, b); return b;
  }

  function ensureInit() {
    if (_svc) return Promise.resolve();
    if (_initP) return _initP;
    if (!S.wasmUrl || !S.runtimeUrl) return Promise.reject(new Error('bergamot: not configured'));
    _initP = (async function () {
      var pair = await Promise.all([
        fetch(S.wasmUrl).then(function (r) { if (!r.ok) throw new Error('wasm ' + r.status); return r.arrayBuffer(); }),
        fetch(S.runtimeUrl).then(function (r) { if (!r.ok) throw new Error('runtime ' + r.status); return r.text(); })
      ]);
      var wasmBinary = pair[0], runtimeText = pair[1];
      await new Promise(function (resolve, reject) {
        var Module = { wasmBinary: wasmBinary, onRuntimeInitialized: function () {
          try { _svc = new Module.BlockingService({ cacheSize: 0 }); _M = Module; resolve(); }
          catch (e) { reject(e); }
        } };
        try { (new Function('Module', runtimeText))(Module); } catch (e) { reject(e); }
      });
    })();
    return _initP;
  }

  function _al(buf, align) { var m = new _M.AlignedMemory(buf.byteLength, align); m.getByteArrayView().set(buf); return m; }

  async function _model(code) {
    if (_models.has(code)) return _models.get(code);
    var pair = 'en' + code;
    var base = S.modelBase.replace(/\/?$/, '/') + pair + '/';
    var m = await Promise.all([
      _fetchCached(base + 'model.' + pair + '.intgemm.alphas.bin', pair + '.model'),
      _fetchCached(base + 'lex.50.50.' + pair + '.s2t.bin', pair + '.lex'),
      _fetchCached(base + 'vocab.' + pair + '.spm', pair + '.vocab')
    ]);
    var vocabs = new _M.AlignedMemoryList(); vocabs.push_back(_al(m[2], 64));
    var cfg = ['beam-size: 1','normalize: 1.0','word-penalty: 0','max-length-break: 128',
      'mini-batch-words: 1024','workspace: 128','max-length-factor: 2.0','skip-cost: true',
      'gemm-precision: int8shiftAll'].join('\n');
    var tm = new _M.TranslationModel(cfg, _al(m[0], 256), _al(m[1], 64), vocabs, null);
    _models.set(code, tm); return tm;
  }

  // texts: string[]; code: BCP-47/ISO target. Returns same-length array; blank
  // and non-string entries pass through untouched.
  async function translate(texts, code) {
    if (!Array.isArray(texts) || !texts.length) return texts;
    code = baseCode(code);
    // en->en (or no target): English is canonical — nothing to translate. Return
    // untouched WITHOUT loading the engine or throwing (an expected no-op, not an error).
    if (!code || code === 'en') return texts;
    if (!supports(code)) throw new Error('bergamot: unsupported target ' + code);
    await ensureInit();
    if (!_svc) throw new Error('bergamot: runtime unavailable');
    var tm = await _model(code);
    var input = new _M.VectorString(), idx = [];
    texts.forEach(function (t, i) { if (typeof t === 'string' && t.trim()) { idx.push(i); input.push_back(t); } });
    if (!idx.length) { input.delete(); return texts; }
    var vo = new _M.VectorResponseOptions();
    for (var i = 0; i < idx.length; i++) vo.push_back({ qualityScores: false, alignment: false, html: false });
    var out = _svc.translate(tm, input, vo);
    var res = texts.slice();
    for (var k = 0; k < idx.length; k++) res[idx[k]] = out.get(k).getTranslatedText().trim();
    input.delete(); vo.delete(); out.delete();
    return res;
  }

  // Warm a language pack into OPFS ahead of first use (call on idle). Downloads
  // the ~30MB model + lex + vocab into the cache but does NOT build the model, so
  // the first real translate() skips the network. No-op for en / unsupported /
  // unconfigured. Never throws.
  async function prefetch(code) {
    try {
      code = baseCode(code);
      if (!code || code === 'en' || !supports(code) || !S.modelBase) return false;
      var pair = 'en' + code;
      var base = S.modelBase.replace(/\/?$/, '/') + pair + '/';
      await Promise.all([
        _fetchCached(base + 'model.' + pair + '.intgemm.alphas.bin', pair + '.model'),
        _fetchCached(base + 'lex.50.50.' + pair + '.s2t.bin', pair + '.lex'),
        _fetchCached(base + 'vocab.' + pair + '.spm', pair + '.vocab')
      ]);
      return true;
    } catch (_) { return false; }
  }

  g.Bergamot = { configure: configure, translate: translate, prefetch: prefetch, supports: supports, SUPPORTED: SUPPORTED };
})(typeof self !== 'undefined' ? self : this);
