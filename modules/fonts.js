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
  // rebuilds the list from scratch on every modal re-open (onShow), so without
  // this the families would collapse every time the tab is activated.
  const _openFams = new Set();

  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

  // Family from the FILENAME — no byte reads, no hydration, no downloads.
  //   GRAPHIK-BLACKITALIC.ttf      → GRAPHIK   (before the first '-')
  //   GRAPHIKBOLD.ttf              → GRAPHIK   (strip trailing style words)
  //   CALIBRIB / CALIBRII / …      → CALIBRI   (single-letter style suffix)
  // Good enough to cluster a font folder into its families; not a substitute
  // for the real name table when the naming is exotic.
  function familyFromFilename(name) {
    const stem = name.replace(/\.(ttf|otf|ttc)$/i, '').toUpperCase();
    const dash = stem.indexOf('-');
    if (dash > 0) return stem.slice(0, dash);
    const WORDS = ['SEMIBOLD', 'BLACK', 'BOLD', 'MEDIUM', 'LIGHT', 'ITALIC', 'REGULAR'];
    let fam = stem, changed = true;
    while (changed && fam.length > 4) {
      changed = false;
      for (const w of WORDS) {
        if (fam.length > w.length && fam.endsWith(w)) { fam = fam.slice(0, -w.length); changed = true; break; }
      }
    }
    // Calibri single-letter suffixes (B/I/L/Z) — only when the base stays long
    // enough that the bare family name survives (CALIBRI=7 must not become CALIBR).
    if (fam.length >= 8) {
      if (fam.endsWith('LI')) fam = fam.slice(0, -2);
      else if (/[BILZ]$/.test(fam)) fam = fam.slice(0, -1);
    }
    return fam || stem;
  }

  async function listFonts() {
    const names = [];
    try { names.push(...(await opfs._listFontFiles())); } catch (_) {}
    return names.sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()))
      .map(name => ({ name, family: familyFromFilename(name) }));
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
          rn.title = f.name;
          const del = document.createElement('button');
          del.className = 'font-del';
          del.textContent = '\u2715'; del.title = 'Delete font';
          del.onclick = () => deleteFont(f.name);
          row.append(rn, del);
          body.appendChild(row);
        }
        listEl.appendChild(item);
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
