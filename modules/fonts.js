// fonts.js — Settings → Fonts tab.
//
// Lists the fonts in sandpie/fonts/ (the ones the in-app document converter
// injects into LibreOffice), lets the user add more (.ttf/.otf/.ttc) and delete
// the ones they don't want. Registers via the settings registry (classic
// script, loaded after settings.js + opfs.js).
//
// Delete uses the canonical page-side path: opfs.remove() (which throws on a
// dehydrated cloud-only file — ignored), then ALWAYS emit 'file:deleted' so the
// sync layer issues Dropbox delete_v2 and drops the cloud-index placeholder.
(function () {
  if (typeof SandpieSettings === 'undefined' || !SandpieSettings.register) return;
  const FONTS_DIR = 'sandpie/fonts';
  const LEGACY_RE = /\.(OTF\.orig|OTF\.cffdisabled)$/i;   // conversion leftovers, never loaded

  let listEl = null, countEl = null, busy = false, panelEl = null;
  // Family groups the user has EXPANDED (normalized family key → true). refresh()
  // rebuilds the list from scratch, so without this the background hydration
  // re-render would collapse every family the moment after you open it.
  const _openFams = new Set();

  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function fmtSize(b) { if (!b && b !== 0) return ''; if (b < 1024) return b + ' B'; if (b < 1048576) return (b / 1024).toFixed(0) + ' KB'; return (b / 1048576).toFixed(1) + ' MB'; }

  // Reliable family identifier: the font's internal 'name' table, NOT the
  // filename. Prefer NameID 16 (typographic family), fall back to NameID 1
  // (family). NameID 4 is the full name (e.g. "Graphik Regular") and must not
  // be used as the group key.
  function fontFamily(bytes) {
    try {
      const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      let base = 0;
      if (dv.getUint32(0) === 0x74746366) base = dv.getUint32(12);   // 'ttcf' → first font
      const numTables = dv.getUint16(base + 4);
      let nameOff = 0;
      for (let i = 0; i < numTables; i++) {
        const rec = base + 12 + i * 16;
        if (dv.getUint32(rec) === 0x6e616d65) { nameOff = dv.getUint32(rec + 8); break; }   // 'name'
      }
      if (!nameOff) return '';
      const count = dv.getUint16(nameOff + 2);
      const strBase = nameOff + dv.getUint16(nameOff + 4);
      for (const want of [16, 1]) {
        for (let i = 0; i < count; i++) {
          const r = nameOff + 6 + i * 12;
          const platform = dv.getUint16(r), nameId = dv.getUint16(r + 6);
          if (nameId !== want) continue;
          const len = dv.getUint16(r + 8), o = strBase + dv.getUint16(r + 10);
          let s = '';
          if (platform === 3 || platform === 0) { for (let j = 0; j + 1 < len; j += 2) s += String.fromCharCode(dv.getUint16(o + j)); }
          else { for (let j = 0; j < len; j++) s += String.fromCharCode(dv.getUint8(o + j)); }
          s = s.replace(/\0/g, '').trim();
          if (s) return s;
        }
      }
      return '';
    } catch (_) { return ''; }
  }

  // Phase 1: read LOCAL bytes only — instant, never blocks on downloads.
  // Phase 2 (background, parallel, time-limited): hydrate cloud-only fonts so
  // their family/size fill in. A stuck hydration times out and the row stays
  // under 'Other' rather than hanging the whole list.
  const HYDRATE_TIMEOUT_MS = 8000;

  async function listFonts() {
    const names = [];
    try { names.push(...(await opfs._listFontFiles())); } catch (_) {}
    const out = [];
    for (const name of names.sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()))) {
      let size = null, family = '';
      try {
        const bytes = await opfs.readBytes(FONTS_DIR + '/' + name);
        if (bytes && bytes.byteLength) { size = bytes.byteLength; family = fontFamily(bytes); }
      } catch (_) {}
      out.push({ name, size, family, local: size != null });
    }
    return out;
  }

  async function hydrateOne(f) {
    if (f.local) return f;
    try {
      const bytes = await Promise.race([
        opfs.readBytesHydrating(FONTS_DIR + '/' + f.name),
        new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), HYDRATE_TIMEOUT_MS)),
      ]);
      if (bytes && bytes.byteLength) { f.size = bytes.byteLength; f.family = fontFamily(bytes); f.local = true; }
    } catch (_) {}
    return f;
  }

  // Fill in families/sizes for cloud-only fonts in parallel, then re-render ONCE
  // — and only if something changed (avoids collapsing families that are open).
  async function hydrateInBackground(fonts) {
    const pending = fonts.filter(f => !f.local);
    if (!pending.length) return;
    await Promise.allSettled(pending.map(hydrateOne));
    if (pending.some(f => f.local) && listEl && listEl.isConnected) refresh();
  }

  async function refresh() {
    if (!listEl || busy) return; busy = true;
    try {
      const fonts = await listFonts();
      countEl.textContent = fonts.length + ' font' + (fonts.length === 1 ? '' : 's');
      listEl.replaceChildren();
      if (!fonts.length) {
        const li = document.createElement('li');
        li.className = 'font-row font-empty';
        li.textContent = 'No fonts yet — drop .ttf / .otf files here, or use “Add fonts”.';
        listEl.appendChild(li);
        return;
      }
      // Group by internal family name; unknown-family fonts go under 'Other'.
      const groups = new Map();
      for (const f of fonts) {
        const fam = f.family || 'Other';
        const key = fam.toLowerCase().replace(/[^a-z0-9]+/g, '');
        if (!groups.has(key)) groups.set(key, { family: fam, items: [] });
        groups.get(key).items.push(f);
      }
      for (const g of [...groups.values()].sort((a, b) => a.family.localeCompare(b.family))) {
        // Collapsed sp-item per family (same pattern as system-prompt.js):
        // head = family + count + caret, body = font rows, hidden until clicked.
        const famKey = g.family.toLowerCase().replace(/[^a-z0-9]+/g, '');
        const wasOpen = _openFams.has(famKey);
        const item = document.createElement('div');
        item.className = 'sp-item';
        const head = document.createElement('div');
        head.className = 'sp-item-head';
        const name = document.createElement('span');
        name.className = 'sp-item-name'; name.textContent = g.family;
        const meta = document.createElement('span');
        meta.className = 'sp-item-meta'; meta.textContent = String(g.items.length);
        const caret = document.createElement('span');
        caret.className = 'sp-caret'; caret.textContent = wasOpen ? '\u25be' : '\u25b8';   // ▾ / ▸
        head.append(name, meta, caret);
        const body = document.createElement('div');
        body.className = 'sp-item-body'; body.style.display = wasOpen ? '' : 'none';
        item.append(head, body);
        head.addEventListener('click', () => {
          const open = body.style.display === 'none';
          body.style.display = open ? '' : 'none';
          caret.textContent = open ? '\u25be' : '\u25b8';   // ▾ / ▸
          if (open) _openFams.add(famKey); else _openFams.delete(famKey);
        });
        for (const f of g.items) {
          const row = document.createElement('div');
          row.className = 'font-row' + (LEGACY_RE.test(f.name) ? ' legacy' : '');
          const rn = document.createElement('span');
          rn.className = 'font-name'; rn.textContent = f.name;
          rn.title = f.name + (f.family ? ' (' + f.family + ')' : '');
          const size = document.createElement('span');
          size.className = 'font-size'; size.textContent = fmtSize(f.size);
          const del = document.createElement('button');
          del.className = 'font-del';
          del.textContent = '\u2715'; del.title = 'Delete font';
          del.onclick = () => deleteFont(f.name);
          row.append(rn, size, del);
          body.appendChild(row);
        }
        listEl.appendChild(item);
      }
      // Non-blocking: hydrate cloud-only fonts in the background; when done it
      // re-renders with real families/sizes.
      hydrateInBackground(fonts);
    } catch (e) { console.warn('[fonts] refresh failed:', e); }
    finally { busy = false; }
  }

  async function deleteFont(name) {
    if (!confirm('Delete font "' + name + '" from sandpie/fonts? This also removes its cloud copy.')) return;
    const rel = FONTS_DIR + '/' + name;
    try { await opfs.remove(rel); } catch (_) {}          // dehydrated → NotFoundError, fine
    try { Sandpie.events.emit('file:deleted', rel); } catch (_) {}  // → Dropbox delete_v2
    await refresh();
  }

  async function addFiles(fileList) {
    if (!fileList || !fileList.length) return;
    let added = 0, skipped = 0;
    for (const file of fileList) {
      const name = file.name.replace(/[^A-Za-z0-9._-]/g, '_');
      if (!/\.(ttf|otf|ttc)$/i.test(name)) { skipped++; continue; }
      try {
        const bytes = new Uint8Array(await file.arrayBuffer());
        await opfs.write(FONTS_DIR + '/' + name, bytes);
        try { Sandpie.events.emit('file:changed', FONTS_DIR + '/' + name); } catch (_) {}
        added++;
      } catch (e) { console.warn('[fonts] add failed:', name, e); }
    }
    await refresh();
    // LibreOffice caches its font list at boot — the README's "click Retry" note.
    const msg = added ? 'Added ' + added + ' font' + (added === 1 ? '' : 's') + (skipped ? ' (' + skipped + ' skipped: only .ttf/.otf/.ttc)' : '') + '. Click Retry in the converter to pick them up.'
                     : (skipped ? 'Nothing added — only .ttf/.otf/.ttc files are accepted.' : 'No files selected.');
    const note = document.getElementById('fontNote');
    if (note) { note.textContent = msg; note.style.display = ''; }
  }

  SandpieSettings.register({
    id: 'fonts', title: 'Fonts', order: 44,
    render(panel) {
      panelEl = panel;
      panel.innerHTML = '';
      const head = document.createElement('div');
      head.className = 'share-head';
      const h = document.createElement('h3'); h.textContent = 'Fonts';
      countEl = document.createElement('span'); countEl.className = 'share-total';
      // Add-fonts action lives in the header row, right of the count
      const add = document.createElement('button');
      add.className = 'act font-add-btn'; add.textContent = '+ Add fonts';
      add.onclick = () => fileInput.click();
      head.append(h, countEl, add);

      listEl = document.createElement('div'); listEl.className = 'font-list';

      const note = document.createElement('div');
      note.className = 'font-note'; note.id = 'fontNote'; note.style.display = 'none';


      const fileInput = document.createElement('input');
      fileInput.type = 'file'; fileInput.accept = '.ttf,.otf,.ttc'; fileInput.multiple = true;
      fileInput.style.display = 'none';
      fileInput.onchange = () => { addFiles(fileInput.files); fileInput.value = ''; };

      panel.append(head, listEl, note, fileInput);
    },
    onShow() { refresh(); },
  });
})();
