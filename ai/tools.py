from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

# Optional dependencies — imported lazily inside functions
# pip install ddgs requests[socks] beautifulsoup4 lxml


def build_diff_payload(path: str, old_lines: List[str], new_lines: List[str]) -> str:
    """Returns a JSON string with unified-style diff chunks for the UI."""
    import json
    chunks: List[dict] = []
    max_len = max(len(old_lines), len(new_lines), 1)
    i = 0
    while i < max_len:
        old_line = old_lines[i] if i < len(old_lines) else None
        new_line = new_lines[i] if i < len(new_lines) else None
        if old_line != new_line:
            chunks.append({"old": old_line, "new": new_line, "ln": i + 1})
        i += 1
        if len(chunks) >= 200:
            break

    return json.dumps({"path": path, "chunks": chunks, "added": max(0, len(new_lines) - len(old_lines)), "removed": max(0, len(old_lines) - len(new_lines))})


# Tool definitions in OpenAI function-calling format
TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Crea o sobreescribe un archivo con el contenido dado. Úsalo para crear código, configuraciones o cualquier archivo de texto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta absoluta o relativa del archivo a crear/sobrescribir."},
                    "content": {"type": "string", "description": "Contenido completo que tendrá el archivo."},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lee el contenido de un archivo. Úsalo antes de editarlo para ver qué hay.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta del archivo a leer."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_folder",
            "description": "Crea una carpeta (y subcarpetas intermedias si hacen falta).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta de la carpeta a crear."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "Lista el contenido de un directorio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta del directorio a listar."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Busca información en internet usando DuckDuckGo. Úsalo cuando necesites datos actuales, documentación, noticias o cualquier cosa que no esté en el contexto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Consulta de búsqueda."},
                    "max_results": {"type": "integer", "description": "Número máximo de resultados (por defecto 5, máximo 10)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tor_search",
            "description": "Busca en internet enrutando la conexión a través de Tor para mayor anonimato. Requiere que Tor esté corriendo en localhost:9050. Si Tor no está disponible, usa conexión normal como fallback.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Consulta de búsqueda."},
                    "max_results": {"type": "integer", "description": "Número máximo de resultados (por defecto 5, máximo 10)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_page",
            "description": "Descarga y lee el contenido de una página web. Extrae el texto limpio (sin HTML). Úsalo para leer artículos, documentación, foros, o cualquier URL específica.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL completa de la página a descargar."},
                    "max_chars": {"type": "integer", "description": "Máximo de caracteres a devolver (por defecto 6000)."},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_multiple",
            "description": "Descarga varias URLs en paralelo y devuelve el contenido de cada una. Úsalo para comparar información entre múltiples fuentes al mismo tiempo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {"type": "array", "items": {"type": "string"}, "description": "Lista de URLs a descargar (máximo 8)."},
                    "max_chars_each": {"type": "integer", "description": "Máximo de caracteres por página (por defecto 4000)."},
                },
                "required": ["urls"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fact_check",
            "description": "Busca un dato o afirmación en múltiples fuentes independientes y analiza si la información es consistente o contradictoria entre ellas. Detecta posible desinformación.",
            "parameters": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string", "description": "La afirmación o dato a verificar."},
                    "num_sources": {"type": "integer", "description": "Número de fuentes a consultar (por defecto 5, máximo 8)."},
                },
                "required": ["claim"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Ejecuta un comando de shell. Para proyectos: npm install, pip install, git init, etc. Solo usa para comandos seguros y autorizados.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Comando a ejecutar."},
                    "cwd": {"type": "string", "description": "Directorio de trabajo (opcional)."},
                    "timeout_s": {"type": "number", "description": "Tiempo máximo en segundos (por defecto 30)."},
                },
                "required": ["command"],
            },
        },
    },
    # ── Playwright browser tools ──────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "browser_open",
            "description": "Abre una URL en el navegador automatizado. Úsalo para navegar a páginas web, formularios, paneles de login, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL completa a abrir."},
                    "headless": {"type": "boolean", "description": "false = muestra el navegador visible (por defecto), true = sin ventana."},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Hace clic en un elemento del navegador usando un selector CSS o XPath.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "Selector CSS o XPath del elemento a clickear. Ej: '#submit-btn', 'button[type=submit]', 'text=Aceptar'."},
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill",
            "description": "Llena un campo de formulario (input, textarea) con un valor. Borra el contenido previo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "Selector CSS del campo. Ej: '#email', 'input[name=password]'."},
                    "value": {"type": "string", "description": "Valor a escribir en el campo."},
                },
                "required": ["selector", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type",
            "description": "Escribe texto en un elemento caracter por caracter (simula teclado humano). Útil cuando browser_fill no funciona.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "Selector CSS del elemento."},
                    "text": {"type": "string", "description": "Texto a escribir."},
                },
                "required": ["selector", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_get_text",
            "description": "Obtiene el texto visible de un elemento o de toda la página. Úsalo para leer contenido, mensajes de error, resultados.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "Selector CSS del elemento (por defecto 'body' = toda la página)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Toma una captura de pantalla del estado actual del navegador.",
            "parameters": {
                "type": "object",
                "properties": {
                    "save_path": {"type": "string", "description": "Ruta donde guardar el PNG (opcional). Si no se da, devuelve base64."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_wait",
            "description": "Espera a que un elemento aparezca o sea visible en la página antes de continuar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "Selector CSS del elemento a esperar."},
                    "state": {"type": "string", "description": "'visible' (por defecto), 'attached', 'hidden', 'detached'."},
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_eval",
            "description": "Ejecuta JavaScript en la página del navegador y devuelve el resultado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "script": {"type": "string", "description": "Código JavaScript a ejecutar en el contexto de la página. Ej: 'document.title' o 'document.cookie'."},
                },
                "required": ["script"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_url",
            "description": "Devuelve la URL actual del navegador.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_select",
            "description": "Selecciona una opción en un elemento <select> (dropdown).",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "Selector CSS del <select>."},
                    "value": {"type": "string", "description": "Valor de la opción a seleccionar."},
                },
                "required": ["selector", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_press",
            "description": "Presiona una tecla del teclado. Ej: 'Enter', 'Tab', 'Escape', 'ArrowDown'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Nombre de la tecla (formato Playwright). Ej: 'Enter', 'Tab', 'F5'."},
                    "selector": {"type": "string", "description": "Selector del elemento donde presionar (opcional, si no se da es global)."},
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_new_tab",
            "description": "Abre una nueva pestaña en el navegador, opcionalmente con una URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL a abrir en la nueva pestaña (opcional)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close",
            "description": "Cierra el navegador y libera todos los recursos. Úsalo cuando termines de automatizar.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ── Wappalyzer ────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "wappalyzer_analyze",
            "description": "Analiza una URL y detecta las tecnologías usadas: CMS, frameworks, servidores, CDNs, analytics, etc. Muy útil para reconocimiento web.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL completa a analizar. Ej: 'https://example.com'."},
                },
                "required": ["url"],
            },
        },
    },
]

