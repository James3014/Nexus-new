"""Every bare gitlink must be declared in .gitmodules.

actions/checkout runs ``git submodule foreach --recursive`` during its
credential cleanup even when submodules are not requested. A tracked gitlink
without a matching ``.gitmodules`` entry makes that call fail with
``No url found for submodule path`` and breaks every checkout-based gate.
"""

from __future__ import annotations

import configparser
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _tracked_gitlinks() -> list[str]:
    output = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    paths: list[str] = []
    for entry in output.split(b"\0"):
        if not entry:
            continue
        metadata, _, path = entry.partition(b"\t")
        if metadata.split()[0] == b"160000":
            paths.append(path.decode("utf-8"))
    return sorted(paths)


def _declared_submodules() -> dict[str, dict[str, str]]:
    parser = configparser.ConfigParser()
    parser.read(ROOT / ".gitmodules", encoding="utf-8")
    declared: dict[str, dict[str, str]] = {}
    for section in parser.sections():
        if not section.startswith("submodule "):
            continue
        declared[parser[section].get("path", "")] = dict(parser[section])
    return declared


def test_every_tracked_gitlink_is_declared_in_gitmodules() -> None:
    gitlinks = _tracked_gitlinks()
    assert gitlinks, "expected at least one tracked gitlink in this repository"
    declared = _declared_submodules()
    missing = [path for path in gitlinks if path not in declared]
    assert not missing, f"gitlinks without a .gitmodules entry: {missing}"
    for path in gitlinks:
        assert declared[path].get("url"), f"{path} has no url in .gitmodules"


def test_submodule_foreach_succeeds_on_clean_tree() -> None:
    result = subprocess.run(
        ["git", "submodule", "foreach", "--recursive", ":"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
