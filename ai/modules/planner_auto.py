from __future__ import annotations

"""
AutoPlanner — multi-step autonomous task execution.

Given a high-level goal, the planner:
  1. Decomposes the goal into an ordered list of sub-tasks (via LLM).
  2. Executes each sub-task using the Reasoner (full agentic loop + tools).
  3. Evaluates the result after each step (via LLM).
  4. Adjusts remaining steps if needed, or aborts on repeated failure.

The planner emits step events through step_fn so Pulso shows progress in real time.
"""

import json
import re
from typing import Any, Callable, Dict, List, Optional


_DECOMPOSE_SYSTEM = """\
Eres un planificador de tareas autónomo. Tu único trabajo es descomponer el objetivo del usuario
en pasos concretos y ejecutables. Responde ÚNICAMENTE con un JSON array de objetos:
[
  {"step": 1, "title": "Título corto", "instruction": "Instrucción precisa para ejecutar este paso"},
  ...
]
Máximo 8 pasos. Cada instrucción debe ser auto-contenida y accionable.
Si el objetivo es simple (1 paso), devuelve un array de 1 elemento.
No incluyas texto fuera del JSON.
"""

_EVAL_SYSTEM = """\
Eres un evaluador de tareas. Dado un paso ejecutado y su resultado, responde SOLO con JSON:
{"ok": true/false, "reason": "breve explicación", "adjustment": "instrucción revisada o null"}
- ok: true si el resultado es satisfactorio para continuar.
- adjustment: si ok es false, una instrucción alternativa para reintentar; si ok es true, null.
"""

_MAX_RETRIES = 2


class AutoPlanner:
    """
    Orchestrates multi-step autonomous execution.
    Call run(goal) — it blocks until completion and returns a summary string.
    """

    def __init__(
        self,
        *,
        chat_fn: Callable[[List[Dict[str, Any]]], str],
        execute_fn: Callable[[str], str],
        step_fn: Optional[Callable[[str, str, Optional[str]], None]] = None,
        model_fast: str = "",
    ):
        self._chat = chat_fn
        self._execute = execute_fn        # runs one sub-task instruction via Reasoner
        self._step_fn = step_fn
        self._model_fast = model_fast
        self._abort = False

    def abort(self) -> None:
        self._abort = True

    # ── Public ────────────────────────────────────────────────────────────────

    def run(self, goal: str) -> str:
        self._abort = False
        self._emit("analysis", "AutoPlanner", f"Descomponiendo: {goal[:80]}")

        steps = self._decompose(goal)
        if not steps:
            return "[AutoPlanner] No se pudo descomponer el objetivo en pasos."

        self._emit("tool_start", "AutoPlanner", f"{len(steps)} pasos planificados")

        results: List[str] = []
        i = 0
        while i < len(steps) and not self._abort:
            step = steps[i]
            title = step.get("title", f"Paso {i+1}")
            instruction = step.get("instruction", "")
            n = i + 1
            total = len(steps)

            self._emit("tool_start", f"Paso {n}/{total}", title)

            result, ok = self._run_step_with_retry(instruction, title, n, total)
            results.append(f"**Paso {n} — {title}**\n{result}")

            if not ok:
                self._emit("tool_end", f"Paso {n}/{total}", f"[error] Abortando tras reintentos fallidos")
                break

            self._emit("tool_end", f"Paso {n}/{total}", title)
            i += 1

        self._emit("tool_end", "AutoPlanner", f"Completado: {i}/{len(steps)} pasos")
        return "\n\n".join(results)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _decompose(self, goal: str) -> List[Dict[str, Any]]:
        messages = [
            {"role": "system", "content": _DECOMPOSE_SYSTEM},
            {"role": "user", "content": f"Objetivo: {goal}"},
        ]
        try:
            raw = self._chat(messages)
            data = _extract_json_array(raw)
            if isinstance(data, list) and data:
                return [s for s in data if isinstance(s, dict) and "instruction" in s]
        except Exception:
            pass
        return []

    def _run_step_with_retry(
        self, instruction: str, title: str, n: int, total: int
    ) -> tuple[str, bool]:
        current_instruction = instruction
        for attempt in range(1, _MAX_RETRIES + 2):
            if self._abort:
                return "[abortado]", False

            result = self._execute(current_instruction)

            eval_ok, reason, adjustment = self._evaluate(title, current_instruction, result)
            if eval_ok:
                return result, True

            if attempt > _MAX_RETRIES:
                return f"{result}\n[evaluación: {reason}]", False

            self._emit("tool_start", f"Paso {n}/{total} (reintento {attempt})", reason)
            if adjustment:
                current_instruction = adjustment

        return result, False

    def _evaluate(self, title: str, instruction: str, result: str) -> tuple[bool, str, Optional[str]]:
        messages = [
            {"role": "system", "content": _EVAL_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Paso: {title}\n"
                    f"Instrucción: {instruction}\n"
                    f"Resultado:\n{result[:1500]}"
                ),
            },
        ]
        try:
            raw = self._chat(messages)
            data = _extract_json_obj(raw)
            if data:
                ok = bool(data.get("ok", True))
                reason = str(data.get("reason", ""))
                adjustment = data.get("adjustment") or None
                return ok, reason, adjustment
        except Exception:
            pass
        return True, "", None

    def _emit(self, event: str, name: str, detail: Optional[str]) -> None:
        if self._step_fn:
            try:
                self._step_fn(event, name, detail)
            except Exception:
                pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_json_array(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return None


def _extract_json_obj(text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return None
