"""
synthesizer.py — Output fusion, response merging, display vs spoken split.

Owns: logic that decides what goes to the UI (full rich text) vs TTS (short spoken).
Currently this logic lives in HybridBrain.reply() and main.py.
Future: move the full display/spoken split here and expose a SynthesizedOutput type.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SynthesizedOutput:
    """Encapsulates the two output surfaces for a single assistant reply."""
    spoken: str        # Short version for TTS — enforced by StylePolicy
    display: str       # Full rich version for UI — may include markdown, tables, code

    @classmethod
    def from_single(cls, text: str) -> "SynthesizedOutput":
        """When there's only one version (no teaching mode split), both surfaces are the same."""
        return cls(spoken=text, display=text)

    @classmethod
    def from_split(cls, spoken: str, display: str) -> "SynthesizedOutput":
        """When teaching mode produces a long display and a short spoken version."""
        return cls(spoken=spoken.strip(), display=display.strip())

    @property
    def has_split(self) -> bool:
        return self.spoken.strip() != self.display.strip()


__all__ = ["SynthesizedOutput"]
