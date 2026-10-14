"""Stage the hidden verifier test out of the workspace for the with-Nexus subprocess (PR-2).

Under the strict/counted lane the hidden test (``test_hidden.py`` beside the visible test:
P16 ``.nexus/bench_cases/<id>/``, hard_v1 ``bench_fixtures/online_ab_hard_v1/<dir>/``) is moved
out of the workspace for the whole with-Nexus row, so nothing the product runs (CodeIntel,
sandbox, ultra_review, the candidate, pytest on a directory) can read or execute it. It is put
back only while the runner itself runs the hidden verifier (a subprocess whose argv names the
hidden file) and permanently when the row ends, including when the row raises (``finally``).
The bare arm is unchanged: it runs after the restore, in an empty cwd.

Where it goes and how it is protected (the with-Nexus subprocess runs as the same user, so
every layer is defence in depth, and every failure is fail closed):

* a per-run ``mkdtemp`` (random name) under ``~/.cache/nexus-bench-hidden``; the path lives only
  in this process's memory, is never exported, and no subprocess env var names it
  (``BENCH_ROOT`` and any variable pointing into the staging tree are scrubbed from the
  with-Nexus subprocess env). The parent and the run directory are ``0300`` (no listing), so
  the random name cannot be discovered by walking; symlinked components are refused;
* the staged file is mode ``0000`` while staged (readable only inside the verifier window);
* a ``<staged>.sha256`` sidecar is written at stage time; every move back first ``lstat``s the
  staged file (regular, one link, no symlink), reads it with ``O_NOFOLLOW`` and checks its
  sha256 against the sidecar and the hash taken when staging. Any mismatch, a missing sidecar,
  or a failure to re-stage after the verifier is ``hidden_test_tampered``: the workspace copy is
  quarantined (moved under the staging dir with a ``.tampered`` suffix, mode ``0000``), the row
  is flagged, and the run is marked aborted (the runner stops and exits 3);
* the row records only ``sha256(staged path)``, never the path.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

HIDDEN_TEST_NAME = "test_hidden.py"
SIDECAR_SUFFIX = ".sha256"
QUARANTINE_SUFFIX = ".tampered"
TAMPERED = "hidden_test_tampered"
# Variables never passed to the with-Nexus subprocess while a hidden test is staged.
SCRUBBED_ENV_KEYS = ("BENCH_ROOT",)
_DIR_MODE = 0o300  # write + search only: entries can be created/opened by exact name, never listed
_STAGED_MODE = 0o000
# Test hook; production uses ~/.cache/nexus-bench-hidden.
_STAGING_PARENT: Path | None = None


class HiddenTestStagingError(RuntimeError):
    """The hidden test could not be staged or restored safely (fail closed)."""


def _regular_single_link(path: Path, *, label: str) -> os.stat_result:
    try:
        info = os.lstat(path)
    except FileNotFoundError as exc:
        raise HiddenTestStagingError(f"{label}_missing") from exc
    if stat.S_ISLNK(info.st_mode):
        raise HiddenTestStagingError(f"{label}_symlink_refused")
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise HiddenTestStagingError(f"{label}_not_regular_single_link")
    return info


def _read_nofollow(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise HiddenTestStagingError("not_regular_single_link")
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
            raise HiddenTestStagingError("staging_root_symlink_refused")


def _path_digest(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()


_ACTIVE: dict[str, HiddenTestStaging] = {}
_RUN_ROOTS: dict[str, Path] = {}
_QUARANTINED: set[str] = set()
_RUN_ABORT: list[str] = []


@dataclass
class HiddenTestStaging:
    hidden_path: Path
    staged_path: Path
    staged: bool = False
    sha256: str = ""
    original_mode: int = 0o644
    absent_checks: int = 0
    verify_windows: int = 0
    quarantined: bool = False
    violations: list[str] = field(default_factory=list)

    @property
    def sidecar_path(self) -> Path:
        return self.staged_path.with_name(self.staged_path.name + SIDECAR_SUFFIX)

    def _tampered(self, detail: str) -> HiddenTestStagingError:
        if TAMPERED not in self.violations:
            self.violations.append(TAMPERED)
        return HiddenTestStagingError(f"{TAMPERED}:{detail}")

    def _fail_closed(self, detail: str) -> None:
        """Quarantine whatever sits at the hidden path, flag the row and abort the run."""
        if TAMPERED not in self.violations:
            self.violations.append(TAMPERED)
        self.violations.append(f"fail_closed:{detail}"[:200])
        if os.path.lexists(self.hidden_path):
            index = 0
            while True:
                target = self.staged_path.with_name(
                    f"{HIDDEN_TEST_NAME}{QUARANTINE_SUFFIX}.{index}"
                )
                if not os.path.lexists(target):
                    break
                index += 1
            os.replace(self.hidden_path, target)  # moves a link itself, never its target
            if not os.path.islink(target):
                os.chmod(target, _STAGED_MODE)
        self.quarantined = True
        _QUARANTINED.add(str(self.hidden_path))
        _RUN_ABORT.append(f"{TAMPERED}:{detail}"[:200])

    def _move_out(self) -> None:
        """Hidden test (workspace) -> staged path (mode 0000), sidecar records its hash."""
        info = _regular_single_link(self.hidden_path, label="hidden_test")
        digest = _sha256_nofollow(self.hidden_path)
        if self.sha256 and digest != self.sha256:
            raise self._tampered("hidden_changed_while_restored")
        if os.path.lexists(self.staged_path) or os.path.lexists(self.sidecar_path):
            raise HiddenTestStagingError("staged_path_occupied")
        if not self.sha256:
            self.original_mode = stat.S_IMODE(info.st_mode)
        _move_file(self.hidden_path, self.staged_path)
        if _sha256_nofollow(self.staged_path) != digest:
            raise self._tampered("staged_copy_mismatch")
        os.chmod(self.staged_path, _STAGED_MODE)
        _write_new(
            self.sidecar_path,
            json.dumps({"sha256": digest, "origin": str(self.hidden_path)}).encode("utf-8"),
        )
        os.chmod(self.sidecar_path, 0o400)
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
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            raise self._tampered("sidecar_unreadable") from exc
        expected = str(sidecar.get("sha256") or "") if isinstance(sidecar, dict) else ""
        origin = str(sidecar.get("origin") or "") if isinstance(sidecar, dict) else ""
        os.chmod(self.staged_path, 0o400)  # lstat-checked regular file just above
        digest = _sha256_nofollow(self.staged_path)
        if not expected or digest != expected or origin != str(self.hidden_path):
            os.chmod(self.staged_path, _STAGED_MODE)
            raise self._tampered("sidecar_mismatch")
        if self.sha256 and digest != self.sha256:
            os.chmod(self.staged_path, _STAGED_MODE)
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
        os.chmod(self.hidden_path, self.original_mode or 0o644)
        os.chmod(self.sidecar_path, 0o600)
        os.unlink(self.sidecar_path)
        if _sha256_nofollow(self.hidden_path) != digest:
            raise self._tampered("restored_copy_mismatch")
        self.sha256 = digest
        self.staged = False

    def stage(self) -> None:
        self.staged_path.parent.mkdir(mode=0o700, exist_ok=True)
        os.chmod(self.staged_path.parent, _DIR_MODE)
        if os.path.lexists(self.hidden_path):
            if os.path.islink(self.hidden_path):
                raise HiddenTestStagingError("hidden_test_symlink_refused")
        elif os.path.lexists(self.staged_path):
            # Left staged by an earlier crash in this run: recover only a verified file.
            self._move_back()
        self._move_out()
        if os.path.lexists(self.hidden_path):
            raise HiddenTestStagingError("hidden_test_still_present")
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

        Raises ``HiddenTestStagingError`` before yielding when the staged file fails
        verification (the verifier never runs on it), and after the verifier when it cannot be
        staged again (the workspace copy is quarantined and the run aborted)."""
        if not self.staged:
            yield
            return
        self.check_absent("verify_window")
        try:
            self._move_back()
        except HiddenTestStagingError as exc:
            self._fail_closed(f"verify_window_move_back:{exc}")
            raise
        self.verify_windows += 1
        try:
            yield
        finally:
            try:
                self._move_out()
            except (HiddenTestStagingError, OSError) as exc:
                self._fail_closed(f"restage_failed:{exc}")
                raise HiddenTestStagingError(f"{TAMPERED}:restage_failed") from exc

    def restore(self) -> None:
        """Idempotent: puts a verified staged file back; never raises (fails closed instead)."""
        if not self.staged:
            return
        self.check_absent("row_end")
        try:
            self._move_back()
        except (HiddenTestStagingError, OSError) as exc:
            self._fail_closed(f"row_end:{exc}")

    def row_fields(self) -> dict[str, object]:
        return {
            "hidden_staged": True,
            "hidden_staged_path_sha256": _path_digest(self.staged_path),
            "hidden_absent_checks": self.absent_checks,
            "hidden_verify_windows": self.verify_windows,
            "hidden_staging_violations": list(self.violations),
            "hidden_test_tampered": TAMPERED in self.violations,
            "hidden_test_quarantined": self.quarantined,
        }


