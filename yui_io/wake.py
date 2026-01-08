from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

from config.settings import Settings
from yui_io.stt import listen


def _normalize(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _wake_candidates(settings: Settings) -> list[str]:
    """
    Wake word + optional aliases (helps when STT mishears "yui").
    """
    base = _normalize(getattr(settings, "wake_word", "") or "")
    env_aliases = (os.getenv("YUI_WAKE_WORD_ALIASES", "") or "").strip()
    aliases: list[str] = []
    if env_aliases:
        for part in re.split(r"[,\|;]\s*", env_aliases):
            p = _normalize(part)
            if p:
                aliases.append(p)

    out: list[str] = []
    seen = set()
    for w in [base, *aliases]:
        if not w:
            continue
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


def _edit_distance_le1(a: str, b: str) -> bool:
    """
    True if Levenshtein distance <= 1 (fast path for short wake words).
    """
    a = a or ""
    b = b or ""
    if a == b:
        return True
    la = len(a)
    lb = len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diff = 0
        for i in range(la):
            if a[i] != b[i]:
                diff += 1
                if diff > 1:
                    return False
        return True

    # Ensure a is the shorter string.
    if la > lb:
        a, b = b, a
        la, lb = lb, la

    i = 0
    j = 0
    diff = 0
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        diff += 1
        if diff > 1:
            return False
        j += 1
    return True


@dataclass(frozen=True)
class WakeResult:
    heard: bool
    transcript: Optional[str] = None


def wait_for_wake_word(settings: Settings) -> WakeResult:
    """
    Listens in short bursts; returns when wake word is heard.
    Works with SpeechRecognition (mic) or text fallback.
    """
    candidates = _wake_candidates(settings)
    if not candidates:
        return WakeResult(heard=True, transcript=None)

    transcript = listen(
        language=settings.stt_language,
        timeout_s=settings.wake_listen_timeout_s,
        phrase_time_limit_s=settings.wake_phrase_time_limit_s,
        backend=settings.stt_backend,
        microphone_index=settings.stt_microphone_index,
        sounddevice_index=settings.sounddevice_input_index,
    )
    if not transcript:
        return WakeResult(heard=False, transcript=None)

    norm = _normalize(transcript)
    # Accept "yui" alone or inside phrase: "yui ...", "oye yui ..."
    words = norm.split()
    if any((w in words or w in norm) for w in candidates):
        return WakeResult(heard=True, transcript=transcript)

    fuzzy = (os.getenv("YUI_WAKE_WORD_FUZZY", "1") or "1").strip()
    if fuzzy not in {"0", "false", "False"}:
        for word in words:
            if len(word) < 2 or len(word) > 6:
                continue
            for cand in candidates:
                if _edit_distance_le1(word, cand):
                    return WakeResult(heard=True, transcript=transcript)

    return WakeResult(heard=False, transcript=transcript)


def strip_wake_word(text: str, settings: Settings) -> str:
    """
    Removes wake word from a transcript like "YUI dime la hora".
    """
    candidates = _wake_candidates(settings)
    if not candidates:
        return _normalize(text)
    candidates = sorted(candidates, key=len, reverse=True)
    wake = "|".join(re.escape(w) for w in candidates if w)
    t = _normalize(text)
    t = re.sub(rf"\b(?:{wake})\b[:,]?\s*", "", t).strip()
    return t
