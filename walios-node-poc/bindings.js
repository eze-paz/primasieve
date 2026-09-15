'use strict';
// Synthetic internalBinding(). Every binding Node's lib/ asks for is served here or
// recorded as a miss. Nothing below calls into the host Node's own bindings -- the
// point of the spike is that node's lib/*.js runs on OUR kernel seam.
const { VfsError } = require('./vfs.js');
const CONST = require('./constants.json');
const { makeBufferBinding } = require('./buffer-binding.js');
const { makeTcpWrap } = require('./tcp-wrap.js');
const { makeDnsWrap } = require('./dns-wrap.js');
const { makeHttpParser } = require('./http-parser.js');
const { makeChildProcess } = require('./child-process.js');
const { makePipeWrap } = require('./pipe-wrap.js');
const { makeProcessWrap } = require('./process-wrap.js');
const { makeContextify } = require('./contextify.js');

// privateSymbols is read off internalBinding('util') (lib/internal/errors.js:939),
// and must be STABLE across reads -- a fresh Symbol per access silently breaks
// every err[arrow_message_private_symbol] round trip.
const PRIVATE_SYMBOLS = new Proxy({}, (() => {
  const made = new Map();
  return { get: (t, k) => { const s = String(k); if (!made.has(s)) made.set(s, Symbol(s)); return made.get(s); } };
})());

// One array, shared by internalBinding('stream_wrap') and tcp_wrap.
const STREAM_BASE_STATE = new Int32Array(8);

const HRTIME_AB = new ArrayBuffer(16);
const HRTIME_BUF = new Uint32Array(HRTIME_AB);
const HRTIME_BIG = new BigUint64Array(HRTIME_AB, 0, 1);

