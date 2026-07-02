const fs = require('fs');
const file = 'modules/conversations.js';
let lines = fs.readFileSync(file, 'utf8').split('\n');
let out = [];
for (let i = 0; i < lines.length; i++) {
  let line = lines[i];
  // 1. Fix backdrop
  if (line.includes('modal-backdrop') && line.includes('onclick')) {
    line = line.replace(' onclick=\"closeQueueModal()\"', '');
    out.push(line);
    console.log('Replaced backdrop at line', i+1);
    continue;
  }
  // 2. Fix close button
  if (line.includes('onclick=\"closeQueueModal()\"') && line.includes('&#215;')) {
    line = line.replace('<button class=\"ghost\" onclick=\"closeQueueModal()\" ', '<button class=\"ghost qm-close\" ');
    out.push(line);
    console.log('Replaced close button at line', i+1);
    continue;
  }
  // 3. Fix clear button
  if (line.includes('clearQueue') && line.includes('stream.id')) {
    line = line.replace(/ onclick=\"clearQueue\(.+?stream\.id.+?\)\"/, ' class=\"ghost qm-clear\"');
    out.push(line);
    console.log('Replaced clear button at line', i+1);
    continue;
  }
  // 4. Inject event listeners after appendChild(modal)
  if (line.trim() === 'document.body.appendChild(modal);') {
    out.push(line);
    out.push('');
    out.push('  // Wire up click handlers (module-scoped; inline onclick can\'t reach them)');
    out.push('  modal.querySelector(\'.modal-backdrop\').addEventListener(\'click\', closeQueueModal);');
    out.push('  modal.querySelector(\'.qm-close\').addEventListener(\'click\', closeQueueModal);');
    out.push('  modal.querySelector(\'.qm-clear\').addEventListener(\'click\', () => clearQueue(stream.id));');
    console.log('Injected listeners at line', i+1);
    continue;
  }
  out.push(line);
}
fs.writeFileSync(file, out.join('\n'), 'utf8');
console.log('Done');
