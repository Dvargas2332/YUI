# YUI — Roadmap del Sistema de Voz

## Estado actual

| Componente | Estado | Notas |
|---|---|---|
| STT backend: Google (speech_recognition) | ✅ Funciona | Requiere internet, latencia 1-3s |
| STT backend: Whisper local (faster-whisper) | ✅ Implementado | Requiere `pip install faster-whisper` + modelo descargado |
| STT backend: sounddevice + Google | ✅ Funciona | Fallback sin PyAudio |
| TTS: edge-tts (Microsoft Neural) | ✅ Funciona | Voz es-CR-MariaNeural, requiere internet |
| TTS: pyttsx3 (local) | ✅ Funciona | Fallback offline |
| TTS: gTTS | ✅ Funciona | Fallback con internet |
| Wake word "YUI" + fuzzy matching | ✅ Funciona | Levenshtein ≤ 1, aliases configurables |
| Reproducción con pygame | ✅ Funciona | Genera archivo MP3, luego reproduce |
| Prosodia contextual (mood) | ✅ Funciona | Ajusta rate/pitch/volume por emoción detectada en texto |
| Botón mic en web UI | ✅ Implementado | Clic: grabar+enviar; Mantener: habla continua |
| Habla continua en web | ✅ Implementado | Loop automático: escucha → transcribe → envía |
| Endpoint `/api/voice` | ✅ Implementado | Recibe WebM del browser, transcribe, despacha como comando |

---

## Pendientes prioritarios

### 1. TTS Streaming (impacto alto, ~2h)
**Problema actual:** edge-tts genera el audio completo antes de reproducir.
Hay un delay de 1-3s antes de que YUI empiece a hablar.

**Solución:**
- Usar `edge_tts.Communicate.stream()` que entrega chunks de audio MP3 mientras genera.
- Reproducir con pygame en modo streaming (ir escribiendo en el mixer mientras llegan chunks).
- Para la web: emitir chunks por WebSocket como base64 y usar la Web Audio API para reproducir en tiempo real.

```python
# Esqueleto en yui_io/tts.py
async def _speak_edge_streaming(text, *, voice, rate, volume, pitch):
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]   # bytes MP3 parciales
```

---

### 2. Detección de emoción en voz del usuario (impacto medio, ~3h)
**Problema actual:** YUI solo detecta emoción en el *texto* de respuesta (prosodia contextual).
No sabe si el usuario suena enojado, triste o alegre al hablar.

**Solución:**
- Extraer features del audio antes de transcribir: pitch promedio, energía RMS, velocidad de habla.
- Clasificar en `neutral | felicidad | enojo | tristeza | angustia` con un modelo liviano.
- Librerías sugeridas:
  - `opensmile` — extracción de features estándar (IS09 emotional feature set)
  - `speechbrain` — modelos preentrenados de clasificación de emoción en voz
  - Alternativa simple: reglas basadas en pitch + energía (sin dependencias extra)

```python
# En yui_io/stt.py — extender listen() para retornar también emoción
def listen_with_emotion(...) -> tuple[Optional[str], Optional[str]]:
    audio = _record_audio(...)
    text = transcribe_audio_bytes(audio)
    emotion = _classify_emotion(audio)   # "neutral" | "felicidad" | ...
    return text, emotion
```

- Integrar en `VoiceAssistant.listen()` → pasar `emotion` al `brain.reply()` → ajustar prosodia TTS.

---

### 3. VAD real con webrtcvad (impacto medio, ~1h)
**Problema actual:** El habla continua en la web usa un timeout fijo de 6s (poco preciso).
El backend sounddevice usa un VAD simple basado en RMS.

**Solución:**
- `pip install webrtcvad` — VAD de Google WebRTC, muy ligero y preciso.
- Reemplazar el loop de bloques en `_listen_sounddevice_google` con webrtcvad.
- Para la web: implementar VAD en JavaScript con el `AudioWorkletProcessor` de la Web Audio API
  y cortar la grabación automáticamente cuando hay silencio real.

```python
# En yui_io/stt.py
import webrtcvad
vad = webrtcvad.Vad(aggressiveness=2)  # 0=permisivo, 3=agresivo
is_speech = vad.is_speech(frame_bytes, sample_rate=16000)
```

---

### 4. Whisper en modo streaming (impacto alto, ~4h)
**Problema actual:** Whisper transcribe después de que el usuario termina de hablar.
No hay retroalimentación visual de lo que está transcribiendo en tiempo real.

**Solución:**
- faster-whisper tiene soporte experimental para transcripción de chunks.
- Implementar `_listen_whisper_stream()` que va mostrando el texto parcial en la UI
  mientras el usuario habla (como los subtítulos en tiempo real de Google Meet).
- Requiere WebSocket bidireccional: el frontend envía chunks de audio, el backend
  responde con texto parcial.

---

### 5. Chat de voz en VSCode extension (impacto medio, ~2h)
**Problema actual:** La extensión VSCode no tiene botón de micrófono.

**Solución:**
- Agregar botón mic en `panel.js` de la extensión.
- Usar la misma API `MediaRecorder` del browser (funciona en WebView de VSCode).
- Enviar al mismo endpoint `/api/voice` del servidor HTTP de YUI.
- Mostrar el estado (grabando/procesando) en el panel.

---

## Instalación de dependencias de voz

```bash
# STT local con Whisper (recomendado)
pip install faster-whisper

# Conversión de formatos de audio (necesario para endpoint web)
pip install pydub
# + instalar ffmpeg: https://ffmpeg.org/download.html  (agregar al PATH)

# VAD preciso (opcional pero recomendado)
pip install webrtcvad

# Análisis de emoción en voz (opcional)
pip install opensmile
# o
pip install speechbrain
```

## Variables de entorno de voz

```env
# STT
YUI_STT_BACKEND=auto          # auto|whisper|speech_recognition|sounddevice|text
YUI_STT_LANGUAGE=es-CR
YUI_WHISPER_MODEL=base        # tiny|base|small|medium|large-v3
YUI_WHISPER_DEVICE=cpu        # cpu|cuda
YUI_WHISPER_COMPUTE=int8      # int8|float16|float32

# TTS
YUI_TTS_ENGINE=edge           # edge|pyttsx3|gtts
YUI_TTS_VOICE=es-CR-MariaNeural
YUI_TTS_EDGE_RATE=+0%
YUI_TTS_EDGE_PITCH=+0Hz
YUI_TTS_CONTEXTUAL=true

# Wake word
YUI_WAKE_WORD=yui
YUI_WAKE_WORD_ENABLED=true
YUI_WAKE_WORD_ALIASES=yu,ui   # aliases separados por coma
```
