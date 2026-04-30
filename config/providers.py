"""
providers.py — Registro de proveedores LLM con persistencia JSON.

Cada proveedor puede ser:
  - OpenAI-compatible API (DeepSeek, Mimo, OpenAI, Groq, Ollama HTTP, etc.)
  - Local backend (Ollama proceso local, llama-cpp-python, transformers)

El registro es la fuente de verdad para el Reasoner. No usa settings.py
para URL/key/modelo — todo viene de aquí en caliente.
"""
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "providers.json"

# Tipos de backend soportados
BACKEND_OPENAI = "openai_compat"   # cualquier API bajo estándar OpenAI
BACKEND_LOCAL  = "local"           # modelo local (Ollama, llama-cpp, transformers)

# Señales de especialidad que el Reasoner usa para elegir proveedor óptimo
KNOWN_STRENGTHS = [
    "general", "programacion", "razonamiento", "creatividad",
    "matematicas", "seguridad", "resumen", "traduccion", "chat",
]


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


class ProviderConfig:
    """Representa un proveedor LLM configurado."""

    def __init__(self, data: Dict[str, Any]):
        self.id: str               = data.get("id") or _new_id()
        self.name: str             = data.get("name", "Sin nombre")
        self.backend: str          = data.get("backend", BACKEND_OPENAI)
        self.enabled: bool         = bool(data.get("enabled", True))
        self.active: bool          = bool(data.get("active", False))
        self.cascade_order: int    = int(data.get("cascade_order", 99))

        # OpenAI-compat
        self.base_url: str         = data.get("base_url", "")
        self.api_key: str          = data.get("api_key", "")

        # Modelos: lista descubierta + selección fast/deep
        self.models_available: List[str] = list(data.get("models_available") or [])
        self.model_fast: str       = data.get("model_fast", "")
        self.model_deep: str       = data.get("model_deep", "")

        # Local backend
        self.local_type: str       = data.get("local_type", "ollama")   # ollama|llamacpp|transformers
        self.local_model: str      = data.get("local_model", "")        # nombre en Ollama o ruta GGUF
        self.local_url: str        = data.get("local_url", "http://localhost:11434")
        self.local_n_ctx: int      = int(data.get("local_n_ctx", 4096))
        self.local_n_gpu_layers: int = int(data.get("local_n_gpu_layers", 0))

        # Especialidades para routing inteligente
        self.strengths: List[str]  = list(data.get("strengths") or ["general"])

        # Timeout propio (0 = usar default global)
        self.timeout_s: float      = float(data.get("timeout_s", 0))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id":                 self.id,
            "name":               self.name,
            "backend":            self.backend,
            "enabled":            self.enabled,
            "active":             self.active,
            "cascade_order":      self.cascade_order,
            "base_url":           self.base_url,
            "api_key":            self.api_key,
            "models_available":   self.models_available,
            "model_fast":         self.model_fast,
            "model_deep":         self.model_deep,
            "local_type":         self.local_type,
            "local_model":        self.local_model,
            "local_url":          self.local_url,
            "local_n_ctx":        self.local_n_ctx,
            "local_n_gpu_layers": self.local_n_gpu_layers,
            "strengths":          self.strengths,
            "timeout_s":          self.timeout_s,
        }

    def effective_model_fast(self) -> str:
        return self.model_fast or self.local_model or ""

    def effective_model_deep(self) -> str:
        return self.model_deep or self.local_model or self.model_fast or ""

    def is_local(self) -> bool:
        return self.backend == BACKEND_LOCAL


