"""Interfaz común para todos los backends LLM."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BackendBase(ABC):
    """
    Interfaz que todo backend debe implementar.
    chat() es el único método requerido.
    """

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: str,
        temperature: float,
        max_tokens: int = 0,
        timeout_s: float = 30.0,
    ) -> str:
        """Envía mensajes al modelo y retorna la respuesta como string."""
        ...

    def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        model: str,
        temperature: float,
        max_tokens: int = 0,
        timeout_s: float = 30.0,
    ) -> Any:
        """
        Versión con herramientas. Retorna str o lista de tool_calls.
        Por defecto delega a chat() sin herramientas (backends locales simples).
        Los backends que soporten function calling lo sobreescriben.
        """
        return self.chat(messages, model=model, temperature=temperature,
                         max_tokens=max_tokens, timeout_s=timeout_s)

    def is_available(self) -> bool:
        """Verifica si el backend está disponible (conexión, modelo cargado, etc.)."""
        return True
