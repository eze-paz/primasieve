// Scripted mock of an OpenAI-compatible chat/completions endpoint, to smoke-test
// the A/B harness without a real model. It detects the arm from the tool schema
// (run_python has `code` = repl, else write-exec) and plays a canned, correct
// interaction for whichever task it sees — Arm A writes a script then execs it
// (leaving a .py garbage file for compute tasks), Arm B runs code directly.
import http from 'node:http';
let step = new Map();   // conversation fingerprint -> step index
const tc = (name, args) => ({ id: 'c' + Math.random().toString(36).slice(2, 8), type: 'function', function: { name, arguments: JSON.stringify(args) } });
const msg = (tool_calls, content) => ({ choices: [{ message: { role: 'assistant', content: content || null, tool_calls } }], usage: { prompt_tokens: 100, completion_tokens: 30 } });

const server = http.createServer((req, res) => {
  let body = ''; req.on('data', d => body += d); req.on('end', () => {
    const b = JSON.parse(body);
    const repl = b.tools.some(t => t.function.name === 'run_python' && t.function.parameters.properties.code);
    const user = b.messages.find(m => m.role === 'user')?.content || '';
    const key = (repl ? 'R' : 'W') + '|' + user.slice(0, 20);
    const s = step.get(key) || 0; step.set(key, s + 1);
    const primes = 'code = "print(sum(1 for n in range(2,1000) if all(n%d for d in range(2,int(n**0.5)+1))))"';
    let out;
    if (/prime/i.test(user)) {
      const code = 'print(sum(1 for n in range(2,1000) if all(n%d for d in range(2,int(n**0.5)+1))))';
      if (repl) { out = s === 0 ? msg([tc('run_python', { code })]) : msg([tc('respond', { text: 'There are 168 primes below 1000.' })]); }
      else { out = s === 0 ? msg([tc('write_file', { path: 'primes.py', content: code })]) : s === 1 ? msg([tc('run_python', { path: 'primes.py' })]) : msg([tc('respond', { text: 'There are 168 primes below 1000.' })]); }
    } else if (/random_numbers/i.test(user)) {
      const code = 'import random\nwith open("random_numbers.txt","w") as f:\n    f.write("\\n".join(str(random.randint(1,100)) for _ in range(62)))';
      if (repl) { out = s === 0 ? msg([tc('run_python', { code })]) : msg([tc('respond', { text: 'Saved 62 numbers to random_numbers.txt.' })]); }
      else { out = s === 0 ? msg([tc('write_file', { path: 'gen.py', content: code })]) : s === 1 ? msg([tc('run_python', { path: 'gen.py' })]) : msg([tc('respond', { text: 'Saved 62 numbers to random_numbers.txt.' })]); }
    } else { out = msg([tc('respond', { text: 'done' })]); }
    res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(out));
  });
});
server.listen(8199, () => console.log('mock on http://127.0.0.1:8199'));
