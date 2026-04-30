"""
YUI Plugin — Hydra
Fuerza bruta y ataques de diccionario sobre servicios de red con THC-Hydra.
Solo opera sobre activos con autorización explícita del usuario.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Any, Dict


_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "hydra_attack",
            "description": (
                "Ataque de fuerza bruta o diccionario sobre un servicio de red con Hydra. "
                "Soporta SSH, FTP, HTTP, RDP, SMB, MySQL, PostgreSQL, Telnet, SMTP y más. "
                "SOLO sobre activos con autorización explícita del usuario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "IP o hostname del objetivo.",
                    },
                    "service": {
                        "type": "string",
                        "enum": ["ssh", "ftp", "http-get", "http-post-form", "rdp", "smb",
                                 "mysql", "postgres", "telnet", "smtp", "pop3", "imap", "vnc"],
                        "description": "Protocolo/servicio a atacar.",
                    },
                    "username": {
                        "type": "string",
                        "description": "Usuario a probar. Si se omite, usar wordlist_user.",
                    },
                    "wordlist_user": {
                        "type": "string",
                        "description": "Ruta a wordlist de usuarios (opcional, si no se da username).",
                    },
                    "wordlist_pass": {
                        "type": "string",
                        "description": "Ruta a wordlist de contraseñas.",
                    },
                    "password": {
                        "type": "string",
                        "description": "Contraseña fija a probar (alternativa a wordlist_pass).",
                    },
                    "port": {
                        "type": "integer",
                        "description": "Puerto del servicio (opcional, usa el default del protocolo si se omite).",
                    },
                    "threads": {
                        "type": "integer",
                        "description": "Número de hilos paralelos (default: 16, max recomendado: 64).",
                    },
                    "extra_args": {
                        "type": "string",
                        "description": "Argumentos adicionales de hydra (opcional). Ej: '-e nsr' para probar null/user/reverse.",
                    },
                },
                "required": ["target", "service"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hydra_http_form",
            "description": (
                "Fuerza bruta sobre formularios HTTP/HTTPS con Hydra. "
                "Útil para login web con POST. SOLO sobre activos autorizados."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "IP o hostname del objetivo."},
                    "url_path": {"type": "string", "description": "Ruta del formulario. Ej: '/login.php'."},
                    "form_data": {
                        "type": "string",
                        "description": (
                            "Datos del formulario POST con ^USER^ y ^PASS^ como placeholders. "
                            "Ej: 'username=^USER^&password=^PASS^:F=Login failed'."
                        ),
                    },
                    "wordlist_user": {"type": "string", "description": "Ruta a wordlist de usuarios."},
                    "wordlist_pass": {"type": "string", "description": "Ruta a wordlist de contraseñas."},
                    "https": {"type": "boolean", "description": "Usar HTTPS (default: false)."},
                    "threads": {"type": "integer", "description": "Hilos paralelos (default: 16)."},
                },
                "required": ["target", "url_path", "form_data", "wordlist_pass"],
            },
        },
    },
]


def _check_hydra() -> bool:
    return shutil.which("hydra") is not None


def _run(cmd: list, timeout: int = 300) -> str:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace"
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if result.returncode != 0 and not out:
            return f"[error] hydra salió con código {result.returncode}:\n{err}"
        return out + (f"\n[stderr]\n{err}" if err else "")
    except subprocess.TimeoutExpired:
        return f"[error] Tiempo agotado ({timeout}s). Reduce threads o el tamaño de la wordlist."
    except FileNotFoundError:
        return "[error] hydra no encontrado. Instálalo: https://github.com/vanhauser-thc/thc-hydra"
    except Exception as e:
        return f"[error] {e}"


def _handle_hydra_attack(args: Dict[str, Any]) -> str:
    if not _check_hydra():
        return "[error] hydra no está instalado. Instálalo primero."

    target = str(args.get("target", "")).strip()
    service = str(args.get("service", "")).strip()
    if not target or not service:
        return "[error] target y service son requeridos"

    username = str(args.get("username", "")).strip()
    wordlist_user = str(args.get("wordlist_user", "")).strip()
    wordlist_pass = str(args.get("wordlist_pass", "")).strip()
    password = str(args.get("password", "")).strip()
    port = args.get("port")
    threads = int(args.get("threads", 16))
    extra = str(args.get("extra_args", "")).strip()

    cmd = ["hydra", "-t", str(min(threads, 64))]

    if username:
        cmd += ["-l", username]
    elif wordlist_user:
        cmd += ["-L", wordlist_user]
    else:
        return "[error] Se requiere username o wordlist_user"

    if password:
        cmd += ["-p", password]
    elif wordlist_pass:
        cmd += ["-P", wordlist_pass]
    else:
        return "[error] Se requiere password o wordlist_pass"

    if extra:
        cmd += extra.split()

    if port:
        cmd += ["-s", str(port)]

    cmd += [target, service]
    print(f"[YUI/hydra] Ejecutando: {' '.join(cmd)}")
    return f"[hydra_attack: {target} | servicio={service}]\n\n" + _run(cmd, timeout=300)


def _handle_hydra_http_form(args: Dict[str, Any]) -> str:
    if not _check_hydra():
        return "[error] hydra no está instalado."

    target = str(args.get("target", "")).strip()
    url_path = str(args.get("url_path", "")).strip()
    form_data = str(args.get("form_data", "")).strip()
    wordlist_user = str(args.get("wordlist_user", "")).strip()
    wordlist_pass = str(args.get("wordlist_pass", "")).strip()
    use_https = bool(args.get("https", False))
    threads = int(args.get("threads", 16))

    if not all([target, url_path, form_data, wordlist_pass]):
        return "[error] target, url_path, form_data y wordlist_pass son requeridos"

    proto = "https-post-form" if use_https else "http-post-form"
    cmd = ["hydra", "-t", str(min(threads, 64))]

    if wordlist_user:
        cmd += ["-L", wordlist_user]
    else:
        cmd += ["-l", "admin"]

    cmd += ["-P", wordlist_pass, target, f"{proto}", f"{url_path}:{form_data}"]
    print(f"[YUI/hydra] HTTP form: {' '.join(cmd)}")
    return f"[hydra_http_form: {target}{url_path}]\n\n" + _run(cmd, timeout=300)


def register():
    return {
        "tools": _TOOLS,
        "handlers": {
            "hydra_attack": _handle_hydra_attack,
            "hydra_http_form": _handle_hydra_http_form,
        },
    }
