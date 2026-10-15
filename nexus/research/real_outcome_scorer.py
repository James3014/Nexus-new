"""Post-hoc real-outcome scorer for #1216 hybrid replication tasks.

Implements docs/research/REAL_OUTCOME_SCORER_SPEC.md (v1) together with the dated
amendment notes in docs/research/REAL_OUTCOME_SCORER_SPEC.amendments.md. The scorer is
read-only with respect to the experiment store: it verifies the sealed raw,
builds scorer-owned git trees (BASE, CAND, GOLD, BASE+T, CAND+T), derives a
FAIL_TO_PASS / PASS_TO_PASS oracle from the merged human fix, runs the tests in
a scrubbed environment and writes a create-only receipt to its own store.
"""

from __future__ import annotations

import base64
import binascii
import gzip
import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import time
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

SCORER_VERSION = "1.2.1"
RECEIPT_SCHEMA = "nexus.research.real_outcome.v1"
RECEIPT_SEAL_SCHEMA = "nexus.research.real_outcome_seal.v1"
SPEC_RELATIVE_PATH = "docs/research/REAL_OUTCOME_SCORER_SPEC.md"
# v2 = v1 + A5 (GOLD port fallback). Receipts whose GOLD needed the fallback record v2 and
# this file's sha256; every other receipt records v1 (pre-registered) and its sha256.
SPEC_V2_RELATIVE_PATH = "docs/research/REAL_OUTCOME_SCORER_SPEC.v2.md"
SPEC_V1, SPEC_V2 = "v1", "v2"

PYTEST_TIMEOUT_SECONDS = 1800
# Amendment A6 (operational, #2291): one pytest run that leaves more than this many bytes
# in the runner's TMPDIR (``scratch/tmp``) is a failed run for that tree, like a timeout.
SCRATCH_TMP_CAP_BYTES = 20 * 1024**3
SCRATCH_TMP_CAP_EXCEEDED = "SCRATCH_TMP_CAP_EXCEEDED"
# Exit code recorded for a run refused by the cap (never a real pytest exit code).
SCRATCH_TMP_CAP_EXIT_CODE = -2
ORACLE_RUNS = 3
SMALL_REPOS = frozenset({"nexus-runtime", "nexus-core", "nexus-learning"})
IMPACT_GATE_REPOS = frozenset({"Nexus-new"})

# Labels (spec §7), in evaluation order.
PENDING_GROUND_TRUTH = "PENDING_GROUND_TRUTH"
NOT_SCORABLE_NO_MERGED_PR = "NOT_SCORABLE_NO_MERGED_PR"
NOT_SCORABLE_NO_ORACLE = "NOT_SCORABLE_NO_ORACLE"
NOT_SCORABLE_ORACLE_INVALID = "NOT_SCORABLE_ORACLE_INVALID"
NO_CANDIDATE = "NO_CANDIDATE"
NOT_RUNNABLE = "NOT_RUNNABLE"
BROKE_EXISTING = "BROKE_EXISTING"
RESOLVED = "RESOLVED"
PARTIAL = "PARTIAL"
UNRESOLVED = "UNRESOLVED"

VALID_ORACLE_LABELS = frozenset({
    NO_CANDIDATE,
    NOT_RUNNABLE,
    BROKE_EXISTING,
    RESOLVED,
    PARTIAL,
    UNRESOLVED,
})

PASS, FAIL, SKIP = "pass", "fail", "skip"

# pytest exit codes that still yield a trustworthy junit report: 0 all passed, 1 some
# failed, 5 nothing collected (e.g. every module of the target is an ignored oracle file).
CLEAN_P2P_EXIT_CODES = frozenset({0, 1, 5})

_SHA_RE = re.compile(r"[0-9a-f]{40}")


class SealRefused(Exception):
    """Raised when a sealed input does not verify (spec §3). No receipt is written."""


class EnvBuildError(Exception):
    pass


class ReceiptExists(Exception):
    pass


# --------------------------------------------------------------------------- utils


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode()


def _digest_outcomes(outcomes: Mapping[str, str]) -> str:
    return sha256_bytes(json.dumps(sorted(outcomes.items()), separators=(",", ":")).encode())


def is_oracle_test_file(path: str) -> bool:
    p = PurePosixPath(path)
    parts = p.parts
    name = p.name
    if parts and parts[0] == "tests":
        return True
    if "tests" in parts[:-1]:
        return True
    if name == "conftest.py":
        return True
    return (name.startswith("test_") and name.endswith(".py")) or name.endswith("_test.py")


def is_oracle_module_name(path: str) -> bool:
    name = PurePosixPath(path).name
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


def parse_task_key(task_key: str) -> tuple[str, str, int]:
    owner, rest = task_key.split("__", 1)
    repo, number = rest.rsplit("--", 1)
    return owner, repo, int(number)


def is_full_sha(value: Any) -> bool:
    """True only for a lowercase 40-hex commit/tree id (never an option or a ref)."""
    return isinstance(value, str) and _SHA_RE.fullmatch(value) is not None


def _require_rev(rev: str) -> str:
    """Guard every revision handed to git: a full SHA, optionally with a ``^1`` suffix."""
    sha = rev[:-2] if rev.endswith("^1") else rev
    if not is_full_sha(sha):
        raise ValueError(f"refusing non-SHA git revision: {rev!r}")
    return rev


def _safe_relpath(path: str) -> bool:
    """Relative, no ``..``, and no ``.git`` component at any depth (case-insensitive:
    ``.GIT`` is the same directory on a case-insensitive filesystem)."""
    if not isinstance(path, str) or not path:
        return False
    p = PurePosixPath(path)
    return (
        not p.is_absolute()
        and ".." not in p.parts
        and not any(part.lower() == ".git" for part in p.parts)
    )


# --------------------------------------------------------------- sealed inputs


@dataclass
class Candidate:
    diff: bytes
    untracked: list[dict[str, Any]]  # {path, sha256, data}
    override: str | None = None

    @property
    def empty(self) -> bool:
        return not self.diff.strip() and not self.untracked

    @property
    def digest(self) -> str:
        payload = {
            "diff_sha256": sha256_bytes(self.diff),
            "untracked": sorted((u["path"], u["sha256"]) for u in self.untracked),
        }
        return sha256_bytes(json.dumps(payload, sort_keys=True).encode())


@dataclass
class TaskInputs:
    task_key: str
    owner: str
    repo: str
    issue: int
    task_dir: Path
    state: dict[str, Any]
    raw: dict[str, Any]
    base_sha: str
    candidate: Candidate
    so: dict[str, Any]
    route: str
    wall_time_seconds: float | None
    cap_seconds: float | None


def _decode_payload(value: Any, what: str) -> bytes:
    """gzip(base64) payload from the sealed raw; any malformation is a seal refusal."""
    try:
        return gzip.decompress(base64.b64decode(value, validate=True))
    except (binascii.Error, ValueError, TypeError, OSError, EOFError, zlib.error) as exc:
        raise SealRefused(f"payload_malformed:{what}:{type(exc).__name__}") from exc


