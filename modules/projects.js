/* =============================================================================
   projects.js — BETA (/app-beta) projects fork
   -----------------------------------------------------------------------------
   Every conversation belongs to a PROJECT: an arbitrary folder in the user's
   Dropbox. This module owns the project registry, the folder picker, and the
   new-project / new-chat-in-project flows. Conversation rendering (grouping the
   sidebar by project) lives in conversations.js and calls back into here for the
   project list + button handlers. Loaded on every shell but INERT unless beta.

   Registry: sandpie/config/projects.json — under the exempt sandpie/ subtree, so
   it syncs across the user's devices like other app metadata.
   ========================================================================== */
(function () {
  'use strict';
  if (!window.SANDPIE_BETA) return;                 // beta-only feature
  if (!window.Sandpie) { console.warn('[projects] no Sandpie host'); return; }

  const REG_PATH = 'sandpie/config/projects.json';
  const ACTIVE_KEY = 'sandpie-beta-active-project';   // localStorage: active project root ('' = Personal)
  const O = () => Sandpie.opfs;
  const P = () => (Sandpie.syncProvider && Sandpie.syncProvider()) || null;
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const norm = (s) => String(s || '').replace(/\/+$/, '').toLowerCase();

  // ---- "Personal" project: the user's own Dropbox workspace folder -----------
  // A built-in, always-present project so a conversation always has somewhere to
  // write. Legacy conversations with no projectRoot map here. Its folder is the
  // sync workspace root (e.g. /sandpie); app metadata lives in its sandpie/
  // subfolder, so user files sit alongside without collision.
  function personalRoot() { const p = P(); return (p && p.workingRoot && p.workingRoot()) || '/sandpie'; }
  function personalProject() { return { name: 'Personal', root: personalRoot(), ns: 'home', personal: true }; }
  // Does a conversation belong to a given project? Personal also claims the
  // projectless (legacy) conversations.
  function convInProject(conv, project) {
    if (!project) return false;
    if (project.personal) return !conv.projectRoot || norm(conv.projectRoot) === norm(project.root);
    return norm(conv.projectRoot) === norm(project.root);
  }

  // ---- active project (per-device selection) --------------------------------
  function activeRoot() { try { return localStorage.getItem(ACTIVE_KEY) || ''; } catch { return ''; } }
  function setActiveRoot(root) { try { localStorage.setItem(ACTIVE_KEY, root || ''); } catch (_) {} }
  async function activeProject() {
    const root = activeRoot();
    if (!root) return personalProject();
    const reg = await loadRegistry();
    const p = reg.find(x => norm(x.root) === norm(root));
    return p || personalProject();
  }
  function setActiveProject(project) { setActiveRoot(project && !project.personal ? project.root : ''); }
  // All projects for the dropdown: Personal first, then the registry (newest-used).
  async function allProjects() { return [personalProject(), ...(await projectsForSidebar())]; }

  // ---- registry ------------------------------------------------------------
  async function loadRegistry() {
    try { const a = JSON.parse(await O().read(REG_PATH)); return Array.isArray(a) ? a : []; }
    catch { return []; }
  }
  async function saveRegistry(list) {
    try { await O().write(REG_PATH, JSON.stringify(list, null, 2)); Sandpie.events.emit('file:changed', REG_PATH); }
    catch (e) { console.warn('[projects] registry save failed:', e); }
  }
  async function addProject(p) {
    const list = await loadRegistry();
    if (!list.find(x => String(x.root).toLowerCase() === String(p.root).toLowerCase())) { list.push(p); await saveRegistry(list); }
    return list;
  }
  async function removeProject(root) {
    const list = (await loadRegistry()).filter(x => String(x.root).toLowerCase() !== String(root).toLowerCase());
    await saveRegistry(list);
    return list;
  }
  async function touchProject(root) {
    const list = await loadRegistry();
    const p = list.find(x => String(x.root).toLowerCase() === String(root).toLowerCase());
    if (p) { p.lastUsed = new Date().toISOString(); await saveRegistry(list); }
  }
  // Projects newest-used first, for the sidebar.
  async function projectsForSidebar() {
    const list = await loadRegistry();
    return list.slice().sort((a, b) => String(b.lastUsed || b.created || '').localeCompare(String(a.lastUsed || a.created || '')));
  }

  // ---- new-conversation stamping ------------------------------------------
  // newConversation() (conversations.js) calls this to learn which project a new
  // chat belongs to: the currently-selected project.
  async function projectForNewChat() {
    const p = await activeProject();
    return { root: p.root, ns: p.ns || 'home' };
  }

  // ---- folder picker -------------------------------------------------------
  // A modal that browses the user's Dropbox (home namespace + team folders) and
  // resolves to { name, root, ns } — or null if cancelled. Reuses the share-modal
  // CSS. Navigation uses the sync provider's cloudList/listTeamFolders/cloudMkdir.
  function pickFolder() {
    return new Promise((resolve) => {
      const prov = P();
      if (!prov || !prov.isConnected || !prov.isConnected()) { alert('Connect Dropbox first (Settings → Cloud sync).'); resolve(null); return; }
      // Navigation state: which namespace (team?) and the absolute path we're in.
      // null loc = the top-level roots menu (My Dropbox / Team folders).
      let loc = null;   // { team:boolean, path:string }
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
        // Up / back — at the root, "back" reveals the roots menu (home / team switch).
        if (next.path) {
          browser.appendChild(rowEl('‹ up', () => navigate({ team: next.team, path: next.path.replace(/\/[^/]+$/, '') }), false));
        } else {
          browser.appendChild(rowEl('⋯ switch (home / team folders)', renderRoots, false));
        }
        const dirs = entries.filter(e => (e.kind === 'folder' || e['.tag'] === 'folder'));
        dirs.sort((a, b) => String(a.name || '').localeCompare(String(b.name || '')));
        if (!dirs.length) browser.appendChild(rowEl('(no subfolders — you can Use this folder or make a New folder here)', () => {}, false));
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
        const name = (prompt('New folder name:') || '').trim();
        if (!name) return;
        const full = (loc.path || '') + '/' + name;
        msg.textContent = 'Creating…';
        try {
          if (prov.cloudMkdir) await prov.cloudMkdir(full, { team: loc.team });
          msg.textContent = '';
          navigate({ team: loc.team, path: full });
        } catch (e) { msg.textContent = 'Create failed: ' + ((e && e.message) || e); }
      };

      // Start at the plain Dropbox root (home namespace); the roots menu (home/team
      // switch) is one click away via "switch" at the root level.
      navigate({ team: false, path: '' });
    });
  }

  // New-project flow: pick a folder, name it, register it, select it as active.
  // Returns the created project (or null if cancelled). Does NOT start a chat —
  // the user creates one with "+ New chat" once the project is selected.
  async function newProjectFlow() {
    const picked = await pickFolder();
    if (!picked) return null;
    let name = (prompt('Project name:', picked.name) || '').trim();
    if (!name) name = picked.name;
    const now = new Date().toISOString();
    const proj = { name, root: picked.root, ns: picked.ns, created: now, lastUsed: now };
    await addProject(proj);
    setActiveProject(proj);
    if (typeof Sandpie.refreshConversations === 'function') await Sandpie.refreshConversations();
    return proj;
  }

  window.SandpieProjects = {
    loadRegistry, saveRegistry, addProject, removeProject, touchProject,
    projectsForSidebar, allProjects, personalProject, convInProject,
    activeProject, setActiveProject, projectForNewChat,
    pickFolder, newProjectFlow,
  };
})();