# Tools that require confirmation before execution
DESTRUCTIVE_TOOLS = {"write_file", "create_folder", "run_command", "browser_eval"}


def execute_tool(
    name: str,
    args: Dict[str, Any],
    *,
    confirm_fn: Optional[Callable[[str], bool]] = None,
    diff_fn: Optional[Callable[[str, List[str], List[str]], None]] = None,
) -> str:
    """
    Execute a tool by name with the given arguments.
    confirm_fn receives a description string and returns True if approved.
    diff_fn receives (path, old_lines, new_lines) before writing.
    """
    if name == "write_file":
        return _write_file(args, confirm_fn=confirm_fn, diff_fn=diff_fn)
    if name == "read_file":
        return _read_file(args)
    if name == "create_folder":
        return _create_folder(args, confirm_fn=confirm_fn)
    if name == "list_dir":
        return _list_dir(args)
    if name == "run_command":
        return _run_command(args, confirm_fn=confirm_fn)
    if name == "web_search":
        return _web_search(args)
    if name == "tor_search":
        return _tor_search(args)
    if name == "fetch_page":
        return _fetch_page(args)
    if name == "fetch_multiple":
        return _fetch_multiple(args)
    if name == "fact_check":
        return _fact_check(args)
    # ── Playwright / Wappalyzer ───────────────────────────────────────────────
    if name in {
        "browser_open", "browser_click", "browser_fill", "browser_type",
        "browser_get_text", "browser_get_html", "browser_screenshot",
        "browser_wait", "browser_eval", "browser_url", "browser_select",
        "browser_press", "browser_new_tab", "browser_close",
        "wappalyzer_analyze",
    }:
        return _dispatch_browser(name, args, confirm_fn=confirm_fn)
    return f"[error] Herramienta desconocida: {name}"


