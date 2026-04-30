"""
local_backend.py — Backend para modelos locales.

Soporta tres modos:
  - ollama:       Ollama corriendo localmente (HTTP en localhost:11434)
  - llamacpp:     llama-cpp-python (GGUF directo en proceso, sin HTTP)
  - transformers: HuggingFace transformers (en proceso)

El modelo se carga una sola vez al primer uso y queda en memoria (warm).
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from ai.backends.base import BackendBase
from config.providers import ProviderConfig


class LocalBackend(BackendBase):
    """
    Backend para modelos locales. Carga el modelo en memoria al primer uso.
    Soporta: ollama (HTTP local), llama-cpp-python (GGUF), transformers (HF).
    """

    def __init__(self, provider: ProviderConfig):
        self.provider = provider
        self._lock = threading.Lock()
        self._llama_model: Optional[Any] = None      # llama-cpp-python instance
        self._hf_pipeline: Optional[Any] = None      # transformers pipeline

    def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: str,
        temperature: float,
        max_tokens: int = 0,
        timeout_s: float = 60.0,
    ) -> str:
        local_type = self.provider.local_type or "ollama"

        if local_type == "ollama":
            return self._chat_ollama(messages, model=model, temperature=temperature,
                                     max_tokens=max_tokens, timeout_s=timeout_s)
        if local_type == "llamacpp":
            return self._chat_llamacpp(messages, temperature=temperature, max_tokens=max_tokens)
        if local_type == "transformers":
            return self._chat_transformers(messages, temperature=temperature, max_tokens=max_tokens)

        return f"[error] local_type desconocido: {local_type!r}"

    # ── Ollama ────────────────────────────────────────────────────────────────

    def _chat_ollama(self, messages: List[Dict[str, Any]], *, model: str,
                     temperature: float, max_tokens: int, timeout_s: float) -> str:
        import requests
        import json

        model_name = model or self.provider.local_model or ""
        if not model_name:
            return "[error] LocalBackend Ollama: no se especificó modelo"

        base = (self.provider.local_url or "http://localhost:11434").rstrip("/")
        url = f"{base}/api/chat"

        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "options": {"temperature": float(temperature)},
        }
        if max_tokens > 0:
            payload["options"]["num_predict"] = max_tokens

        try:
            resp = requests.post(url, json=payload, timeout=timeout_s)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "") or ""
        except Exception as e:
            print(f"[YUI] LocalBackend Ollama error: {e}")
            return f"[error] Ollama: {e}"

    # ── llama-cpp-python ──────────────────────────────────────────────────────

    def _chat_llamacpp(self, messages: List[Dict[str, Any]], *,
                       temperature: float, max_tokens: int) -> str:
        model_path = self.provider.local_model or ""
        if not model_path:
            return "[error] LocalBackend llamacpp: no se especificó ruta del modelo (local_model)"

        llm = self._get_llamacpp(model_path)
        if llm is None:
            return "[error] LocalBackend llamacpp: no se pudo cargar el modelo"

        try:
            kwargs: Dict[str, Any] = {"temperature": float(temperature)}
            if max_tokens > 0:
                kwargs["max_tokens"] = max_tokens
            resp = llm.create_chat_completion(messages=messages, **kwargs)
            return resp["choices"][0]["message"]["content"] or ""
        except Exception as e:
            print(f"[YUI] LocalBackend llamacpp inference error: {e}")
            return f"[error] llamacpp: {e}"

    def _get_llamacpp(self, model_path: str) -> Optional[Any]:
        with self._lock:
            if self._llama_model is not None:
                return self._llama_model
            try:
                from llama_cpp import Llama  # type: ignore
                print(f"[YUI] Cargando modelo llama-cpp: {model_path}")
                self._llama_model = Llama(
                    model_path=model_path,
                    n_ctx=self.provider.local_n_ctx or 4096,
                    n_gpu_layers=self.provider.local_n_gpu_layers or 0,
                    verbose=False,
                )
                print(f"[YUI] Modelo cargado: {model_path}")
                return self._llama_model
            except ImportError:
                print("[YUI] llama-cpp-python no instalado. pip install llama-cpp-python")
                return None
            except Exception as e:
                print(f"[YUI] LocalBackend llamacpp load error: {e}")
                return None

    # ── HuggingFace transformers ──────────────────────────────────────────────

    def _chat_transformers(self, messages: List[Dict[str, Any]], *,
                           temperature: float, max_tokens: int) -> str:
        model_name = self.provider.local_model or ""
        if not model_name:
            return "[error] LocalBackend transformers: no se especificó modelo (local_model)"

        pipe = self._get_hf_pipeline(model_name)
        if pipe is None:
            return "[error] LocalBackend transformers: no se pudo cargar el pipeline"

        try:
            kwargs: Dict[str, Any] = {"temperature": float(temperature), "do_sample": True}
            if max_tokens > 0:
                kwargs["max_new_tokens"] = max_tokens
            result = pipe(messages, **kwargs)
            if isinstance(result, list) and result:
                out = result[0]
                if isinstance(out, dict):
                    generated = out.get("generated_text", "")
                    if isinstance(generated, list) and generated:
                        return str(generated[-1].get("content", ""))
                    return str(generated)
            return str(result)
        except Exception as e:
            print(f"[YUI] LocalBackend transformers inference error: {e}")
            return f"[error] transformers: {e}"

    def _get_hf_pipeline(self, model_name: str) -> Optional[Any]:
        with self._lock:
            if self._hf_pipeline is not None:
                return self._hf_pipeline
            try:
                from transformers import pipeline  # type: ignore
                print(f"[YUI] Cargando modelo HuggingFace: {model_name}")
                self._hf_pipeline = pipeline("text-generation", model=model_name)
                print(f"[YUI] Modelo HuggingFace cargado: {model_name}")
                return self._hf_pipeline
            except ImportError:
                print("[YUI] transformers no instalado. pip install transformers torch")
                return None
            except Exception as e:
                print(f"[YUI] LocalBackend transformers load error: {e}")
                return None

    def is_available(self) -> bool:
        local_type = self.provider.local_type or "ollama"
        if local_type == "ollama":
            try:
                import requests
                base = (self.provider.local_url or "http://localhost:11434").rstrip("/")
                r = requests.get(f"{base}/api/tags", timeout=3)
                return r.status_code == 200
            except Exception:
                return False
        if local_type == "llamacpp":
            from pathlib import Path
            return Path(self.provider.local_model or "").exists()
        return True
