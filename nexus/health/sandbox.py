from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Callable


class SpeculativeSandbox:
    """Temporary repo clone for speculative validation before mainline apply."""

    def __init__(self, source_root: Path):
        self.source_root = Path(source_root)
        self.sandbox_root: Path | None = None

    def fork(self) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix="nexus_sandbox_"))
        self.sandbox_root = temp_dir / "repo"
        shutil.copytree(
            self.source_root,
            self.sandbox_root,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                ".git",
                ".venv",
                "__pycache__",
                ".pytest_cache",
                ".ruff_cache",
                ".mypy_cache",
                ".nexus/runs",
            ),
        )
        return self.sandbox_root

    def run(
        self,
        manifest_path: Path,
        runner: Callable[[Path, Path | None], int],
    ) -> int:
        if self.sandbox_root is None:
            raise RuntimeError("sandbox not initialized")
        return runner(manifest_path, self.sandbox_root)

    def cleanup(self) -> None:
        if self.sandbox_root is None:
            return
        shutil.rmtree(self.sandbox_root.parent, ignore_errors=True)
        self.sandbox_root = None