def _dispatch_browser(
    name: str,
    args: Dict[str, Any],
    *,
    confirm_fn: Optional[Callable[[str], bool]],
) -> str:
    try:
        from plugins.playwright.browser import (
            browser_open, browser_click, browser_fill, browser_type,
            browser_get_text, browser_get_html, browser_screenshot,
            browser_wait, browser_eval, browser_url, browser_select,
            browser_press, browser_new_tab, browser_close,
            wappalyzer_analyze,
        )
    except ImportError as e:
        return f"[error] Plugin Playwright no disponible: {e}"

    if name == "browser_open":
        if confirm_fn and not confirm_fn(f"abrir navegador en: {args.get('url')}"):
            return "[cancelado]"
        return browser_open(args["url"], headless=args.get("headless", True))
    if name == "browser_click":
        return browser_click(args["selector"])
    if name == "browser_fill":
        return browser_fill(args["selector"], args["value"])
    if name == "browser_type":
        return browser_type(args["selector"], args["text"])
    if name == "browser_get_text":
        return browser_get_text(args.get("selector", "body"))
    if name == "browser_get_html":
        return browser_get_html(args.get("selector", "html"), args.get("max_chars", 6000))
    if name == "browser_screenshot":
        return browser_screenshot(args.get("save_path"))
    if name == "browser_wait":
        return browser_wait(args["selector"], args.get("state", "visible"))
    if name == "browser_eval":
        if confirm_fn and not confirm_fn(f"ejecutar JS: {args.get('script','')[:80]}"):
            return "[cancelado]"
        return browser_eval(args["script"])
    if name == "browser_url":
        return browser_url()
    if name == "browser_select":
        return browser_select(args["selector"], args["value"])
    if name == "browser_press":
        return browser_press(args["key"], args.get("selector"))
    if name == "browser_new_tab":
        return browser_new_tab(args.get("url"))
    if name == "browser_close":
        return browser_close()
    if name == "wappalyzer_analyze":
        return wappalyzer_analyze(args["url"])
    return f"[error] Herramienta desconocida: {name}"


def _write_file(
    args: Dict[str, Any],
    *,
    confirm_fn: Optional[Callable[[str], bool]],
    diff_fn: Optional[Callable[[str, List[str], List[str]], None]] = None,
) -> str:
    path = str(args.get("path", "")).strip()
    content = str(args.get("content", ""))
    if not path:
        return "[error] path es requerido"

    p = Path(path).expanduser()
    action = "sobreescribir" if p.exists() else "crear"
    desc = f"{action} archivo: {p}"

    old_lines: List[str] = []
    if p.exists():
        try:
            old_lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            pass

    if confirm_fn is not None:
        if not confirm_fn(desc):
            return "[cancelado] El usuario rechazó la operación."

    if diff_fn is not None:
        try:
            diff_fn(str(p), old_lines, content.splitlines())
        except Exception:
            pass

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"[ok] Archivo guardado: {p} ({len(content)} caracteres)"
    except Exception as e:
        return f"[error] No pude escribir {p}: {e}"


def _read_file(args: Dict[str, Any]) -> str:
    path = str(args.get("path", "")).strip()
    if not path:
        return "[error] path es requerido"
    p = Path(path).expanduser()
    if not p.exists():
        return f"[error] No existe: {p}"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        # Limit to avoid flooding context
        if len(text) > 8000:
            text = text[:8000] + "\n... [truncado]"
        return text
    except Exception as e:
        return f"[error] No pude leer {p}: {e}"


