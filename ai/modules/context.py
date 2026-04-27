"""
context.py — Runtime state, conversation context, visual and mood tracking.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class VisualContext:
    """Snapshot of the current visual perception state."""
    user_name: Optional[str] = None
    face_confidence: float = 0.0
    gestures: Optional[List[str]] = None
    face_emotion: Optional[str] = None

    @classmethod
    def empty(cls) -> "VisualContext":
        return cls()
