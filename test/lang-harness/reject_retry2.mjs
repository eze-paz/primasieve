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
    description: 'Deliver your FINAL, user-facing answer. The "language" parameter is REQUIRED.',
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

const FILLER = 'El projecte avanca segons el previst i totes les parts estan satisfetes amb el progres. ';
const CAT_REQUEST = 'ho vull escrit en angles, no en catala';

function fillerTokens(n) {
  const per = FILLER.split(/\s+/).length;
  return FILLER.repeat(Math.max(1, Math.round(n / per)));
}

const MAX_RETRIES = 4;

async function one(trial, ctxTok) {
  const messages = [
    { role: 'system', content: 'You reply only via the respond() tool.' },
    { role: 'system', content: CURRENT_DIRECTIVE },
  ];
  if (ctxTok > 0) messages.push({ role: 'user', content: fillerTokens(ctxTok) });
  messages.push({ role: 'user', content: CAT_REQUEST });

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    const body = {
      model: MODEL,
      messages,
      tools: [RESPOND_REQUIRED],
      tool_choice: 'required',
      temperature: 0.2,
      max_tokens: 120
    };
    let j;
    try {
      const res = await fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: 'Bearer ' + key },
        body: JSON.stringify(body)
      });
      j = await res.json();
      if (!res.ok) return { ok: false, err: (j.error && j.error.message) || res.status, attempt };
    } catch (e) { return { ok: false, err: e.message, attempt }; }

    const msg = j.choices && j.choices[0] && j.choices[0].message;
    const tc = msg && msg.tool_calls && msg.tool_calls[0];

    // Case 1: no tool call at all (bare prose) — simulate force-respond
    if (!tc) {
      const asstMsg = { role: 'assistant', content: (msg && msg.content) || '' };
      messages.push(asstMsg);
      messages.push({ role: 'user', content: '<system-reminder>Your last message was plain text with no respond() call, so it was NOT shown to the user. Call respond() now with your complete answer. You MUST include the "language" parameter. The user asked for English, so set language: "en".</system-reminder>' });
      continue;
    }

    let lang = null, args = '';
    try {
      args = tc.function.arguments || '';
      lang = JSON.parse(args).language || null;
    } catch (_) {}

    if (lang && String(lang).toLowerCase() === 'en') {
      return { ok: true, lang: 'en', attempt, args };
    }

    // Case 2: tool call but missing/wrong language — reject-retry
    const asstMsg = { role: 'assistant', content: (msg && msg.content) || '', tool_calls: msg.tool_calls };
    messages.push(asstMsg);
    messages.push({
      role: 'tool',
      tool_call_id: tc.id,
      content: 'REJECTED: The "language" parameter is REQUIRED on respond(). You omitted it or set it incorrectly. ' +
        'The user explicitly asked for the reply in English. ' +
        'You MUST set language: "en" on your respond() call. Call respond() again with the same text but with language: "en".'
    });
  }
  return { ok: true, lang: 'FAILED_AFTER_RETRIES', attempt: MAX_RETRIES };
}

const ctxTok = parseInt(process.argv[2] || '0', 10);
const trials = parseInt(process.argv[3] || '6', 10);

const out = [];
for (let i = 0; i < trials; i++) out.push(await one(i, ctxTok));

const ok = out.filter(r => r.ok);
const hit = ok.filter(r => r.lang === 'en').length;

console.log(JSON.stringify({
  ctxTok,
  trials,
  ok: ok.length,
  hit,
  hit_rate_pct: ok.length ? Math.round(1000 * hit / ok.length) / 10 : 0,
  langs: out.map(r => r.ok ? (r.lang || '(none)') : 'ERR:' + r.err),
  attempts: out.map(r => r.attempt),
  sample_args: (ok[0] && ok[0].args) || (out[0] && out[0].err)
}, null, 2));
