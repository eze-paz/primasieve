
const { test, expect } = require('@playwright/test');

const BASE = 'http://localhost:8080';

// Pre-defined LLM responses for each agent turn
const MOCKS = {
  planner: {
    choices: [{
      message: {
        content: '<PLAN>\nStep: Search web for Barcelona beach images\nTool needed: web_search\nExpected outcome: List of Barcelona beach images\n</PLAN>'
      }
    }]
  },
  compressor: {
    choices: [{
      message: {
        content: '<BRIEF>\ngoal: Find Barcelona beach images\ntool: web_search\nparameters: query=Barcelona beach images\nconstraints: none\n</BRIEF>'
      }
    }]
  },
  actor: {
    choices: [{
      message: {
        content: '{"tool":"web_search","arguments":{"query":"Barcelona beach images"}}'
      }
    }]
  },
  evaluator: {
    choices: [{
      message: {
        content: '{"done":true,"state":{"goal":"done","progress":"found images","next":"none","errors":[]},"reasoning":"Task complete"}'
      }
    }]
  }
};

test.beforeAll(async () => {
  // Start static server
  const { exec } = require('child_process');
  const server = exec('npx http-server . -p 8080 -s');
  await new Promise(r => setTimeout(r, 2000));
  global.server = server;
});

test.afterAll(() => {
  if (global.server) global.server.kill();
});

test('agent .md files parse correctly from OPFS', async ({ page }) => {
  let callCount = 0;
  const callLog = [];

  // Route LLM API calls
  await page.route('**/chat/completions', async (route, request) => {
    const body = JSON.parse(request.postData() || '{}');
    const msg = body.messages[body.messages.length - 1].content;
    callLog.push({ idx: callCount++, role: body.messages[0]?.role, contentPreview: msg.slice(0, 80) });

    let mock;
    if (msg.includes('<PLAN>') || msg.includes('PLANNER')) mock = MOCKS.planner;
    else if (msg.includes('<BRIEF>') || msg.includes('COMPRESSOR')) mock = MOCKS.compressor;
    else if (msg.includes('ACTOR') || msg.includes('EXECUTION BRIEF')) mock = MOCKS.actor;
    else if (msg.includes('EVALUATOR')) mock = MOCKS.evaluator;
    else mock = MOCKS.planner; // fallback

    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mock) });
  });

  // 1. Open page
  await page.goto(`${BASE}/sandpie.html`);
  await page.waitForTimeout(2000);

  // 2. Verify page booted
  const hasCore = await page.evaluate(() => typeof window.$ === 'function');
  expect(hasCore).toBe(true);

  // 3. Write agent .md files into OPFS
  const plannerMd = "---\nname: planner\nrole: PLANNER\n---\n# System\nYou are the PLANNER. Decide the single next step.\n# User\nTASK:\n$\{task\}\nCURRENT STATE:\n$\{state\}\nOutput ONLY:\n<PLAN>\nStep: <step>\nTool: <tool>\n</PLAN>";
  const compressorMd = "---\nname: compressor\n---\n# System\nDistill to brief.\n# User\nRAW:\n$\{rawPlan\}\nSTATE:\n$\{state\}\nTOOLS:\n$\{toolSchemas\}\n<BRIEF>goal,tool,params</BRIEF>";
  const actorMd = "---\nname: actor\n---\n# System\nEmit one JSON tool call.\n# User\nBRIEF:\n$\{brief\}\nTOOLS:\n$\{toolSchemas\}\nJSON:{\"tool\":\"...\",\"arguments\":{}}";
  const evaluatorMd = "---\nname: evaluator\n---\n# System\nReview result.\n# User\nTASK:$\{task\}\nBRIEF:$\{brief\}\nRESULT:$\{observation\}\nJSON:{\"done\":bool,\"state\":{},\"reasoning\":\"\"}";

  await page.evaluate(async (files) => {
    for (const [path, content] of files) {
      try { await window.opfs.write(path, content); } catch (e) { console.error('OPFS write failed', path, e); }
    }
  }, [
    ['sandpie/agents/planner.md', plannerMd],
    ['sandpie/agents/compressor.md', compressorMd],
    ['sandpie/agents/actor.md', actorMd],
    ['sandpie/agents/evaluator.md', evaluatorMd],
  ]);

  // 4. Enable zero-shot
  await page.evaluate(() => {
    localStorage.setItem('sandpie:zeroshot:active', '1');
  });
  await page.reload();
  await page.waitForTimeout(1500);

  // 5. Set a simple provider (we mock the API anyway)
  await page.evaluate(() => {
    document.getElementById('endpoint').value = 'http://localhost:8080/fake-api';
    document.getElementById('model').value = 'test-model';
    document.getElementById('apiKey').value = 'test-key';
  });

  // 6. Send prompt
  await page.fill('#input', 'Download a display of barcelona beach');
  await page.press('#input', 'Enter');

  // 7. Wait for turns to process
  await page.waitForTimeout(4000);

  // 8. CHECK: messages array should NOT contain raw .md frontmatter
  const messages = await page.evaluate(() => {
    const s = window.activeStream();
    return s ? s.messages.map(m => ({ role: m.role, content: typeof m.content === 'string' ? m.content.slice(0, 120) : 'complex' })) : [];
  });

  console.log('Messages:', JSON.stringify(messages, null, 2));
  console.log('LLM calls:', JSON.stringify(callLog, null, 2));

  // 9. ASSERT: no raw frontmatter leaked
  for (const m of messages) {
    if (typeof m.content === 'string') {
      expect(m.content).not.toContain('---');
      expect(m.content).not.toContain('name: planner');
      expect(m.content).not.toContain('# System');
      expect(m.content).not.toContain('# User');
    }
  }

  // 10. ASSERT: user message is clean
  const userMsg = messages.find(m => m.role === 'user');
  expect(userMsg).toBeTruthy();
  expect(userMsg.content).toContain('barcelona beach');

  // 11. ASSERT: assistant/tool messages exist (loop ran)
  const asstMsgs = messages.filter(m => m.role === 'assistant');
  expect(asstMsgs.length).toBeGreaterThanOrEqual(1);
  console.log(`Loop produced ${asstMsgs.length} assistant/tool messages`);

  // 12. ASSERT: LLM received clean prompts (not raw .md)
  for (const call of callLog) {
    expect(call.contentPreview).not.toContain('---');
    expect(call.contentPreview).not.toContain('# System');
    expect(call.contentPreview).not.toContain('# User');
  }

  // 13. ASSERT: task variable was substituted (no ${task} left)
  for (const call of callLog) {
    expect(call.contentPreview).not.toContain('${task}');
  }
});
