/**
 * Context Module for Sandpie
 *
 * Registers a "Context" section in the sidebar via SandpieMenu and renders the
 * conversation's token usage (with a context-window percentage when the model's
 * window is known) plus a rolling 7-day token total. The numbers come from
 * window.SandpieTokens, which the page populates from real provider usage.
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

function render() {
  const T = window.SandpieTokens;
  if (typeof T === 'undefined') return;

  const convEl = document.getElementById('ctxConvTokens');
  const barEl = document.getElementById('ctxConvBar');
  const pctEl = document.getElementById('ctxConvPct');
  const weekEl = document.getElementById('ctxWeekTokens');
  if (!convEl) return;

  const convTokens = T.conversationTokens();
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
      if (typeof window.SandpieTokens !== 'undefined') {
        window.SandpieTokens.ensureModels();
        if (!_unsubscribe) _unsubscribe = window.SandpieTokens.subscribe(render);
      }
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
