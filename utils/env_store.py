from __future__ import annotations

from pathlib import Path


def set_env_value(env_path: Path, key: str, value: str) -> None:
    env_path = Path(env_path)
    key = (key or "").strip()
    if not key:
        return

    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    wanted = f"{key}={value}"
    out: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(wanted)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(wanted)
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
