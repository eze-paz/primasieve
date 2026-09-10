/* =============================================================================
   files-modal.js — OS-like Files explorer modal
   Opens from the sidebar header folder button (SandpieFilesModal.open()).
   Reuses opfs.js primitives for listing, navigation, and every right-click
   action (copy path, share, rename, upload, new folder/file, open in new tab,
   pin, download, zip, LaTeX, delete, sort-by). The sidebar Files collapsible
   was removed; #opfsPath/#fileList now live inside this modal, so all existing
   opfs.js render paths keep working unchanged.
   ============================================================================= */
(function () {
  'use strict';

  const SORT_KEY = 'sandpie-files-sort';

  function el(id) { return document.getElementById(id); }

  function ensureDom() {
    if (el('filesModal')) return;
    const wrap = document.createElement('div');
    wrap.className = 'files-modal';
    wrap.id = 'filesModal';
    wrap.style.display = 'none';
    wrap.innerHTML =
      '<div class="fm-panel">' +
        '<div class="fm-title">' +
          '<span class="material-symbols-outlined" style="font-size:18px; color:var(--sp-text-dim);">folder_open</span>' +
          '<span class="fm-name">Files</span>' +
          '<button class="fm-close" title="Close (Esc)">✕</button>' +
        '</div>' +
        '<div class="fm-nav">' +
          '<button class="fm-ic" id="fmUp" title="Up"><span class="material-symbols-outlined">arrow_upward</span></button>' +
          '<input id="opfsPath" value="/" spellcheck="false">' +
          '<button class="fm-ic" id="fmViewList" title="List view"><span class="material-symbols-outlined">view_list</span></button>' +
          '<button class="fm-ic" id="fmViewGrid" title="Grid view"><span class="material-symbols-outlined">grid_view</span></button>' +
        '</div>' +
        '<div class="fm-body"><ul class="fs-list" id="fileList"></ul></div>' +
        '<div class="fm-foot">' +
          '<span id="fmCount"></span>' +
          '<span class="fm-sp"></span>' +
          '<button id="fmUpload">Upload</button>' +
          '<button id="fmNewFolder">New folder</button>' +
          '<button id="fmNewFile">New file</button>' +
        '</div>' +
        '<div id="persistBanner" class="persist-banner" style="display:none">' +
          '<span class="persist-icon" id="persistIcon"></span>' +
          '<span class="persist-msg" id="persistMsg"></span>' +
          '<button class="persist-btn ghost" id="persistBtn" style="display:none">Protect files</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(wrap);

    wrap.querySelector('.fm-close').onclick = close;
    wrap.addEventListener('mousedown', (e) => { if (e.target === wrap) close(); });
    el('fmUp').onclick = () => window.opfsUp();
    const syncViewBtns = () => {
      const grid = localStorage.getItem('sandpie-files-view') === 'grid';
      el('fmViewList').classList.toggle('fm-view-on', !grid);
      el('fmViewGrid').classList.toggle('fm-view-on', grid);
    };
    el('fmViewList').onclick = () => { localStorage.setItem('sandpie-files-view', 'list'); syncViewBtns(); opfs.refreshFileList(); };
    el('fmViewGrid').onclick = () => { localStorage.setItem('sandpie-files-view', 'grid'); syncViewBtns(); opfs.refreshFileList(); };
    syncViewBtns();
    el('fmUpload').onclick = () => opfs.promptUpload(window.opfsCurrentPath());
    el('fmNewFolder').onclick = () => opfs.createFolder();
    el('fmNewFile').onclick = () => opfs.createFile();

    const pathEl = el('opfsPath');
    pathEl.addEventListener('change', () => opfs.refreshFileList());
    pathEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') opfs.refreshFileList(); });

    // Blank-area right-click: upload / new folder / new file (same as the old sidebar)
    el('fileList').addEventListener('contextmenu', (ev) => {
      if (ev.target.closest('li')) return;
      ev.preventDefault();
      opfs.showContextMenu(ev.clientX, ev.clientY, [
        { label: 'Upload files', action: () => opfs.promptUpload(window.opfsCurrentPath()) },
        { label: 'New folder', action: () => opfs.createFolder() },
        { label: 'New file', action: () => opfs.createFile() },
      ]);
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && el('filesModal').style.display !== 'none') close();
    });
  }

  function open() {
    ensureDom();
    el('filesModal').style.display = '';
    const grid = localStorage.getItem('sandpie-files-view') === 'grid';
    el('fmViewList').classList.toggle('fm-view-on', !grid);
    el('fmViewGrid').classList.toggle('fm-view-on', grid);
    opfs.refreshFileList();
    try { if (window.sandpiePersistence && sandpiePersistence.check) sandpiePersistence.check(); } catch (_) {}
  }

  function close() { const m = el('filesModal'); if (m) m.style.display = 'none'; }

  window.SandpieFilesModal = { open, close };
})();
