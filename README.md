# YUI — Agente de IA Generativa Local

**YUI** es un agente de inteligencia artificial generativa personal, diseñado para ejecutarse completamente en local. A diferencia de los sistemas multi-agente clásicos, YUI opera como **un único agente con un cerebro unificado** que sabe, de forma autónoma, qué partes de sí mismo deben activarse ante cada situación — voz, visión, memoria, escritorio, seguridad — reaccionando de manera coordinada como si fueran múltiples especialistas, pero desde una sola mente coherente.

> Copyright © 2026 Diego Alonso Vargas Almengor. Todos los derechos reservados.

---

## Arquitectura: Un agente, múltiples capacidades

La mayoría de los sistemas de IA avanzados simulan colaboración dividiendo el trabajo entre agentes independientes. YUI toma un camino diferente:

> **YUI es un único agente generativo** que razona sobre su propio estado interno y decide en tiempo real qué módulos de su cerebro necesita invocar para responder correctamente.

Cuando procesas una petición, YUI no delega en otro agente — evalúa si necesita hablar, ver, recordar, actuar en el escritorio o buscar en internet, y activa exactamente esas capacidades en el momento justo. El resultado es un comportamiento que *parece* multi-agente pero que mantiene contexto, coherencia y personalidad unificados en todo momento.

---

## Capacidades del agente

Cada capacidad es un módulo del cerebro de YUI que el agente activa según el contexto de la conversación:

| Módulo | Descripción |
|---|---|
| **Razonamiento LLM** | Compatible con cualquier endpoint `/v1/chat/completions` (MiMo, DeepSeek, OpenAI, Ollama…) |
| **Voz (STT)** | Reconocimiento de voz con `speech_recognition` / `sounddevice` + wake word configurable |
| **Voz (TTS)** | Síntesis con `edge-tts` (voz natural es-MX-DaliaNeural por defecto) |
| **Visión** | Cámara + MediaPipe: detección de rostro, manos y gestos en tiempo real |
| **Autenticación facial** | Reconocimiento de personas por nombre desde `known_faces/` |
| **Memoria** | SQLite — corto y largo plazo, resúmenes automáticos, recuperación semántica |
| **Automatización** | Control del escritorio con confirmación de seguridad (código 6 dígitos + UI) |
| **Seguridad** | Guard de URLs/archivos, monitoreo defensivo, auditorías del sistema |
| **Interfaz web** | Panel en `http://127.0.0.1:8080` + WebSocket en puerto `8765` |
| **Extensión VSCode** | Sidebar integrado en el editor con chat, config y soporte MIMO |
| **Plugins / Extensions** | Catálogo modular extensible con carpetas `plugins/` y `extensions/` |

---

## Requisitos

- Python 3.11 o superior (3.13 recomendado)
- Windows 10/11 (soporte principal); Linux/macOS experimental
- API Key de un proveedor LLM compatible (MiMo, DeepSeek, OpenAI, etc.)
- Cámara web (opcional, para visión y autenticación facial)
- Micrófono (opcional, para entrada de voz)

---

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/dvargas2332/YUI.git
cd YUI
```

### 2. Crear entorno virtual e instalar dependencias

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 3. Configurar el entorno

Copia `.env.example` como `.env` y edita los valores:

```bash
copy .env.example .env
```

Variables mínimas necesarias:

```env
YUI_LLM_API_KEY=tu-api-key
YUI_LLM_BASE_URL=https://api.xiaomimimo.com/v1
YUI_LLM_MODEL=mimo-v2.5-pro
YUI_LLM_MODEL_FAST=mimo-v2.5-pro
YUI_LLM_MODEL_DEEP=mimo-v2.5-pro
```

### 4. Ejecutar

```bash
python main.py
```

Abre el panel web en: `http://127.0.0.1:8080`

---

## Extensión de VSCode

YUI incluye una extensión para Visual Studio Code que integra el asistente directamente en el sidebar del editor.

**Instalación:**
```bash
cd vscode-extension
npm install
npm run package
code --install-extension yui-assistant-1.1.1.vsix
```

**Funciones:**
- Chat con YUI desde el sidebar sin salir del editor
- Botones Iniciar / Detener el servidor YUI
- Configuración de LLM, idioma STT, motor TTS e integración MIMO
- Enviar selección de código directamente al chat (`clic derecho → YUI: Enviar selección`)
- Auto-start al abrir VSCode

---

## Proveedor LLM — Xiaomi MiMo

YUI está optimizado para usar la API de **Xiaomi MiMo**, un modelo de razonamiento de código abierto compatible con el protocolo OpenAI.

| Parámetro | Valor |
|---|---|
| Base URL | `https://api.xiaomimimo.com/v1` |
| Modelos disponibles | `mimo-v2.5-pro`, `mimo-v2.5` |
| Header de autenticación | `api-key: <tu-key>` |
| Temperatura recomendada | `1.0` / `top_p: 0.95` |

---

## Variables de entorno principales

### LLM
| Variable | Descripción | Ejemplo |
|---|---|---|
| `YUI_LLM_API_KEY` | API Key del proveedor | `tp-xxx...` |
| `YUI_LLM_BASE_URL` | URL base del endpoint | `https://api.xiaomimimo.com/v1` |
| `YUI_LLM_MODEL` | Modelo por defecto | `mimo-v2.5-pro` |
| `YUI_LLM_MODEL_FAST` | Modelo para respuestas rápidas | `mimo-v2.5-pro` |
| `YUI_LLM_MODEL_DEEP` | Modelo para análisis profundo | `mimo-v2.5-pro` |
| `YUI_LLM_TEMPERATURE` | Temperatura del LLM | `0.4` |
| `YUI_LLM_MAX_TOKENS` | Tokens máximos por respuesta | `240` |

