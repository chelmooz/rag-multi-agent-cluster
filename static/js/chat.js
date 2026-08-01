/* ═══════════════════════════════════════════════════════════
   CTOS — Chat (POST SSE via fetch + ReadableStream)
   ═══════════════════════════════════════════════════════════ */

const Chat = (() => {
  let messagesEl;
  let inputEl;
  let sendBtn;
  let statusEl;
  let history = [];   // sliding window (paires user/assistant)
  let busy = false;

  const MAX_HISTORY = window.CHAT_HISTORY_MAX || 10;

  async function init() {
    const area = document.getElementById('chat-area');
    const res = await fetch('/partials/chat');
    area.innerHTML = await res.text();

    messagesEl = document.getElementById('chat-messages');
    inputEl = document.getElementById('chat-input');
    sendBtn = document.getElementById('chat-send');
    statusEl = document.getElementById('chat-status');

    inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    });
    sendBtn.addEventListener('click', send);
    inputEl.addEventListener('input', autoGrow);
  }

  function autoGrow() {
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
  }

  function setStatus(text, cls) {
    statusEl.textContent = text;
    statusEl.className = 'chat-status' + (cls ? ' ' + cls : '');
  }

  function appendUser(text) {
    const wrap = document.createElement('div');
    wrap.className = 'msg user';
    wrap.innerHTML =
      '<div class="msg-bubble"></div>' +
      '<div class="msg-meta"><span class="msg-time"></span></div>';
    wrap.querySelector('.msg-bubble').textContent = text;
    wrap.querySelector('.msg-time').textContent = CTOS.fmtTime(CTOS.nowIso());
    messagesEl.appendChild(wrap);
    scrollBottom();
  }

  function appendAssistant() {
    const wrap = document.createElement('div');
    wrap.className = 'msg assistant streaming';
    wrap.innerHTML =
      '<div class="msg-bubble"></div>' +
      '<div class="msg-meta"><span class="msg-time"></span><span class="elapsed-tag"></span></div>';
    messagesEl.appendChild(wrap);
    return {
      bubble: wrap.querySelector('.msg-bubble'),
      timeEl: wrap.querySelector('.msg-time'),
      elapsedEl: wrap.querySelector('.elapsed-tag'),
    };
  }

  function appendSources(wrap, sources) {
    if (!sources || !sources.length) return;
    const srcBox = document.createElement('div');
    srcBox.className = 'msg-sources';
    sources.forEach((s) => {
      const btn = document.createElement('button');
      btn.className = 'src-tag';
      btn.textContent = s;
      btn.title = 'Source citée';
      srcBox.appendChild(btn);
    });
    wrap.querySelector('.msg-meta').appendChild(srcBox);
  }

  function scrollBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function trimHistory() {
    // Garder au plus MAX_HISTORY messages, en résumant le début
    if (history.length <= MAX_HISTORY) return history;
    const keep = history.slice(history.length - MAX_HISTORY);
    const trimmed = history.length - keep.length;
    return [
      { role: 'system', content: `[${trimmed} message(s) précédent(s) résumé(s). Contexte : conversation en cours sur le cluster RAG.]` },
      ...keep,
    ];
  }

  async function send() {
    const question = inputEl.value.trim();
    if (!question || busy) return;

    busy = true;
    sendBtn.disabled = true;
    setStatus('PROCESSING — RAG hybride M1/M2/M3…', 'busy');

    appendUser(question);
    inputEl.value = '';
    autoGrow();

    const assistant = appendAssistant();
    assistant.timeEl.textContent = CTOS.fmtTime(CTOS.nowIso());
    let text = '';

    try {
      const res = await fetch(`${CTOS.API_PREFIX}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });

      if (!res.ok || !res.body) {
        throw new Error('HTTP ' + res.status);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        // Extraire les événements SSE complets
        let idx;
        while ((idx = buf.indexOf('\n\n')) !== -1) {
          const raw = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          for (const line of raw.split('\n')) {
            if (!line.startsWith('data: ')) continue;
            const evt = JSON.parse(line.slice(6));
            if (evt.type === 'token') {
              text += evt.token;
              assistant.bubble.textContent = text;
              scrollBottom();
            } else if (evt.type === 'done') {
              assistant.wrap = assistant;
              assistant.elapsedEl.textContent = `⏱ ${evt.elapsed_ms} ms · ${evt.sources ? evt.sources.length : 0} sources`;
              appendSources(assistant, evt.sources);
              history.push({ role: 'user', content: question });
              history.push({ role: 'assistant', content: text });
              history = trimHistory();
            } else if (evt.type === 'error') {
              text = 'ERREUR : ' + evt.detail;
              assistant.bubble.textContent = text;
            }
          }
        }
      }

      assistant.wrap.className = 'msg assistant'; // stop streaming cursor
      setStatus('READY');
    } catch (e) {
      assistant.bubble.textContent = 'ERREUR RÉSEAU : ' + e.message;
      assistant.wrap.className = 'msg assistant';
      setStatus('CONNEXION PERDUE');
    } finally {
      busy = false;
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }

  return { init };
})();
