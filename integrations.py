from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class IntegrationManifest:
    kind: str
    id: str
    name: str
    version: str
    description: str
    entrypoint: str
    enabled: bool
    path: str


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _load_manifests(root: Path, *, kind: str, filename: str) -> list[IntegrationManifest]:
    manifests: list[IntegrationManifest] = []
    if not root.exists():
        return manifests

    for manifest_path in sorted(root.glob(f"*/{filename}")):
        data = _read_json(manifest_path)
        if not data:
            continue
        item_id = str(data.get("id") or manifest_path.parent.name).strip()
        name = str(data.get("name") or item_id).strip()
        manifests.append(
            IntegrationManifest(
                kind=kind,
                id=item_id,
                name=name,
                version=str(data.get("version") or "0.1.0").strip(),
                description=str(data.get("description") or "").strip(),
                entrypoint=str(data.get("entrypoint") or "").strip(),
                enabled=bool(data.get("enabled", True)),
                path=str(manifest_path.parent),
            )
        )
    return manifests


class IntegrationCatalog:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    @property
    def plugins_root(self) -> Path:
        return self.project_root / "plugins"

    @property
    def extensions_root(self) -> Path:
        return self.project_root / "extensions"

    def plugins(self) -> list[IntegrationManifest]:
        return _load_manifests(self.plugins_root, kind="plugin", filename="plugin.json")

    def extensions(self) -> list[IntegrationManifest]:
        return _load_manifests(self.extensions_root, kind="extension", filename="extension.json")

    def summary(self) -> dict[str, Any]:
        plugins = self.plugins()
        extensions = self.extensions()
        return {
            "plugins": [asdict(item) for item in plugins],
            "extensions": [asdict(item) for item in extensions],
            "counts": {"plugins": len(plugins), "extensions": len(extensions)},
        }
