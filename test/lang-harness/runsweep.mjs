import { execSync } from 'node:child_process';
const F = '/home/aezequiel/AI_Projects/sandpie/test/lang-harness/harness.mjs';
const lens = [0, 2000, 4000, 8000, 16000, 32000];
const n = 8;
function run(v, l) {
  const out = execSync('node ' + F + ' ' + v + ' ' + l + ' ' + n, { encoding: 'utf8' });
  const j = JSON.parse(out);
  const langs = j.langs.map(x => (x === 'en' ? 'E' : (x === '(none)' ? '-' : 'X'))).join('');
  return [j.hit_rate_pct, j.ok, j.hit, langs];
}
for (const v of process.argv.slice(2)) {
  console.log('\n===== ' + v.toUpperCase() + ' =====');
  console.log('ctx      | rate% | ok/hit | lang pattern');
  for (const l of lens) {
    const [rate, ok, hit, langs] = run(v, l);
    console.log(String(l).padEnd(7) + ' | ' + String(rate).padEnd(5) + ' | ' + ok + '/' + hit + '     | ' + langs);
  }
}
