/* ═══════════════════════════════════════════════════════════
   JARVIS CTOS — Monitoring (poll JSON 10s, rendu cartes)
   ═══════════════════════════════════════════════════════════ */

const Monitoring = (() => {
  let cardsEl;
  let tickerEl;
  let lastUpdateEl;
  let timer = null;
  const REFRESH_MS = (window.DASHBOARD_REFRESH_SEC || 10) * 1000;

  function init() {
    cardsEl = document.getElementById('monitoring-cards');
    tickerEl = document.getElementById('alert-ticker');
    lastUpdateEl = document.getElementById('mon-last-update');
    poll();
    timer = setInterval(poll, REFRESH_MS);
  }

  async function poll() {
    try {
      const res = await fetch(`${JARVIS.API_PREFIX}/monitoring`);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      render(data);
      updateStatusPill(data);
      renderAlerts(data.alerts || []);
      lastUpdateEl.textContent = 'MAJ ' + JARVIS.fmtTime(data.timestamp || new Date().toISOString());
    } catch (e) {
      updateStatusPill(null);
      lastUpdateEl.textContent = 'POLL ÉCHOUÉ ' + JARVIS.fmtTime(new Date().toISOString());
    }
  }

  function render(data) {
    const order = ['m1', 'm2', 'm3'];
    const html = order.map((key) => cardToHtml(data.cards[key])).join('') + cardToHtml(data.cluster);
    if (cardsEl.innerHTML !== html) {
      cardsEl.innerHTML = html;
    }
  }

  function cardToHtml(card) {
    if (!card) return '';
    const rows = (card.metrics || [])
      .map((m) =>
        `<div class="m-row"><span class="m-label">${JARVIS.esc(m.label)}</span>` +
        `<span class="m-value ${JARVIS.esc(m.status)}">${JARVIS.esc(m.value)}</span></div>`
      )
      .join('');
    return (
      `<div class="metric-card ${JARVIS.esc(card.status)}" data-machine="${JARVIS.esc(card.machine)}">` +
      `<div class="card-header"><span class="machine-label">${JARVIS.esc(card.title)}</span>` +
      `<span class="status-dot ${JARVIS.esc(card.status)}"></span></div>` +
      `<div class="metrics-grid">${rows}</div></div>`
    );
  }

  function updateStatusPill(data) {
    const pill = document.getElementById('status-pill');
    if (!pill) return;
    if (!data) {
      pill.textContent = 'OFFLINE';
      pill.className = 'status-pill crit';
      return;
    }
    const hasCrit = (data.alerts || []).some((a) => a.level === 'critical');
    const hasWarn = (data.alerts || []).length > 0;
    if (hasCrit) { pill.textContent = 'DEGRADED'; pill.className = 'status-pill crit'; }
    else if (hasWarn) { pill.textContent = 'WARNING'; pill.className = 'status-pill warn'; }
    else { pill.textContent = 'NOMINAL'; pill.className = 'status-pill ok'; }
  }

  function renderAlerts(alerts) {
    if (!alerts.length) {
      tickerEl.innerHTML = '';
      return;
    }
    const html = alerts
      .map((a) =>
        `<div class="alert-item ${JARVIS.esc(a.level)}">` +
        `${JARVIS.esc(a.machine.toUpperCase())} · ${JARVIS.esc(a.metric)} : ${JARVIS.esc(a.message)}</div>`
      )
      .join('');
    if (tickerEl.innerHTML !== html) tickerEl.innerHTML = html;
  }

  return { init };
})();
