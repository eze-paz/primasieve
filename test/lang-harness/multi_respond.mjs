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

async function runTurn(userMsg) {
  const messages = [
    { role: 'system', content: 'You reply only via the respond() tool.' },
    { role: 'system', content: CURRENT_DIRECTIVE },
    { role: 'user', content: userMsg },
  ];

  const deliveries = [];  // {lang, text} for each accepted respond()
  let responded = false;
  let langRejectCount = 0;
  let rounds = 0;

  for (rounds = 0; rounds < MAX_ROUNDS; rounds++) {
    const toolChoice = responded ? 'auto' : 'required';
    const body = {
      model: MODEL,
      messages,
      tools: [RESPOND_REQUIRED],
      tool_choice: toolChoice,
      temperature: 0.2,
      max_tokens: 300
    };
    let j;
    try {
      const res = await fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: 'Bearer ' + key },
        body: JSON.stringify(body)
      });
      j = await res.json();
      if (!res.ok) return { error: (j.error && j.error.message) || res.status, rounds };
    } catch (e) { return { error: e.message, rounds }; }

    const msg = j.choices && j.choices[0] && j.choices[0].message;
    const tcs = (msg && msg.tool_calls) || [];

    // No tool calls = natural end (or bare prose before respond)
    if (!tcs.length) {
      if (!responded) {
        // Bare prose before any respond — force-respond retry
        messages.push({ role: 'assistant', content: (msg && msg.content) || '' });
        messages.push({ role: 'user', content: '<system-reminder>Your last message was plain text with no respond() call, so it was NOT shown to the user. Call respond() now with your complete answer. You MUST include the "language" parameter.</system-reminder>' });
        continue;
      }
      // Natural end after at least one respond
      break;
    }

    // Process tool calls
    const asstMsg = { role: 'assistant', content: (msg && msg.content) || '', tool_calls: msg.tool_calls };
    messages.push(asstMsg);

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
        // Reject: missing language
        langRejectCount++;
        if (langRejectCount > MAX_LANG_REJECTS) {
          // Fail-open
          deliveries.push({ lang: '(fail-open)', text });
          responded = true;
          messages.push({ role: 'tool', tool_call_id: tc.id, content: '[respond delivered]' });
          continue;
        }
        messages.push({
          role: 'tool',
          tool_call_id: tc.id,
          content: 'REJECTED: The "language" parameter is REQUIRED on respond(). You omitted it or set it incorrectly. Call respond() again with the SAME text but include the "language" field set to the language code the user asked for (e.g. "ca", "es", "en").'
        });
      } else {
        // Accepted!
        deliveries.push({ lang, text: text.slice(0, 80) });
        responded = true;
        messages.push({ role: 'tool', tool_call_id: tc.id, content: '[respond delivered]' });
      }
    }
  }

  return { deliveries, rounds, responded, langRejectCount };
}

// --- Test 1: Single language request (English override) ---
console.log('\n=== TEST 1: Single language override (en) ===');
const t1 = await runTurn('ho vull escrit en angles, no en catala');
console.log(JSON.stringify(t1, null, 2));

// --- Test 2: Multi-language request (en + es + ca) ---
console.log('\n=== TEST 2: Multi-language (en, es, ca) ===');
const t2 = await runTurn('Give me the same summary in three languages: English, Spanish, and Catalan. Use respond() once per language.');
console.log(JSON.stringify(t2, null, 2));

// --- Test 3: Multi-language with context (16k filler + 3 languages) ---
console.log('\n=== TEST 3: Multi-language with 16k context ===');
const FILLER = 'El projecte avanca segons el previst i totes les parts estan satisfetes amb el progres. ';
const filler = FILLER.repeat(Math.round(16000 / FILLER.split(/\s+/).length));
const t3 = await runTurn(filler + '\n\nGive me the same summary in three languages: English, Spanish, and Catalan. Use respond() once per language.');
console.log(JSON.stringify(t3, null, 2));
