/**
 * Context Module for Sandpie
 *
 * Registers a "Context" section in the sidebar via SandpieMenu.
 * Usage: <script type="module" src="modules/context.js"></script>
 */

function init() {
  if (typeof SandpieMenu === 'undefined') {
    console.warn('Context module: SandpieMenu not found, retrying in 500ms...');
    setTimeout(init, 500);
    return;
  }

  SandpieMenu.add('contextSection', {
    title: 'Context',
    badge: null,
    open: false,
    html: '<p style="font-size:0.75rem; color:var(--sp-text-dim); margin:0;">WIP</p>',
    onRender(bodyEl) {
      console.log('Context section rendered');
    }
  });

  console.log('Context module registered');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