def _create_folder(args: Dict[str, Any], *, confirm_fn: Optional[Callable[[str], bool]]) -> str:
    path = str(args.get("path", "")).strip()
    if not path:
        return "[error] path es requerido"
    p = Path(path).expanduser()
    if p.exists():
        return f"[ok] Ya existe: {p}"

    desc = f"crear carpeta: {p}"
    if confirm_fn is not None:
        if not confirm_fn(desc):
            return "[cancelado] El usuario rechazó la operación."

    try:
        p.mkdir(parents=True, exist_ok=True)
        return f"[ok] Carpeta creada: {p}"
    except Exception as e:
        return f"[error] No pude crear {p}: {e}"


def _list_dir(args: Dict[str, Any]) -> str:
    path = str(args.get("path", ".")).strip() or "."
    p = Path(path).expanduser()
    if not p.exists():
        return f"[error] No existe: {p}"
    if not p.is_dir():
        return f"[error] No es un directorio: {p}"
    try:
        entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        lines = []
        for e in entries[:100]:
            kind = "DIR " if e.is_dir() else "FILE"
            lines.append(f"{kind} {e.name}")
        if not lines:
            return f"[ok] Directorio vacío: {p}"
        result = "\n".join(lines)
        if len(entries) > 100:
            result += f"\n... y {len(entries) - 100} más"
        return result
    except Exception as e:
        return f"[error] No pude listar {p}: {e}"


def _run_command(args: Dict[str, Any], *, confirm_fn: Optional[Callable[[str], bool]]) -> str:
    command = str(args.get("command", "")).strip()
    cwd = str(args.get("cwd", "")).strip() or None
    default_timeout = float(os.getenv("YUI_TOOL_RUN_TIMEOUT_S", "60"))
    timeout_s = float(args.get("timeout_s", default_timeout))

    if not command:
        return "[error] command es requerido"

    # Block obviously destructive commands
    cmd_low = command.lower().strip()
    blocked = ["rm -rf /", "format c:", "del /f /s /q c:\\", "shutdown", "rd /s /q c:\\"]
    if any(b in cmd_low for b in blocked):
        return "[bloqueado] Comando denegado por política de seguridad."

    desc = f"ejecutar: {command}" + (f" (en {cwd})" if cwd else "")
    if confirm_fn is not None:
        if not confirm_fn(desc):
            return "[cancelado] El usuario rechazó la operación."

    print(f"[YUI] Ejecutando (timeout={timeout_s:.0f}s): {command}")

    stdout_lines: List[str] = []
    stderr_lines: List[str] = []
    MAX_LINES = 200
    MAX_LINE_LEN = 500

    def _stream_reader(stream: Any, bucket: List[str], prefix: str) -> None:
        try:
            for raw in stream:
                line = raw.rstrip("\n")[:MAX_LINE_LEN]
                if len(bucket) < MAX_LINES:
                    bucket.append(line)
                print(f"  {prefix}{line}", flush=True)
        except Exception:
            pass

    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            encoding="utf-8",
            errors="replace",
        )

        t_out = threading.Thread(target=_stream_reader, args=(proc.stdout, stdout_lines, ""), daemon=True)
        t_err = threading.Thread(target=_stream_reader, args=(proc.stderr, stderr_lines, "[err] "), daemon=True)
        t_out.start()
        t_err.start()

        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            t_out.join(timeout=2.0)
            t_err.join(timeout=2.0)
            partial = "\n".join(stdout_lines[-50:]) if stdout_lines else ""
            return f"[error] Tiempo agotado ({timeout_s:.0f}s).\nSalida parcial:\n{partial}" if partial else f"[error] Tiempo agotado ({timeout_s:.0f}s)."

        t_out.join(timeout=5.0)
        t_err.join(timeout=5.0)

        rc = proc.returncode
        out = "\n".join(stdout_lines)
        err = "\n".join(stderr_lines)

        parts: List[str] = []
        if out.strip():
            parts.append(out.strip())
        if err.strip():
            parts.append(f"[stderr]\n{err.strip()}")
        if rc != 0:
            parts.append(f"[exit code {rc}]")

        return "\n".join(parts) if parts else "[ok] Comando ejecutado sin salida."

    except Exception as e:
        return f"[error] {e}"


