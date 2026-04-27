"""
planner.py — Task orchestration, multi-file planning, file verification, reference checking.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Set


_MULTIFILE_TRIGGERS = [
    "tema", "theme", "plugin", "proyecto", "project", "web", "sitio", "site",
    "wordpress", "wp", "php", "aplicacion", "aplicación", "app", "sistema",
    "modulo", "módulo", "carpeta", "estructura", "scaffold", "template",
    "varios archivos", "multiple files", "crear todo", "crea todo",
]


def is_multifile_task(user_text: str) -> bool:
    low = user_text.lower()
    return any(t in low for t in _MULTIFILE_TRIGGERS)


class FilePlan:
    """Tracks which files YUI planned to create vs which ones were actually written."""

    def __init__(self) -> None:
        self._planned: List[str] = []
        self._written: Set[str] = set()
        self._active = False

    def activate(self, planned_files: List[str]) -> None:
        self._planned = [p.strip() for p in planned_files if p.strip()]
        self._written = set()
        self._active = True

    def reset(self) -> None:
        self._planned = []
        self._written = set()
        self._active = False

    def mark_written(self, path: str) -> None:
        name = Path(path).name
        self._written.add(name)
        self._written.add(path)

    @property
    def active(self) -> bool:
        return self._active

    def missing(self) -> List[str]:
        if not self._active:
            return []
        result = []
        for p in self._planned:
            name = Path(p).name
            if name not in self._written and p not in self._written:
                result.append(p)
        return result

    def summary(self) -> str:
        total = len(self._planned)
        done = total - len(self.missing())
        return f"{done}/{total} archivos creados"


_TRUNCATION_PATTERNS = [
    r"<\w+[^>]*$",
    r"\becho\s+'<$",
    r"\bfunction\s+\w+\s*\($",
    r"[,\(\[\{]\s*$",
    r"\\\s*$",
]
_COMPILED = [re.compile(p, re.MULTILINE) for p in _TRUNCATION_PATTERNS]


def detect_truncation(content: str) -> Optional[str]:
    if not content or not content.strip():
        return "archivo vacío"
    lines = [l for l in content.splitlines() if l.strip()]
    tail = "\n".join(lines[-3:]) if lines else ""
    for pat in _COMPILED:
        if pat.search(tail):
            return f"línea final parece incompleta: {lines[-1].strip()!r}"
    opens  = content.count("{") + content.count("(") + content.count("[")
    closes = content.count("}") + content.count(")") + content.count("]")
    imbalance = opens - closes
    if imbalance > 3:
        return f"desequilibrio de {imbalance} bloques abiertos sin cerrar"
    return None


def verify_written_file(path: str) -> Optional[str]:
    try:
        p = Path(path)
        if not p.exists():
            return f"el archivo {path} no existe después de escribirlo"
        content = p.read_text(encoding="utf-8", errors="replace")
        return detect_truncation(content)
    except Exception as e:
        return f"no se pudo leer para verificar: {e}"


_REF_PATTERNS = [
    re.compile(r"get_template_part\(['\"]([^'\"]+)['\"]"),
    re.compile(r"include\s+['\"]([^'\"]+)['\"]"),
    re.compile(r"require\s+['\"]([^'\"]+)['\"]"),
    re.compile(r"require_once\s+['\"]([^'\"]+)['\"]"),
    re.compile(r"include_once\s+['\"]([^'\"]+)['\"]"),
    re.compile(r"@import\s+['\"]([^'\"]+)['\"]"),
]


def find_references(content: str) -> List[str]:
    refs = []
    for pat in _REF_PATTERNS:
        for m in pat.finditer(content):
            refs.append(m.group(1))
    return refs


def check_missing_references(written_files: Set[str], project_root: str) -> List[str]:
    missing = []
    root = Path(project_root)
    for fpath in written_files:
        p = Path(fpath) if Path(fpath).is_absolute() else root / fpath
        if not p.exists() or not p.is_file():
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for ref in find_references(content):
            ref_path = ref if "." in Path(ref).name else ref + ".php"
            candidate = root / ref_path
            if not candidate.exists():
                entry = f"{p.name} → {ref_path}"
                if entry not in missing:
                    missing.append(entry)
    return missing


class TaskPolicy:
    """
    Wraps multi-file tasks with pre-execution planning, post-write verification,
    and post-task audit for missing files and broken references.
    """

    def __init__(self) -> None:
        self.plan = FilePlan()
        self._last_audit: Optional[str] = None

    def on_task_start(self, _user_text: str) -> None:
        self.plan.reset()
        self.plan.activate([])
        self._last_audit = None

    def on_file_written(self, path: str) -> Optional[str]:
        self.plan.mark_written(path)
        return verify_written_file(path)

    def on_task_end(self, project_root: str = "") -> Optional[str]:
        issues: List[str] = []
        missing_planned = self.plan.missing()
        if missing_planned:
            issues.append("Archivos planificados no creados: " + ", ".join(missing_planned))
        if project_root and self.plan._written:
            broken_refs = check_missing_references(self.plan._written, project_root)
            if broken_refs:
                issues.append("Referencias rotas entre archivos: " + "; ".join(broken_refs[:8]))
        self.plan.reset()
        if issues:
            self._last_audit = " | ".join(issues)
            return self._last_audit
        return None

    def audit_message(self) -> Optional[str]:
        return self._last_audit
