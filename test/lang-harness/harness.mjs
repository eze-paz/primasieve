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

const OPTION3_DIRECTIVE = CURRENT_DIRECTIVE +
  '\n\nADDITIONAL RULE (option-3): The INSTANT the user\'s current message explicitly asks for a NON-DEFAULT language for this specific reply/deliverable, you MUST set an explicit "language" argument on your respond() call exactly matching what they asked (e.g. language: "en" for English). That per-deliverable override wins for that one output only. Otherwise the default language rule above applies.';

const RESPOND = {
  type: 'function',
  function: {
    name: 'respond',
    description: 'Deliver your final user-facing answer. Ends the turn.',
    parameters: {
      type: 'object',
      properties: {
        text: { type: 'string', description: 'Your complete reply' },
        language: { type: 'string', description: 'Optional language code override for this reply only' }
      },
      required: ['text']
    }
  }
};

const FILLER = 'El projecte avança segons el previst i totes les parts estan satisfetes amb el progrés. ';
const CAT_REQUEST = 'ho vull escrit en anglès, no en català';

const variant = process.argv[2] || 'current';
const ctxTok  = parseInt(process.argv[3] || '0', 10);
const trials  = parseInt(process.argv[4] || '5', 10);

function fillerTokens(n) {
  const per = FILLER.split(/\s+/).length;
  return FILLER.repeat(Math.max(1, Math.round(n / per)));
}

async function one(trial) {
  const messages = [{ role: 'system', content: 'You reply only via the respond() tool.' }];
  messages.push({ role: 'system', content: variant === 'current' ? CURRENT_DIRECTIVE : OPTION3_DIRECTIVE });
  if (ctxTok > 0) messages.push({ role: 'user', content: fillerTokens(ctxTok) });
  messages.push({ role: 'user', content: CAT_REQUEST });
  const body = { model: MODEL, messages, tools: [RESPOND], tool_choice: 'required', temperature: 0.2, max_tokens: 120 };
  let j;
  try {
    const res = await fetch(ENDPOINT, { method: 'POST', headers: { 'content-type': 'application/json', authorization: 'Bearer ' + key }, body: JSON.stringify(body) });
    j = await res.json();
    if (!res.ok) return { ok: false, err: (j.error && j.error.message) || res.status };
  } catch (e) { return { ok: false, err: e.message }; }
  const tc = j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.tool_calls;
  if (!tc || !tc[0]) return { ok: true, lang: null, finish: j.choices[0] && j.choices[0].finish_reason };
  let lang = null; let args = '';
  try { args = tc[0].function.arguments || ''; lang = JSON.parse(args).language || null; } catch (_) {}
  return { ok: true, lang, args, trial };
}

const out = [];
for (let i = 0; i < trials; i++) out.push(await one(i));
const ok = out.filter(r => r.ok);
const hit = ok.filter(r => r.lang && String(r.lang).toLowerCase() === 'en').length;
console.log(JSON.stringify({
  variant, ctxTok, trials, ok: ok.length, hit,
  hit_rate_pct: ok.length ? Math.round(1000 * hit / ok.length) / 10 : 0,
  langs: out.map(r => r.ok ? (r.lang || '(none)') : 'ERR:' + r.err),
  sample_args: (ok[0] && ok[0].args) || (out[0] && out[0].err)
}, null, 2));