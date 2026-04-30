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
    if (type === 'file_diff') {
      renderFileDiff(data, ts);
      return;
    }
    if (type === 'status') {
      qs('#agent-state').textContent = 'listo';
      qs('#avatar-ring').classList.remove('thinking');
      qs('#status-dot').className = 'status-dot';
    }
  });
}

// ---- FILE DIFF PANEL ----
function renderFileDiff(data, ts) {
  let parsed;
  try {
    parsed = typeof data.detail === 'string' ? JSON.parse(data.detail) : data.detail;
  } catch {
    return;
  }
  if (!parsed || !parsed.chunks) return;

  const path = parsed.path || data.tool || '?';
  const added = parsed.added || 0;
  const removed = parsed.removed || 0;
  const chunks = parsed.chunks || [];

  // Activity log — short summary
  addActivityLog('file', `${path.split(/[\\/]/).pop()}  +${added} -${removed}`, ts);

  // Inline diff card in chat
  const card = document.createElement('div');
  card.className = 'file-diff-card';

  // Build diff rows
  const rows = chunks.map(c => {
    const ln = escHtml(String(c.ln || ''));
    if (c.old !== null && c.new !== null && c.old !== c.new) {
      // changed line: show old (del) then new (add)
      return [
        `<tr class="diff-line-del"><td class="diff-ln">${ln}</td><td><span class="diff-sign">-</span>${escHtml(c.old ?? '')}</td></tr>`,
        `<tr class="diff-line-add"><td class="diff-ln">${ln}</td><td><span class="diff-sign">+</span>${escHtml(c.new ?? '')}</td></tr>`,
      ].join('');
    } else if (c.old === null) {
      return `<tr class="diff-line-add"><td class="diff-ln">${ln}</td><td><span class="diff-sign">+</span>${escHtml(c.new ?? '')}</td></tr>`;
    } else if (c.new === null) {
      return `<tr class="diff-line-del"><td class="diff-ln">${ln}</td><td><span class="diff-sign">-</span>${escHtml(c.old ?? '')}</td></tr>`;
    }
    return '';
  }).join('');

  const bodyId = 'diff-body-' + Date.now();
  card.innerHTML = `
    <div class="file-diff-header" onclick="toggleDiffBody('${bodyId}')">
      <span class="file-diff-path" title="${escHtml(path)}">${escHtml(path)}</span>
      <div class="file-diff-stats">
        <span class="diff-stat-add">+${added}</span>
        <span class="diff-stat-del">-${removed}</span>
      </div>
      <span class="file-diff-toggle" id="toggle-lbl-${bodyId}">mostrar</span>
    </div>
    <div class="file-diff-body collapsed" id="${bodyId}">
      <table class="diff-table"><tbody>${rows || '<tr><td colspan="2" style="color:var(--text-muted);padding:8px">sin cambios detectados</td></tr>'}</tbody></table>
    </div>`;
  chatArea.appendChild(card);
  scrollChat();
}

function toggleDiffBody(id) {
  const body = document.getElementById(id);
  const lbl = document.getElementById('toggle-lbl-' + id);
  if (!body) return;
  const collapsed = body.classList.toggle('collapsed');
  if (lbl) lbl.textContent = collapsed ? 'mostrar' : 'ocultar';
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

qs('#cfg-temp-fast')?.addEventListener('input', updateSliderLabels);
qs('#cfg-temp-deep')?.addEventListener('input', updateSliderLabels);

// Mark dirty on any change
['cfg-base-url','cfg-api-key','cfg-model-fast','cfg-model-deep','cfg-llm-mode',
 'cfg-temp-fast','cfg-temp-deep','cfg-max-tokens','cfg-stt-lang','cfg-tts-engine','cfg-wake-word',
].forEach(id => {
  const el = qs('#' + id);
  if (el) el.addEventListener('input', () => { configDirty = true; });
});

// Toggle key visibility
qs('#toggle-key-visibility')?.addEventListener('click', function () {
  const inp = qs('#cfg-api-key');
  const hidden = inp.type === 'password';
  inp.type = hidden ? 'text' : 'password';
  this.textContent = hidden ? 'Ocultar' : 'Mostrar';
});

// Save config
qs('#save-config-btn')?.addEventListener('click', async () => {
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
    const res = await fetch('/api/prompt', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'set_prompt', prompt }),
    });
    const data = await res.json();
    const msg = qs('#prompt-save-msg');
    if (data.ok) {
      delete qs('#cfg-system-prompt').dataset.dirty;
      msg.textContent = '✓ Guardado';
      msg.className = 'save-msg';
    } else {
      msg.textContent = '✗ Error: ' + (data.error || '?');
      msg.className = 'save-msg error';
    }
    msg.classList.remove('hidden');
    setTimeout(() => msg.classList.add('hidden'), 3000);
  } catch (err) {
    addMsg('system', 'Error guardando prompt: ' + err.message);
  }
});

