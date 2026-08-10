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

  async function listFonts() {
    const names = [];
    try { names.push(...(await opfs._listFontFiles())); } catch (_) {}
    const out = [];
    for (const name of names.sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()))) {
      let size = null, fams = [];
      try {
        // Local bytes (no forced hydration — a cloud-only font just shows as such).
        const bytes = await opfs.readBytes(FONTS_DIR + '/' + name);
        if (bytes && bytes.byteLength) {
          size = bytes.byteLength;
          try { fams = opfs._fontFamilyNames(bytes) || []; } catch (_) {}
        }
      } catch (_) {}
      out.push({ name, size, fams, cloudOnly: size == null });
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
      for (const f of fonts) {
        const li = document.createElement('li');
        li.className = 'font-row' + (LEGACY_RE.test(f.name) ? ' legacy' : '');
        const name = document.createElement('span');
        name.className = 'font-name'; name.textContent = f.name;
        name.title = f.name;
        const fam = document.createElement('span');
        fam.className = 'font-fam';
        fam.textContent = f.fams.length ? f.fams.slice(0, 2).join(' · ') : (f.cloudOnly ? 'cloud-only' : '');
        const size = document.createElement('span');
        size.className = 'font-size'; size.textContent = f.cloudOnly ? '' : fmtSize(f.size);
        const del = document.createElement('button');
        del.className = 'font-del';
        del.textContent = '✕'; del.title = 'Delete font';
        del.onclick = () => deleteFont(f.name);
        li.append(name, fam, size, del);
        listEl.appendChild(li);
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

      const sec = document.createElement('div');
      sec.className = 'share-sec-title'; sec.textContent = 'Installed (sandpie/fonts — used by the document converter)';

      listEl = document.createElement('ul'); listEl.className = 'font-list';

      const note = document.createElement('div');
      note.className = 'font-note'; note.id = 'fontNote'; note.style.display = 'none';

      const actions = document.createElement('div');
      actions.className = 'font-actions';
      const add = document.createElement('button');
      add.className = 'act'; add.textContent = '+ Add fonts';
      add.onclick = () => fileInput.click();
      actions.append(add);

      const fileInput = document.createElement('input');
      fileInput.type = 'file'; fileInput.accept = '.ttf,.otf,.ttc'; fileInput.multiple = true;
      fileInput.style.display = 'none';
      fileInput.onchange = () => { addFiles(fileInput.files); fileInput.value = ''; };

      panel.append(head, sec, listEl, note, actions, fileInput);
    },
    onShow() { refresh(); },
  });
})();
