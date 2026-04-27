"""
vision.py — Visual perception pipeline: face recognition, gesture detection, emotion inference.
"""
from __future__ import annotations

from typing import List
from ai.modules.context import VisualContext


def build_visual_context_text(visual: VisualContext) -> str:
    """Formats a VisualContext into a system prompt snippet for the LLM."""
    parts: List[str] = []
    if visual.user_name:
        parts.append(f"Usuario identificado: {visual.user_name} (confianza {visual.face_confidence:.2f}).")
    if visual.gestures:
        parts.append(f"Gestos detectados: {', '.join(visual.gestures)}.")
    if visual.face_emotion:
        parts.append(f"Emoción facial probable: {visual.face_emotion}.")
    if not parts:
        return ""
    return (
        "Contexto visual actual (úsalo solo para adaptar tu respuesta; no lo narres literalmente): "
        + " ".join(parts)
    )
