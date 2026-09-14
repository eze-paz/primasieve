/* =============================================================================
   projects.js — project registry + folder picker (non-beta)
   -----------------------------------------------------------------------------
   A project = a named root folder in the user's Dropbox that conversations can
   be filed under. This module owns the registry (sandpie/config/projects.json —
   under the exempt sandpie/ subtree, so it syncs across devices like pins.json)
   and the Dropbox folder-picker modal used by "+ New project".

   Registry entries: { id, name, root, ns, created, lastUsed }
     - id: stable short id — conversations bind to projectId, NOT to root/name,
       so renaming or re-pointing a project never orphans them.
   No beta gating, no sidebar grouping, no per-project conversation folders.
   ========================================================================== */
(function () {
  'use strict';
  if (!window.Sandpie) { console.warn('[projects] no Sandpie host'); return; }

  const REG_PATH = 'sandpie/config/projects.json';
  const O = () => Sandpie.opfs;
  const P = () => (Sandpie.syncProvider && Sandpie.syncProvider()) || null;
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const norm = (s) => String(s || '').replace(/\/+$/, '').toLowerCase();

  let _cache = null;            // last loaded registry (array)

  const newId = () => 'p' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

  // ---- registry ------------------------------------------------------------
  async function loadRegistry() {
    try {
      const a = JSON.parse(await O().read(REG_PATH));
      const list = Array.isArray(a) ? a : [];
      // Backfill stable ids for pre-id entries (e.g. the legacy "test" project).
      let dirty = false;
      for (const p of list) { if (!p.id) { p.id = newId(); dirty = true; } }
      if (dirty) await saveRegistry(list);
      _cache = list;
      return list;
    } catch { _cache = []; return []; }
  }
  async function saveRegistry(list) {
    _cache = list;
    try {
      await O().write(REG_PATH, JSON.stringify(list, null, 2));
      Sandpie.events.emit('file:changed', REG_PATH);
    } catch (e) { console.warn('[projects] registry save failed:', e); }
  }
  // All projects, newest-used first (for the picker list).
  async function list() {
    const reg = await loadRegistry();
    return reg.slice().sort((a, b) => String(b.lastUsed || b.created || '').localeCompare(String(a.lastUsed || a.created || '')));
  }
  function cached() { return _cache ? _cache.slice() : null; }
  function byId(id) { return (_cache || []).find(x => x.id === id) || null; }
  async function create(name, root, ns) {
    const reg = await loadRegistry();
    const existing = reg.find(x => norm(x.root) === norm(root));
    if (existing) return existing;
    const now = new Date().toISOString();
    const p = { id: newId(), name: String(name || root).trim() || root, root, ns: ns || 'home', created: now, lastUsed: now };
    reg.push(p);
    await saveRegistry(reg);
    return p;
  }
  async function rename(id, name) {
    const reg = await loadRegistry();
    const p = reg.find(x => x.id === id);
    if (p && String(name || '').trim()) { p.name = String(name).trim(); await saveRegistry(reg); }
    return p;
  }
  async function remove(id) {
    const reg = (await loadRegistry()).filter(x => x.id !== id);
    await saveRegistry(reg);
  }
  async function touch(id) {
    const reg = await loadRegistry();
    const p = reg.find(x => x.id === id);
    if (p) { p.lastUsed = new Date().toISOString(); await saveRegistry(reg); }
  }

  // ---- folder picker -------------------------------------------------------
  // Modal that browses the user's Dropbox (home namespace + team folders) and
  // resolves to { name, root, ns } — or null if cancelled. Reuses the share-modal
  // CSS. Navigation uses the sync provider's cloudList/listTeamFolders.
  function pickFolder() {
    return new Promise((resolve) => {
      const prov = P();
      if (!prov || !prov.isConnected || !prov.isConnected()) { alert('Connect Dropbox first (Settings → Cloud sync).'); resolve(null); return; }
      let loc = null;   // { team:boolean, path:string } — null = the roots menu
      const back = document.createElement('div'); back.className = 'share-modal-back';
      back.innerHTML =
        '<div class="share-modal" data-chrome style="min-width:min(520px,92vw)">' +
          '<div class="share-modal-h">Choose a project folder</div>' +
          '<div class="proj-crumbs" style="font-size:.75rem;opacity:.8;margin-bottom:.4rem;word-break:break-all"></div>' +
          '<div class="proj-browser" style="max-height:46vh;overflow:auto;border:1px solid var(--border,#3334);border-radius:6px"></div>' +
          '<div class="share-modal-btns" style="margin-top:.6rem">' +
            '<button class="ghost" data-act="cancel">Cancel</button>' +
            '<button class="ghost" data-act="newfolder">New folder here</button>' +
            '<button class="ghost share-primary" data-act="use">Use this folder</button>' +
          '</div>' +
          '<div class="share-modal-msg"></div>' +
        '</div>';
      document.body.appendChild(back);
      const crumbs = back.querySelector('.proj-crumbs');
      const browser = back.querySelector('.proj-browser');
      const msg = back.querySelector('.share-modal-msg');
      const useBtn = back.querySelector('[data-act="use"]');
      const newBtn = back.querySelector('[data-act="newfolder"]');
      const close = (val) => { back.remove(); resolve(val || null); };
      back.addEventListener('click', (e) => { if (e.target === back) close(null); });
      back.querySelector('[data-act="cancel"]').onclick = () => close(null);

      const rowEl = (label, onClick, isDir) => {
        const d = document.createElement('div');
        d.style.cssText = 'padding:.4rem .6rem;cursor:pointer;border-bottom:1px solid var(--border,#3332);display:flex;gap:.4rem;align-items:center';
        d.innerHTML = (isDir ? '📁 ' : '') + esc(label);
        d.onmouseenter = () => d.style.background = 'var(--hover,#8881)';
        d.onmouseleave = () => d.style.background = '';
        d.onclick = onClick;
        return d;
      };

      async function renderRoots() {
        loc = null;
        crumbs.textContent = 'Dropbox';
        useBtn.style.visibility = 'hidden'; newBtn.style.visibility = 'hidden';
        browser.replaceChildren();
        browser.appendChild(rowEl('My Dropbox', () => navigate({ team: false, path: '' }), true));
        browser.appendChild(rowEl('Team folders', async () => {
          msg.textContent = 'Loading team folders…';
          let depts = [];
          try { depts = (prov.listTeamFolders ? await prov.listTeamFolders() : []) || []; } catch (_) {}
          msg.textContent = '';
          browser.replaceChildren();
          browser.appendChild(rowEl('‹ back', renderRoots, false));
          if (!depts.length) browser.appendChild(rowEl('(no team folders)', () => {}, false));
          for (const t of depts) {
            const p = t.path || t.root || ('/' + (t.name || ''));
            browser.appendChild(rowEl(t.name || p, () => navigate({ team: true, path: p }), true));
          }
        }, true));
      }

      async function navigate(next) {
        loc = next;
        crumbs.textContent = (next.team ? 'Team ' : '') + (next.path || '/');
        useBtn.style.visibility = 'visible'; newBtn.style.visibility = 'visible';
        msg.textContent = 'Loading…';
        let entries = [];
        try { entries = (await prov.cloudList(next.path || '', false, { team: next.team })) || []; }
        catch (e) { msg.textContent = 'Error: ' + ((e && e.message) || e); return; }
        msg.textContent = '';
        browser.replaceChildren();
        if (next.path) browser.appendChild(rowEl('‹ up', () => navigate({ team: next.team, path: next.path.replace(/\/[^/]+$/, '') }), false));
        const dirs = entries.filter(e => (e.kind === 'folder' || e['.tag'] === 'folder'));
        dirs.sort((a, b) => String(a.name || '').localeCompare(String(b.name || '')));
        if (!dirs.length) browser.appendChild(rowEl('(no subfolders — you can Use this folder)', () => {}, false));
        for (const e of dirs) {
          const full = (e.path_display || e.path_lower || (next.path + '/' + e.name));
          browser.appendChild(rowEl(e.name, () => navigate({ team: next.team, path: full }), true));
        }
      }

      useBtn.onclick = () => {
        if (!loc || !loc.path) { msg.textContent = 'Open a folder first (the Dropbox root itself can\'t be a project).'; return; }
        close({ name: loc.path.split('/').filter(Boolean).pop(), root: loc.path, ns: loc.team ? 'team' : 'home' });
      };
      newBtn.onclick = async () => {
        if (!loc) { msg.textContent = 'Open a location first.'; return; }
        if (!prov.cloudMkdir) { msg.textContent = 'Folder creation not available on this provider.'; return; }
        const name = (prompt('New folder name:') || '').trim();
        if (!name) return;
        const full = (loc.path || '') + '/' + name;
        msg.textContent = 'Creating…';
        try {
          await prov.cloudMkdir(full, { team: loc.team });
          msg.textContent = '';
          navigate({ team: loc.team, path: full });
        } catch (e) { msg.textContent = 'Create failed: ' + ((e && e.message) || e); }
      };

      navigate({ team: true, path: '' });   // start at the team root (most projects live there)
    });
  }

  // New-project flow: pick a folder, name it, register it. Returns the created
  // project (or null if cancelled). Binding to the current conversation is the
  // caller's job (conversations.js).
  async function newProjectFlow() {
    const picked = await pickFolder();
    if (!picked) return null;
    let name = (prompt('Project name:', picked.name) || '').trim();
    if (!name) name = picked.name;
    return await create(name, picked.root, picked.ns);
  }

  window.SandpieProjects = {
    REG_PATH, loadRegistry, saveRegistry, list, cached, byId,
    create, rename, remove, touch, pickFolder, newProjectFlow,
  };
})();
