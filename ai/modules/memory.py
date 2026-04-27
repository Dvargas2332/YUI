"""
memory.py — Session management, memory retrieval, session voice commands.
"""
from __future__ import annotations

import re
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from memory.store import MemoryStore


class SessionPolicy:
    """
    Handles session management voice commands and auto-summarization.
    Provides YUI with memory of past conversations organized by session.
    """

    _LIST_TRIGGERS = {
        "sesiones", "historial", "mis sesiones", "ver sesiones", "lista sesiones",
        "sesiones anteriores", "conversaciones anteriores", "que hemos hablado",
        "qué hemos hablado", "history", "sessions",
    }
    _RECALL_PREFIXES = (
        "recuerda la sesion", "recuerda la sesión", "abre sesion", "abre sesión",
        "sesion anterior", "sesión anterior", "busca en sesiones", "busca sesion",
        "que dijimos sobre", "qué dijimos sobre",
    )
    _CLOSE_TRIGGERS = {
        "cierra sesion", "cierra sesión", "nueva sesion", "nueva sesión",
        "fin de sesion", "fin de sesión", "termina sesion", "termina sesión",
    }
    _TITLE_PREFIX = "renombra sesion "

    def __init__(self, memory: "MemoryStore"):
        self.memory = memory

    def maybe_handle(self, user_text: str) -> Optional[str]:
        t = (user_text or "").strip()
        low = t.lower().strip()

        if low in self._LIST_TRIGGERS:
            return self._list_sessions()

        if low.startswith(self._TITLE_PREFIX):
            new_title = t[len(self._TITLE_PREFIX):].strip()
            if new_title:
                self.memory.update_session_title(new_title)
                return f"Listo. Esta sesión ahora se llama: \"{new_title}\"."
            return "Dime el nombre: renombra sesion NOMBRE"

        if low in self._CLOSE_TRIGGERS:
            self.memory.close_session()
            return "Sesion cerrada y guardada. La proxima vez que inicies sera una sesion nueva."

        for prefix in self._RECALL_PREFIXES:
            if low.startswith(prefix):
                keyword = t[len(prefix):].strip()
                return self._search_sessions(keyword)

        return None

    def _list_sessions(self) -> str:
        sessions = self.memory.list_sessions(limit=10)
        if not sessions:
            return "No hay sesiones anteriores guardadas aun."
        lines = ["Sesiones recientes:"]
        for i, s in enumerate(sessions, 1):
            date = s.started_at[:10]
            title = s.title if s.title else f"Sesion del {date}"
            lines.append(f"  {i}. [{date}] {title} ({s.message_count} mensajes)")
            if s.summary:
                lines.append(f"     → {s.summary[:120]}")
        return "\n".join(lines)

    def _search_sessions(self, keyword: str) -> str:
        if not keyword:
            return self._list_sessions()
        sessions = self.memory.list_sessions(limit=30)
        kw = keyword.lower()
        matches = [s for s in sessions if kw in f"{s.title} {s.summary}".lower()]
        if not matches:
            matches = self._deep_search(keyword, sessions)
        if not matches:
            return f"No encontre sesiones relacionadas con \"{keyword}\"."
        lines = [f"Sesiones sobre \"{keyword}\":"]
        for s in matches[:5]:
            date = s.started_at[:10]
            title = s.title if s.title else f"Sesion del {date}"
            lines.append(f"  [{date}] {title}")
            if s.summary:
                lines.append(f"  → {s.summary[:150]}")
        return "\n".join(lines)

    def _deep_search(self, keyword: str, sessions) -> list:
        kw = keyword.lower()
        found = []
        for s in sessions[:15]:
            msgs = self.memory.session_messages(s.session_id, limit=50)
            for m in msgs:
                if kw in m.content.lower():
                    found.append(s)
                    break
        return found

    def auto_summarize(self, response: str) -> None:
        r = (response or "").strip()
        if len(r) < 80:
            return
        try:
            with self.memory._connect() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id=?",
                    (self.memory.session_id,),
                ).fetchone()
                count = int(row[0]) if row else 0
            if count % 5 != 0:
                return
            sentences = re.split(r"(?<=[\.\!\?])\s+", r)
            snippet = sentences[0][:200] if sentences else r[:200]
            self.memory.update_session_summary(snippet)
        except Exception:
            pass
