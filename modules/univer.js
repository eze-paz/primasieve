/**
 * univer.js — Univer spreadsheet viewer for sandpie.
 * Direct mount (no iframe). xlsx via SheetJS, csv via built-in parser.
 */
(function () {
  'use strict';

  var active = null; // { univer }

  function csvParse(text) {
    var lines = text.split(/\r?\n/).filter(Boolean);
    if (!lines.length) return { sheets: [{ name: 'Sheet1', rows: [[]] }], names: ['Sheet1'] };
    var firstLine = lines[0];
    var comma = (firstLine.match(/,/g) || []).length;
    var semi  = (firstLine.match(/;/g) || []).length;
    var tab   = (firstLine.match(/\t/g) || []).length;
    var delim = tab > Math.max(comma, semi) ? '\t' : semi > comma ? ';' : ',';
    function parseRow(l) {
      var r = [], c = '', q = false;
      for (var i = 0; i < l.length; i++) {
        var ch = l[i];
        if (ch === '"') { q = !q; continue; }
        if (ch === delim && !q) { r.push(c.trim()); c = ''; continue; }
        c += ch;
      }
      r.push(c.trim());
      return r;
    }
    var rows = lines.map(parseRow);
    return { sheets: [{ name: 'Sheet1', rows: rows }], names: ['Sheet1'] };
  }

  function xlsxParse(wb) {
    var sheets = [];
    for (var wi = 0; wi < wb.SheetNames.length; wi++) {
      var ws = wb.Sheets[wb.SheetNames[wi]];
      var ref = ws['!ref'];
      var rows = [];
      if (ref) {
        var range = XLSX.utils.decode_range(ref);
        for (var ri = range.s.r; ri <= range.e.r; ri++) {
          var row = [];
          for (var ci = range.s.c; ci <= range.e.c; ci++) {
            var addr = XLSX.utils.encode_cell({ r: ri, c: ci });
            var cell = ws[addr];
            row.push(cell ? cell.v : '');
          }
          rows.push(row);
        }
      }
      sheets.push({ name: wb.SheetNames[wi], rows: rows });
    }
    return { sheets: sheets, names: wb.SheetNames };
  }

  function toSnapshot(name, parsed) {
    var sheets = {}, order = [];
    for (var si = 0; si < parsed.sheets.length; si++) {
      var s = parsed.sheets[si];
      var sid = String(si + 1);
      order.push(sid);
      var cellData = {};
      for (var ri = 0; ri < s.rows.length; ri++) {
        var row = s.rows[ri];
        if (!row) continue;
        for (var ci = 0; ci < row.length; ci++) {
          var v = row[ci];
          if (v === '' || v == null) continue;
          var rs = String(ri), cs = String(ci);
          if (!cellData[rs]) cellData[rs] = {};
          cellData[rs][cs] = { v: typeof v === 'number' ? v : String(v) };
        }
      }
      sheets[sid] = {
        id: sid, name: s.name || 'Sheet' + (si + 1),
        cellData: cellData,
        rowCount: Math.max(s.rows.length, 200),
        columnCount: 60
      };
    }
    return {
      id: 'wb-' + Date.now(), sheetOrder: order,
      name: name || 'Workbook',
      appVersion: '0.25.1', locale: 'enUS',
      styles: {}, sheets: sheets, resources: []
    };
  }

  window.SandpieUniver = {
    mount: async function(container, opts) {
      var fullKey = opts.fullKey;
      var name = opts.name || String(fullKey).split('/').pop() || 'sheet';
      var ext = opts.ext;
      var file = opts.file;

      if (active) { try { active.univer.dispose(); } catch (_) {} active = null; }

      // Parse file
      var parsed;
      if (ext === 'csv') {
        parsed = csvParse(await file.text());
      } else if (ext === 'xlsx' || ext === 'xls') {
        if (!window.XLSX) {
          container.innerHTML = '<div style="padding:2rem;color:var(--sp-text-dim);text-align:center;">Loading SheetJS...</div>';
          await new Promise(function(res, rej) {
            var s = document.createElement('script');
            s.src = 'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js';
            s.onload = res; s.onerror = rej;
            document.head.appendChild(s);
          });
        }
        parsed = xlsxParse(XLSX.read(await file.arrayBuffer(), { type: 'array' }));
      } else {
        container.innerHTML = '<div style="padding:2rem;color:#888;text-align:center;">Unsupported: .' + ext + '</div>';
        return;
      }

      var snapshot = toSnapshot(name, parsed);
      container.innerHTML = '';
      var mountEl = document.createElement('div');
      mountEl.style.cssText = 'width:100%;height:100%;overflow:hidden;position:relative;';
      container.appendChild(mountEl);

      try {
        var CDN = 'https://cdn.jsdelivr.net/npm';
        var mod = await import(CDN + '/@univerjs/presets@0.25.1/+esm');
        var presetMod = await import(CDN + '/@univerjs/preset-sheets-core@0.25.1/+esm');
        var result = mod.createUniver({
          locale: mod.LocaleType.EN_US,
          container: mountEl,
          presets: [presetMod.UniverSheetsCorePreset()]
        });
        var univer = result.univer;

        // Wait a tick for the UI to mount, then create the workbook
        setTimeout(function() {
          try {
            univer.createUnit(mod.UniverInstanceType.UNIVER_SHEET, snapshot);
          } catch (e2) {
            console.error('[SandpieUniver] createUnit:', e2);
          }
        }, 200);
        active = { univer: univer };
      } catch (e) {
        container.innerHTML = '<div style="padding:1.5rem;color:var(--sp-text-dim);text-align:center;">'
          + '<p>Univer error: ' + e.message + '</p>'
          + '<p style="font-size:0.85rem;margin-top:0.5rem;">Switch to PDF (ZetaOffice)</p></div>';
        console.error('[SandpieUniver]', e);
      }
    },

    teardown: function() {
      if (active) { try { active.univer.dispose(); } catch (_) {} active = null; }
    }
  };
})();
