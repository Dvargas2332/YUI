"""
openai_compat.py — Backend para cualquier API compatible con OpenAI.
Soporta: DeepSeek, Mimo, OpenAI, Groq, Together, Ollama HTTP, etc.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import requests

from ai.backends.base import BackendBase
from config.providers import ProviderConfig


class OpenAICompatBackend(BackendBase):
    """
    Backend OpenAI-compatible.
    Intenta usar el SDK openai primero; si falla, usa requests como fallback.
    Soporta function calling nativo.
    """

    def __init__(self, provider: ProviderConfig):
        self.provider = provider

    def _base_url(self) -> str:
        base = (self.provider.base_url or "").rstrip("/")
        return base

    def _is_mimo(self) -> bool:
        url = self.provider.base_url or ""
        return "xiaomimimo.com" in url and "token-plan" not in url

    def _timeout(self, timeout_s: float) -> float:
        return self.provider.timeout_s if self.provider.timeout_s > 0 else timeout_s

    def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: str,
        temperature: float,
        max_tokens: int = 0,
        timeout_s: float = 30.0,
    ) -> str:
        timeout = self._timeout(timeout_s)
        try:
            return self._chat_sdk(messages, model=model, temperature=temperature,
                                  max_tokens=max_tokens, timeout_s=timeout)
        except Exception:
            return self._chat_requests(messages, model=model, temperature=temperature,
                                       max_tokens=max_tokens, timeout_s=timeout)

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
        timeout = self._timeout(timeout_s)
        try:
            from openai import OpenAI
            return self._chat_sdk_tools(OpenAI, messages, tools,
                                        model=model, temperature=temperature,
                                        max_tokens=max_tokens, timeout_s=timeout)
        except Exception as exc:
            print(f"[YUI] OpenAICompatBackend tools fallback to plain: {type(exc).__name__}: {exc}")
            return self.chat(messages, model=model, temperature=temperature,
                             max_tokens=max_tokens, timeout_s=timeout)

    def _make_client(self, OpenAI: Any, base: str) -> Any:
        return OpenAI(
            api_key=self.provider.api_key or "no-key",
            base_url=base,
            timeout=self._timeout(30.0),
        )

    def _chat_sdk(self, messages: List[Dict[str, Any]], *, model: str,
                  temperature: float, max_tokens: int, timeout_s: float) -> str:
        from openai import OpenAI
        base = self._base_url()
        client = self._make_client(OpenAI, base)
        kwargs = self._build_kwargs(model, messages, temperature, max_tokens)
        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception:
            base_v1 = base if base.endswith("/v1") else f"{base}/v1"
            if base_v1 != base:
                client = self._make_client(OpenAI, base_v1)
                resp = client.chat.completions.create(**kwargs)
            else:
                raise
        return resp.choices[0].message.content or ""

    def _chat_sdk_tools(self, OpenAI: Any, messages: List[Dict[str, Any]],
                        tools: List[Dict[str, Any]], *, model: str,
                        temperature: float, max_tokens: int, timeout_s: float) -> Any:
        base = self._base_url()
        client = self._make_client(OpenAI, base)
        kwargs = self._build_kwargs(model, messages, temperature, max_tokens)
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception:
            base_v1 = base if base.endswith("/v1") else f"{base}/v1"
            if base_v1 != base:
                client = self._make_client(OpenAI, base_v1)
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
        return msg.content or ""

    def _build_kwargs(self, model: str, messages: List[Dict[str, Any]],
                      temperature: float, max_tokens: int) -> Dict[str, Any]:
        mimo = self._is_mimo()
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": float(temperature),
        }
        if max_tokens > 0:
            kwargs["max_completion_tokens" if mimo else "max_tokens"] = max_tokens
        return kwargs

    def _chat_requests(self, messages: List[Dict[str, Any]], *, model: str,
                       temperature: float, max_tokens: int, timeout_s: float) -> str:
        mimo = self._is_mimo()
        base = self._base_url()
        if not base.endswith("/v1") and "/v1/" not in (base + "/"):
            base = f"{base}/v1"
        url = f"{base}/chat/completions"

        msgs_out: List[Dict[str, Any]] = []
        for m in messages:
            entry: Dict[str, Any] = {"role": m["role"], "content": m.get("content", "")}
            if mimo and "reasoning_content" in m:
                entry["reasoning_content"] = m["reasoning_content"]
            msgs_out.append(entry)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": msgs_out,
            "temperature": float(temperature),
            "stream": False,
        }
        if max_tokens > 0:
            payload["max_completion_tokens" if mimo else "max_tokens"] = max_tokens

        if mimo:
            headers = {"api-key": self.provider.api_key, "Content-Type": "application/json"}
        else:
            headers = {"Authorization": f"Bearer {self.provider.api_key}", "Content-Type": "application/json"}

        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout_s)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"].get("content") or ""

    def is_available(self) -> bool:
        if not self.provider.base_url:
            return False
        try:
            import requests as _r
            base = self._base_url()
            if not base.endswith("/v1"):
                base = f"{base}/v1"
            hdrs = {"Authorization": f"Bearer {self.provider.api_key}"} if self.provider.api_key else {}
            r = _r.get(f"{base}/models", headers=hdrs, timeout=5)
            return r.status_code < 500
        except Exception:
            return False
