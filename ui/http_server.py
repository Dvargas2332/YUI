from __future__ import annotations

import json
import mimetypes
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse


class UiHttpServer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        static_root: Path,
        on_command: Callable[[str], bool],
        get_state: Callable[[], dict[str, Any]],
        on_toggle: Callable[[str, bool], dict[str, Any]],
        on_config: Optional[Callable[[dict[str, str]], dict[str, Any]]] = None,
        on_clear: Optional[Callable[[], dict[str, Any]]] = None,
        on_compact: Optional[Callable[[], dict[str, Any]]] = None,
        on_set_mode: Optional[Callable[[str], dict[str, Any]]] = None,
    ):
        self.host = host
        self.port = int(port)
        self.static_root = Path(static_root)
        self.on_command = on_command
        self.get_state = get_state
        self.on_toggle = on_toggle
        self.on_config = on_config
        self.on_clear = on_clear
        self.on_compact = on_compact
        self.on_set_mode = on_set_mode
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        handler = self._make_handler()
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True, name="yui-http-ui")
        self._thread.start()
        print(f"[YUI] UI HTTP: http://{self.host}:{self.port}")

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def _make_handler(self):
        static_root = self.static_root
        on_command = self.on_command
        get_state = self.get_state
        on_toggle = self.on_toggle
        on_config = self.on_config
        on_clear = self.on_clear
        on_compact = self.on_compact
        on_set_mode = self.on_set_mode

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                return

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path == "/api/bootstrap":
                    self._send_json(get_state())
                    return
                if parsed.path == "/api/catalog":
                    state = get_state()
                    self._send_json(state.get("catalog", {}))
                    return
                self._serve_static(parsed.path)

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                allowed = {"/api/command", "/api/toggle", "/api/config", "/api/clear", "/api/compact", "/api/mode"}
                if parsed.path not in allowed:
                    self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
                    return
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(length) if length > 0 else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except Exception:
                    self._send_json({"error": "invalid_json"}, status=HTTPStatus.BAD_REQUEST)
                    return

                if parsed.path == "/api/command":
                    text = str(payload.get("text") or "").strip()
                    if not text:
                        self._send_json({"error": "text_required"}, status=HTTPStatus.BAD_REQUEST)
                        return
                    accepted = on_command(text)
                    self._send_json({"ok": bool(accepted), "queued": bool(accepted)})
                    return

                if parsed.path == "/api/toggle":
                    key = str(payload.get("key") or "").strip()
                    if not key:
                        self._send_json({"error": "key_required"}, status=HTTPStatus.BAD_REQUEST)
                        return
                    value = bool(payload.get("value"))
                    self._send_json(on_toggle(key, value))
                    return

                if parsed.path == "/api/config":
                    if on_config is None:
                        self._send_json({"error": "config_not_supported"}, status=HTTPStatus.NOT_IMPLEMENTED)
                        return
                    if not isinstance(payload, dict):
                        self._send_json({"error": "expected_object"}, status=HTTPStatus.BAD_REQUEST)
                        return
                    # Only allow known YUI_ env keys to avoid arbitrary writes
                    allowed_keys = {
                        "YUI_LLM_BASE_URL", "YUI_API_KEY", "YUI_LLM_MODEL",
                        "YUI_LLM_MODEL_FAST", "YUI_LLM_MODEL_DEEP",
                        "YUI_LLM_MODE", "YUI_LLM_TEMPERATURE", "YUI_LLM_DEEP_TEMPERATURE",
                        "YUI_LLM_MAX_TOKENS", "YUI_STT_LANGUAGE", "YUI_TTS_ENGINE",
                        "YUI_WAKE_WORD", "YUI_SYSTEM_PROMPT_OVERRIDE",
                    }
                    payload_typed: Dict[str, Any] = payload  # type: ignore[assignment]
                    filtered: Dict[str, str] = {str(k): str(v) for k, v in payload_typed.items() if str(k) in allowed_keys and str(v).strip()}
                    if not filtered:
                        self._send_json({"error": "no_valid_keys"}, status=HTTPStatus.BAD_REQUEST)
                        return
                    result = on_config(filtered)
                    self._send_json(result)
                    return

                if parsed.path == "/api/clear":
                    if on_clear is None:
                        self._send_json({"error": "not_supported"}, status=HTTPStatus.NOT_IMPLEMENTED)
                        return
                    self._send_json(on_clear())
                    return

                if parsed.path == "/api/compact":
                    if on_compact is None:
                        self._send_json({"error": "not_supported"}, status=HTTPStatus.NOT_IMPLEMENTED)
                        return
                    self._send_json(on_compact())
                    return

                if parsed.path == "/api/mode":
                    if on_set_mode is None:
                        self._send_json({"error": "not_supported"}, status=HTTPStatus.NOT_IMPLEMENTED)
                        return
                    mode = str(payload.get("mode") or "auto").strip()
                    self._send_json(on_set_mode(mode))
                    return

            def _serve_static(self, raw_path: str) -> None:
                path = raw_path.strip() or "/"
                if path == "/":
                    path = "/index.html"
                rel = path.lstrip("/")
                target = (static_root / rel).resolve()
                if not str(target).startswith(str(static_root.resolve())) or not target.exists() or not target.is_file():
                    self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
                    return
                ctype, _ = mimetypes.guess_type(str(target))
                body = target.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", ctype or "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler
