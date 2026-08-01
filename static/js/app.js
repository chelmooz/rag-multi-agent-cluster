/* ═══════════════════════════════════════════════════════════
   CTOS — Bootstrap SPA
   ═══════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', async () => {
  // Thème : dark par défaut, toggle semi-lit (docs sombres)
  const root = document.documentElement;
  const saved = localStorage.getItem('ctos-theme');
  if (saved === 'semi-lit' || (window.DASHBOARD_SEMI_LIGHT && saved !== 'dark')) {
    root.setAttribute('data-theme', 'semi-lit');
  }

  const themeBtn = document.getElementById('theme-toggle');
  themeBtn.addEventListener('click', () => {
    const next = root.getAttribute('data-theme') === 'semi-lit' ? 'dark' : 'semi-lit';
    root.setAttribute('data-theme', next);
    localStorage.setItem('ctos-theme', next);
  });

  // Horloge topbar
  const clockEl = document.getElementById('top-clock');
  function tick() {
    clockEl.textContent = new Date().toLocaleTimeString('fr-FR', { hour12: false });
  }
  tick();
  setInterval(tick, 1000);

  // Initialiser chat + monitoring
  await Chat.init();
  Monitoring.init();
});
