#!/usr/bin/env node
// =============================================================================
// Decision-point A/B — do MINIMAL tool descriptions change tool SELECTION on a
// real, long, multi-tool sandpie task?
// -----------------------------------------------------------------------------
// Uses a real transcript (default: 400budnp "Analyse the data of ReixachGCO",
// 188 tool-call turns spanning load_skill/recall/write_todos/list_files/search/
// read_file/write_file/run_python/edit_file). At sampled decision points we feed
// the model the EXACT recorded context up to that point and force it to pick its
// NEXT tool (tool_choice:required), once with the shipped MEGA tool descriptions
// and once with MINIMAL ones (first sentence, ~140 chars). We compare each pick
// to (a) the other arm and (b) GROUND TRUTH — the tool the real run actually used
// next. No simulation: the context is the real recorded context.
//
// Metric of interest: agreement with ground truth per arm. If minimal ≈ mega,
// descriptions don't drive tool selection on this task. (Caveat: ground truth was
// generated under mega, so mega has a slight home advantage; a large minimal gap,
// or minimal picking clearly-wrong tools mega got right, is the real signal.)
//
// Env: SANDPIE_AB_URL, SANDPIE_AB_KEY, SANDPIE_AB_MODEL; TRANSCRIPT (path),
// TOOLS_MEGA (path), DP_POINTS (comma turn indices), DP_MAXCTX (char cap/msg).
// =============================================================================
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const URL_ = process.env.SANDPIE_AB_URL, KEY = process.env.SANDPIE_AB_KEY || '', MODEL = process.env.SANDPIE_AB_MODEL;
if (!URL_ || !MODEL) { console.error('set SANDPIE_AB_URL / SANDPIE_AB_MODEL / SANDPIE_AB_KEY'); process.exit(2); }
const TRANSCRIPT = process.env.TRANSCRIPT || path.join(HERE, '400budnp.json');
const TOOLS_MEGA = process.env.TOOLS_MEGA || path.join(HERE, 'tools_mega.json');
const MSG_CAP = parseInt(process.env.DP_MAXCTX || '1200', 10);   // truncate each tool/assistant content
const OUT = process.env.DP_OUT || path.join(HERE, 'dp_results.json');

const transcript = JSON.parse(fs.readFileSync(TRANSCRIPT, 'utf8'));
const megaTools = JSON.parse(fs.readFileSync(TOOLS_MEGA, 'utf8'));

// The B arm's descriptions, controlled by DESC_MODE:
//   'firstsent' (default) — the tool's first sentence, ~140 chars (reproducible ~90% cut)
//   'empty'               — NO description at all (field omitted): tool name + params only
const DESC_MODE = process.env.DESC_MODE || 'firstsent';
const firstSentence = (d) => {
  const s = String(d || '').replace(/\s+/g, ' ').trim();
  const m = s.match(/^.*?[.!](\s|$)/);
  let out = (m ? m[0] : s).trim();
  if (out.length > 150) out = out.slice(0, 147) + '…';
  return out;
};
const minTools = megaTools.map(t => {
  const f = { name: t.function.name, parameters: t.function.parameters };
  if (DESC_MODE !== 'empty') f.description = firstSentence(t.function.description);   // omit entirely when empty
  return { type: 'function', function: f };
});
const megaChars = megaTools.reduce((a, t) => a + t.function.description.length, 0);
const minChars = minTools.reduce((a, t) => a + (t.function.description || '').length, 0);

// Truncate a message's content for the replay prefix (applied equally to both arms).
function trunc(msg) {
  const m = { ...msg };
  if (typeof m.content === 'string' && m.content.length > MSG_CAP) m.content = m.content.slice(0, MSG_CAP) + '\n…[truncated]';
  return m;
}
// Build the OpenAI prefix ending just before assistant message at index `idx`,
// and the ground-truth tool names that assistant message issued. Bounded to
// system + first user turn + the last WINDOW messages (so late decision points
// don't blow the context window); the same window is used for both arms, so the
// comparison stays fair. A tool message must not lead the tail (an orphan tool
// result with no preceding tool_call errors), so the window starts on a
// non-tool message.
const WINDOW = parseInt(process.env.DP_WINDOW || '28', 10);
function pointAt(idx) {
  const head = [transcript[0], transcript[1]].filter(Boolean).map(trunc);   // system + first user
  let start = Math.max(2, idx - WINDOW);
  while (start < idx && transcript[start].role === 'tool') start++;          // don't start on an orphan tool result
  const tail = transcript.slice(start, idx).map(trunc);
  const truth = (transcript[idx].tool_calls || []).map(tc => tc.function.name);
  return { prefix: [...head, ...tail], truth };
}

