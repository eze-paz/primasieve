// file-viewer.js — THE file viewer. From-zero replacement for the old
// opfs.openFile modal (deleted): one side pane, no modal, Univer is the
// default surface.
//
//   sheets (xlsx/xls/ods/csv)  → Univer sheet editor (SheetJS bridge)
//   pdf                        → inline <iframe> (blob URL)
//   images / audio / video     → inline element (blob URL)
//   docx/doc/odt/rtf/pptx/…    → LibreOffice-WASM PDF render (opfs._renderOfficePdf)
//   tex                        → convert_latex project iframe
//   html/htm/svg               → sandboxed iframe preview
//   EVERYTHING ELSE that decodes as UTF-8 (txt, md, py, json, js, no-ext…)
//                              → Univer docs editor; Save writes plain text back
//   true binary                → info row + download
//
// The pane mirrors the app's side-viewer conventions (.file-viewer.side inside
// #messagesSide, viewer-mode/viewer-side-open classes, .fv-panel[data-blob-url]
// for closeFile's blob revocation) so opfs.closeFile() remains the single
// teardown path. On mobile (no side column) the same pane goes fullscreen-fixed.
(function () {
  'use strict';

  const SHEET_EXTS = new Set(['xlsx', 'xls', 'ods', 'csv']);
  const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'ico', 'avif']);
  const MEDIA_EXTS = new Set(['mp4', 'webm', 'mp3', 'wav', 'ogg', 'm4a', 'mov']);
  const OFFICE_EXTS = new Set(['docx', 'doc', 'odt', 'rtf', 'pptx', 'ppt', 'odp', 'odg']);
  const TEXT_EDIT_CAP = 4 * 1024 * 1024;   // Univer doc editor cap; larger text → download row

  /* ════════════════════ Univer bridges (SheetJS / plain text) ═══════════ */

  function xlsxToUniver(XLSX, wb, name) {
    const sheets = {}, sheetOrder = [];
    wb.SheetNames.forEach((sn, i) => {
      const ws = wb.Sheets[sn];
      const id = 'sheet-' + i;
      const cellData = {};
      let maxR = 0, maxC = 0;
      for (const addr of Object.keys(ws)) {
        if (addr[0] === '!') continue;
        const { r, c } = XLSX.utils.decode_cell(addr);
        maxR = Math.max(maxR, r); maxC = Math.max(maxC, c);
        const cell = ws[addr];
        const out = {};
        if (cell.f) out.f = '=' + cell.f;
        if (cell.v !== undefined) {
          if (cell.t === 'n') { out.v = cell.v; out.t = 2; }
          else if (cell.t === 'b') { out.v = cell.v ? 1 : 0; out.t = 3; }
          else if (cell.t === 'd') { out.v = String(cell.w || cell.v); out.t = 1; }
          else { out.v = String(cell.v); out.t = 1; }
        }
        if (out.f !== undefined || out.v !== undefined) {
          (cellData[r] = cellData[r] || {})[c] = out;
        }
      }
      const mergeData = (ws['!merges'] || []).map(m => ({
        startRow: m.s.r, startColumn: m.s.c, endRow: m.e.r, endColumn: m.e.c,
      }));
      const columnData = {};
      (ws['!cols'] || []).forEach((col, ci) => { if (col && col.wpx) columnData[ci] = { w: col.wpx }; });
      const rowData = {};
      (ws['!rows'] || []).forEach((row, ri) => { if (row && row.hpx) rowData[ri] = { h: row.hpx }; });
      sheets[id] = {
        id, name: sn, cellData, mergeData, columnData, rowData,
        rowCount: Math.max(maxR + 50, 100),
        columnCount: Math.max(maxC + 10, 26),
      };
      sheetOrder.push(id);
    });
    return { id: 'workbook-1', name, appVersion: '1', locale: 'enUS', styles: {}, sheetOrder, sheets };
  }

  function univerToXlsxBytes(XLSX, snap, bookType) {
    const wb = XLSX.utils.book_new();
    for (const id of snap.sheetOrder) {
      const s = snap.sheets[id];
      const ws = {};
      let maxR = 0, maxC = 0, any = false;
      for (const r of Object.keys(s.cellData || {})) {
        for (const c of Object.keys(s.cellData[r] || {})) {
          const cell = s.cellData[r][c] || {};
          if (cell.v === undefined && !cell.f) continue;
          const addr = XLSX.utils.encode_cell({ r: +r, c: +c });
          const out = {};
          if (cell.f) { out.f = String(cell.f).replace(/^=/, ''); out.t = 'n'; }
          if (cell.v !== undefined) {
            if (cell.t === 2 || (typeof cell.v === 'number' && cell.t === undefined)) { out.v = +cell.v; out.t = 'n'; }
            else if (cell.t === 3) { out.v = !!cell.v; out.t = 'b'; }
            else { out.v = String(cell.v); if (!out.f) out.t = 's'; }
          }
          ws[addr] = out;
          maxR = Math.max(maxR, +r); maxC = Math.max(maxC, +c); any = true;
        }
      }
      ws['!ref'] = XLSX.utils.encode_range({ s: { r: 0, c: 0 }, e: { r: any ? maxR : 0, c: any ? maxC : 0 } });
      if ((s.mergeData || []).length) {
        ws['!merges'] = s.mergeData.map(m => ({ s: { r: m.startRow, c: m.startColumn }, e: { r: m.endRow, c: m.endColumn } }));
      }
      XLSX.utils.book_append_sheet(wb, ws, (s.name || id).slice(0, 31));
    }
    return XLSX.write(wb, { type: 'array', bookType });
  }

  // Univer's dataStream uses '\r' as the paragraph mark and ends '\r\n'.
  function textToUniverDoc(text, name) {
    const dataStream = String(text).replace(/\r\n?/g, '\n').replace(/\n/g, '\r') + '\r\n';
    const paragraphs = [];
    for (let i = 0; i < dataStream.length; i++) if (dataStream[i] === '\r') paragraphs.push({ startIndex: i });
    return {
      id: 'doc-1', title: name, locale: 'enUS',
      body: { dataStream, textRuns: [], paragraphs, sectionBreaks: [{ startIndex: dataStream.length - 1 }] },
      documentStyle: {
        pageSize: { width: 595, height: 842 },
        marginTop: 40, marginBottom: 40, marginLeft: 45, marginRight: 45,
      },
    };
  }
  function univerDocToText(snap) {
    const ds = (snap && snap.body && snap.body.dataStream) || '';
    return ds.replace(/\r\n$/, '').replace(/\r/g, '\n');
  }

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
    body.style.cssText = 'flex:1;min-height:0;overflow:auto;position:relative;';
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
    return { pane, header, body, title };
  }

  function fill(body, el) { body.innerHTML = ''; body.appendChild(el); return el; }

  function blobUrlFor(pane, file, type) {
    const url = URL.createObjectURL(type ? new Blob([file], { type }) : file);
    pane.dataset.blobUrl = url;   // opfs.closeFile revokes .fv-panel[data-blob-url]
    return url;
  }

  /* ════════════════════ Univer mounting ═════════════════════════════════ */

  function mountUniver(body, name, payload, kind, onSave) {
    const iframe = document.createElement('iframe');
    iframe.src = '/univer-editor.html?v=2';
    iframe.style.cssText = 'width:100%;height:100%;border:0;background:#fff;';
    fill(body, iframe);
    const onMsg = async (e) => {
      if (e.source !== iframe.contentWindow || !e.data) return;
      if (e.data.type === 'univer-ready') {
        iframe.contentWindow.postMessage(
          kind === 'doc' ? { type: 'univer-load', name, doc: payload }
                         : { type: 'univer-load', name, workbook: payload },
          location.origin);
      } else if (e.data.type === 'univer-save') {
        let reply;
        try {
          await onSave(e.data.doc || e.data.workbook);
          reply = { type: 'univer-saved', ok: true };
        } catch (err) {
          reply = { type: 'univer-saved', ok: false, error: (err && err.message) || String(err) };
        }
        iframe.contentWindow.postMessage(reply, location.origin);
      }
    };
    addEventListener('message', onMsg);
    const mo = new MutationObserver(() => {
      if (!document.contains(iframe)) { removeEventListener('message', onMsg); mo.disconnect(); }
    });
    mo.observe(document.body, { childList: true, subtree: true });
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
    const { pane, body } = buildPane(fullKey);

    /* sheets → Univer sheet editor */
    if (SHEET_EXTS.has(ext)) {
      body.innerHTML = '<div style="color:var(--sp-text-dim);padding:2rem;text-align:center;">Loading spreadsheet editor…</div>';
      const XLSX = await opfs.getSheetJS();
      const wbData = xlsxToUniver(XLSX, XLSX.read(new Uint8Array(await file.arrayBuffer()), { type: 'array' }), name);
      mountUniver(body, name, wbData, 'sheet', async (snap) => {
        await opfs.write(fullKey, new Blob([univerToXlsxBytes(XLSX, snap, ext === 'csv' ? 'csv' : ext)]));
      });
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

    /* word/powerpoint & friends → LibreOffice-WASM PDF render (read-only for now) */
    if (OFFICE_EXTS.has(ext)) {
      body.innerHTML = '<div style="color:var(--sp-text-dim);padding:2rem;text-align:center;">Rendering document…</div>';
      if (await opfs._renderOfficePdf(file, ext, name, body, pane)) return;
      body.innerHTML = '<div style="color:var(--sp-text-dim);padding:2rem;text-align:center;">Could not render this document.</div>';
      return;
    }

    /* html/svg → sandboxed preview */
    if (ext === 'html' || ext === 'htm' || ext === 'svg') {
      const iframe = document.createElement('iframe');
      iframe.sandbox = 'allow-same-origin';
      iframe.src = blobUrlFor(pane, file, ext === 'svg' ? 'image/svg+xml' : 'text/html');
      iframe.style.cssText = 'width:100%;height:100%;border:0;background:#fff;';
      fill(body, iframe);
      return;
    }

    /* default: text → Univer docs editor; binary → download row */
    const bytes = new Uint8Array(await file.arrayBuffer());
    let text = null;
    if (bytes.length <= TEXT_EDIT_CAP) {
      const probe = new TextDecoder('utf-8', { fatal: false }).decode(bytes);
      const sample = probe.slice(0, 4096);
      let bad = 0;
      for (let i = 0; i < sample.length; i++) {
        const ch = sample.charCodeAt(i);
        if (ch === 0xFFFD || ch === 0) bad++;
      }
      if (!sample.length || bad / Math.max(sample.length, 1) < 0.05) text = probe;
    }
    if (text !== null) {
      mountUniver(body, name, textToUniverDoc(text, name), 'doc', async (snap) => {
        await opfs.write(fullKey, univerDocToText(snap));
      });
      return;
    }
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
