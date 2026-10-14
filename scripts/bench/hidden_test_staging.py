"""Stage the hidden verifier test out of the workspace for the with-Nexus subprocess (PR-2).

Under the strict/counted lane the hidden test (``test_hidden.py`` beside the visible test:
P16 ``.nexus/bench_cases/<id>/``, hard_v1 ``bench_fixtures/online_ab_hard_v1/<dir>/``) is moved
out of the workspace for the whole with-Nexus row, so nothing the product runs (CodeIntel,
sandbox, ultra_review, the candidate, pytest on a directory) can read or execute it. It is put
back only while the runner itself runs the hidden verifier (a subprocess whose argv names the
hidden file) and permanently when the row ends, including when the row raises (``finally``).
The bare arm is unchanged: it runs after the restore, in an empty cwd.

Where it goes and how it is protected (every failure is fail closed):

* a per-run ``mkdtemp`` (random name) under ``~/.cache/nexus-bench-hidden``; the path lives only
  in the runner's memory and in its own output-dir record (``run_manifest.json``), never in a
  subprocess env (``BENCH_ROOT`` and any variable pointing into the staging tree are scrubbed
  from the with-Nexus subprocess env). The parent and the run directory are ``0300`` (no
  listing); symlinked components are refused. There is no fixed-name manifest outside the
  random run dir;
* the staged file is mode ``0000`` while staged (``0400`` only inside the verifier window);
* a ``<staged>.sha256`` sidecar is written at stage time; every move back first ``lstat``s the
  staged file (regular, one link, no symlink), reads it with ``O_NOFOLLOW`` and checks its
  sha256 against the sidecar and the hash taken when staging. Any mismatch, a missing sidecar,
  any OS error or interrupt, or a failure to re-stage after the verifier is
  ``hidden_test_tampered``: the workspace copy is quarantined (``.tampered``, mode ``0000``), the
  row is flagged, and the run is aborted (the runner stops and exits 3);
* recovery after a killed run uses the output-dir record as the authority: the run dir must be
  ours and closed to group/other, each staged file must lie inside it and match both the
  recorded sha256 and its sidecar; anything else is quarantined and the run aborts;
* the row records only ``sha256(staged path)``, never the path.

Residual risk (honest): the with-Nexus subprocess runs as the same user, and same-user code can
defeat file permissions (chmod a ``0000`` file, guess a path). Staging, mode ``0000``, the
unguessable unlistable directory and the env scrub raise the bar; the boundary is that the
product never executes candidate or visible-test code unconfined under the counted lane: it runs
the visible test on a scratch copy inside ``sandboxed_lane.confinement`` (default-deny reads under
``$HOME``, the staging parent and the hidden test as forbidden roots), and refuses to run it at
all without an OS barrier (``confinement_unavailable``).
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


RUN_DIR_MANIFEST_NAME = "MANIFEST.json"
RUN_RECORD_KEY = "hidden_staging"
# The runner's own record of this run's staging (in the bench OUTPUT dir, never in any
# subprocess env): the run-dir path and every staged file's sha256. It is the recovery
# authority; set by the runner via configure_run_record().
_RUN_RECORD_PATH: list[Path] = []


def configure_run_record(path: Path | None) -> None:
    _RUN_RECORD_PATH.clear()
    if path is not None:
        _RUN_RECORD_PATH.append(Path(os.path.abspath(path)))


def _read_json_nofollow(path: Path) -> dict:
    if not os.path.lexists(path):
        return {}
    _regular_single_link(path, label="staging_record")
    mode = stat.S_IMODE(os.lstat(path).st_mode)
    if not mode & 0o400:
        os.chmod(path, 0o400)
    try:
        data = json.loads(_read_nofollow(path).decode("utf-8") or "{}")
    finally:
        if not mode & 0o400:
            os.chmod(path, mode)
    return data if isinstance(data, dict) else {}


def _write_json_atomic(path: Path, data: dict, *, mode: int) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if os.path.lexists(tmp):
        os.unlink(tmp)
    _write_new(tmp, json.dumps(data, sort_keys=True).encode("utf-8"))
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def _record_update(run_root: Path, origin: Path, entry: dict[str, str] | None) -> None:
    """Keep the run-dir manifest (mode 0000, inside the random run dir) and the runner's
    output-dir record in step: origin -> staged path + sha256."""
    manifest = run_root / RUN_DIR_MANIFEST_NAME
    entries = dict(_read_json_nofollow(manifest).get("entries") or {})
    if entry is None:
        entries.pop(str(origin), None)
    else:
        entries[str(origin)] = entry
    _write_json_atomic(manifest, {"run_root": str(run_root), "entries": entries}, mode=_STAGED_MODE)
    if _RUN_RECORD_PATH:
        record_path = _RUN_RECORD_PATH[0]
        record = _read_json_nofollow(record_path)
        record[RUN_RECORD_KEY] = {"run_root": str(run_root), "entries": entries}
        record_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(record_path, record, mode=0o600)


def _trusted_run_root(run_root: Path) -> None:
    """Untrusted on-disk state: the run dir must be ours, a real directory, no symlinked
    component, and closed to group/other."""
    _no_symlink_components(run_root)
    info = os.lstat(run_root)
    if not stat.S_ISDIR(info.st_mode):
        raise HiddenTestStagingError("run_root_not_a_directory")
    if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
        raise HiddenTestStagingError("run_root_not_owned")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise HiddenTestStagingError("run_root_open_to_others")


def recover_from_run_record(record_path: Path) -> list[str]:
    """Restore hidden tests a killed run left staged, using the runner's output-dir record as
    the authority. Each staged file must sit inside the recorded run dir and match BOTH its
    sidecar and the recorded sha256; anything else is quarantined and aborts this run."""
    record = _read_json_nofollow(Path(record_path)).get(RUN_RECORD_KEY)
    if not isinstance(record, dict):
        return []
    run_root = Path(str(record.get("run_root") or ""))
    entries = record.get("entries") if isinstance(record.get("entries"), dict) else {}
    if not entries:
        return []
    restored: list[str] = []
    try:
        _trusted_run_root(run_root)
    except (HiddenTestStagingError, OSError) as exc:
        _RUN_ABORT.append(f"{TAMPERED}:recovery_run_root:{exc}"[:200])
        raise HiddenTestStagingError(f"{TAMPERED}:recovery_run_root") from exc
    for origin, entry in sorted(entries.items()):
        if not isinstance(entry, dict):
            continue
        staged = Path(str(entry.get("staged") or ""))
        expected = str(entry.get("sha256") or "")
        origin_path = Path(origin)
        leftover = HiddenTestStaging(hidden_path=origin_path, staged_path=staged, staged=True, sha256=expected)
        if run_root not in staged.parents or not expected:
            leftover._fail_closed("recovery:staged_outside_run_root")
            continue
        if os.path.lexists(origin_path) and not os.path.lexists(staged):
            restored.append(origin)  # already restored before the kill
            continue
        try:
            os.chmod(staged.parent, 0o700)
            leftover._move_back()
            restored.append(origin)
        except (HiddenTestStagingError, OSError) as exc:
            leftover._fail_closed(f"recovery:{type(exc).__name__}:{exc}")
        finally:
            try:
                os.chmod(staged.parent, _DIR_MODE)
            except OSError:
                pass
    return restored


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
    failed: bool = False
    violations: list[str] = field(default_factory=list)

    @property
    def sidecar_path(self) -> Path:
        return self.staged_path.with_name(self.staged_path.name + SIDECAR_SUFFIX)

    def _tampered(self, detail: str) -> HiddenTestStagingError:
        if TAMPERED not in self.violations:
            self.violations.append(TAMPERED)
        return HiddenTestStagingError(f"{TAMPERED}:{detail}")

    def _lock_staged_bytes(self) -> None:
        """Best effort: a staged regular file goes back to mode 0000 (never raises)."""
        try:
            info = os.lstat(self.staged_path)
            if stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) != _STAGED_MODE:
                os.chmod(self.staged_path, _STAGED_MODE)
        except OSError:
            pass

    def _fail_closed(self, detail: str) -> None:
        """Never raises: flag the row, abort the run, lock the staged bytes and quarantine
        whatever sits at the hidden path (so no verifier can run on it)."""
        self.failed = True
        if TAMPERED not in self.violations:
            self.violations.append(TAMPERED)
        self.violations.append(f"fail_closed:{detail}"[:200])
        _RUN_ABORT.append(f"{TAMPERED}:{detail}"[:200])
        _QUARANTINED.add(str(self.hidden_path))
        self._lock_staged_bytes()
        try:
            if os.path.lexists(self.hidden_path):
                index = 0
                while True:
                    target = self.staged_path.with_name(f"{HIDDEN_TEST_NAME}{QUARANTINE_SUFFIX}.{index}")
                    if not os.path.lexists(target):
                        break
                    index += 1
                os.replace(self.hidden_path, target)  # moves a link itself, never its target
                if not os.path.islink(target):
                    os.chmod(target, _STAGED_MODE)
                self.quarantined = True
        except OSError as exc:
            # The workspace copy could not be moved: the run is already aborted and the path
            # stays registered as quarantined, so the verifier is refused for it.
            self.violations.append(f"quarantine_failed:{type(exc).__name__}")

    @contextmanager
    def _fail_closed_on_error(self, where: str) -> Iterator[None]:
        """Any exception -> fail closed. Ordinary errors surface as HiddenTestStagingError;
        KeyboardInterrupt/SystemExit are re-raised after the row/run are marked."""
        try:
            yield
        except BaseException as exc:
            self._fail_closed(f"{where}:{type(exc).__name__}:{exc}")
            if isinstance(exc, HiddenTestStagingError) or not isinstance(exc, Exception):
                raise
            raise HiddenTestStagingError(f"{TAMPERED}:{where}:{type(exc).__name__}") from exc

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
        try:
            staged_digest = _sha256_nofollow(self.staged_path)
        finally:
            os.chmod(self.staged_path, _STAGED_MODE)
        if staged_digest != digest:
            raise self._tampered("staged_copy_mismatch")
        _write_new(
            self.sidecar_path,
            json.dumps({"sha256": digest, "origin": str(self.hidden_path)}).encode("utf-8"),
        )
        os.chmod(self.sidecar_path, 0o400)
        self.sha256 = digest
        self.staged = True
        _record_update(self.staged_path.parent.parent, self.hidden_path, {"staged": str(self.staged_path), "sha256": digest})

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
        try:
            digest = _sha256_nofollow(self.staged_path)
        finally:
            os.chmod(self.staged_path, _STAGED_MODE)
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
        _move_file(self.staged_path, self.hidden_path)  # still 0000 while moving
        os.chmod(self.hidden_path, 0o400)
        if _sha256_nofollow(self.hidden_path) != digest:
            raise self._tampered("restored_copy_mismatch")
        os.chmod(self.hidden_path, self.original_mode or 0o644)
        os.chmod(self.sidecar_path, 0o600)
        os.unlink(self.sidecar_path)
        self.sha256 = digest
        self.staged = False
        _record_update(self.staged_path.parent.parent, self.hidden_path, None)

    def stage(self) -> None:
        with self._fail_closed_on_error("stage"):
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

        Raises ``HiddenTestStagingError`` before yielding unless the staged file verifies (the
        verifier never runs otherwise, including when this staging already failed), and after
        the verifier when it cannot be staged again (quarantine + run abort)."""
        if self.failed or not self.staged:
            raise HiddenTestStagingError(f"{TAMPERED}:verify_window_not_staged")
        self.check_absent("verify_window")
        with self._fail_closed_on_error("verify_window_move_back"):
            self._move_back()
        self.verify_windows += 1
        try:
            yield
        finally:
            with self._fail_closed_on_error("restage_failed"):
                self._move_out()

    def restore(self) -> None:
        """Idempotent; puts a verified staged file back. Ordinary errors fail closed without
        raising; KeyboardInterrupt/SystemExit are re-raised after failing closed."""
        if not self.staged or self.failed:
            return
        self.check_absent("row_end")
        try:
            with self._fail_closed_on_error("row_end"):
                self._move_back()
        except HiddenTestStagingError:
            pass

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
    root = Path(tempfile.mkdtemp(prefix="run-", dir=parent))  # 0700, random name
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
    try:
        root = staging_root(repo_root)
    except BaseException as exc:
        _RUN_ABORT.append(f"{TAMPERED}:staging_root:{type(exc).__name__}:{exc}"[:200])
        raise
    staging = HiddenTestStaging(
        hidden_path=Path(os.path.abspath(hidden)),
        staged_path=root / _task_key(task_id, trial_index) / HIDDEN_TEST_NAME,
    )
    if not os.path.lexists(staging.hidden_path) and not os.path.lexists(staging.staged_path):
        # The counted lane requires a hidden test for every task: a missing one is never
        # "not staged" (the verifier would fall back to the visible test) - fail closed.
        staging._fail_closed("hidden_test_missing")
        raise HiddenTestStagingError(f"{TAMPERED}:hidden_test_missing")
    key = str(staging.hidden_path.resolve())
    _ACTIVE[key] = staging
    try:
        staging.stage()
        yield staging
    finally:
        _ACTIVE.pop(key, None)
        staging.restore()
