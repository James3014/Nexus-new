from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_ROOT = "tests/archive"


def test_every_archived_test_file_is_inert() -> None:
    """Archived tests must not be pytest-collectable or runnable by the impact gate.

    The impact gate runs every changed ``test_*.py`` by explicit path, which bypasses
    ``norecursedirs``; an archived test cannot import its moved script, so a ``.py``
    file here would fail on the head side. Only ``*.txt`` files and manifests are allowed.
    """
    tracked = subprocess.run(
        ["git", "ls-files", ARCHIVE_ROOT],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    offenders = [
        path
        for path in tracked
        if not (path.endswith(".txt") or Path(path).name == "ARCHIVE_MANIFEST.md")
    ]
    assert offenders == []
