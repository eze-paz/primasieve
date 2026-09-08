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

  // Auto-reload state (Rendered mode only): which file is open, whether the HTML
  // viewer is currently in Rendered mode, and its iframe. Editor/Text modes hold
  // unsaved edits and must never be clobbered by a reload.
  let _openKey = null;
  let _renderedMode = false;
  let _renderedFrame = null;

  const loading = (msg) => `<div style="color:var(--sp-text-dim);padding:2rem;text-align:center;">${msg}</div>`;

  /* ════════════════════ pane host (the ONLY chrome) ═════════════════════ */

  function buildPane(fullKey) {
    const pane = document.createElement('div');
    pane.className = 'file-viewer side fv-panel';
    pane.setAttribute('data-chrome', '');
    pane.style.cssText = 'display:flex;flex-direction:column;height:100%;';
    // Match the show_artifact header: panel bar, monospace label, round icon buttons.
    const header = document.createElement('div');
    header.className = 'fv-header artifact-header';
    header.style.cssText = 'display:flex;align-items:center;gap:5px;padding:2px 8px;flex:none;width:100%;box-sizing:border-box;font:11px monospace;color:var(--sp-text-dim);background:var(--sp-panel);border-bottom:1px solid var(--sp-border);';
    const title = document.createElement('span');
    var _fname = fullKey.split('/').pop(); title.textContent = _fname;
    title.style.cssText = 'flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
    const closeBtn = document.createElement('button');
    closeBtn.className = 'artifact-icon-btn';
    closeBtn.textContent = '✕';
    closeBtn.title = 'Close';
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
    // single glyph/emoji → round artifact-icon-btn; a text label (Save/Source) → pill
    b.className = String(label).length <= 2 ? 'artifact-icon-btn' : 'fv-hbtn-text';
    b.textContent = label; b.title = title;
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
  //   ↗ prefers the file's real /files/ URL (sw.js serves it out of OPFS) — a
  // clean, reloadable, copy-pasteable address instead of blob:… . That serves
  // the SAVED file, so a viewer with unsaved edits says so via hasUnsaved() and
  // gets the blob URL, which is the only way to show content that isn't on disk.
  function addOpenDownload(header, getBlob, getName, fullKey, hasUnsaved) {
    addHeaderButton(header, '↗', 'Open in new tab', async () => {
      if (fullKey && opfs.filesUrlReady() && !(hasUnsaved && hasUnsaved())) {
        window.open(filesUrl(fullKey), '_blank'); return;
      }
      const b = await getBlob(); const url = URL.createObjectURL(b);
      window.open(url, '_blank'); setTimeout(() => URL.revokeObjectURL(url), 60000);
    });
    addHeaderButton(header, '⬇', 'Download', async () => {
      const b = await getBlob(); const url = URL.createObjectURL(b);
      const a = document.createElement('a'); a.href = url; a.download = getName(); a.style.display = 'none';
      document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000);
    });
  }

  // Encode each path segment for a /files/ URL; sw.js decodeURIComponent-s them back.
  const filesUrl = (fullKey) => opfs.filesUrl(fullKey);

  /* ════════════════════ text viewer/editor ══════════════════════════════ */

  function openText(fullKey, name, ext, text, header, body) {
    const isMd = ext === 'md' || ext === 'markdown';
    let mode = isMd ? 'preview' : 'edit';   // md defaults to rendered; others to source
    let ta = null, dirty = false;

    const setTitle = (dirtyNow) => { const t = header.querySelector('span'); if (t) t.textContent = (dirtyNow ? '• ' : '') + fullKey.split('/').pop(); };

    const saveBtn = addHeaderButton(header, 'Save', 'Save to OPFS (Ctrl+S)', async () => {
      if (!ta) return;
      saveBtn.textContent = 'Saving…'; saveBtn.disabled = true;
      try { await opfs.write(fullKey, ta.value); text = ta.value; dirty = false; setTitle(false); if (window.SandpieActivity) SandpieActivity.fire('file_edit', 'edit', fullKey); saveBtn.textContent = 'Saved ✓'; }
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
        // For memory files, turn [[name]] into clickable links to the sibling memory
        // (rendered as a #mem: fragment href, which survives DOMPurify, then intercepted).
        const isMem = /(^|\/)sandpie\/memory\/[^/]+\.md$/.test(fullKey);
        let src = text;
        if (isMem) src = text
          .replace(/^﻿?---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*\r?\n/, '')          // hide frontmatter in the rendered read (Source mode still shows it)
          .replace(/\[\[([A-Za-z0-9][A-Za-z0-9_-]*)\]\]/g, (_m, n) => `[${n}](#mem:${n})`);
        // marked + DOMPurify are loaded blocking in the page head (same as chat rendering).
        try { div.innerHTML = window.DOMPurify.sanitize(window.marked.parse(src)); }
        catch (_) { const pre = document.createElement('pre'); pre.textContent = text; pre.style.whiteSpace = 'pre-wrap'; div.appendChild(pre); }
        if (isMem) div.addEventListener('click', (e) => {
          const a = e.target.closest('a[href^="#mem:"]'); if (!a) return;
          e.preventDefault();
          const n = a.getAttribute('href').slice(5);
          if (n) open('sandpie/memory/' + n + '.md', n + '.md');
        });
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
    let savedHtml = initialHtml;   // last content written to OPFS — ↗ can use /files/ while it matches
    let active = null;       // { getHTML?, destroy? } of the current mode, if any
    let textSave = null;     // Text-mode Save button (removed on mode change)
    // ⌖ element-pick state (Rendered mode): armed?, pending arm, live iframe, teardown fn
    let pickOn = false, pendingPick = false, curFrame = null, pickArm = null;

    // latest content, capturing unsaved edits from the active mode (for the
    // dropdown carry-over AND the ↗/⬇ buttons).
    const currentHtml = () => { if (active && active.getHTML) { try { html = active.getHTML(); } catch (_) {} } return html; };

    const teardown = () => {
      disarmPick();
      currentHtml();
      if (active && active.destroy) { try { active.destroy(); } catch (_) {} }
      active = null;
      if (textSave) { textSave.remove(); textSave = null; }
      body.innerHTML = ''; body.style.padding = '';
    };

    function showPage() {
      teardown(); _renderedMode = false; _renderedFrame = null; modeSel.value = 'page'; body.style.padding = '0';
      if (window.SandpieHtmlEditor) {
        active = SandpieHtmlEditor.mount(body, { html, onSave: (out) => { html = out; savedHtml = out; if (window.SandpieActivity) SandpieActivity.fire('file_edit', 'edit', fullKey); return opfs.write(fullKey, out); } });
      } else {
        body.innerHTML = loading('Editor module not loaded.');
      }
    }

    function showText() {
      teardown(); _renderedMode = false; _renderedFrame = null; modeSel.value = 'text';
      const ta = document.createElement('textarea');
      ta.value = html; ta.spellcheck = false;
      ta.style.cssText = 'width:100%;height:100%;box-sizing:border-box;border:0;outline:none;resize:none;padding:12px 14px;'
        + 'font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--sp-bg,#0d1117);color:var(--sp-text,#e6edf3);';
      const save = async () => {
        textSave.textContent = 'Saving…'; textSave.disabled = true;
        try { html = ta.value; await opfs.write(fullKey, html); savedHtml = html; if (window.SandpieActivity) SandpieActivity.fire('file_edit', 'edit', fullKey); textSave.textContent = 'Saved ✓'; }
        catch (e) { textSave.textContent = 'Save failed'; console.error(e); }
        finally { setTimeout(() => { textSave.textContent = 'Save'; textSave.disabled = false; }, 1200); }
      };
      ta.addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); html = ta.value; save(); } });
      ta.addEventListener('input', () => { html = ta.value; });
      textSave = addHeaderButton(header, 'Save', 'Save to OPFS (Ctrl+S)', save);
      body.appendChild(ta);
    }

    function showRendered() {
      teardown(); _renderedFrame = null; _renderedMode = true; modeSel.value = 'rendered';
      const iframe = document.createElement('iframe');
      // Load the file through the service worker at its real /files/ URL — NOT
      // srcdoc. This gives the doc a REAL same-origin, so it reliably shares the
      // app's OPFS: navigator.storage.getDirectory() sees the same files (a
      // sandboxed/srcdoc opaque origin does NOT, per spec), and its fetch / XHR /
      // resource loads resolve against its own /files/<dir>/ URL → sibling files,
      // all served by sw.js. Full OPFS access.
      //   Tradeoffs: renders the SAVED file (unsaved Text/Editor edits show after a
      //   Save), and the doc runs same-origin (app-level access) — fine for the
      //   user's own files, which is what this viewer opens.
      iframe.src = filesUrl(fullKey);
      iframe.style.cssText = 'width:100%;height:100%;border:0;display:block;background:#fff;';
      body.appendChild(iframe);
      _renderedFrame = iframe;   // auto-reload target
      curFrame = iframe;
      // re-arm the pick (or a pending arm) after every (re)load — the doc is replaced
      iframe.addEventListener('load', () => { if (pickOn || pendingPick) { pendingPick = false; armPick(iframe); } });
    }

    // single view-mode dropdown (Page / Text / Rendered) in the header
    const modeSel = document.createElement('select');
    modeSel.title = 'View mode';
    modeSel.style.cssText = 'font:10px monospace;height:20px;padding:0 4px;flex:none;background:var(--sp-surface);color:var(--sp-text-dim);border:1px solid var(--sp-border);border-radius:10px;cursor:pointer;';
    [['Editor', 'page'], ['Text', 'text'], ['Rendered', 'rendered']].forEach(([l, v]) => { const o = document.createElement('option'); o.textContent = l; o.value = v; modeSel.appendChild(o); });
    modeSel.onchange = () => ({ page: showPage, text: showText, rendered: showRendered }[modeSel.value] || showPage)();
    header.insertBefore(modeSel, header.firstElementChild.nextElementSibling);   // right after the title, not sandwiched among the icons
    // ↗ / ⬇ serving the LIVE document (reflects unsaved edits in any mode). ↗ gets
    // the clean /files/ URL whenever the doc on disk IS the live one.
    addOpenDownload(header, () => new Blob([currentHtml()], { type: 'text/html' }), () => name,
      fullKey, () => currentHtml() !== savedHtml);

    /* ⌖ pick — hover-highlight an element in the Rendered preview and click to
       copy its outerHTML (DevTools "Copy element" without opening DevTools).
       Stays armed so several elements can be grabbed; exit: ⌖ again or Esc. */
    const pickBtn = addHeaderButton(header, '⌖', 'Pick element — click in the preview to copy its HTML and attach it as an image (Esc to exit)', () => {
      if (pickOn) { disarmPick(); return; }
      if (modeSel.value !== 'rendered') { modeSel.value = 'rendered'; showRendered(); pendingPick = true; return; }
      if (curFrame && curFrame.contentDocument && curFrame.contentDocument.body) armPick(curFrame);
      else pendingPick = true;
    });

    function armPick(frame) {
      disarmPick();
      const doc = frame && frame.contentDocument;
      if (!doc || !doc.body) { pendingPick = true; return; }
      // The iframe doc is a foreign document: theme vars don't resolve there, so
      // take the resolved accent color from the app root and inject the literal.
      const accent = (getComputedStyle(document.documentElement).getPropertyValue('--sp-accent') || '').trim() || '#2f81f7';
      const SCALE = 2;   // fixed 2x render for crisp crops
      let last = null, saved = null;
      const clearHl = () => { if (last && saved) { last.style.outline = saved[0]; last.style.outlineOffset = saved[1]; } last = null; saved = null; };
      const onMove = (e) => {
        const t = e.target;
        if (!(t && t.nodeType === 1) || t === doc.documentElement || t === doc.body) { clearHl(); return; }
        if (t !== last) { clearHl(); last = t; saved = [t.style.outline, t.style.outlineOffset]; t.style.outline = '2px solid ' + accent; t.style.outlineOffset = '-2px'; }
      };
      const onLeave = () => clearHl();
      // Rasterize ONE element to a JPEG data URL. Same technique as
      // SandpieScreenshot for whole artifacts, but instead of re-serializing
      // just the node (its outerHTML breaks as XML when the subtree contains
      // HTML entities like &nbsp;), we clone the WHOLE document — exactly what
      // the proven whole-artifact capture does — serialize it with
      // XMLSerializer (namespace-aware, entity-safe), and CROP to the element
      // via relative offsets on the canvas.
      // Known limitation, same as the full-artifact capture: sub-resources
      // (external <img>, fonts) cannot be fetched inside an SVG-in-<img>
      // rasterization context, so they come out blank.
      async function elementToDataUrl(t) {
        const doc = frame.contentDocument;
        if (!doc || !doc.documentElement) throw new Error('no document to capture');
        const root = doc.documentElement;
        const DW = Math.max(1, root.scrollWidth || doc.body.scrollWidth || 1280);
        const DH = Math.max(1, Math.min(root.scrollHeight || doc.body.scrollHeight || 800, 16384));
        const clone = root.cloneNode(true);
        // Neutralize scroll-dependent layouts: show everything from the top.
        clone.querySelectorAll('*').forEach((el) => { try { el.scrollTop = 0; el.scrollLeft = 0; } catch (_) {} });
        clone.setAttribute('xmlns', 'http://www.w3.org/1999/xhtml');
        const html = new XMLSerializer().serializeToString(clone);
        const svg =
          '<svg xmlns="http://www.w3.org/2000/svg" width="' + DW + '" height="' + DH + '" viewBox="0 0 ' + DW + ' ' + DH + '">' +
          '<foreignObject x="0" y="0" width="' + DW + '" height="' + DH + '">' + html + '</foreignObject></svg>';
        const url = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);

        const draw = async () => {
          const img = new Image();
          img.src = url;
          let ok = true;
          if (img.decode) { try { await img.decode(); } catch (_) { ok = false; } }
          if (!ok) await new Promise((res) => { img.onload = res; img.onerror = res; });
          if (!img.complete || !(img.naturalWidth > 0)) throw new Error('SVG rasterization failed (invalid markup or entity in the element\u0027s HTML)');
          const canvas = document.createElement('canvas');
          canvas.width = Math.round(DW * SCALE); canvas.height = Math.round(DH * SCALE);
          const cx = canvas.getContext('2d');
          cx.fillStyle = '#ffffff'; cx.fillRect(0, 0, canvas.width, canvas.height);
          cx.drawImage(img, 0, 0, canvas.width, canvas.height);
          return canvas;
        };
        await draw();                       // Safari's first foreignObject raster can be blank
        const full = await draw();

        // Crop to the element using offsets RELATIVE to the document root —
        // immune to iframe scroll and to the scale used for the full render.
        const rr = root.getBoundingClientRect();
        const er = t.getBoundingClientRect();
        const sx = Math.max(0, Math.round((er.left - rr.left) * SCALE));
        const sy = Math.max(0, Math.round((er.top - rr.top) * SCALE));
        const sw = Math.max(1, Math.min(Math.round(er.width * SCALE), full.width - sx));
        const sh = Math.max(1, Math.min(Math.round(er.height * SCALE), full.height - sy));
        if (!sw || !sh) throw new Error('element has no visible box (display:none or zero size)');
        const out = document.createElement('canvas');
        out.width = sw; out.height = sh;
        out.getContext('2d').drawImage(full, sx, sy, sw, sh, 0, 0, sw, sh);
        return out.toDataURL('image/jpeg', 0.92);
      }

      // Copy + attach: the clipboard keeps the HTML (DevTools "Copy element"),
      // and the element is ALSO rendered to an image and attached to the
      // composer exactly like a pasted screenshot, so the model sees what was
      // picked. Saved under picked/ in OPFS (visible in the sidebar).
      async function attachPicked(t) {
        try {
          const dataUrl = await elementToDataUrl(t);
          const bytes = Uint8Array.from(atob(dataUrl.split(',')[1]), (c) => c.charCodeAt(0));
          const fname = 'element-' + Date.now().toString(36) + '.jpg';
          const name = 'picked/' + fname;
          await opfs.write(name, bytes);
          opfs.notifyUpload(name);
          const pane = 'main';   // the viewer overlays the side pane — attach where the user types
          if (typeof SandpieImages !== 'undefined' && SandpieImages.setState) {
            SandpieImages.setState({ kind: 'image', opfsPath: name, name: fname, mime: 'image/jpeg',
              size: bytes.length, thumb: dataUrl, file: { name: fname, type: 'image/jpeg' } }, pane);
          }
          if (opfs._toast) opfs._toast('\u2713 Element attached to the composer', 2500);
          if (typeof window.injectUploadMessage === 'function') {
            const snippet = t.outerHTML.replace(/\s+/g, ' ').slice(0, 120);
            window.injectUploadMessage('User picked element <' + String(t.tagName || '').toLowerCase() +
              '> from the preview — saved to ' + name + ' and attached: ' + snippet);
          }
        } catch (err) {
          console.error('[file-viewer] pick attach failed', err);
          opfs._toast('Element copied, but the image snapshot failed: ' + ((err && err.message) || err), 6000);
        }
      }

      const onClick = (e) => {
        e.preventDefault(); e.stopPropagation();   // never navigate while picking
        const t = e.target;
        if (!(t && t.nodeType === 1) || t === doc.documentElement || t === doc.body) return;
        navigator.clipboard.writeText(t.outerHTML).then(async () => {
          pickBtn.textContent = '✓'; setTimeout(() => { if (pickOn) pickBtn.textContent = '⌖'; }, 1100);
          await attachPicked(t);
        }).catch((err) => {
          console.error('[file-viewer] pick copy failed', err);
          pickBtn.textContent = '✗'; setTimeout(() => { if (pickOn) pickBtn.textContent = '⌖'; }, 1100);
        });
      };
      const onKey = (e) => { if (e.key === 'Escape') disarmPick(); };
      const onWinKey = (e) => { if (e.key === 'Escape' && pickOn) disarmPick(); };
      doc.addEventListener('mousemove', onMove, true);
      doc.addEventListener('mouseleave', onLeave, true);
      doc.addEventListener('click', onClick, true);
      doc.addEventListener('keydown', onKey, true);
      document.addEventListener('keydown', onWinKey, true);
      const prevCursor = doc.body.style.cursor;
      doc.body.style.cursor = 'crosshair';
      pickOn = true;
      pickBtn.style.background = 'var(--sp-accent)'; pickBtn.style.color = 'var(--sp-bg)';
      pickBtn.title = 'Pick mode ON — click elements to copy their HTML + attach a snapshot (⌖ again or Esc to exit)';
      pickArm = () => {
        doc.removeEventListener('mousemove', onMove, true);
        doc.removeEventListener('mouseleave', onLeave, true);
        doc.removeEventListener('click', onClick, true);
        doc.removeEventListener('keydown', onKey, true);
        document.removeEventListener('keydown', onWinKey, true);
        doc.body.style.cursor = prevCursor;
        clearHl();
        pickOn = false;
        pickBtn.style.background = ''; pickBtn.style.color = '';
        pickBtn.textContent = '⌖';
        pickBtn.title = 'Pick element — click in the preview to copy its HTML and attach it as an image (Esc to exit)';
      };
    }
    function disarmPick() { if (pickArm) { try { pickArm(); } catch (_) {} pickArm = null; } }

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
    if (window.SandpieActivity) SandpieActivity.fire('file_open', 'view', fullKey);
    _openKey = fullKey; _renderedMode = false; _renderedFrame = null;
    const ext = (name.split('.').pop() || '').toLowerCase();
    const { pane, header, body } = buildPane(fullKey);
    // 📌 pin toggle — reflects/sets SandpiePins state for the open file.
    const pinBtn = addHeaderButton(header, '📌', 'Pin file', () => {});
    if (window.SandpiePins) SandpiePins.bindButton(pinBtn, fullKey);
    // 🔗 share this file/folder
    if (window.SandpieSharing) addHeaderButton(header, '🔗', 'Share', () => SandpieSharing.shareDialog(fullKey));
    // ↗ / ⬇ for every file. HTML serves live content via openHtmlModes; all
    // other types serve the original file bytes.
    if (ext !== 'html' && ext !== 'htm') addOpenDownload(header, () => file, () => name, fullKey);

    /* spreadsheet (xlsx / xls / csv) → viewer dropdown (default Univer) */
    if (SPREADSHEET_EXTS.has(ext)) {
      // Mode selector dropdown (Univer or ZetaOffice PDF)
      const sheetModes = window.SandpieUniver
        ? [['SheetsJS / Univer', 'univer'], ['PDF (ZetaOffice)', 'zeta']]
        : [['PDF (ZetaOffice)', 'zeta']];
      const sheetSel = document.createElement('select');
      sheetSel.title = 'Spreadsheet viewer';
      sheetSel.style.cssText = 'font:10px monospace;height:20px;padding:0 4px;flex:none;background:var(--sp-surface);color:var(--sp-text-dim);border:1px solid var(--sp-border);border-radius:10px;cursor:pointer;';
      sheetModes.forEach(([l, v]) => { const o = document.createElement('option'); o.textContent = l; o.value = v; sheetSel.appendChild(o); });
      header.insertBefore(sheetSel, header.firstElementChild.nextElementSibling);   // right after the title

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
      iframe.style.cssText = 'width:100%;height:100%;border:0;display:block;';
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
      iframe.style.cssText = 'width:100%;height:100%;border:0;display:block;';
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
      iframe.style.cssText = 'width:100%;height:100%;border:0;display:block;background:#fff;';
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

  // Auto-reload (Rendered mode only): a tool call rewrote the open file — refresh
  // its iframe so the pane shows the new bytes. The iframe is same-origin at its
  // real /files/ URL (sw.js reads OPFS fresh on every GET), so a plain reload()
  // picks up the change; no cache busting needed.
  if (typeof Sandpie !== 'undefined' && Sandpie.events) {
    Sandpie.events.on('artifact:changed', (path) => {
      if (!path || !_openKey || !_renderedMode || !_renderedFrame) return;
      const np = (p) => String(p || '').replace(/^\/+/, '').replace(/^files\//, '');
      const strip = (p) => p.startsWith('sandpie/') ? p.slice('sandpie/'.length) : p;
      const a = np(path), b = np(_openKey);
      if (a !== b && strip(a) !== strip(b)) return;
      if (!_renderedFrame.isConnected) return;   // pane was closed since
      try { _renderedFrame.contentWindow.location.reload(); }
      catch (_) { _renderedFrame.src = filesUrl(_openKey); }
    });
  }

  window.SandpieFileViewer = { open };
})();
