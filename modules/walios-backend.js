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
  // dlopen14: file modes persist. OPFS has no modes, so chmod lived in RAM and every
  // OPFS-backed file came back 0644 on the next boot (ssh refused its own key again).
  // opfs-worker.js now keeps a mode sidecar in IndexedDB (SETMODE op, returned with
  // READDIR); the kernel guesses 0600 under .ssh/ and 0755 for *.sh when there is no
  // record. Also: 'add-pkg' creates the /bin/<name> stub (a package added mid-session
  // was "not found" by name), and a seeded "#!" blob lands 0755.
  const WORKER_V = 'dlopen14';

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

    // ---- TLS trust + git config, for EVERY walios host ------------------------
    // PY_ENV's SSL_CERT_FILE points at /site-packages/certifi/cacert.pem, which only
    // exists once python's companion tar has been mounted. Anything that needs TLS
    // before that -- `git clone`, wget, curl -- then has no trust store at all. The
    // terminal seeded a real bundle and pointed the env at it; the walios() TOOL did
    // not, so a clone that worked in the terminal died in the tool with
    //   SSL certificate problem: unable to get local issuer certificate
    // Both now take the same two helpers, so they cannot drift again.
    CA_PATH: '/etc/ssl/certs/ca-certificates.crt',

    tlsEnv() {
      return {
        SSL_CERT_FILE: this.CA_PATH,
        CURL_CA_BUNDLE: this.CA_PATH,
        GIT_CONFIG_GLOBAL: '/etc/gitconfig',
        // Never prompt. A private repo cloned without credentials made git ask
        // "Username for 'https://github.com':", read EOF on the tool's closed stdin,
        // and die with exit 128 and the error swallowed -- so the clone "silently
        // did nothing". With prompting off git fails immediately and SAYS it needs
        // credentials, which is the actionable message; put a token in the URL for a
        // private repo (https://x-access-token:TOKEN@github.com/owner/repo).
        GIT_TERMINAL_PROMPT: '0',
      };
    },

    // Blobs to seed into the guest before it runs. `base` lets a caller on another
    // path reach /walios/ (the worker is not served from there).
    async tlsBlobs(base) {
      const b = {};
      const enc = (s2) => new TextEncoder().encode(s2).buffer;
      try {
        const r = await fetch((base || '/walios/') + 'cacert.pem');
        if (r.ok) b[this.CA_PATH] = await r.arrayBuffer();
      } catch (_) {}
      // safe.directory: the guest runs as root over an OPFS-backed tree, which git
      // otherwise refuses as "dubious ownership". Connection: close because the WISP
      // relay does not multiplex a kept-alive connection.
      b['/etc/gitconfig'] = enc('[safe]\n\tdirectory = *\n[http]\n\tsslCAInfo = ' + this.CA_PATH
                                + '\n\textraHeader = Connection: close\n');
      return b;
    },

    // ---- Package index, for EVERY walios host --------------------------------
    // A runnable package can come from three places, all served under /walios/:
    //   index.json            the prebuilt repo: name -> wasm url [+ companion tars]
    //   pkgcache/index.json   binaries users compiled in-tab and uploaded (e.g. git)
    //   aports-catalog.json   the Alpine catalog; tier 'wasm' entries carry a wasm url,
    //                         the rest can only be BUILT (terminal.html's build button)
    // terminal.html folded all three into its boot manifest; the walios() tool folded
    // only pkgcache, so a package the UI could "add" did not exist for the model, and
    // neither host let the GUEST ask for one. One loader now, and `apk add` below asks
    // through the frame channel. Nothing is fetched until a binary is first exec'd.
    // `builtin` names (the host's own manifest) always win a name clash.
    async pkgIndex(base, builtin) {
      base = base || '/walios/';
      builtin = builtin || {};
      const get = async (u) => { try { const r = await fetch(base + u); return r.ok ? await r.json() : null; } catch (_) { return null; } };
      const [repo, cache, cat] = await Promise.all([get('index.json'), get('pkgcache/index.json'), get('aports-catalog.json')]);
      const pk = {};                                         // name -> { url, tars, ver, kind, size, desc, src }
      const add = (name, e) => { if (!name || builtin[name] || pk[name]) return; pk[name] = e; };
      // pkgcache first: an in-tab build of X is the newest X (the ?t= is what
      // terminal.html does too -- pkgcache is served no-store but a wasm compile cache
      // keys on the URL).
      if (cache && Array.isArray(cache.packages)) for (const n of cache.packages) add(n, { url: 'pkgcache/' + n + '.wasm', kind: 'bin', src: 'pkgcache' });
      if (repo && repo.packages) for (const p of Object.values(repo.packages)) add(p.name, { url: p.url, tars: p.tars, ver: p.ver, kind: p.kind, size: p.size, desc: p.desc, src: 'repo' });
      // Boot manifest = repo + pkgcache, exactly what terminal.html puts on PATH at boot.
      // Catalog tier-'wasm' entries are NOT on PATH until asked for -- the UI's "add"
      // button and `apk add` both register them on demand -- so the two hosts agree on
      // what a fresh shell has, and `apk add` means the same thing in both.
      const manifest = {}, lazyTars = {};                    // lazyTars is keyed by module URL (see wali-worker ensureModule)
      for (const [n, e] of Object.entries(pk)) { manifest[n] = e.url; if (Array.isArray(e.tars) && e.tars.length) lazyTars[e.url] = e.tars; }
      const buildOnly = {};                                  // name -> desc; in the catalog, not built to wasm
      if (Array.isArray(cat)) for (const p of cat) {
        if (p.tier === 'wasm' && p.wasm) add(p.name, { url: p.wasm, desc: p.desc, kind: 'bin', src: 'catalog' });
        else if (p.name && !pk[p.name] && !builtin[p.name]) buildOnly[p.name] = p.desc || '';
      }
      // /etc/apk/packages.tsv -- name, version, kind, size, description, status. What
      // `apk search/list/info` read in the guest; only `apk add` needs the host.
      const clean = (s) => String(s == null ? '' : s).replace(/[\t\r\n]+/g, ' ').trim();
      const rows = [];
      for (const n of Object.keys(builtin).sort()) rows.push([n, '', 'builtin', '', '', 'installed'].join('\t'));
      // 'installed' = on PATH at boot (builtin, repo, pkgcache); 'available' = catalog,
      // one `apk add` away.
      for (const n of Object.keys(pk).sort()) { const e = pk[n]; rows.push([n, clean(e.ver), clean(e.kind), clean(e.size), clean(e.desc), manifest[n] ? 'installed' : 'available'].join('\t')); }
      for (const n of Object.keys(buildOnly).sort()) rows.push([n, '', '', '', clean(buildOnly[n]), 'build-only'].join('\t'));
      return {
        pk, buildOnly, manifest, lazyTars,
        tsv: rows.join('\n') + '\n',
        resolve(name) { return pk[name] || null; },
      };
    },

    // Blobs every host seeds so the guest has a package client: the index above as a
    // TSV, and `apk` itself. Kept here so the tool and the terminal ship the same file.
    pkgBlobs(idx) {
      const enc = (s2) => new TextEncoder().encode(s2).buffer;
      const b = { '/usr/bin/apk': enc(this.apkScript()) };
      if (idx && idx.tsv) b['/etc/apk/packages.tsv'] = enc(idx.tsv);
      return b;
    },

    // The in-guest package client. Plain busybox sh: this busybox has no base64, so the
    // frame it sends is plain JSON and it asks (plain:1) for a plain-JSON reply -- see
    // hostChannel, which accepts both encodings. The reply is read from stdin: under the
    // headless tool stdin already hit EOF at boot and the host's line lands LATER, so an
    // empty read is retried (same rule sitecustomize.py follows), not treated as the end.
    apkScript() {
      return [
        '#!/bin/sh',
        '# apk -- walios package client. Packages are wasm binaries served by the host page.',
        '#   apk add <pkg>...    register with the running kernel (fetched on first exec)',
        '#   apk search [pat]    search name/description   apk list    apk info <pkg>',
        'TSV=/etc/apk/packages.tsv',
        'usage() { echo "usage: apk add <pkg>... | search [pattern] | list [installed|available|build-only] | info <pkg>" >&2; exit 2; }',
        '[ $# -ge 1 ] || usage',
        'cmd=$1; shift',
        'need_tsv() { [ -f "$TSV" ] || { echo "apk: no package index ($TSV missing)" >&2; exit 1; }; }',
        'show() { awk -F"\\t" \'{ st=$6; if (st=="installed") st="on PATH"; if (st=="available") st="apk add first"; if (st=="build-only") st="not built to wasm - build it in the walios UI";',
        '  printf "%-26s %-9s %s%s\\n", $1, $2, $5, "  [" st "]" }\' ; }',
        'case "$cmd" in',
        '  search) need_tsv; q=$(printf %s "$1" | tr A-Z a-z)',
        '    awk -F"\\t" -v q="$q" \'index(tolower($1), q) || index(tolower($5), q)\' "$TSV" | show ;;',
        '  list) need_tsv; f=${1:-}',
        '    awk -F"\\t" -v f="$f" \'f=="" || $6==f\' "$TSV" | show ;;',
        '  info) need_tsv; [ $# -ge 1 ] || usage',
        '    awk -F"\\t" -v n="$1" \'$1==n\' "$TSV" | show',
        '    awk -F"\\t" -v n="$1" \'$1==n{f=1} END{exit !f}\' "$TSV" || { echo "apk: unknown package $1" >&2; exit 1; } ;;',
        '  add) [ $# -ge 1 ] || usage',
        '    rc=0; k=0',
        '    for p in "$@"; do',
        '      case "$p" in *[!A-Za-z0-9._+-]*|"") echo "apk: bad package name: $p" >&2; rc=1; continue;; esac',
        '      # Always ask the host, even if /bin/<name> exists: the stub can outlive the',
        '      # manifest entry when a host reuses its worker for a new run. Registering',
        '      # twice is harmless.',
        '      if [ -f "$TSV" ] && awk -F"\\t" -v n="$p" \'$1==n && $3=="builtin"{f=1} END{exit !f}\' "$TSV"; then echo "$p: built-in"; continue; fi',
        '      k=$((k+1)); id="$$$k"',
        '      printf \'\\002{"t":"call","id":%s,"op":"pkg","plain":1,"args":{"name":"%s"}}\\003\\n\' "$id" "$p"',
        '      reply=""; n=0',
        '      while [ $n -lt 600 ]; do',
        '        if IFS= read -r line; then',
        '          case "$line" in *\'"t":"reply"\'*\'"id":\'"$id"[,\\}]*) reply=$line; break;; esac',
        '        else usleep 100000 2>/dev/null || sleep 1; fi',
        '        n=$((n+1))',
        '      done',
        '      case "$reply" in',
        '        "") echo "apk: no reply from the host for $p (is this shell running under a walios host?)" >&2; rc=1;;',
        '        *\'"ok_call":true\'*) echo "$p: added (fetched on first run)";;',
        '        *) err=$(printf %s "$reply" | sed -n \'s/.*"error":"\\([^"]*\\)".*/\\1/p\'); echo "apk: $p: ${err:-failed}" >&2; rc=1;;',
        '      esac',
        '    done',
        '    exit $rc ;;',
        '  *) usage ;;',
        'esac',
        '',
      ].join('\n');
    },

    // Is JSPI here? walios' blocking syscalls are WebAssembly.Suspending imports, so
    // without it the guest traps rather than degrading. Callers pass `jspi: WB.jspi()`
    // so a browser without it takes the synchronous path instead of dying.
    jspi() {
      return typeof WebAssembly !== 'undefined'
          && typeof WebAssembly.Suspending === 'function'
          && typeof WebAssembly.promising === 'function';
    },

    // Yield to the event loop WITHOUT setTimeout.
    //
    // Both SAB bridges below hand the guest one chunk at a time and then spin until it
    // has drained: the host cannot Atomics.wait (it may be the main thread, where that
    // is illegal), so it has to yield. setTimeout was the obvious way, and it is wrong --
    // Chrome clamps timers to >=1s in a HIDDEN tab, so every chunk handshake cost a
    // second the moment the user switched tabs. Measured: an 8-chunk stdlib mount blew
    // through syncRequest's 60s budget and the guest reported the bundle "did not
    // arrive", which surfaces as `ModuleNotFoundError: No module named 'encodings'` --
    // a background tab silently broke python. MessagePort delivery is not throttled.
    tick() {
      if (!this._tickCh) {
        this._tickCh = new MessageChannel();
        this._tickQ = [];
        this._tickCh.port1.onmessage = () => { const f = this._tickQ.shift(); if (f) f(); };
        this._tickCh.port1.start();
      }
      return new Promise((r) => { this._tickQ.push(r); this._tickCh.port2.postMessage(0); });
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
            while (Atomics.load(ctl, 0) !== 0) await g.WALIOS_BACKEND.tick();
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

    // Lazy bundle mounting for the SYNCHRONOUS path.
    //
    // With JSPI the wali worker fetches and extracts a bundle itself. Without it the guest
    // is parked in Atomics.wait ON THAT THREAD, so the worker can never run its own
    // 'mount-tar' handler: the mount frame went out and nothing came back. Measured --
    // `import numpy` hung to the 90s test timeout while the stdlib worked fine.
    //
    // So the host does the half that needs an event loop (fetch + gunzip) on ITS thread
    // and streams the plain tar bytes through a SAB the guest drains from inside its wait
    // loop; the guest parses them with the same installTar() the async path uses. One
    // buffer, installed at boot -- a blocked guest can never be handed a new one.
    //
    //   ctl[0]  0 = host may write, 1 = chunk ready, 2 = last chunk, 3 = host error
    //   ctl[1]  bytes in this chunk        data[0..256) = NUL-padded mount prefix
    // `base` matters: bundle URLs are RELATIVE ('walios-numpy.tar.gz?v=3') and the wali
    // worker resolves them against its own script at /walios/. Fetching from the host
    // instead resolves them against the HOST's document, which 404s and looks exactly
    // like a missing package -- the finder gets ok_call:false and raises
    // ModuleNotFoundError in milliseconds. Resolve explicitly.
    mountBridge(worker, opts) {
      const o = (typeof opts === 'number') ? { chunkBytes: opts } : (opts || {});
      const base = o.base || '/walios/';
      const chunkBytes = o.chunkBytes;
      const PREFIX = 256, cap = chunkBytes || (4 << 20);
      let sab;
      try { sab = new SharedArrayBuffer(32 + PREFIX + cap); }
      catch (_) { return null; }                       // no cross-origin isolation
      const ctl = new Int32Array(sab, 0, 8), data = new Uint8Array(sab, 32);
      try { worker.postMessage({ t: 'mount-sab', sab }); } catch (_) { return null; }
      const idle = async () => { while (Atomics.load(ctl, 0) !== 0) await g.WALIOS_BACKEND.tick(); };
      return {
        ctl,                                             // exposed so a probe can watch the handshake
        state() { return [Atomics.load(ctl, 0), Atomics.load(ctl, 1)]; },
        // prefix 'module:<key>' streams a RAW wasm binary for sync exec to compile;
        // anything else is a gzipped package tarball to unpack. Same buffer, same
        // handshake -- a blocked guest can only be handed one channel.
        async mount(url, prefix) {
          let bytes;
          const raw = String(prefix || '').startsWith('module:');
          try {
            const abs = new URL(url, new URL(base, self.location ? self.location.href : undefined)).href;
            const resp = await fetch(abs);
            if (!resp.ok) throw new Error('HTTP ' + resp.status + ' for ' + abs);
            bytes = raw
              ? new Uint8Array(await resp.arrayBuffer())
              : new Uint8Array(await new Response(resp.body.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
          } catch (e) {
            await idle(); Atomics.store(ctl, 0, 3); Atomics.notify(ctl, 0);
            return { ok: false, error: String((e && e.message) || e) };
          }
          const pb = new TextEncoder().encode(prefix || '/');
          for (let off = 0;;) {
            await idle();
            data.fill(0, 0, PREFIX);
            data.set(pb.subarray(0, PREFIX), 0);        // the prefix rides with every chunk
            const n = Math.min(bytes.length - off, cap);
            data.set(bytes.subarray(off, off + n), PREFIX);
            off += n;
            const last = off >= bytes.length;
            Atomics.store(ctl, 1, n);
            Atomics.store(ctl, 0, last ? 2 : 1);
            Atomics.notify(ctl, 0);
            if (last) break;
          }
          await idle();                                  // guest has installed it
          return { ok: true };
        },
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
    //   mount     optional mountBridge(); when given, bundles are fetched HERE and
    //             streamed in, because a synchronous guest cannot mount its own
    //   pkgs      optional pkgIndex() (or a promise of one); enables the 'pkg' op that
    //             `apk add` sends -- resolved here and registered with the kernel
    //
    // A frame is normally base64; a call carrying plain:1 is plain JSON and gets a plain
    // JSON reply (the shell client has no base64). Both are one line, so the echo strip
    // works the same way.
    hostChannel({ worker, onScreen, onCall, onMountMs, stdin, mount, pkgs }) {
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
        const body = JSON.stringify(Object.assign({ t: 'reply', id: f.id }, o));
        const payload = f.plain ? body : enc(body);
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
          // A synchronous guest cannot service its own 'mount-tar', so fetch here and
          // stream the bytes in. Under JSPI the worker still does it itself.
          if (mount) {
            const t0 = Date.now();
            mount.mount(a.url, a.prefix).then((r) => {
              if (onMountMs) onMountMs(Date.now() - t0);
              reply(f, r.ok ? { ok_call: true } : { ok_call: false, error: r.error || 'mount failed' });
            });
            return;
          }
          mounts.push({ url: a.url, f, t0: Date.now() });
          try { worker.postMessage({ t: 'mount-tar', url: a.url, prefix: a.prefix }); }
          catch (e) { reply(f, { ok_call: false, error: String((e && e.message) || e) }); }
          return;
        }
        if (f.op === 'pkg') {
          // `apk add <name>`: look the name up in the package index and register it with
          // the running kernel. The wasm is fetched on first exec, so this is instant.
          // Error strings deliberately carry no double quotes: the shell client pulls
          // them out of the JSON with a sed that stops at the first one.
          const a = f.args || {}, name = String(a.name || '').trim();
          if (!pkgs) return reply(f, { ok_call: false, error: 'this walios host has no package index' });
          if (!/^[A-Za-z0-9][A-Za-z0-9._+-]*$/.test(name)) return reply(f, { ok_call: false, error: 'bad package name' });
          Promise.resolve(pkgs).then((idx) => {
            const e = idx && idx.resolve(name);
            if (!e) {
              const bo = idx && idx.buildOnly && idx.buildOnly[name];
              return reply(f, { ok_call: false, error: bo !== undefined
                ? name + ' is in the Alpine catalog but not built to wasm yet. It can be built from the walios UI at /walios/ (Packages panel, build), not from this shell.'
                : 'unknown package ' + name + ' (try: apk search ' + name + ')' });
            }
            try { worker.postMessage({ t: 'add-pkg', name, url: e.url, tars: Array.isArray(e.tars) && e.tars.length ? e.tars : undefined }); }
            catch (err) { return reply(f, { ok_call: false, error: String((err && err.message) || err) }); }
            reply(f, { ok_call: true, url: e.url, src: e.src || '' });
          }, (err) => reply(f, { ok_call: false, error: 'package index unavailable: ' + String((err && err.message) || err) }));
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
            // base64 first (Python clients); a plain-JSON frame from the shell client
            // fails atob on its first '{' and is parsed as-is.
            try { f = JSON.parse(dec(raw)); }
            catch (_) { try { f = JSON.parse(raw); } catch (_2) { emit(STX + raw + ETX); continue; } }
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
