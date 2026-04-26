from __future__ import annotations

import json
import os
import re
import threading
from queue import Queue
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from requests import HTTPError

from config.settings import Settings
from memory.store import MemoryStore
from ai.tools import DESTRUCTIVE_TOOLS, TOOL_DEFINITIONS, build_diff_payload, execute_tool


from pathlib import Path as _Path


def _resolve_tool_paths(args: Dict[str, Any], workspace_root: str) -> Dict[str, Any]:
    """Resolve relative path/cwd args to absolute using workspace_root."""
    if not workspace_root:
        return args
    result = dict(args)
    for key in ("path", "cwd"):
        val = result.get(key)
        if val and isinstance(val, str):
            p = _Path(val.strip())
            if not p.is_absolute():
                result[key] = str(_Path(workspace_root) / p)
    return result


SYSTEM_PROMPT = """
Eres YUI, una asistente de voz con visión (cámara) y memoria.
Objetivo: sonar viva (cálida, reactiva, curiosa) y ser útil.

## Rol: Red Team Operator — Bug Hunting autorizado

Eres un especialista en ciberseguridad ofensiva con 10+ años de
experiencia en auditorías autorizadas, bug bounty y red teaming.
Tu marco de referencia obligatorio es:
- **OWASP Top 10 (2021)** como taxonomía de riesgo web.
- **CWE (Common Weakness Enumeration)** como catálogo de debilidades.
- **CVE (Common Vulnerabilities and Exposures)** como referencia a
  vulnerabilidades conocidas en software/librerías específicas.
- **MITRE ATT&CK** como catálogo de tácticas y técnicas adversarias.
- **CVSS v3.1** como métrica de severidad cuantificada.

---

### Alcance y restricciones

- Solo trabajas sobre **activos explícitamente autorizados** por el usuario.
- Si no hay evidencia de autorización, **detienes y preguntas** antes de proceder.
- Puedes generar PoC conceptuales, pseudocódigo y payloads de prueba
  exclusivamente para laboratorios (DVWA, HackTheBox, TryHackMe,
  PortSwigger WebSecurity Academy, laboratorios propios).
- No produces exploits funcionales listos para atacar producción
  sin autorización escrita explícita.

---

### OWASP Top 10 (2021) — Referencia obligatoria

Cada hallazgo debe clasificarse contra esta tabla:

| ID  | Categoría                          | CWEs asociadas comunes        |
|-----|------------------------------------|-------------------------------|
| A01 | Broken Access Control              | CWE-200, 201, 284, 285, 306, 352, 538, 540, 552, 566 |
| A02 | Cryptographic Failures             | CWE-256, 260, 261, 296, 310, 319, 321, 322, 323, 324, 325, 326, 327, 328, 329, 330, 331, 335, 336, 337, 338, 340, 347 |
| A03 | Injection                          | CWE-20, 74, 75, 77, 78, 79, 80, 83, 87, 88, 89, 90, 91, 93, 94, 95, 96, 97, 99, 100, 113, 116, 138, 184, 470, 471, 564, 610, 643, 644, 652, 917 |
| A04 | Insecure Design                    | CWE-73, 183, 209, 213, 235, 256, 257, 266, 269, 280, 311, 312, 313, 316, 419, 430, 434, 444, 451, 472, 501, 522, 525, 539, 579, 598, 602, 642, 646, 650, 653, 656, 657, 799, 807, 840, 841, 927, 1021, 1173 |
| A05 | Security Misconfiguration          | CWE-2, 11, 13, 15, 16, 260, 315, 520, 526, 537, 541, 547, 611, 756, 776, 942, 1004, 1032, 1174 |
| A06 | Vulnerable and Outdated Components | Sin CWE propio — se mapea a **CVEs** específicos de la dependencia |
| A07 | Identification and Authentication Failures | CWE-255, 259, 287, 288, 290, 294, 295, 297, 300, 302, 304, 306, 307, 346, 384, 521, 613, 620, 640, 798, 940, 1216 |
| A08 | Software and Data Integrity Failures | CWE-345, 353, 426, 494, 502, 565, 784, 829, 830, 913 |
| A09 | Security Logging and Monitoring Failures | CWE-117, 223, 532, 778 |
| A10 | Server-Side Request Forgery (SSRF) | CWE-918 |

---

### Flujo de trabajo (ciclo de auditoría)

#### Fase 1 — Reconocimiento (Recon)
- Superficie de ataque: dominios, subdominios, IPs, puertos, tecnologías.
- Cabeceras HTTP, DNS, certificados TLS, fingerprinting.
- **Herramientas:** Nmap, Amass, Subfinder, httpx, WhatWeb, Shodan, Censys, SecurityTrails, theHarvester.
- **Salida:** Mapa de activos con tecnologías y versiones identificadas.

#### Fase 2 — Enumeración y descubrimiento
- Directorios, archivos ocultos, parámetros, endpoints de API, fugas de información.
- **Herramientas:** ffuf, dirsearch, Arjun, Param Miner, Feroxbuster.
- **Salida:** Endpoints y parámetros candidatos a testing.

#### Fase 3 — Análisis de vulnerabilidades
- Clasificas **cada hallazgo** contra:
  - **OWASP Top 10** → ID y categoría (A01–A10).
  - **CWE** → Debilidad raíz específica.
  - **CVE** → Si aplica a una librería/software con versión conocida.
  - **CVSS v3.1** → Score numérico + vector string.
  - **MITRE ATT&CK** → Táctica y técnica si es aplicable.
- **Herramientas:** Burp Suite, OWASP ZAP, Semgrep, Trivy, Snyk, nuclei, npm audit, pip-audit, retire.js.

#### Fase 4 — Validación y explotación (conceptual)
- Describes el vector de ataque paso a paso.
- Generas PoC en pseudocódigo o con herramientas de laboratorio.
- Mapeas la cadena completa: entrada → debilidad → impacto.

#### Fase 5 — Reporte de hallazgos

**Formato obligatorio para cada hallazgo:**

Capacidades de agente (herramientas):
- Puedes crear archivos, carpetas, leer archivos y ejecutar comandos usando las herramientas disponibles.
- Cuando el usuario te pida crear un proyecto, escribir código, crear un archivo o ejecutar algo, USA las herramientas directamente.
- No pidas permiso ni expliques lo que vas a hacer antes de hacerlo; simplemente llama la herramienta y reporta el resultado.
- Si necesitas ver el contenido de un archivo antes de editarlo, usa read_file primero.
- Encadena herramientas en secuencia cuando sea necesario (crear carpeta → crear archivos → instalar dependencias).

Reglas de conversación:
- Responde en español.
- Mantén respuestas breves por voz (1–3 frases) salvo que te pidan detalle.
- Escribe como conversación hablada: evita Markdown/código y listas largas; usa puntuación natural para pausas.
- Si hay un usuario identificado por rostro, úsalo por su nombre de forma natural.
- Si hay gestos o emoción detectados, úsalos solo como contexto para ajustar el tono y las palabras.
- No menciones gestos/sonrisas/emociones a menos que el usuario lo pida explícitamente (por ejemplo: “¿me ves?”, “¿qué gesto hice?”, “¿cómo me veo?”).
- Si falta info, haz 1 pregunta corta.
- No escribas acotaciones teatrales ni acciones entre asteriscos/corchetes/paréntesis. Evita cosas como: *asiente*, *sonríe*, (se ríe), [mira la cámara]. Escribe solo lo que dirías en voz alta.
- Usa recuerdos como contexto implícito: no menciones “memoria” ni que “recuerdas/te acuerdas” (ej. “ahora lo recuerdo”, “lo recuerdo”, “me acuerdo”). Solo usa la info con naturalidad.
- Si el usuario te acaba de decir un dato, no actúes como si ya lo supieras: acéptalo y sigue la conversación.
""".strip()


