const fs = require('fs');
const file = 'modules/conversations.js';
let s = fs.readFileSync(file, 'utf8');

s = s.replace('<div class=\"modal-backdrop\" onclick=\"closeQueueModal()\"></div>', '<div class=\"modal-backdrop\"></div>');
console.log('1. backdrop');

s = s.replace(
  '<button class=\"ghost\" onclick=\"closeQueueModal()\" title=\"Close\" style=\"font-size:1rem; line-height:1; padding:0.15rem 0.5rem;\">&#215;</button>',
  '<button class=\"ghost qm-close\" title=\"Close\" style=\"font-size:1rem; line-height:1; padding:0.15rem 0.5rem;\">&#215;</button>'
);
console.log('2. close button');

s = s.replace(
  'onclick=\"clearQueue(\\\\\' + stream.id + \\\\\')\"',
  'class=\"ghost qm-clear\"'
);
console.log('3. clear button');

var inject = '  document.body.appendChild(modal);\n\n' +
  '  // Wire up click handlers (module-scoped; inline onclick can\'t reach them)\n' +
  '  modal.querySelector(\'.modal-backdrop\').addEventListener(\'click\', closeQueueModal);\n' +
  '  modal.querySelector(\'.qm-close\').addEventListener(\'click\', closeQueueModal);\n' +
  '  modal.querySelector(\'.qm-clear\').addEventListener(\'click\', () => clearQueue(stream.id));\n\n' +
  '  const escHandler';

s = s.replace('  document.body.appendChild(modal);\n\n  const escHandler', inject);
console.log('4. event listeners');

fs.writeFileSync(file, s, 'utf8');
console.log('Done');
