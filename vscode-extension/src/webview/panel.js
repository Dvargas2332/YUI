// @ts-check
'use strict';

// VS Code webview API
const vscode = acquireVsCodeApi();

// ── State ─────────────────────────────────────────────────────────────────────
let WS_PORT = 8765;
let HTTP_PORT = 8080;
let ws = null;
let wsRetryTimer = null;
let confirmTimer = null;
let confirmTimeout = 0;
let bootstrapLoaded = false;
let preBootstrapMessages = 0;
/** @type {Set<string>} */
const shownKeys = new Set();

// ── DOM refs ──────────────────────────────────────────────────────────────────
const $ = (/** @type {string} */ s) => document.querySelector(s);
const messages   = /** @type {HTMLElement} */ ($('#messages'));
const thinkingBar = /** @type {HTMLElement} */ ($('#thinking-bar'));
const confirmBanner = /** @type {HTMLElement} */ ($('#confirm-banner'));
const confirmDesc   = /** @type {HTMLElement} */ ($('#confirm-desc'));
const confirmTimerEl = /** @type {HTMLElement} */ ($('#confirm-timer'));
const confirmInput  = /** @type {HTMLInputElement} */ ($('#confirm-input'));
const confirmBtn    = /** @type {HTMLButtonElement} */ ($('#confirm-btn'));
const msgInput   = /** @type {HTMLTextAreaElement} */ ($('#msg-input'));
const sendBtn    = /** @type {HTMLButtonElement} */ ($('#send-btn'));
const statusDot  = /** @type {HTMLElement} */ ($('#status-dot'));
const statusLabel = /** @type {HTMLElement} */ ($('#status-label'));
const modeBadge  = /** @type {HTMLElement} */ ($('#mode-badge'));
const thinkingLabel = /** @type {HTMLElement} */ ($('#thinking-label'));
const stepsPanel  = /** @type {HTMLElement} */ ($('#steps-panel'));
const diffFeed    = /** @type {HTMLElement} */ ($('#diff-feed'));
const taskDialog  = /** @type {HTMLElement} */ ($('#task-dialog'));
const taskSummary = /** @type {HTMLElement} */ ($('#task-dialog-summary'));

/** @type {boolean} */
let autoEditMode = false;

/** @type {Map<string, HTMLElement>} */
const stepRows = new Map();

function showStep(/** @type {string} */ toolName, /** @type {string|null} */ detail, /** @type {'running'|'done'|'error'} */ state) {
  stepsPanel.style.display = 'flex';
  const icons = { write_file: '📝', read_file: '📖', create_folder: '📁', list_dir: '📂', run_command: '⚙️' };
  const icon = icons[toolName] || '🔧';
  const labels = { write_file: 'Escribiendo archivo', read_file: 'Leyendo archivo', create_folder: 'Creando carpeta', list_dir: 'Listando directorio', run_command: 'Ejecutando comando' };
  const label = labels[toolName] || toolName;

  let row = stepRows.get(toolName);
  if (!row) {
    row = document.createElement('div');
    row.className = 'step-row running';
    row.innerHTML = `<span class="step-icon">${icon}</span><span class="step-text">${label}</span><span class="step-detail"></span>`;
    stepsPanel.appendChild(row);
    stepRows.set(toolName, row);
    stepsPanel.scrollTop = stepsPanel.scrollHeight;
  }

  row.className = `step-row ${state}`;
  const detailEl = /** @type {HTMLElement} */ (row.querySelector('.step-detail'));
  if (detail && detailEl) detailEl.textContent = detail;
  if (state === 'running') {
    const icon2 = /** @type {HTMLElement} */ (row.querySelector('.step-icon'));
    if (icon2) icon2.textContent = '⏳';
  } else if (state === 'done') {
    const icon2 = /** @type {HTMLElement} */ (row.querySelector('.step-icon'));
    if (icon2) icon2.textContent = '✓';
  } else if (state === 'error') {
    const icon2 = /** @type {HTMLElement} */ (row.querySelector('.step-icon'));
    if (icon2) icon2.textContent = '✗';
  }
}

