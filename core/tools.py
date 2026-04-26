from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


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
]

# Tools that require confirmation before execution
DESTRUCTIVE_TOOLS = {"write_file", "create_folder", "run_command"}


def execute_tool(
    name: str,
    args: Dict[str, Any],
    *,
    confirm_fn: Optional[Callable[[str], bool]] = None,
) -> str:
    """
    Execute a tool by name with the given arguments.
    confirm_fn receives a description string and returns True if approved.
    """
    if name == "write_file":
        return _write_file(args, confirm_fn=confirm_fn)
    if name == "read_file":
        return _read_file(args)
    if name == "create_folder":
        return _create_folder(args, confirm_fn=confirm_fn)
    if name == "list_dir":
        return _list_dir(args)
    if name == "run_command":
        return _run_command(args, confirm_fn=confirm_fn)
    return f"[error] Herramienta desconocida: {name}"


def _write_file(args: Dict[str, Any], *, confirm_fn: Optional[Callable[[str], bool]]) -> str:
    path = str(args.get("path", "")).strip()
    content = str(args.get("content", ""))
    if not path:
        return "[error] path es requerido"

    p = Path(path).expanduser()
    action = "sobreescribir" if p.exists() else "crear"
    desc = f"{action} archivo: {p}"

    if confirm_fn is not None:
        if not confirm_fn(desc):
            return "[cancelado] El usuario rechazó la operación."

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
