from __future__ import annotations

import json
import threading
from typing import List, Optional

import numpy as np

_lock = threading.Lock()
_model = None
_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def _get_model():
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(_MODEL_NAME)
            print(f"[YUI:embedder] Modelo cargado: {_MODEL_NAME}")
        except ImportError:
            print("[YUI:embedder] sentence-transformers no instalado — usando embeddings nulos")
            _model = None
    return _model


def embed(text: str) -> Optional[List[float]]:
    """Returns a unit-norm embedding vector, or None if model unavailable."""
    model = _get_model()
    if model is None:
        return None
    text = (text or "").strip()
    if not text:
        return None
    try:
        vec = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        return vec.tolist()
    except Exception as e:
        print(f"[YUI:embedder] Error al embedir: {e}")
        return None


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Fast cosine similarity between two already-normalized vectors."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    dot = float(np.dot(va, vb))
    # Clamp to [-1, 1] due to float precision
    return max(-1.0, min(1.0, dot))


def vec_to_json(vec: List[float]) -> str:
    return json.dumps(vec)


def vec_from_json(s: str) -> Optional[List[float]]:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None
