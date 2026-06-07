// modules/augmentations.js — Conversation relevance engine
// Auto-registers on window.SandpieAugmentations

if (!window.SandpieAugmentations) {
  window.SandpieAugmentations = {};
}
const A = window.SandpieAugmentations;

/* conv provenance */
const convMeta = new Map();
function getConvMeta(id) {
  if (!convMeta.has(id)) convMeta.set(id, { files: new Set(), scripts: new Set() });
  return convMeta.get(id);
}
A.getConvMeta = getConvMeta;

/* TF-IDF state */
let _tfidfIndex = null, _tfidfKey = '';

function tokenize(t) {
  const m = String(t || '').match(/\p{L}[\p{L}\p{Nd}_]{1,}/gu);
  return m ? m.map(x => x.toLowerCase()) : [];
}

function buildTf(tokens) {
  const tf = new Map(); let mx = 0;
  for (const x of tokens) { tf.set(x, (tf.get(x)||0)+1); mx = Math.max(mx, tf.get(x)); }
  if (mx > 1) for (const [k,v] of tf) tf.set(k, v/mx);
  return tf;
}

async function buildTfidfIndex() {
  const docs = [], tdc = new Map(), kp = [];
  try {
    const d = await (await navigator.storage.getDirectory()).getDirectoryHandle('_conversations');
    for await (const [_,h] of d.entries()) {
      try {
        const data = JSON.parse(await (await h.getFile()).text());
        const body = (data.messages||[]).map(m => m.content||'').join('\n');
        const tokens = tokenize(body), seen = new Set(tokens);
        for (const x of seen) tdc.set(x, (tdc.get(x)||0)+1);
        docs.push({ id: h.name.replace(/\.json$/,''), tf: buildTf(tokens) });
        kp.push(h.name + ':' + (data.messages ? data.messages.length : 0));
      } catch(e) {}
    }
  } catch(e) {}
  const N = docs.length||1;
  const idf = new Map();
  for (const [t,c] of tdc) idf.set(t, Math.log(N/c));
  const vecs = docs.map(d => {
    const v = new Map();
    for (const [t,f] of d.tf) { const i=idf.get(t); if(i) v.set(t,f*i); }
    return { convId: d.id, vec: v };
  });
  _tfidfIndex = { idf, vecs }; _tfidfKey = kp.sort().join('|');
}

function cosine(a,b) {
  let dot=0, na=0, nb=0;
  for (const [t,va] of a) { const vb=b.get(t)||0; dot+=va*vb; na+=va*va; }
  for (const v of b.values()) nb+=v*v;
  const d = Math.sqrt(na)*Math.sqrt(nb);
  return d < 1e-12 ? 0 : dot/d;
}

async function indexKey() {
  const k = [];
  try {
    const d = await (await navigator.storage.getDirectory()).getDirectoryHandle('_conversations');
    for await (const [_,h] of d.entries()) {
      try {
        const data = JSON.parse(await (await h.getFile()).text());
        k.push(h.name + ':' + (data.messages ? data.messages.length : 0));
      } catch(e) {}
    }
  } catch(e) {}
  return k.sort().join('|');
}

async function showRelevance(queryText, activeConvId) {
  const ck = await indexKey();
  if (!_tfidfIndex || _tfidfKey !== ck) await buildTfidfIndex();
  if (!_tfidfIndex || _tfidfIndex.vecs.length < 2) {
    console.log('[sandpie] relevance: not enough convs yet'); return;
  }
  const qTf = buildTf(tokenize(queryText));
  const qVec = new Map();
  for (const [t,f] of qTf) { const i=_tfidfIndex.idf.get(t); if(i) qVec.set(t,f*i); }
  const ranked = _tfidfIndex.vecs
    .filter(d => d.convId !== activeConvId)
    .map(d => ({ id: d.convId, score: cosine(qVec, d.vec) }))
    .filter(d => d.score > 0)
    .sort((a,b) => b.score - a.score);
  if (!ranked.length) { console.log('[sandpie] relevance: no related convs'); return; }

  const top3 = ranked.slice(0,3);
  const scriptCounts = new Map();
  const rows = [];
  for (const {id, score} of top3) {
    const m = getConvMeta(id);
    let c = null;
    try {
      const d = await (await navigator.storage.getDirectory()).getDirectoryHandle('_conversations');
      const h = await d.getFileHandle(id + '.json');
      c = JSON.parse(await (await h.getFile()).text());
    } catch(e) {}
    const sc = m ? [...m.scripts] : [], fi = m ? [...m.files] : [];
    rows.push({ title: c && c.title ? c.title.slice(0,40) : id, score: (+score).toFixed(2), scripts: sc, files: fi });
    for (const s of sc) scriptCounts.set(s, (scriptCounts.get(s)||0)+1);
  }
  const top10 = [...scriptCounts.entries()].sort((a,b)=>b[1]-a[1]).slice(0,10).map(([s])=>s);

  console.group('[sandpie] relevance for ' + activeConvId);
  console.log('query:', (queryText || '').slice(0,80));
  rows.forEach((r,i) => {
    console.log('%c' + (i+1) + '. ' + r.title + ' (score ' + r.score + ')', 'font-weight:bold');
    if (r.files && r.files.length) console.log('   files:', r.files.join(', '));
    if (r.scripts && r.scripts.length) console.log('   scripts:', r.scripts.join(', '));
  });
  if (top10.length) console.log('%cTop scripts: ' + top10.join(', '), 'color:#58a6ff');
  console.groupEnd();
}

A.showRelevance = showRelevance;
