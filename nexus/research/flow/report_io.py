from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_output_file(repo_root: Path, path: Path, payload: dict[str, Any]) -> Path:
    out = path if path.is_absolute() else (repo_root / path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out
