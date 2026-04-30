"""
prompt_rules.py — System Prompt y Rules como módulos separados.

- System Prompt: personalidad y rol base de YUI (texto libre)
- Rules: lista de instrucciones adicionales modulares (se pueden agregar/quitar individualmente)

Ambos se combinan en build_full_system() para mandárselo al LLM.
Persisten en data/prompt_rules.json.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "prompt_rules.json"

_DEFAULT_PROMPT = """Eres YUI, una asistente de voz con visión (cámara) y memoria.
Objetivo: sonar viva (cálida, reactiva, curiosa) y ser útil.""".strip()

_DEFAULT_RULES: List[str] = [
    "Responde en español.",
    "Mantén respuestas breves por voz (1–3 frases) salvo que te pidan detalle.",
    "Escribe como conversación hablada: evita Markdown/código y listas largas.",
    "Si hay un usuario identificado por rostro, úsalo por su nombre de forma natural.",
    "Si hay gestos o emoción detectados, úsalos solo como contexto para ajustar el tono.",
    "No menciones gestos/sonrisas/emociones a menos que el usuario lo pida explícitamente.",
    "Si falta info, haz 1 pregunta corta.",
    "No escribas acotaciones teatrales ni acciones entre asteriscos/corchetes/paréntesis.",
    "Usa recuerdos como contexto implícito: no menciones 'memoria' ni que 'recuerdas'.",
    "Si el usuario te acaba de decir un dato, no actúes como si ya lo supieras.",
]


class PromptRulesManager:
    """
    Gestiona System Prompt y Rules de forma independiente.
    Thread-safe. Persiste en JSON.
    """

    def __init__(self, db_path: Path = _DEFAULT_DB):
        self._path = Path(db_path)
        self._lock = threading.RLock()
        self._prompt: str = _DEFAULT_PROMPT
        self._rules: List[str] = list(_DEFAULT_RULES)
        self._load()

    # ── Persistencia ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data: Dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8"))
            self._prompt = str(data.get("system_prompt") or _DEFAULT_PROMPT).strip()
            rules = data.get("rules")
            if isinstance(rules, list):
                self._rules = [str(r) for r in rules if str(r).strip()]
        except Exception as e:
            print(f"[YUI] PromptRulesManager load error: {e}")

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps({"system_prompt": self._prompt, "rules": self._rules},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[YUI] PromptRulesManager save error: {e}")

    # ── System Prompt ─────────────────────────────────────────────────────────

    def get_prompt(self) -> str:
        with self._lock:
            return self._prompt

    def set_prompt(self, text: str) -> None:
        with self._lock:
            self._prompt = (text or "").strip() or _DEFAULT_PROMPT
            self._save()

    def reset_prompt(self) -> None:
        with self._lock:
            self._prompt = _DEFAULT_PROMPT
            self._save()

    # ── Rules ─────────────────────────────────────────────────────────────────

    def get_rules(self) -> List[str]:
        with self._lock:
            return list(self._rules)

    def add_rule(self, rule: str) -> None:
        rule = (rule or "").strip()
        if not rule:
            return
        with self._lock:
            if rule not in self._rules:
                self._rules.append(rule)
                self._save()

    def remove_rule(self, index: int) -> bool:
        with self._lock:
            if 0 <= index < len(self._rules):
                self._rules.pop(index)
                self._save()
                return True
            return False

    def update_rule(self, index: int, rule: str) -> bool:
        rule = (rule or "").strip()
        if not rule:
            return False
        with self._lock:
            if 0 <= index < len(self._rules):
                self._rules[index] = rule
                self._save()
                return True
            return False

    def set_rules(self, rules: List[str]) -> None:
        with self._lock:
            self._rules = [str(r).strip() for r in rules if str(r).strip()]
            self._save()

    def reset_rules(self) -> None:
        with self._lock:
            self._rules = list(_DEFAULT_RULES)
            self._save()

    # ── Construcción del system prompt final ──────────────────────────────────

    def build_full_system(self, extra: Optional[str] = None) -> str:
        """
        Combina prompt base + rules en un solo system prompt para el LLM.
        extra: texto adicional que brain puede inyectar (contexto visual, perfil, etc.)
        """
        with self._lock:
            parts = [self._prompt]
            if self._rules:
                rules_block = "\n".join(f"- {r}" for r in self._rules)
                parts.append(f"\nReglas de conversación:\n{rules_block}")
            if extra:
                parts.append(f"\n{extra.strip()}")
            return "\n".join(parts).strip()

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {"system_prompt": self._prompt, "rules": list(self._rules)}
