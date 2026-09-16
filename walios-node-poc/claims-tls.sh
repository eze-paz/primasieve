# Does tls.connect() actually do TLS in the REAL walios, where tlswrap exists?
# The poc page has no tlswrap, so this can only be answered here.
O=/tmp/t.out; : > $O
echo -n "tlswrap present: " >> $O; (command -v tlswrap || echo ABSENT) >> $O 2>&1
echo -n "tls.connect type: " >> $O; node -e 'console.log(typeof require("tls").connect)' >> $O 2>&1

cat > /tmp/tlsget.js <<'T'
const tls = require('tls');
console.log('STEP:start');
process.on('uncaughtException', (e) => console.log('THREW:' + ((e && e.message) || e)));
const s = tls.connect({ host: 'example.com', port: 443 }, () => {
  console.log('STEP:secureConnect');
  s.write('HEAD / HTTP/1.0\r\nHost: example.com\r\nConnection: close\r\n\r\n');
});
let got = '';
s.setEncoding('utf8');
s.on('data', (d) => { got += d; });
s.on('end', () => console.log('TLS-DIRECT:' + got.split('\r\n')[0]));
s.on('close', () => { if (!got) console.log('TLS-CLOSED-EMPTY'); });
s.on('error', (e) => console.log('TLS-ERR:' + ((e && e.message) || e)));
// Hold the loop open explicitly: if the response only appears WITH this, the read
// path is not keeping the process alive on its own.
const hold = setInterval(() => {}, 250);
setTimeout(() => { clearInterval(hold); console.log('HELD:' + (got ? got.split(String.fromCharCode(13))[0] : 'still-nothing')); }, 8000);
T
node /tmp/tlsget.js >> $O 2>&1

echo '=== RESULT ==='
grep -E 'TLS-DIRECT|TLS-ERR|HELD|THREW|tlswrap present|TLS-CLOSED' $O | tail -4
echo "TLS-DONE"
