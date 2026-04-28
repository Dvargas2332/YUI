"""
brain.py — Central intelligence router for the YUI agent.

Brain is the single entry point for all cognitive processing. It initializes
and wires the cognitive modules, then coordinates them on every request:

  input
    → context   (VisualContext, workspace state)
    → memory    (session commands, long-term recall)   [modules/memory.py]
    → persona   (style, teaching, macros)              [modules/persona.py]
    → planner   (task orchestration, file audit)       [modules/planner.py]
    → reasoner  (LLM call, agentic loop, tool dispatch)[modules/reasoner.py]
    → synthesizer (spoken vs display output split)     [modules/synthesizer.py]
  output
"""
from __future__ import annotations

import os
import re
import threading
from queue import Queue
from typing import Any, Callable, Dict, List, Optional, Tuple

from config.settings import Settings
from memory.store import MemoryStore
from memory.user_profile import UserProfile
from ai.modules.context import VisualContext
from ai.modules.persona import StylePolicy, MacroPolicy, TeachingModePolicy
from ai.modules.memory import SessionPolicy
from ai.modules.planner import TaskPolicy
from ai.modules.reasoner import Reasoner
from ai.modules.synthesizer import SynthesizedOutput
from ai.modules.vision import build_visual_context_text


class Brain:
    """
    Central router — coordinates all cognitive modules.
    Exposes reply() as the single public interface.
    """

    def __init__(
        self,
        settings: Settings,
        memory: MemoryStore,
        confirm_fn: Optional[Callable[[str], bool]] = None,
        step_fn: Optional[Callable[[str, str, Optional[str]], None]] = None,
    ):
        self.settings = settings
        self.memory = memory

        # Cognitive modules
        self.style = StylePolicy(memory)
        self.macros = MacroPolicy(memory)
        self.teaching = TeachingModePolicy(memory)
        self.sessions = SessionPolicy(memory)
        self.planner = TaskPolicy()
        self.reasoner = Reasoner(
            settings, memory,
            confirm_fn=confirm_fn,
            step_fn=self._make_step_fn(step_fn),
        )

        # User profile (persistent semantic model of the user)
        self.user_profile = UserProfile(memory)

        # State
        self.last_display_text: Optional[str] = None
        self._pending_continuation: Optional[str] = None
        self._continuation_count: int = 0
        self._continuation_max: int = 12
        self._postprocess_lock = threading.Lock()
        self._postprocess_scheduled = False
        self._postprocess_q: Queue = Queue()
        if self.settings.memory_async:
            threading.Thread(target=self._postprocess_worker, daemon=True).start()

    # ── Public interface ──────────────────────────────────────────────────────

    def reply(
        self,
        user_text: str,
        *,
        visual: VisualContext,
        screen_context: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_temperature: Optional[float] = None,
        llm_mode: Optional[str] = None,
        workspace_root: str = "",
    ) -> str:
        user_text = (user_text or "").strip()
        if not user_text:
            return ""

        self.last_display_text = None
        self.planner.on_task_start(user_text)

        # 1) Session commands (list, rename, search, close)
        session_reply = self.sessions.maybe_handle(user_text)
        if session_reply is not None:
            self._store_exchange(user_text, session_reply)
            return session_reply

        # 2) Teaching mode toggle
        teach_reply = self.teaching.maybe_handle(user_text)
        if teach_reply is not None:
            self._store_exchange(user_text, teach_reply)
            return teach_reply

        # 3) Style training (ban phrases, max sentences, etc.)
        style_reply = self.style.maybe_handle_training(user_text)
        if style_reply is not None:
            self._store_exchange(user_text, style_reply)
            return style_reply

        # 4) Macro training / shortcut expansion
        macro_reply = self.macros.maybe_handle_training(user_text)
        if macro_reply is not None:
            self._store_exchange(user_text, macro_reply)
            return macro_reply

        # No API key → simple fallback
        if not self.settings.llm_api_key:
            response = self._fallback_reply(user_text, visual=visual)
            self.memory.add("user", user_text)
            self.memory.add("assistant", response)
            return response

        # 5) Route to correct model/temperature
        if llm_model is None or llm_temperature is None or llm_mode is None:
            llm_model, llm_temperature, llm_mode, _max_tokens = self.reasoner.route(user_text)
        else:
            _max_tokens = 0
        self.reasoner.last_mode = str(llm_mode or "fast")

        # 6) Build message context
        messages = self._build_messages(user_text, visual=visual, screen_context=screen_context, workspace_root=workspace_root)
        self.memory.add("user", user_text)

        # 7) LLM call via Reasoner
        tools_enabled = os.getenv("YUI_TOOLS_ENABLED", "1") not in {"0", "false", "False"}
        raw_response = self.reasoner.call(
            messages,
            model=str(llm_model),
            temperature=float(llm_temperature),
            workspace_root=workspace_root,
            max_tokens=_max_tokens,
            tools_enabled=tools_enabled,
        )

        # 8) Sanitize and apply style
        raw_response = (raw_response or "").strip() or "¿Qué necesitas?"
        raw_response = self._sanitize(raw_response, user_text=user_text)

        # 9) Synthesize: spoken vs display split (teaching mode)
        output = self._synthesize(raw_response, user_text=user_text)
        if output.has_split:
            self.last_display_text = output.display

        response = output.spoken or output.display
        response = response.strip() or "¿Qué necesitas?"

        # 10) Post-task audit
        audit = self.planner.on_task_end(project_root=workspace_root)
        if audit:
            self._pending_continuation = (
                f"El audit post-tarea detectó problemas: {audit}. "
                "Repara las referencias rotas y crea los archivos faltantes sin pedir confirmación."
            )

        # 11) Persist response
        self.memory.add("assistant", response)
        user_id = (visual.user_name or "default").strip()
        if self.settings.memory_async:
            self._schedule_postprocess(user_id=user_id)
        else:
            self._run_postprocess(user_id=user_id)

        # 12) Session auto-summarize
        try:
            self.sessions.auto_summarize(response)
        except Exception:
            pass

        return response

    def preprocess(self, user_text: str) -> str:
        """Expands macro triggers before routing to reply()."""
        return self.macros.expand_or_original(user_text)

    def health_check(self) -> bool:
        return self.reasoner.health_check()

    def route(self, user_text: str) -> Tuple[str, float, str, int]:
        return self.reasoner.route(user_text)

    def get_system_prompt(self) -> str:
        return self.reasoner.get_system_prompt()

    def set_system_prompt(self, prompt: str) -> None:
        self.reasoner.set_system_prompt(prompt)

    def abort(self) -> None:
        self.reasoner.abort()

    def shutdown(self) -> None:
        try:
            self.memory.close_session()
        except Exception:
            pass

    def pop_continuation(self) -> Optional[str]:
        c = self._pending_continuation
        self._pending_continuation = None
        if c:
            self._continuation_count += 1
            if self._continuation_count > self._continuation_max:
                print(f"[YUI] Auto-continuación: límite de {self._continuation_max} iteraciones alcanzado.")
                self._continuation_count = 0
                return None
        else:
            self._continuation_count = 0
        return c

    @property
    def last_mode(self) -> str:
        return getattr(self.reasoner, "last_mode", "fast")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _make_step_fn(self, outer_step_fn) -> Optional[Callable]:
        planner = self.planner

        def wrapped(event: str, tool_name: str, detail: Any) -> None:
            if event == "file_diff":
                warning = planner.on_file_written(tool_name)
                if warning and outer_step_fn:
                    try:
                        outer_step_fn("tool_end", tool_name, f"[advertencia] {warning}")
                    except Exception:
                        pass
            if outer_step_fn:
                try:
                    outer_step_fn(event, tool_name, detail)
                except Exception:
                    pass

        return wrapped

    def _store_exchange(self, user_text: str, response: str) -> None:
        try:
            self.memory.add("user", user_text)
            self.memory.add("assistant", response)
        except Exception:
            pass

    def _build_messages(
        self,
        user_text: str,
        *,
        visual: VisualContext,
        screen_context: Optional[str],
        workspace_root: str,
    ) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.reasoner.get_system_prompt()}
        ]

        # Style + teaching + screen context injected as system messages
        extra_parts: List[str] = []
        style_prompt = self.style.system_prompt()
        if style_prompt:
            extra_parts.append(style_prompt)
        teach_prompt = self.teaching.system_prompt()
        if teach_prompt:
            extra_parts.append(teach_prompt)
        if screen_context:
            extra_parts.append("Contexto de pantalla (no lo repitas literalmente; úsalo para ser más útil):\n" + screen_context.strip())
        if extra_parts:
            messages.append({"role": "system", "content": "\n\n".join(extra_parts)})

        # Workspace root context
        ws = (workspace_root or "").strip()
        if ws:
            messages.append({
                "role": "system",
                "content": (
                    f"Directorio de trabajo actual (workspace del usuario): {ws}\n"
                    "Cuando crees archivos o carpetas con rutas relativas, úsalo como base."
                ),
            })

        # Long-term memories (semantic retrieval)
        user_id = (visual.user_name or "default").strip()
        if (self.settings.memory_use_long_term
                and self.settings.memory_retrieve_k > 0
                and self.reasoner.should_retrieve_long_term(user_text, self.settings.memory_min_query_tokens)):
            memories = self.reasoner.retrieve_relevant_memories(
                user_id=user_id,
                query=user_text,
                k=self.settings.memory_retrieve_k,
                min_score=float(self.settings.memory_min_score or 0.0),
            )
            if memories:
                if self.settings.debug_memory:
                    print(f"[YUI] Memories injected ids={memories['ids']}")
                memories_text = "\n".join([f"- {m}" for m in memories["contents"]])
                messages.append({
                    "role": "system",
                    "content": "Recuerdos relevantes (úsalos de forma natural, sin decir 'según mi memoria'):\n" + memories_text,
                })
                self.memory.mark_memory_used(memories["ids"])

        # User profile (persistent model of who the user is)
        profile_block = self.user_profile.as_system_block()
        if profile_block:
            messages.append({"role": "system", "content": profile_block})

        # Long-term facts
        facts = self.memory.list_facts(limit=self.settings.memory_long_term_facts)
        if facts:
            facts_text = "\n".join([f"- {k}: {v}" for k, v in facts])
            messages.append({"role": "system", "content": f"Memoria a largo plazo (hechos):\n{facts_text}"})

        # Summary
        if self.settings.memory_use_summaries:
            summary = self.memory.latest_summary()
            if summary:
                messages.append({"role": "system", "content": f"Resumen de conversación (memoria): {summary}"})

        # Visual context
        visual_text = build_visual_context_text(visual)
        if visual_text:
            messages.append({"role": "system", "content": visual_text})

        # Short-term conversation history
        for item in self.memory.recent(limit=max(6, self.settings.memory_short_term_turns * 2)):
            if item.role == "system":
                continue
            messages.append({"role": item.role, "content": item.content})

        # Current user message (not yet in memory when this runs)
        messages.append({"role": "user", "content": user_text})

        return messages

    def _synthesize(self, raw_response: str, **_kwargs) -> SynthesizedOutput:
        if self.teaching.enabled and self.teaching.print_full:
            display = self.style.postprocess_display(raw_response) if self.style.enabled else raw_response
            spoken = self.style.postprocess(display) if self.style.enabled else display
            if display.strip() != spoken.strip():
                return SynthesizedOutput.from_split(spoken=spoken, display=display)
            return SynthesizedOutput.from_single(display)

        post = self.style.postprocess if self.style.enabled else None
        spoken = post(raw_response) if post else raw_response
        return SynthesizedOutput.from_single(spoken)

    def _sanitize(self, text: str, *, user_text: Optional[str] = None) -> str:
        if not self.settings.strip_stage_directions:
            return (text or "").strip()
        out = (text or "")
        out = re.sub(r"^\s*yui\s*:\s*", "", out, flags=re.IGNORECASE)
        out = re.sub(r"<tool_call>[\s\S]*?</tool_call>", "", out, flags=re.IGNORECASE)
        out = re.sub(r"<function=\w+>[\s\S]*?</function>", "", out, flags=re.IGNORECASE)
        out = re.sub(r"<parameter=\w+>[\s\S]*?</parameter>", "", out, flags=re.IGNORECASE)
        out = re.sub(r"<tool_call>[\s\S]*$", "", out, flags=re.IGNORECASE)
        out = re.sub(r"<function=\w+>[\s\S]*$", "", out, flags=re.IGNORECASE)
        out = re.sub(r"</?speak\b[^>]*>", " ", out, flags=re.IGNORECASE)
        out = re.sub(r"</?prosody\b[^>]*>", " ", out, flags=re.IGNORECASE)
        out = re.sub(r"<break\b[^>]*>", " ", out, flags=re.IGNORECASE)
        out = re.sub(r"\*\s*[^\*\n]{1,80}\s*\*", " ", out)
        out = re.sub(r"^(?:yo\s+)?(?:asiento|sonr[ií]o|suspiro|me\s+r[ií]o|niego)\b[^\n]{0,60}?[.!?]+\s*", "", out, flags=re.IGNORECASE)
        out = re.sub(r"\bseg[uú]n\s+mi\s+memoria\b", " ", out, flags=re.IGNORECASE)
        out = re.sub(r"\bpor\s+lo\s+que\s+recuerdo\b", " ", out, flags=re.IGNORECASE)
        out = re.sub(r"\b(?:ahora|ya)\s+(?:lo\s+)?recuerdo\b", " ", out, flags=re.IGNORECASE)
        out = re.sub(r"\blo\s+recuerdo\b", " ", out, flags=re.IGNORECASE)
        out = re.sub(r"\bme\s+acuerdo(?:\s+de)?\b", " ", out, flags=re.IGNORECASE)
        out = re.sub(r"\brecuerdo\s+que\b", " ", out, flags=re.IGNORECASE)
        stage_words = ["asiente", "sonríe", "sonrie", "ríe", "rie", "se ríe", "se rie",
                       "suspira", "mira", "parpadea", "guiña", "inclina", "niega"]

        def _strip_leading_star_action(m: re.Match) -> str:
            inner = (m.group(1) or "").strip().lower()
            if any(w in inner for w in stage_words):
                return ""
            return m.group(0)

        out = re.sub(r"^\s*\*\s*([^\n]{1,80}?)(?:\s*[,.;:!?]+(?:\s+|$))", _strip_leading_star_action, out)

        def _strip_action(m: re.Match) -> str:
            inner = (m.group(1) or "").strip().lower()
            if any(w in inner for w in stage_words):
                return " "
            return m.group(0)

        out = re.sub(r"\(\s*([^\)\n]{1,60})\s*\)", _strip_action, out)
        out = re.sub(r"\[\s*([^\]\n]{1,60})\s*\]", _strip_action, out)

        if user_text and not self._user_wants_perception_feedback(user_text):
            out = re.sub(
                r"^(?:yo\s+)?(?:vi|veo|te\s+veo|te\s+estoy\s+viendo|not[ée]|detect[ée])\b[^\n]{0,90}?"
                r"\b(?:gesto|mano|pulgar|sonrisa|c[aá]mara|cara|expresi[óo]n|emoci[óo]n)\b[^\n]{0,90}?[.!?]+\s*",
                "", out, flags=re.IGNORECASE,
            )

        out = re.sub(r"\s+([,.;:!?])", r"\1", out)
        out = re.sub(r"\.\.\.\s*\.", "...", out)
        out = re.sub(r"\.\s+\.", ".", out)
        out = re.sub(r"\s{2,}", " ", out).strip()
        return out

    def _user_wants_perception_feedback(self, user_text: str) -> bool:
        t = (user_text or "").strip().lower()
        keys = ["me ves", "puedes verme", "ves", "cámara", "camara", "qué ves", "que ves",
                "gesto", "mano", "pulgar", "sonrisa", "sonriendo", "cara", "expresión",
                "expresion", "emoción", "emocion", "cómo me veo", "como me veo",
                "estoy enoj", "estoy feliz", "estoy triste", "angust"]
        return any(k in t for k in keys)

    def _fallback_reply(self, user_text: str, *, visual: VisualContext) -> str:
        name = visual.user_name
        t = user_text.lower()
        if any(w in t for w in ["hola", "buenas", "hey"]):
            return f"Hola{(' ' + name) if name else ''}. Estoy aquí. ¿Qué hacemos?"
        if "cómo estás" in t or "como estas" in t:
            return "Estoy bien y atenta. ¿Qué te gustaría que hiciera?"
        if "gracias" in t:
            return "De nada. ¿Seguimos?"
        prefix = f"{name}, " if name else ""
        return f"{prefix}¿Qué necesitas?"

    def _maybe_extract_fact(self, user_text: str) -> None:
        t = user_text.strip()
        low = t.lower()
        if "me llamo" in low:
            name = t.split("me llamo", 1)[-1].strip(" .:;!")
            if name:
                self.memory.upsert_fact("name", name)
                self.user_profile.set_name(name)
                return
        if "mi nombre es" in low:
            idx = low.find("mi nombre es")
            name = t[idx + len("mi nombre es"):].strip(" .:;!")
            if name:
                self.memory.upsert_fact("name", name)
                self.user_profile.set_name(name)
                return
        if "me dicen" in low:
            idx = low.find("me dicen")
            name = t[idx + len("me dicen"):].strip(" .:;!")
            if name:
                self.memory.upsert_fact("name", name)
                self.user_profile.set_name(name)
                return
        if low.startswith("recuerda que "):
            rest = t[len("recuerda que "):].strip()
            if rest.lower().startswith("mi ") and " es " in rest.lower():
                after_mi = rest[3:]
                parts = after_mi.split(" es ", 1)
                if len(parts) == 2:
                    key = parts[0].strip().replace(" ", "_").lower()
                    value = parts[1].strip(" .:;!")
                    if key and value:
                        self.memory.upsert_fact(key, value)

    def _schedule_postprocess(self, *, user_id: str) -> None:
        with self._postprocess_lock:
            if self._postprocess_scheduled:
                return
            self._postprocess_scheduled = True
        self._postprocess_q.put((user_id or "default").strip())

    def _postprocess_worker(self) -> None:
        while True:
            user_id = self._postprocess_q.get()
            try:
                if user_id is None:
                    return
                self._run_postprocess(user_id=str(user_id))
            except Exception as e:
                print(f"[YUI] Postprocess error: {type(e).__name__}: {e}")
            finally:
                with self._postprocess_lock:
                    self._postprocess_scheduled = False
                try:
                    self._postprocess_q.task_done()
                except Exception:
                    pass

    def _run_postprocess(self, *, user_id: str) -> None:
        n = int(self.settings.memory_summary_every_n_messages or 0)
        self.reasoner.summarize(n)
        n_mem = int(self.settings.memory_extract_every_n_turns or 0)
        self.reasoner.extract_memories(user_id=user_id, n=n_mem)
        # Update persistent user profile from recent conversation
        try:
            recent = self.memory.recent(limit=12)
            turns = [{"role": it.role, "content": it.content} for it in recent if it.role != "system"]
            if turns:
                changed = self.user_profile.update_from_conversation(
                    turns,
                    chat_fn=lambda msgs: self.reasoner._chat(
                        msgs,
                        model=self.settings.llm_model_fast,
                        temperature=0.1,
                    ),
                )
                if changed and os.getenv("YUI_DEBUG_MEMORY", "0") not in {"0", "false"}:
                    print(f"[YUI] Perfil de usuario actualizado: {self.user_profile.name}")
        except Exception:
            pass
