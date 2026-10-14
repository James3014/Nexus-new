"""Stage the hidden verifier test out of the workspace for the with-Nexus subprocess (PR-2).

Under the strict/counted lane the hidden test (``test_hidden.py`` beside the visible test:
P16 ``.nexus/bench_cases/<id>/``, hard_v1 ``bench_fixtures/online_ab_hard_v1/<dir>/``) is moved
to a private per-run directory ``$BENCH_ROOT/hidden/hidden-XXXX/<task>/`` (0700, created with
``mkdtemp``) for the whole with-Nexus row, so nothing the product runs (CodeIntel, sandbox,
ultra_review, pytest on a directory) can read or execute it. It is put back only while the
runner itself runs the hidden verifier (a subprocess whose argv names the hidden file) and
permanently when the row ends, including when the row raises (``finally``). The bare arm is
unchanged: it runs after the restore, in an empty cwd.

Tamper resistance (fail closed):

* ``BENCH_ROOT`` is required (no shared temp-dir fallback); the staging root and every path
  component are refused when they are symlinks, and the root may not lie inside the workspace;
* the hidden test must be a regular, single-link file (never a symlink) to be staged;
* a ``<staged>.sha256`` sidecar is written at stage time; every move back (verifier window,
  row end, recovery of a killed run) first ``lstat``s the staged file (regular, one link, no
  symlink), reads it with ``O_NOFOLLOW`` and checks its sha256 against the sidecar and the
  hash taken when staging. A mismatch or a missing sidecar is ``hidden_test_tampered``: the
  file is never moved back and the verifier never runs on it.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

HIDDEN_TEST_NAME = "test_hidden.py"
STAGING_DIRNAME = "hidden"
SIDECAR_SUFFIX = ".sha256"
TAMPERED = "hidden_test_tampered"


class HiddenTestStagingError(RuntimeError):
    """The hidden test could not be staged or restored safely (fail closed)."""


def _regular_single_link(path: Path, *, label: str) -> os.stat_result:
    try:
        info = os.lstat(path)
    except FileNotFoundError as exc:
        raise HiddenTestStagingError(f"{label}_missing:{path}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise HiddenTestStagingError(f"{label}_symlink_refused:{path}")
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise HiddenTestStagingError(f"{label}_not_regular_single_link:{path}")
    return info


def _read_nofollow(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise HiddenTestStagingError(f"not_regular_single_link:{path}")
        chunks = []
        while True:
            chunk = os.read(fd, 1 << 16)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _sha256_nofollow(path: Path) -> str:
    return hashlib.sha256(_read_nofollow(path)).hexdigest()


def _write_new(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


def _move_file(src: Path, dst: Path) -> None:
    """Atomic rename; across filesystems a verified copy (never following links) + unlink."""
    try:
        os.replace(src, dst)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        _write_new(dst, _read_nofollow(src))
        os.unlink(src)


def _no_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise HiddenTestStagingError(f"staging_root_symlink_refused:{current}")


@dataclass
class HiddenTestStaging:
    hidden_path: Path
    staged_path: Path
    staged: bool = False
    sha256: str = ""
    absent_checks: int = 0
    verify_windows: int = 0
    violations: list[str] = field(default_factory=list)

    @property
    def sidecar_path(self) -> Path:
        return self.staged_path.with_name(self.staged_path.name + SIDECAR_SUFFIX)

    def _tampered(self, detail: str) -> HiddenTestStagingError:
        if TAMPERED not in self.violations:
            self.violations.append(TAMPERED)
        return HiddenTestStagingError(f"{TAMPERED}:{detail}")

    def _move_out(self) -> None:
        """Hidden test (workspace) -> staged path, with the sidecar recording its hash."""
        _regular_single_link(self.hidden_path, label="hidden_test")
        digest = _sha256_nofollow(self.hidden_path)
        if self.sha256 and digest != self.sha256:
            raise self._tampered("hidden_changed_while_restored")
        if os.path.lexists(self.staged_path) or os.path.lexists(self.sidecar_path):
            raise HiddenTestStagingError(f"staged_path_occupied:{self.staged_path}")
        _move_file(self.hidden_path, self.staged_path)
        if _sha256_nofollow(self.staged_path) != digest:
            raise self._tampered("staged_copy_mismatch")
        _write_new(
            self.sidecar_path,
            json.dumps({"sha256": digest, "origin": str(self.hidden_path)}).encode("utf-8"),
        )
        self.sha256 = digest
        self.staged = True

    def _verified_staged_digest(self) -> str:
        try:
            _regular_single_link(self.staged_path, label="staged_hidden_test")
            _regular_single_link(self.sidecar_path, label="staged_hidden_sidecar")
        except HiddenTestStagingError as exc:
            raise self._tampered(str(exc)) from exc
        try:
            sidecar = json.loads(_read_nofollow(self.sidecar_path).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise self._tampered("sidecar_unreadable") from exc
        expected = str(sidecar.get("sha256") or "") if isinstance(sidecar, dict) else ""
        origin = str(sidecar.get("origin") or "") if isinstance(sidecar, dict) else ""
        digest = _sha256_nofollow(self.staged_path)
        if not expected or digest != expected or origin != str(self.hidden_path):
            raise self._tampered("sidecar_mismatch")
        if self.sha256 and digest != self.sha256:
            raise self._tampered("hash_changed_since_staging")
        return digest

    def _move_back(self) -> None:
        """Staged -> workspace, only after the staged file verified against its sidecar."""
        digest = self._verified_staged_digest()
        if os.path.lexists(self.hidden_path):
            # Whatever reappeared during the run (file or link) is replaced by the original;
            # unlink never follows a link.
            os.unlink(self.hidden_path)
        _move_file(self.staged_path, self.hidden_path)
        os.unlink(self.sidecar_path)
        if _sha256_nofollow(self.hidden_path) != digest:
            raise self._tampered("restored_copy_mismatch")
        self.sha256 = digest
        self.staged = False

    def stage(self) -> None:
        self.staged_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.path.lexists(self.hidden_path):
            if os.path.islink(self.hidden_path):
                raise HiddenTestStagingError(f"hidden_test_symlink_refused:{self.hidden_path}")
        elif os.path.lexists(self.staged_path):
            # Left staged by an earlier crash in this run: recover only a verified file.
            self._move_back()
        self._move_out()
        if os.path.lexists(self.hidden_path):
            raise HiddenTestStagingError(f"hidden_test_still_present:{self.hidden_path}")
        self.check_absent("staged")

    def check_absent(self, where: str) -> bool:
        """Record one absence check; a present hidden file is a violation (row is flagged)."""
        self.absent_checks += 1
        if self.staged and os.path.lexists(self.hidden_path):
            self.violations.append(f"hidden_present_during_run:{where}")
            return False
        return True

    @contextmanager
    def verify_window(self) -> Iterator[None]:
        """Put the verified hidden test back for the runner's own verifier, then stage again.

        Raises ``HiddenTestStagingError`` (``hidden_test_tampered``) before yielding when the
        staged file fails verification: the verifier never runs on it."""
        if not self.staged:
            yield
            return
        self.check_absent("verify_window")
        self._move_back()
        self.verify_windows += 1
        try:
            yield
        finally:
            self._move_out()

    def restore(self) -> None:
        if not self.staged:
            return
        self.check_absent("row_end")
        self._move_back()

    def row_fields(self) -> dict[str, object]:
        return {
            "hidden_staged": True,
            "hidden_staged_path": str(self.staged_path),
            "hidden_absent_checks": self.absent_checks,
            "hidden_verify_windows": self.verify_windows,
            "hidden_staging_violations": list(self.violations),
            "hidden_test_tampered": TAMPERED in self.violations,
        }


_ACTIVE: dict[str, HiddenTestStaging] = {}
_RUN_ROOTS: dict[str, Path] = {}


def active_staging_for(path: str | Path) -> HiddenTestStaging | None:
    key = str(Path(path).resolve())
    return _ACTIVE.get(key)


def stagings_named_in(argv: Sequence[str]) -> list[HiddenTestStaging]:
    """Active stagings whose hidden path appears in ``argv`` (the runner's hidden verifier)."""
    if not _ACTIVE:
        return []
    hits: list[HiddenTestStaging] = []
    for part in argv:
        text = str(part)
        if not text.endswith(HIDDEN_TEST_NAME):
            continue
        staging = active_staging_for(text)
        if staging is not None and staging not in hits:
            hits.append(staging)
    return hits


def check_all_absent(where: str) -> None:
    for staging in list(_ACTIVE.values()):
        staging.check_absent(where)


def staging_root(repo_root: Path) -> Path:
    """This run's private staging dir: ``$BENCH_ROOT/hidden/hidden-XXXX`` (0700, mkdtemp)."""
    bench_root_text = os.environ.get("BENCH_ROOT", "").strip()
    if not bench_root_text:
        raise HiddenTestStagingError("staging_root_unset")
    bench_root = Path(os.path.abspath(os.path.expanduser(bench_root_text)))
    parent = bench_root / STAGING_DIRNAME
    repo = repo_root.resolve()
    if parent.resolve() == repo or repo in parent.resolve().parents:
        raise HiddenTestStagingError(f"staging_root_inside_workspace:{parent}")
    cached = _RUN_ROOTS.get(str(parent))
    if cached is not None and cached.is_dir():
        _no_symlink_components(cached)
        return cached
    _no_symlink_components(bench_root)
    if os.path.lexists(parent) and os.path.islink(parent):
        raise HiddenTestStagingError(f"staging_root_symlink_refused:{parent}")
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="hidden-", dir=parent))
    _no_symlink_components(root)
    _RUN_ROOTS[str(parent)] = root
    return root


def _task_key(task_id: str, trial_index: int) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", str(task_id))[:120] or "task"
    return f"{slug}__t{int(trial_index)}"


@contextmanager
def staged_hidden_test(
    *, enabled: bool, repo_root: Path, test_file: str, task_id: str, trial_index: int
) -> Iterator[HiddenTestStaging | None]:
    """Stage ``test_hidden.py`` next to ``test_file`` for the duration of the block."""
    hidden = Path(test_file).with_name(HIDDEN_TEST_NAME)
    if not enabled:
        yield None
        return
    staging = HiddenTestStaging(
        hidden_path=Path(os.path.abspath(hidden)),
        staged_path=staging_root(repo_root) / _task_key(task_id, trial_index) / HIDDEN_TEST_NAME,
    )
    if not os.path.lexists(staging.hidden_path) and not os.path.lexists(staging.staged_path):
        # No hidden test for this task (and nothing left staged earlier in this run).
        yield None
        return
    key = str(staging.hidden_path.resolve())
    _ACTIVE[key] = staging
    try:
        staging.stage()
        yield staging
    finally:
        _ACTIVE.pop(key, None)
        staging.restore()