def _format_ddg_results(results: List[Dict[str, Any]]) -> str:
    if not results:
        return "[sin resultados]"
    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "Sin título")
        url = r.get("href", r.get("url", ""))
        body = r.get("body", r.get("snippet", "")).strip().replace("\n", " ")
        if len(body) > 300:
            body = body[:300] + "..."
        lines.append(f"{i}. {title}\n   {url}\n   {body}")
    return "\n\n".join(lines)


def _web_search(args: Dict[str, Any]) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return "[error] query es requerido"
    max_results = min(int(args.get("max_results", 5)), 10)

    try:
        from ddgs import DDGS
    except ImportError:
        return "[error] Instala ddgs: pip install ddgs"

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return f"[web_search: {query}]\n\n" + _format_ddg_results(results)
    except Exception as e:
        return f"[error] Búsqueda fallida: {e}"


def _get_session():
    """Returns a requests.Session with browser-like headers."""
    try:
        import requests
    except ImportError:
        return None
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    })
    return s


def _extract_text(html: str, max_chars: int) -> str:
    """Extracts clean readable text from HTML using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        # Fallback: strip tags with regex
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]

    soup = BeautifulSoup(html, "lxml" if _has_lxml() else "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        tag.decompose()

    # Prefer article/main content blocks
    main = soup.find("article") or soup.find("main") or soup.find(id=re.compile(r"content|main|article", re.I))
    target = main if main else soup.body if soup.body else soup

    lines = []
    for elem in target.find_all(["p", "h1", "h2", "h3", "h4", "li", "blockquote", "td"]):
        t = elem.get_text(" ", strip=True)
        if len(t) > 30:
            lines.append(t)

    text = "\n".join(lines)
    if not text.strip():
        text = target.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()

    return text[:max_chars]


def _has_lxml() -> bool:
    try:
        import lxml  # noqa: F401
        return True
    except ImportError:
        return False


def _fetch_url(url: str, max_chars: int = 6000, timeout: int = 15) -> Tuple[str, str]:
    """Downloads a URL and returns (url, extracted_text_or_error)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return url, f"[error] Esquema no permitido: {parsed.scheme}"

    session = _get_session()
    if session is None:
        return url, "[error] Instala requests: pip install requests"

    try:
        resp = session.get(url, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        ct = resp.headers.get("Content-Type", "")
        if "text" not in ct and "html" not in ct and "json" not in ct:
            return url, f"[skip] Tipo de contenido no legible: {ct}"
        if "json" in ct:
            return url, resp.text[:max_chars]
        return url, _extract_text(resp.text, max_chars)
    except Exception as e:
        return url, f"[error] {e}"


def _fetch_page(args: Dict[str, Any]) -> str:
    url = str(args.get("url", "")).strip()
    if not url:
        return "[error] url es requerido"
    max_chars = min(int(args.get("max_chars", 6000)), 20000)

    _, text = _fetch_url(url, max_chars=max_chars)
    if not text.strip():
        return f"[fetch_page: {url}]\n[sin contenido legible]"
    return f"[fetch_page: {url}]\n\n{text}"


def _fetch_multiple(args: Dict[str, Any]) -> str:
    urls: List[str] = [str(u).strip() for u in args.get("urls", []) if str(u).strip()]
    if not urls:
        return "[error] urls es requerido"
    urls = urls[:8]
    max_chars = min(int(args.get("max_chars_each", 4000)), 10000)

    results: Dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(len(urls), 6)) as pool:
        futures = {pool.submit(_fetch_url, u, max_chars): u for u in urls}
        try:
            for fut in as_completed(futures, timeout=30):
                url, text = fut.result()
                results[url] = text
        except FuturesTimeout:
            for fut, u in futures.items():
                if u not in results:
                    results[u] = "[error] Tiempo agotado"

    parts = []
    for i, u in enumerate(urls, 1):
        text = results.get(u, "[sin respuesta]")
        parts.append(f"--- Fuente {i}: {u} ---\n{text}")
    return "\n\n".join(parts)


