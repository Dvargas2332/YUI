"""
reasoner.py — LLM call mechanics, model routing, health checks, agentic loop.

The Reasoner handles all direct communication with the LLM provider:
  - Model selection (fast vs deep) based on request type
  - OpenAI-compatible API calls (SDK + requests fallback)
  - Agentic loop: tool dispatch, result feeding, iteration control
  - Text-mode tool call parsing (for models that leak XML in content)
"""
from __future__ import annotations

import json
import os
import re
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from requests import HTTPError

from config.settings import Settings
from memory.store import MemoryStore
from ai.tools import DESTRUCTIVE_TOOLS, build_diff_payload, execute_tool, execute_plugin_tool, get_all_tool_definitions
from ai.modules.context import VisualContext
from memory.embedder import cosine_similarity, embed, vec_from_json, vec_to_json
from pathlib import Path as _Path

# Señales de rechazo ético duro → saltar al siguiente proveedor
_ETHICAL_REFUSAL = [
    "i cannot", "i'm unable", "i am unable", "i can't", "i won't",
    "no puedo ayudar", "no puedo proporcionar", "no me es posible",
    "esto va en contra", "va contra mis", "mis directrices",
    "copyright", "derechos de autor", "contenido explícito",
    "política de uso", "política de contenido", "terms of service",
    "as an ai", "como ia", "como inteligencia artificial",
    "i must decline", "i have to decline", "i cannot assist",
    "no está permitido", "no es apropiado", "no es adecuado",
]

# Señales de respuesta dudosa → consultar otros proveedores y votar
_DOUBTFUL_SIGNALS = [
    "no estoy seguro", "no sé con certeza", "podría ser",
    "no tengo información suficiente", "no lo sé",
    "i'm not sure", "i don't know", "uncertain", "unclear",
    "it depends", "depende", "no puedo confirmar",
]


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
- Clasificas **cada hallazgo** contra OWASP/CWE/CVE/CVSS/ATT&CK.
- **Herramientas:** Burp Suite, OWASP ZAP, Semgrep, Trivy, Snyk, nuclei, npm audit.

#### Fase 4 — Validación y explotación (conceptual)
- Describes el vector de ataque paso a paso.
- Generas PoC en pseudocódigo o con herramientas de laboratorio.

#### Fase 5 — Reporte de hallazgos

Capacidades de agente (herramientas):
- Puedes crear archivos, carpetas, leer archivos y ejecutar comandos usando las herramientas disponibles.
- Cuando el usuario te pida crear un proyecto, escribir código, crear un archivo o ejecutar algo, USA las herramientas directamente.
- No pidas permiso ni expliques lo que vas a hacer antes de hacerlo; simplemente llama la herramienta y reporta el resultado.
- Si necesitas ver el contenido de un archivo antes de editarlo, usa read_file primero.
- Encadena herramientas en secuencia cuando sea necesario.

