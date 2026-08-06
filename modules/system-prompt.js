/**
 * System Prompt module for Sandpie
 *
 * The chat system prompt is an editable value cached in localStorage — NOT a
 * synced or browsable OPFS file. This replaces the old OPFS `sandpie_memory.md`
 * (which showed in the file browser and synced to Dropbox).
 *
 * - SandpieSystemPrompt.get() is read by conversations.js buildSystemPrompt().
 * - Registers a "System prompt" section in the Settings modal (gear), with a
 *   sidebar (SandpieMenu) fallback.
 * - One-time migration: pull any existing sandpie_memory.md into the local
 *   prompt, then delete that file locally AND from Dropbox.
 */
const SandpieSystemPrompt = (function () {
  'use strict';

  const KEY = 'sandpie-system-prompt';
  const MIGRATED_KEY = 'sandpie-sysprompt-migrated';
  const DEFAULT = 'You are a helpful assistant that reasons through the users requests step-by-step.';

  function get() { const v = localStorage.getItem(KEY); return (v == null || v === '') ? DEFAULT : v; }
  function set(v) { if (v == null || String(v).trim() === '') localStorage.removeItem(KEY); else localStorage.setItem(KEY, String(v)); }
  function isCustom() { const v = localStorage.getItem(KEY); return v != null && v !== '' && v !== DEFAULT; }

  // One-time migration off the old OPFS sandpie_memory.md. Seed the local prompt
  // from it (hydrating first if it's a dehydrated placeholder), then remove the
  // file locally AND from Dropbox (file:deleted → the sync provider's delete).
  // Best-effort: retries next load if OPFS isn't ready yet.
  async function migrate() {
    if (localStorage.getItem(MIGRATED_KEY) === '1') return;
    if (typeof opfs === 'undefined') return;
    try {
      if (localStorage.getItem(KEY) == null) {
        let old = null;
        try { old = await opfs.read('sandpie_memory.md'); } catch (_) {}
        if (old == null) {   // maybe a dehydrated placeholder — hydrate then read
          try {
            const sp = window.Sandpie && Sandpie.syncProvider && Sandpie.syncProvider();
            if (sp && sp.hydrate) { await sp.hydrate('sandpie_memory.md'); old = await opfs.read('sandpie_memory.md'); }
          } catch (_) {}
        }
        if (old != null && old.trim() && old.trim() !== DEFAULT) localStorage.setItem(KEY, old);
      }
      let existed = false;
      try { existed = await opfs.exists('sandpie_memory.md'); } catch (_) {}
      try { await opfs.remove('sandpie_memory.md'); } catch (_) {}
      // Remove the Dropbox copy too — standard delete path; no-op if not connected.
      if (existed && window.Sandpie && Sandpie.events) Sandpie.events.emit('file:deleted', 'sandpie_memory.md');
      localStorage.setItem(MIGRATED_KEY, '1');
    } catch (_) { /* leave MIGRATED_KEY unset → retry next load */ }
  }

  const HTML = `
        <p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0 0 0.5rem;">Sets the assistant's behavior for every conversation. Stored locally in this browser only — not synced and not saved as a file.</p>
        <p id="sysPromptLangNote" style="font-size:0.75rem; color:var(--sp-text-dim); margin:0 0 0.5rem;"></p>
        <textarea id="sysPromptText" rows="8" spellcheck="false" placeholder="You are a helpful assistant…" style="width:100%; resize:vertical; padding:0.5rem; background:var(--sp-panel); border:1px solid var(--sp-border); border-radius:6px; color:var(--sp-text); font:0.82rem 'JetBrains Mono', Consolas, monospace; line-height:1.45;"></textarea>
        <div style="display:flex; align-items:center; gap:0.6rem; margin-top:0.4rem;">
          <span id="sysPromptStatus" style="font-size:0.7rem; color:var(--sp-text-dim); flex:1; min-width:0;"></span>
          <button type="button" class="ghost" id="sysPromptReset" style="font-size:0.72rem; padding:0.2rem 0.55rem;">Reset to default</button>
        </div>

        <div class="sp-block">
          <div class="sp-block-head">Tools <span class="sp-count" id="spToolsCount"></span></div>
          <p class="sp-block-hint">Function tools offered to the model. Untick to stop sending one; expand to view or edit its description (the text the model reads). Applies to every conversation.</p>
          <div id="spToolsList"></div>
        </div>

        <div class="sp-block">
          <div class="sp-block-head">Skills <span class="sp-count" id="spSkillsCount"></span></div>
          <p class="sp-block-hint">Playbooks auto-discovered from <code>sandpie/skills/</code>. Untick to hide one from the model; expand to edit its SKILL.md.</p>
          <div id="spSkillsErrors"></div>
          <div id="spSkillsList"></div>
          <button type="button" class="ghost" id="spSkillCreate" style="font-size:0.72rem; padding:0.2rem 0.55rem; margin-top:0.4rem;">Create example skill</button>
        </div>
      `;

  let _flashT = null;
  function flashMsg(msg) {
    const el = document.getElementById('sysPromptStatus');
    if (!el) return;
    el.textContent = msg; clearTimeout(_flashT); _flashT = setTimeout(() => { if (el) el.textContent = ''; }, 1500);
  }
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // A collapsible row: [checkbox] name  …preview…  meta  ▸ ; clicking anywhere
  // but the checkbox toggles the body open/closed.
  function makeRow(checkbox, nameText, metaText, descPreview) {
    const row = document.createElement('div'); row.className = 'sp-item';
    const head = document.createElement('div'); head.className = 'sp-item-head';
    head.appendChild(checkbox);
    const name = document.createElement('span'); name.className = 'sp-item-name'; name.textContent = nameText;
    if (!checkbox.checked) name.style.opacity = '0.5';
    head.appendChild(name);
    const desc = document.createElement('span'); desc.className = 'sp-item-desc'; desc.textContent = descPreview || '';
    head.appendChild(desc);
    const meta = document.createElement('span'); meta.className = 'sp-item-meta'; meta.textContent = metaText || '';
    head.appendChild(meta);
    const caret = document.createElement('span'); caret.className = 'sp-caret'; caret.textContent = '▸';
    head.appendChild(caret);
    const body = document.createElement('div'); body.className = 'sp-item-body'; body.style.display = 'none';
    row.append(head, body);
    head.addEventListener('click', (e) => {
      if (e.target === checkbox) return;
      const open = body.style.display === 'none';
      body.style.display = open ? '' : 'none'; caret.textContent = open ? '▾' : '▸';
      if (open && body._onOpen) { const f = body._onOpen; body._onOpen = null; f(); }
    });
    return { row, head, body };
  }

  function renderTools(panel) {
    const listEl = panel.querySelector('#spToolsList');
    const countEl = panel.querySelector('#spToolsCount');
    if (!listEl || typeof SandpieTools === 'undefined') return;
    const items = SandpieTools.list();
    if (countEl) countEl.textContent = items.filter(t => t.enabled).length + ' / ' + items.length + ' active';
    listEl.innerHTML = '';
    for (const t of items) {
      const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = t.enabled;
      cb.addEventListener('change', () => { SandpieTools.setEnabled(t.name, cb.checked); flashMsg('Saved'); renderTools(panel); });
      const meta = [t.custom ? 'edited' : '', t.available ? '' : 'needs Dropbox'].filter(Boolean).join(' · ');
      const { row, body } = makeRow(cb, t.name, meta, null);
      const ta = document.createElement('textarea'); ta.className = 'sp-edit'; ta.rows = 7; ta.spellcheck = false; ta.value = t.description;
      const btns = document.createElement('div'); btns.className = 'sp-item-btns';
      const save = document.createElement('button'); save.type = 'button'; save.className = 'ghost'; save.textContent = 'Save';
      save.addEventListener('click', () => { SandpieTools.setDescription(t.name, ta.value); flashMsg('Saved'); renderTools(panel); });
      const reset = document.createElement('button'); reset.type = 'button'; reset.className = 'ghost'; reset.textContent = 'Reset to default'; reset.disabled = !t.custom;
      reset.addEventListener('click', () => { SandpieTools.resetDescription(t.name); flashMsg('Reset to default'); renderTools(panel); });
      btns.append(save, reset);
      body.append(ta, btns);
      listEl.appendChild(row);
    }
  }

  async function renderSkills(panel) {
    const listEl = panel.querySelector('#spSkillsList');
    const errEl = panel.querySelector('#spSkillsErrors');
    const countEl = panel.querySelector('#spSkillsCount');
    if (!listEl || typeof SandpieContext === 'undefined' || !SandpieContext.inspect) return;
    let idx;
    try { idx = await SandpieContext.inspect([]); } catch (_) { return; }
    if (!idx || !idx.exists) {
      if (countEl) countEl.textContent = 'none';
      if (errEl) errEl.innerHTML = '';
      listEl.innerHTML = `<p style="font-size:0.72rem; color:var(--sp-text-dim); margin:0;">No <code>${esc(SandpieContext.SKILLS_DIR)}/</code> folder yet.</p>`;
      return;
    }
    if (countEl) countEl.textContent = idx.skills.filter(s => s.enabled).length + ' / ' + idx.skills.length + ' active';
    if (errEl) errEl.innerHTML = (idx.errors || []).map(e => `<div class="sp-skill-err">⚠ ${esc(e)}</div>`).join('');
    listEl.innerHTML = '';
    for (const s of idx.skills) {
      const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = s.enabled;
      cb.addEventListener('change', () => { SandpieContext.setSkillEnabled(s.name, cb.checked); flashMsg('Saved'); renderSkills(panel); });
      const preview = s.desc.length > 56 ? s.desc.slice(0, 56) + '…' : s.desc;
      const { row, body } = makeRow(cb, s.name, '', preview);
      const ta = document.createElement('textarea'); ta.className = 'sp-edit'; ta.rows = 12; ta.spellcheck = false; ta.value = 'Loading…'; ta.disabled = true;
      const btns = document.createElement('div'); btns.className = 'sp-item-btns';
      const save = document.createElement('button'); save.type = 'button'; save.className = 'ghost'; save.textContent = 'Save'; save.disabled = true;
      const st = document.createElement('span'); st.className = 'sp-item-status';
      save.addEventListener('click', async () => {
        try { await SandpieContext.saveSkill(s.file, ta.value); st.textContent = 'Saved'; flashMsg('Saved'); renderSkills(panel); }
        catch (_) { st.textContent = 'Save failed'; }
      });
      btns.append(save, st);
      body.append(ta, btns);
      body._onOpen = async () => {
        try { ta.value = await opfs.read(s.file); } catch (_) { ta.value = ''; }
        ta.disabled = false; save.disabled = false;
      };
      listEl.appendChild(row);
    }
  }

  function wire(panel) {
    const ta = panel.querySelector('#sysPromptText');
    const resetBtn = panel.querySelector('#sysPromptReset');
    const langNote = panel.querySelector('#sysPromptLangNote');
    if (langNote) {
      try {
        if (typeof SandpieLanguage !== 'undefined' && SandpieLanguage.nativeName && SandpieLanguage.effective) {
          langNote.textContent = 'Reply language: ' + SandpieLanguage.nativeName(SandpieLanguage.effective()) + ' — set in Settings → Account.';
        }
      } catch (_) {}
    }
    if (ta) {
      ta.value = get();
      ta.addEventListener('input', () => { set(ta.value); flashMsg('Saved'); });
    }
    if (resetBtn) resetBtn.addEventListener('click', () => { set(''); if (ta) ta.value = get(); flashMsg('Reset to default'); });
    renderTools(panel);
    renderSkills(panel);
    const createBtn = panel.querySelector('#spSkillCreate');
    if (createBtn) createBtn.addEventListener('click', async () => {
      try { if (typeof SandpieContext !== 'undefined' && SandpieContext.scaffold) { await SandpieContext.scaffold(); flashMsg('Created example skill'); renderSkills(panel); } }
      catch (_) { flashMsg('Could not create'); }
    });
  }

  let _retry = 0;
  function init() {
    migrate();
    if (window.SandpieSettings) {
      SandpieSettings.register({ id: 'system-prompt', title: 'System prompt', order: 15, render(panel) { panel.innerHTML = HTML; wire(panel); }, onShow(panel) { renderSkills(panel); } });
      return;
    }
    if (typeof SandpieMenu !== 'undefined') {
      SandpieMenu.add('systemPromptSection', { title: 'System prompt', badge: null, open: false, html: HTML, onRender: wire });
      return;
    }
    if (_retry++ < 40) setTimeout(init, 500);   // neither host ready yet — retry
  }

  return { get, set, isCustom, init };
})();

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', SandpieSystemPrompt.init);
else SandpieSystemPrompt.init();
window.SandpieSystemPrompt = SandpieSystemPrompt;
