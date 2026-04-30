from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _git_remote_origin(cwd: str) -> Optional[str]:
    try:
        r = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=cwd, timeout=3,
        )
        return r.stdout.strip() or None
    except Exception:
        return None


def _safe_slug(name: str) -> str:
    import re
    slug = re.sub(r"[^\w\-]", "_", name.lower())
    return slug[:80] or "unknown"


def _repo_name(workspace: str) -> str:
    p = Path(workspace)
    origin = _git_remote_origin(workspace)
    if origin:
        # github.com/user/repo → repo
        name = origin.rstrip("/").split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]
        return _safe_slug(name)
    return _safe_slug(p.name)


class ProjectContext:
    """
    Persistent context for a single repository stored in ~/.yui/projects/<slug>/.

    Saved:
      context.json — metadata, stack, goals, notes
      sessions/    — per-session summary files (one per session, pruned to keep last 20)
      training_pairs/ — (future) Q&A pairs for local model training
    """

    def __init__(self, workspace: str) -> None:
        from config.yui_home import YUI_PROJECTS
        self.workspace = workspace.strip() if workspace else ""
        self._slug = _repo_name(self.workspace) if self.workspace else "unknown"
        self._root = YUI_PROJECTS / self._slug
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / "sessions").mkdir(exist_ok=True)
        (self._root / "training_pairs").mkdir(exist_ok=True)
        self._ctx_path = self._root / "context.json"
        self._data: Dict[str, Any] = self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> Dict[str, Any]:
        try:
            if self._ctx_path.exists():
                raw = json.loads(self._ctx_path.read_text(encoding="utf-8", errors="replace"))
                if isinstance(raw, dict):
                    return raw
        except Exception:
            pass
        return {"slug": self._slug, "workspace": self.workspace, "notes": [], "stack": [], "goals": []}

    def _save(self) -> None:
        try:
            self._data["slug"] = self._slug
            self._data["workspace"] = self.workspace
            self._data["updated_at"] = time.time()
            self._ctx_path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def slug(self) -> str:
        return self._slug

    def get_notes(self) -> List[str]:
        return list(self._data.get("notes") or [])

    def add_note(self, note: str) -> None:
        notes: List[str] = self._data.setdefault("notes", [])
        notes.append(note.strip())
        if len(notes) > 50:
            notes[:] = notes[-50:]
        self._save()

    def set_stack(self, stack: List[str]) -> None:
        self._data["stack"] = [s.strip() for s in stack if s.strip()]
        self._save()

    def get_stack(self) -> List[str]:
        return list(self._data.get("stack") or [])

    def set_goals(self, goals: List[str]) -> None:
        self._data["goals"] = [g.strip() for g in goals if g.strip()]
        self._save()

    def get_goals(self) -> List[str]:
        return list(self._data.get("goals") or [])

    def save_session_summary(self, summary: str) -> None:
        """Appends a session summary file. Prunes to keep last 20."""
        ts = int(time.time())
        fname = f"{ts}.txt"
        path = self._root / "sessions" / fname
        try:
            path.write_text(summary.strip(), encoding="utf-8")
        except Exception:
            return
        # Prune: keep last 20 sessions
        sessions = sorted((self._root / "sessions").glob("*.txt"), key=lambda p: p.stat().st_mtime)
        for old in sessions[:-20]:
            try:
                old.unlink()
            except Exception:
                pass

    def get_recent_sessions(self, n: int = 3) -> List[str]:
        sessions = sorted((self._root / "sessions").glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        result = []
        for s in sessions[:n]:
            try:
                result.append(s.read_text(encoding="utf-8", errors="replace").strip())
            except Exception:
                pass
        return result

    def save_training_pair(self, question: str, answer: str) -> None:
        """Stores a Q&A pair for local model training."""
        ts = int(time.time() * 1000)
        path = self._root / "training_pairs" / f"{ts}.json"
        try:
            path.write_text(
                json.dumps({"q": question, "a": answer, "ts": ts}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def as_system_block(self) -> str:
        """Returns a system prompt block with project context."""
        parts: List[str] = []
        stack = self.get_stack()
        goals = self.get_goals()
        notes = self.get_notes()
        sessions = self.get_recent_sessions(2)

        if stack:
            parts.append("Tech stack: " + ", ".join(stack))
        if goals:
            parts.append("Project goals:\n" + "\n".join(f"- {g}" for g in goals))
        if notes:
            parts.append("Project notes:\n" + "\n".join(f"- {n}" for n in notes[-10:]))
        if sessions:
            parts.append("Recent session context:\n" + "\n---\n".join(sessions))

        if not parts:
            return ""
        header = f"[Project context: {self._slug}]"
        return header + "\n" + "\n\n".join(parts)