qs('#reset-prompt-btn').addEventListener('click', async () => {
  if (!confirm('¿Resetear al prompt por defecto?')) return;
  await fetch('/api/prompt', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'reset_prompt' }) });
  await loadPromptRules();
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

// ══════════════════════════════════════════════════════════
// VOZ — grabación, transcripción y habla continua
// ══════════════════════════════════════════════════════════
const VoiceUI = (() => {
  let mediaRecorder = null;
  let audioChunks = [];
  let stream = null;
  let mode = 'idle';          // 'idle' | 'recording' | 'continuous'
  let continuousLoop = false;
  let holdTimer = null;

  const micBtn   = qs('#mic-btn');
  const voiceBar = qs('#voice-bar');
  const statusTx = qs('#voice-status-text');
  const stopBtn  = qs('#voice-stop-btn');

  function setStatus(text, barMode) {
    if (statusTx) statusTx.textContent = text;
    if (voiceBar) {
      voiceBar.classList.remove('hidden', 'continuous');
      if (barMode === 'hidden') { voiceBar.classList.add('hidden'); return; }
      if (barMode === 'continuous') voiceBar.classList.add('continuous');
    }
  }

  function setMicState(s) {
    mode = s;
    micBtn.classList.remove('recording', 'continuous');
    if (s === 'recording')  micBtn.classList.add('recording');
    if (s === 'continuous') micBtn.classList.add('continuous');
  }

  async function getStream() {
    if (stream && stream.active) return stream;
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    return stream;
  }

  async function startRecording() {
    try {
      const s = await getStream();
      audioChunks = [];
      mediaRecorder = new MediaRecorder(s);
      mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
      mediaRecorder.start();
      setMicState('recording');
      setStatus('Escuchando…', 'normal');
    } catch (err) {
      console.error('[YUI voz] No se pudo acceder al micrófono:', err);
      setStatus('Micrófono no disponible', 'hidden');
    }
  }

  async function stopAndSend() {
    if (!mediaRecorder || mediaRecorder.state === 'inactive') return;
    return new Promise(resolve => {
      mediaRecorder.onstop = async () => {
        const blob = new Blob(audioChunks, { type: 'audio/webm' });
        audioChunks = [];
        setStatus('Transcribiendo…', 'normal');
        try {
          const lang = (S.bootstrap?.settings?.stt_language || 'es').split('-')[0];
          const res = await fetch('/api/voice', {
            method: 'POST',
            headers: { 'Content-Type': 'audio/webm', 'X-Language': lang },
            body: blob,
          });
          const data = await res.json();
          if (data.text) {
            // Mostrar el texto transcrito en el input brevemente antes de enviar
            const inp = qs('#command-input');
            if (inp) inp.value = data.text;
            await sendCommand(data.text);
            if (inp) inp.value = '';
          } else {
            setStatus('No entendí. Intenta de nuevo.', 'normal');
          }
        } catch (e) {
          console.error('[YUI voz] Error enviando audio:', e);
          setStatus('Error de red', 'normal');
        }
        resolve();
      };
      mediaRecorder.stop();
    });
  }

  // ── Modo clic simple: grabar y enviar ────────────────────
  async function toggleRecording() {
    if (mode === 'recording') {
      await stopAndSend();
      setMicState('idle');
      setStatus('', 'hidden');
    } else if (mode === 'idle') {
      await startRecording();
    }
  }

  // ── Modo habla continua: escucha → envía → escucha → … ──
  async function startContinuous() {
    continuousLoop = true;
    setMicState('continuous');
    setStatus('Habla continua activa — escuchando…', 'continuous');
    while (continuousLoop) {
      await startRecording();
      // Graba hasta que haya 2.5s de silencio (MediaRecorder no tiene VAD nativo;
      // usamos un timeout fijo de 6s como aproximación razonable).
      await new Promise(r => setTimeout(r, 6000));
      if (!continuousLoop) break;
      setMicState('continuous');   // mantener el estado visual
      await stopAndSend();
      if (!continuousLoop) break;
      setStatus('Habla continua — escuchando…', 'continuous');
      await new Promise(r => setTimeout(r, 400));  // pequeña pausa entre turnos
    }
    stopContinuous();
  }

  function stopContinuous() {
    continuousLoop = false;
    if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
    setMicState('idle');
    setStatus('', 'hidden');
  }

  // ── Eventos del botón ─────────────────────────────────────
  micBtn.addEventListener('mousedown', () => {
    // Detectar mantener pulsado (>700ms) → habla continua
    holdTimer = setTimeout(() => {
      holdTimer = null;
      if (mode === 'continuous') { stopContinuous(); return; }
      if (mode === 'recording') { stopAndSend().then(() => { setMicState('idle'); setStatus('', 'hidden'); }); return; }
      startContinuous();
    }, 700);
  });

  micBtn.addEventListener('mouseup', () => {
    if (holdTimer !== null) {
      clearTimeout(holdTimer);
      holdTimer = null;
      // Clic corto: toggle grabación simple
      toggleRecording();
    }
  });

  micBtn.addEventListener('mouseleave', () => {
    if (holdTimer !== null) { clearTimeout(holdTimer); holdTimer = null; }
  });

  // Touch para móvil
  micBtn.addEventListener('touchstart', e => { e.preventDefault(); micBtn.dispatchEvent(new MouseEvent('mousedown')); });
  micBtn.addEventListener('touchend',   e => { e.preventDefault(); micBtn.dispatchEvent(new MouseEvent('mouseup')); });

  // Botón detener en la barra
  stopBtn.addEventListener('click', () => {
    if (mode === 'continuous') { stopContinuous(); return; }
    if (mode === 'recording')  { stopAndSend().then(() => { setMicState('idle'); setStatus('', 'hidden'); }); }
  });

  return { startContinuous, stopContinuous, toggleRecording };
})();

