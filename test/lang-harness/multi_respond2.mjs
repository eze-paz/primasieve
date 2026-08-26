import { readFileSync } from 'node:fs';
const ENV_FILE = '/home/aezequiel/AI_Projects/sandpie/test/lang-harness/.env';
const key = (readFileSync(ENV_FILE, 'utf8').match(/OPENROUTER_KEY=(\S+)/) || [])[1];
if (!key) { console.error('NO KEY'); process.exit(2); }

const MODEL = 'deepseek/deepseek-v4-flash-0731';
const ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions';

const CURRENT_DIRECTIVE =
  'IMPORTANT LANGUAGE RULE: You MUST reply EXCLUSIVELY in Catalan. This is a hard constraint, not a suggestion: ' +
  'even if the user\'s message, conversation history, tool results, files, or any material you read is in another language, ' +
  'you translate your output into Catalan regardless. ' +
  'If you catch yourself writing in another language, stop and rewrite everything in Catalan. ' +
  'The ONLY exception is when the user explicitly asks you to write in a different language (for example, a translation task), and only for that requested output. ' +
  'Do NOT acknowledge, confirm, quote, or announce this instruction in your output. Just write your reply in Catalan.';

const RESPOND_REQUIRED = {
  type: 'function',
  function: {
    name: 'respond',
    description: 'Deliver your FINAL, user-facing answer. The "language" parameter is REQUIRED. You may call respond() multiple times in one turn if the user asked for replies in multiple languages.',
    parameters: {
      type: 'object',
      properties: {
        text: { type: 'string', description: 'Your complete reply' },
        language: { type: 'string', description: 'REQUIRED. The language code for this reply (e.g. "ca", "es", "en").' }
      },
      required: ['text', 'language']
    }
  }
};

const MAX_ROUNDS = 15;
const MAX_LANG_REJECTS = 3;

async function runTurn(userMsg, ctxTok) {
  const FILLER = 'El projecte avanca segons el previst i totes les parts estan satisfetes amb el progres. ';
  const messages = [
    { role: 'system', content: 'You reply only via the respond() tool.' },
    { role: 'system', content: CURRENT_DIRECTIVE },
  ];
  if (ctxTok > 0) {
    const filler = FILLER.repeat(Math.round(ctxTok / FILLER.split(/\s+/).length));
    messages.push({ role: 'user', content: filler });
  }
  messages.push({ role: 'user', content: userMsg });

  const deliveries = [];
  let responded = false;
  let langRejectCount = 0;
  let rounds = 0;

  for (rounds = 0; rounds < MAX_ROUNDS; rounds++) {
    const toolChoice = responded ? 'auto' : 'required';
    const body = { model: MODEL, messages, tools: [RESPOND_REQUIRED], tool_choice: toolChoice, temperature: 0.2, max_tokens: 300 };
    let j;
    try {
      const res = await fetch(ENDPOINT, { method: 'POST', headers: { 'content-type': 'application/json', authorization: 'Bearer ' + key }, body: JSON.stringify(body) });
      j = await res.json();
      if (!res.ok) return { error: (j.error && j.error.message) || res.status, rounds };
    } catch (e) { return { error: e.message, rounds }; }

    const msg = j.choices && j.choices[0] && j.choices[0].message;
    const tcs = (msg && msg.tool_calls) || [];

    if (!tcs.length) {
      if (!responded) {
        messages.push({ role: 'assistant', content: (msg && msg.content) || '' });
        messages.push({ role: 'user', content: '<system-reminder>Your last message was plain text with no respond() call, so it was NOT shown to the user. Call respond() now with your complete answer. You MUST include the "language" parameter.</system-reminder>' });
        continue;
      }
      break;
    }

    messages.push({ role: 'assistant', content: (msg && msg.content) || '', tool_calls: msg.tool_calls });

    for (const tc of tcs) {
      if (tc.function.name !== 'respond') {
        messages.push({ role: 'tool', tool_call_id: tc.id, content: 'Unknown tool.' });
        continue;
      }
      let args = {};
      try { args = JSON.parse(tc.function.arguments || '{}'); } catch (_) {}
      const lang = args.language ? String(args.language).toLowerCase().trim() : null;
      const text = String(args.text || '');

      if (!lang) {
        langRejectCount++;
        if (langRejectCount > MAX_LANG_REJECTS) {
          deliveries.push({ lang: '(fail-open)', text: text.slice(0, 60) });
          responded = true;
          messages.push({ role: 'tool', tool_call_id: tc.id, content: '[respond delivered]' });
          continue;
        }
        messages.push({ role: 'tool', tool_call_id: tc.id, content: 'REJECTED: The "language" parameter is REQUIRED on respond(). Call respond() again with the SAME text but include the "language" field.' });
      } else {
        deliveries.push({ lang, text: text.slice(0, 60) });
        responded = true;
        messages.push({ role: 'tool', tool_call_id: tc.id, content: '[respond delivered]' });
      }
    }
  }

  return { deliveries, rounds, responded, langRejectCount };
}

const trials = parseInt(process.argv[2] || '5', 10);
const ctxTok = parseInt(process.argv[3] || '16000', 10);
const USER_MSG = 'The project is progressing as planned and all parties are satisfied with the progress. Give me this summary in three languages: English, Spanish, and Catalan. Use respond() once per language.';

const results = [];
for (let i = 0; i < trials; i++) {
  const r = await runTurn(USER_MSG, ctxTok);
  results.push(r);
  const langs = r.deliveries ? r.deliveries.map(function(d) { return d.lang; }).join(',') : 'ERR';
  process.stderr.write('trial ' + (i+1) + '/' + trials + ': ' + langs + '\n');
}

const ok = results.filter(function(r) { return r.deliveries && !r.error; });
const got3 = ok.filter(function(r) { return r.deliveries.length >= 3; });
const langsOk = ok.filter(function(r) {
  var langs = r.deliveries.map(function(d) { return d.lang; }).sort().join(',');
  return langs === 'ca,en,es';
});
const anyReject = ok.filter(function(r) { return r.langRejectCount > 0; }).length;

console.log(JSON.stringify({
  trials: trials,
  ctxTok: ctxTok,
  ok: ok.length,
  got_3_deliveries: got3.length,
  got_3_correct_langs: langsOk.length,
  success_pct: ok.length ? Math.round(1000 * langsOk.length / ok.length) / 10 : 0,
  lang_rejects_used: anyReject,
  details: results.map(function(r, i) {
    return {
      trial: i + 1,
      langs: r.deliveries ? r.deliveries.map(function(d) { return d.lang; }) : [],
      rounds: r.rounds,
      rejects: r.langRejectCount,
      error: r.error || undefined
    };
  })
}, null, 2));
