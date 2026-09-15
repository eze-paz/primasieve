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
      getCallerLocation: () => [], defineLazyProperties: () => {},
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
        flushCompileCache: () => {}, setCompileCacheDir: () => {},
        getCompileCacheDir: () => undefined, enableCompileCache: () => ({ status: 0 }),
        compileCacheStatus: ['FAILED', 'ENABLED', 'ALREADY_ENABLED', 'DISABLED'],
      };
    })(),
    builtins: { builtinIds: [], setInternalLoaders: () => {}, canBeRequiredByUsers: () => true, getCanBeRequiredByUsersWithoutSchemeList: () => [], getCanBeRequiredByUsersList: () => [], hasCachedBuiltins: () => false },
    encoding_binding: {
      encodeInto: (s, u8) => { const r = new TextEncoder().encodeInto(s, u8); return new Uint32Array([r.read, r.written]); },
      encodeUtf8String: (s) => new TextEncoder().encode(s),
      decodeUTF8: (u8) => new TextDecoder().decode(u8),
      toASCII: (s) => s, toUnicode: (s) => s,
    },
    url: { domainToASCII: (s) => s, domainToUnicode: (s) => s, parse: () => undefined, format: () => '', canParse: () => false, pathToFileURL: (p) => 'file://' + p },
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
      ContextifyScript: class {}, makeContext: () => {}, isContext: () => false,
      measureMemory: () => {}, constants: { measureMemory: { mode: {}, execution: {} } },
      startSigintWatchdog: () => {}, stopSigintWatchdog: () => {}, watchdogHasPendingSigint: () => false,
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
        const inner = new Function(
          'process', 'Buffer', 'console', 'setTimeout', 'setInterval', 'setImmediate', 'clearTimeout', 'clearInterval',
          'globalThis', 'global', 'require', 'module', 'exports', '__filename', '__dirname',
          content + '\n//# sourceURL=' + filename);
        function wrapper(exports, require, module, __filename, __dirname) {
          return inner.call(this, realm.process, realm.Buffer, realm.console,
            realm.setTimeout, realm.setInterval, realm.setImmediate, realm.clearTimeout, realm.clearInterval,
            realm.global, realm.global,
            require, module, exports, __filename, __dirname);
        }
        return { __proto__: null, function: wrapper, sourceMapURL: undefined, sourceURL: filename, canParseAsESM: false };
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
