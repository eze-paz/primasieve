// TDZ / use-before-init gate: catches "Cannot access 'X' before initialization"
// bugs that node --check (syntax-only) cannot see. Runs ESLint's
// no-use-before-define (variables only — function hoisting is fine) on every
// JS module the app loads. Fails the build only on NEW findings; pre-existing
// ones live in scripts/lint-tdz-baseline.txt so the debt shrinks over time.
// Regenerate the baseline with: node scripts/lint-tdz.mjs --update-baseline
import { ESLint } from 'eslint';
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, relative } from 'node:path';
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
const errors = results.flatMap(r =>
  r.messages
    .filter(m => m.ruleId === 'no-use-before-define')
    .map(m => relative(cwd(), r.filePath) + ':' + m.line + ':' + m.column + '  ' + m.message)
);

const update = process.argv.includes('--update-baseline');
if (update) {
  writeFileSync(BASELINE, errors.map(e => '  ' + e).join('\n') + '\n');
  console.log('baseline updated: ' + errors.length + ' known findings');
  process.exit(0);
}

let known = new Set();
try {
  known = new Set(readFileSync(BASELINE, 'utf8').split('\n').map(s => s.trim()).filter(Boolean));
} catch { /* no baseline yet: everything counts as new */ }

const fresh = errors.filter(e => !known.has(e));
if (fresh.length) {
  console.error('X ' + fresh.length + ' NEW use-before-define (TDZ risk) error(s):\n');
  for (const e of fresh) console.error('  ' + e);
  console.error('\nThese will throw "Cannot access X before initialization" at runtime.');
  console.error('Fix them, or if genuinely pre-existing, refresh the baseline:');
  console.error('  node scripts/lint-tdz.mjs --update-baseline');
  process.exit(1);
}
console.log('OK no NEW use-before-define findings (' + errors.length + ' known/baselined, ' + files.length + ' files checked)');