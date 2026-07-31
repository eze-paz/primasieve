// Mobile UI and touch interactions for sandpie
function toggleSidebar() {
  const open = document.body.classList.toggle('sidebar-open');
  const btn = document.querySelector('.hamburger');
  if (btn) btn.textContent = open ? '✕' : '☰';
}
function toggleSidebarCollapse() {
  const aside = document.querySelector('aside');
  const isCollapsed = aside.classList.toggle('collapsed');
  document.body.classList.toggle('sidebar-collapsed', isCollapsed);
  localStorage.setItem('sandpie-sidebar-collapsed', isCollapsed ? '1' : '');
}
document.addEventListener('submit', () => {
  document.body.classList.remove('sidebar-open');
  const btn = document.querySelector('.hamburger');
  if (btn) btn.textContent = '☰';
});

// On mobile, tapping "+ New chat" should also dismiss the sidebar so the user
// lands straight on the fresh conversation. Desktop keeps the sidebar open.
document.addEventListener('click', (e) => {
  if (!e.target.closest || !e.target.closest('#newChatBtn')) return;
  if (!isMobileViewport()) return;
  document.body.classList.remove('sidebar-open');
  const btn = document.querySelector('.hamburger');
  if (btn) btn.textContent = '☰';
});

function isMobileViewport() {
  return window.matchMedia && window.matchMedia('(max-width: 768px)').matches;
}

let wakeLock = null;
async function requestWakeLock() {
  try {
    if ('wakeLock' in navigator) {
      wakeLock = await navigator.wakeLock.request('screen');
      wakeLock.addEventListener('release', () => { wakeLock = null; });
    }
  } catch (e) {  }
}
function releaseWakeLock() {
  if (wakeLock) {
    try { wakeLock.release(); } catch (e) {}
    wakeLock = null;
  }
}
document.addEventListener('visibilitychange', () => {
  if (document.hidden) return;
  for (const s of convStreams.values()) {
    if (s.generating) { requestWakeLock(); break; }
  }
});

const LP_DELAY = 500;
const LP_SLOP = 30;
function attachLongPress(el, handler) {
  el.addEventListener('touchstart', (e) => {
    const t = e.touches[0];
    el._lp = {
      timer: setTimeout(() => {
        el._lp.timer = null;
        el.classList.remove('lp-active');
        handler({
          currentTarget: el, target: el,
          clientX: el._lp.x, clientY: el._lp.y,
          preventDefault() {}, stopPropagation() {}
        });

        const swallow = (ce) => { ce.stopPropagation(); ce.preventDefault(); };
        document.addEventListener('click', swallow, { capture: true, once: true });
        setTimeout(() => document.removeEventListener('click', swallow, { capture: true }), 350);
      }, LP_DELAY),
      x: t.clientX,
      y: t.clientY,
    };
    el.classList.add('lp-active');
  }, { passive: true });
  el.addEventListener('touchmove', (e) => {
    if (!el._lp || !el._lp.timer) return;
    const t = e.touches[0];
    if (Math.abs(t.clientX - el._lp.x) > LP_SLOP || Math.abs(t.clientY - el._lp.y) > LP_SLOP) {
      clearTimeout(el._lp.timer);
      el._lp = null;
      el.classList.remove('lp-active');
    }
  }, { passive: true });
  el.addEventListener('touchend', () => {
    if (el._lp) {
      if (el._lp.timer) clearTimeout(el._lp.timer);
      el._lp = null;
    }
    el.classList.remove('lp-active');
  });
  el.addEventListener('touchcancel', () => {
    if (el._lp) {
      if (el._lp.timer) clearTimeout(el._lp.timer);
      el._lp = null;
    }
    el.classList.remove('lp-active');
  });
}

window.toggleSidebar = toggleSidebar;
window.toggleSidebarCollapse = toggleSidebarCollapse;
window.isMobileViewport = isMobileViewport;
window.requestWakeLock = requestWakeLock;
window.releaseWakeLock = releaseWakeLock;
window.attachLongPress = attachLongPress;
window.LP_DELAY = LP_DELAY;
window.LP_SLOP = LP_SLOP;

export {
  toggleSidebar, toggleSidebarCollapse, isMobileViewport,
  requestWakeLock, releaseWakeLock, attachLongPress,
  LP_DELAY, LP_SLOP
};
