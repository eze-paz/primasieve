// file-viewer.js — THE file viewer. One side pane, no modal.
//
//   office (docx/xlsx/csv/ods/pptx/odt/rtf/…) → LibreOffice-WASM (ZetaOffice) PDF render
//   pdf                                        → inline <iframe> (blob URL)
//   images / audio / video                     → inline element (blob URL)
//   tex                                        → convert_latex project iframe
//   html/htm/svg                               → rendered preview (+ source toggle)
//   text (txt/md/py/json/js/no-ext/…)          → editable plain-text pane; Save → OPFS
//                                                (md also gets a rendered preview toggle)
//   true binary                                → info row + download
//
// The pane mirrors the app's side-viewer conventions (.file-viewer.side inside
// #messagesSide, viewer-mode/viewer-side-open classes, .fv-panel[data-blob-url]
// for closeFile's blob revocation) so opfs.closeFile() remains the single
// teardown path. On mobile (no side column) the same pane goes fullscreen-fixed.
(function () {
  'use strict';

  const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'ico', 'avif']);
  const MEDIA_EXTS = new Set(['mp4', 'webm', 'mp3', 'wav', 'ogg', 'm4a', 'mov']);
  const OFFICE_EXTS = new Set(['docx', 'doc', 'odt', 'rtf', 'xlsx', 'xls', 'ods', 'csv', 'pptx', 'ppt', 'odp', 'odg']);
  const SPREADSHEET_EXTS = new Set(['xlsx', 'xls', 'csv']);
  const TEXT_EDIT_CAP = 4 * 1024 * 1024;   // above this a text file offers download, not an editor

  const loading = (msg) => `<div style="color:var(--sp-text-dim);padding:2rem;text-align:center;">${msg}</div>`;

  /* ════════════════════ pane host (the ONLY chrome) ═════════════════════ */

  function buildPane(fullKey) {
    const pane = document.createElement('div');
    pane.className = 'file-viewer side fv-panel';
    pane.setAttribute('data-chrome', '');
    pane.style.cssText = 'display:flex;flex-direction:column;height:100%;';
    const header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;gap:8px;padding:4px 8px;flex:none;';
    const title = document.createElement('span');
    title.textContent = '/' + fullKey;
    title.style.cssText = 'flex:1;font-size:0.78rem;color:var(--sp-text-dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;direction:rtl;text-align:left;';
    const closeBtn = document.createElement('button');
    closeBtn.className = 'ghost';
    closeBtn.textContent = '✕';
    closeBtn.title = 'Close';
    closeBtn.style.cssText = 'font-size:0.72rem;padding:2px 8px;flex:none;';
    closeBtn.onclick = () => opfs.closeFile();
    header.append(title, closeBtn);
    const body = document.createElement('div');
    body.style.cssText = 'flex:1;width:100%;min-height:0;overflow:auto;position:relative;';
    pane.append(header, body);

    const host = document.getElementById('messagesSide');
    if (host && !opfs._isMobile()) {
      host.appendChild(pane);
      host.classList.add('viewer-mode');
      document.body.classList.add('viewer-side-open');
    } else {
      // mobile / no side column: same pane, fixed fullscreen. Still .file-viewer,
      // so opfs.closeFile() tears it down identically.
      pane.classList.remove('side');
      pane.style.cssText += 'position:fixed;inset:0;z-index:1000;background:var(--sp-bg,#0d1117);';
      document.body.appendChild(pane);
    }
    return { pane, header, title, body };
  }

  function fill(body, el) { body.innerHTML = ''; body.appendChild(el); return el; }

  // Add a button to a pane's header (before the ✕ close button = header's last child).
  function addHeaderButton(header, label, title, onClick) {
    const b = document.createElement('button');
    b.className = 'ghost'; b.textContent = label; b.title = title;
    b.style.cssText = 'font-size:0.72rem;padding:2px 8px;flex:none;';
    b.onclick = onClick;
    header.insertBefore(b, header.lastChild);
    return b;
  }

  function blobUrlFor(pane, file, type) {
    const url = URL.createObjectURL(type ? new Blob([file], { type }) : file);
    pane.dataset.blobUrl = url;   // opfs.closeFile revokes .fv-panel[data-blob-url]
    return url;
  }

  // ↗ open-in-new-tab + ⬇ download, like the show_artifact buttons. getBlob()
  // returns the content to serve (a Blob/File; may be async) so it can reflect
  // live edits, and getName() the download filename.
  function addOpenDownload(header, getBlob, getName) {
    addHeaderButton(header, '↗', 'Open in new tab', async () => {
      const b = await getBlob(); const url = URL.createObjectURL(b);
      window.open(url, '_blank'); setTimeout(() => URL.revokeObjectURL(url), 60000);
    });
    addHeaderButton(header, '⬇', 'Download', async () => {
      const b = await getBlob(); const url = URL.createObjectURL(b);
      const a = document.createElement('a'); a.href = url; a.download = getName(); a.style.display = 'none';
      document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000);
    });
  }

  /* ════════════════════ text viewer/editor ══════════════════════════════ */

  function openText(fullKey, name, ext, text, header, body) {
    const isMd = ext === 'md' || ext === 'markdown';
    let mode = isMd ? 'preview' : 'edit';   // md defaults to rendered; others to source
    let ta = null, dirty = false;

    const setTitle = (dirtyNow) => { const t = header.querySelector('span'); if (t) t.textContent = (dirtyNow ? '• ' : '') + '/' + fullKey; };

    const saveBtn = addHeaderButton(header, 'Save', 'Save to OPFS (Ctrl+S)', async () => {
      if (!ta) return;
      saveBtn.textContent = 'Saving…'; saveBtn.disabled = true;
      try { await opfs.write(fullKey, ta.value); text = ta.value; dirty = false; setTitle(false); saveBtn.textContent = 'Saved ✓'; }
      catch (e) { saveBtn.textContent = 'Save failed'; console.error(e); }
      finally { setTimeout(() => { saveBtn.textContent = 'Save'; saveBtn.disabled = false; }, 1200); }
    });
    const modeBtn = isMd ? addHeaderButton(header, 'Source', 'Toggle rendered / source', () => {
      mode = mode === 'preview' ? 'edit' : 'preview';
      modeBtn.textContent = mode === 'preview' ? 'Source' : 'Preview';
      render();
    }) : null;

    function render() {
      const showEdit = mode === 'edit';
      saveBtn.style.display = showEdit ? '' : 'none';
      if (showEdit) {
        ta = document.createElement('textarea');
        ta.value = (dirty && ta) ? ta.value : text;
        ta.spellcheck = false;
        ta.style.cssText = 'width:100%;height:100%;box-sizing:border-box;border:0;outline:none;resize:none;padding:12px 14px;'
          + 'font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--sp-bg,#0d1117);color:var(--sp-text,#e6edf3);';
        ta.addEventListener('input', () => { dirty = true; setTitle(true); });
        ta.addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); saveBtn.click(); } });
        fill(body, ta);
        ta.focus();
      } else {
        ta = null;
        const div = document.createElement('div');
        div.className = 'md-body';
        div.style.cssText = 'padding:14px 18px;max-width:820px;margin:0 auto;color:var(--sp-text,#e6edf3);line-height:1.6;';
        // marked + DOMPurify are loaded blocking in the page head (same as chat rendering).
        try { div.innerHTML = window.DOMPurify.sanitize(window.marked.parse(text)); }
        catch (_) { const pre = document.createElement('pre'); pre.textContent = text; pre.style.whiteSpace = 'pre-wrap'; div.appendChild(pre); }
        fill(body, div);
      }
    }
    render();
  }

  /* ════════════════════ HTML — 3 view modes ════════════════════════════ */
  // Page (WYSIWYG page-document editor) · Text (raw HTML source) · Rendered
  // (read-only preview). Mode buttons live in the pane header; switching carries
  // the latest (unsaved) content across modes so nothing is lost.
  function openHtmlModes(fullKey, name, initialHtml, header, body) {
    let html = initialHtml;
    let active = null;       // { getHTML?, destroy? } of the current mode, if any
    let textSave = null;     // Text-mode Save button (removed on mode change)

    // latest content, capturing unsaved edits from the active mode (for the
    // dropdown carry-over AND the ↗/⬇ buttons).
    const currentHtml = () => { if (active && active.getHTML) { try { html = active.getHTML(); } catch (_) {} } return html; };

    const teardown = () => {
      currentHtml();
      if (active && active.destroy) { try { active.destroy(); } catch (_) {} }
      active = null;
      if (textSave) { textSave.remove(); textSave = null; }
      body.innerHTML = ''; body.style.padding = '';
    };

    function showPage() {
      teardown(); modeSel.value = 'page'; body.style.padding = '0';
      if (window.SandpieHtmlEditor) {
        active = SandpieHtmlEditor.mount(body, { html, onSave: (out) => { html = out; return opfs.write(fullKey, out); } });
      } else {
        body.innerHTML = loading('Editor module not loaded.');
      }
    }

    function showText() {
      teardown(); modeSel.value = 'text';
      const ta = document.createElement('textarea');
      ta.value = html; ta.spellcheck = false;
      ta.style.cssText = 'width:100%;height:100%;box-sizing:border-box;border:0;outline:none;resize:none;padding:12px 14px;'
        + 'font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--sp-bg,#0d1117);color:var(--sp-text,#e6edf3);';
      const save = async () => {
        textSave.textContent = 'Saving…'; textSave.disabled = true;
        try { html = ta.value; await opfs.write(fullKey, html); textSave.textContent = 'Saved ✓'; }
        catch (e) { textSave.textContent = 'Save failed'; console.error(e); }
        finally { setTimeout(() => { textSave.textContent = 'Save'; textSave.disabled = false; }, 1200); }
      };
      ta.addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); html = ta.value; save(); } });
      ta.addEventListener('input', () => { html = ta.value; });
      textSave = addHeaderButton(header, 'Save', 'Save to OPFS (Ctrl+S)', save);
      body.appendChild(ta);
    }

    function showRendered() {
      teardown(); modeSel.value = 'rendered';
      const iframe = document.createElement('iframe');
      // allow-scripts (no allow-same-origin) → the doc's own scripts run in a
      // null origin, so charts/artifacts render but can't reach the app.
      iframe.sandbox = 'allow-scripts';
      iframe.srcdoc = html;
      iframe.style.cssText = 'width:100%;height:100%;border:0;background:#fff;';
      body.appendChild(iframe);
    }

    // single view-mode dropdown (Page / Text / Rendered) in the header
    const modeSel = document.createElement('select');
    modeSel.title = 'View mode';
    modeSel.style.cssText = 'font-size:0.72rem;padding:2px 6px;flex:none;background:var(--sp-bg,#0d1117);color:var(--sp-text,#e6edf3);border:1px solid var(--sp-border,#30363d);border-radius:4px;';
    [['Page', 'page'], ['Text', 'text'], ['Rendered', 'rendered']].forEach(([l, v]) => { const o = document.createElement('option'); o.textContent = l; o.value = v; modeSel.appendChild(o); });
    modeSel.onchange = () => ({ page: showPage, text: showText, rendered: showRendered }[modeSel.value] || showPage)();
    header.insertBefore(modeSel, header.lastChild);
    // ↗ / ⬇ serving the LIVE document (reflects unsaved edits in any mode)
    addOpenDownload(header, () => new Blob([currentHtml()], { type: 'text/html' }), () => name);

    showPage();   // default
  }

  /* ════════════════════ the dispatcher ══════════════════════════════════ */

  async function open(fullKey, name, opts = {}) {
    name = name || String(fullKey).split('/').pop();
    // read (with dehydrated-cloud fault-in, same contract the old viewer had)
    let file;
    const readLocal = async () => {
      const parts = fullKey.split('/').filter(Boolean);
      const fname = parts.pop();
      const dir = await opfs.resolveDir(parts);
      return (await dir.getFileHandle(fname)).getFile();
    };
    try {
      file = await readLocal();
    } catch (e) {
      const sp = (window.Sandpie && Sandpie.syncProvider) ? Sandpie.syncProvider() : null;
      let hydrated = false;
      if (sp && sp.hydrate) { try { hydrated = await sp.hydrate(fullKey); } catch (_) {} }
      if (hydrated) { try { file = await readLocal(); } catch (_) {} opfs.refreshFileList().catch(() => {}); }
      if (!file) { Sandpie.addMsg('err', `Could not open ${fullKey}: ${e.message}`); return; }
    }

    opfs.closeFile();                       // single viewer instance
    window._openFilePath = fullKey;
    const ext = (name.split('.').pop() || '').toLowerCase();
    const { pane, header, body } = buildPane(fullKey);
    // ↗ / ⬇ for every file. HTML serves live content via openHtmlModes; all
    // other types serve the original file bytes.
    if (ext !== 'html' && ext !== 'htm') addOpenDownload(header, () => file, () => name);

    /* spreadsheet (xlsx / xls / csv) → viewer dropdown (default Univer) */
    if (SPREADSHEET_EXTS.has(ext)) {
      // Mode selector dropdown (Univer or ZetaOffice PDF)
      const sheetModes = window.SandpieUniver
        ? [['SheetsJS / Univer', 'univer'], ['PDF (ZetaOffice)', 'zeta']]
        : [['PDF (ZetaOffice)', 'zeta']];
      const sheetSel = document.createElement('select');
      sheetSel.title = 'Spreadsheet viewer';
      sheetSel.style.cssText = 'font-size:0.72rem;padding:2px 6px;flex:none;background:var(--sp-bg,#0d1117);color:var(--sp-text,#e6edf3);border:1px solid var(--sp-border,#30363d);border-radius:4px;';
      sheetModes.forEach(([l, v]) => { const o = document.createElement('option'); o.textContent = l; o.value = v; sheetSel.appendChild(o); });
      header.insertBefore(sheetSel, header.lastChild);

      let teardown = null;

      async function renderSheet(mode) {
        if (teardown) { try { teardown(); } catch (_) {} teardown = null; }
        body.innerHTML = ''; body.style.padding = ''; body.style.overflow = '';

        if (mode === 'univer' && window.SandpieUniver) {
          body.style.padding = '0';
          body.style.overflow = 'hidden';
          try {
            await window.SandpieUniver.mount(body, { fullKey, name, ext, file });
            teardown = () => window.SandpieUniver.teardown();
          } catch (e) {
            body.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--sp-text-dim,#8b949e);">SheetsJS / Univer error: ' + e.message + '<br><small>Switch to PDF view below</small></div>';
          }
          return;
        }

        body.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--sp-text-dim,#8b949e);">Rendering via ZetaOffice…</div>';
        try {
          if (await opfs._renderOfficePdf(file, ext, name, body, pane)) { teardown = () => {}; return; }
        } catch (_) {}
        body.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--sp-text-dim,#8b949e);">Could not render this document.</div>';
      }

      sheetSel.value = window.SandpieUniver ? 'univer' : 'zeta';
      sheetSel.onchange = () => renderSheet(sheetSel.value);
      await renderSheet(sheetSel.value);
      return;
    }

        /* office (word / sheets / slides) → LibreOffice-WASM (ZetaOffice) render */
    if (OFFICE_EXTS.has(ext)) {
      body.innerHTML = loading('Rendering document…');
      if (await opfs._renderOfficePdf(file, ext, name, body, pane)) return;
      body.innerHTML = loading('Could not render this document.');
      return;
    }

    /* pdf → inline iframe */
    if (ext === 'pdf') {
      const iframe = document.createElement('iframe');
      iframe.src = blobUrlFor(pane, file, 'application/pdf');
      iframe.style.cssText = 'width:100%;height:100%;border:0;';
      fill(body, iframe);
      return;
    }

    /* images */
    if (IMAGE_EXTS.has(ext)) {
      const img = document.createElement('img');
      img.src = blobUrlFor(pane, file);
      img.style.cssText = 'max-width:100%;max-height:100%;display:block;margin:0 auto;';
      fill(body, img);
      return;
    }

    /* audio / video */
    if (MEDIA_EXTS.has(ext)) {
      const isAudio = ['mp3', 'wav', 'ogg', 'm4a'].includes(ext);
      const el = document.createElement(isAudio ? 'audio' : 'video');
      el.controls = true;
      el.src = blobUrlFor(pane, file);
      el.style.cssText = 'width:100%;' + (isAudio ? 'margin-top:2rem;' : 'height:100%;');
      fill(body, el);
      return;
    }

    /* LaTeX project → converter iframe */
    if (ext === 'tex') {
      const dirPath = fullKey.replace(/\/[^\/]+$/, '');
      const iframe = document.createElement('iframe');
      iframe.src = '/convert_latex/index.html?v=4#project=' + encodeURIComponent(dirPath);
      iframe.style.cssText = 'width:100%;height:100%;border:0;';
      fill(body, iframe);
      return;
    }

    /* html → 3 view modes: Page (editor) · Text (raw source) · Rendered (preview) */
    if (ext === 'html' || ext === 'htm') {
      const html0 = new TextDecoder('utf-8', { fatal: false }).decode(new Uint8Array(await file.arrayBuffer()));
      openHtmlModes(fullKey, name, html0, header, body);
      return;
    }
    if (ext === 'svg') {
      const iframe = document.createElement('iframe');
      iframe.sandbox = 'allow-same-origin';
      iframe.src = blobUrlFor(pane, file, 'image/svg+xml');
      iframe.style.cssText = 'width:100%;height:100%;border:0;background:#fff;';
      fill(body, iframe);
      return;
    }

    /* default: text → editable pane; binary → download row */
    const bytes = new Uint8Array(await file.arrayBuffer());
    let text = null;
    if (bytes.length <= TEXT_EDIT_CAP) {
      const probe = new TextDecoder('utf-8', { fatal: false }).decode(bytes);
      const sample = probe.slice(0, 4096);
      let bad = 0;
      for (let i = 0; i < sample.length; i++) { const ch = sample.charCodeAt(i); if (ch === 0xFFFD || ch === 0) bad++; }
      if (!sample.length || bad / Math.max(sample.length, 1) < 0.05) text = probe;
    }
    if (text !== null) { openText(fullKey, name, ext, text, header, body); return; }

    const row = document.createElement('div');
    row.style.cssText = 'padding:2rem;text-align:center;color:var(--sp-text-dim);';
    const kb = (bytes.length / 1024).toFixed(1);
    row.innerHTML = `<p style="margin-bottom:1rem;">${name} — ${kb} KB (binary)</p>`;
    const a = document.createElement('a');
    a.textContent = '⬇ Download';
    a.className = 'ghost';
    a.style.cssText = 'padding:0.4rem 1rem;border:1px solid var(--sp-border);border-radius:6px;text-decoration:none;color:var(--sp-text);';
    a.href = blobUrlFor(pane, file);
    a.download = name;
    row.appendChild(a);
    fill(body, row);
  }

  window.SandpieFileViewer = { open };
})();