class ProviderRegistry:
    """
    Registro central de proveedores LLM.
    Thread-safe. Persiste en JSON.
    """

    def __init__(self, db_path: Path = _DEFAULT_DB):
        self._path = Path(db_path)
        self._lock = threading.RLock()
        self._providers: List[ProviderConfig] = []
        self._load()

    # ── Persistencia ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            self._providers = []
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._providers = [ProviderConfig(p) for p in (raw if isinstance(raw, list) else [])]
        except Exception as e:
            print(f"[YUI] ProviderRegistry load error: {e}")
            self._providers = []

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps([p.to_dict() for p in self._providers], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[YUI] ProviderRegistry save error: {e}")

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def list_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [p.to_dict() for p in sorted(self._providers, key=lambda x: x.cascade_order)]

    def get(self, provider_id: str) -> Optional[ProviderConfig]:
        with self._lock:
            return next((p for p in self._providers if p.id == provider_id), None)

    def add(self, data: Dict[str, Any]) -> ProviderConfig:
        with self._lock:
            data.setdefault("id", _new_id())
            if not data.get("cascade_order"):
                data["cascade_order"] = max((p.cascade_order for p in self._providers), default=0) + 1
            p = ProviderConfig(data)
            self._providers.append(p)
            self._save()
            return p

    def update(self, provider_id: str, data: Dict[str, Any]) -> Optional[ProviderConfig]:
        with self._lock:
            p = self.get(provider_id)
            if p is None:
                return None
            merged = {**p.to_dict(), **data, "id": provider_id}
            idx = self._providers.index(p)
            self._providers[idx] = ProviderConfig(merged)
            self._save()
            return self._providers[idx]

    def delete(self, provider_id: str) -> bool:
        with self._lock:
            before = len(self._providers)
            self._providers = [p for p in self._providers if p.id != provider_id]
            if len(self._providers) < before:
                self._save()
                return True
            return False

    def set_active(self, provider_id: str) -> bool:
        with self._lock:
            found = any(p.id == provider_id for p in self._providers)
            if not found:
                return False
            for p in self._providers:
                p.active = (p.id == provider_id)
            self._save()
            return True

    def set_cascade_order(self, ordered_ids: List[str]) -> None:
        with self._lock:
            id_to_order = {pid: i + 1 for i, pid in enumerate(ordered_ids)}
            for p in self._providers:
                if p.id in id_to_order:
                    p.cascade_order = id_to_order[p.id]
            self._save()

    # ── Consultas ─────────────────────────────────────────────────────────────

    def get_active(self) -> Optional[ProviderConfig]:
        with self._lock:
            active = [p for p in self._providers if p.active and p.enabled]
            if active:
                return active[0]
            enabled = [p for p in self._providers if p.enabled]
            return enabled[0] if enabled else None

    def cascade_order(self) -> List[ProviderConfig]:
        """Proveedores habilitados ordenados para cascada."""
        with self._lock:
            return sorted(
                [p for p in self._providers if p.enabled],
                key=lambda x: x.cascade_order,
            )

    def best_for_task(self, task: str) -> Optional[ProviderConfig]:
        """
        Elige el proveedor más adecuado para una tarea dada.
        Prioriza: strengths match > cascade_order > activo.
        """
        with self._lock:
            enabled = [p for p in self._providers if p.enabled]
            if not enabled:
                return None
            task_low = (task or "").lower()
            scored: List[tuple] = []
            for p in enabled:
                score = 0
                for s in p.strengths:
                    if s in task_low or task_low in s:
                        score += 10
                if p.active:
                    score += 3
                score -= p.cascade_order * 0.1
                scored.append((score, p))
            scored.sort(key=lambda x: x[0], reverse=True)
            return scored[0][1] if scored else None

    # ── Fetch modelos desde API ───────────────────────────────────────────────

    def fetch_models(self, provider_id: str, timeout_s: float = 10.0) -> List[str]:
        """
        Intenta obtener la lista de modelos del proveedor llamando a /v1/models.
        Retorna lista vacía si falla (el usuario puede escribir los modelos a mano).
        """
        p = self.get(provider_id)
        if p is None:
            return []

        if p.is_local():
            return self._fetch_ollama_models(p, timeout_s)

        return self._fetch_openai_models(p, timeout_s)

    def _fetch_openai_models(self, p: ProviderConfig, timeout_s: float) -> List[str]:
        import requests
        base = (p.base_url or "").rstrip("/")
        if not base:
            return []
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        url = f"{base}/models"
        headers: Dict[str, str] = {}
        if p.api_key:
            headers["Authorization"] = f"Bearer {p.api_key}"
        try:
            resp = requests.get(url, headers=headers, timeout=timeout_s)
            resp.raise_for_status()
            data = resp.json()
            models = [m["id"] for m in data.get("data", []) if isinstance(m, dict) and "id" in m]
            if models:
                with self._lock:
                    stored = self.get(p.id)
                    if stored:
                        stored.models_available = models
                        self._save()
            return models
        except Exception as e:
            print(f"[YUI] fetch_models({p.id}): {e}")
            return []

    def _fetch_ollama_models(self, p: ProviderConfig, timeout_s: float) -> List[str]:
        import requests
        base = (p.local_url or "http://localhost:11434").rstrip("/")
        try:
            resp = requests.get(f"{base}/api/tags", timeout=timeout_s)
            resp.raise_for_status()
            data = resp.json()
            models = [m["name"] for m in data.get("models", []) if isinstance(m, dict)]
            if models:
                with self._lock:
                    stored = self.get(p.id)
                    if stored:
                        stored.models_available = models
                        self._save()
            return models
        except Exception as e:
            print(f"[YUI] fetch_ollama_models({p.id}): {e}")
            return []
