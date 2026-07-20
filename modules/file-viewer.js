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

  /* ════════════════════ HTML — WYSIWYG ("Word for HTML") ════════════════ */
  // Edits the LIVE rendered document via designMode, so ALL CSS/layout survives
  // (a schema editor like Tiptap would flatten a styled doc to its node model).
  // No libraries — native contenteditable + execCommand. Two modes: Visual (a
  // formatting toolbar over the editable iframe) and Source (raw HTML textarea).
  function openHtml(fullKey, name, text, header, body) {
    let mode = 'visual', dirty = false, iframe = null, ta = null;
    const setDirty = (d) => { dirty = d; const t = header.querySelector('span'); if (t) t.textContent = (d ? '• ' : '') + '/' + fullKey; };

    const currentHtml = () => {
      if (mode === 'source' && ta) return ta.value;
      if (iframe && iframe.contentDocument) {
        const doc = iframe.contentDocument;
        const dt = doc.doctype ? '<!DOCTYPE html>\n' : '';
        return dt + doc.documentElement.outerHTML;
      }
      return text;
    };
    const saveBtn = addHeaderButton(header, 'Save', 'Save to OPFS (Ctrl+S)', async () => {
      saveBtn.textContent = 'Saving…'; saveBtn.disabled = true;
      try { text = currentHtml(); await opfs.write(fullKey, text); setDirty(false); saveBtn.textContent = 'Saved ✓'; }
      catch (e) { saveBtn.textContent = 'Save failed'; console.error(e); }
      finally { setTimeout(() => { saveBtn.textContent = 'Save'; saveBtn.disabled = false; }, 1200); }
    });
    const modeBtn = addHeaderButton(header, 'Source', 'Toggle visual / HTML source', () => {
      text = currentHtml();            // capture edits from the mode we're leaving
      mode = mode === 'visual' ? 'source' : 'visual';
      modeBtn.textContent = mode === 'visual' ? 'Source' : 'Visual';
      render();
    });

    // one formatting command against the editable iframe document
    const exec = (cmd, val) => { try { iframe.contentDocument.execCommand(cmd, false, val); iframe.contentWindow.focus(); setDirty(true); } catch (_) {} };
    const TOOLS = [
      ['B', 'Bold', () => exec('bold'), 'font-weight:700'],
      ['I', 'Italic', () => exec('italic'), 'font-style:italic'],
      ['U', 'Underline', () => exec('underline'), 'text-decoration:underline'],
      ['H1', 'Heading 1', () => exec('formatBlock', 'H1')],
      ['H2', 'Heading 2', () => exec('formatBlock', 'H2')],
      ['¶', 'Paragraph', () => exec('formatBlock', 'P')],
      ['•', 'Bullet list', () => exec('insertUnorderedList')],
      ['1.', 'Numbered list', () => exec('insertOrderedList')],
      ['🔗', 'Insert link', () => { const u = prompt('Link URL:'); if (u) exec('createLink', u); }],
      ['↶', 'Undo', () => exec('undo')],
      ['↷', 'Redo', () => exec('redo')],
    ];

    function buildToolbar() {
      const bar = document.createElement('div');
      bar.style.cssText = 'display:flex;flex-wrap:wrap;gap:2px;padding:4px 6px;border-bottom:1px solid var(--sp-border,#30363d);flex:none;background:var(--sp-panel,#161b22);';
      for (const [label, title, fn, extra] of TOOLS) {
        const b = document.createElement('button');
        b.className = 'ghost'; b.textContent = label; b.title = title;
        b.style.cssText = 'min-width:26px;padding:2px 6px;font-size:0.8rem;' + (extra || '');
        b.addEventListener('mousedown', (e) => e.preventDefault());   // keep the iframe selection
        b.onclick = fn;
        bar.appendChild(b);
      }
      return bar;
    }

    function render() {
      const editing = mode === 'visual';
      modeBtn.textContent = editing ? 'Source' : 'Visual';
      body.innerHTML = '';
      if (editing) {
        body.appendChild(buildToolbar());
        iframe = document.createElement('iframe');
        iframe.sandbox = 'allow-same-origin';   // same-origin so we can edit; NO allow-scripts
        iframe.style.cssText = 'width:100%;flex:1;border:0;background:#fff;';
        iframe.srcdoc = text;
        iframe.addEventListener('load', () => {
          try {
            const doc = iframe.contentDocument;
            doc.designMode = 'on';
            doc.addEventListener('input', () => setDirty(true));
            doc.addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); saveBtn.click(); } });
          } catch (_) {}
        }, { once: true });
        body.appendChild(iframe);
      } else {
        iframe = null;
        ta = document.createElement('textarea');
        ta.value = text; ta.spellcheck = false;
        ta.style.cssText = 'width:100%;height:100%;box-sizing:border-box;border:0;outline:none;resize:none;padding:12px 14px;'
          + 'font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--sp-bg,#0d1117);color:var(--sp-text,#e6edf3);';
        ta.addEventListener('input', () => setDirty(true));
        ta.addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); saveBtn.click(); } });
        body.appendChild(ta);
      }
    }
    body.style.display = 'flex'; body.style.flexDirection = 'column';
    render();
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

    /* office (word / sheet / slides) → LibreOffice-WASM (ZetaOffice) render */
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

    /* html → WYSIWYG editor ("Word for HTML"); svg → sandboxed preview */
    if (ext === 'html' || ext === 'htm') {
      const html = new TextDecoder('utf-8', { fatal: false }).decode(new Uint8Array(await file.arrayBuffer()));
      openHtml(fullKey, name, html, header, body);
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
