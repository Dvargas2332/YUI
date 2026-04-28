from __future__ import annotations

import base64
import json
import queue
import threading
from pathlib import Path
from typing import Any, Callable, Optional

# ── Browser worker thread ─────────────────────────────────────────────────────
# Playwright sync_api requires ALL calls to happen in the SAME thread that
# called sync_playwright().start(). YUI runs tools in secondary threads, so we
# use a dedicated worker thread that owns the Playwright instance and processes
# commands via a queue.

_cmd_q: "queue.Queue[tuple]" = queue.Queue()
_worker_thread: Optional[threading.Thread] = None
_worker_started = threading.Event()
_worker_lock = threading.Lock()

_pw = None
_browser = None
_context = None
_page = None


def _worker_loop():
    global _pw, _browser, _context, _page
    _worker_started.set()
    while True:
        item = _cmd_q.get()
        if item is None:
            break
        fn, args, kwargs, result_box = item
        try:
            out = fn(*args, **kwargs)
            result_box.append(("ok", out))
        except Exception as e:
            result_box.append(("err", e))
        finally:
            _cmd_q.task_done()


def _ensure_worker():
    global _worker_thread
    with _worker_lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            _worker_started.clear()
            _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="pw-worker")
            _worker_thread.start()
            _worker_started.wait(timeout=5)


def _call(fn: Callable, *args, **kwargs) -> Any:
    """Run fn(*args, **kwargs) in the browser worker thread and return result."""
    _ensure_worker()
    box: list = []
    _cmd_q.put((fn, args, kwargs, box))
    # wait for result — use a simple Event
    done = threading.Event()

    def _waiter():
        _cmd_q.join()
        done.set()

    # Poll box directly (queue.join() would block all callers)
    import time
    timeout = 35.0
    start = time.monotonic()
    while not box and (time.monotonic() - start) < timeout:
        time.sleep(0.05)
    if not box:
        return "[error] timeout esperando respuesta del navegador"
    status, val = box[0]
    if status == "err":
        return f"[error] {val}"
    return val


# ── Internal browser operations (run inside worker thread) ────────────────────

def _op_ensure_browser(headless: bool):
    global _pw, _browser, _context, _page
    if _browser is not None and _browser.is_connected():
        if _page is None or _page.is_closed():
            _page = _context.new_page()
        return
    from playwright.sync_api import sync_playwright
    _pw = sync_playwright().start()
    _browser = _pw.chromium.launch(headless=headless)
    _context = _browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
    )
    _page = _context.new_page()


def _op_open(url: str, headless: bool, wait_until: str) -> str:
    _op_ensure_browser(headless)
    _page.goto(url, wait_until=wait_until, timeout=30000)
    return f"[ok] Abierto: {url} — título: {_page.title()}"


def _op_click(selector: str, timeout_ms: int) -> str:
    _page.click(selector, timeout=timeout_ms)
    return f"[ok] Clic en: {selector}"


def _op_fill(selector: str, value: str, timeout_ms: int) -> str:
    _page.fill(selector, value, timeout=timeout_ms)
    return f"[ok] Llenado '{selector}'"


def _op_type(selector: str, text: str, delay_ms: int) -> str:
    _page.type(selector, text, delay=delay_ms)
    return f"[ok] Escrito en {selector}"


def _op_get_text(selector: str, timeout_ms: int) -> str:
    if selector == "body":
        text = _page.inner_text("body")
    else:
        _page.wait_for_selector(selector, timeout=timeout_ms)
        text = _page.inner_text(selector)
    if len(text) > 4000:
        text = text[:4000] + "\n... [truncado]"
    return text


def _op_get_html(selector: str, max_chars: int) -> str:
    html = _page.inner_html(selector)
    if len(html) > max_chars:
        html = html[:max_chars] + "\n... [truncado]"
    return html