def _fact_check(args: Dict[str, Any]) -> str:
    claim = str(args.get("claim", "")).strip()
    if not claim:
        return "[error] claim es requerido"
    num_sources = min(int(args.get("num_sources", 5)), 8)

    # Step 1: search for the claim + counter-claim
    try:
        from ddgs import DDGS
    except ImportError:
        return "[error] Instala ddgs: pip install ddgs"

    queries = [
        f'"{claim}" verdadero falso',
        f"{claim} fact check verificación fuente",
        f"{claim} es cierto evidencia científica",
        f"{claim} debunked myth false",
    ]

    all_urls: List[str] = []
    seen: set = set()
    try:
        with DDGS() as ddgs:
            for q in queries:
                for r in ddgs.text(q, max_results=4):
                    u = r.get("href", r.get("url", ""))
                    if u and u not in seen:
                        seen.add(u)
                        all_urls.append(u)
                if len(all_urls) >= num_sources * 2:
                    break
    except Exception as e:
        return f"[error] Búsqueda fallida: {e}"

    urls_to_fetch = all_urls[:num_sources]
    if not urls_to_fetch:
        return "[fact_check] No se encontraron fuentes."

    # Step 2: download pages in parallel
    page_contents: List[Tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=min(len(urls_to_fetch), 5)) as pool:
        futures = {pool.submit(_fetch_url, u, 3000): u for u in urls_to_fetch}
        try:
            for fut in as_completed(futures, timeout=25):
                page_contents.append(fut.result())
        except FuturesTimeout:
            pass

    # Step 3: build structured report
    lines = [f"[fact_check] Afirmación: «{claim}»", f"Fuentes consultadas: {len(page_contents)}", ""]

    supports, contradicts, unclear = [], [], []
    claim_words = set(re.findall(r"\w+", claim.lower()))

    for url, text in page_contents:
        if text.startswith("[error") or text.startswith("[skip"):
            continue
        text_low = text.lower()
        neg_signals = [
                "falso", "mito", "incorrecto", "desinformación", "fake", "false", "myth",
                "no es cierto", "no es verdad", "engaño", "rumor", "sin evidencia",
                "teoría de conspiración", "conspiracy", "pseudoscience", "pseudociencia",
                "debunked", "refutado", "no tiene base", "carece de evidencia",
            ]
        pos_signals = [
                "confirmado", "verdadero", "correcto", "cierto", "comprobado",
                "true", "confirmed", "correct", "evidence shows", "studies show",
                "scientific consensus", "consenso científico", "demostrado",
            ]
        # Signals that a source is debunking/explaining a false claim (context clue)
        debunk_context = [
                "por qué hay gente que cree", "why people believe", "believers claim",
                "flat earth", "terraplanista", "terraplanismo", "tierra plana",
                "gente que aún cree", "still believe", "conspiracy theorists",
                "the myth", "el mito", "la creencia errónea",
            ]

        neg_hits = sum(1 for s in neg_signals if s in text_low)
        pos_hits = sum(1 for s in pos_signals if s in text_low)
        debunk_hits = sum(1 for s in debunk_context if s in text_low)
        # Debunking articles count as contradiction evidence
        neg_hits += debunk_hits // 2
        # How relevant is this page to the claim?
        overlap = sum(1 for w in claim_words if len(w) > 4 and w in text_low)

        domain = urlparse(url).netloc
        snippet = text[:200].replace("\n", " ")

        if neg_hits > pos_hits and overlap > 1:
            contradicts.append(f"  [NO] {domain}: {snippet}...")
        elif pos_hits > neg_hits and overlap > 1:
            supports.append(f"  [SI] {domain}: {snippet}...")
        else:
            unclear.append(f"  [?] {domain}: {snippet}...")

    if supports:
        lines.append(f"FUENTES QUE APOYAN ({len(supports)}):")
        lines.extend(supports)
        lines.append("")
    if contradicts:
        lines.append(f"FUENTES QUE CONTRADICEN ({len(contradicts)}):")
        lines.extend(contradicts)
        lines.append("")
    if unclear:
        lines.append(f"FUENTES AMBIGUAS ({len(unclear)}):")
        lines.extend(unclear)
        lines.append("")

    # Verdict
    if contradicts and not supports:
        verdict = "PROBABLE DESINFORMACIÓN — múltiples fuentes contradicen la afirmación."
    elif supports and not contradicts:
        verdict = "INFORMACIÓN CONSISTENTE — las fuentes consultadas la apoyan."
    elif contradicts and supports:
        verdict = "INFORMACIÓN DISPUTADA — hay fuentes a favor y en contra. Verificar con fuentes primarias."
    else:
        verdict = "INDETERMINADO — no se pudo extraer suficiente contexto de las fuentes."

    lines.append(f"VEREDICTO: {verdict}")
    return "\n".join(lines)


