#!/usr/bin/env node
// =============================================================================
// run_python REPL vs write-then-exec — A/B harness
// -----------------------------------------------------------------------------
// Question: does the model do the task with fewer steps / less token / fewer
// GARBAGE files when run_python takes CODE directly (REPL) instead of forcing
// write_file(script) then run_python(path)?
//
// Two arms, same tasks, same model:
//   A "write-exec": tools = write_file, run_python{path}, respond
//   B "repl":       tools = run_python{code} (+ write_file for real outputs), respond
//
// Each (task, arm) runs an agentic loop: the model calls tools, we execute them
// against a fresh temp working dir (Python via subprocess), feed results back,
// until it calls respond() or hits the turn cap. We score success, tool calls,
// tokens, and files left in the dir that are NOT the requested deliverable.
//
// Model access via env:
//   SANDPIE_AB_URL   full chat/completions URL (OpenAI-compatible)
//   SANDPIE_AB_KEY   bearer token / api key
//   SANDPIE_AB_MODEL model id
// Optional: AB_TASKS (comma ids to subset), AB_MAXTURNS (default 8), AB_OUT.
// =============================================================================
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const URL_ = process.env.SANDPIE_AB_URL;
const KEY = process.env.SANDPIE_AB_KEY || '';
const MODEL = process.env.SANDPIE_AB_MODEL;
const MAX_TURNS = parseInt(process.env.AB_MAXTURNS || '8', 10);
const PY = process.env.AB_PYTHON || 'python';
const OUT = process.env.AB_OUT || path.join(HERE, 'results.json');
if (!URL_ || !MODEL) { console.error('Set SANDPIE_AB_URL and SANDPIE_AB_MODEL (and SANDPIE_AB_KEY).'); process.exit(2); }

let TASKS = JSON.parse(fs.readFileSync(path.join(HERE, 'tasks.json'), 'utf8'));
if (process.env.AB_TASKS) { const want = new Set(process.env.AB_TASKS.split(',')); TASKS = TASKS.filter(t => want.has(t.id)); }

// ---- tool schemas per arm ---------------------------------------------------
const T_WRITE = { type: 'function', function: { name: 'write_file', description: 'Write text to a file in your working folder.', parameters: { type: 'object', properties: { path: { type: 'string' }, content: { type: 'string' } }, required: ['path', 'content'] } } };
const T_RESPOND = { type: 'function', function: { name: 'respond', description: 'Give your final answer to the user. Ends the task.', parameters: { type: 'object', properties: { text: { type: 'string' } }, required: ['text'] } } };
const T_RUN_PATH = { type: 'function', function: { name: 'run_python', description: 'Run a Python script that already exists in your working folder. Save it with write_file first, then pass its path here.', parameters: { type: 'object', properties: { path: { type: 'string' } }, required: ['path'] } } };
const T_RUN_CODE = { type: 'function', function: { name: 'run_python', description: 'Run Python code directly and get its stdout/stderr. Pass the code as a string — no need to save a script first. (write_file is only for producing real output files the user asked for.)', parameters: { type: 'object', properties: { code: { type: 'string' } }, required: ['code'] } } };

// Description A/B (AB_MODE=desc): both arms are REPL `pyodide{code}`; the ONLY
// difference is the tool description — the shipped "mega" text vs a bare minimum.
const DESC_MEGA = `Run Python and get its stdout/stderr. Pass \`code\` to run a snippet DIRECTLY — no need to save a script first (preferred for one-off computation, data inspection, quick transforms). Pass \`path\` instead to run a .py script that already exists in your project. Files the code reads/writes resolve inside this conversation's project folder (relative paths), and reads may also use absolute Dropbox paths. Don't write a script file just to run it once — use \`code\`.`;
const DESC_MIN = `Run Python code.`;
const pyodideTool = (desc) => ({ type: 'function', function: { name: 'pyodide', description: desc, parameters: { type: 'object', properties: { code: { type: 'string' }, path: { type: 'string' }, args: { type: 'array', items: { type: 'string' } } }, required: [] } } });

