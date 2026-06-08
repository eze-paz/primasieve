#!/usr/bin/env node
// Syntax check for .js files, inline <script> blocks in .html, and .json files.
// Run: node scripts/check-syntax.mjs

import { readdirSync, readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { join, extname, relative } from 'node:path';
import { tmpdir } from 'node:os';
import { spawnSync } from 'node:child_process';

const ROOT = process.cwd();
const SKIP_DIRS = new Set(['.git', 'node_modules', '.github']);
let errors = 0;

function* walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (SKIP_DIRS.has(entry.name)) continue;
    const p = join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(p);
    else yield p;
  }
}

const tmpRoot = mkdtempSync(join(tmpdir(), 'syntax-'));
let tmpCounter = 0;

function checkJs(code, label) {
  const file = join(tmpRoot, `s${tmpCounter++}.js`);
  writeFileSync(file, code);
  const r = spawnSync(process.execPath, ['--check', file], { encoding: 'utf8' });
  if (r.status !== 0) {
    // node prints the temp path in errors; replace it with the real label
    const msg = (r.stderr || r.stdout || '').replaceAll(file, label);
    console.error(`FAIL ${label}\n${msg.trim()}\n`);
    errors++;
  }
}

function checkJson(code, label) {
  try {
    JSON.parse(code);
  } catch (e) {
    console.error(`FAIL ${label}: ${e.message}\n`);
    errors++;
  }
}

// Extract inline <script> blocks. Skips external (src=) and non-JS types.
function extractScripts(html) {
  const re = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
  const out = [];
  let m;
  while ((m = re.exec(html)) !== null) {
    const attrs = m[1];
    const body = m[2];
    if (/\bsrc\s*=/i.test(attrs)) continue;
    if (/\btype\s*=\s*["']?(importmap|application\/json|text\/plain|text\/template)/i.test(attrs)) continue;
    const lineOffset = html.slice(0, m.index + m[0].indexOf('>') + 1).split('\n').length;
    out.push({ body, lineOffset });
  }
  return out;
}

try {
  for (const abs of walk(ROOT)) {
    const file = relative(ROOT, abs);
    const ext = extname(file);
    if (ext === '.js' || ext === '.mjs' || ext === '.cjs') {
      checkJs(readFileSync(abs, 'utf8'), file);
    } else if (ext === '.html' || ext === '.htm') {
      const html = readFileSync(abs, 'utf8');
      for (const { body, lineOffset } of extractScripts(html)) {
        // Pad with newlines so error line numbers match the HTML source.
        const padded = '\n'.repeat(lineOffset - 1) + body;
        checkJs(padded, `${file} (inline <script>)`);
      }
    } else if (ext === '.json') {
      checkJson(readFileSync(abs, 'utf8'), file);
    }
  }
} finally {
  rmSync(tmpRoot, { recursive: true, force: true });
}

if (errors > 0) {
  console.error(`${errors} syntax error(s) found.`);
  process.exit(1);
}
console.log('Syntax check passed.');
