/**
 * Artifacts Module for Sandpie
 *
 * Registers an "Artifacts" section in the sidebar via SandpieMenu.
 * Usage: <script type="module" src="modules/artifacts.js"></script>
 */

function init() {
  if (typeof SandpieMenu === 'undefined') {
    console.warn('Artifacts module: SandpieMenu not found, retrying in 500ms...');
    setTimeout(init, 500);
    return;
  }

  SandpieMenu.add('artifactsSection', {
    title: 'Artifacts',
    badge: '0',
    open: false,
    html: '<p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0;">WIP</p>',
    onRender(bodyEl) {
      console.log('Artifacts section rendered');
    }
  });

  console.log('Artifacts module registered');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

window.SandpieArtifacts = {
  setCount(n) {
    SandpieMenu.updateBadge('artifactsSection', String(n));
  },
  increment() {
    const el = SandpieMenu.get('artifactsSection');
    if (!el) return;
    const badge = el.querySelector('summary span');
    const current = parseInt(badge?.textContent || '0', 10);
    SandpieMenu.updateBadge('artifactsSection', String(current + 1));
  }
};
