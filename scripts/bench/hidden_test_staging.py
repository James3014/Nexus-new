"""Stage the hidden verifier test out of the workspace for the with-Nexus subprocess (PR-2).

Under the strict/counted lane the hidden test (``test_hidden.py`` beside the visible test:
P16 ``.nexus/bench_cases/<id>/``, hard_v1 ``bench_fixtures/online_ab_hard_v1/<dir>/``) is moved
to ``$BENCH_ROOT/hidden/<task>/`` for the whole with-Nexus row, so nothing the product runs
(CodeIntel, sandbox, ultra_review, pytest on a directory) can read or execute it. It is put
back only while the runner itself runs the hidden verifier (a subprocess whose argv names the
hidden file) and permanently when the row ends, including when the row raises (``finally``).
The bare arm is unchanged: it runs after the restore, in an empty cwd.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

HIDDEN_TEST_NAME = "test_hidden.py"
STAGING_DIRNAME = "hidden"


class HiddenTestStagingError(RuntimeError):
    """The hidden test could not be staged (fail closed: the row must not run)."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class HiddenTestStaging:
    hidden_path: Path
    staged_path: Path
    staged: bool = False
    sha256: str = ""
    absent_checks: int = 0
    verify_windows: int = 0
    violations: list[str] = field(default_factory=list)

    def stage(self) -> None:
        self.staged_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.hidden_path.exists() and self.staged_path.exists():
            # A previous crash left it staged: recover the original first.
            os.replace(self.staged_path, self.hidden_path)
        if not self.hidden_path.is_file():
            raise HiddenTestStagingError(f"hidden_test_missing:{self.hidden_path}")
        self.sha256 = _sha256(self.hidden_path)
        shutil.move(str(self.hidden_path), str(self.staged_path))
        self.staged = True
        if self.hidden_path.exists():
            raise HiddenTestStagingError(f"hidden_test_still_present:{self.hidden_path}")
        self.check_absent("staged")

    def check_absent(self, where: str) -> bool:
        """Record one absence check; a present hidden file is a violation (row is flagged)."""
        self.absent_checks += 1
        if self.staged and self.hidden_path.exists():
            self.violations.append(f"hidden_present_during_run:{where}")
            return False
        return True

    def _move_back(self) -> None:
        if not self.staged_path.exists():
            raise HiddenTestStagingError(f"staged_hidden_test_missing:{self.staged_path}")
        if self.hidden_path.exists() or self.hidden_path.is_symlink():
            # Whatever reappeared during the run is replaced by the original.
            self.hidden_path.unlink()
        shutil.move(str(self.staged_path), str(self.hidden_path))
        if self.sha256 and _sha256(self.hidden_path) != self.sha256:
            self.violations.append("hidden_restored_hash_mismatch")

    @contextmanager
    def verify_window(self) -> Iterator[None]:
        """Put the hidden test back for the runner's own hidden verifier, then stage again."""
        if not self.staged:
            yield
            return
        self.check_absent("verify_window")
        self._move_back()
        self.staged = False
        self.verify_windows += 1
        try:
            yield
        finally:
            shutil.move(str(self.hidden_path), str(self.staged_path))
            self.staged = True

    def restore(self) -> None:
        if not self.staged:
            return
        self.check_absent("row_end")
        self._move_back()
        self.staged = False

    def row_fields(self) -> dict[str, object]:
        return {
            "hidden_staged": True,
            "hidden_staged_path": str(self.staged_path),
            "hidden_absent_checks": self.absent_checks,
            "hidden_verify_windows": self.verify_windows,
            "hidden_staging_violations": list(self.violations),
        }


_ACTIVE: dict[str, HiddenTestStaging] = {}


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
    bench_root = os.environ.get("BENCH_ROOT", "").strip()
    root = (
        Path(bench_root).expanduser() / STAGING_DIRNAME
        if bench_root
        else Path(tempfile.gettempdir()) / "nexus-bench-hidden"
    ).resolve()
    repo = repo_root.resolve()
    if root == repo or repo in root.parents:
        raise HiddenTestStagingError(f"staging_root_inside_workspace:{root}")
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
        hidden_path=hidden.resolve(),
        staged_path=staging_root(repo_root) / _task_key(task_id, trial_index) / HIDDEN_TEST_NAME,
    )
    if not hidden.is_file() and not staging.staged_path.is_file():
        # No hidden test for this task (and nothing left staged by a killed run).
        yield None
        return
    key = str(staging.hidden_path)
    _ACTIVE[key] = staging
    try:
        staging.stage()
        yield staging
    finally:
        _ACTIVE.pop(key, None)
        staging.restore()
