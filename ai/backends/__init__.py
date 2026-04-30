"""
ai/backends — Capa de abstracción para backends LLM.

Todos los backends exponen la misma interfaz:
    chat(messages, *, model, temperature, max_tokens, timeout_s) -> str

El Reasoner usa esta capa — no sabe si habla con una API o un modelo local.
"""
from ai.backends.base import BackendBase
from ai.backends.openai_compat import OpenAICompatBackend
from ai.backends.local_backend import LocalBackend

__all__ = ["BackendBase", "OpenAICompatBackend", "LocalBackend"]