// ════════════════════════════════════════════════════════════════════════════
// PROVIDERS UI
// ════════════════════════════════════════════════════════════════════════════
const ProvidersUI = (() => {
  let _providers = [];
  let _editingId = null;

  const api = (action, body = {}) =>
    fetch('/api/providers', { method: action === 'list' ? 'GET' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: action === 'list' ? undefined : JSON.stringify({ action, ...body }),
    }).then(r => r.json());

  const fetchModelsApi = (id) =>
    fetch('/api/providers/fetch-models', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }),
    }).then(r => r.json());

  function renderCascadeFlow(providers) {
    const el = qs('#cascade-flow');
    if (!providers.length) { el.innerHTML = '<span style="color:var(--text-muted);font-size:.85rem">Sin proveedores configurados.</span>'; return; }
    el.innerHTML = providers.map((p, i) => `
      <div class="cascade-node">
        <div>
          <div class="cascade-box ${p.active ? 'active' : ''}">${p.name}</div>
          <span class="cascade-label">${p.backend === 'local' ? 'local' : 'api'}</span>
        </div>
        ${i < providers.length - 1 ? '<span class="cascade-arrow" title="si rechaza → siguiente">→</span>' : ''}
      </div>`).join('');
  }

  function renderProviders(providers) {
    _providers = providers;
    const el = qs('#providers-list');
    if (!providers.length) {
      el.innerHTML = '<p style="color:var(--text-muted);padding:.5rem 0">No hay proveedores. Agrega uno con el botón de arriba.</p>';
      renderCascadeFlow([]);
      return;
    }
    el.innerHTML = providers.map(p => `
      <div class="provider-card ${p.active ? 'active' : ''}" data-id="${p.id}">
        <div class="provider-order-badge">${p.cascade_order}</div>
        <div class="provider-info">
          <div class="provider-name">
            ${p.name}
            <span class="provider-active-badge">activo</span>
            <span style="font-size:.7rem;color:var(--text-muted);font-weight:400">${p.backend === 'local' ? '⬡ local' : '⬡ api'}</span>
          </div>
          <div class="provider-meta">
            ${p.backend === 'local'
              ? `${p.local_type} · ${p.local_model || 'sin modelo'} · ${p.local_url || 'localhost:11434'}`
              : `${p.base_url || '—'} · fast: ${p.model_fast || '—'} · deep: ${p.model_deep || '—'}`}
          </div>
          <div class="provider-strengths">
            ${(p.strengths || []).map(s => `<span class="strength-tag">${s}</span>`).join('')}
          </div>
        </div>
        <div class="provider-actions">
          ${!p.active ? `<button class="btn-accent" data-action="activate" data-id="${p.id}">Activar</button>` : ''}
          <button class="btn-ghost-sm" data-action="edit" data-id="${p.id}">Editar</button>
          <button class="btn-ghost-sm" style="color:var(--accent-red)" data-action="delete" data-id="${p.id}">✕</button>
        </div>
      </div>`).join('');
    renderCascadeFlow(providers);
  }

  async function loadProviders() {
    const data = await api('list');
    if (data.ok) renderProviders(data.providers || []);
  }

  function showForm(provider = null) {
    _editingId = provider ? provider.id : null;
    qs('#provider-form-title').textContent = provider ? 'Editar proveedor' : 'Nuevo proveedor';
    qs('#pf-name').value = provider?.name || '';
    qs('#pf-backend').value = provider?.backend || 'openai_compat';
    qs('#pf-order').value = provider?.cascade_order || (_providers.length + 1);
    qs('#pf-strengths').value = (provider?.strengths || ['general']).join(',');
    qs('#pf-timeout').value = provider?.timeout_s || 0;
    qs('#pf-base-url').value = provider?.base_url || '';
    qs('#pf-api-key').value = provider?.api_key || '';
    qs('#pf-model-fast').value = provider?.model_fast || '';
    qs('#pf-model-deep').value = provider?.model_deep || '';
    qs('#pf-local-type').value = provider?.local_type || 'ollama';
    qs('#pf-local-model').value = provider?.local_model || '';
    qs('#pf-local-url').value = provider?.local_url || 'http://localhost:11434';
    qs('#pf-n-ctx').value = provider?.local_n_ctx || 4096;
    qs('#pf-n-gpu').value = provider?.local_n_gpu_layers || 0;
    updateBackendCols();
    qs('#provider-form-wrap').classList.remove('hidden');
    qs('#pf-status').classList.add('hidden');
    qs('#pf-name').focus();
  }

  function hideForm() {
    qs('#provider-form-wrap').classList.add('hidden');
    _editingId = null;
  }

  function updateBackendCols() {
    const isLocal = qs('#pf-backend').value === 'local';
    qs('#pf-col-api').classList.toggle('hidden', isLocal);
    qs('#pf-col-local').classList.toggle('hidden', !isLocal);
  }

  function populateModelsList(models) {
    const dl = qs('#pf-models-list');
    dl.innerHTML = models.map(m => `<option value="${m}">`).join('');
  }

  async function fetchModelsForForm() {
    if (_editingId) {
      const data = await fetchModelsApi(_editingId);
      if (data.ok && data.models.length) { populateModelsList(data.models); return; }
    }
    // Sin ID guardado: hacer fetch ad-hoc con los datos del form
    const isLocal = qs('#pf-backend').value === 'local';
    const body = isLocal
      ? { id: '__preview__', backend: 'local', local_type: qs('#pf-local-type').value,
          local_url: qs('#pf-local-url').value }
      : { id: '__preview__', backend: 'openai_compat',
          base_url: qs('#pf-base-url').value, api_key: qs('#pf-api-key').value };
    // Crear proveedor temporal, fetch, eliminar
    const addRes = await api('add', body);
    if (!addRes.ok) return;
    const tmpId = addRes.provider.id;
    const modelsRes = await fetchModelsApi(tmpId);
    await api('delete', { id: tmpId });
    if (modelsRes.ok && modelsRes.models.length) populateModelsList(modelsRes.models);
  }

  async function saveProvider() {
    const isLocal = qs('#pf-backend').value === 'local';
    const data = {
      name: qs('#pf-name').value.trim(),
      backend: qs('#pf-backend').value,
      cascade_order: parseInt(qs('#pf-order').value) || 1,
      strengths: qs('#pf-strengths').value.split(',').map(s => s.trim()).filter(Boolean),
      timeout_s: parseFloat(qs('#pf-timeout').value) || 0,
      base_url: qs('#pf-base-url').value.trim(),
      api_key: qs('#pf-api-key').value,
      model_fast: qs('#pf-model-fast').value.trim(),
      model_deep: qs('#pf-model-deep').value.trim(),
      local_type: qs('#pf-local-type').value,
      local_model: qs('#pf-local-model').value.trim(),
      local_url: qs('#pf-local-url').value.trim(),
      local_n_ctx: parseInt(qs('#pf-n-ctx').value) || 4096,
      local_n_gpu_layers: parseInt(qs('#pf-n-gpu').value) || 0,
    };
    if (!data.name) { alert('El nombre es requerido'); return; }
    const action = _editingId ? 'update' : 'add';
    if (_editingId) data.id = _editingId;
    const res = await api(action, data);
    const msg = qs('#pf-status');
    if (res.ok) {
      msg.textContent = '✓ Guardado';
      msg.className = 'save-msg';
      msg.classList.remove('hidden');
      await loadProviders();
      setTimeout(() => hideForm(), 800);
    } else {
      msg.textContent = '✗ ' + (res.error || 'Error');
      msg.className = 'save-msg error';
      msg.classList.remove('hidden');
    }
  }

  // Events
  qs('#add-provider-btn').addEventListener('click', () => showForm());
  qs('#pf-cancel-btn').addEventListener('click', hideForm);
  qs('#pf-save-btn').addEventListener('click', saveProvider);
  qs('#pf-backend').addEventListener('change', updateBackendCols);
  qs('#pf-toggle-key').addEventListener('click', () => {
    const inp = qs('#pf-api-key');
    inp.type = inp.type === 'password' ? 'text' : 'password';
  });
  qs('#pf-fetch-models').addEventListener('click', fetchModelsForForm);
  qs('#pf-fetch-local-models').addEventListener('click', fetchModelsForForm);

  qs('#providers-list').addEventListener('click', async e => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const { action, id } = btn.dataset;
    if (action === 'activate') {
      await api('set_active', { id });
      await loadProviders();
    } else if (action === 'edit') {
      const p = _providers.find(x => x.id === id);
      if (p) showForm(p);
    } else if (action === 'delete') {
      if (!confirm('¿Eliminar este proveedor?')) return;
      await api('delete', { id });
      await loadProviders();
    }
  });

  // Load on tab switch
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.dataset.tab === 'providers') loadProviders();
    });
  });

  return { loadProviders };
})();

