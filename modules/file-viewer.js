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

  /* ════════════════════ OPFS fetch-bridge (rendered HTML) ══════════════════
   * A rendered HTML file runs in a sandboxed srcdoc iframe (origin null), so its
   * fetch()/XHR of sibling or workspace files can't reach OPFS — they hit the
   * network and CORS-fail. We inject a shim that overrides fetch + XMLHttpRequest
   * and proxies same-origin/relative requests to the parent over postMessage; the
   * parent reads OPFS and returns the bytes. FULL OPFS access by design: a relative
   * path resolves against the file's own directory, and '/abs' or an app-origin
   * absolute URL maps to the OPFS root. Genuinely external (other-origin) URLs pass
   * straight through to the network. The random per-open token isolates channels.
   */
  function bridgeMime(path) {
    const ext = (path.split('.').pop() || '').toLowerCase();
    return ({ html: 'text/html', htm: 'text/html', css: 'text/css', js: 'text/javascript', mjs: 'text/javascript',
      json: 'application/json', svg: 'image/svg+xml', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg',
      gif: 'image/gif', webp: 'image/webp', csv: 'text/csv', txt: 'text/plain', xml: 'application/xml',
      wasm: 'application/wasm', woff: 'font/woff', woff2: 'font/woff2' })[ext] || 'application/octet-stream';
  }
  // Map a URL as seen by the shim to an OPFS-root-relative path.
  function bridgeResolve(url, baseDir) {
    let path;
    if (/^[a-z][a-z0-9+.\-]*:\/\//i.test(url)) { try { path = new URL(url).pathname; } catch (_) { path = url; } path = path.replace(/^\/+/, ''); }
    else if (url[0] === '/') path = url.replace(/^\/+/, '');
    else {                                   // relative → resolve against the file's directory
      const segs = baseDir ? baseDir.split('/').filter(Boolean) : [];
      for (const s of url.split('/')) { if (s === '' || s === '.') continue; if (s === '..') segs.pop(); else segs.push(s); }
      path = segs.join('/');
    }
    return path.replace(/[?#].*$/, '').replace(/^files\//, '');   // drop query/hash + tolerate a /files/ prefix
  }
  // Runs INSIDE the sandboxed iframe (serialized via .toString()); self-contained.
  function bridgeShim(T, ORIGIN) {
    var pending = {}, seq = 0;
    function proxied(u) {
      if (u == null) return false; u = String(u);
      if (/^(data|blob):/i.test(u)) return false;
      if (/^[a-z][a-z0-9+.\-]*:\/\//i.test(u)) { try { return new URL(u).origin === ORIGIN; } catch (e) { return false; } }
      return true;   // relative or root-relative → serve from OPFS
    }
    function ask(u) {
      return new Promise(function (resolve, reject) {
        var id = ++seq; pending[id] = { resolve: resolve, reject: reject };
        try { parent.postMessage({ __opfsBridge: T, req: true, id: id, url: u }, '*'); }
        catch (e) { delete pending[id]; reject(e); return; }
        setTimeout(function () { if (pending[id]) { var p = pending[id]; delete pending[id]; p.reject(new Error('opfs bridge timeout: ' + u)); } }, 20000);
      });
    }
    window.addEventListener('message', function (e) {
      var d = e.data;
      if (!d || d.__opfsBridge !== T || d.req || !('id' in d)) return;
      var p = pending[d.id]; if (!p) return; delete pending[d.id];
      if (d.ok) p.resolve(d); else p.reject(new Error(d.error || 'opfs bridge: not found'));
    });
    var _fetch = window.fetch ? window.fetch.bind(window) : null;
    window.fetch = function (input, init) {
      var url = (typeof input === 'string') ? input : (input && input.url) ? input.url : String(input);
      if (!proxied(url)) return _fetch ? _fetch(input, init) : Promise.reject(new Error('fetch unavailable'));
      return ask(url).then(function (d) {
        return new Response(d.bytes, { status: 200, headers: { 'Content-Type': d.contentType || 'application/octet-stream' } });
      }, function (err) {
        return new Response(String((err && err.message) || err), { status: 404, statusText: 'Not Found' });
      });
    };
    try {
      var XO = XMLHttpRequest.prototype.open, XS = XMLHttpRequest.prototype.send;
      XMLHttpRequest.prototype.open = function (m, u) { this.__bu = u; this.__bp = proxied(u); return XO.apply(this, arguments); };
      XMLHttpRequest.prototype.send = function () {
        if (!this.__bp) return XS.apply(this, arguments);
        var xhr = this;
        function def(k, v) { try { Object.defineProperty(xhr, k, { configurable: true, get: function () { return v; } }); } catch (e) {} }
        ask(xhr.__bu).then(function (d) {
          var buf = d.bytes, txt = ''; try { txt = new TextDecoder().decode(new Uint8Array(buf)); } catch (e) {}
          def('readyState', 4); def('status', 200); def('statusText', 'OK'); def('responseURL', xhr.__bu); def('responseText', txt);
          def('response', xhr.responseType === 'arraybuffer' ? buf : xhr.responseType === 'blob' ? new Blob([buf])
            : xhr.responseType === 'json' ? (function () { try { return JSON.parse(txt); } catch (e) { return null; } })() : txt);
          if (typeof xhr.onreadystatechange === 'function') xhr.onreadystatechange();
          xhr.dispatchEvent(new Event('readystatechange')); xhr.dispatchEvent(new Event('load')); xhr.dispatchEvent(new Event('loadend'));
        }, function () {
          def('readyState', 4); def('status', 404);
          xhr.dispatchEvent(new Event('readystatechange')); xhr.dispatchEvent(new Event('error')); xhr.dispatchEvent(new Event('loadend'));
        });
      };
    } catch (e) {}
  }
  // Inject a <script> as the first child of <head> (or <html>), keeping any doctype first.
  function injectHeadScript(html, js) {
    const tag = '<script>' + js + '</scr' + 'ipt>';
    const mHead = html.match(/<head[^>]*>/i);
    if (mHead) return html.slice(0, mHead.index + mHead[0].length) + tag + html.slice(mHead.index + mHead[0].length);
    const mHtml = html.match(/<html[^>]*>/i);
    if (mHtml) return html.slice(0, mHtml.index + mHtml[0].length) + tag + html.slice(mHtml.index + mHtml[0].length);
    return tag + html;
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
      // null origin, so charts/artifacts render but can't reach the app. An
      // injected OPFS fetch-bridge lets the doc's fetch/XHR read workspace files
      // (see the bridge helpers above); full OPFS access, resolved against this
      // file's directory.
      iframe.sandbox = 'allow-scripts';
      const token = (self.crypto && crypto.randomUUID) ? crypto.randomUUID() : ('b' + Date.now() + '_' + (window._openFilePath || ''));
      const baseDir = fullKey.includes('/') ? fullKey.slice(0, fullKey.lastIndexOf('/')) : '';
      const shim = '(' + bridgeShim.toString() + ')(' + JSON.stringify(token) + ',' + JSON.stringify(location.origin) + ')';
      const onMsg = async (e) => {
        const d = e.data;
        if (!d || d.__opfsBridge !== token || !d.req || e.source !== iframe.contentWindow) return;
        let reply, transfer = [];
        try {
          const bytes = await opfs.readBytes(bridgeResolve(d.url, baseDir));
          const buf = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
          reply = { __opfsBridge: token, id: d.id, ok: true, bytes: buf, contentType: bridgeMime(bridgeResolve(d.url, baseDir)) };
          transfer = [buf];
        } catch (err) {
          reply = { __opfsBridge: token, id: d.id, ok: false, error: String((err && err.message) || err) };
        }
        try { e.source.postMessage(reply, '*', transfer); } catch (_) { try { e.source.postMessage(reply, '*'); } catch (__) {} }
      };
      window.addEventListener('message', onMsg);
      active = { destroy: () => window.removeEventListener('message', onMsg) };
      iframe.srcdoc = injectHeadScript(html, shim);
      iframe.style.cssText = 'width:100%;height:100%;border:0;background:#fff;';
      body.appendChild(iframe);
    }

    // single view-mode dropdown (Page / Text / Rendered) in the header
    const modeSel = document.createElement('select');
    modeSel.title = 'View mode';
    modeSel.style.cssText = 'font-size:0.72rem;padding:2px 6px;flex:none;background:var(--sp-bg,#0d1117);color:var(--sp-text,#e6edf3);border:1px solid var(--sp-border,#30363d);border-radius:4px;';
    [['Editor', 'page'], ['Text', 'text'], ['Rendered', 'rendered']].forEach(([l, v]) => { const o = document.createElement('option'); o.textContent = l; o.value = v; modeSel.appendChild(o); });
    modeSel.onchange = () => ({ page: showPage, text: showText, rendered: showRendered }[modeSel.value] || showPage)();
    header.insertBefore(modeSel, header.lastChild);
    // ↗ / ⬇ serving the LIVE document (reflects unsaved edits in any mode)
    addOpenDownload(header, () => new Blob([currentHtml()], { type: 'text/html' }), () => name);

    showRendered();   // default (falls back to Editor/Text via the dropdown)
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
    // 📌 pin toggle — reflects/sets SandpiePins state for the open file.
    const pinBtn = addHeaderButton(header, '📌', 'Pin file', () => {});
    if (window.SandpiePins) SandpiePins.bindButton(pinBtn, fullKey);
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
