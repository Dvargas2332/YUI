from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from memory.store import MemoryStore


_EMPTY_PROFILE: Dict[str, Any] = {
    "name": "",
    "language": "es",
    "occupation": "",
    "projects": [],        # [{"name": "...", "description": "..."}]
    "preferences": [],     # ["responde corto", "no uses emojis", ...]
    "interests": [],       # ["programación", "música", ...]
    "timezone": "",
    "notes": [],           # datos sueltos que no encajan en otra categoría
    "updated_at": "",
}

_PROFILE_FACT_KEY = "user_profile_v1"


class UserProfile:
    """
    Persistent, structured model of the user.
    Stored as a JSON blob in the facts table.
    Updated automatically by the LLM after each conversation turn.
    """

    def __init__(self, store: MemoryStore):
        self._store = store
        self._profile: Dict[str, Any] = self._load()

    # ── Load / save ───────────────────────────────────────────────────────────

    def _load(self) -> Dict[str, Any]:
        raw = self._store.get_preference(_PROFILE_FACT_KEY)
        if raw:
            try:
                data = json.loads(raw)
                # Merge with empty template so new keys always exist
                merged = dict(_EMPTY_PROFILE)
                merged.update(data)
                return merged
            except Exception:
                pass
        return dict(_EMPTY_PROFILE)

    def _save(self) -> None:
        self._profile["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._store.set_preference(_PROFILE_FACT_KEY, json.dumps(self._profile, ensure_ascii=False))

    # ── Read ──────────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return str(self._profile.get("name") or "")

    def is_empty(self) -> bool:
        p = self._profile
        return not any([
            p.get("name"), p.get("occupation"),
            p.get("projects"), p.get("preferences"),
            p.get("interests"), p.get("notes"),
        ])

    def as_system_block(self) -> str:
        """Returns a compact text block to inject into the system prompt."""
        p = self._profile
        lines: List[str] = []

        if p.get("name"):
            lines.append(f"Nombre del usuario: {p['name']}")
        if p.get("occupation"):
            lines.append(f"Ocupación: {p['occupation']}")
        if p.get("timezone"):
            lines.append(f"Zona horaria: {p['timezone']}")
        if p.get("language"):
            lines.append(f"Idioma preferido: {p['language']}")

        projects = p.get("projects") or []
        if projects:
            proj_strs = [f"{pr['name']}: {pr.get('description','')}" if isinstance(pr, dict) else str(pr) for pr in projects[:6]]
            lines.append("Proyectos activos: " + " | ".join(proj_strs))

        prefs = p.get("preferences") or []
        if prefs:
            lines.append("Preferencias: " + ", ".join(prefs[:8]))

        interests = p.get("interests") or []
        if interests:
            lines.append("Intereses: " + ", ".join(interests[:8]))

        notes = p.get("notes") or []
        if notes:
            lines.append("Notas: " + " | ".join(str(n) for n in notes[:4]))

        if not lines:
            return ""
        return "## Perfil del usuario\n" + "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._profile)

    # ── Write (direct) ────────────────────────────────────────────────────────

    def set_name(self, name: str) -> None:
        self._profile["name"] = name.strip()
        self._save()

    def merge(self, updates: Dict[str, Any]) -> None:
        """Merge a partial update dict into the profile."""
        for key, val in updates.items():
            if key not in _EMPTY_PROFILE:
                continue
            existing = self._profile.get(key)
            if isinstance(existing, list) and isinstance(val, list):
                # deduplicate merge for lists
                seen = {_canonical(x) for x in existing}
                for item in val:
                    if _canonical(item) not in seen:
                        existing.append(item)
                        seen.add(_canonical(item))
            elif isinstance(existing, list) and isinstance(val, str):
                if _canonical(val) not in {_canonical(x) for x in existing}:
                    existing.append(val)
            else:
                if val:
                    self._profile[key] = val
        self._save()

    # ── LLM-driven update ─────────────────────────────────────────────────────

    def update_from_conversation(
        self,
        recent_turns: List[Dict[str, str]],
        chat_fn,  # callable(messages) -> str
    ) -> bool:
        """
        Ask the LLM to extract profile updates from recent conversation.
        Returns True if anything changed.
        """
        if not recent_turns:
            return False

        convo_text = "\n".join(
            f"{t['role'].upper()}: {t['content']}" for t in recent_turns[-12:]
        )

        current_json = json.dumps(self._profile, ensure_ascii=False, indent=2)

        prompt = [
            {
                "role": "system",
                "content": (
                    "Analiza la conversación y extrae información nueva o actualizada sobre el usuario. "
                    "Devuelve SOLO un JSON con los campos que cambiarían en el perfil. "
                    "Esquema permitido:\n"
                    "{\n"
                    '  "name": "string",\n'
                    '  "occupation": "string",\n'
                    '  "language": "string",\n'
                    '  "timezone": "string",\n'
                    '  "projects": [{"name":"...","description":"..."}],\n'
                    '  "preferences": ["..."],\n'
                    '  "interests": ["..."],\n'
                    '  "notes": ["..."]\n'
                    "}\n"
                    "Solo incluye los campos que tengan información NUEVA o CORREGIDA. "
                    "Si no hay nada nuevo devuelve {}. No inventes datos."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Perfil actual:\n{current_json}\n\n"
                    f"Conversación reciente:\n{convo_text}"
                ),
            },
        ]

        try:
            raw = chat_fn(prompt).strip()
        except Exception:
            return False

        # Extract JSON from response
        data = _extract_json(raw)
        if not data:
            return False

        before = json.dumps(self._profile, sort_keys=True)
        self.merge(data)
        after = json.dumps(self._profile, sort_keys=True)
        return before != after


# ── Helpers ───────────────────────────────────────────────────────────────────

def _canonical(item: Any) -> str:
    if isinstance(item, dict):
        return item.get("name", str(item)).lower().strip()
    return str(item).lower().strip()


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    # Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass
    # Try extracting first {...} block
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return None