def _op_screenshot(save_path: Optional[str]) -> str:
    if save_path:
        p = Path(save_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        _page.screenshot(path=str(p), full_page=False)
        return f"[ok] Screenshot guardado: {p}"
    data = _page.screenshot(full_page=False)
    b64 = base64.b64encode(data).decode()
    return f"[ok] Screenshot base64 ({len(b64)} chars): data:image/png;base64,{b64[:200]}..."


def _op_wait(selector: str, state: str, timeout_ms: int) -> str:
    _page.wait_for_selector(selector, state=state, timeout=timeout_ms)
    return f"[ok] Elemento '{state}': {selector}"


def _op_eval(script: str) -> str:
    result = _page.evaluate(script)
    return f"[ok] {json.dumps(result, ensure_ascii=False)[:2000]}"


def _op_url() -> str:
    return f"[ok] URL actual: {_page.url}"


def _op_select(selector: str, value: str) -> str:
    _page.select_option(selector, value=value)
    return f"[ok] Seleccionado '{value}' en {selector}"


def _op_press(key: str, selector: Optional[str]) -> str:
    if selector:
        _page.press(selector, key)
    else:
        _page.keyboard.press(key)
    return f"[ok] Tecla: {key}"


def _op_new_tab(url: Optional[str]) -> str:
    global _page
    _page = _context.new_page()
    if url:
        _page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return f"[ok] Nueva pestaña: {url}"
    return "[ok] Nueva pestaña vacía"


def _op_close() -> str:
    global _pw, _browser, _context, _page
    try:
        if _page and not _page.is_closed():
            _page.close()
        if _context:
            _context.close()
        if _browser and _browser.is_connected():
            _browser.close()
        if _pw:
            _pw.stop()
    except Exception:
        pass
    finally:
        _pw = _browser = _context = _page = None
    return "[ok] Navegador cerrado"


# ── Public API (called from any thread) ──────────────────────────────────────

def browser_open(url: str, headless: bool = True, wait_until: str = "domcontentloaded") -> str:
    return _call(_op_open, url, headless, wait_until)

def browser_click(selector: str, timeout_ms: int = 8000) -> str:
    return _call(_op_click, selector, timeout_ms)

def browser_fill(selector: str, value: str, timeout_ms: int = 8000) -> str:
    return _call(_op_fill, selector, value, timeout_ms)

def browser_type(selector: str, text: str, delay_ms: int = 60) -> str:
    return _call(_op_type, selector, text, delay_ms)

def browser_get_text(selector: str = "body", timeout_ms: int = 8000) -> str:
    return _call(_op_get_text, selector, timeout_ms)

def browser_get_html(selector: str = "html", max_chars: int = 6000) -> str:
    return _call(_op_get_html, selector, max_chars)

def browser_screenshot(save_path: Optional[str] = None) -> str:
    return _call(_op_screenshot, save_path)

def browser_wait(selector: str, state: str = "visible", timeout_ms: int = 15000) -> str:
    return _call(_op_wait, selector, state, timeout_ms)

def browser_eval(script: str) -> str:
    return _call(_op_eval, script)

def browser_url() -> str:
    return _call(_op_url)

def browser_select(selector: str, value: str) -> str:
    return _call(_op_select, selector, value)

def browser_press(key: str, selector: Optional[str] = None) -> str:
    return _call(_op_press, key, selector)

def browser_new_tab(url: Optional[str] = None) -> str:
    return _call(_op_new_tab, url)

def browser_close() -> str:
    return _call(_op_close)


# ── Wappalyzer ────────────────────────────────────────────────────────────────

def wappalyzer_analyze(url: str) -> str:
    try:
        from Wappalyzer import Wappalyzer, WebPage
        wapp = Wappalyzer.latest()
        webpage = WebPage.new_from_url(url, verify=False)
        technologies = wapp.analyze_with_categories(webpage)
        if not technologies:
            return f"[ok] No se detectaron tecnologías conocidas en {url}"
        lines = [f"Tecnologías detectadas en {url}:"]
        for tech, cats in sorted(technologies.items()):
            lines.append(f"  • {tech} [{', '.join(cats) if cats else '—'}]")
        return "\n".join(lines)
    except Exception as e:
        return f"[error] wappalyzer_analyze: {e}"
