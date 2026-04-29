// @ts-check
'use strict';

const vscode = require('vscode');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

/** @type {vscode.WebviewView | undefined} */
let chatView;
/** @type {import('child_process').ChildProcess | undefined} */
let yuiProcess;
/** @type {vscode.OutputChannel} */
let outputChannel;

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
  outputChannel = vscode.window.createOutputChannel('YUI');
  context.subscriptions.push(outputChannel);

  const provider = new YuiChatViewProvider(context);

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider('yui.chatView', provider, {
      webviewOptions: { retainContextWhenHidden: true },
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('yui.openChat', () => {
      vscode.commands.executeCommand('yui.chatView.focus');
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('yui.startServer', () => startYui(context))
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('yui.stopServer', stopYui)
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('yui.sendSelection', () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) return;
      const selection = editor.document.getText(editor.selection);
      if (!selection.trim()) return;
      const lang = editor.document.languageId;
      const msg = `\`\`\`${lang}\n${selection}\n\`\`\``;
      provider.sendToWebview({ type: 'inject_text', text: msg });
    })
  );

  const cfg = vscode.workspace.getConfiguration('yui');
  if (cfg.get('autoStart')) startYui(context);
}

function deactivate() {
  stopYui();
}

/**
 * @param {vscode.ExtensionContext} context
 */
function startYui(context) {
  if (yuiProcess) {
    vscode.window.showInformationMessage('YUI ya está corriendo.');
    return;
  }

  // Read yui-specific settings only (never inherit from python extension).
  const yuiCfg = vscode.workspace.getConfiguration('yui');
  const pythonExe = String(yuiCfg.get('pythonPath') || '').trim() || 'python';
  const yuiPathCfg = String(yuiCfg.get('yuiPath') || '').trim();

  // Find YUI root: explicit setting → workspace folder with main.py → two levels up from extension.
  let yuiRoot = yuiPathCfg;
  if (!yuiRoot) {
    for (const f of (vscode.workspace.workspaceFolders || [])) {
      if (fs.existsSync(path.join(f.uri.fsPath, 'main.py'))) {
        yuiRoot = f.uri.fsPath;
        break;
      }
    }
  }
  if (!yuiRoot) {
    const up2 = path.join(context.extensionPath, '..', '..');
    yuiRoot = fs.existsSync(path.join(up2, 'main.py')) ? up2 : context.extensionPath;
  }

  const mainPy = path.join(yuiRoot, 'main.py');
  const lockPath = path.join(yuiRoot, 'data', 'yui.lock');

  outputChannel.appendLine(`[YUI] python  : ${pythonExe}`);
  outputChannel.appendLine(`[YUI] main.py : ${mainPy}`);
  outputChannel.show(true);

  if (!fs.existsSync(mainPy)) {
    vscode.window.showErrorMessage(`YUI: no se encontró main.py en "${yuiRoot}". Configura yui.yuiPath.`);
    return;
  }

  // Kill stale Python, remove lock, then spawn after a short delay.
  try { require('child_process').execSync('taskkill /f /im python.exe', { stdio: 'ignore' }); } catch (_) {}
  setTimeout(() => {
    try { fs.unlinkSync(lockPath); } catch (_) {}

    let stderrBuf = '';
    yuiProcess = spawn(pythonExe, [mainPy], { cwd: yuiRoot, stdio: ['ignore', 'pipe', 'pipe'] });

  yuiProcess.stdout?.on('data', (data) => {
    const text = data.toString();
    outputChannel.append(text);
    if (chatView) chatView.webview.postMessage({ type: 'server_log', text });
  });

  yuiProcess.stderr?.on('data', (data) => {
    const text = data.toString();
    stderrBuf += text;
    outputChannel.append('[ERR] ' + text);
  });

  yuiProcess.on('exit', (code) => {
    outputChannel.appendLine(`[YUI] Proceso terminó con código: ${code}`);
    yuiProcess = undefined;
    if (chatView) chatView.webview.postMessage({ type: 'server_stopped' });
    if (code !== 0 && code !== null) {
      const snippet = stderrBuf.slice(-600).trim() || '(sin salida de error)';
      vscode.window.showErrorMessage(`YUI se cerró (código ${code}). Ver panel "YUI" en Output.`);
    }
  });

  yuiProcess.on('error', (err) => {
    outputChannel.appendLine(`[YUI] Error al iniciar: ${err.message}`);
    yuiProcess = undefined;
    vscode.window.showErrorMessage(`YUI no pudo iniciar: ${err.message}\nVerifica que python esté en PATH o configura yui.pythonPath.`);
    if (chatView) chatView.webview.postMessage({ type: 'server_stopped' });
  });

    vscode.window.showInformationMessage(`YUI iniciando desde: ${yuiRoot}`);
    if (chatView) chatView.webview.postMessage({ type: 'server_started' });
  }, 1200);
}

