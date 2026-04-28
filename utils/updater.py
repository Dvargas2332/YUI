from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str], cwd: Path = ROOT, timeout: int = 60) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout + r.stderr).strip()
        return r.returncode, out
    except subprocess.TimeoutExpired:
        return 1, "[error] timeout"
    except Exception as e:
        return 1, f"[error] {e}"


def check_updates() -> dict:
    """Returns {'available': bool, 'commits': int, 'summary': str}"""
    # fetch without pulling
    _run(["git", "fetch", "--quiet"])
    code, out = _run(["git", "rev-list", "HEAD..origin/HEAD", "--count"])
    if code != 0:
        return {"available": False, "commits": 0, "summary": "No se pudo verificar (sin conexión o repo sin remote)."}
    try:
        n = int(out.strip())
    except ValueError:
        n = 0
    if n == 0:
        return {"available": False, "commits": 0, "summary": "YUI ya está en la última versión."}

    # get short log of incoming commits
    _, log = _run(["git", "log", "HEAD..origin/HEAD", "--oneline", "--no-decorate"])
    return {"available": True, "commits": n, "summary": log}


def apply_update(
    *,
    on_progress: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    git pull + pip install -r requirements.txt + reinstall vsix if changed.
    Returns {'ok': bool, 'message': str}
    """
    def prog(msg: str):
        if on_progress:
            on_progress(msg)

    prog("Descargando cambios de GitHub…")
    code, out = _run(["git", "pull", "--rebase", "--autostash"])
    if code != 0:
        return {"ok": False, "message": f"git pull falló:\n{out}"}
    prog(f"Git pull:\n{out}")

    req = ROOT / "requirements.txt"
    if req.exists():
        prog("Instalando dependencias nuevas…")
        pip = str(Path(sys.executable).parent / "pip")
        code2, out2 = _run([pip, "install", "-r", str(req), "--quiet"], timeout=120)
        if code2 != 0:
            prog(f"pip install con advertencias:\n{out2}")
        else:
            prog("Dependencias OK.")

    vsix_dir = ROOT / "vscode-extension"
    if vsix_dir.exists():
        vsix_files = sorted(vsix_dir.glob("*.vsix"), key=lambda p: p.stat().st_mtime, reverse=True)
        if vsix_files:
            vsix = vsix_files[0]
            prog(f"Reinstalando extensión VSCode: {vsix.name}…")
            code3, out3 = _run(["code", "--install-extension", str(vsix)], timeout=30)
            if code3 == 0:
                prog("Extensión VSCode actualizada.")
            else:
                prog(f"VSCode install (ignorado): {out3}")

    return {"ok": True, "message": "Actualización completada. Reinicia YUI para aplicar todos los cambios."}
