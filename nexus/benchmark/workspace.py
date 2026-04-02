from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class BenchmarkWorkspace:
    repo_root: Path
    case_id: str
    run_dir: Path

    def __post_init__(self) -> None:
        self.repo_root = Path(self.repo_root)
        self.run_dir = Path(self.run_dir)
        self.workspace_root = self.run_dir / "workspace"

    def create(self) -> Path:
        self.workspace_root.parent.mkdir(parents=True, exist_ok=True)
        self._force_remove_workspace_path()
        self._prune_worktrees()
        try:
            self._worktree_add()
        except subprocess.CalledProcessError:
            # Stale worktree metadata is common after interrupted runs.
            self._prune_worktrees()
            self._force_remove_workspace_path()
            try:
                self._worktree_add()
            except subprocess.CalledProcessError as retry_exc:
                stderr = (retry_exc.stderr or "").strip()
                raise RuntimeError(
                    f"git worktree add failed for {self.workspace_root}: {stderr or retry_exc}"
                ) from retry_exc
        return self.workspace_root

    def apply_fixture(self, case_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        fixture = case_data.get("benchmark_fixture")
        if not fixture:
            return None

        relative_file = fixture.get("file")
        target_text = fixture.get("target")
        replacement_text = fixture.get("replacement", "")
        if not relative_file or target_text is None:
            raise ValueError("benchmark_fixture requires file and target")

        file_path = self.workspace_root / relative_file
        original_text = file_path.read_text(encoding="utf-8")
        if target_text not in original_text:
            raise ValueError(f"benchmark fixture target not found in {relative_file}")

        mutated_text = original_text.replace(target_text, replacement_text, 1)
        file_path.write_text(mutated_text, encoding="utf-8")
        return {
            "relative_file": relative_file,
            "original_text": original_text,
        }

    def restore_fixture(self, applied_fixture: Optional[Dict[str, Any]]) -> None:
        if not applied_fixture:
            return
        relative_file = applied_fixture["relative_file"]
        original_text = applied_fixture["original_text"]
        file_path = self.workspace_root / relative_file
        file_path.write_text(original_text, encoding="utf-8")

    def cleanup(self) -> None:
        self._force_remove_workspace_path()
        self._prune_worktrees()

    def _worktree_add(self) -> None:
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repo_root),
                "worktree",
                "add",
                "--detach",
                str(self.workspace_root),
                "HEAD",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    def _force_remove_workspace_path(self) -> None:
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repo_root),
                "worktree",
                "remove",
                "--force",
                str(self.workspace_root),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if self.workspace_root.exists():
            shutil.rmtree(self.workspace_root, ignore_errors=True)

    def _prune_worktrees(self) -> None:
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repo_root),
                "worktree",
                "prune",
                "--expire",
                "now",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
