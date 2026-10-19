"""Small shared helpers: git, diff capture, JSON(L) IO."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

_GIT_ENV = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_AUTHOR_NAME": "measure-2721",
    "GIT_AUTHOR_EMAIL": "measure-2721@invalid",
    "GIT_COMMITTER_NAME": "measure-2721",
    "GIT_COMMITTER_EMAIL": "measure-2721@invalid",
}


def git(cwd: Path | str, *args: str, env: Mapping[str, str] | None = None, check: bool = True) -> str:
    merged = {**os.environ, **_GIT_ENV, **(env or {})}
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), env=merged, capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {result.stderr.strip()[-500:]}")
    return result.stdout


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def capture_diff(worktree: Path | str, base: str) -> str:
    """Full diff of the working tree (tracked + untracked) against ``base``.

    Uses a throwaway index so the worktree's own index and files stay
    untouched; ignored files are left out, as ``git add -A`` does.
    """
    worktree = Path(worktree)
    with tempfile.TemporaryDirectory(prefix="m2721-index-") as tmp:
        env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        git(worktree, "read-tree", base, env=env)
        git(worktree, "add", "-A", "--", ".", env=env)
        return git(worktree, "diff", "--cached", "--binary", "--no-color", "--no-ext-diff", base, env=env)


def diff_paths(diff: str) -> list[str]:
    paths: list[str] = []
    for line in diff.splitlines():
        if line.startswith("diff --git a/"):
            rest = line[len("diff --git a/") :]
            path = rest.split(" b/", 1)[0]
            if path not in paths:
                paths.append(path)
    return paths


def write_json(path: Path, value: Any, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    if mode is not None:
        os.chmod(path, mode)


def append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def read_jsonl(path: Path | str) -> Iterator[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