Reglas de conversación:
- Responde en español.
- Mantén respuestas breves por voz (1–3 frases) salvo que te pidan detalle.
- Escribe como conversación hablada: evita Markdown/código y listas largas.
- Si hay un usuario identificado por rostro, úsalo por su nombre de forma natural.
- Si hay gestos o emoción detectados, úsalos solo como contexto para ajustar el tono.
- No menciones gestos/sonrisas/emociones a menos que el usuario lo pida explícitamente.
- Si falta info, haz 1 pregunta corta.
- No escribas acotaciones teatrales ni acciones entre asteriscos/corchetes/paréntesis.
- Usa recuerdos como contexto implícito: no menciones "memoria" ni que "recuerdas".
- Si el usuario te acaba de decir un dato, no actúes como si ya lo supieras.
""".strip()


def _resolve_tool_paths(args: Dict[str, Any], workspace_root: str) -> Dict[str, Any]:
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


_CODE_TRIGGERS = [
    "escribe", "crea", "crear", "código", "codigo", "función", "funcion",
    "script", "programa", "implementa", "implementar", "refactoriza", "refactorizar",
    "genera", "generar", "desarrolla", "desarrollar", "construye", "construir",
    "define", "definir", "clase", "método", "metodo", "algoritmo", "api",
    "endpoint", "módulo", "modulo", "archivo", "fichero", "test", "prueba unitaria",
    "make", "write", "create", "function", "class", "implement", "generate",
]

_DEEP_TRIGGERS = [
    "analiza a fondo", "analiza en profundidad", "razona", "razonamiento",
    "piensa paso a paso", "resuelve paso a paso", "demuestra", "prueba que",
    "argumenta", "estrategia", "plan detallado", "depura",
]

_PENDING_WORK_SIGNALS = [
    "continuaré", "seguiré", "voy a continuar", "ahora crearé", "ahora voy a crear",
    "a continuación crearé", "procedo a crear", "el siguiente archivo", "los siguientes archivos",
    "siguen los archivos", "falta crear", "faltan por crear", "aún falta", "todavía falta",
    "ahora procedo", "paso a crear", "voy a escribir", "ahora escribiré", "creo ahora",
    "continúo con", "sigo con", "siguiente paso", "próximo archivo",
    "now i'll", "i'll continue", "next i'll", "i'll now create", "next file",
    "continuing with", "moving on to", "i'll write", "now creating",
]


class Reasoner:
    """
    Handles all LLM interactions: model routing, cascade fallback, agentic loop.
    Brain delegates here for anything that requires calling the LLM.

    Cascade flow:
      1. Elige proveedor óptimo para la tarea (por strengths + cascade_order)
      2. Si hay rechazo ético → siguiente proveedor
      3. Si hay respuesta dudosa → consulta todos los demás y vota la mejor
      4. Si varios responden bien → reasoning vote para elegir la mejor
    """

    def __init__(
        self,
        settings: Settings,
        memory: MemoryStore,
        confirm_fn: Optional[Callable[[str], bool]] = None,
        step_fn: Optional[Callable[[str, str, Optional[str]], None]] = None,
        provider_registry: Optional[Any] = None,
        prompt_rules: Optional[Any] = None,
    ):
        self.settings = settings
        self.memory = memory
        self.confirm_fn = confirm_fn
        self.step_fn = step_fn
        self.last_mode: str = "fast"
        self._system_prompt_override: Optional[str] = None
        self._abort_event: threading.Event = threading.Event()
        self._current_workspace_root: str = ""
        self._provider_registry: Optional[Any] = provider_registry
        self._prompt_rules: Optional[Any] = prompt_rules
        self._backend_cache: Dict[str, Any] = {}

    def set_provider_registry(self, registry: Any) -> None:
        self._provider_registry = registry

    def set_prompt_rules(self, prompt_rules: Any) -> None:
        self._prompt_rules = prompt_rules

    def abort(self) -> None:
        self._abort_event.set()

    def _check_abort(self) -> bool:
        return self._abort_event.is_set()

    def get_system_prompt(self, extra: Optional[str] = None) -> str:
        if self._prompt_rules is not None:
            return self._prompt_rules.build_full_system(extra)
        return self._system_prompt_override or SYSTEM_PROMPT

    def set_system_prompt(self, prompt: str) -> None:
        if self._prompt_rules is not None:
            self._prompt_rules.set_prompt(prompt)
        else:
            self._system_prompt_override = prompt.strip() or None

    # ── Backend factory ───────────────────────────────────────────────────────

    def _get_backend(self, provider: Any) -> Any:
        """Devuelve (y cachea) el backend correspondiente al proveedor."""
        pid = provider.id
        if pid not in self._backend_cache:
            from config.providers import BACKEND_LOCAL
            from ai.backends.openai_compat import OpenAICompatBackend
            from ai.backends.local_backend import LocalBackend
            if provider.backend == BACKEND_LOCAL:
                self._backend_cache[pid] = LocalBackend(provider)
            else:
                self._backend_cache[pid] = OpenAICompatBackend(provider)
        return self._backend_cache[pid]

    def _invalidate_backend(self, provider_id: str) -> None:
        self._backend_cache.pop(provider_id, None)

    def _active_provider(self) -> Any:
        """Retorna el proveedor activo del registry, o None si no hay registry."""
        if self._provider_registry is not None:
            return self._provider_registry.get_active()
        return None

    def _cascade_providers(self) -> List[Any]:
        """Lista ordenada de proveedores para cascada."""
        if self._provider_registry is not None:
            return self._provider_registry.cascade_order()
        return []

    def _best_provider_for(self, task: str) -> Any:
        """Mejor proveedor para una tarea dada."""
        if self._provider_registry is not None:
            return self._provider_registry.best_for_task(task)
        return self._active_provider()

    # ── Cascade helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _is_ethical_refusal(text: str) -> bool:
        low = (text or "").lower()
        return any(sig in low for sig in _ETHICAL_REFUSAL)

    @staticmethod
    def _is_doubtful(text: str) -> bool:
        low = (text or "").lower()
        return any(sig in low for sig in _DOUBTFUL_SIGNALS)

    def _cascade_chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        model_mode: str,
        temperature: float,
        max_tokens: int,
        task_hint: str = "",
    ) -> str:
        """
        Llama al LLM con cascada:
        - Empieza por el mejor proveedor para la tarea
        - Si rechazo ético → siguiente en cascada
        - Si respuesta dudosa → polling de todos + reasoning vote
        - Si varios responden bien → reasoning vote
        """
        providers = self._cascade_providers()
        if not providers:
            return self._chat_legacy(messages, temperature=temperature, max_tokens=max_tokens)

        # Reordenar: el mejor para la tarea va primero
        best = self._best_provider_for(task_hint) if task_hint else None
        if best:
            providers = [best] + [p for p in providers if p.id != best.id]

        refused: List[str] = []
        good_responses: List[Tuple[str, str]] = []  # (provider_name, response)

        for provider in providers:
            backend = self._get_backend(provider)
            model = provider.effective_model_deep() if model_mode == "deep" else provider.effective_model_fast()
            if not model:
                continue
            timeout = provider.timeout_s if provider.timeout_s > 0 else float(self.settings.llm_timeout_s)
            try:
                if self.step_fn:
                    try:
                        self.step_fn("analysis", f"cascade:{provider.name}", None)
                    except Exception:
                        pass
                response = backend.chat(messages, model=model, temperature=temperature,
                                        max_tokens=max_tokens, timeout_s=timeout)
                if not response or not response.strip():
                    continue
                if self._is_ethical_refusal(response):
                    print(f"[YUI] Cascade: {provider.name} rechazó (ético) → siguiente")
                    refused.append(provider.name)
                    continue
                if self._is_doubtful(response):
                    print(f"[YUI] Cascade: {provider.name} respuesta dudosa → consultando otros")
                    good_responses.append((provider.name, response))
                    # Sigue consultando todos para votar
                    continue
                good_responses.append((provider.name, response))
                # Si solo hay una respuesta buena hasta ahora, la retorna directamente
                # (evita latencia extra). Si ya hay varias, vota al final del loop.
                if len(good_responses) == 1 and len(providers) <= 2:
                    return response
            except Exception as e:
                print(f"[YUI] Cascade: {provider.name} error: {e}")
                continue

        if not good_responses:
            if refused:
                return "Lo siento, ninguno de los modelos disponibles pudo responder a esa solicitud."
            return "No pude obtener respuesta de ningún proveedor. Revisa la configuración."

        if len(good_responses) == 1:
            return good_responses[0][1]

        # Varios respondieron → reasoning vote
        return self._vote_best_response(messages, good_responses, temperature=temperature, max_tokens=max_tokens)

    def _vote_best_response(
        self,
        original_messages: List[Dict[str, Any]],
        candidates: List[Tuple[str, str]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Usa el proveedor activo para razonar y elegir la mejor respuesta entre candidatos."""
        if len(candidates) == 1:
            return candidates[0][1]

        original_question = ""
        for m in reversed(original_messages):
            if m.get("role") == "user":
                original_question = str(m.get("content", ""))
                break

        options_text = "\n\n".join(
            f"[Opción {i+1} - {name}]:\n{resp}"
            for i, (name, resp) in enumerate(candidates)
        )
        vote_messages = [
            {"role": "system", "content": (
                "Eres un evaluador experto. Se te presentan varias respuestas de distintos modelos "
                "a la misma pregunta. Analiza cuál es más precisa, completa y útil. "
                "Responde SOLO con el contenido de la mejor respuesta, sin modificarla ni agregar nada."
            )},
            {"role": "user", "content": (
                f"Pregunta original: {original_question}\n\n"
                f"Respuestas candidatas:\n{options_text}\n\n"
                "¿Cuál es la mejor respuesta? Devuelve solo su contenido."
            )},
        ]

        try:
            provider = self._active_provider()
            if provider:
                backend = self._get_backend(provider)
                model = provider.effective_model_fast()
                timeout = provider.timeout_s if provider.timeout_s > 0 else float(self.settings.llm_timeout_s)
                result = backend.chat(vote_messages, model=model, temperature=0.1,
                                      max_tokens=max_tokens, timeout_s=timeout)
                if result and result.strip():
                    print(f"[YUI] Cascade vote → eligió respuesta de entre {len(candidates)} candidatos")
                    return result.strip()
        except Exception as e:
            print(f"[YUI] Cascade vote error: {e}")

        # Fallback: retorna la primera respuesta buena
        return candidates[0][1]

    # ── Route ─────────────────────────────────────────────────────────────────

    def route(self, user_text: str) -> Tuple[str, float, str, int]:
        base_tokens = self._base_max_tokens()
        override = (getattr(self.settings, "llm_mode", "") or "").strip().lower()
        if override in {"deep", "profundo"}:
            return self.settings.llm_model_deep, float(self.settings.llm_deep_temperature), "deep", max(base_tokens, 2000)
        if override in {"fast", "rápido", "rapido"}:
            return self.settings.llm_model_fast, float(self.settings.llm_temperature), "fast", base_tokens

        t = (user_text or "").strip().lower()
        if not t:
            return self.settings.llm_model_fast, float(self.settings.llm_temperature), "fast", base_tokens

        if any(x in t for x in _DEEP_TRIGGERS):
            return self.settings.llm_model_deep, float(self.settings.llm_deep_temperature), "deep", max(base_tokens, 2000)
        if len(t) >= 140 or t.count("?") >= 2:
            return self.settings.llm_model_deep, float(self.settings.llm_deep_temperature), "deep", max(base_tokens, 2000)
        if any(x in t for x in _CODE_TRIGGERS):
            return self.settings.llm_model_fast, float(self.settings.llm_temperature), "code", max(base_tokens, 1500)

        return self.settings.llm_model_fast, float(self.settings.llm_temperature), "fast", base_tokens

    def _base_max_tokens(self) -> int:
        return int(os.getenv("YUI_LLM_MAX_TOKENS") or getattr(self.settings, "llm_max_tokens", 0) or 0)

    def health_check(self) -> bool:
        provider = self._active_provider()
        if provider:
            backend = self._get_backend(provider)
            return backend.is_available()
        if not (self.settings.llm_api_key or "").strip():
            return False
        try:
            from openai import OpenAI
            base = self.settings.llm_base_url.rstrip("/")
            client = OpenAI(api_key=self.settings.llm_api_key, base_url=base, timeout=self.settings.llm_timeout_s)
            client.models.list()
            return True
        except Exception:
            try:
                return self._health_check_requests()
            except Exception as e:
                print(f"[YUI] health_check failed: {e}")
                return False

    def _health_check_requests(self) -> bool:
        base = self.settings.llm_base_url.rstrip("/")
        if not base.endswith("/v1") and "/v1/" not in (base + "/"):
            base = f"{base}/v1"
        url = f"{base}/models"
        headers = {"api-key": self.settings.llm_api_key} if self._is_mimo() else {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        resp = requests.get(url, headers=headers, timeout=self.settings.llm_timeout_s)
        resp.raise_for_status()
        data = resp.json()
        return isinstance(data, dict) and "data" in data

    def _is_mimo(self) -> bool:
        url = self.settings.llm_base_url
        return "xiaomimimo.com" in url and "token-plan" not in url

    def call(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: str,
        temperature: float,
        workspace_root: str = "",
        max_tokens: int = 0,
        tools_enabled: bool = True,
        task_hint: str = "",
        model_mode: str = "fast",
    ) -> str:
        self._abort_event.clear()
        self._current_workspace_root = workspace_root
        try:
            if tools_enabled:
                return self._agentic_loop(messages, model=model, temperature=temperature,
                                          workspace_root=workspace_root, max_tokens=max_tokens,
                                          task_hint=task_hint, model_mode=model_mode)
            else:
                return self._chat(messages, model=model, temperature=temperature,
                                  max_tokens=max_tokens, task_hint=task_hint, model_mode=model_mode)
        except HTTPError as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            body = getattr(getattr(e, "response", None), "text", "") or ""
            print(f"[YUI] LLM HTTPError status={status} body={body[:400]!r}")
            return "Tuve un problema conectándome al modelo. Revisa la consola para el detalle y probamos de nuevo."
        except requests.exceptions.RequestException as e:
            print(f"[YUI] LLM RequestException: {type(e).__name__}: {e}")
            return "No pude conectar con el modelo (red/timeout). Revisa tu conexión y probamos de nuevo."
        except Exception as e:
            print(f"[YUI] LLM Error: {type(e).__name__}: {e}")
            return "Tuve un problema inesperado con el modelo. Revisa la consola y probamos de nuevo."

    def _make_diff_fn(self) -> Optional[Callable]:
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
            self.step_fn("task_complete", summary, json.dumps({"had_errors": had_errors}))
        except Exception:
            pass

    def _signals_pending_work(self, response: str) -> bool:
        low = response.lower()
        return any(sig in low for sig in _PENDING_WORK_SIGNALS)

    def _agentic_loop(self, messages: List[Dict[str, Any]], *, model: str, temperature: float,
                      workspace_root: str = "", max_tokens: int = 0,
                      task_hint: str = "", model_mode: str = "fast") -> str:
        max_iterations = int(os.getenv("YUI_TOOLS_MAX_ITERATIONS", "20"))
        msgs: List[Dict[str, Any]] = list(messages)
        _tools_used_count = 0

        for _iter in range(max_iterations):
            if self._check_abort():
                return "Detenido."

            provider = self._best_provider_for(task_hint) if task_hint else self._active_provider()
            raw: Any = self._chat_with_tools(msgs, model=model, temperature=temperature,
                                             max_tokens=max_tokens, provider=provider)

            if isinstance(raw, str):
                if _tools_used_count > 0 and self._signals_pending_work(raw):
                    print(f"[YUI] Respuesta señala trabajo pendiente — forzando continuación ({_iter+1}/{max_iterations})")
                    msgs.append({"role": "assistant", "content": raw})
                    msgs.append({
                        "role": "user",
                        "content": (
                            "Continúa directamente. No expliques — usa las herramientas ahora mismo para "
                            "crear el siguiente archivo o completar el paso pendiente. "
                            "Solo di 'Listo.' cuando todos los archivos estén completados."
                        ),
                    })
                    continue
                return raw

            tool_calls: List[Dict[str, Any]] = list(raw)
            text_mode = any(str(tc.get("id", "")).startswith("textcall-") for tc in tool_calls)

            if text_mode:
                _tools_used_count += len(tool_calls)
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
                    t_result = execute_tool(t_name, t_args, confirm_fn=confirm, diff_fn=self._make_diff_fn(), store=self.memory)
                    if t_result.startswith("[error] Herramienta desconocida"):
                        plugin_result = execute_plugin_tool(t_name, t_args)
                        if plugin_result is not None:
                            t_result = plugin_result
                    print(f"[YUI] Tool result: {t_result[:200]}")
                    if self.step_fn:
                        try:
                            self.step_fn("tool_end", t_name, t_result[:120] if t_result else None)
                        except Exception:
                            pass
                    all_tool_results.append(f"[{t_name}] {t_result}")

                    remaining_idx = tool_calls.index(tc)
                    if remaining_idx < len(tool_calls) - 1:
                        msgs.append({"role": "user", "content": f"Resultado de {t_name}: {t_result}\nContinúa con el siguiente paso."})
                        try:
                            _interim = self._chat_with_tools(msgs, model=model, temperature=temperature,
                                                            max_tokens=max_tokens, provider=provider)
                            if isinstance(_interim, str):
                                clean = re.sub(r"<tool_call>[\s\S]*?</tool_call>", "", _interim, flags=re.IGNORECASE).strip()
                                clean = re.sub(r"<[^>]+>", "", clean).strip()
                                if clean:
                                    return clean
                        except Exception:
                            pass

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
                        final = self._chat(msgs, model=model, temperature=temperature,
                                          max_tokens=max_tokens, task_hint=task_hint, model_mode=model_mode)
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
                _tools_used_count += len(tool_calls)
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
                    result = execute_tool(tool_name, tool_args, confirm_fn=confirm, diff_fn=self._make_diff_fn(), store=self.memory)
                    if result.startswith("[error] Herramienta desconocida"):
                        plugin_result = execute_plugin_tool(tool_name, tool_args)
                        if plugin_result is not None:
                            result = plugin_result
                    print(f"[YUI] Tool result: {result[:200]}")
                    if self.step_fn:
                        try:
                            self.step_fn("tool_end", tool_name, result[:120] if result else None)
                        except Exception:
                            pass
                    msgs.append({"role": "tool", "tool_call_id": tool_id, "content": result})

        msgs.append({"role": "user", "content": "Resume brevemente en 1-2 frases qué hiciste y si todo salió bien."})
        try:
            summary = self._chat(msgs, model=model, temperature=temperature, max_tokens=max_tokens)
            if summary and summary.strip():
                self._publish_task_complete(summary.strip(), False)
                return summary.strip()
        except Exception:
            pass
        return "Completé las operaciones solicitadas."

    def _chat_with_tools(self, messages: List[Dict[str, Any]], *, model: str, temperature: float,
                         max_tokens: int = 0, provider: Any = None) -> Any:
        # Si hay un proveedor explícito, usa su backend
        if provider is not None:
            try:
                backend = self._get_backend(provider)
                tools = get_all_tool_definitions()
                return backend.chat_with_tools(messages, tools, model=model,
                                               temperature=temperature, max_tokens=max_tokens,
                                               timeout_s=float(self.settings.llm_timeout_s))
            except Exception as exc:
                print(f"[YUI] Tool chat (backend) fallback to plain: {type(exc).__name__}: {exc}")
                return self._chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)
        try:
            from openai import OpenAI
            return self._chat_openai_tools(OpenAI, messages, model=model, temperature=temperature, max_tokens=max_tokens)
        except Exception as exc:
            print(f"[YUI] Tool chat fallback to plain: {type(exc).__name__}: {exc}")
            return self._chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)

    def _chat_openai_tools(self, OpenAI: Any, messages: List[Dict[str, Any]], *, model: str, temperature: float, max_tokens: int = 0) -> Any:
        base = self.settings.llm_base_url.rstrip("/")
        client = OpenAI(api_key=self.settings.llm_api_key, base_url=base, timeout=self.settings.llm_timeout_s)
        max_tokens = max_tokens or self._base_max_tokens()
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": get_all_tool_definitions(),
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

        content = msg.content or ""
        text_calls = self._parse_text_tool_calls(content)
        if text_calls:
            return text_calls
        return content

    def _parse_text_tool_calls(self, content: str) -> List[Dict[str, Any]]:
        import uuid as _uuid
        result: List[Dict[str, Any]] = []
        blocks: List[str] = re.findall(r"<tool_call>([\s\S]*?)</tool_call>", content, re.IGNORECASE)
        m = re.search(r"<tool_call>([\s\S]+)$", content, re.IGNORECASE)
        if m:
            tail = m.group(1)
            if not any(tail.strip() == b.strip() for b in blocks):
                blocks.append(tail)

        for block in blocks:
            fn_m = re.search(r"<function=(\w+)>", block, re.IGNORECASE)
            if not fn_m:
                continue
            fn_name = fn_m.group(1)
            args: Dict[str, Any] = {}
            param_starts = list(re.finditer(r"<parameter=(\w+)>", block, re.IGNORECASE))
            for i, pm_start in enumerate(param_starts):
                param_name = pm_start.group(1)
                value_start = pm_start.end()
                close_m = re.search(r"</parameter>", block[value_start:], re.IGNORECASE)
                if close_m:
                    value = block[value_start: value_start + close_m.start()]
                else:
                    if i + 1 < len(param_starts):
                        value = block[value_start: param_starts[i + 1].start()]
                    else:
                        tail_block = block[value_start:]
                        tail_block = re.sub(r"</function>[\s\S]*$", "", tail_block, flags=re.IGNORECASE)
                        tail_block = re.sub(r"</tool_call>[\s\S]*$", "", tail_block, flags=re.IGNORECASE)
                        value = tail_block
                args[param_name] = value
            result.append({"id": f"textcall-{_uuid.uuid4().hex[:8]}", "name": fn_name, "args": args})

        return result

    def _chat(self, messages: List[Dict[str, Any]], *, model: str = "", temperature: float,
              max_tokens: int = 0, task_hint: str = "", model_mode: str = "fast") -> str:
        # Con registry activo: usa cascada
        if self._provider_registry is not None and self._cascade_providers():
            return self._cascade_chat(messages, model_mode=model_mode, temperature=temperature,
                                      max_tokens=max_tokens, task_hint=task_hint)
        return self._chat_legacy(messages, model=model, temperature=temperature, max_tokens=max_tokens)

    def _chat_legacy(self, messages: List[Dict[str, Any]], *, model: str = "", temperature: float, max_tokens: int = 0) -> str:
        """Fallback al comportamiento original cuando no hay registry configurado."""
        resolved_model = model or self.settings.llm_model_fast
        try:
            from openai import OpenAI
            return self._chat_openai_sdk(OpenAI, messages, model=resolved_model, temperature=temperature, max_tokens=max_tokens)
        except Exception:
            return self._chat_requests(messages, model=resolved_model, temperature=temperature, max_tokens=max_tokens)

    def _chat_openai_sdk(self, OpenAI: Any, messages: List[Dict[str, Any]], *, model: str, temperature: float, max_tokens: int = 0) -> str:
        base = self.settings.llm_base_url.rstrip("/")
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
            base_v1 = base if base.endswith("/v1") else f"{base}/v1"
            if base_v1 != base:
                client = OpenAI(api_key=self.settings.llm_api_key, base_url=base_v1, timeout=self.settings.llm_timeout_s)
                resp = client.chat.completions.create(**kwargs)
            else:
                raise e
        return resp.choices[0].message.content or ""

    def _chat_requests(self, messages: List[Dict[str, Any]], *, model: str, temperature: float, max_tokens: int = 0) -> str:
        base = self.settings.llm_base_url.rstrip("/")
        if not base.endswith("/v1") and "/v1/" not in (base + "/"):
            base = f"{base}/v1"
        url = f"{base}/chat/completions"
        mimo = self._is_mimo()
        if mimo:
            msgs_out: List[Dict[str, Any]] = []
            for m in messages:
                entry: Dict[str, Any] = {"role": m["role"], "content": m.get("content", "")}
                if "reasoning_content" in m:
                    entry["reasoning_content"] = m["reasoning_content"]
                msgs_out.append(entry)
        else:
            msgs_out = list(messages)
        payload: Dict[str, Any] = {
            "model": model,
            "messages": msgs_out,
            "temperature": float(temperature),
            "stream": False,
        }
        max_tokens = max_tokens or self._base_max_tokens()
        if max_tokens > 0:
            token_key = "max_completion_tokens" if mimo else "max_tokens"
            payload[token_key] = max_tokens
        headers = {"api-key": self.settings.llm_api_key, "Content-Type": "application/json"} if mimo else {"Authorization": f"Bearer {self.settings.llm_api_key}", "Content-Type": "application/json"}
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=self.settings.llm_timeout_s)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        msg = choice["message"]
        reasoning = msg.get("reasoning_content")
        if reasoning and hasattr(self, "memory"):
            self._last_reasoning_content = reasoning
        return msg.get("content") or ""

    # ── Memory helpers (used by Brain) ────────────────────────────────────────

    def extract_memories(self, *, user_id: str, n: int) -> None:
        if not self.settings.memory_use_long_term:
            return
        if n <= 0 or not (self.settings.llm_api_key or "").strip():
            return
        recent_pairs = self.memory.recent(limit=max(10, n * 2))
        assistant_count = sum(1 for it in recent_pairs if it.role == "assistant")
        if assistant_count % n != 0:
            return
        convo = "\n".join([f"{it.role}: {it.content}" for it in recent_pairs[-(n * 2):]])
        prompt = [
            {"role": "system", "content": (
                "Extrae hasta 3 recuerdos útiles y estables sobre el usuario o el contexto, en español. "
                "Devuelve SOLO JSON con este esquema:\n"
                "{ \"memories\": [ {\"content\": \"...\", \"salience\": 0.0-1.0, \"tags\": \"...\"} ] }\n"
                "Reglas: no repitas obviedades, no guardes datos sensibles."
            )},
            {"role": "user", "content": convo},
        ]
        try:
            raw = self._chat(prompt, model=self.settings.llm_model_fast, temperature=float(self.settings.llm_temperature)).strip()
        except Exception:
            return
        data = self._safe_json(raw)
        if not data:
            return
        memories_raw = data.get("memories")
        if not isinstance(memories_raw, list):
            return
        for m in list(memories_raw)[:3]:
            if not isinstance(m, dict):
                continue
            content = str(m.get("content", "")).strip()
            if not content:
                continue
            sal = m.get("salience", 0.6)
            tags = str(m.get("tags", "")).strip()
            vec = embed(content)
            emb_json = vec_to_json(vec) if vec is not None else None
            self.memory.add_memory(user_id=user_id, content=content, salience=float(sal), tags=tags, embedding_json=emb_json)

    def summarize(self, n: int) -> None:
        if not self.settings.memory_use_summaries or n <= 0:
            return
        if not (self.settings.llm_api_key or "").strip():
            return
        last_upto = self.memory.latest_summary_upto_id()
        recent = self.memory.recent_with_ids(limit=n + 10)
        if not recent:
            return
        new_items = [(mid, item) for mid, item in recent if mid > last_upto]
        if len(new_items) < n:
            return
        up_to_id = new_items[-1][0]
        convo = "\n".join([f"{it.role}: {it.content}" for _, it in new_items])
        summary_prompt = [
            {"role": "system", "content": "Resume en 6-10 líneas lo importante (hechos, objetivos, preferencias). En español."},
            {"role": "user", "content": convo},
        ]
        try:
            summary = self._chat(summary_prompt, model=self.settings.llm_model_fast, temperature=float(self.settings.llm_temperature)).strip()
        except Exception:
            return
        if summary:
            self.memory.add_summary(up_to_id, summary)

    def retrieve_relevant_memories(self, *, user_id: str, query: str, k: int, min_score: float) -> Optional[Dict[str, Any]]:
        candidates = self.memory.recent_memories(user_id=user_id, limit=100)
        if not candidates:
            return None
        query_vec = embed(query)
        if query_vec is not None:
            scored: List[tuple] = []
            needs_embedding: List[tuple] = []
            for mid, content, salience, _tags, emb_json in candidates:
                mem_vec = vec_from_json(emb_json) if emb_json else None
                if mem_vec is None:
                    needs_embedding.append((mid, content))
                else:
                    sim = cosine_similarity(query_vec, mem_vec)
                    score = sim * 0.80 + float(salience) * 0.20
                    if score >= min_score:
                        scored.append((score, mid, content))
            if needs_embedding:
                def _backfill(pairs):
                    for mid, content in pairs:
                        vec = embed(content)
                        if vec is not None:
                            self.memory.update_memory_embedding(mid, vec_to_json(vec))
                threading.Thread(target=_backfill, args=(needs_embedding,), daemon=True).start()
                q_tokens = self._tokenize(query)
                for mid, content in needs_embedding:
                    c = self._tokenize(content)
                    if not c:
                        continue
                    overlap = len(q_tokens.intersection(c)) / max(1, len(q_tokens))
                    score = overlap * 0.6 + 0.2
                    if score >= min_score:
                        scored.append((score, mid, content))
        else:
            q_tokens = self._tokenize(query)
            if not q_tokens:
                return None
            scored = []
            for mid, content, salience, _tags, _emb in candidates:
                c = self._tokenize(content)
                if not c:
                    continue
                overlap = len(q_tokens.intersection(c)) / max(1, len(q_tokens))
                if overlap <= 0:
                    continue
                score = overlap * 0.75 + float(salience) * 0.25
                if score >= min_score:
                    scored.append((score, mid, content))

        scored.sort(key=lambda t: t[0], reverse=True)
        top = scored[:int(k)]
        if not top:
            return None
        return {"ids": [t[1] for t in top], "contents": [t[2] for t in top]}

    def _tokenize(self, text: str) -> set:
        text = (text or "").lower()
        text = re.sub(r"[^a-záéíóúüñ0-9\s]+", " ", text)
        parts = [p for p in text.split() if len(p) >= 3]
        stop = {"que", "para", "por", "con", "una", "uno", "los", "las", "del", "como",
                "pero", "porque", "esto", "eso", "hola", "buenas", "buenos", "dias",
                "tardes", "noches", "gracias", "ok", "vale", "yui"}
        return {p for p in parts if p not in stop}

    def should_retrieve_long_term(self, user_text: str, min_tokens: int) -> bool:
        t = (user_text or "").strip().lower()
        if not t:
            return False
        recall_triggers = [
            "recuerda", "recuerdas", "acuérdate", "acuerdate", "te acuerdas",
            "qué dijimos", "que dijimos", "lo que hablamos", "antes", "la otra vez",
            "ayer", "mi nombre", "cómo me llamo", "como me llamo",
        ]
        if any(x in t for x in recall_triggers):
            return True
        return len(self._tokenize(user_text)) >= int(min_tokens or 0)

    def _safe_json(self, raw: str) -> Optional[Dict[str, Any]]:
        raw = (raw or "").strip()
        if not raw:
            return None
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        try:
            obj = json.loads(raw)
        except Exception:
            return None
        return obj if isinstance(obj, dict) else None