def active_staging_for(path: str | Path) -> HiddenTestStaging | None:
    key = str(Path(path).resolve())
    return _ACTIVE.get(key)


def is_quarantined(path: str | Path) -> bool:
    return str(Path(os.path.abspath(path))) in _QUARANTINED


def run_abort_reason() -> str:
    return _RUN_ABORT[0] if _RUN_ABORT else ""


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


def _staging_parent() -> Path:
    parent = (
        _STAGING_PARENT
        if _STAGING_PARENT is not None
        else Path.home() / ".cache" / "nexus-bench-hidden"
    )
    return Path(os.path.abspath(parent))


def scrub_subprocess_env(env: Mapping[str, str]) -> dict[str, str]:
    """Env for a subprocess while a hidden test is staged: no ``BENCH_ROOT`` and no variable
    whose value points into the staging tree."""
    out = {key: value for key, value in env.items() if key not in SCRUBBED_ENV_KEYS}
    if not _ACTIVE and not _RUN_ROOTS:
        return out
    roots = [_staging_parent(), *_RUN_ROOTS.values()]
    for key, value in list(out.items()):
        for part in str(value).split(os.pathsep):
            if not part or not os.path.isabs(part):
                continue
            candidate = Path(os.path.abspath(part))
            if any(candidate == root or root in candidate.parents for root in roots):
                out.pop(key, None)
                break
    return out


def staging_root(repo_root: Path) -> Path:
    """This run's private staging dir (random mkdtemp name, kept only in memory)."""
    parent = _staging_parent()
    repo = repo_root.resolve()
    if parent.resolve() == repo or repo in parent.resolve().parents:
        raise HiddenTestStagingError("staging_root_inside_workspace")
    cached = _RUN_ROOTS.get(str(parent))
    if cached is not None and os.path.isdir(cached):
        _no_symlink_components(cached)
        return cached
    _no_symlink_components(parent)
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _no_symlink_components(parent)
    os.chmod(parent, _DIR_MODE)
    root = Path(tempfile.mkdtemp(prefix="run-", dir=parent))
    os.chmod(root, _DIR_MODE)
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
