/** sandpie Univer v2 — iframe-based spreadsheet viewer for .xlsx and .csv */
(function () {
  'use strict';

  let activeIframe = null;

  function buildSrcdoc(snapshotJson, fullKey, name) {
    return '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
      + '<meta name="viewport" content="width=device-width,initial-scale=1.0">'
      + '<title>' + name.replace(/</g,'&lt;') + '</title>'
      + '<style>*{margin:0;padding:0;box-sizing:border-box}'
      + 'html,body{width:100%;height:100%;overflow:hidden;background:#fff}'
      + '#mount{width:100%;height:100%}</style></head><body>'
      + '<div id="mount"></div>'
      + '<script type="module">'
      + 'const CDN="https://cdn.jsdelivr.net/npm";'
      + 'const SNAPSHOT=' + snapshotJson + ';'
      + 'async function main(){'
      + 'const[{createUniver,LocaleType,UniverInstanceType},'
      + '{UniverSheetsCorePreset}]=await Promise.all(['
      + 'import(CDN+"/@univerjs/presets@0.25.1/+esm"),'
      + 'import(CDN+"/@univerjs/preset-sheets-core@0.25.1/+esm")]);'
      + 'const{univer}=createUniver({locale:LocaleType.EN_US,'
      + 'presets:[UniverSheetsCorePreset()]});'
      + 'univer.createUnit(UniverInstanceType.UNIVER_SHEET,SNAPSHOT);}'
      + 'main().catch(e=>{document.body.innerHTML='
      + '"<p style=\\"padding:2rem;color:#c00;font:14px sans-serif\\">"
      + '+"Univer: "+e.message;console.error(e)});'
      + '<\/script></body></html>';
  }

  function csvToSnapshot(name, text) {
    const lines = text.split(/\r?\n/).filter(Boolean);
    const rows = lines.map(l => {
      const r = []; let c = '', q = false;
      let delim = ',';
      if (lines[0] && (lines[0].match(/;/g)||[]).length > (lines[0].match(/,/g)||[]).length) delim = ';';
      if (lines[0] && (lines[0].match(/\t/g)||[]).length > (lines[0].match(/;/g)||[]).length) delim = '\t';
      for (let i = 0; i < l.length; i++) {
        const ch = l[i];
        if (ch === '"') { q = !q; continue; }
        if (ch === delim && !q) { r.push(c.trim()); c = ''; continue; }
        c += ch;
      }
      r.push(c.trim());
      return r;
    });
    return buildCellSnapshot(name, [name], rows);
  }

  function buildCellSnapshot(name, sheetNames, allRows) {
    // allRows[0] is a 2D array for the first sheet
    const sheets = {};
    const sid = '1';
    const cellData = {};
    const rows = allRows;
    for (let r = 0; r < rows.length; r++) {
      const row = rows[r];
      for (let c = 0; c < row.length; c++) {
        const v = row[c];
        if (v === '' || v == null) continue;
        const rs = String(r), cs = String(c);
        if (!cellData[rs]) cellData[rs] = {};
        cellData[rs][cs] = { v: typeof v === 'number' ? v : String(v) };
      }
    }
    sheets[sid] = { id: sid, name: sheetNames[0] || 'Sheet1', cellData, rowCount: Math.max(rows.length, 200), columnCount: 60 };
    return { id: 'wb-' + Date.now(), sheetOrder: [sid], name: name || 'Workbook', appVersion: '0.25.1', locale: 'enUS', styles: {}, sheets, resources: [] };
  }

  window.SandpieUniver = {
    async mount(container, { fullKey, name, ext, file }) {
      if (activeIframe) { try { activeIframe.remove(); } catch(_) {} activeIframe = null; }
      name = name || String(fullKey).split('/').pop() || 'sheet';

      let snapshot;
      if (ext === 'csv') {
        const text = await file.text();
        snapshot = csvToSnapshot(name, text);
      } else if (ext === 'xlsx' || ext === 'xls') {
        // Load SheetJS, parse in main thread, pass data to iframe
        if (!window.XLSX) {
          container.innerHTML = '<div style="padding:2rem;color:var(--sp-text-dim);text-align:center;">Loading SheetJS...</div>';
          await new Promise((res, rej) => {
            const s = document.createElement('script');
            s.src = 'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js';
            s.onload = res; s.onerror = rej;
            document.head.appendChild(s);
          });
        }
        const buf = await file.arrayBuffer();
        const wb = XLSX.read(buf, { type: 'array' });
        const cellRows = [];
        if (wb.SheetNames.length > 0) {
          const ws = wb.Sheets[wb.SheetNames[0]];
          const ref = ws['!ref'];
          if (ref) {
            const range = XLSX.utils.decode_range(ref);
            for (let r = range.s.r; r <= range.e.r; r++) {
              const row = [];
              for (let c = range.s.c; c <= range.e.c; c++) {
                const addr = XLSX.utils.encode_cell({ r, c });
                row.push(ws[addr] ? ws[addr].v : '');
              }
              cellRows.push(row);
            }
          }
        }
        snapshot = buildCellSnapshot(name, wb.SheetNames, cellRows);
      } else {
        container.innerHTML = '<div style="padding:2rem;color:var(--sp-text-dim);text-align:center;">Unsupported: .' + ext + '</div>';
        return;
      }

      container.innerHTML = '';
      const iframe = document.createElement('iframe');
      iframe.style.cssText = 'width:100%;height:100%;border:0;';
      iframe.sandbox = 'allow-scripts allow-same-origin';
      container.appendChild(iframe);
      iframe.srcdoc = buildSrcdoc(JSON.stringify(snapshot), fullKey, name);
      activeIframe = iframe;
    },
    teardown() {
      if (activeIframe) { try { activeIframe.remove(); } catch(_) {} activeIframe = null; }
    }
  };
})();
