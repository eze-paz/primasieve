// univer-editor.js — in-app spreadsheet EDITING via Univer (vendor/univer, lazy).
//
// Zero-touch integration: opfs.js is not modified. This module wraps
// opfs._renderOfficePdf (the single funnel every xlsx/xls/ods/csv open goes
// through) to drop an "Edit" button onto the viewer panel, and wraps
// opfs.openFile only to remember the OPFS path of the file being viewed so
// Save can write back to it.
//
// Format bridge is SheetJS (already lazy-loaded by opfs.getSheetJS for the
// preview fallback): xlsx bytes -> IWorkbookData on open, snapshot -> xlsx
// bytes on save. Univer's own exchange plugin is Pro/server-side, so SheetJS
// is the only self-contained path. Known losses: charts, rich styling.
(function () {
  'use strict';

  const EXTS = new Set(['xlsx', 'xls', 'ods', 'csv']);
  let lastKey = null;   // fullKey of the file most recently opened via opfs.openFile

  /* ── xlsx (SheetJS model) → Univer IWorkbookData ─────────────────── */
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
    return { id: 'workbook-1', name: name, appVersion: '1', locale: 'enUS', styles: {}, sheetOrder, sheets };
  }

  /* ── Univer snapshot → xlsx bytes ─────────────────────────────────── */
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

  /* ── the editor panel ─────────────────────────────────────────────── */
  async function openEditor(fullKey, name, ext, bytes, body) {
    const XLSX = await opfs.getSheetJS();
    const workbook = xlsxToUniver(XLSX, XLSX.read(bytes, { type: 'array' }), name);
    body.innerHTML = '';
    const iframe = document.createElement('iframe');
    iframe.src = '/univer-editor.html?v=1';
    iframe.style.cssText = 'width:100%;height:calc(100vh - 60px);border:0;border-radius:6px;background:#fff;';
    body.appendChild(iframe);

    const onMsg = async (e) => {
      if (e.source !== iframe.contentWindow || !e.data) return;
      if (e.data.type === 'univer-ready') {
        iframe.contentWindow.postMessage({ type: 'univer-load', name, workbook }, location.origin);
      } else if (e.data.type === 'univer-save') {
        // Save in the file's own format; xls has shaky write support → save
        // legacy .xls files as real xlsx bytes under the same name is WORSE
        // than an honest error, so keep bookType = original extension and let
        // SheetJS throw if it truly can't (surfaced in the status bar).
        let reply;
        try {
          const out = univerToXlsxBytes(XLSX, e.data.workbook, ext === 'csv' ? 'csv' : ext);
          await opfs.write(fullKey, new Blob([out]));
          reply = { type: 'univer-saved', ok: true };
        } catch (err) {
          reply = { type: 'univer-saved', ok: false, error: (err && err.message) || String(err) };
        }
        iframe.contentWindow.postMessage(reply, location.origin);
      }
    };
    window.addEventListener('message', onMsg);
    // stop listening when the panel is torn down (iframe removed from DOM)
    const mo = new MutationObserver(() => {
      if (!document.contains(iframe)) { window.removeEventListener('message', onMsg); mo.disconnect(); }
    });
    mo.observe(document.body, { childList: true, subtree: true });
  }

  /* ── hook install (opfs.js loads before us; retry covers races) ───── */
  function install() {
    if (!window.opfs || !opfs._renderOfficePdf || !opfs.openFile) return false;
    if (opfs._renderOfficePdf.__univerWrapped) return true;

    const origOpen = opfs.openFile;
    opfs.openFile = function (fullKey) { lastKey = fullKey; return origOpen.apply(this, arguments); };

    const orig = opfs._renderOfficePdf;
    const wrapped = async function (file, ext, name, body, panel) {
      if (EXTS.has(ext) && lastKey) {
        const fullKey = lastKey;
        try {
          const bytes = new Uint8Array(await file.arrayBuffer());
          const btn = document.createElement('button');
          btn.textContent = '✎ Edit';
          btn.title = 'Edit in the in-app spreadsheet editor (Univer)';
          btn.className = 'ghost';
          btn.style.cssText = 'position:absolute;top:10px;right:52px;z-index:30;padding:0.25rem 0.7rem;font-size:0.8rem;';
          btn.onclick = () => { btn.remove(); openEditor(fullKey, name, ext, bytes, body); };
          (panel || body).style.position = 'relative';
          (panel || body).appendChild(btn);
        } catch (_) {}
      }
      return orig.apply(this, arguments);
    };
    wrapped.__univerWrapped = true;
    opfs._renderOfficePdf = wrapped;
    return true;
  }

  if (!install()) {
    const t = setInterval(() => { if (install()) clearInterval(t); }, 500);
    setTimeout(() => clearInterval(t), 20000);
  }
})();
