from __future__ import annotations

import base64
import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

# Singleton browser session — one browser per YUI process
_lock = threading.Lock()
_pw = None          # playwright instance
_browser = None     # Browser
_page = None        # active Page
_context = None     # BrowserContext


def _ensure_browser(headless: bool = True):
    global _pw, _browser, _context, _page
    with _lock:
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


def _page_ref():
    global _page, _context
    if _page is None or _page.is_closed():
        _page = _context.new_page()
    return _page


# ── Public tool functions ─────────────────────────────────────────────────────

def browser_open(url: str, headless: bool = True, wait_until: str = "domcontentloaded") -> str:
    try:
        _ensure_browser(headless=headless)
        page = _page_ref()
        page.goto(url, wait_until=wait_until, timeout=30000)
        title = page.title()
        return f"[ok] Abierto: {url} — título: {title}"
    except Exception as e:
        return f"[error] browser_open: {e}"


def browser_click(selector: str, timeout_ms: int = 8000) -> str:
    try:
        page = _page_ref()
        page.click(selector, timeout=timeout_ms)
        return f"[ok] Clic en: {selector}"
    except Exception as e:
        return f"[error] browser_click: {e}"


def browser_fill(selector: str, value: str, timeout_ms: int = 8000) -> str:
    try:
        page = _page_ref()
        page.fill(selector, value, timeout=timeout_ms)
        return f"[ok] Llenado '{selector}' con valor"
    except Exception as e:
        return f"[error] browser_fill: {e}"


def browser_type(selector: str, text: str, delay_ms: int = 60) -> str:
    try:
        page = _page_ref()
        page.type(selector, text, delay=delay_ms)
        return f"[ok] Escrito en {selector}"
    except Exception as e:
        return f"[error] browser_type: {e}"


def browser_get_text(selector: str = "body", timeout_ms: int = 8000) -> str:
    try:
        page = _page_ref()
        if selector == "body":
            text = page.inner_text("body")
        else:
            page.wait_for_selector(selector, timeout=timeout_ms)
            text = page.inner_text(selector)
        if len(text) > 4000:
            text = text[:4000] + "\n... [truncado]"
        return text
    except Exception as e:
        return f"[error] browser_get_text: {e}"


def browser_get_html(selector: str = "html", max_chars: int = 6000) -> str:
    try:
        page = _page_ref()
        html = page.inner_html(selector)
        if len(html) > max_chars:
            html = html[:max_chars] + "\n... [truncado]"
        return html
    except Exception as e:
        return f"[error] browser_get_html: {e}"


def browser_screenshot(save_path: Optional[str] = None) -> str:
    try:
        page = _page_ref()
        if save_path:
            p = Path(save_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(p), full_page=False)
            return f"[ok] Screenshot guardado en: {p}"
        else:
            data = page.screenshot(full_page=False)
            b64 = base64.b64encode(data).decode()
            return f"[ok] Screenshot base64 ({len(b64)} chars): data:image/png;base64,{b64[:200]}..."
    except Exception as e:
        return f"[error] browser_screenshot: {e}"


def browser_wait(selector: str, state: str = "visible", timeout_ms: int = 15000) -> str:
    try:
        page = _page_ref()
        page.wait_for_selector(selector, state=state, timeout=timeout_ms)
        return f"[ok] Elemento visible: {selector}"
    except Exception as e:
        return f"[error] browser_wait: {e}"


def browser_eval(script: str) -> str:
    try:
        page = _page_ref()
        result = page.evaluate(script)
        return f"[ok] {json.dumps(result, ensure_ascii=False)[:2000]}"
    except Exception as e:
        return f"[error] browser_eval: {e}"


def browser_url() -> str:
    try:
        page = _page_ref()
        return f"[ok] URL actual: {page.url}"
    except Exception as e:
        return f"[error] browser_url: {e}"


def browser_close() -> str:
    global _pw, _browser, _context, _page
    with _lock:
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


def browser_new_tab(url: Optional[str] = None) -> str:
    global _page
    try:
        _ensure_browser()
        with _lock:
            _page = _context.new_page()
        if url:
            _page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return f"[ok] Nueva pestaña abierta: {url}"
        return "[ok] Nueva pestaña vacía abierta"
    except Exception as e:
        return f"[error] browser_new_tab: {e}"


def browser_select(selector: str, value: str) -> str:
    try:
        page = _page_ref()
        page.select_option(selector, value=value)
        return f"[ok] Seleccionado '{value}' en {selector}"
    except Exception as e:
        return f"[error] browser_select: {e}"


def browser_press(key: str, selector: Optional[str] = None) -> str:
    try:
        page = _page_ref()
        if selector:
            page.press(selector, key)
        else:
            page.keyboard.press(key)
        return f"[ok] Tecla presionada: {key}"
    except Exception as e:
        return f"[error] browser_press: {e}"


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
            cat_str = ", ".join(cats) if cats else "—"
            lines.append(f"  • {tech} [{cat_str}]")
        return "\n".join(lines)
    except Exception as e:
        return f"[error] wappalyzer_analyze: {e}"