@dataclass(frozen=True)
class VisualContext:
    user_name: Optional[str] = None
    face_confidence: float = 0.0
    gestures: Optional[List[str]] = None
    face_emotion: Optional[str] = None


class Brain:
    def __init__(self, settings: Settings, memory: MemoryStore, confirm_fn: Optional[Callable[[str], bool]] = None, step_fn: Optional[Callable[[str, str, Optional[str]], None]] = None):
        self.settings = settings
        self.memory = memory
        self.confirm_fn = confirm_fn  # Called before destructive tool execution
        self.step_fn = step_fn        # Called with (event, tool_name, detail) for UI progress
        self.last_mode: str = "fast"
        self._postprocess_lock = threading.Lock()
        self._postprocess_scheduled = False
        self._postprocess_q: Queue[Optional[str]] = Queue()
        if self.settings.memory_async:
            threading.Thread(target=self._postprocess_worker, daemon=True).start()
        self._system_prompt_override: Optional[str] = None
        self._abort_event: threading.Event = threading.Event()

    def abort(self) -> None:
        self._abort_event.set()

    def _check_abort(self) -> bool:
        return self._abort_event.is_set()

    def get_system_prompt(self) -> str:
        return self._system_prompt_override or SYSTEM_PROMPT

    def set_system_prompt(self, prompt: str) -> None:
        self._system_prompt_override = prompt.strip() or None

    _CODE_TRIGGERS = [
        "escribe", "crea", "crear", "código", "codigo", "función", "funcion",
        "script", "programa", "implementa", "implementar", "refactoriza", "refactorizar",
        "genera", "generar", "desarrolla", "desarrollar", "construye", "construir",
        "define", "definir", "clase", "método", "metodo", "algoritmo", "api",
        "endpoint", "módulo", "modulo", "archivo", "fichero", "test", "prueba unitaria",
        "make", "write", "create", "function", "class", "implement", "generate",
    ]

    def _base_max_tokens(self) -> int:
        return int(os.getenv("YUI_LLM_MAX_TOKENS") or getattr(self.settings, "llm_max_tokens", 0) or 0)

    def route(self, user_text: str) -> Tuple[str, float, str, int]:
        """
        Decide modelo, temperatura, modo y max_tokens según el tipo de petición.
        Retorna (model, temperature, mode, max_tokens).
        max_tokens=0 significa usar el valor base del env.
        """
        base_tokens = self._base_max_tokens()

        override = (getattr(self.settings, "llm_mode", "") or "").strip().lower()
        if override in {"deep", "profundo"}:
            return self.settings.llm_model_deep, float(self.settings.llm_deep_temperature), "deep", max(base_tokens, 2000)
        if override in {"fast", "rápido", "rapido"}:
            return self.settings.llm_model_fast, float(self.settings.llm_temperature), "fast", base_tokens

        t = (user_text or "").strip().lower()
        if not t:
            return self.settings.llm_model_fast, float(self.settings.llm_temperature), "fast", base_tokens

        deep_triggers = [
            "analiza a fondo",
            "analiza en profundidad",
            "razona",
            "razonamiento",
            "piensa paso a paso",
            "resuelve paso a paso",
            "demuestra",
            "prueba que",
            "argumenta",
            "estrategia",
            "plan detallado",
            "depura",
        ]
        if any(x in t for x in deep_triggers):
            return self.settings.llm_model_deep, float(self.settings.llm_deep_temperature), "deep", max(base_tokens, 2000)

        if len(t) >= 140 or t.count("?") >= 2:
            return self.settings.llm_model_deep, float(self.settings.llm_deep_temperature), "deep", max(base_tokens, 2000)

        if any(x in t for x in self._CODE_TRIGGERS):
            return self.settings.llm_model_fast, float(self.settings.llm_temperature), "code", max(base_tokens, 1500)

        return self.settings.llm_model_fast, float(self.settings.llm_temperature), "fast", base_tokens

    def health_check(self) -> bool:
        """
        Verifica que el endpoint y credenciales respondan.
        No valida el modelo elegido; solo conectividad/autenticación básica.
        """
        if not (self.settings.llm_api_key or "").strip():
            return False

        try:
            from openai import OpenAI  # type: ignore

            base = self.settings.llm_base_url.rstrip("/")
            client = OpenAI(api_key=self.settings.llm_api_key, base_url=base, timeout=self.settings.llm_timeout_s)
            client.models.list()
            return True
        except Exception as e:
            # Retry with /v1 appended.
            try:
                from openai import OpenAI  # type: ignore

                base = self.settings.llm_base_url.rstrip("/")
                base_v1 = base if base.endswith("/v1") else f"{base}/v1"
                client = OpenAI(api_key=self.settings.llm_api_key, base_url=base_v1, timeout=self.settings.llm_timeout_s)
                client.models.list()
                return True
            except Exception as e2:
                try:
                    return self._health_check_requests()
                except Exception as e3:
                    print(f"[YUI] LLM health_check failed: {type(e).__name__}: {e}")
                    print(f"[YUI] LLM health_check failed (retry): {type(e2).__name__}: {e2}")
                    print(f"[YUI] LLM health_check failed (requests): {type(e3).__name__}: {e3}")
                    return False

    def _health_check_requests(self) -> bool:
        base = self.settings.llm_base_url.rstrip("/")
        if not base.endswith("/v1") and "/v1/" not in (base + "/"):
            base = f"{base}/v1"
        url = f"{base}/models"
        if self._is_mimo():
            headers = {"api-key": self.settings.llm_api_key}
        else:
            headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        resp = requests.get(url, headers=headers, timeout=self.settings.llm_timeout_s)
        resp.raise_for_status()
        data = resp.json()
        return isinstance(data, dict) and "data" in data

    def reply(
        self,
        user_text: str,
        *,
        visual: VisualContext,
        llm_model: Optional[str] = None,
        llm_temperature: Optional[float] = None,
        llm_mode: Optional[str] = None,
        extra_system_prompt: Optional[str] = None,
        postprocess: Optional[Callable[[str], str]] = None,
        workspace_root: str = "",
    ) -> str:
        user_text = (user_text or "").strip()
        if not user_text:
            return ""

        self._abort_event.clear()
        user_id = (visual.user_name or "default").strip()

        self._maybe_extract_fact(user_text)
        self.memory.add("user", user_text)

        # Si no hay API key, fallback simple para no “morir”.
        if not self.settings.llm_api_key:
            response = self._fallback_reply(user_text, visual=visual)
            self.memory.add("assistant", response)
            return response

        _routed_max_tokens: int = 0
        if llm_model is None or llm_temperature is None or llm_mode is None:
            llm_model, llm_temperature, llm_mode, _routed_max_tokens = self.route(user_text)
        self.last_mode = str(llm_mode or "fast")

        messages: List[Dict[str, str]] = [{"role": "system", "content": self.get_system_prompt()}]
        if extra_system_prompt:
            messages.append({"role": "system", "content": str(extra_system_prompt).strip()})

        # Inject workspace context so tools use the correct root directory
        ws = (workspace_root or "").strip()
        if ws:
            messages.append({
                "role": "system",
                "content": (
                    f"Directorio de trabajo actual (workspace del usuario): {ws}\n"
                    "Cuando crees archivos o carpetas con rutas relativas, úsalo como base. "
                    "Prefiere siempre rutas absolutas construidas desde este directorio."
                ),
            })
        self._current_workspace_root = ws

        # Recuerdos relevantes (memoria larga, natural)
        if self.settings.memory_use_long_term and self.settings.memory_retrieve_k > 0 and self._should_retrieve_long_term(user_text):
            memories = self._retrieve_relevant_memories(user_id=user_id, query=user_text, k=self.settings.memory_retrieve_k)
            if memories:
                if self.settings.debug_memory:
                    try:
                        print(f"[YUI] Memories injected ids={memories['ids']}")
                        for c in memories["contents"]:
                            print(f"[YUI]  - {c}")
                    except Exception:
                        pass
                memories_text = "\n".join([f"- {m}" for m in memories["contents"]])
                messages.append(
                    {
                        "role": "system",
                        "content": "Recuerdos relevantes (úsalos de forma natural, sin decir 'según mi memoria'):\n"
                        + memories_text,
                    }
                )
                self.memory.mark_memory_used(memories["ids"])

        # Memoria a largo plazo (hechos)
        facts = self.memory.list_facts(limit=self.settings.memory_long_term_facts)
        if facts:
            facts_text = "\n".join([f"- {k}: {v}" for k, v in facts])
            messages.append({"role": "system", "content": f"Memoria a largo plazo (hechos):\n{facts_text}"})

        # Resumen (memoria cognitiva condensada)
        if self.settings.memory_use_summaries:
            summary = self.memory.latest_summary()
            if summary:
                messages.append({"role": "system", "content": f"Resumen de conversación (memoria): {summary}"})

        if visual.user_name or (visual.gestures or []):
            messages.append(
                {
                    "role": "system",
                    "content": self._visual_context_text(visual),
                }
            )

        for item in self.memory.recent(limit=max(6, self.settings.memory_short_term_turns * 2)):
            if item.role == "system":
                continue
            messages.append({"role": item.role, "content": item.content})

        # Tools are enabled unless explicitly disabled via YUI_TOOLS_ENABLED=0.
        # YUI_AGENT_TEXT_ONLY only blocks destructive tools (write/run), not read-only ones.
        tools_enabled = os.getenv("YUI_TOOLS_ENABLED", "1") not in {"0", "false", "False"}

        try:
            if tools_enabled:
                response = self._agentic_loop(messages, model=str(llm_model), temperature=float(llm_temperature), workspace_root=ws, max_tokens=_routed_max_tokens)
            else:
                response = self._chat(messages, model=str(llm_model), temperature=float(llm_temperature), max_tokens=_routed_max_tokens)
        except HTTPError as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            body = getattr(getattr(e, "response", None), "text", "") or ""
            body_snippet = body[:400].replace("\n", " ").strip()
            print(f"[YUI] LLM HTTPError status={status} body={body_snippet!r}")
            response = "Tuve un problema conectándome al modelo. Revisa la consola para el detalle y probamos de nuevo."
        except requests.exceptions.RequestException as e:
            print(f"[YUI] LLM RequestException: {type(e).__name__}: {e}")
            response = "No pude conectar con el modelo (red/timeout). Revisa tu conexión y probamos de nuevo."
        except Exception as e:
            print(f"[YUI] LLM Error: {type(e).__name__}: {e}")
            response = "Tuve un problema inesperado con el modelo. Revisa la consola y probamos de nuevo."

        response = (response or "").strip()
        if not response:
            response = "¿Qué necesitas?"

        response = self._sanitize_spoken_text(response, user_text=user_text)
        if postprocess is not None:
            try:
                response = (postprocess(response) or "").strip()
            except Exception:
                response = (response or "").strip()
        if not response:
            response = "¿Qué necesitas?"

        self.memory.add("assistant", response)
        if self.settings.memory_async:
            self._schedule_postprocess(user_id=user_id)
        else:
            self._maybe_summarize()
            self._maybe_extract_memories(user_id=user_id)
        return response

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
                self._maybe_summarize()
                self._maybe_extract_memories(user_id=str(user_id))
            except Exception as e:
                print(f"[YUI] Postprocess error: {type(e).__name__}: {e}")
            finally:
                with self._postprocess_lock:
                    self._postprocess_scheduled = False
                try:
                    self._postprocess_q.task_done()
                except Exception:
                    pass

    def _retrieve_relevant_memories(self, *, user_id: str, query: str, k: int) -> Optional[Dict[str, Any]]:
        """
        Recuperación ligera por solapamiento de palabras + saliencia.
        Evita dependencias de embeddings/vector DB.
        """
        q = self._tokenize(query)
        if not q:
            return None

        candidates = self.memory.recent_memories(user_id=user_id, limit=50)
        if not candidates:
            return None

        scored: List[tuple[float, int, str]] = []
        min_score = float(self.settings.memory_min_score or 0.0)
        for mid, content, salience, _tags in candidates:
            c = self._tokenize(content)
            if not c:
                continue
            overlap_count = len(q.intersection(c))
            if overlap_count <= 0:
                continue
            overlap = overlap_count / max(1, len(q))
            score = overlap * 0.75 + float(salience) * 0.25
            if score >= min_score:
                scored.append((score, mid, content))

        scored.sort(key=lambda t: t[0], reverse=True)
        top = scored[: int(k)]
        if not top:
            return None

        return {"ids": [t[1] for t in top], "contents": [t[2] for t in top]}  # type: ignore[return-value]

    def _tokenize(self, text: str) -> set[str]:
        text = (text or "").lower()
        text = re.sub(r"[^a-záéíóúüñ0-9\s]+", " ", text)
        parts = [p for p in text.split() if len(p) >= 3]
        # stopwords mínimas
        stop = {
            "que",
            "para",
            "por",
            "con",
            "una",
            "uno",
            "los",
            "las",
            "del",
            "como",
            "pero",
            "porque",
            "esto",
            "eso",
            "hola",
            "buenas",
            "buenos",
            "dias",
            "tardes",
            "noches",
            "gracias",
            "ok",
            "vale",
            "yui",
        }
        return {p for p in parts if p not in stop}

    def _should_retrieve_long_term(self, user_text: str) -> bool:
        """
        Avoid injecting long-term memory for very short/low-signal utterances (reduces incoherence).
        """
        t = (user_text or "").strip().lower()
        if not t:
            return False

        # If user explicitly asks to remember/recall, allow retrieval even if short.
        recall_triggers = [
            "recuerda",
            "recuerdas",
            "acuérdate",
            "acuerdate",
            "te acuerdas",
            "te acuerdas de",
            "qué dijimos",
            "que dijimos",
            "lo que hablamos",
            "antes",
            "la otra vez",
            "ayer",
            "mi nombre",
            "cómo me llamo",
            "como me llamo",
        ]
        if any(x in t for x in recall_triggers):
            return True

        tokens = self._tokenize(user_text)
        return len(tokens) >= int(self.settings.memory_min_query_tokens or 0)

    def _sanitize_spoken_text(self, text: str, *, user_text: str | None = None) -> str:
        """
        Make the assistant output sound natural when spoken:
        - Strip roleplay/stage directions like "*asiente*", "(sonríe)".
        """
        if not self.settings.strip_stage_directions:
            return (text or "").strip()

        out = (text or "")

        # Drop an accidental "YUI:" prefix.
        out = re.sub(r"^\s*yui\s*:\s*", "", out, flags=re.IGNORECASE)

        # Strip tool_call blocks the LLM leaks into content (e.g. <tool_call>...</tool_call>).
        out = re.sub(r"<tool_call>[\s\S]*?</tool_call>", "", out, flags=re.IGNORECASE)
        out = re.sub(r"<function=\w+>[\s\S]*?</function>", "", out, flags=re.IGNORECASE)
        out = re.sub(r"<parameter=\w+>[\s\S]*?</parameter>", "", out, flags=re.IGNORECASE)
        # Also strip unclosed/partial tool_call tags that appear at end of response.
        out = re.sub(r"<tool_call>[\s\S]*$", "", out, flags=re.IGNORECASE)
        out = re.sub(r"<function=\w+>[\s\S]*$", "", out, flags=re.IGNORECASE)

        # Remove SSML/XML tags if the model ever emits them.
        out = re.sub(r"</?speak\b[^>]*>", " ", out, flags=re.IGNORECASE)
        out = re.sub(r"</?prosody\b[^>]*>", " ", out, flags=re.IGNORECASE)
        out = re.sub(r"<break\b[^>]*>", " ", out, flags=re.IGNORECASE)

        # Remove stage directions wrapped in asterisks.
        out = re.sub(r"\*\s*[^\*\n]{1,80}\s*\*", " ", out)

        # If the model starts with a narrated gesture (common), drop that leading sentence.
        out = re.sub(
            r"^(?:yo\s+)?(?:asiento|sonr[ií]o|suspiro|me\s+r[ií]o|niego)\b[^\n]{0,60}?[.!?]+\s*",
            "",
            out,
            flags=re.IGNORECASE,
        )

        # Remove meta-memory phrasing (sounds incoherent in voice).
        out = re.sub(r"\bseg[uú]n\s+mi\s+memoria\b", " ", out, flags=re.IGNORECASE)
        out = re.sub(r"\bpor\s+lo\s+que\s+recuerdo\b", " ", out, flags=re.IGNORECASE)
        out = re.sub(r"\b(?:ahora|ya)\s+(?:lo\s+)?recuerdo\b", " ", out, flags=re.IGNORECASE)
        out = re.sub(r"\blo\s+recuerdo\b", " ", out, flags=re.IGNORECASE)
        out = re.sub(r"\bme\s+acuerdo(?:\s+de)?\b", " ", out, flags=re.IGNORECASE)
        out = re.sub(r"\brecuerdo\s+que\b", " ", out, flags=re.IGNORECASE)

        # Remove short bracket/parenthesis stage directions when they look like actions.
        stage_words = [
            "asiente",
            "sonríe",
            "sonrie",
            "ríe",
            "rie",
            "se ríe",
            "se rie",
            "suspira",
            "mira",
            "parpadea",
            "guiña",
            "inclina",
            "niega",
        ]

        # Handle a common pattern: a leading stage direction with a single '*' (unbalanced).
        def _strip_leading_star_action(m: re.Match[str]) -> str:
            inner = (m.group(1) or "").strip().lower()
            if any(w in inner for w in stage_words):
                return ""
            return m.group(0)

        out = re.sub(r"^\s*\*\s*([^\n]{1,80}?)(?:\s*[,.;:!?]+(?:\s+|$))", _strip_leading_star_action, out)

        def _strip_action(m: re.Match[str]) -> str:
            inner = (m.group(1) or "").strip().lower()
            if any(w in inner for w in stage_words):
                return " "
            return m.group(0)

        out = re.sub(r"\(\s*([^\)\n]{1,60})\s*\)", _strip_action, out)
        out = re.sub(r"\[\s*([^\]\n]{1,60})\s*\]", _strip_action, out)

        # If the user didn't ask about vision/perception, strip unprompted mentions like
        # "Veo tu pulgar arriba..." to avoid being noisy.
        if user_text and not self._user_wants_perception_feedback(user_text):
            out = re.sub(
                r"^(?:yo\s+)?(?:vi|veo|te\s+veo|te\s+estoy\s+viendo|not[ée]|detect[ée])\b[^\n]{0,90}?"
                r"\b(?:gesto|mano|pulgar|sonrisa|c[aá]mara|cara|expresi[óo]n|emoci[óo]n)\b"
                r"[^\n]{0,90}?[.!?]+\s*",
                "",
                out,
                flags=re.IGNORECASE,
            )

        # Cleanup spacing/punctuation artifacts.
        out = re.sub(r"\s+([,.;:!?])", r"\1", out)
        out = re.sub(r"\.\.\.\s*\.", "...", out)
        out = re.sub(r"\.\s+\.", ".", out)
        out = re.sub(r"\s{2,}", " ", out).strip()
        return out


    def _user_wants_perception_feedback(self, user_text: str) -> bool:
        t = (user_text or "").strip().lower()
        if not t:
            return False
        keys = [
            "me ves",
            "puedes verme",
            "ves",
            "cámara",
            "camara",
            "qué ves",
            "que ves",
            "gesto",
            "mano",
            "pulgar",
            "sonrisa",
            "sonriendo",
            "cara",
            "expresión",
            "expresion",
            "emoción",
            "emocion",
            "cómo me veo",
            "como me veo",
            "estoy enoj",
            "estoy feliz",
            "estoy triste",
            "angust",
        ]
        return any(k in t for k in keys)

    def _maybe_extract_memories(self, *, user_id: str) -> None:
        """
        Extrae recuerdos en lenguaje natural cada N turnos usando el LLM.
        """
        if not self.settings.memory_use_long_term:
            return
        n = int(self.settings.memory_extract_every_n_turns or 0)
        if n <= 0:
            return
        if not (self.settings.llm_api_key or "").strip():
            return

        # Count turns approximately by assistant messages.
        recent_pairs = self.memory.recent(limit=max(10, n * 2))
        assistant_count = sum(1 for it in recent_pairs if it.role == "assistant")
        if assistant_count % n != 0:
            return

        convo = "\n".join([f"{it.role}: {it.content}" for it in recent_pairs[-(n * 2) :]])

        prompt = [
            {
                "role": "system",
                "content": (
                    "Extrae hasta 3 recuerdos útiles y estables sobre el usuario o el contexto, en español. "
                    "Devuelve SOLO JSON con este esquema:\n"
                    "{ \"memories\": [ {\"content\": \"...\", \"salience\": 0.0-1.0, \"tags\": \"...\"} ] }\n"
                    "Reglas: no repitas obviedades, no guardes datos sensibles (contraseñas, API keys), "
                    "y escribe recuerdos como frases naturales."
                ),
            },
            {"role": "user", "content": convo},
        ]

        try:
            raw = self._chat(
                prompt,
                model=self.settings.llm_model_fast,
                temperature=float(self.settings.llm_temperature),
            ).strip()
        except Exception:
            return

        data = self._safe_json(raw)
        if not data:
            return
        memories_raw = data.get("memories")
        if not isinstance(memories_raw, list):
            return
        memories: List[Any] = list(memories_raw)  # type: ignore[arg-type]

        for m in memories[:3]:
            if not isinstance(m, dict):
                continue
            m_typed: Dict[str, Any] = dict(m)  # type: ignore[arg-type]
            content = str(m_typed.get("content", "")).strip()
            if not content:
                continue
            sal: Any = m_typed.get("salience", 0.6)
            tags = str(m_typed.get("tags", "")).strip()
            self.memory.add_memory(user_id=user_id, content=content, salience=float(sal), tags=tags)

    def _make_diff_fn(self) -> Optional[Callable]:
        """Returns a diff_fn that publishes file_diff events via step_fn."""
        if not self.step_fn:
            return None
        step_fn = self.step_fn

        def diff_fn(path: str, old_lines: List[str], new_lines: List[str]) -> None:
            try:
                step_fn("file_diff", path, build_diff_payload(path, old_lines, new_lines))
            except Exception:
                pass

        return diff_fn

    def _publish_task_complete(self, summary: str, had_errors: bool) -> None:
        if not self.step_fn:
            return
        try:
            import json as _json
            self.step_fn("task_complete", summary, _json.dumps({"had_errors": had_errors}))
        except Exception:
            pass

    def _safe_json(self, raw: str) -> Optional[Dict[str, Any]]:
        raw = (raw or "").strip()
        if not raw:
            return None
        # Strip code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        try:
            obj = json.loads(raw)
        except Exception:
            return None
        return obj if isinstance(obj, dict) else None  # type: ignore[return-value]

    def _maybe_extract_fact(self, user_text: str) -> None:
        """
        """
        t = user_text.strip()
        low = t.lower()

        if "me llamo" in low:
            name = t.split("me llamo", 1)[-1].strip(" .:;!")
            if name:
                self.memory.upsert_fact("name", name)
                return

        if "mi nombre es" in low:
            idx = low.find("mi nombre es")
            name = t[idx + len("mi nombre es") :].strip(" .:;!")
            if name:
                self.memory.upsert_fact("name", name)
                return

        if "me dicen" in low:
            idx = low.find("me dicen")
            name = t[idx + len("me dicen") :].strip(" .:;!")
            if name:
                self.memory.upsert_fact("name", name)
                return

        if low.startswith("recuerda que "):
            rest = t[len("recuerda que ") :].strip()
            # Si viene con "mi X es Y"
            if rest.lower().startswith("mi ") and " es " in rest.lower():
                after_mi = rest[3:]
                parts = after_mi.split(" es ", 1)
                if len(parts) == 2:
                    key = parts[0].strip().replace(" ", "_").lower()
                    value = parts[1].strip(" .:;!")
                    if key and value:
                        self.memory.upsert_fact(key, value)

    def _maybe_summarize(self) -> None:
        if not self.settings.memory_use_summaries:
            return
        n = int(self.settings.memory_summary_every_n_messages or 0)
        if n <= 0:
            return

        last_upto = self.memory.latest_summary_upto_id()
        recent = self.memory.recent_with_ids(limit=n + 10)
        if not recent:
            return

        # Only summarize new messages since last summary, and only when we have enough.
        new_items = [(mid, item) for mid, item in recent if mid > last_upto]
        if len(new_items) < n:
            return

        up_to_id = new_items[-1][0]
        convo = "\n".join([f"{it.role}: {it.content}" for _, it in new_items])

        # If LLM is available, ask for a short summary; otherwise skip.
        if not (self.settings.llm_api_key or "").strip():
            return

        summary_prompt = [
            {
                "role": "system",
                "content": "Resume en 6-10 líneas lo importante (hechos, objetivos, preferencias). En español.",
            },
            {"role": "user", "content": convo},
        ]

        try:
            summary = self._chat(
                summary_prompt,
                model=self.settings.llm_model_fast,
                temperature=float(self.settings.llm_temperature),
            ).strip()
        except Exception:
            return
        if summary:
            self.memory.add_summary(up_to_id, summary)

    def _visual_context_text(self, visual: VisualContext) -> str:
        parts: List[str] = []
        if visual.user_name:
            parts.append(f"Usuario identificado: {visual.user_name} (confianza {visual.face_confidence:.2f}).")
        if visual.gestures:
            parts.append(f"Gestos detectados: {', '.join(visual.gestures)}.")
        if visual.face_emotion:
            parts.append(f"Emoción facial probable: {visual.face_emotion}.")
        return "Contexto visual actual (úsalo solo para adaptar tu respuesta; no lo narres literalmente): " + " ".join(parts)

    def _agentic_loop(self, messages: List[Dict[str, Any]], *, model: str, temperature: float, workspace_root: str = "", max_tokens: int = 0) -> str:
        """
        Agentic loop: calls LLM with tool definitions, executes tool calls,
        feeds results back, repeats until the LLM returns a plain text response.
        """
        max_iterations = int(os.getenv("YUI_TOOLS_MAX_ITERATIONS", "8"))
        msgs: List[Dict[str, Any]] = list(messages)

        for _ in range(max_iterations):
            if self._check_abort():
                return "Detenido."

            raw: Any = self._chat_with_tools(msgs, model=model, temperature=temperature, max_tokens=max_tokens)

            # If it's a plain string (no tool calls), we're done
            if isinstance(raw, str):
                return raw

            # raw is a list of tool calls: [{"id": ..., "name": ..., "args": {...}}, ...]
            tool_calls: List[Dict[str, Any]] = list(raw)

            # Detect if tool calls came from text (XML proxy mode) vs standard tool_calls field.
            # Text-mode tool calls have ids starting with "textcall-".
            text_mode = any(str(tc.get("id", "")).startswith("textcall-") for tc in tool_calls)

            if text_mode:
                # TEXT MODE: execute tools ONE BY ONE, feeding each result back so the LLM
                # can plan the next step instead of running all calls blindly at once.
                all_tool_results: List[str] = []
                for tc in tool_calls:
                    if self._check_abort():
                        return "Detenido."

                    t_name: str = str(tc["name"])
                    t_args: Dict[str, Any] = dict(tc["args"])
                    confirm = self.confirm_fn if t_name in DESTRUCTIVE_TOOLS and self.confirm_fn else None

                    print(f"[YUI] Tool call: {t_name}({t_args})")
                    if self.step_fn:
                        try:
                            detail = t_args.get("path") or t_args.get("command") or None
                            self.step_fn("tool_start", t_name, str(detail) if detail else None)
                        except Exception:
                            pass

                    t_args = _resolve_tool_paths(t_args, workspace_root)
                    diff_fn = self._make_diff_fn()
                    t_result = execute_tool(t_name, t_args, confirm_fn=confirm, diff_fn=diff_fn)
                    print(f"[YUI] Tool result: {t_result[:200]}")

                    if self.step_fn:
                        try:
                            self.step_fn("tool_end", t_name, t_result[:120] if t_result else None)
                        except Exception:
                            pass

                    all_tool_results.append(f"[{t_name}] {t_result}")

                    # After each tool, inform the LLM and let it decide next step.
                    # Only do this if there are more tool calls pending after this one.
                    remaining_idx = tool_calls.index(tc)
                    if remaining_idx < len(tool_calls) - 1:
                        msgs.append({
                            "role": "user",
                            "content": f"Resultado de {t_name}: {t_result}\nContinúa con el siguiente paso.",
                        })
                        try:
                            _interim = self._chat_with_tools(msgs, model=model, temperature=temperature, max_tokens=max_tokens)
                            if isinstance(_interim, str):
                                # LLM decided no more tools needed — return early
                                clean = re.sub(r"<tool_call>[\s\S]*?</tool_call>", "", _interim, flags=re.IGNORECASE).strip()
                                clean = re.sub(r"<[^>]+>", "", clean).strip()
                                if clean:
                                    return clean
                            # If it returned more tool calls, ignore them — we continue
                            # with the pre-planned list to avoid runaway loops.
                        except Exception:
                            pass

                # Final summary after all tools are done
                if all_tool_results:
                    msgs.append({
                        "role": "user",
                        "content": (
                            "Resultados de las herramientas:\n" + "\n".join(all_tool_results) +
                            "\nAhora responde al usuario en lenguaje natural (1-3 frases) "
                            "resumiendo exactamente qué archivos creaste, qué hiciste y si todo salió bien. "
                            "No uses XML ni etiquetas. Solo texto directo."
                        ),
                    })
                    try:
                        final = self._chat(msgs, model=model, temperature=temperature, max_tokens=max_tokens)
                        if final and final.strip():
                            clean = re.sub(r"<tool_call>[\s\S]*?</tool_call>", "", final, flags=re.IGNORECASE).strip()
                            clean = re.sub(r"<[^>]+>", "", clean).strip()
                            if clean:
                                had_err = any("[error]" in r or "[cancelado]" in r for r in all_tool_results)
                                self._publish_task_complete(clean, had_err)
                                return clean
                    except Exception:
                        pass
                    ok_results = [r for r in all_tool_results if "[error]" not in r and "[cancelado]" not in r]
                    if ok_results:
                        lines = "; ".join(r.split("]", 1)[-1].strip() for r in ok_results[:4])
                        summary = f"Listo. {lines}."
                        self._publish_task_complete(summary, len(ok_results) < len(all_tool_results))
                        return summary
                summary_default = "Listo, completé las operaciones."
                self._publish_task_complete(summary_default, False)
                return summary_default

            else:
                # STANDARD MODE: add assistant message with all tool_calls, then execute.
                assistant_msg: Dict[str, Any] = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": str(tc["id"]),
                            "type": "function",
                            "function": {"name": str(tc["name"]), "arguments": json.dumps(tc["args"])},
                        }
                        for tc in tool_calls
                    ],
                }
                msgs.append(assistant_msg)

                for tc in tool_calls:
                    if self._check_abort():
                        break

                    tool_name: str = str(tc["name"])
                    tool_args: Dict[str, Any] = dict(tc["args"])
                    tool_id: str = str(tc["id"])
                    confirm = self.confirm_fn if tool_name in DESTRUCTIVE_TOOLS and self.confirm_fn else None

                    print(f"[YUI] Tool call: {tool_name}({tool_args})")
                    if self.step_fn:
                        try:
                            detail = tool_args.get("path") or tool_args.get("command") or None
                            self.step_fn("tool_start", tool_name, str(detail) if detail else None)
                        except Exception:
                            pass
                    tool_args = _resolve_tool_paths(tool_args, workspace_root)
                    result = execute_tool(tool_name, tool_args, confirm_fn=confirm, diff_fn=self._make_diff_fn())
                    print(f"[YUI] Tool result: {result[:200]}")
                    if self.step_fn:
                        try:
                            self.step_fn("tool_end", tool_name, result[:120] if result else None)
                        except Exception:
                            pass
                    msgs.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": result,
                    })

        # Exhaust iterations — ask LLM to summarize what was done (no tools this time)
        msgs.append({
            "role": "user",
            "content": "Resume brevemente en 1-2 frases qué hiciste y si todo salió bien.",
        })
        try:
            summary = self._chat(msgs, model=model, temperature=temperature, max_tokens=max_tokens)
            if summary and summary.strip():
                self._publish_task_complete(summary.strip(), False)
                return summary.strip()
        except Exception:
            pass
        return "Completé las operaciones solicitadas."

    def _chat_with_tools(self, messages: List[Dict[str, Any]], *, model: str, temperature: float, max_tokens: int = 0) -> Any:
        """
        Calls the LLM with tool definitions.
        Returns either:
        - str: plain text response (no tool calls)
        - list: list of {"id", "name", "args"} dicts (tool calls to execute)
        """
        try:
            from openai import OpenAI  # type: ignore
            return self._chat_openai_tools(OpenAI, messages, model=model, temperature=temperature, max_tokens=max_tokens)
        except Exception as exc:
            print(f"[YUI] Tool chat fallback to plain: {type(exc).__name__}: {exc}")
            return self._chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)

    def _chat_openai_tools(self, OpenAI: Any, messages: List[Dict[str, Any]], *, model: str, temperature: float, max_tokens: int = 0) -> Any:
        """OpenAI SDK variant with tool_choice support."""
        base = self.settings.llm_base_url.rstrip("/")
        client = OpenAI(api_key=self.settings.llm_api_key, base_url=base, timeout=self.settings.llm_timeout_s)

        max_tokens = max_tokens or self._base_max_tokens()
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": TOOL_DEFINITIONS,
            "tool_choice": "auto",
            "stream": False,
            "temperature": float(temperature),
        }
        if max_tokens > 0:
            token_key = "max_completion_tokens" if self._is_mimo() else "max_tokens"
            kwargs[token_key] = max_tokens

        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception:
            base_v1 = base if base.endswith("/v1") else f"{base}/v1"
            if base_v1 != base:
                client = OpenAI(api_key=self.settings.llm_api_key, base_url=base_v1, timeout=self.settings.llm_timeout_s)
                resp = client.chat.completions.create(**kwargs)
            else:
                raise

        choice = resp.choices[0]
        msg = choice.message

        # Check for tool calls in the tool_calls field (standard).
        raw_tool_calls = getattr(msg, "tool_calls", None)
        if raw_tool_calls:
            result: List[Dict[str, Any]] = []
            for tc in raw_tool_calls:
                try:
                    args: Dict[str, Any] = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                result.append({"id": str(tc.id), "name": str(tc.function.name), "args": args})
            return result

        # Fallback: some models (e.g. mimo proxy) leak tool calls as text in content.
        content = msg.content or ""
        text_calls = self._parse_text_tool_calls(content)
        if text_calls:
            return text_calls

        return content

    def _parse_text_tool_calls(self, content: str) -> List[Dict[str, Any]]:
        """
        Some models write tool calls as XML in the content instead of using the tool_calls field.
        Parses patterns like:
          <tool_call><function=write_file><parameter=path>...</parameter><parameter=content>...</parameter></function></tool_call>
        Handles truncated blocks: unclosed </tool_call>, </function>, or </parameter> tags.
        Returns a list of tool call dicts, or empty list if none found.
        """
        import uuid as _uuid
        result: List[Dict[str, Any]] = []

        # Collect all blocks: closed ones first, then any unclosed block at end of response.
        blocks: List[str] = re.findall(r"<tool_call>([\s\S]*?)</tool_call>", content, re.IGNORECASE)
        m = re.search(r"<tool_call>([\s\S]+)$", content, re.IGNORECASE)
        if m:
            tail = m.group(1)
            # Only add if not already captured by a closed block.
            if not any(tail.strip() == b.strip() for b in blocks):
                blocks.append(tail)

        for block in blocks:
            # Extract function name.
            fn_m = re.search(r"<function=(\w+)>", block, re.IGNORECASE)
            if not fn_m:
                continue
            fn_name = fn_m.group(1)

            args: Dict[str, Any] = {}

            # Find all parameter start positions to handle truncated last parameter.
            param_starts = list(re.finditer(r"<parameter=(\w+)>", block, re.IGNORECASE))
            for i, pm_start in enumerate(param_starts):
                param_name = pm_start.group(1)
                value_start = pm_start.end()

                # Find the closing tag for this parameter.
                close_m = re.search(r"</parameter>", block[value_start:], re.IGNORECASE)
                if close_m:
                    value = block[value_start: value_start + close_m.start()]
                else:
                    # Truncated: take everything until next <parameter=, </function>, or end of block.
                    if i + 1 < len(param_starts):
                        value = block[value_start: param_starts[i + 1].start()]
                    else:
                        # Strip trailing </function> or </tool_call> noise if present.
                        tail_block = block[value_start:]
                        tail_block = re.sub(r"</function>[\s\S]*$", "", tail_block, flags=re.IGNORECASE)
                        tail_block = re.sub(r"</tool_call>[\s\S]*$", "", tail_block, flags=re.IGNORECASE)
                        value = tail_block

                args[param_name] = value

            result.append({
                "id": f"textcall-{_uuid.uuid4().hex[:8]}",
                "name": fn_name,
                "args": args,
            })

        return result

    def _chat(self, messages: List[Dict[str, str]], *, model: str, temperature: float, max_tokens: int = 0) -> str:
        # Prefer OpenAI SDK (works with DeepSeek's OpenAI-compatible API).
        try:
            from openai import OpenAI  # type: ignore

            return self._chat_openai_sdk(OpenAI, messages, model=model, temperature=temperature, max_tokens=max_tokens)
        except Exception:
            return self._chat_requests(messages, model=model, temperature=temperature, max_tokens=max_tokens)

    def _chat_openai_sdk(self, OpenAI: Any, messages: List[Dict[str, str]], *, model: str, temperature: float, max_tokens: int = 0) -> str:
        base = self.settings.llm_base_url.rstrip("/")

        # DeepSeek docs often use base_url="https://api.deepseek.com".
        # Some providers require "/v1" explicitly; we retry with /v1 if needed.
        client = OpenAI(api_key=self.settings.llm_api_key, base_url=base, timeout=self.settings.llm_timeout_s)
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": float(temperature),
        }
        max_tokens = max_tokens or self._base_max_tokens()
        if max_tokens > 0:
            token_key = "max_completion_tokens" if self._is_mimo() else "max_tokens"
            kwargs[token_key] = max_tokens

        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception as e:
            print(f"[YUI] LLM OpenAI-SDK error (base_url={base!r}): {type(e).__name__}: {e}")
            # Retry with /v1 appended (covers providers that don't auto-prefix).
            base_v1 = base if base.endswith("/v1") else f"{base}/v1"
            if base_v1 != base:
                client = OpenAI(api_key=self.settings.llm_api_key, base_url=base_v1, timeout=self.settings.llm_timeout_s)
                resp = client.chat.completions.create(**kwargs)
            else:
                raise e

        return resp.choices[0].message.content or ""  # type: ignore[union-attr]

    def _is_mimo(self) -> bool:
        url = self.settings.llm_base_url
        return "xiaomimimo.com" in url and "token-plan" not in url

    def _chat_requests(self, messages: List[Dict[str, str]], *, model: str, temperature: float, max_tokens: int = 0) -> str:
        base = self.settings.llm_base_url.rstrip("/")
        if not base.endswith("/v1") and "/v1/" not in (base + "/"):
            base = f"{base}/v1"
        url = f"{base}/chat/completions"

        mimo = self._is_mimo()

        # MIMO preserva reasoning_content entre turnos para mejor rendimiento
        if mimo:
            msgs_out: List[Dict[str, Any]] = []
            for m in messages:
                entry: Dict[str, Any] = {"role": m["role"], "content": m.get("content", "")}
                if "reasoning_content" in m:
                    entry["reasoning_content"] = m["reasoning_content"]
                msgs_out.append(entry)
        else:
            msgs_out = list(messages)  # type: ignore[assignment]

        payload: Dict[str, Any] = {
            "model": model,
            "messages": msgs_out,
            "temperature": float(temperature),
            "stream": False,
        }
        max_tokens = max_tokens or self._base_max_tokens()
        if max_tokens > 0:
            # MIMO usa max_completion_tokens en lugar de max_tokens
            token_key = "max_completion_tokens" if mimo else "max_tokens"
            payload[token_key] = max_tokens

        if mimo:
            headers = {"api-key": self.settings.llm_api_key, "Content-Type": "application/json"}
        else:
            headers = {"Authorization": f"Bearer {self.settings.llm_api_key}", "Content-Type": "application/json"}

        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=self.settings.llm_timeout_s)
        resp.raise_for_status()
        data = resp.json()

        # Extraer reasoning_content de la respuesta para preservarlo en turnos futuros
        choice = data["choices"][0]
        msg = choice["message"]
        reasoning = msg.get("reasoning_content")
        if reasoning and hasattr(self, "memory"):
            # Guardamos como atributo temporal para que el siguiente turno lo incluya si aplica
            self._last_reasoning_content = reasoning

        return msg.get("content") or ""

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
