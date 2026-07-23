// sharing.js — share skills / artifacts / folders across an org, with scoped
// audiences (a person, a team, cross-team, everyone) and silent auto-update of
// accepted subscriptions. Browser-only; rides the existing OPFS + Dropbox sync.
//
// MODEL
//   Hub (registry)      sandpie/shared-hub/index.json      catalog + ACLs
//                       sandpie/shared-hub/packages/<id>/v/<n>/…   published content
//   Installed (mine)    sandpie/shared/<id>/…              read-only, auto-updated
//   Subscriptions       sandpie/config/shares.json         {accepted:{id:ver}, dismissed:[]}
//
//   index.json:
//     { packages: { "<id>": {
//         id, kind:'skill'|'artifact'|'folder', title, publisher:<email>,
//         latest:"<n>", acl:{ users:[email], teams:[id], org:bool }, ts } } }
//
// SEAMS (need backend/deploy support for true cross-user delivery):
//   1. sandpie/shared-hub must be a Dropbox TEAM-shared folder so every member
//      reads the same registry. Today it lives in the user's own synced tree, so
//      the engine is exercised locally / single-account; wiring the team-folder
//      namespace mount is a deploy step.
//   2. SSO team directory: acl.teams uses team ids from SandpieAccount.current()
//      (_user.teams). Until the server returns teams, team-scoped shares fall back
//      to user/org scoping. Everything else works.
//
// TESTING: window.SandpieSharing.setIdentity({user,teams}) simulates another user
// in the same browser — publish as A, switch to B, see the invite, accept, install.
(function () {
  'use strict';
  const HUB = 'sandpie/shared-hub';
  const HUB_INDEX = HUB + '/index.json';
  const INSTALL_ROOT = 'sandpie/shared';       // Phase-1 read-only managed area
  const SUBS_PATH = 'sandpie/config/shares.json';
  const ID_OVERRIDE_KEY = 'sandpie-share-identity';   // dev/test identity override
  const slug = (s) => String(s || '').toLowerCase().replace(/\.[^.]+$/, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48) || 'pkg';

  /* ── identity ─────────────────────────────────────────────────────────── */
  function me() {
    try { const o = JSON.parse(localStorage.getItem(ID_OVERRIDE_KEY) || 'null'); if (o && o.user) return { user: String(o.user), teams: Array.isArray(o.teams) ? o.teams : [] }; } catch (_) {}
    try { const u = window.SandpieAccount && SandpieAccount.current && SandpieAccount.current(); if (u && (u.email || u.name)) return { user: String(u.email || u.name), teams: Array.isArray(u.teams) ? u.teams : [] }; } catch (_) {}
    return { user: 'me@local', teams: [] };   // anonymous / no backend → local testing identity
  }
  function setIdentity(id) { if (id) localStorage.setItem(ID_OVERRIDE_KEY, JSON.stringify(id)); else localStorage.removeItem(ID_OVERRIDE_KEY); fire(); }

  /* ── OPFS helpers ─────────────────────────────────────────────────────── */
  const O = () => window.opfs;
  async function readJSON(path, dflt) { try { return JSON.parse(await O().read(path)); } catch (_) { return dflt; } }
  async function writeJSON(path, obj) { await O().write(path, new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' })); markDirty(path); }
  function markDirty(path) { try { if (window.Sandpie && Sandpie.events) Sandpie.events.emit('file:changed', path); } catch (_) {} }
  async function isDir(path) { try { await O().listDir(path); return true; } catch (_) { return false; } }
  async function copyTree(src, dst) {
    if (await isDir(src)) {
      for (const e of await O().listDir(src)) await copyTree(src + '/' + e.name, dst + '/' + e.name);
    } else {
      const bytes = await O().readBytes(src);
      await O().write(dst, new Blob([bytes]));
      markDirty(dst);
    }
  }

  /* ── registry + subscriptions ─────────────────────────────────────────── */
  async function catalog() { return (await readJSON(HUB_INDEX, { packages: {} })).packages || {}; }
  async function subs() { const s = await readJSON(SUBS_PATH, null); return s && typeof s === 'object' ? { accepted: s.accepted || {}, dismissed: s.dismissed || [] } : { accepted: {}, dismissed: [] }; }
  async function saveSubs(s) { await writeJSON(SUBS_PATH, s); }

  function entitled(entry, who) {
    const a = entry.acl || {};
    if (a.org) return true;
    if (Array.isArray(a.users) && a.users.map(String).includes(who.user)) return true;
    if (Array.isArray(a.teams) && a.teams.some(t => who.teams.includes(t))) return true;
    return false;
  }

  /* ── publish ──────────────────────────────────────────────────────────── */
  // srcPath: an OPFS path (skill folder, artifact file, or any folder).
  // audience: { org?:bool, users?:[email], teams?:[id] }
  async function publish(srcPath, audience, opts) {
    opts = opts || {};
    const src = String(srcPath || '').replace(/^\/+/, '').replace(/\/+$/, '');
    if (!src) throw new Error('publish: srcPath required');
    if (src.startsWith(INSTALL_ROOT + '/') || src.startsWith(HUB + '/')) throw new Error('publish: cannot re-share a managed/hub path — share your own file');
    const dir = await isDir(src);
    const base = src.split('/').pop();
    const kind = opts.kind || (dir ? (await isDir(src) && await fileExists(src + '/SKILL.md') ? 'skill' : 'folder') : 'artifact');
    const id = opts.id || slug(base);
    const cat = await catalog();
    const prev = cat[id];
    const ver = String((prev ? parseInt(prev.latest, 10) || 0 : 0) + 1);
    const verDir = `${HUB}/packages/${id}/v/${ver}`;
    if (dir) await copyTree(src, verDir);
    else await copyTree(src, `${verDir}/${base}`);   // artifact: keep its filename
    const idx = await readJSON(HUB_INDEX, { packages: {} }); idx.packages = idx.packages || {};
    idx.packages[id] = {
      id, kind, title: opts.title || base, publisher: me().user,
      latest: ver,
      acl: { org: !!audience.org, users: (audience.users || []).map(String), teams: (audience.teams || []).map(String) },
      entryFile: kind === 'artifact' ? base : (kind === 'skill' ? 'SKILL.md' : ''),
      ts: (window.Sandpie && Sandpie.now ? Sandpie.now() : 0) || 0,
    };
    await writeJSON(HUB_INDEX, idx);
    fire();
    return idx.packages[id];
  }
  async function fileExists(p) { try { await O().readBytes(p); return true; } catch (_) { return false; } }

  /* ── invites / accept / dismiss ───────────────────────────────────────── */
  async function pendingInvites() {
    const who = me(), cat = await catalog(), s = await subs(), out = [];
    for (const id in cat) {
      const e = cat[id];
      if (e.publisher === who.user) continue;            // don't invite yourself to your own share
      if (s.accepted[id] != null) continue;              // already subscribed
      if (s.dismissed.includes(id)) continue;            // explicitly dismissed
      if (!entitled(e, who)) continue;                   // not shared with me
      out.push(e);
    }
    return out;
  }
  async function acceptedList() {
    const cat = await catalog(), s = await subs(), out = [];
    for (const id in s.accepted) if (cat[id]) out.push({ ...cat[id], installedVer: String(s.accepted[id]) });
    return out;
  }
  async function accept(id) {
    const cat = await catalog(); const e = cat[id]; if (!e) return;
    await install(id, e.latest);
    const s = await subs(); s.accepted[id] = e.latest; s.dismissed = s.dismissed.filter(x => x !== id); await saveSubs(s);
    fire();
  }
  async function dismiss(id) { const s = await subs(); if (!s.dismissed.includes(id)) s.dismissed.push(id); await saveSubs(s); fire(); }

  async function install(id, ver) {
    const verDir = `${HUB}/packages/${id}/v/${ver}`;
    const dst = `${INSTALL_ROOT}/${id}`;
    await copyTree(verDir, dst);              // overwrite-in-place (Dropbox keeps history)
    // keep the Pyodide pool + file viewer coherent, same as write_file does
    try { window.dispatchEvent(new CustomEvent('sandpie-shares-installed', { detail: { id, ver, dst } })); } catch (_) {}
  }

  /* ── auto-update ──────────────────────────────────────────────────────── */
  // Advance every accepted subscription to the catalog's latest version. Silent
  // (internal shares are trusted). Runs at boot + on focus + after any change.
  let syncing = false;
  async function autoSync() {
    if (syncing || !O()) return; syncing = true;
    try {
      const cat = await catalog(), s = await subs(); let changed = false;
      for (const id in s.accepted) {
        const e = cat[id]; if (!e) continue;
        if (String(e.latest) !== String(s.accepted[id])) { await install(id, e.latest); s.accepted[id] = e.latest; changed = true; }
      }
      if (changed) { await saveSubs(s); fire(); }
    } catch (e) { console.warn('[sharing] autoSync failed:', e); }
    finally { syncing = false; }
  }

  /* ── events + boot ────────────────────────────────────────────────────── */
  function fire() { try { window.dispatchEvent(new CustomEvent('sandpie-shares-changed')); } catch (_) {} renderHome(); }
  function subscribe(cb) { const h = () => cb(); window.addEventListener('sandpie-shares-changed', h); return () => window.removeEventListener('sandpie-shares-changed', h); }

  const Sharing = { me, setIdentity, catalog, subs, entitled, publish, pendingInvites, acceptedList, accept, dismiss, autoSync, subscribe, shareDialog, HUB, INSTALL_ROOT };
  window.SandpieSharing = Sharing;

  /* ── share dialog (audience picker) ───────────────────────────────────── */
  function shareDialog(srcPath, presetKind) {
    const who = me();
    const back = document.createElement('div');
    back.className = 'share-modal-back';
    back.innerHTML =
      '<div class="share-modal" data-chrome>' +
        '<div class="share-modal-h">Share “' + esc(String(srcPath).split('/').pop()) + '”</div>' +
        '<label class="share-opt"><input type="radio" name="aud" value="org" checked> Everyone in the org</label>' +
        (who.teams.length ? '<label class="share-opt"><input type="radio" name="aud" value="teams"> Specific team(s): <input class="share-in" data-k="teams" placeholder="' + esc(who.teams.join(', ')) + '"></label>'
                          : '<label class="share-opt share-dim"><input type="radio" name="aud" value="teams" disabled> Teams (no team directory available)</label>') +
        '<label class="share-opt"><input type="radio" name="aud" value="users"> Specific people: <input class="share-in" data-k="users" placeholder="email, email…"></label>' +
        '<div class="share-modal-btns"><button class="ghost" data-act="cancel">Cancel</button><button class="ghost share-primary" data-act="share">Share</button></div>' +
        '<div class="share-modal-msg"></div>' +
      '</div>';
    document.body.appendChild(back);
    const close = () => back.remove();
    back.addEventListener('click', (e) => { if (e.target === back) close(); });
    back.querySelector('[data-act="cancel"]').onclick = close;
    back.querySelector('[data-act="share"]').onclick = async () => {
      const sel = back.querySelector('input[name="aud"]:checked').value;
      const audience = {};
      if (sel === 'org') audience.org = true;
      else if (sel === 'teams') audience.teams = splitList(back.querySelector('.share-in[data-k="teams"]').value) || who.teams;
      else audience.users = splitList(back.querySelector('.share-in[data-k="users"]').value);
      if ((sel === 'users' && !(audience.users || []).length) || (sel === 'teams' && !(audience.teams || []).length)) {
        back.querySelector('.share-modal-msg').textContent = 'Enter at least one ' + (sel === 'users' ? 'email' : 'team') + '.'; return;
      }
      const msg = back.querySelector('.share-modal-msg'); msg.textContent = 'Sharing…';
      try { const p = await publish(srcPath, audience, { kind: presetKind }); msg.textContent = 'Shared “' + p.title + '” (v' + p.latest + ').'; setTimeout(close, 900); }
      catch (e) { msg.textContent = 'Share failed: ' + ((e && e.message) || e); }
    };
  }
  function splitList(s) { return String(s || '').split(/[,\s]+/).map(x => x.trim()).filter(Boolean); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }

  /* ── home-screen "Shared with you" inbox + installed list ─────────────── */
  let homeBusy = false, homePending = false;
  async function renderHome() {
    const welcome = document.getElementById('welcome'); if (!welcome || !O()) return;
    if (homeBusy) { homePending = true; return; }   // coalesce: re-render once the in-flight pass finishes
    homeBusy = true;
    try {
      let box = document.getElementById('sharedHome');
      if (!box) { box = document.createElement('div'); box.id = 'sharedHome'; box.className = 'shared-home'; welcome.appendChild(box); }
      const invites = await pendingInvites();
      const installed = await acceptedList();
      box.textContent = '';
      if (!invites.length && !installed.length) { box.style.display = 'none'; return; }
      box.style.display = '';
      if (invites.length) {
        const h = document.createElement('div'); h.className = 'shared-home-title'; h.textContent = '📥 Shared with you'; box.appendChild(h);
        for (const e of invites) box.appendChild(inviteRow(e));
      }
      if (installed.length) {
        const h = document.createElement('div'); h.className = 'shared-home-title'; h.textContent = '🔗 Shared with me'; box.appendChild(h);
        for (const e of installed) box.appendChild(installedRow(e));
      }
    } finally { homeBusy = false; if (homePending) { homePending = false; renderHome(); } }
  }
  function kindIcon(k) { return k === 'skill' ? '🧩' : k === 'folder' ? '📁' : '📄'; }
  function inviteRow(e) {
    const row = document.createElement('div'); row.className = 'shared-file invite';
    row.innerHTML = '<span class="shared-file-name">' + kindIcon(e.kind) + ' ' + esc(e.title) + '</span><span class="shared-by">from ' + esc(e.publisher) + '</span>';
    const acc = document.createElement('button'); acc.className = 'ghost shared-accept'; acc.textContent = 'Accept'; acc.onclick = () => accept(e.id);
    const dis = document.createElement('button'); dis.className = 'shared-dismiss'; dis.title = 'Dismiss'; dis.textContent = '✕'; dis.onclick = () => dismiss(e.id);
    row.append(acc, dis); return row;
  }
  function installedRow(e) {
    const row = document.createElement('div'); row.className = 'shared-file';
    const open = document.createElement('button'); open.className = 'shared-file-open';
    open.innerHTML = kindIcon(e.kind) + ' ' + esc(e.title);
    open.title = e.kind === 'skill' ? 'Shared skill — the model can load it by name' : INSTALL_ROOT + '/' + e.id;
    open.onclick = () => {
      if (e.kind === 'artifact' && e.entryFile) { try { opfs.openFile(INSTALL_ROOT + '/' + e.id + '/' + e.entryFile, e.entryFile); } catch (_) {} }
      else { try { opfsGoto && opfsGoto(INSTALL_ROOT + '/' + e.id); } catch (_) {} }
    };
    row.append(open); return row;
  }
  function opfsGoto(dir) { if (window.opfs && opfs.openFolder) opfs.openFolder(dir); else if (window.opfsSetPath) window.opfsSetPath(dir); }

  /* ── boot ─────────────────────────────────────────────────────────────── */
  function boot() { renderHome(); autoSync(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
  window.addEventListener('focus', () => { autoSync(); });
  try { if (window.Sandpie && Sandpie.events) Sandpie.events.on && Sandpie.events.on('sync:done', () => autoSync()); } catch (_) {}
})();