// The indices of assistant messages that issued tool_calls. DP_MAXIDX bounds the
// sample to a single-prompt segment (decision points before the 2nd user turn).
const MAXIDX = parseInt(process.env.DP_MAXIDX || String(transcript.length), 10);
const dpIdx = [];
for (let i = 0; i < transcript.length && i < MAXIDX; i++) if (transcript[i].role === 'assistant' && Array.isArray(transcript[i].tool_calls) && transcript[i].tool_calls.length) dpIdx.push(i);
// Sample ~12 spread across the run (env override: DP_POINTS = comma indices into dpIdx).
let picks;
if (process.env.DP_POINTS) picks = process.env.DP_POINTS.split(',').map(n => parseInt(n, 10));
else { const N = 12, step = Math.max(1, Math.floor(dpIdx.length / N)); picks = []; for (let k = 0; k < dpIdx.length && picks.length < N; k += step) picks.push(k); }

async function chat(messages, tools) {
  const body = { model: MODEL, messages, tools, tool_choice: 'required', temperature: 0, stream: false };
  for (let a = 0; a < 3; a++) {
    try {
      const res = await fetch(URL_, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(KEY ? { Authorization: 'Bearer ' + KEY } : {}) }, body: JSON.stringify(body) });
      if (!res.ok) { const t = await res.text().catch(() => ''); if (res.status === 429 || res.status >= 500) { await new Promise(r => setTimeout(r, 1500 * (a + 1))); continue; } return { error: 'HTTP ' + res.status + ': ' + t.slice(0, 200) }; }
      return await res.json();
    } catch (e) { if (a === 2) return { error: String(e.message || e) }; await new Promise(r => setTimeout(r, 1500 * (a + 1))); }
  }
}
const pickName = (resp) => { const tc = resp?.choices?.[0]?.message?.tool_calls?.[0]; return tc ? tc.function.name : (resp?.error ? 'ERR:' + resp.error.slice(0, 40) : '(none)'); };

(async () => {
  console.log(`Decision-point A/B — ${TRANSCRIPT.split(/[\\/]/).pop()}, ${picks.length} points (single-prompt≤${MAXIDX}), model=${MODEL}`);
  console.log(`B arm = ${DESC_MODE.toUpperCase()} descriptions. tool desc chars: full=${megaChars} B=${minChars} (${Math.round(100 - 100 * minChars / megaChars)}% smaller)\n`);
  const rows = [];
  let megaHit = 0, minHit = 0, agree = 0, tokMega = 0, tokMin = 0;
  for (const k of picks) {
    const idx = dpIdx[k];
    const { prefix, truth } = pointAt(idx);
    const rM = await chat(prefix, megaTools);
    const rN = await chat(prefix, minTools);
    const pM = pickName(rM), pN = pickName(rN);
    tokMega += rM?.usage?.prompt_tokens || 0; tokMin += rN?.usage?.prompt_tokens || 0;
    const truthHit = (p) => truth.includes(p);
    if (truthHit(pM)) megaHit++; if (truthHit(pN)) minHit++; if (pM === pN) agree++;
    rows.push({ turn: k, idx, truth: truth.join('+'), mega: pM, minimal: pN, megaOK: truthHit(pM), minOK: truthHit(pN), same: pM === pN });
    console.log(`  turn ${String(k).padStart(3)}  truth=${truth.join('+').padEnd(13)} mega=${pM.padEnd(14)} min=${pN.padEnd(14)} ${pM === pN ? '=' : '≠'} ${truthHit(pM) ? 'M✓' : 'M✗'} ${truthHit(pN) ? 'N✓' : 'N✗'}`);
  }
  const n = picks.length;
  const summary = {
    points: n,
    // HEADLINE: given identical real context, do the two description regimes lead
    // to the same next tool? High = minimization doesn't change selection.
    megaVsMinimalAgree: agree + '/' + n,
    // Secondary (noisy oracle — ground truth was generated under mega, with
    // thinking + temperature the forced-choice replay can't reproduce):
    megaMatchesGroundTruth: megaHit + '/' + n,
    minimalMatchesGroundTruth: minHit + '/' + n,
    avgPromptTokens: { mega: Math.round(tokMega / n), minimal: Math.round(tokMin / n) },
    toolDescChars: { mega: megaChars, minimal: minChars },
  };
  console.log('\n=== SUMMARY ==='); console.table([summary].reduce((o, s) => (Object.assign(o, s), o), {}));
  console.log(JSON.stringify(summary, null, 1));
  fs.writeFileSync(OUT, JSON.stringify({ summary, rows }, null, 2));
  console.log('wrote ' + OUT);
})();
