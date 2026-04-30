"""
YUI Plugin — Hashcat
Cracking de hashes por diccionario, fuerza bruta y ataques por reglas con Hashcat.
Para uso en auditorías autorizadas y recuperación de contraseñas propias.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Any, Dict


_HASH_TYPES = {
    "md5": "0",
    "sha1": "100",
    "sha256": "1400",
    "sha512": "1700",
    "bcrypt": "3200",
    "ntlm": "1000",
    "mysql41": "300",
    "sha512crypt": "1800",
    "wpa2": "22000",
    "argon2": "argon2",
}

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "hashcat_crack",
            "description": (
                "Crackea hashes de contraseñas con Hashcat usando diccionario o fuerza bruta. "
                "Soporta MD5, SHA1, SHA256, SHA512, bcrypt, NTLM, WPA2, MySQL y más. "
                "Para recuperación de contraseñas propias o auditorías autorizadas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hash_value": {
                        "type": "string",
                        "description": "Hash o archivo con hashes a crackear. Ej: '5f4dcc3b5aa765d61d8327deb882cf99' o '/ruta/hashes.txt'.",
                    },
                    "hash_type": {
                        "type": "string",
                        "enum": list(_HASH_TYPES.keys()),
                        "description": "Tipo de hash. md5, sha1, sha256, sha512, bcrypt, ntlm, mysql41, sha512crypt, wpa2.",
                    },
                    "attack_mode": {
                        "type": "string",
                        "enum": ["dictionary", "brute_force", "combination", "rules"],
                        "description": (
                            "Modo de ataque: "
                            "dictionary=wordlist, "
                            "brute_force=máscara de caracteres, "
                            "combination=combina dos wordlists, "
                            "rules=wordlist + reglas de mutación."
                        ),
                    },
                    "wordlist": {
                        "type": "string",
                        "description": "Ruta a wordlist (requerido para dictionary, rules, combination).",
                    },
                    "mask": {
                        "type": "string",
                        "description": (
                            "Máscara para brute_force. Ej: '?l?l?l?l?d?d' (4 letras + 2 dígitos). "
                            "?l=minúscula, ?u=mayúscula, ?d=dígito, ?s=especial, ?a=todos."
                        ),
                    },
                    "rules_file": {
                        "type": "string",
                        "description": "Ruta a archivo de reglas para modo rules (opcional). Ej: '/usr/share/hashcat/rules/best64.rule'.",
                    },
                    "wordlist2": {
                        "type": "string",
                        "description": "Segunda wordlist para modo combination.",
                    },
                    "output_file": {
                        "type": "string",
                        "description": "Archivo donde guardar resultados crackeados (opcional).",
                    },
                    "extra_args": {
                        "type": "string",
                        "description": "Argumentos adicionales de hashcat (opcional).",
                    },
                },
                "required": ["hash_value", "hash_type", "attack_mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hashcat_identify",
            "description": "Identifica el tipo probable de un hash desconocido analizando su formato y longitud.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hash_value": {
                        "type": "string",
                        "description": "Hash a identificar.",
                    },
                },
                "required": ["hash_value"],
            },
        },
    },
]


def _check_hashcat() -> bool:
    return shutil.which("hashcat") is not None


def _run(cmd: list, timeout: int = 600) -> str:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace"
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        combined = out + (f"\n[stderr]\n{err}" if err else "")
        if not combined:
            return f"[hashcat] Proceso terminado con código {result.returncode} (sin output)"
        return combined
    except subprocess.TimeoutExpired:
        return f"[error] Tiempo agotado ({timeout}s). El hash puede requerir más tiempo o una wordlist más pequeña."
    except FileNotFoundError:
        return "[error] hashcat no encontrado. Instálalo: https://hashcat.net/hashcat/"
    except Exception as e:
        return f"[error] {e}"


def _handle_hashcat_crack(args: Dict[str, Any]) -> str:
    if not _check_hashcat():
        return "[error] hashcat no está instalado. Descárgalo en https://hashcat.net/hashcat/"

    hash_value = str(args.get("hash_value", "")).strip()
    hash_type = str(args.get("hash_type", "")).strip()
    attack_mode = str(args.get("attack_mode", "dictionary")).strip()
    wordlist = str(args.get("wordlist", "")).strip()
    mask = str(args.get("mask", "")).strip()
    rules_file = str(args.get("rules_file", "")).strip()
    wordlist2 = str(args.get("wordlist2", "")).strip()
    output_file = str(args.get("output_file", "")).strip()
    extra = str(args.get("extra_args", "")).strip()

    if not hash_value or not hash_type:
        return "[error] hash_value y hash_type son requeridos"

    hash_code = _HASH_TYPES.get(hash_type)
    if not hash_code:
        return f"[error] Tipo de hash no soportado: {hash_type}"

    mode_map = {"dictionary": "0", "brute_force": "3", "combination": "1", "rules": "0"}
    attack_code = mode_map[attack_mode]

    cmd = ["hashcat", "-m", hash_code, "-a", attack_code, "--force", hash_value]

    if attack_mode == "dictionary":
        if not wordlist:
            return "[error] dictionary requiere wordlist"
        cmd.append(wordlist)
    elif attack_mode == "brute_force":
        if not mask:
            return "[error] brute_force requiere mask"
        cmd.append(mask)
    elif attack_mode == "combination":
        if not wordlist or not wordlist2:
            return "[error] combination requiere wordlist y wordlist2"
        cmd += [wordlist, wordlist2]
    elif attack_mode == "rules":
        if not wordlist:
            return "[error] rules requiere wordlist"
        cmd.append(wordlist)
        if rules_file:
            cmd += ["-r", rules_file]

    if output_file:
        cmd += ["-o", output_file]

    if extra:
        cmd += extra.split()

    print(f"[YUI/hashcat] Ejecutando: {' '.join(cmd)}")
    return f"[hashcat_crack: {hash_type} | modo={attack_mode}]\n\n" + _run(cmd, timeout=600)


def _handle_hashcat_identify(args: Dict[str, Any]) -> str:
    h = str(args.get("hash_value", "")).strip()
    if not h:
        return "[error] hash_value es requerido"

    length = len(h)
    candidates = []

    if length == 32 and all(c in "0123456789abcdefABCDEF" for c in h):
        candidates.append("MD5 (longitud 32, hex)")
        candidates.append("NTLM (longitud 32, hex)")
    elif length == 40 and all(c in "0123456789abcdefABCDEF" for c in h):
        candidates.append("SHA1 (longitud 40, hex)")
    elif length == 64 and all(c in "0123456789abcdefABCDEF" for c in h):
        candidates.append("SHA256 (longitud 64, hex)")
    elif length == 128 and all(c in "0123456789abcdefABCDEF" for c in h):
        candidates.append("SHA512 (longitud 128, hex)")
    elif h.startswith("$2y$") or h.startswith("$2a$") or h.startswith("$2b$"):
        candidates.append("bcrypt (prefijo $2y/$2a/$2b$)")
    elif h.startswith("$6$"):
        candidates.append("SHA512crypt (prefijo $6$)")
    elif h.startswith("$1$"):
        candidates.append("MD5crypt (prefijo $1$)")
    elif h.startswith("*") and length == 41:
        candidates.append("MySQL4.1/MySQL5+ (prefijo *, longitud 41)")

    if candidates:
        return "Tipos probables:\n" + "\n".join(f"  - {c}" for c in candidates)
    return f"Hash de longitud {length} — no identificado automáticamente. Usa 'hashcat --example-hashes' para comparar manualmente."


def register():
    return {
        "tools": _TOOLS,
        "handlers": {
            "hashcat_crack": _handle_hashcat_crack,
            "hashcat_identify": _handle_hashcat_identify,
        },
    }