function clearSteps() {
  stepsPanel.style.display = 'none';
  stepsPanel.innerHTML = '';
  stepRows.clear();
}

// ── Init ──────────────────────────────────────────────────────────────────────
vscode.postMessage({ type: 'get_vscode_config' });

// ── Tabs ──────────────────────────────────────────────────────────────────────
document.querySelectorAll('.tab').forEach((btn) => {
  btn.addEventListener('click', () => {
    const tab = btn.getAttribute('data-tab');
    document.querySelectorAll('.tab').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
    btn.classList.add('active');
    const panel = $(`#panel-${tab}`);
    if (panel) panel.classList.add('active');
    if (tab === 'plugins') loadPlugins();
  });
});

// ── Chat composer ─────────────────────────────────────────────────────────────
msgInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
msgInput.addEventListener('input', () => autoResize(msgInput));
sendBtn.addEventListener('click', sendMessage);

function autoResize(/** @type {HTMLTextAreaElement} */ el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

function sendMessage() {
  if (sendBtn.getAttribute('data-busy') === '1') {
    vscode.postMessage({ type: 'send_command', text: '__abort__' });
    return;
  }
  const text = msgInput.value.trim();
  if (!text) return;
  msgInput.value = '';
  autoResize(msgInput);
  vscode.postMessage({ type: 'send_command', text });

  // Si el WS está conectado, el evento stt lo mostrará (evita duplicado).
  // Si no hay WS, mostrarlo inmediatamente para que el usuario vea su mensaje.
  const wsConnected = ws && ws.readyState === WebSocket.OPEN;
  if (!wsConnected) addMessage('user', text);

}

// ── Mode buttons ─────────────────────────────────────────────────────────────
document.querySelectorAll('.btn-mode').forEach((btn) => {
  btn.addEventListener('click', async () => {
    const mode = btn.getAttribute('data-mode') || 'auto';
    try {
      const res = await fetch(`http://127.0.0.1:${HTTP_PORT}/api/mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      });
      const data = await res.json();
      if (data.ok) {
        document.querySelectorAll('.btn-mode').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const labels = { fast: 'CHAT', auto: 'AUTO', deep: 'DEEP' };
        modeBadge.textContent = labels[mode] || mode.toUpperCase();
        modeBadge.style.display = 'inline';
        showToast(`Modo: ${labels[mode] || mode}`);
      }
    } catch (_) { showToast('Error cambiando modo'); }
  });
});

// ── Conversation controls ─────────────────────────────────────────────────────
$('#btn-compact')?.addEventListener('click', async () => {
  try {
    const res = await fetch(`http://127.0.0.1:${HTTP_PORT}/api/compact`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    const data = await res.json();
    if (data.ok) showToast(`Compactado — ${data.kept} mensajes conservados`);
    else showToast('Error al compactar');
  } catch (_) { showToast('Sin conexión al servidor'); }
});

$('#btn-clear-chat')?.addEventListener('click', async () => {
  if (!confirm('¿Limpiar toda la conversación? No se puede deshacer.')) return;
  try {
    const res = await fetch(`http://127.0.0.1:${HTTP_PORT}/api/clear`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    const data = await res.json();
    if (data.ok) {
      messages.innerHTML = '';
      bootstrapLoaded = false;
      preBootstrapMessages = 0;
      showToast('Conversación limpiada');
    } else showToast('Error al limpiar');
  } catch (_) { showToast('Sin conexión al servidor'); }
});

// ── Server controls ───────────────────────────────────────────────────────────
const btnStart = /** @type {HTMLButtonElement|null} */ ($('#btn-start'));
const btnStop  = /** @type {HTMLButtonElement|null} */ ($('#btn-stop'));

function setServerRunning(running) {
  if (btnStart) btnStart.disabled = running;
  if (btnStop)  btnStop.disabled  = !running;
  if (btnStart) btnStart.style.opacity = running ? '0.45' : '1';
  if (btnStop)  btnStop.style.opacity  = !running ? '0.45' : '1';
}

btnStart?.addEventListener('click', () => {
  setServerRunning(true);
  vscode.postMessage({ type: 'start_server' });
});
btnStop?.addEventListener('click', () => {
  setServerRunning(false);
  vscode.postMessage({ type: 'stop_server' });
  ws?.close();
  setStatus('disconnected', 'Sin conexión');
});

$('#btn-shutdown')?.addEventListener('click', async () => {
  if (!confirm('¿Apagar YUI? El proceso Python se cerrará limpiamente.')) return;
  try {
    await fetch(`http://127.0.0.1:${HTTP_PORT}/api/shutdown`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    });
  } catch (_) {}
  ws?.close();
  setStatus('disconnected', 'Apagado');
  setServerRunning(false);
  showToast('YUI apagado');
});

// Estado inicial: Detener deshabilitado
setServerRunning(false);

// ── Config save ───────────────────────────────────────────────────────────────
$('#btn-save-config')?.addEventListener('click', () => {
  const payload = {};
  const fields = {
    'cfg-base-url':    'YUI_LLM_BASE_URL',
    'cfg-api-key':     'YUI_LLM_API_KEY',
    'cfg-model-fast':  'YUI_LLM_MODEL_FAST',
    'cfg-model-deep':  'YUI_LLM_MODEL_DEEP',
    'cfg-llm-mode':    'YUI_LLM_MODE',
    'cfg-temperature': 'YUI_LLM_TEMPERATURE',
    'cfg-max-tokens':  'YUI_LLM_MAX_TOKENS',
    'cfg-stt-lang':    'YUI_STT_LANGUAGE',
    'cfg-tts':         'YUI_TTS_ENGINE',
  };
  for (const [id, key] of Object.entries(fields)) {
    const el = /** @type {HTMLInputElement | null} */ (document.getElementById(id));
    if (el && el.value.trim()) payload[key] = el.value.trim();
  }
  vscode.postMessage({ type: 'save_config', payload });
  showToast('Configuración guardada');
});

// ── Toggle switches ───────────────────────────────────────────────────────────
document.querySelectorAll('[data-key]').forEach((el) => {
  el.addEventListener('change', (e) => {
    const input = /** @type {HTMLInputElement} */ (e.target);
    vscode.postMessage({ type: 'toggle', key: input.dataset.key, value: input.checked });
  });
});

// ── Confirm ───────────────────────────────────────────────────────────────────
confirmBtn.addEventListener('click', () => {
  const code = confirmInput.value.trim();
  if (!code) return;
  vscode.postMessage({ type: 'send_command', text: `confirmar codigo ${code}` });
  hideConfirm();
});

$('#confirm-yes-btn')?.addEventListener('click', () => {
  const code = confirmInput.value.trim();
  vscode.postMessage({ type: 'send_command', text: code ? `confirmar codigo ${code}` : 'confirmar' });
  hideConfirm();
});

$('#confirm-no-btn')?.addEventListener('click', () => {
  vscode.postMessage({ type: 'send_command', text: 'cancelar' });
  hideConfirm();
});

// ── WebSocket ─────────────────────────────────────────────────────────────────
function connectWS() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  ws = new WebSocket(`ws://127.0.0.1:${WS_PORT}`);

  ws.onopen = () => {
    setStatus('connected', 'Conectado');
    clearTimeout(wsRetryTimer ?? undefined);
    setServerRunning(true);
  };

  ws.onclose = () => {
    setStatus('disconnected', 'Sin conexión');
    wsRetryTimer = setTimeout(connectWS, 2000);
  };

  ws.onerror = () => {
    ws?.close();
  };

  ws.onmessage = (ev) => {
    let evt;
    try { evt = JSON.parse(ev.data); } catch { return; }
    handleWsEvent(evt);
  };
}

function handleWsEvent(/** @type {any} */ evt) {
  switch (evt.type) {
    case 'hello':
      loadBootstrap();
      break;

    case 'thinking':
      setStatus('thinking', 'Pensando…');
      if (thinkingLabel) thinkingLabel.textContent = 'YUI está pensando…';
      thinkingBar.style.display = 'flex';
      clearSteps();
      clearDiffFeed();
      hideTaskDialog();
      autoEditMode = false;
      break;

    case 'tool_start': {
      const tool = evt.data?.tool || '';
      const detail = evt.data?.detail || null;
      if (thinkingLabel) thinkingLabel.textContent = `Ejecutando ${tool}…`;
      showStep(tool, detail, 'running');
      addPulseMsg('start', tool, detail);
      break;
    }

    case 'tool_end': {
      const tool = evt.data?.tool || '';
      const detail = evt.data?.detail || null;
      const isError = (detail || '').startsWith('[error]') || (detail || '').startsWith('[cancelado]');
      showStep(tool, detail, isError ? 'error' : 'done');
      addPulseMsg(isError ? 'error' : 'end', tool, detail);
      if (thinkingLabel) thinkingLabel.textContent = 'YUI está pensando…';
      break;
    }

    case 'status':
      setStatus('connected', 'Listo');
      thinkingBar.style.display = 'none';
      setTimeout(clearSteps, 1500);
      break;

    case 'assistant': {
      thinkingBar.style.display = 'none';
      setStatus('connected', 'Listo');
      setTimeout(clearSteps, 1500);
      // Use full display text when available; spoken is the short TTS version
      const text = evt.data?.text || evt.data?.spoken || '';
      addMessage('assistant', text);
      break;
    }

    case 'stt': {
      const text = evt.data?.text || '';
      if (text) addMessage('user', text);
      break;
    }

    case 'confirm': {
      const { state, description, code, timeout_s } = evt.data || {};
      if (state === 'cleared') { hideConfirm(); break; }
      showConfirm(description, timeout_s, code);
      break;
    }

    case 'busy': {
      const busy = evt.data?.state === 'start';
      sendBtn.title = busy ? 'Detener' : 'Enviar';
      sendBtn.setAttribute('data-busy', busy ? '1' : '0');
      sendBtn.innerHTML = busy
        ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>'
        : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>';
      break;
    }

    case 'security_alert': {
      const { title, detail } = evt.data || {};
      addMessage('assistant', `⚠️ **${title}**\n${detail}`);
      break;
    }

    case 'file_diff': {
      const payload = evt.data?.detail;
      if (!payload) break;
      let diff;
      try { diff = JSON.parse(payload); } catch { break; }
      showDiffCard(diff);
      break;
    }

    case 'task_complete': {
      if (autoEditMode) break;
      const summary = evt.data?.tool || evt.data?.detail || 'Tarea completada.';
      showTaskDialog(summary);
      break;
    }
  }
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────
async function loadBootstrap() {
  try {
    const res = await fetch(`http://127.0.0.1:${HTTP_PORT}/api/bootstrap`);
    if (!res.ok) return;
    const state = await res.json();

    // actualizar puerto WS real si el servidor lo reporta
    if (state.ws_port && state.ws_port !== WS_PORT) {
      WS_PORT = state.ws_port;
    }

    // mode badge
    if (state.mode) {
      const m = state.mode.input || '';
      modeBadge.textContent = m.toUpperCase();
      modeBadge.style.display = 'inline';
    }

    // history — solo carga una vez para evitar duplicados en reconexión
    if (!bootstrapLoaded && Array.isArray(state.history)) {
      bootstrapLoaded = true;
      const relevant = state.history.filter(h => h.role === 'user' || h.role === 'assistant');
      for (const h of relevant.slice(-30)) {
        addMessage(h.role, h.content, true);
      }
    }

    // toggles
    const perms = state.permissions || {};
    setToggle('tog-desktop',    perms.desktop_enabled);
    setToggle('tog-text-only',  perms.agent_text_only);
    setToggle('tog-security',   perms.security_guard);
    setToggle('tog-confirm-ui', perms.confirm_ui_allowed);

    // LLM config
    const prompts = state.prompts || {};
    if (prompts.llm_mode) {
      document.querySelectorAll('.btn-mode').forEach(b => {
        b.classList.toggle('active', b.getAttribute('data-mode') === prompts.llm_mode);
      });
    }
    setField('cfg-base-url',    prompts.llm_base_url);
    setField('cfg-model-fast',  prompts.llm_model_fast);
    setField('cfg-model-deep',  prompts.llm_model_deep);
    setField('cfg-temperature', prompts.llm_temperature);
    setField('cfg-llm-mode',    prompts.llm_mode);
    setField('cfg-stt-lang',    prompts.stt_language);
    setField('cfg-tts',         prompts.tts_engine);

  } catch (_) {}
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function addMessage(/** @type {string} */ role, /** @type {string} */ text, /** @type {boolean} */ fromHistory = false) {
  const key = role + ':' + text.trim();
  if (fromHistory && shownKeys.has(key)) return;
  shownKeys.add(key);

  const isUser = role === 'user';
  const div = document.createElement('div');
  div.className = `msg msg-${isUser ? 'user' : 'assistant'}`;

  const header = document.createElement('div');
  header.className = 'msg-header';
  const avatar = document.createElement('div');
  avatar.className = `avatar ${isUser ? 'avatar-user' : 'avatar-ai'}`;
  avatar.textContent = isUser ? 'Tú' : '✦';
  const time = document.createElement('span');
  time.textContent = new Date().toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
  header.append(avatar, time);

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.innerHTML = simpleMarkdown(text);

  div.append(header, bubble);
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

function simpleMarkdown(/** @type {string} */ raw) {
  let s = String(raw || '');

  // Escape HTML first
  s = s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');

  // Code blocks
  s = s.replace(/```([\w]*)\n?([\s\S]*?)```/g, (_, _lang, code) =>
    `<pre class="md-pre"><code>${code.trim()}</code></pre>`);

  // Inline code
  s = s.replace(/`([^`\n]+)`/g, '<code class="md-code">$1</code>');

  // Headings
  s = s.replace(/^### (.+)$/gm, '<h4 class="md-h4">$1</h4>');
  s = s.replace(/^## (.+)$/gm,  '<h3 class="md-h3">$1</h3>');
  s = s.replace(/^# (.+)$/gm,   '<h2 class="md-h2">$1</h2>');

  // Horizontal rule
  s = s.replace(/^(?:---|\*\*\*|___)$/gm, '<hr class="md-hr">');

  // Bold + italic
  s = s.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/__(.+?)__/g,     '<strong>$1</strong>');
  s = s.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
  s = s.replace(/_([^_\n]+)_/g,   '<em>$1</em>');

  // Unordered lists
  s = s.replace(/((?:^[ \t]*[-*] .+\n?)+)/gm, (block) => {
    const items = block.trim().split('\n')
      .map(l => `<li>${l.replace(/^[ \t]*[-*] /, '').trim()}</li>`).join('');
    return `<ul class="md-ul">${items}</ul>`;
  });

  // Ordered lists
  s = s.replace(/((?:^[ \t]*\d+\. .+\n?)+)/gm, (block) => {
    const items = block.trim().split('\n')
      .map(l => `<li>${l.replace(/^[ \t]*\d+\. /, '').trim()}</li>`).join('');
    return `<ol class="md-ol">${items}</ol>`;
  });

  // Tables
  s = s.replace(/((?:^\|.+\|\n?)+)/gm, (block) => {
    const rows = block.trim().split('\n').filter(r => !/^\|[-| :]+\|$/.test(r.trim()));
    if (!rows.length) return block;
    const [header, ...body] = rows;
    const ths = header.split('|').filter((_, i, a) => i > 0 && i < a.length - 1)
      .map(c => `<th>${c.trim()}</th>`).join('');
    const trs = body.map(row => {
      const tds = row.split('|').filter((_, i, a) => i > 0 && i < a.length - 1)
        .map(c => `<td>${c.trim()}</td>`).join('');
      return `<tr>${tds}</tr>`;
    }).join('');
    return `<table class="md-table"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
  });

  // Blockquote
  s = s.replace(/^&gt; (.+)$/gm, '<blockquote class="md-bq">$1</blockquote>');

  // Paragraphs
  const blocks = s.split(/\n{2,}/);
  s = blocks.map(b => {
    b = b.trim();
    if (!b) return '';
    if (/^<(ul|ol|pre|h[2-4]|blockquote|hr|table)/.test(b)) return b;
    return `<p>${b.replace(/\n/g, '<br>')}</p>`;
  }).join('\n');

  return s;
}

// ── Pulso: agent trace bubbles ────────────────────────────────────────────────
const PULSE_ICONS = {
  start: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.22-8.56"/><polyline points="21 3 21 9 15 9"/></svg>`,
  end:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`,
  error: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
};
const PULSE_LABELS = { start: 'ejecutando', end: 'listo', error: 'error' };

function addPulseMsg(/** @type {'start'|'end'|'error'} */ kind, /** @type {string} */ toolName, /** @type {string|null} */ detail) {
  const now = new Date().toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const div = document.createElement('div');
  div.className = `pulse-trace ${kind}`;
  div.innerHTML = `
    <div class="pulse-icon">${PULSE_ICONS[kind]}</div>
    <div class="pulse-body">
      <div class="pulse-header">
        <span class="pulse-tag">${PULSE_LABELS[kind]}</span>
        <span class="pulse-tool">${escHtml(toolName || '?')}</span>
        <span class="pulse-time">${now}</span>
      </div>
      ${detail ? `<div class="pulse-detail">${escHtml(detail)}</div>` : ''}
    </div>`;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

function setStatus(/** @type {string} */ state, /** @type {string} */ label) {
  statusDot.className = `dot ${state}`;
  statusLabel.textContent = label;
}

function setToggle(/** @type {string} */ id, /** @type {boolean|undefined} */ value) {
  const el = /** @type {HTMLInputElement|null} */ (document.getElementById(id));
  if (el && value !== undefined) el.checked = Boolean(value);
}

function setField(/** @type {string} */ id, /** @type {any} */ value) {
  const el = /** @type {HTMLInputElement|null} */ (document.getElementById(id));
  if (el && value !== undefined && value !== null) el.value = String(value);
}

function showConfirm(/** @type {string} */ desc, /** @type {number} */ timeout, /** @type {string} */ code) {
  confirmDesc.textContent = desc || 'Confirmar acción';
  confirmBanner.style.display = 'block';
  confirmInput.value = code || '';
  confirmTimeout = timeout || 60;
  updateConfirmTimer();
  clearInterval(confirmTimer ?? undefined);
  confirmTimer = setInterval(() => {
    confirmTimeout--;
    if (confirmTimeout <= 0) { hideConfirm(); return; }
    updateConfirmTimer();
  }, 1000);
}

function updateConfirmTimer() {
  confirmTimerEl.textContent = `${confirmTimeout}s`;
}

function hideConfirm() {
  clearInterval(confirmTimer ?? undefined);
  confirmBanner.style.display = 'none';
}

function showToast(/** @type {string} */ msg) {
  const t = document.createElement('div');
  t.textContent = msg;
  t.style.cssText = `position:fixed;bottom:60px;left:50%;transform:translateX(-50%);
    background:#333;color:#eee;font-size:11px;border-radius:6px;padding:5px 12px;
    z-index:999;animation:fadeIn .15s ease;`;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2000);
}

// ── Diff cards ────────────────────────────────────────────────────────────────
function showDiffCard(/** @type {any} */ diff) {
  if (!diffFeed) return;
  const path = diff.path || '';
  const chunks = Array.isArray(diff.chunks) ? diff.chunks : [];
  const added = diff.added || 0;
  const removed = diff.removed || 0;

  const card = document.createElement('div');
  card.className = 'diff-card';

  const header = document.createElement('div');
  header.className = 'diff-card-header';
  header.innerHTML = `
    <span class="diff-card-icon">📝</span>
    <span class="diff-card-path" title="${escHtml(path)}">${escHtml(path.split(/[\\/]/).pop() || path)}</span>
    <span class="diff-card-stats">
      ${added ? `<span class="diff-stat-add">+${added}</span>` : ''}
      ${removed ? `<span class="diff-stat-rm">-${removed}</span>` : ''}
    </span>
    <span style="color:var(--text3);font-size:10px">▼</span>`;
  header.addEventListener('click', () => {
    card.classList.toggle('expanded');
    const arrow = /** @type {HTMLElement|null} */ (header.querySelector('span:last-child'));
    if (arrow) arrow.textContent = card.classList.contains('expanded') ? '▲' : '▼';
  });

  const body = document.createElement('div');
  body.className = 'diff-card-body';

  for (const chunk of chunks.slice(0, 150)) {
    if (chunk.old !== null && chunk.old !== undefined && chunk.old !== chunk.new) {
      const rm = document.createElement('div');
      rm.className = 'diff-line rm';
      rm.innerHTML = `<span class="diff-ln">${chunk.ln}</span><span>- ${escHtml(String(chunk.old))}</span>`;
      body.appendChild(rm);
    }
    if (chunk.new !== null && chunk.new !== undefined && chunk.old !== chunk.new) {
      const add = document.createElement('div');
      add.className = 'diff-line add';
      add.innerHTML = `<span class="diff-ln">${chunk.ln}</span><span>+ ${escHtml(String(chunk.new))}</span>`;
      body.appendChild(add);
    }
  }

  if (!chunks.length) {
    const note = document.createElement('div');
    note.className = 'diff-line ctx';
    note.textContent = '  (archivo nuevo sin diff)';
    body.appendChild(note);
  }

  card.append(header, body);
  diffFeed.appendChild(card);
  diffFeed.scrollTop = diffFeed.scrollHeight;

  // Keep at most 10 diff cards to avoid flooding
  while (diffFeed.children.length > 10) {
    diffFeed.removeChild(diffFeed.firstChild);
  }
}

function clearDiffFeed() {
  if (diffFeed) diffFeed.innerHTML = '';
}

// ── Task dialog ───────────────────────────────────────────────────────────────
function showTaskDialog(/** @type {string} */ summary) {
  if (!taskDialog || !taskSummary) return;
  taskSummary.textContent = summary;
  taskDialog.style.display = 'block';
}

function hideTaskDialog() {
  if (taskDialog) taskDialog.style.display = 'none';
}

$('#task-btn-approve')?.addEventListener('click', () => {
  hideTaskDialog();
  clearDiffFeed();
  showToast('Tarea aprobada');
});

$('#task-btn-deny')?.addEventListener('click', () => {
  hideTaskDialog();
  clearDiffFeed();
  vscode.postMessage({ type: 'send_command', text: 'No es lo que pedí, inténtalo de nuevo.' });
  showToast('Enviando corrección…');
});

$('#task-btn-auto')?.addEventListener('click', () => {
  autoEditMode = true;
  hideTaskDialog();
  clearDiffFeed();
  showToast('Modo auto-editar activado — YUI continuará sin pedir confirmación');
});

// ── Plugins ───────────────────────────────────────────────────────────────────
const pluginList = /** @type {HTMLElement|null} */ ($('#plugin-list'));

async function loadPlugins() {
  if (!pluginList) return;
  try {
    const res = await fetch(`http://127.0.0.1:${HTTP_PORT}/api/plugins`);
    const data = await res.json();
    renderPlugins(data.plugins || []);
  } catch (_) {
    if (pluginList) pluginList.innerHTML = '<div class="hint">Sin conexión al servidor</div>';
  }
}

function renderPlugins(/** @type {any[]} */ plugins) {
  if (!pluginList) return;
  if (!plugins.length) {
    pluginList.innerHTML = '<div class="hint">No hay plugins instalados.</div>';
    return;
  }
  pluginList.innerHTML = plugins.map(p => `
    <div class="plugin-card">
      <div class="plugin-info">
        <div class="plugin-name">${escHtml(p.name)} <span class="badge">${escHtml(p.version)}</span></div>
        <div class="plugin-desc">${escHtml(p.description)}</div>
      </div>
      <label class="switch" title="${p.enabled ? 'Deshabilitar' : 'Habilitar'}">
        <input type="checkbox" ${p.enabled ? 'checked' : ''} data-plugin-folder="${escHtml(p.folder)}"/>
        <span class="slider"></span>
      </label>
    </div>
  `).join('');

  pluginList.querySelectorAll('[data-plugin-folder]').forEach(el => {
    el.addEventListener('change', async (e) => {
      const input = /** @type {HTMLInputElement} */ (e.target);
      const folder = input.dataset.pluginFolder || '';
      const action = input.checked ? 'enable' : 'disable';
      try {
        const res = await fetch(`http://127.0.0.1:${HTTP_PORT}/api/plugins`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action, folder }),
        });
        const data = await res.json();
        if (data.ok) renderPlugins(data.plugins || []);
        else showToast('Error: ' + (data.error || 'desconocido'));
      } catch (_) { showToast('Sin conexión'); }
    });
  });
}

