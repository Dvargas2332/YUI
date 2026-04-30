"""
yui_home.py — Rutas centrales de YUI en el sistema del usuario.

Estructura en ~/.yui/:
  config/   — prompt_rules.json, providers.json, settings.json
  data/     — user_data.db, embeddings, backups
  projects/ — contexto por repo (A+B model)
  logs/     — logs de sesión

~/.yui-model/ — separado, modelo local auto-entrenado (no tocado por YUI)
"""
from __future__ import annotations

import shutil
from pathlib import Path

# ── Raíz de la instalación de YUI (código fuente) ────────────────────────────
PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]

# ── Directorio de usuario — persiste entre actualizaciones ───────────────────
YUI_HOME: Path = Path.home() / ".yui"

# Subdirectorios
YUI_CONFIG  = YUI_HOME / "config"
YUI_DATA    = YUI_HOME / "data"
YUI_BACKUPS = YUI_HOME / "data" / "backups"
YUI_PROJECTS= YUI_HOME / "projects"
YUI_LOGS    = YUI_HOME / "logs"

# Archivos de configuración
PROMPT_RULES_PATH = YUI_CONFIG / "prompt_rules.json"
PROVIDERS_PATH    = YUI_CONFIG / "providers.json"
MEMORY_DB_PATH    = YUI_DATA   / "user_data.db"
SYSTEM_PROFILE_PATH = YUI_DATA / "system_profile.json"


def init_yui_home() -> None:
    """Crea la estructura ~/.yui/ si no existe y migra datos legacy de data/."""
    for d in [YUI_CONFIG, YUI_DATA, YUI_BACKUPS, YUI_PROJECTS, YUI_LOGS]:
        d.mkdir(parents=True, exist_ok=True)

    _migrate_legacy()


def _migrate_legacy() -> None:
    """Mueve archivos de data/ al nuevo ~/.yui/ si aún están en la ruta vieja."""
    legacy_map = {
        PROJECT_ROOT / "data" / "prompt_rules.json" : PROMPT_RULES_PATH,
        PROJECT_ROOT / "data" / "providers.json"    : PROVIDERS_PATH,
        PROJECT_ROOT / "data" / "user_data.db"      : MEMORY_DB_PATH,
        PROJECT_ROOT / "data" / "system_profile.json": SYSTEM_PROFILE_PATH,
    }
    for src, dst in legacy_map.items():
        if src.exists() and not dst.exists():
            try:
                shutil.copy2(src, dst)
                print(f"[YUI] Migrado: {src.name} → {dst}")
            except Exception as e:
                print(f"[YUI] No se pudo migrar {src.name}: {e}")