def _tor_search(args: Dict[str, Any]) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return "[error] query es requerido"
    max_results = min(int(args.get("max_results", 5)), 10)

    try:
        from ddgs import DDGS
    except ImportError:
        return "[error] Instala ddgs: pip install ddgs"

    # Try via Tor SOCKS5 proxy (requires requests[socks])
    tor_proxy = {"http": "socks5h://127.0.0.1:9050", "https": "socks5h://127.0.0.1:9050"}
    via_tor = False
    try:
        import requests
        r = requests.get("https://check.torproject.org/api/ip", proxies=tor_proxy, timeout=8)
        via_tor = r.json().get("IsTor", False)
    except Exception:
        pass

    try:
        if via_tor:
            with DDGS(proxies=tor_proxy, timeout=20) as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            prefix = "[tor_search (via Tor)"
        else:
            # Tor not available — fallback to clearnet
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            prefix = "[tor_search (Tor no disponible, usando clearnet)"

        return f"{prefix}: {query}]\n\n" + _format_ddg_results(results)
    except Exception as e:
        return f"[error] Búsqueda fallida: {e}"


# ── Plugin system ─────────────────────────────────────────────────────────────

_PLUGINS_ROOT = Path(__file__).parent.parent / "plugins"

# Runtime registry: tool_name -> handler function (loaded from plugin.py)
_plugin_tool_handlers: Dict[str, Callable[..., str]] = {}
# Extra tool definitions injected by enabled plugins
_plugin_tool_definitions: List[Dict[str, Any]] = []


def _load_plugins() -> None:
    """
    Scans plugins/ directory, loads enabled plugins, registers their tool
    definitions and handlers. Safe to call multiple times — re-scans each time
    so enabling/disabling a plugin takes effect on the next call.
    """
    global _plugin_tool_handlers, _plugin_tool_definitions
    _plugin_tool_handlers = {}
    _plugin_tool_definitions = []

    if not _PLUGINS_ROOT.exists():
        return

    for entry in sorted(_PLUGINS_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        manifest_path = entry / "plugin.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not manifest.get("enabled", False):
            continue

        entrypoint = entry / manifest.get("entrypoint", "plugin.py")
        if not entrypoint.exists():
            continue

        try:
            spec = importlib.util.spec_from_file_location(
                f"yui_plugin_{entry.name}", str(entrypoint)
            )
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[attr-defined]
        except Exception as e:
            print(f"[YUI Plugin] Error cargando {entry.name}: {e}")
            continue

        if not hasattr(mod, "register"):
            continue
        try:
            reg = mod.register()
        except Exception as e:
            print(f"[YUI Plugin] Error en register() de {entry.name}: {e}")
            continue

        # Each plugin returns {"tools": [...openai-format...], "handlers": {name: fn}}
        for tool_def in reg.get("tools", []):
            _plugin_tool_definitions.append(tool_def)
            print(f"[YUI Plugin] Tool registrado: {tool_def.get('function', {}).get('name')} ({entry.name})")

        for name, fn in reg.get("handlers", {}).items():
            _plugin_tool_handlers[name] = fn


def get_all_tool_definitions() -> List[Dict[str, Any]]:
    """Returns base tools + all enabled plugin tools."""
    _load_plugins()
    return TOOL_DEFINITIONS + _plugin_tool_definitions


def execute_plugin_tool(name: str, args: Dict[str, Any]) -> Optional[str]:
    """
    Executes a tool registered by a plugin. Returns result string or None if
    the tool name is not from any plugin.
    """
    fn = _plugin_tool_handlers.get(name)
    if fn is None:
        return None
    try:
        return str(fn(args))
    except Exception as e:
        return f"[error] Plugin tool {name} falló: {e}"
