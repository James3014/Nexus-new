"""Materialize tasks into clean, history-free checkouts at their base commit.

For every task row (tasks.jsonl schema of taskbank-2721) this creates
``<out>/tasks/<task_id>/base``: a fresh repository holding **only** the base
commit (``git fetch --depth 1`` of that sha from the local mirror), checked
out detached.  Consequences, all by construction:

* the hidden tests are withheld: ``test_patch`` is never applied;
* the merged fix cannot leak through git: no later commit, ref, tag or remote
  exists in the checkout (``rev-list --all`` is exactly the base);
* both arms start from byte-identical trees (the BARE arm clones this
  checkout per run; the NEXUS arm uses it as the external target).

Next to it ``task.json`` holds the shared task text (``task_text.py``), the
fixed scope (``scope.py``) and hashes, and ``TASK_PROMPT.txt`` the rendered
base worker prompt.  Gold and test patches are never copied out.

The source mirrors are only read (``upload-pack``); nothing is written to them.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.bench.measure_2721.common import git, read_jsonl, sha256_text, write_json, write_jsonl
from scripts.bench.measure_2721.scope import SCOPE_VERSION, scope_for
from scripts.bench.measure_2721.task_text import build_task_text, render_worker_prompt

MANIFEST_SCHEMA = "nexus.measure_2721.task_manifest.v1"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def mirror_for(repos_root: Path, repo: str) -> Path:
    return repos_root / repo.split("/", 1)[1]


def checkout_base(mirror: Path, base_commit: str, dest: Path) -> None:
    """A repository containing only ``base_commit``, checked out detached."""
    if not _SHA_RE.fullmatch(base_commit):
        raise ValueError(f"base_commit must be a full sha: {base_commit!r}")
    if not (mirror / ".git").exists() and not (mirror / "HEAD").exists():
        raise FileNotFoundError(f"mirror is not a git repository: {mirror}")
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    git(dest, "init", "-q")
    git(dest, "fetch", "-q", "--depth", "1", "--no-tags", f"file://{mirror.resolve()}", base_commit)
    git(dest, "checkout", "-q", "--detach", "FETCH_HEAD")
    # No reflog or FETCH_HEAD pointer to the source; HEAD is the only ref.
    for leftover in ("FETCH_HEAD", "ORIG_HEAD"):
        (dest / ".git" / leftover).unlink(missing_ok=True)
    git(dest, "reflog", "expire", "--expire=now", "--all")
    verify_base_checkout(dest, base_commit)


def verify_base_checkout(dest: Path, base_commit: str) -> None:
    head = git(dest, "rev-parse", "HEAD").strip()
    if head != base_commit:
        raise RuntimeError(f"checkout HEAD {head} != base {base_commit}")
    reachable = git(dest, "rev-list", "--all").split()
    if reachable != [base_commit]:
        raise RuntimeError(f"checkout must hold only the base commit, found {len(reachable)}")
    if git(dest, "for-each-ref").strip():
        raise RuntimeError("checkout must have no refs besides detached HEAD")
    if git(dest, "remote").strip():
        raise RuntimeError("checkout must have no remote")
    if git(dest, "status", "--porcelain", "--untracked-files=all").strip():
        raise RuntimeError("checkout is not clean")


def task_venv(venv_root: Path | None, task_id: str) -> str | None:
    if venv_root is None:
        return None
    venv = Path(venv_root) / task_id
    if not (venv / "bin" / "python").exists():
        raise FileNotFoundError(f"{task_id}: no venv at {venv}")
    return str(venv.resolve())


def link_venv(task: Mapping[str, Any], repo_dir: Path) -> None:
    """Put the task venv beside a run's controller/target repo as ``../venv``."""
    if task.get("venv"):
        link = repo_dir.parent / "venv"
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(task["venv"])


def _patch_files(patch: str) -> list[str]:
    return re.findall(r"^diff --git a/(\S+) b/", patch or "", re.M)


def materialize_task(row: Mapping[str, Any], repos_root: Path, out: Path,
                     venv_root: Path | None = None) -> dict[str, Any]:
    task_id = str(row["id"])
    if not _ID_RE.fullmatch(task_id):
        raise ValueError(f"unsafe task id: {task_id!r}")
    repo = str(row["repo"])
    base = str(row["base_commit"])
    scope = scope_for(repo)
    text = build_task_text(str(row["problem_statement"]), scope)
    task_dir = out / "tasks" / task_id
    base_dir = task_dir / "base"
    checkout_base(mirror_for(repos_root, repo), base, base_dir)
    # Files the hidden test patch would create must not exist in the checkout.
    leaked_new_tests = [
        path
        for path in _patch_files(str(row.get("test_patch") or ""))
        if f"--- /dev/null\n+++ b/{path}" in str(row.get("test_patch") or "") and (base_dir / path).exists()
    ]
    if leaked_new_tests:
        raise RuntimeError(f"{task_id}: hidden test files already present in base")
    prompt = render_worker_prompt(text)
    (task_dir / "TASK_PROMPT.txt").write_text(prompt, encoding="utf-8")
    record = {
        "schema": MANIFEST_SCHEMA,
        "task_id": task_id,
        "set": row.get("set"),
        "repo": repo,
        "base_commit": base,
        "base_checkout": str(base_dir.resolve()),
        "scope": list(scope),
        "scope_version": SCOPE_VERSION,
        "text": text.as_dict(),
        "text_sha256": text.sha256(),
        "prompt_sha256": sha256_text(prompt),
        "test_patch_withheld": True,
        "hidden_test_file_count": len(_patch_files(str(row.get("test_patch") or ""))),
        # Per-task read-only venv (built separately, deps at base, no package
        # install); both arms see it at <run controller>/../venv.
        "venv": task_venv(venv_root, task_id),
    }
    write_json(task_dir / "task.json", record)
    return record


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tasks", required=True, help="tasks.jsonl (read only)")
    parser.add_argument("--repos-root", required=True, help="directory of local mirrors named after the repo")
    parser.add_argument("--out", required=True)
    parser.add_argument("--ids", nargs="*", help="only these task ids")
    parser.add_argument("--set", dest="task_set", help="only rows of this set (M, LA, LB)")
    parser.add_argument("--venv-root", help="directory of per-task venvs named by task id (optional)")
    args = parser.parse_args(argv)
    out = Path(args.out)
    rows = list(read_jsonl(args.tasks))
    if args.ids:
        wanted = set(args.ids)
        rows = [row for row in rows if row["id"] in wanted]
        missing = wanted - {row["id"] for row in rows}
        if missing:
            parser.error(f"unknown ids: {sorted(missing)}")
    if args.task_set:
        rows = [row for row in rows if row.get("set") == args.task_set]
    venv_root = Path(args.venv_root) if args.venv_root else None
    records = [materialize_task(row, Path(args.repos_root), out, venv_root) for row in rows]
    write_jsonl(out / "manifest.jsonl", records)
    print(json.dumps({"materialized": len(records), "manifest": str(out / "manifest.jsonl")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
