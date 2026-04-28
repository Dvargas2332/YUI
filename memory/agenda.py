from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from memory.store import MemoryStore

# Recurrence helpers
_RECURRENCE_DELTAS = {
    "daily":   timedelta(days=1),
    "weekly":  timedelta(weeks=1),
    "monthly": timedelta(days=30),
}


def _next_due(due_at: str, recurrence: str) -> Optional[str]:
    delta = _RECURRENCE_DELTAS.get(recurrence)
    if delta is None:
        return None
    try:
        dt = datetime.fromisoformat(due_at)
        return (dt + delta).isoformat()
    except Exception:
        return None


class AgendaManager:
    """
    Background thread that checks for due reminders every minute and fires
    a callback so the brain can inject them into the chat.
    """

    def __init__(self, store: MemoryStore, on_reminder: Callable[[str], None]):
        self._store = store
        self._on_reminder = on_reminder
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="agenda-watcher")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception:
                pass
            self._stop_event.wait(timeout=60)

    def _tick(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        due = self._store.agenda_due(now)
        for item in due:
            self._store.agenda_mark_notified(item["id"])

            notes_part = f" — {item['notes']}" if item["notes"] else ""
            msg = f"[Agenda] Recordatorio: **{item['title']}**{notes_part}"
            try:
                self._on_reminder(msg)
            except Exception:
                pass

            # Reschedule if recurring
            next_due = _next_due(item["due_at"], item["recurrence"])
            if next_due:
                self._store.agenda_reschedule(item["id"], next_due)
            else:
                self._store.agenda_mark_done(item["id"])