const MODE = process.env.AB_MODE || 'repl';
const ARMS = MODE === 'desc'
  ? {
      mega:    { tools: [pyodideTool(DESC_MEGA), T_WRITE, T_RESPOND], exec: 'code', pyName: 'pyodide' },
      minimal: { tools: [pyodideTool(DESC_MIN),  T_WRITE, T_RESPOND], exec: 'code', pyName: 'pyodide' },
    }
  : {
      write_exec: { tools: [T_WRITE, T_RUN_PATH, T_RESPOND], exec: 'path', pyName: 'run_python' },
      repl:       { tools: [T_RUN_CODE, T_WRITE, T_RESPOND], exec: 'code', pyName: 'run_python' },
    };
const ARM_NAMES = Object.keys(ARMS);

const SYS = `You are a coding assistant with a Python sandbox. Your working directory already contains any files the user mentions. Use your tools to do the task, then call respond() with the final answer. Be efficient — use as few tool calls as possible. Do not write files unless the task asks you to produce a file.`;

// ---- helpers ----------------------------------------------------------------
function runPy(code, cwd) {
  const tmp = path.join(os.tmpdir(), 'abrepl_' + Math.random().toString(36).slice(2) + '.py');
  fs.writeFileSync(tmp, code);
  try {
    const out = execFileSync(PY, [tmp], { cwd, timeout: 8000, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
    return { ok: true, out };
  } catch (e) {
    return { ok: false, out: (e.stdout || '') + (e.stderr ? '\n--- stderr ---\n' + e.stderr : '') + (e.killed ? '\n[timed out]' : '') };
  } finally { try { fs.unlinkSync(tmp); } catch (_) {} }
}
function listFiles(dir) { const out = []; (function walk(d, rel) { for (const e of fs.readdirSync(d, { withFileTypes: true })) { const r = rel ? rel + '/' + e.name : e.name; if (e.isDirectory()) walk(path.join(d, e.name), r); else out.push(r); } })(dir, ''); return out; }
async function chat(messages, tools) {
  const body = { model: MODEL, messages, tools, tool_choice: 'auto', temperature: 0, stream: false };
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await fetch(URL_, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(KEY ? { Authorization: 'Bearer ' + KEY } : {}) }, body: JSON.stringify(body) });
      if (!res.ok) { const t = await res.text().catch(() => ''); if (res.status === 429 || res.status >= 500) { await new Promise(r => setTimeout(r, 1500 * (attempt + 1))); continue; } throw new Error('HTTP ' + res.status + ': ' + t.slice(0, 300)); }
      return await res.json();
    } catch (e) { if (attempt === 2) throw e; await new Promise(r => setTimeout(r, 1500 * (attempt + 1))); }
  }
}
function checkTask(task, answer, dir) {
  const c = task.check; const ans = String(answer || '').toLowerCase();
  try {
    if (c.type === 'answer_contains') return ans.includes(String(c.value).toLowerCase());
    if (c.type === 'answer_contains_all') return c.value.every(v => ans.includes(String(v).toLowerCase()));
    if (c.type === 'file_lines') { const p = path.join(dir, c.file); if (!fs.existsSync(p)) return false; return fs.readFileSync(p, 'utf8').split('\n').filter(x => x.trim()).length === c.count; }
    if (c.type === 'file_contains') { const p = path.join(dir, c.file); return fs.existsSync(p) && fs.readFileSync(p, 'utf8').includes(String(c.value)); }
  } catch (_) {}
  return false;
}

