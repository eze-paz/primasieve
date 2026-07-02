const fs = require('fs');
let js = fs.readFileSync('modules/conversations.js', 'utf8');

const oldCancel =   modal.querySelectorAll('.qm-cancel').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const idx = +e.target.dataset.idx;
      stream.queue.splice(idx, 1);
      updateQueueCount(stream);
      openQueueModal(stream);
    });
  });;

const newCancel =   modal.querySelectorAll('.qm-cancel').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const idx = +e.currentTarget.dataset.idx;
      stream.queue.splice(idx, 1);
      updateQueueCount(stream);
      const item = e.currentTarget.closest('.qm-item');
      if (item) item.remove();
      // Re-index remaining items
      modal.querySelectorAll('.qm-item').forEach((el, newIdx) => {
        el.dataset.idx = String(newIdx);
        const num = el.querySelector('.qm-number');
        if (num) num.textContent = String(newIdx + 1);
        el.querySelectorAll('.qm-edit, .qm-cancel').forEach(b => b.dataset.idx = String(newIdx));
      });
      if (stream.queue.length === 0) closeQueueModal();
    });
  });;

if (!js.includes(oldCancel)) {
  console.log('OLD block not found');
  process.exit(1);
}

js = js.replace(oldCancel, newCancel);
fs.writeFileSync('modules/conversations.js', js, 'utf8');
console.log('Fixed');