def load_sealed_task(task_dir: Path) -> TaskInputs:
    """Spec §3.1, §3.2, §3.4 and §2. Raises SealRefused on any mismatch."""
    task_dir = Path(task_dir)
    try:
        raw_bytes = (task_dir / "raw.json").read_bytes()
        seal = json.loads((task_dir / "raw_seal.json").read_text())
        state = json.loads((task_dir / "state.json").read_text())
    except FileNotFoundError as exc:
        raise SealRefused(f"missing_sealed_file:{exc.filename}") from exc
    if sha256_bytes(raw_bytes) != seal.get("raw_sha256"):
        raise SealRefused("raw_sha256_mismatch")
    if state.get("raw_seal") != seal:
        raise SealRefused("state_raw_seal_mismatch")
    try:
        raw = json.loads(raw_bytes)
        rr = raw["raw_response"]
        so = rr["strong_online_raw_response"]
        base_sha = rr["candidate_packet"]["source_revision"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SealRefused(f"raw_shape_invalid:{exc}") from exc
    if not re.fullmatch(r"[0-9a-f]{40}", str(base_sha)):
        raise SealRefused("base_sha_invalid")
    diff = b""
    if so.get("diff_gzip_base64"):
        diff = _decode_payload(so["diff_gzip_base64"], "diff")
        if so.get("diff_sha256") and sha256_bytes(diff) != so["diff_sha256"]:
            raise SealRefused("diff_sha256_mismatch")
    untracked = []
    for item in so.get("untracked_files") or []:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise SealRefused("untracked_entry_invalid")
        data = _decode_payload(item.get("gzip_base64"), f"untracked:{item['path']}")
        if sha256_bytes(data) != item.get("sha256"):
            raise SealRefused(f"untracked_sha256_mismatch:{item.get('path')}")
        size = item.get("size")
        if size is not None:
            if isinstance(size, bool) or not isinstance(size, int):
                raise SealRefused(f"untracked_size_invalid:{item.get('path')}")
            if len(data) != size:
                raise SealRefused(f"untracked_size_mismatch:{item.get('path')}")
        untracked.append({"path": item["path"], "sha256": item["sha256"], "data": data})
    owner, repo, issue = parse_task_key(task_dir.name)
    wall = raw.get("wall_time_seconds")
    cap = rr.get("strong_online_timeout_seconds")
    return TaskInputs(
        task_key=task_dir.name,
        owner=owner,
        repo=repo,
        issue=issue,
        task_dir=task_dir,
        state=state,
        raw=raw,
        base_sha=base_sha,
        candidate=Candidate(diff=diff, untracked=untracked),
        so=so,
        route=str(raw.get("route", "")),
        wall_time_seconds=float(wall) if wall is not None else None,
        cap_seconds=float(cap) if cap is not None else None,
    )


def load_ground_truth(inputs: TaskInputs) -> dict[str, Any] | None:
    """Spec §3.3 / §4 step 2. Returns None when the task is not terminal."""
    state_gt = inputs.state.get("ground_truth")
    path = inputs.task_dir / "ground_truth.json"
    if not state_gt or not path.exists():
        return None
    data = path.read_bytes()
    if sha256_bytes(data) != state_gt.get("sha256"):
        raise SealRefused("ground_truth_sha256_mismatch")
    try:
        gt = json.loads(data)
    except ValueError as exc:
        raise SealRefused("ground_truth_shape_invalid:json") from exc
    if not isinstance(gt, dict):
        raise SealRefused("ground_truth_shape_invalid:not_object")
    details = gt.get("details", {})
    if details is None:
        details = {}
    if not isinstance(details, dict):
        raise SealRefused("ground_truth_shape_invalid:details")
    prs = details.get("merged_prs") or []
    if not isinstance(prs, list):
        raise SealRefused("ground_truth_shape_invalid:merged_prs")
    # Every SHA taken from ground truth is validated before any git call (it is passed to
    # `git fetch`, where a value such as `--upload-pack=...` would be an option).
    for pr in prs:
        if not isinstance(pr, dict) or not is_full_sha(pr.get("merge_commit_sha")):
            raise SealRefused("ground_truth_merge_commit_sha_invalid")
    return gt


# --------------------------------------------------------------------------- git


class GitRepo:
    """Scorer-owned repository. Commits are addressed by SHA only."""

    def __init__(self, path: Path, sources: Sequence[str]):
        self.path = Path(path)
        self.sources = list(sources)
        if not (self.path / ".git").exists():
            self.path.mkdir(parents=True, exist_ok=True)
            self.git("init", "-q")
            self.git("config", "gc.auto", "0")

    def git(
        self, *args: str, cwd: Path | None = None, input: bytes | None = None, check: bool = True
    ) -> subprocess.CompletedProcess[bytes]:
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update({
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "scorer",
            "GIT_AUTHOR_EMAIL": "scorer@invalid",
            "GIT_COMMITTER_NAME": "scorer",
            "GIT_COMMITTER_EMAIL": "scorer@invalid",
        })
        proc = subprocess.run(
            ["git", *args], cwd=str(cwd or self.path), input=input, capture_output=True, env=env
        )
        if check and proc.returncode != 0:
            raise RuntimeError(f"git {' '.join(args[:3])} failed: {proc.stderr.decode()[-400:]}")
        return proc

    def has_commit(self, sha: str) -> bool:
        _require_rev(sha)
        return self.git("cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode == 0

    def ensure_commit(self, sha: str) -> bool:
        if self.has_commit(sha):
            return True
        for source in self.sources:
            self.git("fetch", "-q", "--no-tags", "--", source, sha, check=False)
            if self.has_commit(sha):
                return True
        return False

    def worktree(self, dest: Path, sha: str) -> Path:
        dest = Path(dest)
        if dest.exists():
            self.git("worktree", "remove", "--force", str(dest), check=False)
            shutil.rmtree(dest, ignore_errors=True)
        self.git("worktree", "prune")
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.git("worktree", "add", "-q", "--detach", "--force", "--", str(dest), _require_rev(sha))
        return dest

    def remove_worktree(self, dest: Path) -> None:
        self.git("worktree", "remove", "--force", str(dest), check=False)
        shutil.rmtree(dest, ignore_errors=True)

    def tree_id(self, wt: Path, extra_paths: Iterable[str] = ()) -> str:
        self.git("add", "-A", cwd=wt)
        extra = [p for p in extra_paths if (wt / p).exists()]
        if extra:
            self.git("add", "-f", "--", *extra, cwd=wt)
        return self.git("write-tree", cwd=wt).stdout.decode().strip()

    def changed_paths(self, a: str, b: str) -> list[str]:
        out = self.git(
            "diff", "--no-renames", "--name-only", _require_rev(a), _require_rev(b), "--"
        ).stdout.decode()
        return sorted(p for p in out.splitlines() if p)

    def pr_patch(self, merge_sha: str, path: str | None = None) -> bytes:
        return self.git(
            "--literal-pathspecs",
            "diff",
            "--binary",
            "--no-renames",
            _require_rev(f"{merge_sha}^1"),
            _require_rev(merge_sha),
            "--",
            *([path] if path is not None else []),
        ).stdout

    def pr_paths(self, merge_sha: str) -> list[str]:
        """Paths the PR net patch changes (``-z``: no quoting, any byte is preserved)."""
        out = self.git(
            "diff",
            "--no-renames",
            "--name-only",
            "-z",
            _require_rev(f"{merge_sha}^1"),
            _require_rev(merge_sha),
            "--",
        ).stdout
        return [p.decode("utf-8", "surrogateescape") for p in out.split(b"\0") if p]

    def path_in(self, rev: str, path: str) -> bool:
        """True if ``path`` is a blob or link in commit/tree ``rev``."""
        out = self.git(
            "--literal-pathspecs", "ls-tree", "-z", _require_rev(rev), "--", path, check=False
        ).stdout
        return any(
            e.split(b"\t", 1)[-1] == path.encode("utf-8", "surrogateescape")
            for e in out.split(b"\0")
            if e
        )


# ------------------------------------------------------------------- GOLD port

GOLD_PORT_3WAY = "3way"
# v2: a GOLD_REF run (oracle or P2P) that times out or exits outside the clean codes.
GOLD_REF_RUN_FAILED = "GOLD_REF_RUN_FAILED"
GOLD_PORT_PER_FILE = "3way_per_file_fallback"
# Documentation whose PR change may be left out of GOLD when it does not merge onto BASE
# (spec v2, A5): prose files, and data files only inside a documentation tree. Code,
# config, workflow/action files (anything under .github/), package data (anything inside
# a Python package at BASE) and prompt/template/data trees are never dropped.
DROPPABLE_PROSE_SUFFIXES = frozenset({".md", ".rst"})
# .txt is data here: outside a doc tree it can be a dependency manifest (requirements.txt).
DROPPABLE_DOC_DATA_SUFFIXES = frozenset({".txt", ".json", ".jsonl", ".yml", ".yaml", ".csv"})
# Directory names whose files are commonly read at runtime (prompt text, templates, data).
NEVER_DROPPED_DIR_NAMES = frozenset({"prompts", "templates", "data"})


def _in_doc_tree(parts: Sequence[str]) -> bool:
    return bool(parts) and (parts[0] == "docs" or any(p.endswith("_wiki_vault") for p in parts))


def is_droppable_non_code(path: str, in_python_package: bool = False) -> bool:
    """``in_python_package``: some ancestor directory of ``path`` has ``__init__.py`` at
    BASE, so the file may be package data that the code reads at runtime."""
    p = PurePosixPath(path)
    parts = p.parts[:-1]
    if is_oracle_test_file(path) or ".github" in p.parts or in_python_package:
        return False
    if any(part.lower() in NEVER_DROPPED_DIR_NAMES for part in parts):
        return False
    suffix = p.suffix.lower()
    if suffix in DROPPABLE_PROSE_SUFFIXES:
        return True
    return suffix in DROPPABLE_DOC_DATA_SUFFIXES and _in_doc_tree(parts)


@dataclass
class GoldPort:
    ok: bool
    method: str = GOLD_PORT_3WAY
    test_files_from_merge: list[str] = field(default_factory=list)
    dropped_non_code_paths: list[str] = field(default_factory=list)
    # dropped path -> merge commit whose content GOLD_REF uses for it (the last PR wins)
    dropped_from: dict[str, str] = field(default_factory=dict)
    failed_pr: int | None = None
    failed_paths: list[str] = field(default_factory=list)

    def receipt_fields(self) -> dict[str, Any]:
        out: dict[str, Any] = {"gold_port_method": self.method}
        if self.method != GOLD_PORT_3WAY:
            out["gold_port_test_files_from_merge"] = sorted(set(self.test_files_from_merge))
            out["gold_port_dropped_non_code_paths"] = sorted(set(self.dropped_non_code_paths))
        if self.failed_paths:
            out["gold_port_failed_paths"] = sorted(self.failed_paths)
        return out


def _snapshot(repo: GitRepo, wt: Path) -> str:
    repo.git("add", "-A", cwd=wt)
    return repo.git("write-tree", cwd=wt).stdout.decode().strip()


def _restore_tree(repo: GitRepo, wt: Path, tree: str) -> None:
    repo.git("read-tree", "--reset", "-u", _require_rev(tree), cwd=wt)
    repo.git("clean", "-fdxq", cwd=wt)


def _set_path_from(repo: GitRepo, wt: Path, rev: str, path: str) -> None:
    """Set one path (index and worktree) to its state in ``rev``; delete it if absent."""
    repo.git(
        "--literal-pathspecs",
        "rm",
        "-q",
        "-r",
        "-f",
        "--cached",
        "--ignore-unmatch",
        "--",
        path,
        cwd=wt,
    )
    target = wt / path
    if not _inside(wt.resolve(), target.parent.resolve()):
        raise UnsafeTreePath(f"gold_path_escapes:{path}")  # never touch a file outside wt
    if target.is_symlink() or target.is_file():
        target.unlink()
    if repo.path_in(rev, path):
        repo.git("--literal-pathspecs", "checkout", _require_rev(rev), "--", path, cwd=wt)


def _in_python_package(repo: GitRepo, base: str, path: str) -> bool:
    """True if any ancestor directory of ``path`` has ``__init__.py`` in ``base``."""
    parents = PurePosixPath(path).parents
    return any(repo.path_in(base, f"{d.as_posix()}/__init__.py") for d in parents if d.parts)


def _unmerged(repo: GitRepo, wt: Path) -> bool:
    return bool(repo.git("ls-files", "-u", cwd=wt).stdout.strip())


def _apply_3way(repo: GitRepo, wt: Path, patch: bytes) -> bool:
    proc = repo.git("apply", "--3way", "--binary", "-", cwd=wt, input=patch, check=False)
    return proc.returncode == 0 and not _unmerged(repo, wt)


def port_gold(repo: GitRepo, wt: Path, prs: Sequence[Mapping[str, Any]]) -> GoldPort:
    """Spec §5 GOLD, with the amendment A5 fallback.

    Each PR net patch is first applied whole with ``git apply --3way`` (v1, unchanged).
    Only when that fails is the PR replayed file by file onto the pre-PR state:

    - a file whose own 3-way apply succeeds keeps that result;
    - an oracle test file that does not merge is set to its content in the merge commit
      (SWE-bench rule: tests are taken at their post-fix state);
    - a non-test documentation/data file (``DROPPABLE_SUFFIXES``) that does not merge is
      left at its pre-PR state and recorded;
    - any other file that does not merge is GOLD_PORT_FAILED, as in v1.

    So GOLD's non-test content is always BASE plus a subset of the human fix's non-test
    changes: every F2P node still flips because of the human fix alone.
    """
    port = GoldPort(ok=True)
    base = repo.git("rev-parse", "HEAD", cwd=wt).stdout.decode().strip()
    for p in prs:
        merge_sha = p["merge_commit_sha"]
        patch = repo.pr_patch(merge_sha)
        if not patch.strip():
            continue
        # A path dropped by an earlier PR and changed again here: GOLD_REF must use this
        # (later) merge commit's content for it, however this PR's own port goes.
        for path in set(repo.pr_paths(merge_sha)) & set(port.dropped_from):
            port.dropped_from[path] = merge_sha
        pre = _snapshot(repo, wt)
        if _apply_3way(repo, wt, patch):
            continue
        _restore_tree(repo, wt, pre)
        port.method = GOLD_PORT_PER_FILE
        failed: list[str] = []
        for path in repo.pr_paths(merge_sha):
            if not _safe_relpath(path):
                failed.append(path)
                continue
            file_patch = repo.pr_patch(merge_sha, path)
            if file_patch.strip() and _apply_3way(repo, wt, file_patch):
                continue
            try:
                _set_path_from(repo, wt, pre, path)  # undo the partial apply of this file
                if is_oracle_test_file(path):
                    _set_path_from(repo, wt, merge_sha, path)
                    port.test_files_from_merge.append(path)
                elif is_droppable_non_code(path, _in_python_package(repo, base, path)):
                    port.dropped_non_code_paths.append(path)
                    port.dropped_from[path] = merge_sha
                else:
                    failed.append(path)
            except (UnsafeTreePath, RuntimeError, OSError):
                failed.append(path)
                break
        if failed or _unmerged(repo, wt):
            port.ok = False
            port.failed_pr = int(p["number"])
            port.failed_paths = failed
            return port
    return port


def _inside(root_real: Path, path: Path) -> bool:
    try:
        path.relative_to(root_real)
    except ValueError:
        return False
    return True


def _base_symlinks(repo: GitRepo, wt: Path) -> dict[str, str]:
    """Symlinks tracked in the worktree's HEAD commit (BASE): path -> link target."""
    out = repo.git("ls-tree", "-r", "-z", "HEAD", cwd=wt).stdout
    links: dict[str, str] = {}
    for entry in out.split(b"\0"):
        if not entry.startswith(b"120000 "):
            continue
        meta, _, path = entry.partition(b"\t")
        blob = meta.split()[2].decode()
        target = repo.git("cat-file", "blob", blob, cwd=wt).stdout
        links[path.decode(errors="surrogateescape")] = target.decode(errors="surrogateescape")
    return links


def _escaping_symlinks(repo: GitRepo, wt: Path) -> list[str]:
    """Every symlink in ``wt`` (``.git`` skipped, links not followed) that resolves
    outside ``wt``, including git-ignored paths and chains of links.

    A symlink tracked unchanged in BASE is part of the repository, not of the candidate,
    and is not reported (Nexus-new tracks a few absolute links).
    """
    root_real = wt.resolve()
    bad: list[str] = []
    base_links: dict[str, str] | None = None
    for dirpath, dirnames, filenames in os.walk(wt, followlinks=False):
        if Path(dirpath) == wt:
            dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            if not p.is_symlink() or _inside(root_real, p.resolve()):
                continue
            rel = p.relative_to(wt).as_posix()
            if base_links is None:
                base_links = _base_symlinks(repo, wt)
            if base_links.get(rel) == os.readlink(p):
                continue
            bad.append(rel)
    return sorted(bad)


def _write_target_error(wt: Path, rel: str) -> str | None:
    """Spec §7 APPLY_FAILED: an untracked path that exists already or escapes the tree."""
    root_real = wt.resolve()
    target = wt / rel
    cur = wt
    for part in PurePosixPath(rel).parts[:-1]:
        cur = cur / part
        if cur.is_symlink() and not _inside(root_real, cur.resolve()):
            return f"untracked_path_escapes:{rel}"
    if os.path.lexists(target):
        return f"untracked_path_exists:{rel}"
    if not _inside(root_real, target.parent.resolve() / target.name):
        return f"untracked_path_escapes:{rel}"
    return None


def apply_candidate(repo: GitRepo, wt: Path, cand: Candidate) -> str | None:
    """Apply a candidate onto a BASE worktree. Returns an error string or None.

    Nothing is ever written outside ``wt``: a diff that creates a symlink resolving
    outside the tree, and an untracked file whose resolved target escapes the tree, are
    APPLY_FAILED (spec §7 row 6).
    """
    if cand.diff.strip():
        proc = repo.git("apply", "--binary", "-", cwd=wt, input=cand.diff, check=False)
        if proc.returncode != 0:
            return "diff_apply_failed:" + proc.stderr.decode()[-300:]
        escaping = _escaping_symlinks(repo, wt)
        if escaping:
            return "symlink_escapes_tree:" + ",".join(escaping)[:300]
    for item in cand.untracked:
        rel = item["path"]
        if not _safe_relpath(rel):
            return f"untracked_path_unsafe:{rel}"
        err = _write_target_error(wt, rel)
        if err:
            return err
        target = wt / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not _inside(wt.resolve(), target.parent.resolve()):
            return f"untracked_path_escapes:{rel}"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(target, flags, 0o644)
        except OSError as exc:
            return f"untracked_write_refused:{rel}:{exc.errno}"
        with os.fdopen(fd, "wb") as fh:
            fh.write(item["data"])
    return None


class UnsafeTreePath(ValueError):
    """An oracle-file write would leave the worktree (through a parent symlink)."""


class UnsafeOracleSource(UnsafeTreePath):
    """An oracle source file is a symlink (its target, possibly outside the tree, would
    be copied in). Candidate-independent: the oracle is invalid."""


def overwrite_oracle_files(wt: Path, gold_wt: Path, oracle_files: Iterable[str]) -> None:
    """Set each oracle file in ``wt`` to its content in ``gold_wt`` (delete if absent).

    Never follows a link: a symlinked source is refused (``UnsafeOracleSource``), and a
    destination link (which the candidate may have placed) is removed, not written through.
    """
    root_real = wt.resolve()
    src_root_real = gold_wt.resolve()
    for rel in oracle_files:
        src, dst = gold_wt / rel, wt / rel
        if src.is_symlink() or (
            os.path.lexists(src) and not _inside(src_root_real, src.parent.resolve())
        ):
            raise UnsafeOracleSource(f"oracle_source_symlink:{rel}")
        if not _inside(root_real, dst.parent.resolve()):
            raise UnsafeTreePath(f"oracle_path_escapes:{rel}")
        if dst.is_symlink():
            dst.unlink()  # never write through a link the candidate may have placed
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst, follow_symlinks=False)
        elif dst.exists():
            dst.unlink()


# ---------------------------------------------------------------- environments


@dataclass(frozen=True)
class TestEnv:
    key: str
    python: str
    recipe: str
    description: Mapping[str, str] = field(default_factory=dict)
    # Import roots appended after the scored tree, for an interpreter whose packages are not
    # in its own site-packages (e.g. a CI executor that supplies them via PYTHONPATH).
    extra_pythonpath: tuple[str, ...] = ()

    @property
    def cache_key(self) -> str:
        """Key for cached test results: env identity plus everything else that can change
        an outcome without changing ``key`` (interpreter, import roots, scorer version)."""
        return sha256_bytes(
            json.dumps(
                [
                    self.key,
                    self.python,
                    self.description.get("python", ""),
                    list(self.extra_pythonpath),
                    SCORER_VERSION,
                ],
                sort_keys=True,
            ).encode()
        )


class EnvProvider(Protocol):
    def get(self, repo: str, base_wt: Path) -> TestEnv: ...


def _workflow_learning_pin(base_wt: Path) -> str:
    wf = base_wt / ".github" / "workflows" / "tests.yml"
    if not wf.exists():
        return ""
    text = wf.read_text(errors="replace")
    m = re.search(r"repository:\s*James3014/nexus-learning\s*\n\s*ref:\s*([0-9a-f]{40})", text)
    return m.group(1) if m else ""


class UvEnvProvider:
    """Spec §8 env build. Envs are cached by key under ``envs_dir``."""

    PYTHON = "3.12"
    RUNTIME_PINS = (
        "pytest==9.0.2",
        "pytest-asyncio==1.3.0",
        "anyio==4.12.1",
        "pydantic==2.13.5",
        "PyYAML==6.0.3",
    )

    def __init__(self, envs_dir: Path, log: Callable[[str], None] = print):
        self.envs_dir = Path(envs_dir)
        self.log = log

    def _recipe(self, repo: str, base_wt: Path) -> tuple[str, dict[str, str]]:
        files = [
            "pyproject.toml",
            "uv.lock",
            "requirements/canonical-learning.txt",
            "requirements/canonical-runtime.txt",
        ]
        digests = {
            f: sha256_bytes((base_wt / f).read_bytes()) for f in files if (base_wt / f).exists()
        }
        if repo in IMPACT_GATE_REPOS:
            recipe = "uv-sync-all-extras+canonical"
        elif (base_wt / "uv.lock").exists():
            recipe = "uv-sync-all-groups"
        else:
            recipe = "uv-venv-runtime-pins"
            digests["learning_pin"] = _workflow_learning_pin(base_wt)
        return recipe, digests

    def _interpreter(self) -> dict[str, str]:
        """The uv-managed interpreter ``--python 3.12`` resolves to (path and version)."""
        try:
            path = subprocess.run(
                ["uv", "python", "find", self.PYTHON],
                capture_output=True,
                text=True,
                timeout=120,
            ).stdout.strip()
            version = (
                subprocess.run(
                    [path, "-c", "import sys;print(sys.version.split()[0])"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                ).stdout.strip()
                if path
                else ""
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise EnvBuildError(f"uv python find {self.PYTHON}: {exc}") from exc
        if not path or not version:
            raise EnvBuildError(f"uv python find {self.PYTHON}: no interpreter")
        return {"path": path, "version": version}

    def env_key(self, repo: str, base_wt: Path) -> tuple[str, str, dict[str, str], dict[str, str]]:
        """(key, recipe, input digests, interpreter). The key covers the repo, recipe,
        BASE lock inputs, the resolved interpreter path and version, the extra import roots
        (none for this provider) and the scorer version."""
        recipe, digests = self._recipe(repo, base_wt)
        interpreter = self._interpreter()
        key = sha256_bytes(
            json.dumps(
                [
                    repo,
                    recipe,
                    self.PYTHON,
                    digests,
                    interpreter,
                    [],  # extra_pythonpath: this provider supplies none
                    SCORER_VERSION,
                ],
                sort_keys=True,
            ).encode()
        )
        return key, recipe, digests, interpreter

    def get(self, repo: str, base_wt: Path) -> TestEnv:
        key, recipe, digests, interpreter = self.env_key(repo, base_wt)
        env_dir = self.envs_dir / key[:16]
        marker = env_dir / ".real_outcome_env.json"
        if marker.exists():
            desc = json.loads(marker.read_text())
            return TestEnv(key, str(env_dir / "bin" / "python"), recipe, desc)
        shutil.rmtree(env_dir, ignore_errors=True)
        env = {k: v for k, v in os.environ.items() if k not in {"VIRTUAL_ENV", "PYTHONPATH"}}
        env["UV_PROJECT_ENVIRONMENT"] = str(env_dir)

        def run(cmd: list[str]) -> None:
            self.log("env: " + " ".join(cmd[:6]))
            proc = subprocess.run(
                cmd, cwd=str(base_wt), env=env, capture_output=True, text=True, timeout=3600
            )
            if proc.returncode != 0:
                raise EnvBuildError(f"{' '.join(cmd[:4])}: {proc.stderr[-600:]}")

        py = str(env_dir / "bin" / "python")
        try:
            if recipe.startswith("uv-sync"):
                cmd = [
                    "uv",
                    "sync",
                    "--directory",
                    str(base_wt),
                    "--frozen",
                    "--all-groups",
                    "--no-install-project",
                    "--python",
                    self.PYTHON,
                ]
                if recipe == "uv-sync-all-extras+canonical":
                    cmd.append("--all-extras")
                run(cmd)
                for req in (
                    "requirements/canonical-learning.txt",
                    "requirements/canonical-runtime.txt",
                ):
                    if recipe.endswith("canonical") and (base_wt / req).exists():
                        run(["uv", "pip", "install", "--python", py, "-r", str(base_wt / req)])
            else:
                pin = digests.get("learning_pin", "")
                if not pin:
                    raise EnvBuildError("nexus-learning pin not found in tests.yml")
                run(["uv", "venv", "-q", "--python", self.PYTHON, str(env_dir)])
                run([
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    py,
                    *self.RUNTIME_PINS,
                    f"nexus-learning @ git+https://github.com/James3014/nexus-learning.git@{pin}",
                ])
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise EnvBuildError(str(exc)) from exc
        version = subprocess.run(
            [py, "-c", "import sys;print(sys.version.split()[0])"], capture_output=True, text=True
        ).stdout.strip()
        uv_version = subprocess.run(
            ["uv", "--version"], capture_output=True, text=True
        ).stdout.strip()
        desc = {
            "python": version,
            "python_path": interpreter["path"],
            "scorer_version": SCORER_VERSION,
            "uv": uv_version,
            "recipe": recipe,
            "inputs": json.dumps(digests, sort_keys=True),
        }
        marker.write_text(json.dumps(desc, sort_keys=True))
        return TestEnv(key, py, recipe, desc)


# ---------------------------------------------------------------------- pytest


@dataclass
class RunResult:
    outcomes: dict[str, str]
    exit_code: int
    timed_out: bool
    seconds: float = 0.0
    # Set when the run is failed for an operational reason (A6), e.g. the TMPDIR cap.
    diagnostic: str | None = None


def tree_bytes(root: Path) -> int:
    """Total size of the regular files under ``root``; symlinks are never followed."""
    total = 0
    if not root.is_dir() or root.is_symlink():
        return 0
    for dirpath, _dirs, files in os.walk(root, followlinks=False):
        for name in files:
            try:
                st = os.lstat(os.path.join(dirpath, name))
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode):
                total += st.st_size
    return total


def _is_junit_name(name: str) -> bool:
    return name.startswith("junit-") and name.endswith(".xml")


def clean_scratch_tmp(tmp: Path) -> None:
    """Empty ``tmp`` except the runner's own ``junit-*.xml`` files; never follows links."""
    if not tmp.is_dir() or tmp.is_symlink():
        return
    with os.scandir(tmp) as it:
        entries = list(it)
    for entry in entries:
        if _is_junit_name(entry.name) and entry.is_file(follow_symlinks=False):
            continue
        path = Path(entry.path)
        try:
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(path, ignore_errors=True)
                if path.exists():
                    _make_tree_writable(path)
                    shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink()
        except OSError:
            pass  # best effort: what is left is measured again after the next task


def _make_tree_writable(root: Path) -> None:
    """A test may leave read-only directories behind, which rmtree cannot empty."""
    os.chmod(root, 0o700)
    for dirpath, dirs, _files in os.walk(root, followlinks=False):
        for name in dirs:
            path = os.path.join(dirpath, name)
            if not os.path.islink(path):
                os.chmod(path, 0o700)


def parse_junit(path: Path) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    if not path.exists():
        return outcomes
    data = path.read_bytes()
    # The junit file is produced by candidate-controlled test code: refuse any
    # DTD/entity declaration (entity expansion), which is the only XML feature
    # that makes the stdlib parser unsafe here.
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        return outcomes
    try:
        root = ET.fromstring(data)  # nosec B314 - DTD/entities rejected above
    except ET.ParseError:
        return outcomes
    for case in root.iter("testcase"):
        classname = case.get("classname") or ""
        name = case.get("name") or ""
        node = f"{classname}::{name}" if classname else name
        tags = {child.tag for child in case}
        if tags & {"failure", "error"}:
            outcome = FAIL
        elif "skipped" in tags:
            outcome = SKIP
        else:
            outcome = PASS
        prev = outcomes.get(node)
        if prev == FAIL or outcome == FAIL:
            outcomes[node] = FAIL
        elif prev is None or prev == SKIP:
            outcomes[node] = outcome
    return outcomes


class PytestRunner:
    """Spec §8 test run.

    Results are cached by (env cache key, tree id, target, ignores, run index, role). The
    env cache key includes the scorer version, so a new scorer version never reuses an
    older version's results. ``role`` separates candidate-tree runs from GOLD runs: with
    candidate := GOLD the CAND+T tree id equals the GOLD tree id, and without the role
    self-check (a) would only replay GOLD's cached run instead of executing the tests.
    """

    def __init__(
        self,
        scratch: Path,
        timeout: int = PYTEST_TIMEOUT_SECONDS,
        log: Callable[[str], None] = print,
    ):
        self.scratch = Path(scratch)
        self.cache = self.scratch / "pytest-cache"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.log = log
        self.total_seconds = 0.0
        self.tmp = self.scratch / "tmp"

    def clean_tmp(self) -> int:
        """A6: empty ``scratch/tmp`` after a task. Returns its size in bytes before."""
        size = tree_bytes(self.tmp)
        clean_scratch_tmp(self.tmp)
        return size

    def _env(self, env: TestEnv, tree: Path) -> dict[str, str]:
        home = self.scratch / "home"
        tmp = self.scratch / "tmp"
        home.mkdir(parents=True, exist_ok=True)
        tmp.mkdir(parents=True, exist_ok=True)
        pythonpath = [str(tree)]
        if (tree / "src").is_dir():
            pythonpath.append(str(tree / "src"))
        pythonpath.extend(env.extra_pythonpath)
        return {
            "PATH": f"{Path(env.python).parent}:/usr/bin:/bin",
            "HOME": str(home),
            "TMPDIR": str(tmp),
            "PYTHONPATH": os.pathsep.join(pythonpath),
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": "en_US.UTF-8",
            "TZ": "UTC",
        }

    def run(
        self,
        env: TestEnv,
        tree: Path,
        tree_id: str,
        target: str,
        ignores: Sequence[str],
        run_idx: int,
        role: str = "",
    ) -> RunResult:
        ignores = sorted(set(ignores))
        key = sha256_bytes(
            json.dumps([env.cache_key, tree_id, target, ignores, run_idx, role]).encode()
        )
        cached = self.cache / f"{key}.json"
        if cached.exists():
            data = json.loads(cached.read_text())
            return RunResult(
                data["outcomes"],
                data["exit_code"],
                data["timed_out"],
                0.0,
                data.get("diagnostic"),
            )
        junit = self.scratch / "tmp" / f"junit-{key}.xml"
        junit.parent.mkdir(parents=True, exist_ok=True)
        junit.unlink(missing_ok=True)
        cmd = [
            env.python,
            "-m",
            "pytest",
            target,
            "-q",
            "-p",
            "no:cacheprovider",
            f"--junitxml={junit}",
            *[f"--ignore={p}" for p in ignores],
        ]
        tmp_before = tree_bytes(self.tmp)
        start = time.monotonic()
        timed_out = False
        diagnostic = None
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(tree),
                env=self._env(env, tree),
                capture_output=True,
                timeout=self.timeout,
            )
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out, exit_code = True, -1
        seconds = time.monotonic() - start
        self.total_seconds += seconds
        # A6: what this run left in TMPDIR (its own junit report excluded).
        junit_bytes = junit.stat().st_size if junit.is_file() and not junit.is_symlink() else 0
        left = tree_bytes(self.tmp) - tmp_before - junit_bytes
        if left > SCRATCH_TMP_CAP_BYTES:
            # Same path as a crashed run: no outcomes, so expected nodes count as fail.
            diagnostic, exit_code = SCRATCH_TMP_CAP_EXCEEDED, SCRATCH_TMP_CAP_EXIT_CODE
            outcomes: dict[str, str] = {}
        else:
            outcomes = {} if timed_out else parse_junit(junit)
        junit.unlink(missing_ok=True)
        if diagnostic:
            clean_scratch_tmp(self.tmp)
        self.log(
            f"  pytest {target} run={run_idx}{' role=' + role if role else ''} exit={exit_code}"
            f"{' TIMEOUT' if timed_out else ''}{' ' + diagnostic if diagnostic else ''}"
            f" nodes={len(outcomes)} {seconds:.0f}s"
        )
        record: dict[str, Any] = {
            "outcomes": outcomes,
            "exit_code": exit_code,
            "timed_out": timed_out,
        }
        if diagnostic:
            record["diagnostic"] = diagnostic
        cached.write_text(json.dumps(record, sort_keys=True))
        return RunResult(outcomes, exit_code, timed_out, seconds, diagnostic)


def _merge(results: Iterable[RunResult]) -> dict[str, str]:
    """Merge per-invocation outcomes: fail dominates pass, pass dominates skip."""
    rank = {SKIP: 0, PASS: 1, FAIL: 2}
    merged: dict[str, str] = {}
    for res in results:
        for node, outcome in res.outcomes.items():
            if node not in merged or rank[outcome] > rank[merged[node]]:
                merged[node] = outcome
    return merged


def _get(outcomes: Mapping[str, str], node: str) -> str:
    return outcomes.get(node, FAIL)


# ------------------------------------------------------------------- impact plan

_TRUSTED_PLAN_CODE = r"""
import dataclasses, importlib.util, json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location(
    "trusted_pr_impact_gate", root / "scripts" / "ops" / "pr_impact_gate.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
plan = mod.build_impact_plan(json.loads(sys.stdin.read()), root=root)
print(json.dumps(dataclasses.asdict(plan), sort_keys=True))
"""


def trusted_impact_plan(
    env: TestEnv, base_wt: Path, changed: Sequence[str], scratch: Path
) -> dict[str, Any] | None:
    """Spec §6.3 P2P(b): trusted BASE copy of the impact gate selects targets."""
    if not (base_wt / "scripts" / "ops" / "pr_impact_gate.py").exists():
        return None
    home = scratch / "home"
    home.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [env.python, "-c", _TRUSTED_PLAN_CODE, str(base_wt)],
        cwd=str(base_wt),
        input=json.dumps(sorted(changed)),
        capture_output=True,
        text=True,
        env={
            "PATH": f"{Path(env.python).parent}:/usr/bin:/bin",
            "HOME": str(home),
            "PYTHONPATH": os.pathsep.join([str(base_wt), *env.extra_pythonpath]),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        timeout=600,
    )
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


# ----------------------------------------------------------------------- scoring


_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


@dataclass
class ScoreContext:
    work: Path
    env_provider: EnvProvider
    runner: PytestRunner
    repo_sources: Mapping[str, Sequence[str]]
    spec_sha256: str
    # Required (no default): a v2 receipt must never carry an empty spec hash.
    spec_v2_sha256: str
    leakage_flags: Mapping[str, str] = field(default_factory=dict)
    log: Callable[[str], None] = print
    keep_trees: bool = False

    def __post_init__(self) -> None:
        for name in ("spec_sha256", "spec_v2_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or not _SHA256_HEX.fullmatch(value):
                raise ValueError(f"{name} must be 64 lowercase hex characters")


def _capped(inputs: TaskInputs) -> bool:
    if inputs.wall_time_seconds is None or inputs.cap_seconds is None:
        return False
    return inputs.wall_time_seconds >= inputs.cap_seconds - 60


def _base_receipt(inputs: TaskInputs, ctx: ScoreContext) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "scorer_version": SCORER_VERSION,
        "spec_sha256": ctx.spec_sha256,
        "spec_version": SPEC_V1,
        "task_key": inputs.task_key,
        "repo": f"{inputs.owner}/{inputs.repo}",
        "issue": inputs.issue,
        "route": inputs.route,
        "base_sha": inputs.base_sha,
        "candidate_digest": inputs.candidate.digest,
        "candidate_empty": inputs.candidate.empty,
        "candidate_override": inputs.candidate.override,
        "candidate_raw_status": inputs.so.get("status"),
        "failure_kind": inputs.so.get("failure_kind"),
        "scope_valid": inputs.so.get("scope_valid"),
        "capped": _capped(inputs),
        "leakage_flags": sorted([ctx.leakage_flags[inputs.task_key]])
        if inputs.task_key in ctx.leakage_flags
        else [],
        "label": None,
        "sub_reason": None,
        "shadow_label": None,
    }


def _repo_kind(repo: str) -> str:
    return "impact_gate" if repo in IMPACT_GATE_REPOS else "full_suite"


@dataclass
class Oracle:
    files: list[str]
    modules: list[str]
    f2p: list[str]
    p2p_a: list[str]
    flaky: list[str]
    base_outcomes: list[dict[str, str]]
    gold_outcomes: list[dict[str, str]]


CAND_ROLE = "CAND+T"


def _run_modules(
    ctx: ScoreContext,
    env: TestEnv,
    tree: Path,
    tree_id: str,
    modules: Sequence[str],
    run_idx: int,
    role: str = "",
) -> list[RunResult]:
    return [ctx.runner.run(env, tree, tree_id, m, (), run_idx, role) for m in modules]


def score_task(
    task_dir: Path, ctx: ScoreContext, candidate_override: str | None = None
) -> dict[str, Any]:
    """Score one task. Returns {"receipt", "timing"}. Raises SealRefused."""
    t0 = time.monotonic()
    inputs = load_sealed_task(task_dir)  # §4 step 1
    if candidate_override == "empty":
        inputs.candidate = Candidate(b"", [], override="empty")
    receipt = _base_receipt(inputs, ctx)
    timing: dict[str, Any] = {"task_key": inputs.task_key}
    gt = load_ground_truth(inputs)  # §4 step 2
    if gt is None:
        receipt["label"] = PENDING_GROUND_TRUTH
        return _finish(receipt, timing, t0, ctx)
    if gt.get("terminal_state") != "CLOSED_WITH_MERGED_PR":
        receipt["label"] = NOT_SCORABLE_NO_MERGED_PR
        receipt["terminal_state"] = gt.get("terminal_state")
        return _finish(receipt, timing, t0, ctx)
    prs = sorted(
        gt.get("details", {}).get("merged_prs") or [],
        key=lambda p: (str(p.get("merged_at", "")), int(p.get("number", 0))),
    )
    receipt["merged_prs"] = [
        {"number": p["number"], "merge_commit_sha": p["merge_commit_sha"]} for p in prs
    ]
    if not prs:
        receipt["label"] = NOT_SCORABLE_NO_MERGED_PR
        return _finish(receipt, timing, t0, ctx)

    repo = GitRepo(ctx.work / "repos" / inputs.repo, ctx.repo_sources.get(inputs.repo, ()))
    for sha in [inputs.base_sha, *[p["merge_commit_sha"] for p in prs]]:
        if not repo.ensure_commit(sha):
            receipt["label"] = NOT_SCORABLE_ORACLE_INVALID
            receipt["sub_reason"] = "GOLD_PORT_FAILED"
            receipt["detail"] = f"commit_missing:{sha}"
            return _finish(receipt, timing, t0, ctx)
    oracle_files: set[str] = set()
    for p in prs:
        for path in repo.changed_paths(f"{p['merge_commit_sha']}^1", p["merge_commit_sha"]):
            if is_oracle_test_file(path):
                oracle_files.add(path)
    receipt["oracle_test_files"] = sorted(oracle_files)
    if not oracle_files:
        receipt["label"] = NOT_SCORABLE_NO_ORACLE
        return _finish(receipt, timing, t0, ctx)

    trees_dir = ctx.work / "trees" / inputs.task_key
    wts: dict[str, Path] = {}
    try:
        wts["base"] = repo.worktree(trees_dir / "base", inputs.base_sha)
        base_tree = repo.tree_id(wts["base"])
        # GOLD (§5)
        wts["gold"] = repo.worktree(trees_dir / "gold", inputs.base_sha)
        port = port_gold(repo, wts["gold"], prs)
        receipt.update(port.receipt_fields())
        if port.method != GOLD_PORT_3WAY:
            # Spec v2 (A5): reported apart from the pre-registered v1 results.
            receipt["spec_version"] = SPEC_V2
            receipt["spec_sha256"] = ctx.spec_v2_sha256
        if not port.ok:
            receipt["label"] = NOT_SCORABLE_ORACLE_INVALID
            receipt["sub_reason"] = "GOLD_PORT_FAILED"
            receipt["detail"] = f"pr:{port.failed_pr}"
            return _finish(receipt, timing, t0, ctx)
        # v2: a merge-taken test file that is not a test module (conftest.py, __init__.py,
        # test data, helpers), whether or not it exists at BASE, could change how BASE
        # tests in other files behave (a new conftest.py can stop them being collected),
        # and those tests are not re-run at their BASE state (P2P(d) covers modules
        # only): refuse.
        support = sorted(f for f in set(port.test_files_from_merge) if not is_oracle_module_name(f))
        if support:
            receipt["label"] = NOT_SCORABLE_ORACLE_INVALID
            receipt["sub_reason"] = "GOLD_PORT_FAILED"
            receipt["detail"] = "merge_taken_test_support_file:" + ",".join(support)[:300]
            return _finish(receipt, timing, t0, ctx)
        gold_tree = repo.tree_id(wts["gold"])
        if port.dropped_from:
            # Amendment A5 detector tree: GOLD with each dropped doc/data file set to its
            # merge-commit content. Never scored; used only to prove the drop changes no
            # oracle outcome and to keep `gold_also_fails` from excusing a P2P failure
            # that the dropped file explains.
            wts["goldref"] = repo.worktree(trees_dir / "goldref", inputs.base_sha)
            _restore_tree(repo, wts["goldref"], gold_tree)
            try:
                for path, merge_sha in sorted(port.dropped_from.items()):
                    _set_path_from(repo, wts["goldref"], merge_sha, path)
            except (UnsafeTreePath, RuntimeError, OSError) as exc:
                receipt["label"] = NOT_SCORABLE_ORACLE_INVALID
                receipt["sub_reason"] = "GOLD_PORT_FAILED"
                receipt["detail"] = str(exc)
                return _finish(receipt, timing, t0, ctx)
        files = sorted(oracle_files)
        modules = [f for f in files if is_oracle_module_name(f) and (wts["gold"] / f).exists()]
        wts["baset"] = repo.worktree(trees_dir / "baset", inputs.base_sha)
        try:
            overwrite_oracle_files(wts["baset"], wts["gold"], files)
        except UnsafeTreePath as exc:
            receipt["label"] = NOT_SCORABLE_ORACLE_INVALID
            receipt["sub_reason"] = "ORACLE_FILE_UNSAFE"
            receipt["detail"] = str(exc)
            return _finish(receipt, timing, t0, ctx)
        baset_tree = repo.tree_id(wts["baset"])
        receipt["trees"] = {"BASE": base_tree, "GOLD": gold_tree, "BASE+T": baset_tree}
        receipt["oracle_modules"] = modules

        try:
            env = ctx.env_provider.get(inputs.repo, wts["base"])
        except EnvBuildError as exc:
            receipt["label"] = NOT_SCORABLE_ORACLE_INVALID
            receipt["sub_reason"] = "ENV_FAILED"
            timing["env_error"] = str(exc)[-800:]
            return _finish(receipt, timing, t0, ctx)
        receipt["env_key"] = env.key
        timing["env"] = dict(env.description)

        if candidate_override and candidate_override.startswith("gold"):
            diff = repo.git("diff", "--binary", "--no-renames", base_tree, gold_tree).stdout
            inputs.candidate = Candidate(diff, [], override="gold")
            inputs.so = {**inputs.so, "status": "VALID", "scope_valid": True}
        elif candidate_override and candidate_override.startswith("broken"):
            inputs.candidate = _broken_candidate(
                repo, wts["base"], base_tree, gold_tree, candidate_override
            )
            inputs.so = {**inputs.so, "status": "VALID", "scope_valid": True}
        if candidate_override:
            receipt["candidate_override"] = inputs.candidate.override
            receipt["candidate_digest"] = inputs.candidate.digest
            receipt["candidate_empty"] = inputs.candidate.empty

        # Oracle (§6.2): candidate-independent.
        tq = time.monotonic()
        base_runs, gold_runs = [], []
        gold_by_module: dict[str, list[dict[str, str]]] = {m: [] for m in modules}
        for i in range(ORACLE_RUNS):
            gr = _run_modules(ctx, env, wts["gold"], gold_tree, modules, i)
            for m, res in zip(modules, gr):
                gold_by_module[m].append(res.outcomes)
            if any(r.timed_out or r.exit_code not in (0, 1) for r in gr):
                receipt["label"] = NOT_SCORABLE_ORACLE_INVALID
                receipt["sub_reason"] = "GOLD_COLLECTION_FAILED"
                receipt["detail"] = ",".join(
                    f"{m}:{r.exit_code}" + (f":{r.diagnostic}" if r.diagnostic else "")
                    for m, r in zip(modules, gr)
                    if r.timed_out or r.exit_code not in (0, 1)
                )
                return _finish(receipt, timing, t0, ctx)
            gold_runs.append(_merge(gr))
            base_runs.append(_merge(_run_modules(ctx, env, wts["baset"], baset_tree, modules, i)))
        nodes = sorted(set().union(*gold_runs, *base_runs))
        flaky = sorted(
            n
            for n in nodes
            if len({_get(r, n) for r in gold_runs}) > 1 or len({_get(r, n) for r in base_runs}) > 1
        )
        stable = [n for n in nodes if n not in set(flaky)]
        f2p = [
            n
            for n in stable
            if all(_get(r, n) == PASS for r in gold_runs)
            and all(_get(r, n) == FAIL for r in base_runs)
        ]
        p2p_a = [n for n in stable if all(_get(r, n) == PASS for r in gold_runs + base_runs)]
        timing["oracle_seconds"] = round(time.monotonic() - tq, 1)
        receipt.update({
            "f2p": f2p,
            "p2p_a": p2p_a,
            "f2p_total": len(f2p),
            "oracle_flaky": flaky,
            "outcome_digests": {
                "GOLD": [_digest_outcomes(r) for r in gold_runs],
                "BASE+T": [_digest_outcomes(r) for r in base_runs],
            },
        })
        if port.method != GOLD_PORT_3WAY:
            # Diagnostic only (v2): nodes of merge-taken test modules that fail on every
            # GOLD oracle run (typically tests that need another main commit's code).
            receipt["gold_port_merge_test_nodes_failing_on_gold"] = sum(
                1
                for m in sorted(set(port.test_files_from_merge) & set(modules))
                for n in set().union(*gold_by_module[m])
                if all(_get(r, n) == FAIL for r in gold_by_module[m])
            )
        if "goldref" in wts:
            goldref_tree = repo.tree_id(wts["goldref"])
            receipt["trees"]["GOLD_REF"] = goldref_tree
            ref_results = _run_modules(ctx, env, wts["goldref"], goldref_tree, modules, 0)
            if any(r.timed_out or r.exit_code not in (0, 1) for r in ref_results):
                # The detector itself failed: fail closed.
                receipt["label"] = NOT_SCORABLE_ORACLE_INVALID
                receipt["sub_reason"] = GOLD_REF_RUN_FAILED
                receipt["detail"] = "oracle"
                receipt["flaky_dropped"] = len(flaky)
                return _finish(receipt, timing, t0, ctx)
            ref = _merge(ref_results)
            # A5: every stable oracle node must have the same outcome with and without the
            # dropped files; otherwise the drop could hide an F2P node -> GOLD_PORT_FAILED.
            # Presence counts too: a node collected on only one of the two trees is a
            # mismatch even when "absent" and "fail" would compare equal.
            gold0 = gold_runs[0]
            mismatch = sorted(
                n
                for n in set(ref) | set(gold0)
                if n not in set(flaky) and ref.get(n) != gold0.get(n)
            )
            if mismatch:
                receipt["label"] = NOT_SCORABLE_ORACLE_INVALID
                receipt["sub_reason"] = "GOLD_PORT_FAILED"
                receipt["detail"] = "dropped_paths_change_oracle_outcome"
                receipt["gold_ref_mismatch"] = mismatch
                receipt["flaky_dropped"] = len(flaky)
                return _finish(receipt, timing, t0, ctx)
        if not f2p:
            receipt["label"] = NOT_SCORABLE_ORACLE_INVALID
            receipt["sub_reason"] = "EMPTY_F2P"
            receipt["flaky_dropped"] = len(flaky)
            return _finish(receipt, timing, t0, ctx)

        # Candidate labels (§7 rows 5-6).
        cand = inputs.candidate
        if cand.empty:
            receipt["label"] = NO_CANDIDATE
            receipt["flaky_dropped"] = len(flaky)
            return _finish(receipt, timing, t0, ctx)
        not_runnable = None
        if inputs.so.get("scope_valid") is False:
            not_runnable = "SCOPE_INVALID"
        elif inputs.so.get("status") == "TIMEOUT":
            not_runnable = "SEALED_WHILE_PROVIDER_RUNNING"
        wts["candt"] = repo.worktree(trees_dir / "candt", inputs.base_sha)
        err = apply_candidate(repo, wts["candt"], cand)
        if err:
            receipt["label"] = NOT_RUNNABLE
            receipt["sub_reason"] = not_runnable or "APPLY_FAILED"
            receipt["detail"] = err
            receipt["flaky_dropped"] = len(flaky)
            return _finish(receipt, timing, t0, ctx)
        untracked_paths = [u["path"] for u in cand.untracked]
        cand_tree = repo.tree_id(wts["candt"], untracked_paths)
        try:
            overwrite_oracle_files(wts["candt"], wts["gold"], files)
        except UnsafeTreePath as exc:
            receipt["label"] = NOT_RUNNABLE
            receipt["sub_reason"] = not_runnable or "APPLY_FAILED"
            receipt["detail"] = str(exc)
            receipt["flaky_dropped"] = len(flaky)
            return _finish(receipt, timing, t0, ctx)
        candt_tree = repo.tree_id(wts["candt"], untracked_paths)
        receipt["trees"].update({"CAND": cand_tree, "CAND+T": candt_tree})
        # v2 P2P(d): BASE tests in a merge-taken test file are gone from every scored
        # tree (main deleted or rewrote them), and P2P(b/c) ignores oracle files. So the
        # BASE version of each such module is also run, on trees that all carry the BASE
        # bytes of every oracle file: BASE, CAND@BASE_TESTS, GOLD@BASE_TESTS and (with
        # dropped files) GOLD_REF@BASE_TESTS.
        d_targets = sorted(
            f
            for f in set(port.test_files_from_merge)
            if is_oracle_module_name(f) and repo.path_in(inputs.base_sha, f)
        )
        d_trees: dict[str, str] = {}
        if d_targets:
            sources = {"cand0": cand_tree, "gold0": gold_tree}
            if "goldref" in wts:
                sources["goldref0"] = repo.tree_id(wts["goldref"])
            key = ""
            try:
                for key, tree in sources.items():
                    wts[key] = repo.worktree(trees_dir / key, inputs.base_sha)
                    _restore_tree(repo, wts[key], tree)
                    overwrite_oracle_files(wts[key], wts["base"], files)
                    d_trees[key] = repo.tree_id(wts[key])
            except UnsafeTreePath as exc:
                if isinstance(exc, UnsafeOracleSource) or key != "cand0":
                    # A BASE oracle file is a link, or a GOLD/GOLD_REF tree cannot be
                    # built: candidate-independent, the oracle is invalid.
                    receipt["label"] = NOT_SCORABLE_ORACLE_INVALID
                    receipt["sub_reason"] = "ORACLE_FILE_UNSAFE"
                    receipt["detail"] = str(exc)
                    receipt["flaky_dropped"] = len(flaky)
                    return _finish(receipt, timing, t0, ctx)
                receipt["label"] = NOT_RUNNABLE
                receipt["sub_reason"] = not_runnable or "APPLY_FAILED"
                receipt["detail"] = str(exc)
                receipt["flaky_dropped"] = len(flaky)
                return _finish(receipt, timing, t0, ctx)
            receipt["trees"].update({
                {"cand0": "CAND@BASE_TESTS", "gold0": "GOLD@BASE_TESTS"}.get(
                    k, "GOLD_REF@BASE_TESTS"
                ): v
                for k, v in d_trees.items()
            })
        if not_runnable == "SCOPE_INVALID":
            receipt["label"] = NOT_RUNNABLE
            receipt["sub_reason"] = not_runnable
            receipt["flaky_dropped"] = len(flaky)
            return _finish(receipt, timing, t0, ctx)

        tc = time.monotonic()
        evaluation = _evaluate_candidate(
            ctx,
            env,
            repo,
            inputs,
            wts,
            files,
            modules,
            base_tree,
            cand_tree,
            gold_tree,
            baset_tree,
            candt_tree,
            f2p,
            p2p_a,
            flaky,
            d_targets if port.method != GOLD_PORT_3WAY else None,
            d_trees,
        )
        timing["candidate_seconds"] = round(time.monotonic() - tc, 1)
        receipt.update(evaluation)
        evaluated = evaluation["evaluated_label"]
        if evaluated == NOT_SCORABLE_ORACLE_INVALID:
            # A candidate-independent detector run failed (v2): oracle-invalid comes
            # before NOT_RUNNABLE in §7 order, and no candidate label is given.
            receipt["label"] = evaluated
            receipt["sub_reason"] = evaluation["evaluated_sub_reason"]
        elif not_runnable:
            receipt["label"] = NOT_RUNNABLE
            receipt["sub_reason"] = not_runnable
            receipt["shadow_label"] = evaluated
        else:
            receipt["label"] = evaluated
        return _finish(receipt, timing, t0, ctx)
    finally:
        if not ctx.keep_trees:
            for wt in wts.values():
                repo.remove_worktree(wt)
            shutil.rmtree(trees_dir, ignore_errors=True)
        # A6: TMPDIR is emptied after every task (also with keep_trees), so a leaky test
        # cannot fill the disk across tasks. Its size before cleaning is recorded.
        timing["scratch_tmp_bytes"] = ctx.runner.clean_tmp()


def _broken_candidate(
    repo: GitRepo, base_wt: Path, base_tree: str, gold_tree: str, override: str
) -> Candidate:
    """Self-check (c): syntax error injected into a non-test module."""
    if ":" in override:
        module = override.split(":", 1)[1]
    else:
        candidates = [
            p
            for p in repo.changed_paths(base_tree, gold_tree)
            if p.endswith(".py") and not is_oracle_test_file(p) and (base_wt / p).exists()
        ]
        if not candidates:
            raise ValueError("no non-test python module changed by GOLD")
        module = candidates[0]
    original = (base_wt / module).read_bytes()
    (base_wt / module).write_bytes(original + b"\ndef __real_outcome_broken(:\n")
    diff = repo.git("diff", "--binary", "--", module, cwd=base_wt).stdout
    (base_wt / module).write_bytes(original)
    return Candidate(diff, [], override=f"broken:{module}")


def _evaluate_candidate(
    ctx: ScoreContext,
    env: TestEnv,
    repo: GitRepo,
    inputs: TaskInputs,
    wts: Mapping[str, Path],
    files: Sequence[str],
    modules: Sequence[str],
    base_tree: str,
    cand_tree: str,
    gold_tree: str,
    baset_tree: str,
    candt_tree: str,
    f2p: Sequence[str],
    p2p_a: Sequence[str],
    flaky: Sequence[str],
    d_targets: Sequence[str] | None = None,
    d_trees: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Spec §6.3-§6.4, plus v2 P2P(d) when ``d_targets`` is not None."""
    out: dict[str, Any] = {}
    flaky_dropped = set(flaky)
    goldref_tree = repo.tree_id(wts["goldref"]) if "goldref" in wts else None
    # 1. oracle modules on CAND+T with majority rerun.
    runs = [_merge(_run_modules(ctx, env, wts["candt"], candt_tree, modules, 0, CAND_ROLE))]
    watched = list(f2p) + list(p2p_a)
    if any(_get(runs[0], n) != PASS for n in watched):
        for i in (1, 2):
            runs.append(
                _merge(_run_modules(ctx, env, wts["candt"], candt_tree, modules, i, CAND_ROLE))
            )

    def majority_pass(node: str) -> bool:
        if len(runs) == 1:
            return _get(runs[0], node) == PASS
        return sum(_get(r, node) == PASS for r in runs) >= 2

    f2p_pass = sorted(n for n in f2p if majority_pass(n))
    p2p_a_fail = sorted(n for n in p2p_a if not majority_pass(n))

    # 2. P2P(b/c).
    changed = sorted(
        set(repo.changed_paths(base_tree, cand_tree))
        | set(repo.changed_paths(base_tree, gold_tree))
    )
    plan_sha = None
    selector_failed = False
    if _repo_kind(inputs.repo) == "impact_gate":
        plan = trusted_impact_plan(env, wts["base"], changed, ctx.runner.scratch)
        if plan is None:
            targets, selector_failed = [], True
        else:
            plan_sha = sha256_bytes(json.dumps(plan, sort_keys=True).encode())
            targets = [t for t in plan.get("pytest_targets", []) if t not in set(files)]
    else:
        targets = ["tests"] if (wts["base"] / "tests").is_dir() else []
    targets = sorted(dict.fromkeys(targets))
    ignores = list(files)
    base_p2p: dict[str, dict[str, str]] = {}
    cand_p2p: dict[str, dict[str, str]] = {}
    # Diagnostic only (amendment A2): candidate-independent P2P runs (BASE+T, GOLD) that
    # timed out or exited outside {0, 1, 5}. Scoring follows v1 unchanged: such a run's
    # expected nodes count as fail (§6.2, §8), so a BASE+T failure leaves no base-pass
    # nodes and a GOLD failure makes suspects `gold_also_fails`. The label is unaffected.
    baseline_failures: list[dict[str, Any]] = []

    tree_names = {
        "baset": "BASE+T",
        "gold": "GOLD",
        "goldref": "GOLD_REF",
        "base": "BASE",
        "gold0": "GOLD@BASE_TESTS",
        "goldref0": "GOLD_REF@BASE_TESTS",
    }
    goldref_failures: list[dict[str, Any]] = []

    def baseline_run(
        tree_key: str, tree_id: str, t: str, i: int, ign: Sequence[str]
    ) -> dict[str, str]:
        res = ctx.runner.run(env, wts[tree_key], tree_id, t, ign, i)
        if res.timed_out or res.exit_code not in CLEAN_P2P_EXIT_CODES:
            failure = {
                "tree": tree_names[tree_key],
                "target": t,
                "run": i,
                "exit_code": res.exit_code,
                "timed_out": res.timed_out,
            }
            if res.diagnostic:
                failure["diagnostic"] = res.diagnostic
            baseline_failures.append(failure)
            if tree_key.startswith("goldref"):
                goldref_failures.append(failure)
        return res.outcomes

    new_failures: set[str] = set(p2p_a_fail)
    gold_also_fails: set[str] = set()

    def judge(
        t: str,
        ign: Sequence[str],
        trees: Mapping[str, tuple[str, str]],
        b0: Mapping[str, str],
        c0: Mapping[str, str],
        exclude: set[str],
    ) -> int:
        """§6.4 for one target. ``trees``: role -> (worktree key, tree id) for base,
        cand, gold and optionally goldref. Returns the number of base-pass nodes."""
        base_pass = [n for n, o in b0.items() if o == PASS and n not in exclude]
        suspects = [n for n in base_pass if _get(c0, n) != PASS]
        if not suspects:
            return len(base_pass)
        ck, ct = trees["cand"]
        c_runs = [c0] + [
            ctx.runner.run(env, wts[ck], ct, t, ign, i, CAND_ROLE).outcomes for i in (1, 2)
        ]
        b_runs = [b0] + [baseline_run(*trees["base"], t, i, ign) for i in (1, 2)]
        g_run = baseline_run(*trees["gold"], t, 0, ign)
        stable = []
        for n in suspects:
            if not all(_get(r, n) != PASS for r in c_runs) or not all(
                _get(r, n) == PASS for r in b_runs
            ):
                flaky_dropped.add(n)
            elif _get(g_run, n) == PASS:
                new_failures.add(n)  # GOLD passes it: a new failure whatever GOLD_REF says
            else:
                stable.append(n)
        # A5: with dropped doc/data files, a suspect that GOLD fails is excused only if it
        # also fails on GOLD_REF, so a failure explained by a dropped file stays a P2P new
        # failure. GOLD_REF runs only when such a suspect exists; a GOLD_REF run that is
        # not clean then leaves these suspects without a verdict and the task NOT_SCORABLE
        # (below).
        r_run = None
        if stable and "goldref" in trees:
            n_ref_failures = len(goldref_failures)
            r_run = baseline_run(*trees["goldref"], t, 0, ign)
            if len(goldref_failures) != n_ref_failures:
                return len(base_pass)
        for n in stable:
            if r_run is None or _get(r_run, n) != PASS:
                gold_also_fails.add(n)
            else:
                new_failures.add(n)
        return len(base_pass)

    bc_trees = {
        "base": ("baset", baset_tree),
        "cand": ("candt", candt_tree),
        "gold": ("gold", gold_tree),
    }
    if goldref_tree is not None:
        bc_trees["goldref"] = ("goldref", goldref_tree)
    for t in targets:
        base_p2p[t] = baseline_run("baset", baset_tree, t, 0, ignores)
        cand_p2p[t] = ctx.runner.run(
            env, wts["candt"], candt_tree, t, ignores, 0, CAND_ROLE
        ).outcomes
    oracle_nodes = set(f2p) | set(p2p_a) | set(flaky)
    p2p_bc_total = 0
    for t in targets:
        p2p_bc_total += judge(t, ignores, bc_trees, base_p2p[t], cand_p2p[t], oracle_nodes)

    # v2 P2P(d): the BASE version of each merge-taken test module, with identical BASE
    # bytes for every oracle file on every tree. Not excluded: oracle node ids, since the
    # BASE test body may differ from the merge-tree one (stricter, never looser).
    p2p_d_total = 0
    if d_targets:
        d_map = {
            "base": ("base", base_tree),
            "cand": ("cand0", (d_trees or {})["cand0"]),
            "gold": ("gold0", (d_trees or {})["gold0"]),
        }
        if "goldref0" in (d_trees or {}):
            d_map["goldref"] = ("goldref0", (d_trees or {})["goldref0"])
        for t in d_targets:
            b0 = baseline_run("base", base_tree, t, 0, ())
            c0 = ctx.runner.run(env, wts["cand0"], d_map["cand"][1], t, (), 0, CAND_ROLE).outcomes
            p2p_d_total += judge(t, (), d_map, b0, c0, set())

    if goldref_failures:
        label = NOT_SCORABLE_ORACLE_INVALID
        out["evaluated_sub_reason"] = GOLD_REF_RUN_FAILED
    elif new_failures:
        label = BROKE_EXISTING
    elif len(f2p_pass) == len(f2p):
        label = RESOLVED
    elif f2p_pass:
        label = PARTIAL
    else:
        label = UNRESOLVED
    out.update({
        "evaluated_label": label,
        "f2p_pass": len(f2p_pass),
        "f2p_passed_nodes": f2p_pass,
        "p2p_total": len(p2p_a) + p2p_bc_total,
        "p2p_a_total": len(p2p_a),
        "p2p_bc_total": p2p_bc_total,
        "p2p_new_failures": sorted(new_failures),
        "flaky_dropped": len(flaky_dropped),
        "gold_also_fails": sorted(gold_also_fails),
        "p2p_targets": targets,
        "p2p_selector_failed": selector_failed,
        "p2p_baseline_failures": sorted(
            baseline_failures, key=lambda d: (d["tree"], d["target"], d["run"])
        ),
        "impact_plan_sha256": plan_sha,
        "candidate_changed_paths_digest": sha256_bytes("\n".join(changed).encode()),
    })
    if d_targets is not None:
        out.update({"p2p_d_targets": list(d_targets), "p2p_d_total": p2p_d_total})
    out.setdefault("outcome_digests_cand", [_digest_outcomes(r) for r in runs])
    return out


def _finish(
    receipt: dict[str, Any], timing: dict[str, Any], t0: float, ctx: ScoreContext
) -> dict[str, Any]:
    receipt.setdefault("flaky_dropped", 0)
    timing["wall_seconds"] = round(time.monotonic() - t0, 1)
    ctx.log(
        f"{receipt['task_key']}: {receipt['label']}"
        f"{'/' + receipt['sub_reason'] if receipt.get('sub_reason') else ''}"
        f" ({timing['wall_seconds']}s)"
    )
    return {"receipt": receipt, "timing": timing}


# ---------------------------------------------------------------------- receipts


def write_receipt(out_store: Path, result: Mapping[str, Any]) -> Path:
    receipt = result["receipt"]
    task_dir = Path(out_store) / "tasks" / receipt["task_key"]
    task_dir.mkdir(parents=True, exist_ok=True)
    body = canonical_bytes(receipt)
    path = task_dir / "real_outcome.json"
    try:
        with open(path, "xb") as fh:
            fh.write(body)
    except FileExistsError as exc:
        raise ReceiptExists(str(path)) from exc
    seal = {
        "schema": RECEIPT_SEAL_SCHEMA,
        "path": "real_outcome.json",
        "sha256": sha256_bytes(body),
    }
    with open(task_dir / "real_outcome_seal.json", "xb") as fh:
        fh.write(canonical_bytes(seal))
    with open(task_dir / "real_outcome_timing.json", "xb") as fh:
        fh.write(canonical_bytes(result["timing"]))
    return path


# ---------------------------------------------------------------------- summary


def _binom_cdf(k: int, n: int, p: float) -> float:
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact two-sided binomial CI."""
    if n == 0:
        return (0.0, 1.0)

    def solve(f: Callable[[float], float]) -> float:
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if f(mid) > 0:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    lower = 0.0 if k == 0 else solve(lambda p: alpha / 2 - (1 - _binom_cdf(k - 1, n, p)))
    upper = 1.0 if k == n else solve(lambda p: _binom_cdf(k, n, p) - alpha / 2)
    return (lower, upper)


def spec_version_of(receipt: Mapping[str, Any]) -> str:
    """Receipts written before spec v2 existed carry no ``spec_version`` key: they are v1.
    Any value that is present is taken as written (an empty or null one is not v1)."""
    if "spec_version" not in receipt:
        return SPEC_V1
    return str(receipt["spec_version"])


def v1_equivalent(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    """The receipt as spec v1 would have reported it. A v2 receipt exists only because the
    PR patch did not apply whole (A5), which under v1 is NOT_SCORABLE / GOLD_PORT_FAILED."""
    if spec_version_of(receipt) != SPEC_V2:
        return receipt
    return {**receipt, "label": NOT_SCORABLE_ORACLE_INVALID, "sub_reason": "GOLD_PORT_FAILED"}


def summarize(receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Headline numbers are what spec v1 (pre-registered) reports: v1 receipts, plus each
    v2 receipt at its v1-equivalent label (GOLD_PORT_FAILED). ``v1_plus_v2`` counts the v2
    receipts at their own labels (A5, designed after the V11/V12 replays), reported apart.
    A receipt with any other spec version is in neither block (``unknown_spec_versions``)."""
    versions: dict[str, int] = {}
    for r in receipts:
        versions[spec_version_of(r)] = versions.get(spec_version_of(r), 0) + 1
    known = [r for r in receipts if spec_version_of(r) in (SPEC_V1, SPEC_V2)]
    return {
        **_summary([v1_equivalent(r) for r in known]),
        "v1_plus_v2": _summary(known),
        "spec_version_counts": dict(sorted(versions.items())),
        "unknown_spec_versions": {
            v: n for v, n in sorted(versions.items()) if v not in (SPEC_V1, SPEC_V2)
        },
    }


def _summary(receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for r in receipts:
        counts[r["label"]] = counts.get(r["label"], 0) + 1
    valid = [r for r in receipts if r["label"] in VALID_ORACLE_LABELS]
    resolved = sum(r["label"] == RESOLVED for r in valid)
    lo, hi = clopper_pearson(resolved, len(valid))

    def rate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        k = sum(r["label"] == RESOLVED for r in rows)
        a, b = clopper_pearson(k, len(rows))
        return {"resolved": k, "n": len(rows), "ci95": [round(a, 4), round(b, 4)]}

    by_route = {
        route: rate([r for r in valid if r["route"] == route])
        for route in sorted({r["route"] for r in valid})
    }
    by_status = {
        s: rate([r for r in valid if str(r["candidate_raw_status"]) == s])
        for s in sorted({str(r["candidate_raw_status"]) for r in valid})
    }
    by_capped = {str(c): rate([r for r in valid if r["capped"] == c]) for c in (True, False)}
    no_leak = rate([r for r in valid if not r.get("leakage_flags")])
    partial_timeouts = [
        {
            "task_key": r["task_key"],
            "label": r["label"],
            "shadow_label": r.get("shadow_label"),
            "status": r["candidate_raw_status"],
            "capped": r["capped"],
            "f2p": f"{r.get('f2p_pass', '-')}/{r.get('f2p_total', '-')}",
        }
        for r in valid
        if not r["candidate_empty"]
        and (
            r["candidate_raw_status"] == "TIMEOUT"
            or r.get("failure_kind") == "TIMEOUT"
            or r["capped"]
        )
    ]
    return {
        "counts": dict(sorted(counts.items())),
        "valid_oracle_n": len(valid),
        "resolved": resolved,
        "resolved_rate": (resolved / len(valid)) if valid else None,
        "ci95": [round(lo, 4), round(hi, 4)],
        "by_route": by_route,
        "by_raw_status": by_status,
        "by_capped": by_capped,
        "excluding_leakage_flags": no_leak,
        "partial_candidate_timeouts": partial_timeouts,
    }
