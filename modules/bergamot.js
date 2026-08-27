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

  // Structure-preserving translation for a rich markdown string. Bergamot is a
  // sentence-level NMT and would shred table grids (| --- |), so we translate ONLY
  // the natural-language fragments (prose, header text, list-item text, table cell
  // text) in ONE batch and leave every structural token untouched: table pipes and
  // separator rows, fenced code blocks, numbers/symbols, and leading markers.
  var _numCell = /^[\s\d.,%+\-−$€£¥():/xX~]*$/;   // numeric/symbol-only cell → keep
  var _tableSep = /^\s*\|?[\s:|\-—−]+\|?\s*$/;               // | --- | --- | row
  // A cell "reads like prose" when it contains a word that BEGINS with a lowercase
  // letter (a function word or verb: "on", "the", "passed"). All-Title-Case /
  // ALLCAPS / symbol-only cells are names, tickers or codes ("Dow Jones", "S&P 500")
  // that this sentence-level NMT mangles on such short fragments — so DATA cells that
  // fail this test pass through untouched. Full-sentence data cells always pass it.
  function _hasLowerWord(t) {
    var w = String(t).split(/\s+/);
    for (var i = 0; i < w.length; i++) {
      var tok = w[i].replace(/^[^\p{L}]+/u, '');   // strip leading punctuation
      if (tok && /^\p{Ll}/u.test(tok)) return true;
    }
    return false;
  }
  // Should a DATA cell be translated? A SINGLE word is translated when it holds any
  // lowercase letter — this catches status labels ("Pending"→"Pendent", "Active",
  // "Completed") which are common words the NMT knows, while single proper nouns
  // (Nasdaq, Google, Tesla) are copied through unchanged by the NMT anyway, and
  // ALLCAPS tickers ("AAPL") / symbol-only cells are left alone. A MULTI-word cell
  // is translated only when it reads like prose (_hasLowerWord); an all-Title-case
  // multi-word cell is a proper noun ("Dow Jones", "New York") and is kept as-is.
  function _translatableCell(t) {
    var words = String(t).trim().split(/\s+/);
    if (words.length === 1) return /\p{Ll}/u.test(t);
    return _hasLowerWord(t);
  }
  function _splitPrefix(line) {
    var m = line.match(/^(\s*(?:#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+)?)([\s\S]*)$/);
    return m ? [m[1], m[2]] : ['', line];
  }
  // True when the text carries structure the whole-string NMT would shred — a
  // markdown table (a |---|---| separator row) or a fenced code block. Callers use
  // this to switch from the default translate() to the structure-preserving
  // translateMarkdown() only when needed (plain prose stays on the better default).
  function isStructured(text) {
    if (typeof text !== 'string' || !text) return false;
    if (/(^|\n)\s*(```|~~~)/.test(text)) return true;
    var ls = text.split('\n');
    for (var i = 0; i < ls.length; i++) {
      var l = ls[i];
      if (l.indexOf('|') !== -1 && l.indexOf('-') !== -1 && /^\s*\|?[\s:|\-—−]+\|?\s*$/.test(l)) return true;
    }
    return false;
  }
  async function translateMarkdown(text, code) {
    code = baseCode(code);
    if (!code || code === 'en') return text;
    if (typeof text !== 'string' || !text.trim()) return text;
    var lines = text.split('\n');
    var frags = [];             // natural-language fragments to translate
    var plan = [];              // per line: how to reassemble
    var inFence = false;
    // A table row is a HEADER iff the next non-blank line is a separator (|---|).
    // Header cells are labels ("Index", "Price") and always translate. DATA cells
    // translate ONLY when they read like prose (_hasLowerWord) — full sentences get
    // translated, but proper-noun / ticker / code fragments ("Dow Jones", "S&P 500")
    // pass through untouched so the NMT can't mangle them ("Pel·lícules Dow Jones").
    var headerLines = {};
    for (var hi = 0; hi < lines.length; hi++) {
      var hl = lines[hi];
      if (hl.indexOf('|') === -1 || (_tableSep.test(hl) && hl.indexOf('-') !== -1)) continue;
      for (var hj = hi + 1; hj < lines.length; hj++) {
        if (!lines[hj].trim()) continue;
        if (lines[hj].indexOf('|') !== -1 && _tableSep.test(lines[hj]) && lines[hj].indexOf('-') !== -1) headerLines[hi] = true;
        break;
      }
    }
    for (var li = 0; li < lines.length; li++) {
      var line = lines[li];
      if (/^\s*(```|~~~)/.test(line)) { inFence = !inFence; plan.push({ k: 'raw', line: line }); continue; }
      if (inFence || !line.trim()) { plan.push({ k: 'raw', line: line }); continue; }
      if (line.indexOf('|') !== -1 && _tableSep.test(line) && line.indexOf('-') !== -1) { plan.push({ k: 'raw', line: line }); continue; }
      if (line.indexOf('|') !== -1) {
        var isHdr = !!headerLines[li];
        var cells = line.split('|');
        var refs = cells.map(function (cell) {
          var t = cell.trim();
          if (t && !_numCell.test(t) && (isHdr || _translatableCell(t))) { frags.push(t); return frags.length - 1; }
          return -1;
        });
        plan.push({ k: 'row', cells: cells, refs: refs });
        continue;
      }
      var pb = _splitPrefix(line);
      if (pb[1].trim()) { frags.push(pb[1]); plan.push({ k: 'prose', prefix: pb[0], ref: frags.length - 1 }); }
      else plan.push({ k: 'raw', line: line });
    }
    if (!frags.length) return text;
    var tr = await translate(frags, code);
    var out = plan.map(function (p) {
      if (p.k === 'raw') return p.line;
      if (p.k === 'prose') return p.prefix + (tr[p.ref] || frags[p.ref]);
      // table row: re-emit cells, keeping each cell's surrounding whitespace
      return p.cells.map(function (cell, ci) {
        if (p.refs[ci] < 0) return cell;
        var lead = (cell.match(/^\s*/) || [''])[0];
        var trail = (cell.match(/\s*$/) || [''])[0];
        return lead + (tr[p.refs[ci]] || cell.trim()) + trail;
      }).join('|');
    });
    return out.join('\n');
  }

  // Fully warm a language ahead of first use (call on idle): load the WASM runtime,
  // download the pack (OPFS-cached), AND build the TranslationModel — so the first
  // real translate() is instant (~50ms) and its result lands before a re-render can
  // discard it. No-op for en / unsupported / unconfigured. Never throws.
  async function prefetch(code) {
    try {
      code = baseCode(code);
      if (!code || code === 'en' || !supports(code) || !S.wasmUrl || !S.modelBase) return false;
      await ensureInit();
      await _model(code);   // fetch (OPFS-cached) + build, held in the model cache
      return true;
    } catch (_) { return false; }
  }

  g.Bergamot = { configure: configure, translate: translate, translateMarkdown: translateMarkdown, isStructured: isStructured, prefetch: prefetch, supports: supports, SUPPORTED: SUPPORTED };
})(typeof self !== 'undefined' ? self : this);
