// TDZ / use-before-init gate: catches "Cannot access 'X' before initialization"
// bugs that node --check (syntax-only) cannot see. Runs ESLint's
// no-use-before-define (variables only — function hoisting is fine) on every
// JS module the app loads. Fails the build only on NEW findings; pre-existing
// ones live in scripts/lint-tdz-baseline.txt so the debt shrinks over time.
// Regenerate the baseline with: node scripts/lint-tdz.mjs --update-baseline
//
// Baseline identity is (file + message) WITHOUT line:column. Line numbers shift
// on every unrelated edit above a finding, so every baselined entry read as
// "new" on the next commit and the gate failed on literally every push. The
// trade: a second misuse of an already-baselined symbol in the same file slips
// through. Worth it - a gate that always fails is a gate everyone ignores.
import { ESLint } from 'eslint';
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { cwd } from 'node:process';

const MODULES = 'modules';
const BASELINE = 'scripts/lint-tdz-baseline.txt';
const files = readdirSync(MODULES)
  .filter(f => f.endsWith('.js') && !f.endsWith('.min.js'))
  .map(f => join(MODULES, f));

const eslint = new ESLint({
  cwd: process.cwd(),
  overrideConfigFile: true,
  overrideConfig: [{
    files: ['modules/**/*.js'],
    languageOptions: { ecmaVersion: 2022, sourceType: 'module' },
    plugins: {},
    rules: {
      // variables:true is the TDZ catcher; functions/classes hoist safely
      'no-use-before-define': ['error', { functions: false, classes: false, variables: true }],
    },
  }],
});

const results = await eslint.lintFiles(files);
const findings = results.flatMap(r => {
  // Normalise separators: relative() yields backslashes on Windows and forward
  // slashes on the Linux runner, so an unnormalised path never matches locally.
  const file = relative(cwd(), r.filePath).split(sep).join('/');
  return r.messages
    .filter(m => m.ruleId === 'no-use-before-define')
    .map(m => ({
      key: file + '  ' + m.message,
      label: file + ':' + m.line + ':' + m.column + '  ' + m.message,
    }));
});

const update = process.argv.includes('--update-baseline');
if (update) {
  const keys = [...new Set(findings.map(f => f.key))].sort();
  writeFileSync(BASELINE, keys.map(k => '  ' + k).join('\n') + '\n');
  console.log('baseline updated: ' + keys.length + ' known finding(s)');
  process.exit(0);
}

let known = new Set();
try {
  known = new Set(readFileSync(BASELINE, 'utf8').split('\n').map(s => s.trim()).filter(Boolean));
} catch { /* no baseline yet: everything counts as new */ }

const fresh = findings.filter(f => !known.has(f.key));
if (fresh.length) {
  console.error('X ' + fresh.length + ' NEW use-before-define (TDZ risk) error(s):\n');
  for (const f of fresh) console.error('  ' + f.label);
  console.error('\nThese will throw "Cannot access X before initialization" at runtime.');
  console.error('Fix them, or if genuinely pre-existing, refresh the baseline:');
  console.error('  node scripts/lint-tdz.mjs --update-baseline');
  process.exit(1);
}
console.log('OK no NEW use-before-define findings (' + findings.length + ' known/baselined, ' + files.length + ' files checked)');