function makeBindings(vfs, trace, realm) {
  realm = realm || {};
  const hit = (n, k) => { trace.used.add(n + '.' + k); };
  const miss = (n, k) => { trace.missing.add(n + '.' + k); };

  // ONE pipe_wrap for both bindings. child_process constructs its stdio handles from
  // internalBinding('pipe_wrap').Pipe and passes them into process_wrap's spawn(), so
  // a second instance would hand it a different class than the one it built.
  const PIPE_WRAP = (realm.sys && realm.mem) ? makePipeWrap(realm.sys, realm.mem, {
    streamBaseState: STREAM_BASE_STATE,
    kReadBytesOrError: 0, kArrayBufferOffset: 1, kBytesWritten: 2, kLastWriteWasAsync: 3,
    getBuffer: () => realm.Buffer,
    pending: realm.pending,
    trace: (m) => realm.trace && realm.trace('[pipe] ' + m),
    uvErrno: { UV_EOF: -4095 },
  }) : null;

  // ---- fs: the binding that actually proves the thesis -------------------
  function statArray(st, bigint) {
    const A = bigint ? BigInt64Array : Float64Array;
    const a = new A(18);
    const v = (x) => (bigint ? BigInt(Math.trunc(x)) : x);
    const ms = st.mtime, s = Math.floor(ms / 1000), ns = (ms % 1000) * 1e6;
    a[0] = v(2049); a[1] = v(st.mode); a[2] = v(1); a[3] = v(0); a[4] = v(0);
    a[5] = v(0); a[6] = v(4096); a[7] = v(st.ino); a[8] = v(st.size);
    a[9] = v(Math.ceil(st.size / 512));
    for (const i of [10, 12, 14, 16]) { a[i] = v(s); a[i + 1] = v(ns); }
    return a;
  }
  const uvErr = (e, sys, path) => {
    const err = new Error(e.code + ': ' + sys + " '" + (path || '') + "'");
    err.errno = e.errno; err.code = e.code; err.syscall = sys;
    if (path) err.path = path;
    return err;
  };
  const wrap = (sys) => (fn) => (...a) => {
    try { return fn(...a); }
    catch (e) { if (e instanceof VfsError) throw uvErr(e, e.syscall || sys, e.path); throw e; }
  };
  const td = new TextDecoder(), te = new TextEncoder();

  const fsBinding = {
    open: wrap('open')((path, flags, mode) => vfs.open(path, flags, mode)),
    close: wrap('close')((fd) => { vfs.close(fd); }),
    read: wrap('read')((fd, buf, off, len, pos) => vfs.read(fd, buf, off, len, pos)),
    writeBuffer: wrap('write')((fd, buf, off, len, pos) => vfs.write(fd, buf.subarray(off, off + (len == null ? buf.length - off : len)), pos)),
    writeString: wrap('write')((fd, str, pos) => vfs.write(fd, te.encode(str), pos)),
    writeBuffers: wrap('write')((fd, bufs, pos) => { let n = 0; for (const b of bufs) n += vfs.write(fd, b, pos == null ? null : pos + n); return n; }),
    fstat: wrap('fstat')((fd, bigint) => statArray(vfs.statFd(fd), bigint)),
    stat: wrap('stat')((path, bigint) => statArray(vfs.statPath(path), bigint)),
    lstat: wrap('lstat')((path, bigint) => statArray(vfs.statPath(path), bigint)),
    readFileUtf8: wrap('open')((path) => {
      const st = vfs.statPath(path);
      const fd = vfs.open(path, 0, 0);
      const b = new Uint8Array(st.size);
      vfs.read(fd, b, 0, st.size, 0);
      vfs.close(fd);
      return td.decode(b);
    }),
    mkdir: wrap('mkdir')((path) => { vfs.mkdir(path); return undefined; }),
    rmdir: wrap('rmdir')((path) => { vfs.dirs.delete(vfs._norm(path)); }),
    unlink: wrap('unlink')((path) => vfs.unlink(path)),
    readdir: wrap('scandir')((path, enc, withTypes) => {
      const names = vfs.readdir(path);
      return withTypes ? [names, names.map(() => 1)] : names;
    }),
    access: wrap('access')((path) => { vfs.statPath(path); }),
    realpath: wrap('realpath')((path) => vfs._norm(path)),
    existsSync: (path) => vfs.exists(path) >= 0,

    // ---- fs.promises -------------------------------------------------------
    // node's promises layer passes kUsePromises as the request argument and awaits
    // the result. Our bindings return synchronously, and `await` on a plain value
    // is fine -- so the whole promises surface works without an async kernel path.
    // What it is NOT is concurrent: two awaited reads still run one after the other.
    openFileHandle: wrap('open')((path, flags, mode) => {
      const fd = vfs.open(path, flags, mode === undefined ? 0o666 : mode);
      return {
        fd,
        // Awaited inside a promise chain, so it must return a real Promise.
        close: () => { try { vfs.close(fd); } catch (_) {} return Promise.resolve(); },
        release: () => {},
        getAsyncId: () => 0,
      };
    }),
    // Cheap POSIX bits promises.js reaches for. No ownership or permission model
    // here, so these succeed rather than pretending to enforce something.
    chmod: () => 0, fchmod: () => 0, lchmod: () => 0,
    chown: () => 0, fchown: () => 0, lchown: () => 0,
    utimes: () => 0, futimes: () => 0, lutimes: () => 0,
    fdatasync: () => 0, fsync: () => 0,
    copyFile: wrap('copyfile')((src, dest) => {
      const st = vfs.statPath(src);
      const rfd = vfs.open(src, 0, 0);
      const buf = new Uint8Array(st.size);
      vfs.read(rfd, buf, 0, st.size, 0);
      vfs.close(rfd);
      const wfd = vfs.open(dest, 1 | 0o100 | 0o1000, 0o644);
      vfs.write(wfd, buf, null);
      vfs.close(wfd);
      return 0;
    }),
    mkdtemp: wrap('mkdtemp')((prefix) => {
      const p = String(prefix).replace(/X{6}$/, '') + Math.random().toString(36).slice(2, 8);
      vfs.mkdir(p);
      return p;
    }),
    statfs: () => new Float64Array([4096, 4096, 1 << 20, 1 << 19, 1 << 19, 1 << 16, 1 << 15, 0, 255, 0, 0]),
    // Pass the caller's flags THROUGH. Force-ORing O_TRUNC here truncated on every
    // append: fs.appendFileSync('/x','!') returned '!' instead of '<old>!'.
    // stringToFlags() already sets O_CREAT|O_TRUNC for 'w', O_CREAT|O_APPEND for 'a'.
    writeFileUtf8: wrap('open')((path, data, flags, mode) => {
      const fd = vfs.open(path, flags, mode);
      const n = vfs.write(fd, te.encode(String(data)), null);
      vfs.close(fd);
      return n;
    }),
    rename: wrap('rename')((from, to) => vfs.rename(from, to)),
    // Scratch array the sync stat family fills when it does not return one.
    statValues: new Float64Array(36),
    // Async request handle. Phase 1 replaces this with a real kernel completion;
    // here it just defers so the callback shape is exercised.
    FSReqCallback: class FSReqCallback {
      constructor(bigint) { this.bigint = bigint; this.oncomplete = null; }
    },
    // CJS resolver probe -- ONE argument (loader.js:273). 0 = file, 1 = dir, <0 = miss.
    internalModuleStat: (path) => { const r = vfs.exists(path); return r === 1 ? 0 : r === 0 ? 1 : -2; },
    getFormatOfExtensionlessFile: () => 1,
    getValidatedPath: (p) => p,
  };

  // node's promises layer passes kUsePromises as the request argument and then calls
  // PromisePrototypeThen on the RESULT -- which must therefore be a genuine Promise,
  // not a plain value ("Promise.prototype.then called on incompatible receiver").
  // Wrap every fs entry: called with the sentinel, return a real Promise; otherwise
  // behave exactly as before, so the sync paths are untouched.
  const K_USE_PROMISES = Symbol('kUsePromises');
  for (const [name, fn] of Object.entries(fsBinding)) {
    if (typeof fn !== 'function' || name === 'FSReqCallback') continue;
    fsBinding[name] = function (...a) {
      const promised = a.length && a[a.length - 1] === K_USE_PROMISES;
      if (promised) a = a.slice(0, -1);
      if (!promised) return fn.apply(this, a);
      try { return Promise.resolve(fn.apply(this, a)); }
      catch (e) { return Promise.reject(e); }
    };
  }
  fsBinding.kUsePromises = K_USE_PROMISES;

  const errnoEntries = Object.entries(CONST.os.errno);

  const table = {
    fs: fsBinding,
    constants: CONST,
    types: {
      isDate: (v) => v instanceof Date, isRegExp: (v) => v instanceof RegExp,
      isMap: (v) => v instanceof Map, isSet: (v) => v instanceof Set,
      isNativeError: (v) => v instanceof Error, isPromise: (v) => v instanceof Promise,
      isArrayBuffer: (v) => v instanceof ArrayBuffer,
      isTypedArray: (v) => ArrayBuffer.isView(v) && !(v instanceof DataView),
      isUint8Array: (v) => v instanceof Uint8Array, isDataView: (v) => v instanceof DataView,
      isExternal: () => false,
      isAnyArrayBuffer: (v) => v instanceof ArrayBuffer || (typeof SharedArrayBuffer !== 'undefined' && v instanceof SharedArrayBuffer),
      isSharedArrayBuffer: (v) => typeof SharedArrayBuffer !== 'undefined' && v instanceof SharedArrayBuffer,
      isBigInt64Array: (v) => v instanceof BigInt64Array, isFloat64Array: (v) => v instanceof Float64Array,
      isProxy: () => false, isModuleNamespaceObject: () => false, isBoxedPrimitive: () => false,
      isArgumentsObject: (v) => Object.prototype.toString.call(v) === '[object Arguments]',
      isGeneratorFunction: () => false, isAsyncFunction: () => false, isGeneratorObject: () => false,
      isNumberObject: (v) => typeof v === 'object' && v !== null && Object.prototype.toString.call(v) === '[object Number]',
      isStringObject: (v) => typeof v === 'object' && v !== null && Object.prototype.toString.call(v) === '[object String]',
      isBooleanObject: (v) => typeof v === 'object' && v !== null && Object.prototype.toString.call(v) === '[object Boolean]',
      isSymbolObject: (v) => typeof v === 'object' && v !== null && Object.prototype.toString.call(v) === '[object Symbol]',
      isBigIntObject: (v) => typeof v === 'object' && v !== null && Object.prototype.toString.call(v) === '[object BigInt]',
      isWeakMap: (v) => v instanceof WeakMap, isWeakSet: (v) => v instanceof WeakSet,
      isCryptoKey: () => false, isKeyObject: () => false,
    },
    uv: Object.assign(
      {
        errname: (n) => { for (const [k, v] of errnoEntries) if (Math.abs(v) === Math.abs(n)) return k; return 'UNKNOWN'; },
        getErrorMap: () => new Map(errnoEntries.map(([k, v]) => [-Math.abs(v), [k, k]])),
        UV_EOF: -4095,
      },
      Object.fromEntries(errnoEntries.map(([k, v]) => ['UV_' + k, -Math.abs(v)])),
    ),
    config: { hasOpenSSL: false, fipsMode: false, hasIntl: true, hasSmallICU: false, hasNodeOptions: false, hasInspector: false, noBrowserGlobals: false, bits: 64, hasDtrace: false, isDebugBuild: false, hasCachedBuiltins: false },
    options: {
      getOptions: () => ({ options: new Map(), aliases: new Map() }),
      getCLIOptionsInfo: () => ({ options: new Map(), aliases: new Map() }),
      getEnvOptionsInputType: () => ({}),
      // getOptionValue(name) reads straight off this object. List-valued options MUST
      // be arrays -- lib/internal/modules/esm/utils.js spreads --conditions, and an
      // undefined there is "userConditions is not iterable".
      getCLIOptionsValues: () => ({
        '--conditions': [], '--import': [], '--require': [], '--experimental-loader': [],
        '--preserve-symlinks': false, '--preserve-symlinks-main': false,
        '--experimental-detect-module': false, '--experimental-require-module': false,
        '--experimental-strip-types': false, '--experimental-transform-types': false,
        '--experimental-vm-modules': false, '--experimental-import-meta-resolve': false,
        '--experimental-network-imports': false, '--experimental-permission': false,
        '--pending-deprecation': false, '--no-deprecation': false,
        '--throw-deprecation': false, '--trace-deprecation': false, '--trace-warnings': false,
        '--expose-internals': false, '--frozen-intrinsics': false, '--trace-sync-io': false,
        '--max-http-header-size': 16384, '--input-type': undefined,
        '--force-node-api-uncaught-exceptions-policy': false,
      }),
      getEmbedderOptions: () => ({ shouldNotRegisterESMLoader: true, noGlobalSearchPaths: true, noBrowserGlobals: false, hasStartedUserCJSExecution: true }),
      envSettings: { kAllowedInEnvvar: 0 },
    },
    errors: {
      setPrepareStackTraceCallback: () => {}, setSourceMapsEnabled: () => {},
      setGetSourceMapErrorSource: () => {}, setEnhanceStackForFatalException: () => {},
      setMaybeCacheGeneratedSourceMap: () => {}, getContinuationPreservedEmbedderData: () => undefined,
      noSideEffectsToString: (v) => { try { return String(v); } catch { return '<toString threw>'; } },
      triggerUncaughtException: (e) => { throw e; },
      exitCodes: {
        kNoFailure: 0, kGenericUserError: 1, kInvalidCommandLineArgument: 9,
        kInternalJSParseError: 3, kInternalJSEvaluationFailure: 4, kV8FatalError: 5,
        kUnsettledTopLevelAwait: 13, kUnfinishedSnapshot: 14, kStartupSnapshotFailure: 15,
        kUncaughtExceptionMonitor: 7, kInvalidFatalExceptionMonitor: 6,
      },
    },
    buffer: makeBufferBinding(),
    util: {
      privateSymbols: PRIVATE_SYMBOLS,
      constants: { ALL_PROPERTIES: 0, ONLY_ENUMERABLE: 2, SKIP_STRINGS: 8, SKIP_SYMBOLS: 16 },
      isArrayBufferView: (v) => ArrayBuffer.isView(v),
      isError: (v) => v instanceof Error,
      isFloat32Array: (v) => v instanceof Float32Array,
      isFloat16Array: (v) => typeof Float16Array !== 'undefined' && v instanceof Float16Array,
      // filter: 0 = ALL_PROPERTIES, 2 = ONLY_ENUMERABLE. Ignoring it leaks [length]
      // and other non-enumerables into util.inspect output.
      getOwnNonIndexProperties: (o, filter) => {
        const names = Object.getOwnPropertyNames(o).filter((k) => !/^(0|[1-9]\d*)$/.test(k));
        if (filter !== 2) return names;
        return names.filter((k) => { const d = Object.getOwnPropertyDescriptor(o, k); return d && d.enumerable; });
      },
      getPromiseDetails: () => [0, undefined], getProxyDetails: () => undefined,
      previewEntries: () => [[], false],
      getConstructorName: (o) => (o && o.constructor && o.constructor.name) || '',
      getExternalValue: () => 0n,
      propertyFilter: { ALL_PROPERTIES: 0, ONLY_ENUMERABLE: 2, SKIP_STRINGS: 8, SKIP_SYMBOLS: 16 },
      shouldRetainSymbols: () => false, isInsideNodeModules: () => false,
      getCallerLocation: () => [],
      // NOT a no-op. lib/util.js publishes TextEncoder/TextDecoder, parseArgs,
      // MIMEType and diff through this; stubbing it left util.TextEncoder
      // undefined, and axios failed with "is not a constructor" rather than with
      // anything of its own. Define real lazy getters that load the builtin on
      // first touch and then replace themselves with the plain value.
      defineLazyProperties: (target, id, keys, enumerable = true) => {
        for (const key of keys) {
          Object.defineProperty(target, key, {
            configurable: true,
            enumerable,
            get() {
              const v = realm.requireBuiltin(id)[key];
              Object.defineProperty(target, key, { configurable: true, enumerable, writable: true, value: v });
              return v;
            },
            set(v) { Object.defineProperty(target, key, { configurable: true, enumerable, writable: true, value: v }); },
          });
        }
      },
      // 'FILE' makes node build stdout/stderr as internal/fs/sync_write_stream,
      // which writes through fs.writeSync -> our fs binding -> SYS_write. 'TTY'
      // would pull in tty_wrap, which we do not serve yet.
      guessHandleType: () => 'FILE',
      WeakReference: class { constructor(v) { this._r = new WeakRef(v); } get() { return this._r.deref(); } incRef() {} decRef() {} },
      setHiddenValue: () => true, getHiddenValue: () => undefined, arrayBufferViewHasBuffer: () => true,
      kPending: 0, kFulfilled: 1, kRejected: 2,
    },
    symbols: {
      async_id_symbol: Symbol('async_id_symbol'), trigger_async_id_symbol: Symbol('trigger_async_id_symbol'),
      owner_symbol: Symbol('owner_symbol'), oninit_symbol: Symbol('oninit'), onbefore_symbol: Symbol('onbefore'),
      onafter_symbol: Symbol('onafter'), ondestroy_symbol: Symbol('ondestroy'), onpromiseresolve_symbol: Symbol('onpromiseresolve'),
      no_message_symbol: Symbol('no_message'), messaging_deserialize_symbol: Symbol('messaging_deserialize'),
      messaging_transfer_symbol: Symbol('messaging_transfer'), messaging_clone_symbol: Symbol('messaging_clone'),
      messaging_transfer_list_symbol: Symbol('messaging_transfer_list'), transfer_mode_private_symbol: Symbol('transfer_mode'),
    },
    async_wrap: {
      async_hook_fields: new Uint32Array(16), async_id_fields: new Float64Array(16), execution_async_resource: [],
      constants: { kInit: 0, kBefore: 1, kAfter: 2, kDestroy: 3, kPromiseResolve: 4, kTotals: 5, kCheck: 6, kStackLength: 7, kUsesExecutionAsyncResource: 8, kExecutionAsyncId: 0, kTriggerAsyncId: 1, kAsyncIdCounter: 2, kDefaultTriggerAsyncId: 3 },
      pushAsyncContext: () => {}, popAsyncContext: () => true, clearAsyncIdStack: () => {},
      setCallbackTrampoline: () => {}, registerDestroyHook: () => {}, setPromiseHooks: () => {},
      enablePromiseHook: () => {}, disablePromiseHook: () => {},
      Providers: new Proxy({}, { get: () => 0 }),
    },
    task_queue: {
      setTickCallback: () => {}, enqueueMicrotask: (f) => queueMicrotask(f),
      setPromiseRejectCallback: () => {}, runMicrotasks: () => {}, tickInfo: new Uint8Array(2),
      promiseRejectEvents: { kPromiseRejectWithNoHandler: 0, kPromiseHandlerAddedAfterReject: 1, kPromiseResolveAfterResolved: 2, kPromiseRejectAfterResolved: 3 },
    },
    timers: {
      getLibuvNow: () => Math.trunc(performance.now()),
      setupTimers: () => {}, scheduleTimer: () => {}, toggleTimerRef: () => {},
      immediateInfo: new Uint32Array(3), toggleImmediateRef: () => {},
      timeoutInfo: new Uint32Array(1),   // lib/internal/timers.js writes timeoutInfo[0]
    },
    credentials: { safeGetenv: () => undefined, getuid: () => 0, geteuid: () => 0, getgid: () => 0, getegid: () => 0 },
    process_methods: {
      // hrtimeBuffer is written IN PLACE by hrtime()/hrtimeBigInt(); lib/ reads it back
      // through two views (Uint32Array x3, BigUint64Array x1). See per_thread.js:76.
      hrtimeBuffer: HRTIME_BUF,
      hrtime: () => {
        const ns = Math.trunc(performance.now() * 1e6);
        const sec = Math.floor(ns / 1e9);
        HRTIME_BUF[0] = Math.floor(sec / 0x100000000);
        HRTIME_BUF[1] = sec >>> 0;
        HRTIME_BUF[2] = ns % 1e9;
      },
      hrtimeBigInt: () => { HRTIME_BIG[0] = BigInt(Math.trunc(performance.now() * 1e6)); },
      cpuUsage: () => ({ user: 0, system: 0 }), memoryUsage: () => [0, 0, 0, 0, 0],
      resourceUsage: () => [0, 0], uptime: () => performance.now() / 1000,
      _rawDebug: (s) => trace.stderr.push(String(s)), reallyExit: () => {}, patchProcessObject: () => {},
    },
    // A real decoder, not a stub: fs.promises.readFile decodes its chunks through
    // StringDecoder, and a stub failed with ERR_INVALID_ARG_TYPE. The encoding index
    // lives in the handle buffer at kEncodingField; state is kept per handle.
    string_decoder: (() => {
      const ENC = ['ascii', 'utf8', 'base64', 'ucs2', 'binary', 'hex', 'utf16le', 'base64url'];
      const state = new WeakMap();
      const mk = (enc) => {
        if (enc === 'utf8') { const d = new TextDecoder('utf-8'); return { write: (b) => d.decode(b, { stream: true }), end: () => d.decode(new Uint8Array(0)) }; }
        if (enc === 'ucs2' || enc === 'utf16le') { const d = new TextDecoder('utf-16le'); return { write: (b) => d.decode(b, { stream: true }), end: () => '' }; }
        const conv = (b) => {
          if (enc === 'hex') { let o = ''; for (const x of b) o += x.toString(16).padStart(2, '0'); return o; }
          if (enc === 'base64' || enc === 'base64url') return makeBufferBinding().base64Slice.call(b, 0, b.length);
          let o = ''; for (const x of b) o += String.fromCharCode(enc === 'ascii' ? x & 0x7f : x); return o;
        };
        return { write: conv, end: () => '' };
      };
      const get = (h) => {
        const enc = ENC[h[6]] || 'utf8';
        let st = state.get(h);
        if (!st || st.enc !== enc) { st = { enc, dec: mk(enc) }; state.set(h, st); }
        return st;
      };
      return {
        encodings: ENC,
        decode: (h, buf) => get(h).dec.write(buf),
        flush: (h) => { const st = state.get(h); const s2 = st ? st.dec.end() : ''; state.delete(h); return s2; },
        kIncompleteCharactersStart: 0, kIncompleteCharactersEnd: 4,
        kMissingBytes: 4, kBufferedBytes: 5, kEncodingField: 6, kNumFields: 7, kSize: 7,
      };
    })(),
    blob: { createBlob: () => ({}), getDataObject: () => undefined, storeDataObject: () => {}, revokeDataObject: () => {}, concat: () => new Uint8Array(0), FixedSizeBlobCopyJob: class {} },
    messaging: { MessageChannel: class {}, MessagePort: class {}, JSTransferable: class {}, setDeserializerCreateObjectFunction: () => {}, broadcastChannel: () => ({}), structuredClone: (v) => v },
    // Package resolution. Stubbing these out is why any package with an "exports"
    // map (debug, minimatch -- most modern ones) failed to resolve while lodash,
    // which has only "main", worked: without a package config node cannot apply
    // exports and gives up. The binding returns a SIX-ELEMENT ARRAY, not an object:
    //   [name, main, type, imports, exports, path]   (see deserializePackageJSON)
    // where imports/exports are JSON strings when they are not plain strings.
    modules: (() => {
      const readPkg = (jsonPath) => {
        let txt;
        try { txt = new TextDecoder().decode(readFileBytes(jsonPath)); } catch (_) { return undefined; }
        let j;
        try { j = JSON.parse(txt); } catch (_) { return undefined; }
        const ser = (v) => (v === undefined ? undefined : (typeof v === 'string' ? v : JSON.stringify(v)));
        return [
          typeof j.name === 'string' ? j.name : undefined,
          typeof j.main === 'string' ? j.main : undefined,
          j.type === 'module' || j.type === 'commonjs' ? j.type : 'none',
          ser(j.imports),
          ser(j.exports),
          undefined,
        ];
      };
      const readFileBytes = (p2) => {
        const st = vfs.statPath(p2);
        const fd = vfs.open(p2, 0, 0);
        const b = new Uint8Array(st.size);
        vfs.read(fd, b, 0, st.size, 0);
        vfs.close(fd);
        return b;
      };
      // Walk up for the nearest package.json, as node's resolver does.
      const nearest = (start) => {
        let dir = String(start).replace(/\/[^/]*$/, '');
        for (;;) {
          const cand = (dir || '') + '/package.json';
          const r = readPkg(cand);
          if (r) return { cfg: r, path: cand };
          if (!dir || dir === '/') return null;
          dir = dir.replace(/\/[^/]*$/, '');
        }
      };
      return {
        readPackageJSON: (jsonPath) => readPkg(jsonPath),
        getNearestParentPackageJSON: (p2) => { const n = nearest(p2); return n ? n.cfg : undefined; },
        getNearestParentPackageJSONType: (p2) => { const n = nearest(p2); return n ? [n.cfg[2], n.path] : undefined; },
        getPackageScopeConfig: (p2) => { const n = nearest(p2); return n ? n.cfg : undefined; },
        getPackageJSONScripts: () => undefined,
        getRepresentativeMainPath: () => undefined,
        flushCompileCache: () => {}, setCompileCacheDir: () => {},
        getCompileCacheDir: () => undefined, enableCompileCache: () => ({ status: 0 }),
        compileCacheStatus: ['FAILED', 'ENABLED', 'ALREADY_ENABLED', 'DISABLED'],
      };
    })(),
    builtins: { builtinIds: [], setInternalLoaders: () => {}, canBeRequiredByUsers: () => true, getCanBeRequiredByUsersWithoutSchemeList: () => [], getCanBeRequiredByUsersList: () => [], hasCachedBuiltins: () => false },
    // TextEncoder/TextDecoder are bindings over the page's own, not reimplementations.
    // encodeIntoResults is the shared Uint32Array node reads [read, written] out of,
    // so it must be one stable array rather than a fresh one per call.
    encoding_binding: (() => {
      const RESULTS = new Uint32Array(2);
      const dec = (label, ignoreBOM, fatal, input) =>
        new TextDecoder(label, { ignoreBOM: !!ignoreBOM, fatal: !!fatal })
          .decode(input === undefined ? new Uint8Array(0) : input);
      return {
        encodeIntoResults: RESULTS,
        encodeInto: (s, u8) => { const r = new TextEncoder().encodeInto(s, u8); RESULTS[0] = r.read; RESULTS[1] = r.written; return RESULTS; },
        encodeUtf8String: (s) => new TextEncoder().encode(s),
        decodeUTF8: (u8, ignoreBOM, fatal) => dec('utf-8', ignoreBOM, fatal, u8),
        decodeWindows1252: (u8, ignoreBOM, fatal) => dec('windows-1252', ignoreBOM, fatal, u8),
        decodeLatin1: (u8, ignoreBOM, fatal) => dec('windows-1252', ignoreBOM, fatal, u8),
        toASCII: (s) => { try { return new URL('http://' + s).hostname; } catch (_) { return s; } },
        toUnicode: (s) => s,
      };
    })(),
    // config.hasIntl is true because the page HAS full ICU -- but that makes
    // internal/encoding take the ICU branch, which needs this binding. Without it
    // util.TextDecoder resolved to undefined and axios died on
    // "util.TextEncoder is not a constructor". A converter handle is just a
    // platform TextDecoder; the FLUSH flag is the inverse of {stream:true}.
    icu: (() => {
      const FLUSH = 0x1, FATAL = 0x2, IGNORE_BOM = 0x4;
      return {
        getConverter: (encoding, flags) => {
          try {
            return new TextDecoder(encoding, {
              fatal: !!(flags & FATAL), ignoreBOM: !!(flags & IGNORE_BOM),
            });
          } catch (_) { return undefined; }
        },
        decode: (handle, input, flags) =>
          handle.decode(input === undefined ? new Uint8Array(0) : input, { stream: !(flags & FLUSH) }),
        hasConverter: (encoding) => { try { void new TextDecoder(encoding); return true; } catch (_) { return false; } },
        toASCII: (s) => { try { return new URL('http://' + s).hostname; } catch (_) { return s; } },
        toUnicode: (s) => s,
        // Real ICU measures East Asian width; node only uses this for console
        // alignment, so codepoint count is close enough to be honest about.
        getStringWidth: (s) => [...String(s)].length,
        icuErrName: (n) => 'U_ERROR_' + n,
      };
    })(),
    // A binding over the page's own WHATWG URL parser -- not a reimplementation.
    // lib/internal/url.js does not read parse()'s return value for the pieces: it
    // destructures the 9-slot `urlComponents` array the binding writes as a side
    // effect, then slices href by those offsets. Omitting it made `new URL(...)`
    // throw "Cannot destructure property '0' of 'bindingUrl.urlComponents'", which
    // is what took qs down; getting the offsets subtly wrong is worse, because
    // fileURLToPath then returns '' and the CJS resolver reports "Cannot find
    // module ''". So the offsets are derived from the END of href backwards --
    // the only way that holds for file:/// (empty host) and node: (no authority).
    url: (() => {
      const OMITTED = 4294967295;                   // ada's uint32_t(-1)
      // ada::scheme::type, in ada's order -- NOT alphabetical.
      const SCHEME = { 'http:': 0, 'https:': 2, 'ws:': 3, 'ftp:': 4, 'wss:': 5, 'file:': 6 };
      const mk = (input, base) => (base === undefined || base === null ? new URL(input) : new URL(input, base));
      const b = {
        urlComponents: new Uint32Array(9),
        domainToASCII: (v) => { try { return new URL('http://' + v).hostname; } catch (_) { return ''; } },
        domainToUnicode: (v) => v,
        canParse: (input, base) => { try { mk(input, base); return true; } catch (_) { return false; } },
        getOrigin: (input) => { try { return mk(input).origin; } catch (_) { return undefined; } },
        format: (href) => href,
        pathToFileURL: (p2) => {
          // Windows drive letters never occur here: the guest's paths are the
          // kernel's, which are POSIX.
          const u = new URL('file:///');
          u.pathname = String(p2);
          return u.href;
        },
        parse: (input, base, raiseException) => {
          let u;
          try { u = mk(input, base); }
          catch (e) { if (raiseException) throw e; return undefined; }
          return b.fill(u);
        },
        // The setter path: url.js hands back href plus what changed and re-reads
        // the components, so one shared filler serves both.
        update: (href, action, value) => {
          let u;
          try { u = new URL(href); } catch (_) { return undefined; }
          const field = ['protocol', 'host', 'hostname', 'port', 'username',
                         'password', 'pathname', 'search', 'hash', 'href'][action];
          try { u[field] = String(value); } catch (_) { return undefined; }
          return b.fill(u);
        },
        fill: (u) => {
          const href = u.href;
          const c = b.urlComponents;
          const protoEnd = u.protocol.length;                 // includes the ':'
          const hashStart = u.hash ? href.length - u.hash.length : OMITTED;
          const searchStart = u.search
            ? (u.hash ? hashStart : href.length) - u.search.length : OMITTED;
          const pathEnd = u.search ? searchStart : (u.hash ? hashStart : href.length);
          const pathStart = pathEnd - u.pathname.length;
          const hostEnd = pathStart - (u.port ? 1 + u.port.length : 0);
          // With credentials host_start points AT the '@': url.js skips it
          // explicitly and slices the password out of the gap before it.
          const hasCred = !!(u.username || u.password);
          const hostStart = hasCred ? href.indexOf('@', protoEnd + 2) : hostEnd - u.hostname.length;
          c[0] = protoEnd;
          c[1] = hasCred ? protoEnd + 2 + u.username.length : hostStart;
          c[2] = hostStart;
          c[3] = hostEnd;
          c[4] = u.port ? Number(u.port) : OMITTED;
          c[5] = pathStart;
          c[6] = searchStart;
          c[7] = hashStart;
          c[8] = SCHEME[u.protocol] === undefined ? 1 : SCHEME[u.protocol];   // 1 = NOT_SPECIAL
          return href;
        },
      };
      return b;
    })(),
    // observerCounts is read as observerCounts[getObserverType(type)] by
    // internal/perf/observe.js hasObserver(); absent, dns.lookup died on
    // "Cannot read properties of undefined (reading 'undefined')".
    performance: { now: () => performance.now(),
      observerCounts: new Uint32Array(16),
      constants: {
        NODE_PERFORMANCE_ENTRY_TYPE_GC: 0, NODE_PERFORMANCE_ENTRY_TYPE_HTTP2: 1,
        NODE_PERFORMANCE_ENTRY_TYPE_HTTP: 2, NODE_PERFORMANCE_ENTRY_TYPE_NET: 3,
        NODE_PERFORMANCE_ENTRY_TYPE_DNS: 4,
        NODE_PERFORMANCE_MILESTONE_TIME_ORIGIN: 0,
      }, milestones: new Float64Array(8), installGarbageCollectionTracking: () => {}, removeGarbageCollectionTracking: () => {}, markMilestone: () => {}, setupObservers: () => {}, timeOrigin: Date.now(), timeOriginTimestamp: Date.now(), loopIdleTime: () => 0, createELDHistogram: () => ({}), nodeTiming: {} },
    trace_events: { trace: () => {}, isTraceCategoryEnabled: () => false, getCategoryEnabledBuffer: () => new Uint8Array(1), setTraceCategoryState: () => {}, trace_category_state: new Uint8Array(1) },
    contextify: {
      // vm. runInThisContext is exact (it is new Function, this realm); runInContext
      // is an approximation over `with (sandbox)` -- see contextify.js for what that
      // does and does not give you. It is NOT isolation, and it does not claim to be.
      ...makeContextify(realm, PRIVATE_SYMBOLS),
      // THE seam where user source becomes a callable. In Node this is V8's
      // CompileFunction; in a browser it is just new Function -- same V8 underneath,
      // same JIT. This is why "native speed" is not an aspiration here.
      // User code must NOT be able to reach the host realm. Real Node relies on the
      // realm's own globals (globalThis.process, globalThis.Buffer); in the walios
      // worker those ARE ours, but in this harness the host's `process` is in scope,
      // so user code saw platform=win32. We shadow the realm globals as parameters,
      // which is what the worker gets for free.
      compileFunctionForCJSLoader: (content, filename) => {
        // EVERY realm global must be shadowed BY NAME. Missing one does not fail --
        // it silently resolves to the HOST's. That is how console.log ended up on the
        // host terminal instead of going through SYS_write, and how process.platform
        // reported win32 before `process` joined this list.
        // Strip a shebang the way node does -- `#!` is not valid JS and new Function
        // rejects the whole file. Replaced with a blank line, not removed, so stack
        // traces keep their line numbers.
        if (content.charCodeAt(0) === 35 && content.charCodeAt(1) === 33) {
          const nl = content.indexOf(String.fromCharCode(10));
          content = nl < 0 ? '' : content.slice(nl);
        }
        // Shadowing as PARAMETERS is not quite what node does: node has these as
        // real globals, which a module-level `const process = ...` may legally
        // shadow. As parameters that same declaration is a redeclaration, and
        // commander died on "Identifier 'process' has already been declared".
        // So: compile, and if V8 names a colliding identifier, drop that one
        // global and retry -- the module then sees its own binding, as under node.
        const GLOBALS = ['process', 'Buffer', 'console', 'setTimeout', 'setInterval', 'setImmediate',
                         'clearTimeout', 'clearInterval', 'globalThis', 'global'];
        const CJS = ['require', 'module', 'exports', '__filename', '__dirname'];
        const valueOf = (n) => (n === 'globalThis' || n === 'global' ? realm.global : realm[n]);
        const gnames = GLOBALS.slice();
        let inner;
        for (;;) {
          try {
            inner = new Function(...gnames, ...CJS, content + String.fromCharCode(10) + '//# sourceURL=' + filename);
            break;
          } catch (e) {
            const m = (e instanceof SyntaxError)
              ? /Identifier '([^']+)' has already been declared/.exec(e.message || '') : null;
            const i = m ? gnames.indexOf(m[1]) : -1;
            if (i < 0) throw e;                     // a real syntax error in the module
            gnames.splice(i, 1);
          }
        }
        const gvals = gnames.map(valueOf);
        function wrapper(exports, require, module, __filename, __dirname) {
          return inner.call(this, ...gvals, require, module, exports, __filename, __dirname);
        }
        return { __proto__: null, function: wrapper, sourceMapURL: undefined, sourceURL: filename, canParseAsESM: false };
      },
        // cjs/loader.js calls this to decide whether a file that failed to parse as
        // CJS is actually ESM, so it must exist before the loader can report any
        // syntax error at all -- axios died on "containsModuleSyntax is not a
        // function" rather than on anything of its own. V8 is the parser: try the
        // source as a CJS function body; if only the ESM-only keywords explain the
        // failure, call it module syntax.
        containsModuleSyntax: (content) => {
          try { new Function(content); return false; }
          catch (_) { return /(^|[;}\n])\s*(import|export)[\s{*]/.test(content) || /\bimport\s*\.\s*meta\b/.test(content); }
        },
      compileFunction: (content, filename, ...rest) => new Function(content),
    },
    // stream_base's shared scratch: node reads read/write results out of this array
    // rather than returning them, so tcp_wrap and the binding must share one copy.
    // Real sockets. node's own lib/net.js and lib/_http_*.js run on top of this, so
    // `net` and `http` stop being modules we own and become modules walios serves.
    tcp_wrap: (() => {
      if (!realm.sys || !realm.mem) return null;       // headless callers without a kernel
      return makeTcpWrap(realm.sys, realm.mem, {
        streamBaseState: STREAM_BASE_STATE,
        kReadBytesOrError: 0, kArrayBufferOffset: 1, kBytesWritten: 2, kLastWriteWasAsync: 3,
        getBuffer: () => realm.Buffer,
        pending: realm.pending,
        trace: (m) => realm.trace && realm.trace('[tcp] ' + m),
        uvErrno: { UV_EOF: -4095 },
      });
    })(),
    // DNS over REAL UDP sockets: the kernel's sockaddr carries only an address, so a
    // guest must resolve names itself. walios serves UDP through wisp, so this speaks
    // actual DNS rather than reaching for fetch.
    cares_wrap: (() => {
      if (!realm.sys || !realm.mem) return null;
      return makeDnsWrap(realm.sys, realm.mem, {
        readFileSync: (p2, e) => realm.readFileSync(p2, e),
        pending: realm.pending,
        servers: ['1.1.1.1', '8.8.8.8'],
      });
    })(),

    // HTTP/1.1 in JS in place of llhttp, driven through node's callback-slot protocol.
    http_parser: makeHttpParser({ getBuffer: () => realm.Buffer }),
    // child_process. Only the SYNC half: spawnSync/execSync/execFileSync. The async
    // path needs process_wrap on the event loop and is not built yet, so
    // child_process.spawn() still fails -- deliberately, rather than half-working.
    // The ASYNC half: pipe_wrap gives child_process real streams and process_wrap
    // polls the exit. Both share tcp_wrap's STREAM_BASE_STATE, because
    // stream_base_commons drives every stream handle through the same array.
    pipe_wrap: PIPE_WRAP,
    process_wrap: (() => {
      if (!PIPE_WRAP) return null;
      return makeProcessWrap(realm.sys, realm.mem, {
        pending: realm.pending,
        Pipe: PIPE_WRAP.Pipe,
        trace: (m) => realm.trace && realm.trace('[proc] ' + m),
      });
    })(),
    spawn_sync: (() => {
      if (!realm.sys || !realm.mem) return null;          // headless callers with no kernel
      return makeChildProcess(realm.sys, realm.mem, {
        getBuffer: () => realm.Buffer,
        trace: (m) => realm.trace && realm.trace('[cp] ' + m),
      });
    })(),

    // isatty(2), via the same ioctl(TCGETS) probe the REPL uses. Packages branch on
    // this constantly (debug colourises only on a terminal).
    tty_wrap: {
      isTTY: (fd) => { try { return !!vfs.isatty(fd); } catch (_) { return false; } },
      guessHandleType: (fd) => { try { return vfs.isatty(fd) ? 'TTY' : 'FILE'; } catch (_) { return 'FILE'; } },
      TTY: class TTY {
        constructor(fd) { this.fd = fd; }
        setRawMode() { return 0; }
        getWindowSize(out) { if (out) { out[0] = 100; out[1] = 30; } return 0; }
        ref() {} unref() {} close(cb) { if (cb) queueMicrotask(cb); return 0; }
      },
    },
    stream_wrap: {
      streamBaseState: STREAM_BASE_STATE,
      kReadBytesOrError: 0, kArrayBufferOffset: 1, kBytesWritten: 2,
      kLastWriteWasAsync: 3, kNumStreamBaseStateFields: 4,
      WriteWrap: function WriteWrap() {}, ShutdownWrap: function ShutdownWrap() {},
    },
    os: { getHostname: () => 'walios', getOSInformation: () => ['Linux', 'walios', '6.0.0-wasm'], getCPUs: () => [], getFreeMem: () => 2 ** 30, getTotalMem: () => 2 ** 31, getUptime: () => performance.now() / 1000, getLoadAvg: (a) => { a[0] = a[1] = a[2] = 0; }, getInterfaceAddresses: () => [], getHomeDirectory: () => '/root', getUserInfo: () => ({ uid: 0, gid: 0, username: 'root', homedir: '/root', shell: '/bin/sh' }), setPriority: () => 0, getPriority: () => 0, getAvailableParallelism: () => 4, isBigEndian: false },
  };

  const stub = (name) => new Proxy({}, {
    get(_t, k) {
      if (typeof k === 'symbol') return undefined;
      miss(name, k);
      return function notImplemented() {
        const e = new Error("[PoC] internalBinding('" + name + "')." + String(k) + '() not implemented');
        e.__poc = true;
        throw e;
      };
    },
    has() { return true; },
  });

  const seen = new Map();
  return function internalBinding(name) {
    trace.bindings.add(name);
    if (seen.has(name)) return seen.get(name);
    let b = table[name];
    if (!b) { trace.stubbed.add(name); b = stub(name); }   // includes tcp_wrap when no kernel
    else {
      b = new Proxy(b, {
        get(t, k) {
          if (typeof k !== 'symbol') { if (k in t) hit(name, k); else miss(name, k); }
          return t[k];
        },
      });
    }
    seen.set(name, b);
    return b;
  };
}
module.exports = { makeBindings };
