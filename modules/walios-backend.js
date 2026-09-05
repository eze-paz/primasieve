// Single source of truth for the walios Python backend.
//
// Consumed by BOTH modules/sandpie-worker.js (run_python + the walios shell tool, via
// importScripts) and /walios/terminal.html (via a <script> tag), so the interactive
// terminal can never drift onto a different CPython than the one the agent runs. It had:
// python -> the old stdlib-only python.wasm, worker ?v=dlopen6, no certifi, no matplotlib.
//
// Plain classic script on purpose — sandpie-worker.js is a classic Worker and cannot
// `import`, so this assigns onto the global instead of exporting.

(function (g) {
  // Bumped with every wali-worker.js deploy.
  // dlopen9: the host no longer silently answers 0 for unimplemented `wali.*` imports.
  // __wasm_thread_spawn now returns EAGAIN so threading.Thread().start() raises
  // RuntimeError instead of trapping the whole interpreter (exit 139).
  const WORKER_V = 'dlopen9';

  // The main CPython. Reactor exec model: its exports are not wrapped in thunks that
  // re-run __wasm_call_ctors, which is what made every cross-module call re-initialise
  // mimalloc and flood stderr (25GB across a 12-package run, ~14x slower imports).
  const MAIN = 'python_cxx.wasm?v=7';

  // Every package bundle, with the mount point it unpacks to.
  const BUNDLES = {
    stdlib:  ['pylib.tar.gz', '/py'],
    ext:     ['walios-ext.tar.gz', '/ext'],
    // certifi (TLS), packaging (micropip's resolver) and _shims/ctypes, which MUST be on
    // the path before stdlib ctypes or pandas fails to import. Always eager: it is ~64ms.
    extras:  ['walios-extras.tar.gz?v=3', '/site-packages'],
    numpy:   ['walios-numpy.tar.gz?v=2', '/site-packages'],
    docs:    ['walios-docs.tar.gz?v=4', '/site-packages'],
    mpl:     ['walios-mpl.tar.gz?v=3', '/site-packages'],
  };

  // Which bundle provides which top-level module, for mount-on-import-miss.
  const LAZY_PKGS = (() => {
    const m = {};
    for (const n of ['numpy', 'pandas', 'dateutil', 'pytz', 'tzdata', 'six', 'msgpack', 'simplejson', 'zlib']) m[n] = BUNDLES.numpy;
    for (const n of ['PIL', 'lxml', 'docx', 'openpyxl', 'pptx', 'reportlab', 'pypdf', 'PyPDF2', 'bs4', 'soupsieve',
                     'fontTools', 'xlsxwriter', 'olefile', 'OleFileIO_PL', 'striprtf', 'chardet', 'charset_normalizer',
                     'et_xmlfile', 'fpdf', 'pdfminer', 'typing_extensions', '_ssl']) m[n] = BUNDLES.docs;
    for (const n of ['matplotlib', 'mpl_toolkits', 'contourpy', 'kiwisolver']) m[n] = BUNDLES.mpl;
    return m;
  })();

  const PY_ENV = {
    PYTHONHOME: '/py',
    PYTHONPATH: '/site-packages/_shims:/py/Lib:/ext:/site-packages',
    PYTHONDONTWRITEBYTECODE: '1',
    MPLBACKEND: 'Agg',
    MPLCONFIGDIR: '/site-packages/_mplcache',      // prebuilt font cache: the in-guest scan costs >600s
    SSL_CERT_FILE: '/site-packages/certifi/cacert.pem',  // default context otherwise loads ZERO CA certs
  };

  g.WALIOS_BACKEND = {
    WORKER_V,
    MAIN,
    BUNDLES,
    LAZY_PKGS,
    PY_ENV,

    // python/python3 must resolve to the SAME binary run_python uses. `pydl` is kept as a
    // historical alias so existing terminal muscle memory still works.
    manifest(busybox) {
      return { busybox, sh: busybox, ash: busybox, hush: busybox,
               python: MAIN, python3: MAIN, pydl: MAIN };
    },

    // Mount strategy differs by host, and only because of capability:
    //  - 'repl'     : the warm interpreter installs a meta_path finder that can call OUT to
    //                 the host to mount a bundle on an import miss, so heavy bundles wait.
    //  - 'terminal' : an interactive `python` has no host RPC channel, so nothing could
    //                 service a lazy mount; everything is unpacked up front instead.
    // Same binary, same packages, same env either way.
    eagerTars(mode) {
      const base = [BUNDLES.stdlib, BUNDLES.ext, BUNDLES.extras];
      if (mode === 'terminal') base.push(BUNDLES.numpy, BUNDLES.docs, BUNDLES.mpl);
      return { 'python.wasm': [BUNDLES.stdlib], [MAIN]: base };
    },

    env(mode) {
      const e = Object.assign({}, PY_ENV);
      if (mode === 'repl') {
        e.SANDPIE_ASYNCIO = '1';                          // the browser worker has JSPI, so asyncio works
        e.SANDPIE_LAZY_PKGS = JSON.stringify(LAZY_PKGS);
      }
      return e;
    },
  };
})(typeof self !== 'undefined' ? self : globalThis);
