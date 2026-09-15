'use strict';
// `worker_threads`, minus the threads.
//
// There are two different things here and conflating them is a mistake I made out loud:
//
//   "implement worker_threads"  -- back Worker with a separate walios process. Node's
//                                  semantics include SharedArrayBuffer and Atomics
//                                  coordination BETWEEN threads, and separate processes
//                                  do not share memory, so that would look like it
//                                  worked and silently not share state. Worse than
//                                  absent.
//   "stop crashing on require"  -- this file. A great many packages do no more than
//                                  `const { isMainThread } = require('worker_threads')`
//                                  to decide whether they are on the main thread. Node's
//                                  own lib/worker_threads.js cannot load here (it pulls
//                                  internal/worker/io, which needs the messaging
//                                  binding), so those packages died at IMPORT over a
//                                  boolean they were only going to read.
//
// So: everything that is genuinely single-threaded is REAL -- MessageChannel,
// MessagePort and BroadcastChannel are the platform's own and work in-realm --
// isMainThread and threadId tell the truth, and anything that actually requires a second
// thread throws a specific, named error instead of pretending.

function makeWorkerThreads(deps) {
  const R = deps && deps.require;

  const unsupported = (what) => {
    const e = new Error(what + ' is not supported in walios: a worker thread would be a '
      + 'separate process here, and separate processes do not share memory -- so '
      + 'SharedArrayBuffer and Atomics coordination between "threads" would silently '
      + 'do nothing. Use child_process (spawn/fork) for parallelism, which is honest '
      + 'about being processes.');
    e.code = 'ERR_WORKER_UNSUPPORTED_OPERATION';
    return e;
  };

  class Worker {
    constructor() { throw unsupported('new Worker()'); }
  }

  const envData = new Map();

  return {
    // True, not a placeholder: this IS the main (and only) thread of this process.
    isMainThread: true,
    isInternalThread: false,
    threadId: 0,
    workerData: null,
    parentPort: null,
    resourceLimits: {},
    SHARE_ENV: Symbol.for('nodejs.worker_threads.SHARE_ENV'),

    Worker,
    // The platform's own, and genuinely functional WITHIN this thread -- which is what
    // a fair amount of code uses them for.
    MessageChannel: (typeof MessageChannel !== 'undefined') ? MessageChannel : class { constructor() { throw unsupported('MessageChannel'); } },
    MessagePort: (typeof MessagePort !== 'undefined') ? MessagePort : class { constructor() { throw unsupported('MessagePort'); } },
    BroadcastChannel: (typeof BroadcastChannel !== 'undefined') ? BroadcastChannel : class { constructor() { throw unsupported('BroadcastChannel'); } },

    getEnvironmentData: (key) => envData.get(key),
    setEnvironmentData: (key, value) => { if (value === undefined) envData.delete(key); else envData.set(key, value); },

    // Only meaningful with more than one thread, so they say so rather than no-op.
    moveMessagePortToContext: () => { throw unsupported('moveMessagePortToContext'); },
    receiveMessageOnPort: () => { throw unsupported('receiveMessageOnPort'); },
    markAsUntransferable: () => {},
    isMarkedAsUntransferable: () => false,
    markAsUncloneable: () => {},
    postMessageToThread: () => { throw unsupported('postMessageToThread'); },
  };
}

module.exports = { makeWorkerThreads };
