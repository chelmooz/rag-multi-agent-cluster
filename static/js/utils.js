/* ═══════════════════════════════════════════════════════════
   JARVIS CTOS — Utilitaires
   ═══════════════════════════════════════════════════════════ */

const JARVIS = (() => {
  const API_PREFIX = '/api/v1';

  function fmtTime(iso) {
    const d = new Date(iso);
    return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function esc(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function debounce(fn, ms) {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  }

  return { API_PREFIX, fmtTime, nowIso, esc, debounce };
})();