$('#btn-install-plugin')?.addEventListener('click', async () => {
  const nameEl = /** @type {HTMLInputElement|null} */ ($('#new-plugin-name'));
  const descEl = /** @type {HTMLInputElement|null} */ ($('#new-plugin-desc'));
  const name = nameEl?.value.trim() || '';
  const description = descEl?.value.trim() || '';
  if (!name) { showToast('Escribe un nombre para el plugin'); return; }
  try {
    const res = await fetch(`http://127.0.0.1:${HTTP_PORT}/api/plugins`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'install', name, description }),
    });
    const data = await res.json();
    if (data.ok) {
      if (nameEl) nameEl.value = '';
      if (descEl) descEl.value = '';
      renderPlugins(data.plugins || []);
      showToast(`Plugin "${name}" instalado`);
    } else {
      showToast('Error: ' + (data.error || 'desconocido'));
    }
  } catch (_) { showToast('Sin conexión'); }
});

function escHtml(/** @type {string} */ s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Messages from extension host ──────────────────────────────────────────────
window.addEventListener('message', (ev) => {
  const msg = ev.data;
  switch (msg.type) {
    case 'vscode_config':
      HTTP_PORT = msg.config.httpPort || 8080;
      WS_PORT   = msg.config.wsPort   || 8765;
      connectWS();
      break;

    case 'inject_text':
      msgInput.value = (msgInput.value ? msgInput.value + '\n' : '') + msg.text;
      autoResize(msgInput);
      msgInput.focus();
      break;

    case 'server_started':
      setStatus('thinking', 'Iniciando…');
      setServerRunning(true);
      // Reintentar durante 30 s mientras el proceso levanta
      let _startAttempts = 0;
      const _startPoll = setInterval(() => {
        _startAttempts++;
        connectWS();
        if (_startAttempts >= 15) clearInterval(_startPoll);
      }, 2000);
      break;

    case 'server_stopped':
      setStatus('disconnected', 'Servidor detenido');
      setServerRunning(false);
      break;
  }
});
