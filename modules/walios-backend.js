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
  // dlopen10: one armed itimer had TWO delivery sources (a polled deadline and a real
  // setTimeout) and neither cancelled the other, so a ONE-SHOT setitimer/alarm fired
  // SIGALRM twice -- measured 2 handler entries where 1 was expected. In Python the
  // second delivery re-entered the handler inside the except clause of the first and
  // went uncaught, which is exactly the _set_timeout pattern.
  // dlopen11: fork returns ENOSYS on a binary without Asyncify (CPython). It used to
  // hand back a pid and never run the child, so subprocess/os.popen waited out the
  // whole timeout; now they raise OSError immediately.
  const WORKER_V = 'dlopen11';

  // The main CPython. Reactor exec model: its exports are not wrapped in thunks that
  // re-run __wasm_call_ctors, which is what made every cross-module call re-initialise
  // mimalloc and flood stderr (25GB across a 12-package run, ~14x slower imports).
  const MAIN = 'python_cxx.wasm?v=7';

  // Every package bundle, with the mount point it unpacks to.
  const BUNDLES = {
    stdlib:  ['pylib.tar.gz', '/py'],
    ext:     ['walios-ext.tar.gz', '/ext'],
    // certifi (TLS), packaging (micropip's resolver) and _shims/ctypes, which MUST be on
    // the path before stdlib ctypes or pandas fails to import. Also requests + urllib3 +
    // idna + charset_normalizer, and the two C extensions they need: zlib (which lived in
    // the 16MB numpy bundle) and _ssl (in the 11MB docs bundle). `import requests` used to
    // fail outright or drag a whole heavy bundle in for one HTTP call. Eager, ~2.4MB gz,
    // paid once per interpreter boot.
    extras:  ['walios-extras.tar.gz?v=4', '/site-packages'],
    numpy:   ['walios-numpy.tar.gz?v=3', '/site-packages'],
    docs:    ['walios-docs.tar.gz?v=5', '/site-packages'],
    mpl:     ['walios-mpl.tar.gz?v=3', '/site-packages'],
  };

  // Which bundle provides which top-level module, for mount-on-import-miss.
  const LAZY_PKGS = (() => {
    const m = {};
    for (const n of ['numpy', 'pandas', 'dateutil', 'pytz', 'tzdata', 'six', 'msgpack', 'simplejson']) m[n] = BUNDLES.numpy;
    for (const n of ['PIL', 'lxml', 'docx', 'openpyxl', 'pptx', 'reportlab', 'pypdf', 'PyPDF2', 'bs4', 'soupsieve',
                     'fontTools', 'xlsxwriter', 'olefile', 'OleFileIO_PL', 'striprtf', 'chardet', 'charset_normalizer',
                     'et_xmlfile', 'fpdf', 'pdfminer', 'typing_extensions']) m[n] = BUNDLES.docs;
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

    // ONE mount strategy for every host. It used to fork: 'terminal' unpacked all six
    // bundles on the first `python` because an interactive shell had nothing to service
    // a lazy mount, while 'repl'/'tool' unpacked three. That fork is what let the walios()
    // tool ship with the lazy list and NO mount channel, so numpy/pandas/PIL/docx simply
    // did not exist there. Every host now carries hostChannel() below, so every host can
    // mount on demand and the mode argument is kept only so old callers keep working.
    eagerTars(_mode) {
      return { 'python.wasm': [BUNDLES.stdlib], [MAIN]: [BUNDLES.stdlib, BUNDLES.ext, BUNDLES.extras] };
    },

    env(_mode) {
      const e = Object.assign({}, PY_ENV);
      e.SANDPIE_ASYNCIO = '1';                            // the browser worker has JSPI, so asyncio works
      e.SANDPIE_LAZY_PKGS = JSON.stringify(LAZY_PKGS);
      return e;
    },

    // Is JSPI here? walios' blocking syscalls are WebAssembly.Suspending imports, so
    // without it the guest traps rather than degrading. Callers pass `jspi: WB.jspi()`
    // so a browser without it takes the synchronous path instead of dying.
    jspi() {
      return typeof WebAssembly !== 'undefined'
          && typeof WebAssembly.Suspending === 'function'
          && typeof WebAssembly.promising === 'function';
    },

    // Blocking stdin for the SYNCHRONOUS path.
    //
    // Without JSPI the guest cannot await a postMessage, so `{t:'stdin'}` is useless to
    // it: a read on fd 0 returns EOF immediately and the warm REPL exits the instant it
    // starts (measured — "guest exited 0" in 5s). wali-worker.js has always had the
    // receiving half of the fix — readStdin() parks on Atomics.wait against a
    // SharedArrayBuffer installed by a 'stdin-sab' message — but NO host ever sent that
    // message, so the whole mechanism was dead code. This is the writing half.
    //
    // Protocol (ctl = Int32Array(sab,0,4), data = Uint8Array(sab,16)):
    //   ctl[0]  0 = empty / host may write, 1 = data ready, 2 = EOF
    //   ctl[1]  byte count in data
    // The guest drains, sets ctl[0] back to 0 and notifies; we wait for that before the
    // next chunk. Never Atomics.wait here — a host may be on the main thread, where it
    // is disallowed — so yield to the event loop instead.
    stdinBridge(worker, capacity) {
      let sab;
      try { sab = new SharedArrayBuffer(16 + (capacity || (1 << 20))); }
      catch (_) { return null; }                       // no cross-origin isolation
      const ctl = new Int32Array(sab, 0, 4), data = new Uint8Array(sab, 16);
      try { worker.postMessage({ t: 'stdin-sab', sab }); } catch (_) { return null; }
      const enc = new TextEncoder();
      return {
        async write(str) {
          const b = enc.encode(str);
          for (let off = 0; off < b.length;) {
            while (Atomics.load(ctl, 0) !== 0) await new Promise((r) => setTimeout(r, 0));
            const n = Math.min(b.length - off, data.length);
            data.set(b.subarray(off, off + n), 0);
            Atomics.store(ctl, 1, n);
            Atomics.store(ctl, 0, 1);
            Atomics.notify(ctl, 0);
            off += n;
          }
        },
        eof() { Atomics.store(ctl, 0, 2); Atomics.notify(ctl, 0); },
      };
    },

    // The guest->host frame channel, shared by the walios() tool and terminal.html so
    // there is one implementation to debug rather than two that drift.
    //
    // Frames ride fd 1 as \x02<base64 json>\x03. Under a pty that is also the user's
    // screen, which is workable in both directions but for one wrinkle measured here:
    // the pty ECHOES the reply we write to stdin straight back into the output, so the
    // base64 line lands on screen. We know the exact bytes we sent, so we drop the first
    // occurrence of each. Without that a terminal user sees a line of base64 every time
    // a package is mounted.
    //
    //   worker    the Worker running wali-worker.js
    //   onScreen  called with everything that is NOT a frame (write it to the terminal)
    //   onCall    optional, for ops other than 'mount'; returns a promise of the reply
    //   onMountMs optional, told how long a mount took so a caller can extend a deadline
    //   stdin     optional stdinBridge(); when given, replies go through the SAB as well
    //             as postMessage, so the same channel works with and without JSPI
    hostChannel({ worker, onScreen, onCall, onMountMs, stdin }) {
      const STX = String.fromCharCode(2), ETX = String.fromCharCode(3);
      const enc = (str) => {
        const b = new TextEncoder().encode(str);
        let out = '';
        for (let i = 0; i < b.length; i += 0x8000) out += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
        return btoa(out);
      };
      const dec = (x) => new TextDecoder().decode(Uint8Array.from(atob(x), (c) => c.charCodeAt(0)));
      let pend = '';
      const echoes = [];                 // reply payloads we expect the pty to echo back
      const mounts = [];                 // in-flight mounts, awaiting 'tar-mounted'
      const reply = (f, o) => {
        const payload = enc(JSON.stringify(Object.assign({ t: 'reply', id: f.id }, o)));
        echoes.push(payload);
        // The JSPI guest reads postMessage'd chunks; the synchronous guest is parked in
        // Atomics.wait and only ever sees the SAB. Feed both — whichever path this guest
        // is on, exactly one of them is listening.
        try { worker.postMessage({ t: 'stdin', data: payload + '\n' }); } catch (_) {}
        if (stdin) { try { stdin.write(payload + '\n'); } catch (_) {} }
      };
      // Strip our own echoed replies before anything reaches the screen.
      const emit = (text) => {
        if (!text) return;
        for (let i = 0; i < echoes.length; i++) {
          const at = text.indexOf(echoes[i]);
          if (at < 0) continue;
          let end = at + echoes[i].length;
          if (text[end] === '\r') end++;
          if (text[end] === '\n') end++;
          text = text.slice(0, at) + text.slice(end);
          echoes.splice(i, 1);
          i--;
        }
        if (text) onScreen(text);
      };
      const serve = (f) => {
        if (f.op === 'mount') {
          const a = f.args || {};
          if (!a.url) return reply(f, { ok_call: false, error: 'mount without url' });
          mounts.push({ url: a.url, f, t0: Date.now() });
          try { worker.postMessage({ t: 'mount-tar', url: a.url, prefix: a.prefix }); }
          catch (e) { reply(f, { ok_call: false, error: String((e && e.message) || e) }); }
          return;
        }
        if (onCall) { Promise.resolve(onCall(f)).then((o) => reply(f, o)); return; }
        reply(f, { ok_call: false, error: 'unknown host op ' + f.op });
      };
      return {
        // Feed it fd-1 output. Returns nothing; screen text goes to onScreen.
        feed(strIn) {
          pend += strIn;
          for (;;) {
            const a = pend.indexOf(STX);
            if (a < 0) { emit(pend); pend = ''; return; }
            if (a > 0) emit(pend.slice(0, a));
            const b = pend.indexOf(ETX, a + 1);
            if (b < 0) { pend = pend.slice(a); return; }
            const raw = pend.slice(a + 1, b);
            pend = pend.slice(b + 1);
            if (pend.startsWith('\r')) pend = pend.slice(1);
            if (pend.startsWith('\n')) pend = pend.slice(1);
            let f = null;
            try { f = JSON.parse(dec(raw)); } catch (_) { emit(STX + raw + ETX); continue; }
            if (f && f.t === 'call') serve(f);
          }
        },
        // Call from the worker's onmessage for {t:'tar-mounted'}. True if it was ours.
        mounted(m) {
          const i = mounts.findIndex((x) => x.url === m.url);
          if (i < 0) return false;
          const wt = mounts.splice(i, 1)[0];
          if (onMountMs) onMountMs(Date.now() - wt.t0);
          reply(wt.f, m.ok ? { ok_call: true } : { ok_call: false, error: m.err || 'mount failed' });
          return true;
        },
        flush() { if (pend) { emit(pend); pend = ''; } },
      };
    },
  };
})(typeof self !== 'undefined' ? self : globalThis);