function stopYui() {
  if (yuiProcess) {
    yuiProcess.kill();
    yuiProcess = undefined;
  }
}

class YuiChatViewProvider {
  /** @param {vscode.ExtensionContext} context */
  constructor(context) {
    this._context = context;
  }

  /**
   * @param {vscode.WebviewView} webviewView
   */
  resolveWebviewView(webviewView) {
    chatView = webviewView;
    const wv = webviewView.webview;

    wv.options = {
      enableScripts: true,
      localResourceRoots: [
        vscode.Uri.joinPath(this._context.extensionUri, 'src', 'webview'),
      ],
    };

    wv.html = this._getHtml(wv);

    wv.onDidReceiveMessage((msg) => this._handleMessage(msg, wv));
  }

  /** @param {any} msg */
  sendToWebview(msg) {
    chatView?.webview.postMessage(msg);
  }

  /**
   * @param {any} msg
   * @param {vscode.Webview} wv
   */
  _handleMessage(msg, wv) {
    const cfg = vscode.workspace.getConfiguration('yui');
    const port = cfg.get('httpPort') || 8080;
    const base = `http://127.0.0.1:${port}`;

    switch (msg.type) {
      case 'send_command': {
        const folders = vscode.workspace.workspaceFolders;
        const workspaceRoot = folders && folders.length > 0 ? folders[0].uri.fsPath : '';
        fetch(`${base}/api/command`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: msg.text, workspace_root: workspaceRoot }),
        }).catch(() => {});
        break;
      }

      case 'toggle':
        fetch(`${base}/api/toggle`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key: msg.key, value: msg.value }),
        }).catch(() => {});
        break;

      case 'save_config':
        fetch(`${base}/api/config`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(msg.payload),
        }).catch(() => {});
        break;

      case 'start_server':
        startYui(this._context);
        break;

      case 'stop_server':
        stopYui();
        break;

      case 'get_vscode_config': {
        const vsConfig = {
          httpPort: cfg.get('httpPort'),
          wsPort: cfg.get('wsPort'),
        };
        wv.postMessage({ type: 'vscode_config', config: vsConfig });
        break;
      }
    }
  }

  /** @param {vscode.Webview} wv */
  _getHtml(wv) {
    const base = vscode.Uri.joinPath(this._context.extensionUri, 'src', 'webview');
    const cssUri = wv.asWebviewUri(vscode.Uri.joinPath(base, 'panel.css'));
    const jsUri = wv.asWebviewUri(vscode.Uri.joinPath(base, 'panel.js'));
    const nonce = getNonce();

    return /* html */ `<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <meta http-equiv="Content-Security-Policy"
    content="default-src 'none';
             style-src ${wv.cspSource} 'unsafe-inline';
             script-src 'nonce-${nonce}';
             connect-src http://127.0.0.1:* ws://127.0.0.1:*;
             img-src ${wv.cspSource} data:;
             font-src ${wv.cspSource};">
  <link rel="stylesheet" href="${cssUri}"/>
  <title>YUI</title>
</head>
<body>
  <div id="app">
    <div id="topbar">
      <div id="brand">
        <span class="logo">✦</span>
        <span class="brand-name">YUI</span>
      </div>
      <div id="status-row">
        <span id="status-dot" class="dot disconnected"></span>
        <span id="status-label">Sin conexión</span>
        <span id="mode-badge" class="badge" style="display:none"></span>
      </div>
      <div id="tabs">
        <button class="tab active" data-tab="chat">Chat</button>
        <button class="tab" data-tab="config">Config</button>
        <button class="tab" data-tab="plugins">Plugins</button>
      </div>
    </div>

    <!-- CHAT PANEL -->
    <div id="panel-chat" class="panel active">
      <div id="messages"></div>
      <div id="thinking-bar" style="display:none">
        <span class="dot-pulse"></span>
        <span id="thinking-label">YUI está pensando…</span>
      </div>
      <div id="steps-panel" style="display:none"></div>
      <div id="diff-feed"></div>
      <div id="task-dialog" style="display:none">
        <div class="task-dialog-body">
          <div class="task-dialog-icon">✦</div>
          <div id="task-dialog-summary" class="task-dialog-summary"></div>
          <div class="task-dialog-actions">
            <button id="task-btn-approve" class="btn-task-approve">Aprobar</button>
            <button id="task-btn-deny" class="btn-task-deny">Denegar</button>
            <button id="task-btn-auto" class="btn-task-auto">Auto-editar</button>
          </div>
        </div>
      </div>
      <div id="confirm-banner" style="display:none">
        <div class="confirm-inner">
          <span id="confirm-desc"></span>
          <span id="confirm-timer" class="badge"></span>
        </div>
        <div class="confirm-row">
          <button id="confirm-yes-btn">✓ Aceptar</button>
          <button id="confirm-no-btn">✗ Cancelar</button>
          <input id="confirm-input" type="text" maxlength="6" placeholder="Código (opcional)"/>
          <button id="confirm-btn" style="display:none">Confirmar</button>
        </div>
      </div>
      <div id="composer">
        <textarea id="msg-input" rows="1" placeholder="Mensaje para YUI… (Enter para enviar)"></textarea>
        <!-- Mic: clic = grabar+enviar | mantener 700ms = habla continua -->
        <button id="mic-btn" aria-label="Grabar voz" title="Clic: grabar | Mantener: habla continua">
          <svg id="mic-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="2" width="6" height="12" rx="3"/>
            <path d="M19 10a7 7 0 0 1-14 0"/>
            <line x1="12" y1="19" x2="12" y2="22"/>
            <line x1="8" y1="22" x2="16" y2="22"/>
          </svg>
        </button>
        <button id="send-btn" aria-label="Enviar">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
            <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </div>
      <!-- Barra de estado de voz -->
      <div id="voice-bar" class="voice-bar hidden">
        <div class="voice-wave"><span></span><span></span><span></span><span></span><span></span></div>
        <span id="voice-status-text">Escuchando…</span>
        <button id="voice-stop-btn">&#9632; Detener</button>
      </div>
    </div>

    <!-- CONFIG PANEL -->
    <div id="panel-config" class="panel">
      <div class="section-title">Servidor YUI</div>
      <div class="btn-row">
        <button id="btn-start" class="btn-primary">▶ Iniciar</button>
        <button id="btn-stop" class="btn-danger">■ Detener</button>
        <button id="btn-shutdown" class="btn-danger" title="Apagar YUI limpiamente desde la API">⏻ Apagar</button>
      </div>
      <div class="section-title" style="margin-top:16px">LLM</div>
      <label class="field-label">Base URL</label>
      <input class="field-input" id="cfg-base-url" type="text" placeholder="https://api.openai.com/v1"/>
      <label class="field-label">API Key</label>
      <input class="field-input" id="cfg-api-key" type="password" placeholder="sk-..."/>
      <label class="field-label">Modelo (fast)</label>
      <select class="field-input" id="cfg-model-fast">
        <option value="mimo-v2.5-pro">mimo-v2.5-pro</option>
        <option value="mimo-v2.5">mimo-v2.5</option>
        <option value="gpt-4o-mini">gpt-4o-mini</option>
        <option value="gpt-4o">gpt-4o</option>
      </select>
      <label class="field-label">Modelo (deep)</label>
      <select class="field-input" id="cfg-model-deep">
        <option value="mimo-v2.5-pro">mimo-v2.5-pro</option>
        <option value="mimo-v2.5">mimo-v2.5</option>
        <option value="gpt-4o">gpt-4o</option>
        <option value="gpt-4o-mini">gpt-4o-mini</option>
      </select>
      <label class="field-label">Modo LLM</label>
      <select class="field-input" id="cfg-llm-mode">
        <option value="auto">Auto</option>
        <option value="fast">Fast</option>
        <option value="deep">Deep</option>
      </select>
      <label class="field-label">Temperatura</label>
      <input class="field-input" id="cfg-temperature" type="number" step="0.05" min="0" max="2" placeholder="0.4"/>
      <label class="field-label">Max tokens</label>
      <input class="field-input" id="cfg-max-tokens" type="number" step="10" min="64" placeholder="240"/>
      <label class="field-label">Idioma STT</label>
      <select class="field-input" id="cfg-stt-lang">
        <option value="es-CR">Español — Costa Rica (es-CR)</option>
        <option value="es-MX">Español — México (es-MX)</option>
        <option value="es-ES">Español — España (es-ES)</option>
        <option value="es-AR">Español — Argentina (es-AR)</option>
        <option value="es-CO">Español — Colombia (es-CO)</option>
        <option value="en-US">English — US (en-US)</option>
        <option value="en-GB">English — UK (en-GB)</option>
        <option value="pt-BR">Português — Brasil (pt-BR)</option>
        <option value="fr-FR">Français — France (fr-FR)</option>
        <option value="de-DE">Deutsch — Deutschland (de-DE)</option>
        <option value="zh-CN">中文 — 中国 (zh-CN)</option>
        <option value="ja-JP">日本語 — 日本 (ja-JP)</option>
      </select>
      <label class="field-label">Motor TTS</label>
      <select class="field-input" id="cfg-tts">
        <option value="edge">edge</option>
        <option value="pyttsx3">pyttsx3</option>
        <option value="gtts">gtts</option>
      </select>
      <button id="btn-save-config" class="btn-primary" style="margin-top:12px;width:100%">Guardar config</button>

      <div class="section-title" style="margin-top:20px">Modo del agente</div>
      <div id="mode-btns" class="btn-row" style="gap:6px">
        <button class="btn-mode" data-mode="fast">Chat</button>
        <button class="btn-mode" data-mode="auto">Auto</button>
        <button class="btn-mode" data-mode="deep">Deep</button>
      </div>
      <div class="toggle-row" style="margin-top:10px">
        <span>Full Access (desktop)</span>
        <label class="switch"><input type="checkbox" data-key="YUI_DESKTOP_ENABLED" id="tog-desktop"/><span class="slider"></span></label>
      </div>
      <div class="toggle-row">
        <span>Solo texto (sin voz/cámara)</span>
        <label class="switch"><input type="checkbox" data-key="YUI_AGENT_TEXT_ONLY" id="tog-text-only"/><span class="slider"></span></label>
      </div>

      <div class="section-title" style="margin-top:20px">Conversación</div>
      <div class="btn-row" style="gap:6px">
        <button id="btn-compact" class="btn-secondary" style="flex:1">Compactar tokens</button>
        <button id="btn-clear-chat" class="btn-danger" style="flex:1">Limpiar todo</button>
      </div>

      <div class="section-title" style="margin-top:20px">Permisos</div>
      <div class="toggle-row">
        <span>Seguridad</span>
        <label class="switch"><input type="checkbox" data-key="YUI_SECURITY_GUARD" id="tog-security"/><span class="slider"></span></label>
      </div>
      <div class="toggle-row">
        <span>Confirmar por UI</span>
        <label class="switch"><input type="checkbox" data-key="YUI_CONFIRM_UI_ALLOWED" id="tog-confirm-ui"/><span class="slider"></span></label>
      </div>
    </div>

    <!-- PLUGINS PANEL -->
    <div id="panel-plugins" class="panel">
      <div class="section-title">Plugins instalados</div>
      <div id="plugin-list" class="plugin-list">
        <div class="hint">Cargando plugins…</div>
      </div>
      <div class="section-title" style="margin-top:16px">Instalar plugin</div>
      <p class="hint">Crea un plugin vacío que puedes editar en <code>plugins/</code></p>
      <label class="field-label">Nombre</label>
      <input class="field-input" id="new-plugin-name" type="text" placeholder="Mi Plugin"/>
      <label class="field-label">Descripción</label>
      <input class="field-input" id="new-plugin-desc" type="text" placeholder="Qué hace este plugin"/>
      <button id="btn-install-plugin" class="btn-primary" style="margin-top:10px;width:100%">+ Instalar plugin</button>
    </div>

  </div>
  <script nonce="${nonce}" src="${jsUri}"></script>
</body>
</html>`;
  }
}

function getNonce() {
  let text = '';
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  for (let i = 0; i < 32; i++) text += chars.charAt(Math.floor(Math.random() * chars.length));
  return text;
}

module.exports = { activate, deactivate };
