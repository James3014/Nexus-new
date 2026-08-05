"""Workspace isolation used before the World C pipeline may mutate files."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from nexus.services.local_heal.armor_artifact_storage import make_isolated_workspace


_IGNORED_NAMES = {
    ".git",
    ".nexus",
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
}


def prepare_world_c_workspace(
    source_root: str | Path,
    task_id: str,
    *,
    target_file: str = "",
    repro_script: str = "",
) -> Path:
    """Copy the source snapshot before HealOrchestrator patch/verify execution."""
    source = Path(source_root).expanduser().resolve()
    if not source.is_dir():
        raise ValueError("world_c_source_root_missing")
    safe_task = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(task_id)).strip("-") or "unknown"
    target = make_isolated_workspace(prefix=f"world-c-{safe_task[:32]}-")

    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {name for name in names if name in _IGNORED_NAMES}

    if (source / ".git").exists() or (source / "pyproject.toml").exists():
        shutil.copytree(
            source,
            target,
            dirs_exist_ok=True,
            symlinks=True,
            ignore=ignore,
        )
    else:
        # Synthetic workspaces must not expand an arbitrary parent such as /tmp.
        for relative in (target_file, repro_script):
            if not relative:
                continue
            relative_path = Path(relative)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                continue
            source_path = source / relative_path
            target_path = target / relative_path
            if source_path.is_file():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path)
    return target.resolve()
