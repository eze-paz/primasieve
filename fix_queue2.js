const fs = require('fs');

// Fix conversations.js
let js = fs.readFileSync('modules/conversations.js', 'utf8');

// 1. Use closeQueueModal() instead of existing.remove() to clean up keydown listener
js = js.replace(
  'const existing = document.getElementById(\'queueModal\');\n  if (existing) existing.remove();',
  'const existing = document.getElementById(\'queueModal\');\n  if (existing) closeQueueModal();'
);
console.log('1. existing.remove -> closeQueueModal');

// 2. Add type=\"button\" to all modal buttons
js = js.replace('<button class=\"ghost qm-close\"', '<button type=\"button\" class=\"ghost qm-close\"');
js = js.replace('<button class=\"ghost qm-cancel\"', '<button type=\"button\" class=\"ghost qm-cancel\"');
js = js.replace('<button class=\"ghost qm-edit\"', '<button type=\"button\" class=\"ghost qm-edit\"');
js = js.replace('<button class=\"ghost qm-clear\"', '<button type=\"button\" class=\"ghost qm-clear\"');
js = js.replace('<button class=\"ghost qm-save\"', '<button type=\"button\" class=\"ghost qm-save\"');
js = js.replace('<button class=\"ghost qm-cancel-edit\"', '<button type=\"button\" class=\"ghost qm-cancel-edit\"');
console.log('2. type=button added');

fs.writeFileSync('modules/conversations.js', js, 'utf8');

// Fix sandpie.css
let css = fs.readFileSync('sandpie.css', 'utf8');

// Add #queueModal button.ghost rules after #settingsModal button.ghost block
const ghostBlock = '/* Settings modal also lives on <body> (so position:fixed anchors to the\\n     viewport, not the aurora sidebar\\'s backdrop-filter) — same reason .subs-modal\\n     does: \"aside button.ghost\" can\\'t reach a body-level modal, so restyle here. */\\n  #settingsModal button.ghost { background: var(--sp-panel); color: var(--sp-text-dim); border: 1px solid var(--sp-border); border-radius: 6px; padding: 0.35rem 0.6rem; font: inherit; font-size: 0.8rem; cursor: pointer; }\\n  #settingsModal button.ghost:hover:not(:disabled) { background: var(--sp-surface); color: var(--sp-text); border-color: var(--sp-border-bright); }\\n  #settingsModal button.ghost.active { background: var(--sp-accent-dim); color: var(--sp-text); border-color: var(--sp-accent); }';

if (!css.includes('#queueModal button.ghost')) {
  const queueGhost = '  #queueModal button.ghost { background: var(--sp-panel); color: var(--sp-text-dim); border: 1px solid var(--sp-border); border-radius: 6px; padding: 0.35rem 0.6rem; font: inherit; font-size: 0.8rem; cursor: pointer; }\n  #queueModal button.ghost:hover:not(:disabled) { background: var(--sp-surface); color: var(--sp-text); border-color: var(--sp-border-bright); }\n';
  css = css.replace(ghostBlock, ghostBlock + '\n' + queueGhost);
  console.log('3. #queueModal button.ghost styles added');
} else {
  console.log('3. #queueModal button.ghost already exists');
}

fs.writeFileSync('sandpie.css', css, 'utf8');

// Bump sandpie.html CSS/JS versions if needed
let html = fs.readFileSync('sandpie.html', 'utf8');
if (html.includes('sandpie.css?v=38')) {
  html = html.replace('sandpie.css?v=38', 'sandpie.css?v=39');
  html = html.replace('conversations.js?v=63', 'conversations.js?v=64');
  fs.writeFileSync('sandpie.html', html, 'utf8');
  console.log('4. Versions bumped to v39/v64');
} else {
  console.log('4. Versions already bumped or different');
}

console.log('Done');
