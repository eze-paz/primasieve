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

  async function listFonts() {
    const names = [];
    try { names.push(...(await opfs._listFontFiles())); } catch (_) {}
    const out = [];
    for (const name of names.sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()))) {
      let size = null, family = '';
      try {
        // Hydrate so the family is readable even for cloud-only fonts.
        const bytes = await opfs.readBytesHydrating(FONTS_DIR + '/' + name);
        if (bytes && bytes.byteLength) {
          size = bytes.byteLength;
          family = fontFamily(bytes);
        }
      } catch (_) {}
      out.push({ name, size, family });
    }
    return out;
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
        const hli = document.createElement('li');
        hli.className = 'font-group';
        hli.textContent = g.family + ' · ' + g.items.length;
        listEl.appendChild(hli);
        for (const f of g.items) {
          const li = document.createElement('li');
          li.className = 'font-row' + (LEGACY_RE.test(f.name) ? ' legacy' : '');
          const name = document.createElement('span');
          name.className = 'font-name'; name.textContent = f.name;
          name.title = f.name + (f.family ? ' (' + f.family + ')' : '');
          const size = document.createElement('span');
          size.className = 'font-size'; size.textContent = fmtSize(f.size);
          const del = document.createElement('button');
          del.className = 'font-del';
          del.textContent = '✕'; del.title = 'Delete font';
          del.onclick = () => deleteFont(f.name);
          li.append(name, size, del);
          listEl.appendChild(li);
        }
      }
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
      head.append(h, countEl);

      // Add-fonts action at the TOP, above the list
      const actions = document.createElement('div');
      actions.className = 'font-actions';
      const add = document.createElement('button');
      add.className = 'act'; add.textContent = '+ Add fonts';
      add.onclick = () => fileInput.click();
      actions.append(add);

      listEl = document.createElement('ul'); listEl.className = 'font-list';

      const note = document.createElement('div');
      note.className = 'font-note'; note.id = 'fontNote'; note.style.display = 'none';


      const fileInput = document.createElement('input');
      fileInput.type = 'file'; fileInput.accept = '.ttf,.otf,.ttc'; fileInput.multiple = true;
      fileInput.style.display = 'none';
      fileInput.onchange = () => { addFiles(fileInput.files); fileInput.value = ''; };

      panel.append(head, actions, listEl, note, fileInput);
    },
    onShow() { refresh(); },
  });
})();
