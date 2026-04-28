'use strict';

// ---- STATE ----
const S = {
  ws: null,
  bootstrap: null,
  typingMsg: null,
};

// ---- UTILS ----
function fmt(ts) {
  return new Date(ts ? ts * 1000 : Date.now()).toLocaleTimeString('es-CR', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

function qs(sel, ctx = document) { return ctx.querySelector(sel); }
function qsa(sel, ctx = document) { return [...ctx.querySelectorAll(sel)]; }

// ---- TABS ----
qsa('.nav-item').forEach(btn => {
  btn.addEventListener('click', () => {
    const tabId = 'tab-' + btn.dataset.tab;
    qsa('.nav-item').forEach(b => b.classList.remove('active'));
    qsa('.tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    const tab = document.getElementById(tabId);
    if (tab) tab.classList.add('active');
  });
});

// ---- CHAT ----
const chatArea = document.getElementById('chat-messages');

function scrollChat() {
  chatArea.scrollTop = chatArea.scrollHeight;
}

function addMsg(role, text, ts) {
  const names = { assistant: 'YUI', user: 'Tú', system: 'Sistema' };
  const initials = { assistant: 'Y', user: 'U', system: '!' };

  // Assistant messages get markdown rendering; user/system get plain escaped text
  const bubbleHtml = role === 'assistant'
    ? renderMarkdown(text)
    : escHtml(text).replace(/\n/g, '<br>');

  const article = document.createElement('article');
  article.className = `msg ${role}`;
  article.innerHTML = `
    <div class="msg-avatar">${initials[role] || '?'}</div>
    <div class="msg-body">
      <div class="msg-meta">
        <span class="msg-name">${names[role] || role}</span>
        <span class="msg-time">${fmt(ts)}</span>
      </div>
      <div class="msg-bubble md-body">${bubbleHtml}</div>
    </div>`;
  chatArea.appendChild(article);
  scrollChat();
  return article;
}

// ---- PULSO — agent trajectory trace ----
const TOOL_ICONS = {
  start: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.22-8.56"/><polyline points="21 3 21 9 15 9"/></svg>`,
  end:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`,
  error: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
};

const TOOL_LABELS = {
  start: 'ejecutando',
  end:   'completado',
  error: 'error',
};

function addPulse(kind, toolName, detail, ts) {
  const isStart = kind === 'start';
  const isError = kind === 'error';
  const stateClass = isError ? 'error' : (isStart ? 'start' : 'end');

  const wrap = document.createElement('div');
  wrap.className = `pulse-trace ${stateClass}`;
  wrap.innerHTML = `
    <div class="pulse-icon">${TOOL_ICONS[stateClass]}</div>
    <div class="pulse-body">
      <div class="pulse-header">
        <span class="pulse-tag">${TOOL_LABELS[stateClass]}</span>
        <span class="pulse-tool">${escHtml(toolName || '?')}</span>
        <span class="pulse-time">${fmt(ts)}</span>
      </div>
      ${detail ? `<div class="pulse-detail">${escHtml(detail)}</div>` : ''}
    </div>`;
  chatArea.appendChild(wrap);
  scrollChat();
  return wrap;
}

function addActivityLog(kind, text, ts) {
  const log = document.getElementById('activity-log');
  if (!log) return;
  const item = document.createElement('div');
  item.className = 'activity-item';
  item.innerHTML = `<span class="act-time">${fmt(ts)}</span><span class="act-kind ${kind}">${kind.toUpperCase()}</span><span class="act-text">${escHtml(text)}</span>`;
  log.prepend(item);
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Lightweight markdown renderer (no external deps)
function renderMarkdown(raw) {
  let s = String(raw || '');

  // Escape HTML first so injected content is safe
  s = s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

  // Code blocks (``` ... ```)
  s = s.replace(/```([\w]*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre class="md-code"><code>${code.trim()}</code></pre>`;
  });

  // Inline code (`code`)
  s = s.replace(/`([^`\n]+)`/g, '<code class="md-inline">$1</code>');

  // Headings (### ## #) — must be at start of line
  s = s.replace(/^### (.+)$/gm, '<h4 class="md-h">$1</h4>');
  s = s.replace(/^## (.+)$/gm, '<h3 class="md-h">$1</h3>');
  s = s.replace(/^# (.+)$/gm, '<h2 class="md-h">$1</h2>');

  // Horizontal rule (--- or ***)
  s = s.replace(/^(?:---|\*\*\*|___)$/gm, '<hr class="md-hr">');

  // Bold+italic ***text***
  s = s.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  // Bold **text** or __text__
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/__(.+?)__/g, '<strong>$1</strong>');
  // Italic *text* or _text_
  s = s.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
  s = s.replace(/_([^_\n]+)_/g, '<em>$1</em>');

  // Unordered lists (- item or * item)
  s = s.replace(/((?:^[ \t]*[-*] .+\n?)+)/gm, (block) => {
    const items = block.trim().split('\n').map(l => {
      const text = l.replace(/^[ \t]*[-*] /, '').trim();
      return `<li>${text}</li>`;
    }).join('');
    return `<ul class="md-list">${items}</ul>`;
  });

  // Ordered lists (1. item)
  s = s.replace(/((?:^[ \t]*\d+\. .+\n?)+)/gm, (block) => {
    const items = block.trim().split('\n').map(l => {
      const text = l.replace(/^[ \t]*\d+\. /, '').trim();
      return `<li>${text}</li>`;
    }).join('');
    return `<ol class="md-list">${items}</ol>`;
  });

  // Tables (| col | col |)
  s = s.replace(/((?:^\|.+\|\n?)+)/gm, (block) => {
    const rows = block.trim().split('\n').filter(r => !/^\|[-| :]+\|$/.test(r.trim()));
    if (rows.length === 0) return block;
    const [header, ...body] = rows;
    const thCells = header.split('|').filter((_, i, a) => i > 0 && i < a.length - 1)
      .map(c => `<th>${c.trim()}</th>`).join('');
    const trs = body.map(row => {
      const tds = row.split('|').filter((_, i, a) => i > 0 && i < a.length - 1)
        .map(c => `<td>${c.trim()}</td>`).join('');
      return `<tr>${tds}</tr>`;
    }).join('');
    return `<table class="md-table"><thead><tr>${thCells}</tr></thead><tbody>${trs}</tbody></table>`;
  });

  // Blockquote (> text)
  s = s.replace(/^&gt; (.+)$/gm, '<blockquote class="md-quote">$1</blockquote>');

  // Paragraph breaks: double newline → new block
  const blocks = s.split(/\n{2,}/);
  s = blocks.map(block => {
    block = block.trim();
    if (!block) return '';
    // Don't wrap already-block elements
    if (/^<(ul|ol|pre|h[2-4]|blockquote|hr|table)/.test(block)) return block;
    // Single newlines within a paragraph → <br>
    block = block.replace(/\n/g, '<br>');
    return `<p>${block}</p>`;
  }).join('\n');

  return s;
}

// ---- SEND COMMAND ----
async function sendCommand(text) {
  if (!text.trim()) return;
  addMsg('user', text);
  addActivityLog('user', text);

  // show typing indicator on assistant side
  const typing = document.createElement('article');
  typing.className = 'msg assistant typing';
  typing.innerHTML = `
    <div class="msg-avatar">Y</div>
    <div class="msg-body">
      <div class="msg-meta"><span class="msg-name">YUI</span></div>
      <div class="msg-bubble">…</div>
    </div>`;
  chatArea.appendChild(typing);
  S.typingMsg = typing;
  scrollChat();

  try {
    const res = await fetch('/api/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    if (!data.ok) {
      removeTyping();
      addMsg('system', 'No pude enviar ese comando.');
    }
  } catch (err) {
    removeTyping();
    addMsg('system', 'Error de red: ' + err.message);
  }
}

function removeTyping() {
  if (S.typingMsg) { S.typingMsg.remove(); S.typingMsg = null; }
}

// FORM SUBMIT
qs('#command-form').addEventListener('submit', async e => {
  e.preventDefault();
  const inp = qs('#command-input');
  const text = inp.value.trim();
  if (!text) return;
  inp.value = '';
  inp.style.height = '';
  await sendCommand(text);
});

// Auto-resize textarea
qs('#command-input').addEventListener('input', function () {
  this.style.height = '';
  this.style.height = Math.min(this.scrollHeight, 160) + 'px';
});

// Enter to send (shift+enter for newline)
qs('#command-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    qs('#command-form').dispatchEvent(new Event('submit'));
  }
});

// Chips
qsa('[data-command]').forEach(btn => {
  btn.addEventListener('click', () => sendCommand(btn.dataset.command));
});

// Clear chat
qs('#clear-chat').addEventListener('click', async () => {
  if (!confirm('¿Borrar el historial de conversación?')) return;
  chatArea.innerHTML = '';
  try {
    await fetch('/api/clear', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  } catch (_) {}
});

// ---- CONFIRMATION BANNER ----
function renderConfirmBanner(data) {
  const banner = qs('#confirm-banner');
  if (!data) { banner.classList.add('hidden'); return; }
  banner.classList.remove('hidden');
  qs('#confirm-desc').textContent = data.description || 'Acción pendiente';
  qs('#confirm-timeout-label').textContent = `Vence en ${Math.max(0, Math.round(data.timeout_s || 0))}s · código: ${data.code}`;
}

qs('#confirm-form').addEventListener('submit', async e => {
  e.preventDefault();
  const code = qs('#confirm-code').value.trim();
  if (!code) return;
  qs('#confirm-code').value = '';
  await sendCommand(`confirmar codigo ${code}`);
});

qs('#cancel-confirm').addEventListener('click', () => sendCommand('cancelar'));

// ---- WEBSOCKET ----
function connectWs(port) {
  port = port || (S.bootstrap && S.bootstrap.ws_port) || 8765;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.hostname}:${port}`);
  S.ws = ws;

  ws.addEventListener('open', () => {
    qs('#ws-state').textContent = 'conectado';
    qs('#ws-dot').classList.add('connected');
  });

  ws.addEventListener('close', () => {
    qs('#ws-state').textContent = 'reconectando';
    qs('#ws-dot').classList.remove('connected');
    setTimeout(() => connectWs(port), 1800);
  });

  ws.addEventListener('message', e => {
    let payload;
    try { payload = JSON.parse(e.data); } catch { return; }
    const { type, data, ts } = payload;

    if (type === 'assistant') {
      removeTyping();
      addMsg('assistant', data.text || '', ts);
      // Activity log shows the short spoken version (no markdown clutter)
      addActivityLog('assistant', data.spoken || data.text || '', ts);
      qs('#avatar-ring').classList.remove('thinking');
      qs('#status-dot').className = 'status-dot';
      qs('#agent-state').textContent = 'listo';
      return;
    }
    if (type === 'stt') {
      addMsg('user', data.text || '', ts);
      addActivityLog('user', data.text || '', ts);
      return;
    }
    if (type === 'thinking') {
      qs('#avatar-ring').classList.add('thinking');
      qs('#status-dot').className = 'status-dot thinking';
      qs('#agent-state').textContent = 'pensando';
      return;
    }
    if (type === 'confirm') {
      renderConfirmBanner(data);
      if (data.description) addMsg('system', `⚠ Confirmación requerida: ${data.description}`, ts);
      return;
    }
    if (type === 'security_alert') {
      addMsg('system', `🔒 ${data.title || 'Alerta'}\n${data.detail || ''}`.trim(), ts);
      addActivityLog('system', data.title || 'Alerta de seguridad', ts);
      return;
    }
    if (type === 'tool_start') {
      addPulse('start', data.tool, data.detail, ts);
      addActivityLog('system', `→ ${data.tool}${data.detail ? ': ' + data.detail : ''}`, ts);
      return;
    }
    if (type === 'tool_end') {
      const isErr = data.detail && data.detail.startsWith('[error]');
      addPulse(isErr ? 'error' : 'end', data.tool, data.detail, ts);
      addActivityLog('system', `✓ ${data.tool}${data.detail ? ': ' + data.detail : ''}`, ts);
      return;
    }
    if (type === 'analysis') {
      if (data.state === 'step') {
        addPulse('start', data.step || 'análisis', null, ts);
      } else if (data.state === 'done') {
        addPulse('end', 'análisis completado', data.canceled ? 'cancelado' : null, ts);
      }
      return;
    }
    if (type === 'status') {
      qs('#agent-state').textContent = 'listo';
      qs('#avatar-ring').classList.remove('thinking');
      qs('#status-dot').className = 'status-dot';
    }
  });
}

// ---- TOGGLE HELPER ----
async function setToggle(key, value) {
  const res = await fetch('/api/toggle', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key, value }),
  });
  const data = await res.json();
  if (data.ok !== false) setTimeout(loadBootstrap, 200);
}

// ---- BOOTSTRAP ----
async function loadBootstrap() {
  try {
    const res = await fetch('/api/bootstrap');
    S.bootstrap = await res.json();
    applyBootstrap(S.bootstrap);
  } catch (err) {
    qs('#agent-state').textContent = 'sin conexión';
  }
}

function applyBootstrap(d) {
  const mode = d.mode || {};
  qs('#mode-pill').textContent = mode.input || 'text';
  qs('#agent-state').textContent = d.agent_state || 'listo';
  qs('#status-dot').className = 'status-dot' + (d.agent_state === 'pensando' ? ' thinking' : '');

  const prompts = d.prompts || {};
  qs('#llm-model-badge').textContent = prompts.llm_model_fast || '—';

  // Chat history (only on first load)
  if (chatArea.children.length === 0) {
    (d.history || []).slice(-40).forEach(h => {
      addMsg(h.role === 'assistant' ? 'assistant' : h.role === 'user' ? 'user' : 'system', h.content);
    });
  }

  // Confirmation banner
  renderConfirmBanner(d.confirmation || null);

  // Tasks tab
  renderTasks(d.tasks || []);
  renderCatalog(d.catalog || {});

  // Prompts & Rules tab
  renderRules(d.rules || {});
  renderToggles(d.permissions || {});

  // Config tab (pre-fill if not dirty)
  fillConfigForm(prompts);

  // System tab
  renderModeStats(mode);
  renderKvList('prompts-panel', [
    ['Modo LLM', prompts.llm_mode || 'auto'],
    ['Modelo rápido', prompts.llm_model_fast || '—'],
    ['Modelo profundo', prompts.llm_model_deep || '—'],
    ['Temp rápida', prompts.llm_temperature],
    ['Temp profunda', prompts.llm_deep_temperature],
    ['Base URL', prompts.llm_base_url || '—'],
  ]);
  renderKvList('permissions-panel', [
    ['Desktop', d.permissions?.desktop_enabled ? '✓ habilitado' : '✗ apagado'],
    ['Guardia seguridad', d.permissions?.security_guard ? '✓ activo' : '✗ apagado'],
    ['Vigilancia', d.permissions?.security_watch ? '✓ activa' : '✗ apagada'],
    ['Solo voz', d.permissions?.confirm_voice_only ? 'sí' : 'no'],
    ['UI confirma', d.permissions?.confirm_ui_allowed ? 'sí' : 'no'],
    ['Face auth', d.permissions?.require_face_auth ? 'sí' : 'no'],
  ]);

  // System prompt
  if (d.system_prompt && !qs('#cfg-system-prompt').dataset.dirty) {
    qs('#cfg-system-prompt').value = d.system_prompt;
  }
}

// ---- RENDER HELPERS ----
function renderModeStats(mode) {
  const el = document.getElementById('mode-facts');
  el.innerHTML = '';
  [
    ['Entrada', mode.input || 'texto'],
    ['Voz', mode.voice ? 'activa' : 'apagada'],
    ['Visión', mode.vision ? 'activa' : 'apagada'],
    ['Desktop', mode.desktop ? 'activo' : 'apagado'],
  ].forEach(([k, v]) => {
    const d = document.createElement('div');
    d.className = 'stat-item';
    d.innerHTML = `<strong>${k}</strong><span>${v}</span>`;
    el.appendChild(d);
  });
}

function renderKvList(id, rows) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = '';
  rows.forEach(([k, v]) => {
    const row = document.createElement('div');
    row.className = 'kv-row';
    row.innerHTML = `<span>${k}</span><span>${escHtml(String(v ?? '—'))}</span>`;
    el.appendChild(row);
  });
}

function renderTasks(tasks) {
  const el = document.getElementById('task-list');
  if (!el) return;
  el.innerHTML = '';
  if (!tasks.length) {
    el.innerHTML = '<div class="task-item"><div class="task-item-info"><strong>Sin tareas guardadas</strong></div></div>';
    return;
  }
  tasks.forEach(t => {
    const item = document.createElement('div');
    item.className = 'task-item';
    item.innerHTML = `
      <div class="task-item-info">
        <strong>${escHtml(t.name || t)}</strong>
        <small>${t.step_count !== undefined ? t.step_count + ' pasos' : (t.description || '')}</small>
      </div>
      <div class="task-item-actions">
        <button class="btn-ghost-sm" data-run="${escHtml(t.name || t)}">Ejecutar</button>
        <button class="btn-ghost-sm" data-del="${escHtml(t.name || t)}">Borrar</button>
      </div>`;
    item.querySelector('[data-run]').addEventListener('click', () => sendCommand(`ejecuta tarea ${t.name || t}`));
    item.querySelector('[data-del]').addEventListener('click', () => sendCommand(`borra tarea ${t.name || t}`));
    el.appendChild(item);
  });
}

function renderCatalog(catalog) {
  renderCatalogList('plugin-list', catalog.plugins || []);
  renderCatalogList('extension-list', catalog.extensions || []);
}

function renderCatalogList(id, items) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = '';
  if (!items.length) {
    el.innerHTML = '<div class="catalog-item"><div class="catalog-item-info"><strong>Ninguno instalado</strong></div></div>';
    return;
  }
  items.forEach(p => {
    const item = document.createElement('div');
    item.className = 'catalog-item';
    item.innerHTML = `<div class="catalog-item-info"><strong>${escHtml(p.name || p.id)}</strong><small>${escHtml(p.description || p.version || '')}</small></div>`;
    el.appendChild(item);
  });
}

function renderRules(rules) {
  // Banned phrases list
  const bannedList = document.getElementById('banned-list');
  if (bannedList) {
    bannedList.innerHTML = '';
    (rules.banned_phrases || []).forEach(phrase => {
      const item = document.createElement('div');
      item.className = 'banned-item';
      item.innerHTML = `<span>${escHtml(phrase)}</span><button class="btn-ghost-sm" data-remove-phrase="${escHtml(phrase)}">✕</button>`;
      item.querySelector('button').addEventListener('click', () => sendCommand(`permite decir ${phrase}`));
      bannedList.appendChild(item);
    });
  }
  // Macros
  const macroList = document.getElementById('macro-list');
  if (macroList) {
    macroList.innerHTML = '';
    (rules.macros || []).forEach(m => {
      const item = document.createElement('div');
      item.className = 'macro-item';
      item.innerHTML = `<span>${escHtml(m.trigger)}</span><small>→ ${escHtml(m.action)}</small>`;
      macroList.appendChild(item);
    });
  }
}

function renderToggles(perms) {
  const grid = document.getElementById('toggle-grid');
  if (!grid) return;
  const defs = [
    ['YUI_DESKTOP_ENABLED', perms.desktop_enabled, 'Desktop', 'Automatización de escritorio'],
    ['YUI_SECURITY_GUARD', perms.security_guard, 'Guardia seguridad', 'Filtra URLs y comandos riesgosos'],
    ['YUI_SECURITY_WATCH_ENABLED', perms.security_watch, 'Vigilancia continua', 'Monitor de procesos y red'],
    ['YUI_CONFIRM_VOICE_ONLY', perms.confirm_voice_only, 'Confirmar solo por voz', 'Bloquea confirmación desde UI'],
    ['YUI_CONFIRM_UI_ALLOWED', perms.confirm_ui_allowed, 'Confirmar desde UI', 'Permite código por texto'],
    ['YUI_CONFIRM_TEXT_ARM_ENABLED', perms.confirm_text_arm_enabled, 'Armar texto', 'Activa 2FA por texto'],
    ['YUI_DESKTOP_CONFIRM_POINTER', perms.confirm_pointer, 'Confirmar mouse', 'Pide confirmación en clics'],
    ['YUI_MACROS_ENABLED', perms.macros_enabled, 'Macros de voz', 'Atajos de voz definidos por el usuario'],
    ['YUI_STYLE_ENABLED', perms.style_enabled, 'Reglas de estilo', 'Aplica restricciones de formato y frases'],
    ['YUI_TEACHING_MODE', perms.teaching_mode, 'Modo enseñanza', 'Aprende nuevas tareas paso a paso'],
  ];
  grid.innerHTML = '';
  defs.forEach(([key, enabled, label, desc]) => {
    const row = document.createElement('div');
    row.className = 'toggle-row';
    const uid = 'tog-' + key;
    row.innerHTML = `
      <div class="toggle-label">
        <strong>${label}</strong>
        <small>${key}</small>
      </div>
      <label class="toggle-switch">
        <input type="checkbox" id="${uid}" ${enabled ? 'checked' : ''}>
        <span class="toggle-track"></span>
      </label>`;
    row.querySelector('input').addEventListener('change', function () {
      setToggle(key, this.checked);
    });
    grid.appendChild(row);
  });
}

// ---- CONFIG TAB ----
let configDirty = false;

function fillConfigForm(prompts) {
  if (configDirty) return;
  const safe = (id, val) => { const el = qs('#' + id); if (el && val !== undefined) el.value = val; };
  safe('cfg-base-url', prompts.llm_base_url);
  safe('cfg-model-fast', prompts.llm_model_fast);
  safe('cfg-model-deep', prompts.llm_model_deep);
  safe('cfg-llm-mode', prompts.llm_mode || '');
  safe('cfg-temp-fast', prompts.llm_temperature);
  safe('cfg-temp-deep', prompts.llm_deep_temperature);
  safe('cfg-max-tokens', prompts.llm_max_tokens);
  safe('cfg-stt-lang', prompts.stt_language);
  safe('cfg-tts-engine', prompts.tts_engine);
  safe('cfg-wake-word', prompts.wake_word);
  updateSliderLabels();
}

function updateSliderLabels() {
  const ft = qs('#cfg-temp-fast');
  const dt = qs('#cfg-temp-deep');
  if (ft) qs('#temp-fast-val').textContent = parseFloat(ft.value).toFixed(2);
  if (dt) qs('#temp-deep-val').textContent = parseFloat(dt.value).toFixed(2);
}

qs('#cfg-temp-fast').addEventListener('input', updateSliderLabels);
qs('#cfg-temp-deep').addEventListener('input', updateSliderLabels);

// Mark dirty on any change
['cfg-base-url','cfg-api-key','cfg-model-fast','cfg-model-deep','cfg-llm-mode',
 'cfg-temp-fast','cfg-temp-deep','cfg-max-tokens','cfg-stt-lang','cfg-tts-engine','cfg-wake-word',
].forEach(id => {
  const el = qs('#' + id);
  if (el) el.addEventListener('input', () => { configDirty = true; });
});

// Toggle key visibility
qs('#toggle-key-visibility').addEventListener('click', function () {
  const inp = qs('#cfg-api-key');
  const hidden = inp.type === 'password';
  inp.type = hidden ? 'text' : 'password';
  this.textContent = hidden ? 'Ocultar' : 'Mostrar';
});

// Save config
qs('#save-config-btn').addEventListener('click', async () => {
  const payload = {
    YUI_LLM_BASE_URL: qs('#cfg-base-url').value.trim(),
    YUI_LLM_API_KEY: qs('#cfg-api-key').value.trim(),
    YUI_LLM_MODEL_FAST: qs('#cfg-model-fast').value.trim(),
    YUI_LLM_MODEL_DEEP: qs('#cfg-model-deep').value.trim(),
    YUI_LLM_MODE: qs('#cfg-llm-mode').value,
    YUI_LLM_TEMPERATURE: qs('#cfg-temp-fast').value,
    YUI_LLM_DEEP_TEMPERATURE: qs('#cfg-temp-deep').value,
    YUI_LLM_MAX_TOKENS: qs('#cfg-max-tokens').value,
    YUI_STT_LANGUAGE: qs('#cfg-stt-lang').value.trim(),
    YUI_TTS_ENGINE: qs('#cfg-tts-engine').value,
    YUI_WAKE_WORD: qs('#cfg-wake-word').value.trim(),
  };
  // Remove empty values so we don't overwrite with blanks
  Object.keys(payload).forEach(k => { if (!payload[k]) delete payload[k]; });

  showSaveResult('Guardando…', false, false);
  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.ok) {
      configDirty = false;
      showSaveResult('✓ Configuración guardada. Reinicia YUI para aplicar cambios de modelo/API.', false, true);
    } else {
      showSaveResult('✗ Error: ' + (data.error || 'desconocido'), true, true);
    }
  } catch (err) {
    showSaveResult('✗ Error de red: ' + err.message, true, true);
  }
});

function showSaveResult(msg, isError, visible) {
  const el = qs('#save-result');
  el.textContent = msg;
  el.className = 'save-result' + (isError ? ' error' : '');
  if (visible) el.classList.remove('hidden');
  else el.classList.add('hidden');
  if (visible && !isError) setTimeout(() => el.classList.add('hidden'), 5000);
}

// ---- PROMPTS TAB ----
qs('#cfg-system-prompt').addEventListener('input', function () {
  this.dataset.dirty = '1';
});

qs('#save-prompt-btn').addEventListener('click', async () => {
  const prompt = qs('#cfg-system-prompt').value.trim();
  if (!prompt) return;
  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ YUI_SYSTEM_PROMPT_OVERRIDE: prompt }),
    });
    const data = await res.json();
    if (data.ok) {
      delete qs('#cfg-system-prompt').dataset.dirty;
      addMsg('system', '✓ Prompt del sistema guardado. Reinicia YUI para aplicarlo.');
    }
  } catch (err) {
    addMsg('system', 'Error guardando prompt: ' + err.message);
  }
});

qs('#apply-style-btn').addEventListener('click', async () => {
  const max = qs('#style-max-sentences').value.trim();
  if (max) await sendCommand(`responde en ${max} frases`);
});

qs('#reset-style').addEventListener('click', () => sendCommand('reinicia estilo'));

qs('#add-ban-phrase').addEventListener('click', async () => {
  const phrase = qs('#style-ban-phrase').value.trim();
  if (!phrase) return;
  qs('#style-ban-phrase').value = '';
  await sendCommand(`no digas ${phrase}`);
  setTimeout(loadBootstrap, 400);
});

qs('#save-macro-btn').addEventListener('click', async () => {
  const trigger = qs('#macro-trigger').value.trim();
  const action = qs('#macro-action').value.trim();
  if (!trigger || !action) return;
  await sendCommand(`aprende comando ${trigger} => ${action}`);
  qs('#macro-trigger').value = '';
  qs('#macro-action').value = '';
  setTimeout(loadBootstrap, 400);
});

// ---- TASKS TAB ----
qs('#save-task-btn').addEventListener('click', async () => {
  const name = qs('#quick-task-name').value.trim().toLowerCase();
  const steps = qs('#quick-task-steps').value
    .split(/\r?\n/)
    .map(l => l.trim())
    .filter(Boolean);
  if (!name || !steps.length) return;
  await sendCommand(`aprende tarea ${name}`);
  for (const step of steps) await sendCommand(step);
  await sendCommand('termina aprendizaje');
  qs('#quick-task-name').value = '';
  qs('#quick-task-steps').value = '';
  setTimeout(loadBootstrap, 600);
});

// ---- SYSTEM TAB ----
qs('#refresh-state').addEventListener('click', loadBootstrap);

qs('#shutdown-btn').addEventListener('click', async () => {
  const btn = qs('#shutdown-btn');
  if (!confirm('¿Apagar YUI? El proceso se cerrará.')) return;
  btn.disabled = true;
  btn.textContent = 'Apagando…';
  try {
    await fetch('/api/shutdown', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  } catch (_) { /* proceso ya cerró */ }
});

// ---- BOOT ----
loadBootstrap().then(() => connectWs());
