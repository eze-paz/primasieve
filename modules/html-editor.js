// html-editor.js — standalone, dependency-free, page-oriented HTML document editor.
//
//   SandpieHtmlEditor.mount(container, { html, onSave }) -> { getHTML, destroy }
//
// Edits the LIVE document inside an iframe (so arbitrary CSS/layout is preserved
// — the whole point of staying HTML-first), with a Word-like ribbon driven by a
// native Selection/Range engine. NO execCommand anywhere. NO libraries.
//
// Model: the body holds one or more `.sp-page` divs (A4). The document keeps a
// small `<style id="sp-doc-css">` (page sizing + print rules) that IS saved, and
// the editor injects a transient `<style id="sp-editor-css">` (grey backdrop,
// selection handles, caret outline) that is STRIPPED on save. Images are inlined
// as base64 data URIs; they resize (corner handles) and can float with pixel
// positioning inside their page.
(function () {
  'use strict';

  const A4 = { w: '210mm', h: '297mm' };
  const FONTS = ['Inherit', 'Arial', 'Georgia', 'Times New Roman', 'Courier New', 'Verdana', 'Tahoma', 'Graphik', 'Inter', 'system-ui'];
  const SIZES = ['8', '9', '10', '11', '12', '14', '16', '18', '24', '30', '36', '48'];
  const LINEH = ['1.0', '1.15', '1.5', '2.0'];
  const BLOCKS = [['Normal', 'P'], ['Heading 1', 'H1'], ['Heading 2', 'H2'], ['Heading 3', 'H3'], ['Quote', 'BLOCKQUOTE'], ['Code', 'PRE']];

  const DOC_CSS = `
body{margin:0;font-family:system-ui,sans-serif;}
.sp-page{width:${A4.w};min-height:${A4.h};padding:25mm 20mm;margin:10mm auto;background:#fff;color:#111;box-sizing:border-box;position:relative;box-shadow:0 2px 14px rgba(0,0,0,.35);}
.sp-page:focus{outline:none;}
.sp-page img{max-width:100%;}
@media print{body{background:none;}.sp-page{margin:0;box-shadow:none;break-after:page;}.sp-page:last-child{break-after:auto;}}
@page{size:A4;margin:0;}`;

  const EDITOR_CSS = `
html{background:#525659;}
[contenteditable]{outline:none;}
.sp-img-sel{outline:2px solid #4a9eff !important;}
.sp-handle{position:fixed;width:11px;height:11px;background:#4a9eff;border:1.5px solid #fff;border-radius:2px;z-index:2147483000;box-sizing:border-box;}
.sp-imgbar{position:fixed;z-index:2147483001;display:flex;gap:2px;background:#1b1f24;border-radius:6px;padding:3px;box-shadow:0 2px 8px rgba(0,0,0,.4);}
.sp-imgbar button{background:#2b313a;color:#d8dee5;border:0;border-radius:4px;font-size:11px;padding:3px 7px;cursor:pointer;}
.sp-imgbar button.on{background:#4a9eff;color:#fff;}
.sp-imgbar span{color:#8b949e;font:11px system-ui;padding:3px 4px;}`;

  const NEW_DOC = `<!DOCTYPE html><html><head><meta charset="utf-8"><style id="sp-doc-css">${DOC_CSS}</style></head><body><div class="sp-page"><p>Start typing…</p></div></body></html>`;

  function mount(container, opts = {}) {
    opts = opts || {};
    const root = document.createElement('div');
    root.style.cssText = 'display:flex;flex-direction:column;height:100%;width:100%;';
    const ribbon = document.createElement('div');
    ribbon.style.cssText = 'flex:none;display:flex;flex-wrap:wrap;align-items:center;gap:3px;padding:5px 8px;'
      + 'border-bottom:1px solid var(--sp-border,#30363d);background:var(--sp-panel,#161b22);';
    const stage = document.createElement('div');
    stage.style.cssText = 'flex:1;min-height:0;width:100%;position:relative;';
    const iframe = document.createElement('iframe');
    iframe.style.cssText = 'width:100%;height:100%;border:0;background:#525659;';
    stage.appendChild(iframe);
    root.append(ribbon, stage);
    container.appendChild(root);

    let doc = null, win = null, savedRange = null, selectedImg = null;
    let history = [], hist_i = -1, histBytes = 0, inputTimer = null;
    const HIST_MAX_BYTES = 80 * 1024 * 1024;

    const editRoot = () => doc && doc.body;

    /* ── selection helpers ──────────────────────────────────────────────── */
    const getSel = () => (win && win.getSelection && win.getSelection.call(win)) || (win && win.getSelection());
    function curRange() { const s = win.getSelection(); return (s && s.rangeCount) ? s.getRangeAt(0) : null; }
    function saveSel() { const r = curRange(); if (r && editRoot().contains(r.commonAncestorContainer)) savedRange = r.cloneRange(); }
    function restoreSel() { if (!savedRange) return null; const s = win.getSelection(); s.removeAllRanges(); s.addRange(savedRange); return savedRange; }

    function splitBoundaries(r) {
      if (r.startContainer.nodeType === 3 && r.startOffset > 0 && r.startOffset < r.startContainer.length) {
        const a = r.startContainer.splitText(r.startOffset); r.setStart(a, 0);
      }
      if (r.endContainer.nodeType === 3 && r.endOffset > 0 && r.endOffset < r.endContainer.length) {
        r.endContainer.splitText(r.endOffset);
      }
    }
    function selectedTextNodes(r) {
      splitBoundaries(r);
      const out = [], w = doc.createTreeWalker(editRoot(), NodeFilter.SHOW_TEXT);
      let n; while ((n = w.nextNode())) { if (n.textContent.length && r.intersectsNode(n)) out.push(n); }
      return out;
    }
    // reselect a set of (now-wrapped) nodes so formatting can be chained
    function reselect(first, last) {
      if (!first || !last) return;
      const r = doc.createRange(); r.setStartBefore(first); r.setEndAfter(last);
      const s = win.getSelection(); s.removeAllRanges(); s.addRange(r); savedRange = r.cloneRange();
    }

    /* ── inline styling (span + CSS property) ───────────────────────────── */
    function wrap(t, apply) { const sp = doc.createElement('span'); apply(sp); t.parentNode.insertBefore(sp, t); sp.appendChild(t); return sp; }
    function applyInline(apply) {
      const r = restoreSel() || curRange(); if (!r || r.collapsed) return;
      const nodes = selectedTextNodes(r); if (!nodes.length) return;
      const spans = nodes.map(t => wrap(t, apply));
      normalize(editRoot());
      reselect(spans[0], spans[spans.length - 1]);
      onEdit();
    }
    // toggle b/i/u/s: if the whole selection already has it, turn off; else on
    function toggleProp(prop, onVal, offVal, test) {
      const r = restoreSel() || curRange(); if (!r || r.collapsed) return;
      const nodes = selectedTextNodes(r); if (!nodes.length) return;
      const allOn = nodes.every(t => test(win.getComputedStyle(t.parentElement)));
      applyInline(sp => sp.style[prop] = allOn ? offVal : onVal);
    }

    function normalize(node) {
      // merge adjacent spans with identical style; drop style-less/empty spans
      const spans = [...node.querySelectorAll('span')];
      for (const sp of spans) {
        if (!sp.parentNode) continue;
        if (!sp.getAttribute('style') && !sp.className) { while (sp.firstChild) sp.parentNode.insertBefore(sp.firstChild, sp); sp.remove(); continue; }
        let nx = sp.nextSibling;
        while (nx && nx.nodeType === 1 && nx.tagName === 'SPAN' && nx.getAttribute('style') === sp.getAttribute('style')) {
          while (nx.firstChild) sp.appendChild(nx.firstChild); const rm = nx; nx = nx.nextSibling; rm.remove();
        }
      }
      node.normalize();
    }

    /* ── block styling ──────────────────────────────────────────────────── */
    function selectedBlocks() {
      const r = restoreSel() || curRange(); if (!r) return [];
      const isBlock = (el) => el && el.nodeType === 1 && /^(P|H1|H2|H3|H4|H5|H6|DIV|LI|BLOCKQUOTE|PRE|TD|TH)$/.test(el.tagName) && el !== editRoot();
      const blockOf = (n) => { let el = n.nodeType === 3 ? n.parentElement : n; while (el && !isBlock(el) && el !== editRoot()) el = el.parentElement; return isBlock(el) ? el : null; };
      const set = new Set();
      const walker = doc.createTreeWalker(editRoot(), NodeFilter.SHOW_TEXT);
      let n; let started = false;
      const sB = blockOf(r.startContainer), eB = blockOf(r.endContainer);
      if (sB) set.add(sB); if (eB) set.add(eB);
      while ((n = walker.nextNode())) { if (r.intersectsNode(n)) { const b = blockOf(n); if (b) set.add(b); } }
      return [...set];
    }
    function styleBlocks(fn) { const bs = selectedBlocks(); bs.forEach(fn); if (bs.length) onEdit(); }
    function formatBlock(tag) {
      const bs = selectedBlocks(); if (!bs.length) return;
      for (const b of bs) {
        if (b.tagName === tag || b.tagName === 'LI') continue;
        const el = doc.createElement(tag);
        if (b.getAttribute('style')) el.setAttribute('style', b.getAttribute('style'));
        while (b.firstChild) el.appendChild(b.firstChild);
        b.replaceWith(el);
      }
      onEdit();
    }

    /* ── lists ──────────────────────────────────────────────────────────── */
    function toggleList(ordered) {
      const bs = selectedBlocks(); if (!bs.length) return;
      const tag = ordered ? 'OL' : 'UL';
      const inList = bs.every(b => b.tagName === 'LI');
      if (inList) {                       // unwrap
        for (const li of bs) {
          const list = li.parentElement; const p = doc.createElement('p');
          while (li.firstChild) p.appendChild(li.firstChild);
          list.parentNode.insertBefore(p, list);
          li.remove(); if (!list.children.length) list.remove();
        }
      } else {
        const list = doc.createElement(tag);
        bs[0].parentNode.insertBefore(list, bs[0]);
        for (const b of bs) { const li = doc.createElement('li'); while (b.firstChild) li.appendChild(b.firstChild); list.appendChild(li); b.remove(); }
      }
      onEdit();
    }

    /* ── insertions ─────────────────────────────────────────────────────── */
    function insertNodeAtCaret(node) {
      const r = restoreSel() || curRange();
      if (r) { r.deleteContents(); r.insertNode(node); r.setStartAfter(node); r.collapse(true); const s = win.getSelection(); s.removeAllRanges(); s.addRange(r); }
      else { (curPage() || editRoot()).appendChild(node); }
      onEdit();
    }
    function insertLink(url) { if (!url) return; const r = restoreSel(); if (!r || r.collapsed) { const a = doc.createElement('a'); a.href = url; a.textContent = url; insertNodeAtCaret(a); return; } const a = doc.createElement('a'); a.href = url; try { a.appendChild(r.extractContents()); r.insertNode(a); } catch (_) {} onEdit(); }
    function insertImageData(dataUri) { const img = doc.createElement('img'); img.src = dataUri; img.style.maxWidth = '100%'; insertNodeAtCaret(img); }
    function insertTable(rows, cols) {
      const t = doc.createElement('table'); t.setAttribute('border', '1'); t.style.cssText = 'border-collapse:collapse;width:100%;';
      for (let i = 0; i < rows; i++) { const tr = doc.createElement('tr'); for (let j = 0; j < cols; j++) { const td = doc.createElement('td'); td.style.cssText = 'border:1px solid #999;padding:4px 6px;min-width:40px;'; td.innerHTML = '<br>'; tr.appendChild(td); } t.appendChild(tr); }
      insertNodeAtCaret(t);
    }
    function curPage() { const r = curRange(); let el = r ? (r.startContainer.nodeType === 3 ? r.startContainer.parentElement : r.startContainer) : null; while (el && !el.classList?.contains('sp-page')) el = el.parentElement; return el || doc.querySelector('.sp-page'); }
    function addPage() { const p = doc.createElement('div'); p.className = 'sp-page'; p.innerHTML = '<p><br></p>'; const pages = doc.querySelectorAll('.sp-page'); const last = pages[pages.length - 1]; if (last) last.after(p); else editRoot().appendChild(p); p.querySelector('p').focus?.(); onEdit(); }

    /* ── image selection + resize/move handles ──────────────────────────── */
    let handles = [], imgbar = null;
    function clearImgSel() { if (selectedImg) selectedImg.classList.remove('sp-img-sel'); selectedImg = null; handles.forEach(h => h.remove()); handles = []; if (imgbar) { imgbar.remove(); imgbar = null; } }
    function selectImg(img) {
      clearImgSel(); selectedImg = img; img.classList.add('sp-img-sel');
      const CORNERS = [['nw', 0, 0], ['ne', 1, 0], ['sw', 0, 1], ['se', 1, 1]];
      handles = CORNERS.map(() => { const h = doc.createElement('div'); h.className = 'sp-handle'; doc.body.appendChild(h); return h; });
      imgbar = doc.createElement('div'); imgbar.className = 'sp-imgbar';
      const floatBtn = document.createElement('button'); floatBtn.textContent = 'Float';
      const sizeLbl = document.createElement('span');
      imgbar.append(floatBtn, sizeLbl); doc.body.appendChild(imgbar);
      const isFloat = () => img.style.position === 'absolute';
      const syncFloat = () => { floatBtn.classList.toggle('on', isFloat()); };
      floatBtn.onmousedown = (e) => e.preventDefault();
      floatBtn.onclick = () => {
        if (isFloat()) { img.style.position = ''; img.style.left = img.style.top = ''; }
        else { const pg = closestPage(img); if (pg) pg.style.position = 'relative'; const r = img.getBoundingClientRect(), pr = (pg || doc.body).getBoundingClientRect(); img.style.position = 'absolute'; img.style.left = Math.round(img.offsetLeft) + 'px'; img.style.top = Math.round(img.offsetTop) + 'px'; }
        syncFloat(); place(); onEdit();
      };
      const place = () => {
        const r = img.getBoundingClientRect();
        CORNERS.forEach(([, cx, cy], i) => { handles[i].style.left = (r.left + cx * r.width - 5) + 'px'; handles[i].style.top = (r.top + cy * r.height - 5) + 'px'; handles[i].style.cursor = (cx === cy ? 'nwse' : 'nesw') + '-resize'; });
        imgbar.style.left = r.left + 'px'; imgbar.style.top = Math.max(2, r.top - 30) + 'px';
        sizeLbl.textContent = Math.round(r.width) + '×' + Math.round(r.height) + (isFloat() ? ' · ' + Math.round(img.offsetLeft) + ',' + Math.round(img.offsetTop) : '');
      };
      // resize by dragging a corner
      CORNERS.forEach(([, cx, cy], i) => {
        handles[i].onmousedown = (e) => {
          e.preventDefault(); const sx = e.clientX, sw = img.getBoundingClientRect().width, ar = img.getBoundingClientRect().height / sw;
          const mv = (ev) => { let nw = Math.max(20, sw + (cx ? (ev.clientX - sx) : (sx - ev.clientX))); img.style.width = Math.round(nw) + 'px'; img.style.height = Math.round(nw * ar) + 'px'; place(); };
          const up = () => { doc.removeEventListener('mousemove', mv); doc.removeEventListener('mouseup', up); onEdit(); };
          doc.addEventListener('mousemove', mv); doc.addEventListener('mouseup', up);
        };
      });
      // move (float only) by dragging the image
      img.onmousedown = (e) => {
        if (!isFloat()) return; e.preventDefault();
        const sx = e.clientX, sy = e.clientY, ol = img.offsetLeft, ot = img.offsetTop;
        const mv = (ev) => { img.style.left = Math.round(ol + ev.clientX - sx) + 'px'; img.style.top = Math.round(ot + ev.clientY - sy) + 'px'; place(); };
        const up = () => { doc.removeEventListener('mousemove', mv); doc.removeEventListener('mouseup', up); onEdit(); };
        doc.addEventListener('mousemove', mv); doc.addEventListener('mouseup', up);
      };
      syncFloat(); place();
      win.addEventListener('scroll', place, true); win.addEventListener('resize', place);
      img._spPlace = place;
    }
    function closestPage(el) { while (el && !el.classList?.contains('sp-page')) el = el.parentElement; return el; }

    /* ── history (byte-budgeted undo/redo) ──────────────────────────────── */
    function snapshot() {
      const html = editRoot().innerHTML;
      if (history[hist_i] === html) return;
      history = history.slice(0, hist_i + 1);
      history.push(html); hist_i = history.length - 1; histBytes += html.length * 2;
      while (histBytes > HIST_MAX_BYTES && history.length > 1) { histBytes -= history.shift().length * 2; hist_i--; }
    }
    function restore(i) { if (i < 0 || i >= history.length) return; hist_i = i; clearImgSel(); editRoot().innerHTML = history[i]; syncRibbon(); }
    function undo() { if (hist_i > 0) restore(hist_i - 1); }
    function redo() { if (hist_i < history.length - 1) restore(hist_i + 1); }
    function onEdit() { clearTimeout(inputTimer); inputTimer = setTimeout(snapshot, 400); markDirty(); }

    /* ── dirty / save ───────────────────────────────────────────────────── */
    let dirty = false, saveBtn = null;
    function markDirty() { dirty = true; if (saveBtn) saveBtn.disabled = false; }

    /* ── serialize (strip editor-only chrome) ───────────────────────────── */
    function getHTML() {
      const clone = doc.documentElement.cloneNode(true);
      clone.querySelectorAll('#sp-editor-css,.sp-handle,.sp-imgbar').forEach(n => n.remove());
      clone.querySelectorAll('.sp-img-sel').forEach(n => n.classList.remove('sp-img-sel'));
      clone.querySelectorAll('[contenteditable]').forEach(n => n.removeAttribute('contenteditable'));
      return '<!DOCTYPE html>\n' + clone.outerHTML;
    }

    /* ── ribbon ─────────────────────────────────────────────────────────── */
    function btn(label, title, fn, opt = {}) {
      const b = document.createElement('button'); b.className = 'ghost'; b.innerHTML = label; b.title = title;
      b.style.cssText = 'min-width:26px;padding:3px 7px;font-size:0.82rem;line-height:1;' + (opt.css || '');
      b.addEventListener('mousedown', e => e.preventDefault());
      b.onclick = () => { fn(); };
      ribbon.appendChild(b); return b;
    }
    function sep() { const s = document.createElement('span'); s.style.cssText = 'width:1px;height:20px;background:var(--sp-border,#30363d);margin:0 3px;'; ribbon.appendChild(s); }
    function select(items, title, fn, width) {
      const s = document.createElement('select'); s.title = title;
      s.style.cssText = 'font-size:0.8rem;padding:2px 4px;max-width:' + (width || '120px') + ';background:var(--sp-bg,#0d1117);color:var(--sp-text,#e6edf3);border:1px solid var(--sp-border,#30363d);border-radius:4px;';
      for (const it of items) { const o = document.createElement('option'); if (Array.isArray(it)) { o.textContent = it[0]; o.value = it[1]; } else { o.textContent = o.value = it; } s.appendChild(o); }
      s.addEventListener('mousedown', () => saveSel());
      s.onchange = () => { fn(s.value); s.blur(); };
      ribbon.appendChild(s); return s;
    }
    function colorBtn(label, title, fn) {
      const wrap = document.createElement('label'); wrap.title = title; wrap.className = 'ghost';
      wrap.style.cssText = 'display:inline-flex;align-items:center;min-width:26px;padding:3px 6px;font-size:0.82rem;cursor:pointer;';
      wrap.textContent = label;
      const inp = document.createElement('input'); inp.type = 'color'; inp.style.cssText = 'width:0;height:0;opacity:0;position:absolute;';
      wrap.addEventListener('mousedown', () => saveSel());
      inp.oninput = () => fn(inp.value);
      wrap.appendChild(inp); ribbon.appendChild(wrap); return wrap;
    }

    function buildRibbon() {
      if (opts.onSave) { saveBtn = btn('Save', 'Save (Ctrl+S)', doSave, { css: 'font-weight:600;color:#2ea043;' }); saveBtn.disabled = true; }
      btn('↶', 'Undo (Ctrl+Z)', undo); btn('↷', 'Redo (Ctrl+Y)', redo); sep();
      select(BLOCKS, 'Paragraph style', formatBlock, '110px');
      select(FONTS, 'Font', (v) => applyInline(sp => sp.style.fontFamily = v === 'Inherit' ? '' : v), '120px');
      select(SIZES, 'Font size', (v) => applyInline(sp => sp.style.fontSize = v + 'pt'), '60px'); sep();
      btn('<b>B</b>', 'Bold', () => toggleProp('fontWeight', '700', '400', s => +s.fontWeight >= 600 || s.fontWeight === 'bold'));
      btn('<i>I</i>', 'Italic', () => toggleProp('fontStyle', 'italic', 'normal', s => s.fontStyle === 'italic'));
      btn('<u>U</u>', 'Underline', () => toggleProp('textDecorationLine', 'underline', 'none', s => /underline/.test(s.textDecorationLine || s.textDecoration)));
      btn('<s>S</s>', 'Strikethrough', () => toggleProp('textDecorationLine', 'line-through', 'none', s => /line-through/.test(s.textDecorationLine || s.textDecoration)));
      colorBtn('A', 'Text color', (c) => applyInline(sp => sp.style.color = c));
      colorBtn('▉', 'Highlight', (c) => applyInline(sp => sp.style.backgroundColor = c)); sep();
      btn('⯇', 'Align left', () => styleBlocks(b => b.style.textAlign = 'left'));
      btn('≡', 'Align center', () => styleBlocks(b => b.style.textAlign = 'center'));
      btn('⯈', 'Align right', () => styleBlocks(b => b.style.textAlign = 'right'));
      btn('☰', 'Justify', () => styleBlocks(b => b.style.textAlign = 'justify'));
      select(LINEH.map(v => ['↕ ' + v, v]), 'Line spacing', (v) => styleBlocks(b => b.style.lineHeight = v), '70px'); sep();
      btn('• List', 'Bullet list', () => toggleList(false));
      btn('1. List', 'Numbered list', () => toggleList(true));
      btn('⇥', 'Indent', () => styleBlocks(b => b.style.marginLeft = (parseFloat(b.style.marginLeft || 0) + 24) + 'px'));
      btn('⇤', 'Outdent', () => styleBlocks(b => b.style.marginLeft = Math.max(0, parseFloat(b.style.marginLeft || 0) - 24) + 'px')); sep();
      btn('🔗', 'Insert link', () => { saveSel(); const u = prompt('Link URL:'); if (u) insertLink(u); });
      btn('🖼', 'Insert image', () => { saveSel(); pickImage(); });
      btn('▦', 'Insert table', () => { saveSel(); const s = prompt('Table size (rows x cols):', '3x3'); if (s) { const m = /(\d+)\s*[x×]\s*(\d+)/.exec(s); if (m) insertTable(+m[1], +m[2]); } });
      btn('⤓ Page', 'Add page', addPage); sep();
      btn('🔍', 'Find & replace', toggleFind);
    }

    /* ── image picker / drag / paste ────────────────────────────────────── */
    function fileToImg(file) { if (!file || !/^image\//.test(file.type)) return; const rd = new FileReader(); rd.onload = () => insertImageData(rd.result); rd.readAsDataURL(file); }
    function pickImage() { const inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/*'; inp.onchange = () => { restoreSel(); fileToImg(inp.files[0]); }; inp.click(); }

    /* ── find & replace ─────────────────────────────────────────────────── */
    let findBar = null;
    function toggleFind() {
      if (findBar) { findBar.remove(); findBar = null; return; }
      findBar = document.createElement('div');
      findBar.style.cssText = 'position:absolute;top:6px;right:16px;z-index:20;display:flex;gap:4px;background:var(--sp-panel,#161b22);border:1px solid var(--sp-border,#30363d);border-radius:6px;padding:6px;box-shadow:0 2px 10px rgba(0,0,0,.4);';
      const f = document.createElement('input'), rep = document.createElement('input'), go = document.createElement('button'), all = document.createElement('button');
      f.placeholder = 'Find'; rep.placeholder = 'Replace'; go.textContent = 'Replace'; all.textContent = 'All'; go.className = all.className = 'ghost';
      [f, rep].forEach(i => i.style.cssText = 'font-size:0.8rem;padding:3px 6px;background:var(--sp-bg,#0d1117);color:var(--sp-text,#e6edf3);border:1px solid var(--sp-border,#30363d);border-radius:4px;');
      const doReplace = (global) => { if (!f.value) return; const html = editRoot().innerHTML; const re = new RegExp(f.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), global ? 'g' : ''); editRoot().innerHTML = html.replace(re, rep.value); onEdit(); };
      go.onclick = () => doReplace(false); all.onclick = () => doReplace(true);
      findBar.append(f, rep, go, all); stage.appendChild(findBar); f.focus();
    }

    /* ── ribbon state sync ──────────────────────────────────────────────── */
    function syncRibbon() {/* lightweight; selects reflect nothing persistent in v1 */}

    /* ── boot ───────────────────────────────────────────────────────────── */
    function doSave() {
      if (!opts.onSave) return;
      saveBtn.textContent = 'Saving…'; saveBtn.disabled = true;
      Promise.resolve(opts.onSave(getHTML()))
        .then(() => { dirty = false; saveBtn.textContent = 'Saved ✓'; })
        .catch(e => { saveBtn.textContent = 'Save failed'; console.error(e); })
        .finally(() => setTimeout(() => { saveBtn.textContent = 'Save'; saveBtn.disabled = dirty ? false : true; }, 1200));
    }

    let initialHtml = (opts.html && opts.html.trim()) ? opts.html : NEW_DOC;
    // ensure the doc carries sp-doc-css and a page wrapper for a clean editing frame
    iframe.srcdoc = initialHtml;
    iframe.addEventListener('load', () => {
      doc = iframe.contentDocument; win = iframe.contentWindow;
      // inject doc-css (saved) if absent, and editor-css (transient, stripped on save)
      if (!doc.getElementById('sp-doc-css')) { const s = doc.createElement('style'); s.id = 'sp-doc-css'; s.textContent = DOC_CSS; (doc.head || doc.documentElement).appendChild(s); }
      const es = doc.createElement('style'); es.id = 'sp-editor-css'; es.textContent = EDITOR_CSS; (doc.head || doc.documentElement).appendChild(es);
      // Wrap loose content into a page ONLY for documents with no structure of
      // their own — never wrap a doc that already lays itself out (its own .page
      // sections, divs, tables…), or we'd nest A4 pages inside A4 pages and it
      // overflows horizontally. Detect existing structure broadly.
      const hasOwnStructure = doc.querySelector('.sp-page')
        || (doc.body && [...doc.body.children].some(el => /^(DIV|SECTION|ARTICLE|MAIN|TABLE|HEADER|FOOTER|ASIDE)$/.test(el.tagName)))
        || doc.querySelector('[class*="page" i]');
      if (!hasOwnStructure && doc.body) { const pg = doc.createElement('div'); pg.className = 'sp-page'; while (doc.body.firstChild) pg.appendChild(doc.body.firstChild); doc.body.appendChild(pg); }
      doc.body.contentEditable = 'true';
      doc.body.addEventListener('input', onEdit);
      doc.body.addEventListener('mousedown', (e) => { if (e.target.tagName === 'IMG') { selectImg(e.target); } else { clearImgSel(); } });
      doc.addEventListener('selectionchange', saveSel);
      doc.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); doSave(); }
        else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); undo(); }
        else if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'y' || (e.shiftKey && e.key.toLowerCase() === 'z'))) { e.preventDefault(); redo(); }
      });
      // drag-drop + paste images
      doc.body.addEventListener('dragover', (e) => e.preventDefault());
      doc.body.addEventListener('drop', (e) => { const f = e.dataTransfer && e.dataTransfer.files[0]; if (f && /^image\//.test(f.type)) { e.preventDefault(); fileToImg(f); } });
      doc.body.addEventListener('paste', (e) => { const items = e.clipboardData && e.clipboardData.items; if (!items) return; for (const it of items) { if (/^image\//.test(it.type)) { e.preventDefault(); fileToImg(it.getAsFile()); return; } } });
      history = [editRoot().innerHTML]; hist_i = 0; histBytes = history[0].length * 2;
      buildRibbon();
    }, { once: true });

    return {
      getHTML,
      isDirty: () => dirty,
      destroy() { try { clearImgSel(); } catch (_) {} root.remove(); },
    };
  }

  window.SandpieHtmlEditor = { mount };
})();