// ---- one (task, arm) run ----------------------------------------------------
async function runOne(task, armName) {
  const arm = ARMS[armName];
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ab_' + task.id + '_'));
  const setup = task.setup_files || {};
  for (const [f, content] of Object.entries(setup)) fs.writeFileSync(path.join(dir, f), content);
  const setupNames = new Set(Object.keys(setup));
  const messages = [{ role: 'system', content: SYS }, { role: 'user', content: task.prompt }];
  let toolCalls = 0, pyRuns = 0, writes = 0, promptTok = 0, complTok = 0, answer = '', turns = 0, error = '';
  try {
    for (turns = 0; turns < MAX_TURNS; turns++) {
      const resp = await chat(messages, arm.tools);
      if (resp.usage) { promptTok += resp.usage.prompt_tokens || 0; complTok += resp.usage.completion_tokens || 0; }
      const m = resp.choices?.[0]?.message;
      if (!m) { error = 'no message'; break; }
      messages.push(m);
      const calls = m.tool_calls || [];
      if (!calls.length) { // model answered in content without respond()
        if (m.content && m.content.trim()) { answer = m.content.trim(); }
        break;
      }
      let done = false;
      for (const call of calls) {
        toolCalls++;
        let args = {}; try { args = JSON.parse(call.function.arguments || '{}'); } catch (_) {}
        const name = call.function.name;
        let result = '';
        if (name === 'respond') { answer = String(args.text || ''); done = true; result = 'Delivered.'; }
        else if (name === 'write_file') { writes++; try { const fp = path.join(dir, String(args.path || 'file.txt').replace(/^\/+/, '')); fs.mkdirSync(path.dirname(fp), { recursive: true }); fs.writeFileSync(fp, args.content || ''); result = 'Created ' + args.path + ' (' + Buffer.byteLength(args.content || '') + ' bytes)'; } catch (e) { result = 'Write failed: ' + e.message; } }
        else if (name === 'run_python' || name === 'pyodide') {
          pyRuns++;
          let code = '';
          // Prefer inline code when the arm/tool supports it and the model sent it;
          // else run the named script file (write-then-exec arm).
          if (arm.exec === 'code' && String(args.code || '').trim()) { code = String(args.code); }
          else if (args.path) { const fp = path.join(dir, String(args.path).replace(/^\/+/, '')); if (!fs.existsSync(fp)) { result = 'Error: could not read ' + args.path + ' — write it with write_file first.'; messages.push({ role: 'tool', tool_call_id: call.id, content: result }); continue; } code = fs.readFileSync(fp, 'utf8'); }
          else { result = 'Error: pass `code` to run directly, or `path` to run a saved script.'; messages.push({ role: 'tool', tool_call_id: call.id, content: result }); continue; }
          const r = runPy(code, dir);
          result = (r.out || (r.ok ? '(no output)' : 'error')).slice(0, 4000);
        } else { result = 'Unknown tool ' + name; }
        messages.push({ role: 'tool', tool_call_id: call.id, content: result });
      }
      if (done) break;
    }
  } catch (e) { error = String((e && e.message) || e); }
  const success = !error && checkTask(task, answer, dir);
  const files = listFiles(dir).filter(f => !setupNames.has(f));
  const deliverables = new Set(task.deliverables || []);
  const garbage = files.filter(f => !deliverables.has(f));
  try { fs.rmSync(dir, { recursive: true, force: true }); } catch (_) {}
  return { task: task.id, arm: armName, success, turns: turns + 1, toolCalls, pyRuns, writes, tokens: promptTok + complTok, promptTok, complTok, filesCreated: files, garbageFiles: garbage, garbage: garbage.length, error, answer: answer.slice(0, 200) };
}

// ---- main -------------------------------------------------------------------
(async () => {
  console.log(`A/B [${MODE}]: ${TASKS.length} tasks x ${ARM_NAMES.length} arms (${ARM_NAMES.join(', ')}), model=${MODEL}`);
  const results = [];
  for (const task of TASKS) {
    for (const arm of ARM_NAMES) {
      process.stdout.write(`  ${task.id} / ${arm} … `);
      const r = await runOne(task, arm);
      results.push(r);
      console.log(`${r.success ? 'ok' : 'FAIL'}  calls=${r.toolCalls} tok=${r.tokens} garbage=${r.garbage}${r.error ? ' err=' + r.error : ''}`);
    }
  }
  fs.writeFileSync(OUT, JSON.stringify(results, null, 2));
  // Aggregate
  const agg = {};
  for (const arm of ARM_NAMES) {
    const rs = results.filter(r => r.arm === arm);
    agg[arm] = {
      success: rs.filter(r => r.success).length + '/' + rs.length,
      avgToolCalls: +(rs.reduce((a, r) => a + r.toolCalls, 0) / rs.length).toFixed(2),
      avgTokens: Math.round(rs.reduce((a, r) => a + r.tokens, 0) / rs.length),
      totalGarbageFiles: rs.reduce((a, r) => a + r.garbage, 0),
      garbageOnComputeTasks: rs.filter(r => TASKS.find(t => t.id === r.task)?.deliverables.length === 0).reduce((a, r) => a + r.garbage, 0),
    };
  }
  console.log('\n=== SUMMARY ===');
  console.table(agg);
  fs.writeFileSync(OUT.replace(/\.json$/, '.summary.json'), JSON.stringify(agg, null, 2));
  console.log('wrote ' + OUT);
})();
