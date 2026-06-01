from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FindingsFileStore:
    """Filesystem persistence for findings cards."""

    base_path: Path

    def ensure_dirs(self) -> None:
        for scope in ["task", "global"]:
            for kind in ["papers", "knowledge", "episodes", "decisions", "ideas"]:
                (self.base_path / scope / kind).mkdir(parents=True, exist_ok=True)

    def card_path(self, *, scope: str, kind: str, card_id: str, task_id: str = "") -> Path:
        safe_task_id = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in task_id)
        filename = f"{safe_task_id}_{card_id}.json" if safe_task_id else f"{card_id}.json"
        return self.base_path / scope / kind / filename

    def write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=4, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    def read_json(self, path: Path) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
