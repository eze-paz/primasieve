// Dropbox sync pipeline tests.
//
//   node tests/sync/run-tests.mjs
//
// They drive the REAL modules (dbx-token.js, dbx-syncstate.js, dropbox.js and
// the file tools from sandpie-worker.js) over an in-memory OPFS and a fake
// Dropbox API — see harness.mjs.
//
// Two kinds of assertion:
//   ok()    a contract that must hold now AND after the full-Dropbox refactor.
//           Any failure is a regression.
//   known() a behaviour that is currently WRONG. Reported, never fatal. When the
//           refactor fixes one it prints "known bug now FIXED" and should be
//           promoted to ok().
import { runner } from './harness.mjs';
import * as session from './suite-session.mjs';
import * as reload from './suite-reload.mjs';
import * as workers from './suite-workers.mjs';
import * as artifacts from './suite-artifacts.mjs';
import * as multidevice from './suite-multidevice.mjs';
import * as coldread from './suite-coldread.mjs';
import * as engine from './suite-engine.mjs';

const t = runner();
await session.run(t);
await reload.run(t);
await workers.run(t);
await artifacts.run(t);
await multidevice.run(t);
await coldread.run(t);
// Internals of the CURRENT engine. Delete alongside the code they cover.
await engine.run(t);
t.done('sync pipeline');
