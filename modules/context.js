
const SandpieTokens = (() => {
  const WEEK_LOG_KEY = 'sandpie-token-weeklog';
  const USAGE_PREFIX = 'sandpie-usage-';
  const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
  const listeners = new Set();

  function usageTotal(u) {
    if (!u) return 0;
    return u.total_tokens || ((u.prompt_tokens || 0) + (u.completion_tokens || 0));
  }

  function loadLog() {
    try { const v = JSON.parse(localStorage.getItem(WEEK_LOG_KEY) || '[]'); return Array.isArray(v) ? v : []; }
    catch { return []; }
  }
  function prune(log) {
    const cutoff = Date.now() - WEEK_MS;
    return log.filter(e => e && typeof e.t === 'number' && e.t >= cutoff);
  }
  function weeklyTotal() {
    return prune(loadLog()).reduce((a, e) => a + (e.tokens || 0), 0);
  }

  function textOf(content) {
    if (typeof content === 'string') return content;
    if (Array.isArray(content)) return content.map(p => p && p.type === 'text' ? (p.text || '') : '').join(' ');
    return '';
  }
  function estimateTokens(msgs) {
    let chars = 0;
    for (const m of (msgs || [])) {
      chars += textOf(m.content).length;
      if (m.tool_calls) for (const tc of m.tool_calls) chars += (tc.function?.arguments || '').length + (tc.function?.name || '').length;
    }
    return Math.ceil(chars / 4);
  }

  async function conversationTokens() {
    const convId = localStorage.getItem('sandpie-active-conv');
    if (!convId) return 0;
    try {
      const stored = localStorage.getItem(USAGE_PREFIX + convId);
      if (stored) return usageTotal(JSON.parse(stored));
    } catch {}
    try {
      const text = await window.opfs.read('_conversations/' + convId + '.json');
      const data = JSON.parse(text);
      if (data.usage) return usageTotal(data.usage);
      if (data.messages) return estimateTokens(data.messages);
    } catch {}
    return 0;
  }

  function isEstimated() {
    const convId = localStorage.getItem('sandpie-active-conv');
    return !convId || !localStorage.getItem(USAGE_PREFIX + convId);
  }

  function contextWindow() {
    const ap = (typeof SandpieProviders !== 'undefined') ? SandpieProviders.getActive() : null;
    return (ap && ap.contextWindow > 0) ? ap.contextWindow : null;
  }

  function recordUsage(convId, usage) {
    if (!usage) return;
    localStorage.setItem(USAGE_PREFIX + convId, JSON.stringify(usage));
    const log = prune(loadLog());
    log.push({ t: Date.now(), tokens: usageTotal(usage) });
    localStorage.setItem(WEEK_LOG_KEY, JSON.stringify(log));
    notify();
  }

  function subscribe(cb) { listeners.add(cb); return () => listeners.delete(cb); }
  function notify() { for (const cb of listeners) { try { cb(); } catch (e) { console.warn(e); } } }

  return {
    recordUsage, conversationTokens, isEstimated, weeklyTotal,
    contextWindow, subscribe, notify,
  };
})();
window.SandpieTokens = SandpieTokens;

/**
 * Context Module for Sandpie
 *
 * Registers a "Context" section in the sidebar via SandpieMenu and renders the
 * conversation's token usage (with a context-window percentage when the model's
 * window is known) plus a rolling 7-day token total. The numbers come from
 * SandpieTokens, which the page populates from real provider usage.
 *
 * Usage: <script type="module" src="modules/context.js"></script>
 */

let _unsubscribe = null;

function fmtTokens(n) {
  n = Math.max(0, Math.round(n || 0));
  if (n < 1000) return String(n);
  if (n < 1000000) return (n / 1000).toFixed(n < 10000 ? 1 : 0) + 'k';
  return (n / 1000000).toFixed(1) + 'M';
}

async function render() {
  const T = SandpieTokens;
  if (typeof T === 'undefined') return;

  const convEl = document.getElementById('ctxConvTokens');
  const barEl = document.getElementById('ctxConvBar');
  const pctEl = document.getElementById('ctxConvPct');
  const weekEl = document.getElementById('ctxWeekTokens');
  if (!convEl) return;

  const convTokens = await T.conversationTokens();
  const window_ = T.contextWindow();
  const estimated = T.isEstimated();

  convEl.textContent = fmtTokens(convTokens) + (estimated ? ' ~' : '');
  convEl.title = estimated
    ? 'Estimated (provider did not report usage)'
    : 'Reported by the provider';

  let badge = fmtTokens(convTokens);
  if (window_) {
    const pct = Math.min(100, (convTokens / window_) * 100);
    barEl.style.width = pct.toFixed(1) + '%';
    barEl.style.background = pct > 90 ? 'var(--sp-accent-neg, #e06c75)' : 'var(--sp-accent)';
    barEl.parentElement.style.visibility = 'visible';
    pctEl.textContent = `${pct.toFixed(pct < 10 ? 1 : 0)}% used · ${fmtTokens(window_ - convTokens)} left of ${fmtTokens(window_)}`;
    badge = `${pct.toFixed(0)}%`;
  } else {
    barEl.parentElement.style.visibility = 'hidden';
    pctEl.textContent = 'Context window unknown for this model';
  }

  if (weekEl) weekEl.textContent = fmtTokens(T.weeklyTotal());

  if (typeof SandpieMenu !== 'undefined') SandpieMenu.updateBadge('contextSection', badge);
}

function init() {
  if (typeof SandpieMenu === 'undefined') {
    console.warn('Context module: SandpieMenu not found, retrying in 500ms...');
    setTimeout(init, 500);
    return;
  }

  if (typeof Sandpie !== 'undefined' && Sandpie.events) {
    Sandpie.events.on('tokens:record', ({convId, usage}) => {
      recordUsage(convId, usage);
    });
  }

  SandpieMenu.add('contextSection', {
    title: 'Context',
    badge: '—',
    open: false,
    html: `
      <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:0.25rem;">
        <span style="color:var(--sp-text-dim);">Conversation</span>
        <span id="ctxConvTokens" style="font-variant-numeric:tabular-nums;">–</span>
      </div>
      <div style="height:6px; border-radius:3px; background:var(--sp-border); overflow:hidden; visibility:hidden;">
        <div id="ctxConvBar" style="height:100%; width:0%; background:var(--sp-accent); transition:width 0.3s;"></div>
      </div>
      <p id="ctxConvPct" style="font-size:0.7rem; color:var(--sp-text-dim); margin:0.3rem 0 0;"></p>
      <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-top:0.7rem;">
        <span style="color:var(--sp-text-dim);">This week (7d)</span>
        <span id="ctxWeekTokens" style="font-variant-numeric:tabular-nums;">–</span>
      </div>
    `,
    onRender(bodyEl) {
      if (!_unsubscribe) _unsubscribe = SandpieTokens.subscribe(render);
      render();
    }
  });

  console.log('Context module registered');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
