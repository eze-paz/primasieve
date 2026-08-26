import { execSync } from 'node:child_process';
// Self-contained: no shell $var substitution issues; values baked in.
const F = '/home/aezequiel/AI_Projects/sandpie/test/lang-harness/harness.mjs';
const lens = [0, 2000, 4000, 8000, 16000, 32000];
const N = 6;
function run(v, l) {
  const out = execSync('node ' + F + ' ' + v + ' ' + l + ' ' + N, { encoding: 'utf8', timeout: 120000 });
  const j = JSON.parse(out);
  const langs = j.langs.map(function (x) { return (x === 'en' ? 'E' : (x === '(none)' ? '-' : 'X')); }).join('');
  return ['rate=' + j.hit_rate_pct + '%', 'ok=' + j.ok + ' hit=' + j.hit, langs];
}
let csv = [];
for (const v of process.argv.slice(2)) {
  for (const l of lens) {
    let rec;
    try { rec = run(v, l); } catch (e) { rec = ['ERR ' + e.message, '', '']; }
    console.log(v.padEnd(8) + ' ctx=' + String(l).padEnd(6) + ' ' + rec[0].padEnd(9) + ' ' + rec[1].padEnd(12) + ' [' + rec[2] + ']');
    csv.push(v + ',' + l + ',' + rec[0]);
  }
}
console.log('\nCSV:'); console.log(csv.join('\n'));