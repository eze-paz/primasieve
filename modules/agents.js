/**
 * Agents Module for Sandpie
 *
 * Registers an "Agents" section in the sidebar via SandpieMenu.
 * Usage: <script type="module" src="modules/agents.js"></script>
 */

function init() {
  if (typeof SandpieMenu === 'undefined') {
    console.warn('Agents module: SandpieMenu not found, retrying in 500ms...');
    setTimeout(init, 500);
    return;
  }

  SandpieMenu.add('agentsSection', {
    title: 'Agents',
    badge: '0',
    open: false,
    html: '<p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0;">WIP</p>',
    onRender(bodyEl) {
      console.log('Agents section rendered');
    }
  });

  console.log('Agents module registered');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

window.SandpieAgents = {
  setCount(n) {
    SandpieMenu.updateBadge('agentsSection', String(n));
  },
  increment() {
    const el = SandpieMenu.get('agentsSection');
    if (!el) return;
    const badge = el.querySelector('summary span');
    const current = parseInt(badge?.textContent || '0', 10);
    SandpieMenu.updateBadge('agentsSection', String(current + 1));
  }
};
