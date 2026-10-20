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
    # surrogateescape: a byte-exact diff read with errors="surrogateescape"
    # round-trips to the same bytes (and so the same hash).
    return hashlib.sha256(text.encode("utf-8", errors="surrogateescape")).hexdigest()


# The shared measurement diff rule (#2761, used by P1's
# ``measurement_worktree_diff`` and by the BARE arm): attributes only from the
# base tree, no textconv/attributes file, no system/global config, no
# fsmonitor/hooks/transports, no inherited GIT_* variables, byte-exact output.
_SHARED_GIT_CONFIG = (
    "-c", "core.fsmonitor=false",
    "-c", "core.hooksPath=/dev/null",
    "-c", "protocol.allow=never",
    "-c", "core.attributesFile=/dev/null",
    "-c", "core.splitIndex=false",
    "-c", "core.untrackedCache=false",
    "-c", "index.threads=1",
)  # fmt: skip


def _shared_rule_env(index_file: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        GIT_INDEX_FILE=str(index_file),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_ATTR_NOSYSTEM="1",
        GIT_TERMINAL_PROMPT="0",
    )
    return env


def capture_diff_bytes(worktree: Path | str, base: str) -> bytes:
    """Byte-exact diff of the working tree (tracked + untracked) against ``base``
    under the shared rule; a throwaway index leaves the worktree's own index alone."""
    worktree = Path(worktree)
    with tempfile.TemporaryDirectory(prefix="m2721-index-") as tmp:
        env = _shared_rule_env(Path(tmp) / "index")
        attr = f"--attr-source={base}"

        def run(*args: str) -> bytes:
            result = subprocess.run(
                ["git", *_SHARED_GIT_CONFIG, attr, *args], cwd=str(worktree), env=env,
                capture_output=True, stdin=subprocess.DEVNULL, check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(f"git {args[0]} failed: {result.stderr.decode(errors='replace')[-300:]}")
            return result.stdout

        run("read-tree", base)
        run("add", "-A", "--", ".")
        return run("diff", "--cached", "--binary", "--no-color", "--no-ext-diff", "--no-textconv", base)


def capture_diff(worktree: Path | str, base: str) -> str:
    """``capture_diff_bytes`` as text that round-trips byte for byte."""
    return capture_diff_bytes(worktree, base).decode("utf-8", errors="surrogateescape")


def write_diff(path: Path, diff: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(diff.encode("utf-8", errors="surrogateescape"))


def read_diff(path: Path) -> str:
    return Path(path).read_bytes().decode("utf-8", errors="surrogateescape")


_GIT_META = ("config", "info", "hooks")


def git_meta_fingerprint(repo: Path | str, worktree: Path | str | None = None) -> str:
    """sha256 over ``.git/config``, ``.git/info/*`` and ``.git/hooks/*`` of the
    repository (and the worktree's ``.git`` file, when given) (#2749).

    Taken at materialize time and again before capture: a mismatch means the
    git configuration was changed, and no git command is run."""
    root = Path(repo) / ".git"
    digest = hashlib.sha256()
    if worktree is not None:
        dot_git = Path(worktree) / ".git"
        digest.update(b"W " + (dot_git.read_bytes() if dot_git.is_file() else b"<not a file>") + b"\n")
    for name in _GIT_META:
        entry = root / name
        paths = sorted(p for p in entry.rglob("*") if p.is_file() or p.is_symlink()) if entry.is_dir() else [entry]
        for path in paths:
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                digest.update(f"L {rel} {os.readlink(path)}\n".encode())
            elif path.is_file():
                digest.update(f"F {rel} ".encode() + hashlib.sha256(path.read_bytes()).hexdigest().encode() + b"\n")
            else:
                digest.update(f"- {rel}\n".encode())
    return digest.hexdigest()


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
