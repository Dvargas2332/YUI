# Plugins de YUI

Cada plugin vive en su propia carpeta y expone un `plugin.json`.

Campos base:

```json
{
  "id": "mi-plugin",
  "name": "Mi Plugin",
  "version": "0.1.0",
  "description": "Qué aporta a YUI",
  "entrypoint": "plugin.py",
  "enabled": true
}
```

Este repositorio queda como base para conectar módulos de automatización, conectores o nuevas capacidades del agente.