// ════════════════════════════════════════════════════════════════════════════
// PROMPT & RULES UI
// ════════════════════════════════════════════════════════════════════════════
async function loadPromptRules() {
  try {
    const data = await fetch('/api/prompt').then(r => r.json());
    if (!data.ok) return;
    qs('#cfg-system-prompt').value = data.system_prompt || '';
    renderRules(data.rules || []);
  } catch (_) {}
}

function renderRules(rules) {
  const el = qs('#rules-list');
  el.innerHTML = rules.map((r, i) => `
    <div class="rule-item" data-idx="${i}">
      <span class="rule-item-text">${r.replace(/</g,'&lt;')}</span>
      <div class="rule-item-actions">
        <button class="btn-ghost-sm" data-rule-action="edit" data-idx="${i}">✎</button>
        <button class="btn-ghost-sm" style="color:var(--accent-red)" data-rule-action="delete" data-idx="${i}">✕</button>
      </div>
    </div>`).join('') || '<p style="color:var(--text-muted);font-size:.85rem">Sin reglas configuradas.</p>';
}

qs('#rules-list').addEventListener('click', async e => {
  const btn = e.target.closest('[data-rule-action]');
  if (!btn) return;
  const { ruleAction, idx } = btn.dataset;
  const action = btn.getAttribute('data-rule-action');
  const index = parseInt(btn.getAttribute('data-idx'));
  if (action === 'delete') {
    const res = await fetch('/api/prompt', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'remove_rule', index }) }).then(r => r.json());
    if (res.ok) renderRules(res.rules || []);
  } else if (action === 'edit') {
    const span = btn.closest('.rule-item').querySelector('.rule-item-text');
    const current = span.textContent;
    const input = document.createElement('input');
    input.value = current;
    span.replaceWith(input);
    input.focus();
    input.addEventListener('blur', async () => {
      const res = await fetch('/api/prompt', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'update_rule', index, rule: input.value }) }).then(r => r.json());
      if (res.ok) renderRules(res.rules || []);
    });
  }
});

qs('#add-rule-btn').addEventListener('click', async () => {
  const inp = qs('#new-rule-input');
  const rule = inp.value.trim();
  if (!rule) return;
  const res = await fetch('/api/prompt', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'add_rule', rule }) }).then(r => r.json());
  if (res.ok) { renderRules(res.rules || []); inp.value = ''; }
});

qs('#new-rule-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') qs('#add-rule-btn').click();
});

qs('#reset-rules-btn').addEventListener('click', async () => {
  if (!confirm('¿Resetear rules al valor por defecto?')) return;
  const res = await fetch('/api/prompt', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'reset_rules' }) }).then(r => r.json());
  if (res.ok) renderRules(res.rules || []);
});

// Cargar prompt+rules al abrir el tab
document.querySelectorAll('.nav-item').forEach(btn => {
  btn.addEventListener('click', () => {
    if (btn.dataset.tab === 'prompts') loadPromptRules();
  });
});