### Voz
| Variable | Descripción | Ejemplo |
|---|---|---|
| `YUI_VOICE_ENABLED` | Habilitar salida de voz TTS | `1` |
| `YUI_STT_BACKEND` | Backend de reconocimiento de voz | `auto` / `text` |
| `YUI_STT_LANGUAGE` | Idioma del reconocimiento de voz | `es-MX` |
| `YUI_TTS_ENGINE` | Motor TTS | `edge` |
| `YUI_TTS_VOICE` | Voz TTS | `es-MX-DaliaNeural` |
| `YUI_WAKE_WORD_ENABLED` | Activar detección de wake word | `1` |
| `YUI_WAKE_WORD` | Palabra de activación | `yui` |

### Visión y cámara
| Variable | Descripción | Ejemplo |
|---|---|---|
| `YUI_VISION_ENABLED` | Habilitar módulo de visión | `1` |
| `YUI_CAMERA_INDEX` | Índice de la cámara (`-1` = auto) | `-1` |
| `YUI_PREVIEW` | Mostrar ventana de previsualización | `1` |
| `YUI_GESTURE_RECOGNIZER` | Habilitar reconocimiento de gestos | `1` |

### Escritorio y seguridad
| Variable | Descripción | Ejemplo |
|---|---|---|
| `YUI_DESKTOP_ENABLED` | Habilitar automatización de escritorio | `1` |
| `YUI_SECURITY_GUARD` | Guardia de seguridad para URLs/archivos | `1` |
| `YUI_CONFIRM_UI_ALLOWED` | Confirmar acciones sensibles por UI | `1` |
| `YUI_CONFIRM_CODE_DIGITS` | Dígitos del código de confirmación | `6` |

---

## Comandos de voz / texto

### Generales
- `"para"` / `"detente"` — cancela la acción en curso
- `"no escuches"` — silencia el micrófono
- `"escucha"` — reactiva el micrófono

### Seguridad y auditorías
- `auditoria seguridad` — escanea Defender y firewall
- `auditoria procesos` — detecta procesos sospechosos
- `auditoria puertos` — lista puertos en escucha con su proceso
- `auditoria extensiones` — revisa extensiones de Chrome/Edge
- `escanea archivo RUTA` — escanea un archivo con Windows Defender
- `escanea descargas` — escanea la carpeta de descargas
- `activa vigilancia` / `desactiva vigilancia` — monitoreo defensivo en tiempo real

---

## Reconocimiento facial (opcional)

1. Crea la carpeta `known_faces/` en la raíz del proyecto
2. Añade imágenes con el nombre de la persona: `Ana.jpg`, `Carlos.png`
3. YUI saludará por nombre cuando reconozca el rostro en cámara

---

## Estructura del proyecto

```
YUI/
├── main.py                  # Punto de entrada principal
├── config/
│   └── settings.py          # Carga y validación de configuración
├── core/
│   ├── brain.py             # Cliente LLM principal
│   ├── hybrid_brain.py      # Cerebro híbrido (estilos, macros, memoria)
│   ├── voice_processing.py  # STT + TTS + wake word
│   ├── vision_engine.py     # Cámara + MediaPipe
│   ├── face_authentication.py
│   ├── memory.py            # Memoria corto/largo plazo (SQLite)
│   └── integrations.py      # Catálogo de plugins y extensiones
├── desktop/
│   ├── controller.py        # Automatización de escritorio
│   ├── security_watch.py    # Monitoreo defensivo
│   ├── screen_context.py    # Contexto de ventana activa
│   └── tasks.py             # Tareas grabadas/reproducibles
├── ui/
│   ├── http_server.py       # API REST (puerto 8080)
│   ├── ws_server.py         # Servidor WebSocket (puerto 8765)
│   └── web/                 # Frontend web del panel
├── vscode-extension/        # Extensión para VSCode
├── plugins/                 # Plugins locales (plugin.json)
├── extensions/              # Extensiones locales (extension.json)
├── data/                    # Archivos de datos en tiempo de ejecución
├── known_faces/             # Imágenes para autenticación facial
└── .env                     # Configuración privada (NO subir a git)
```

---

## API REST

El servidor HTTP expone una API local en `http://127.0.0.1:8080`:

| Endpoint | Método | Descripción |
|---|---|---|
| `/api/bootstrap` | GET | Estado completo del sistema (historial, permisos, config) |
| `/api/command` | POST | Enviar un comando de texto a YUI |
| `/api/toggle` | POST | Activar/desactivar permisos en tiempo real |
| `/api/config` | POST | Actualizar variables de entorno en caliente |

---

## Modo solo texto (sin voz ni cámara)

Para ejecutar YUI en modo agente de texto puro, ideal para desarrollo:

```env
YUI_AGENT_TEXT_ONLY=1
YUI_VOICE_ENABLED=0
YUI_VISION_ENABLED=0
YUI_DESKTOP_ENABLED=1
```

---

## Seguridad y privacidad

- YUI **no envía datos a servidores externos** salvo las peticiones al LLM configurado
- El módulo de visión **no guarda imágenes** ni capturas de pantalla — solo embeddings numéricos
- Las confirmaciones de acciones sensibles requieren un código de 6 dígitos
- El guard de seguridad bloquea URLs no HTTPS y dominios en lista negra
- **No subas `.env` a git** — contiene tu API key

---

## Licencia

Copyright © 2026 Diego Alonso Vargas Almengor. Todos los derechos reservados.

Este software es de uso personal y privado. No se permite su distribución, copia, modificación ni uso comercial sin autorización expresa del autor.
