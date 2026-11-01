"""local_heal reads that #3053/#3057 left on a plain, link-following read.

Each test plants a symlink, hard link or FIFO at a repo path that points outside the repo and
asserts the outside text never reaches the result (and a FIFO never blocks the read).
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from nexus.services.local_heal.canonical_span import get_canonical_search_span
from nexus.services.local_heal.diff_repair import repair_malformed_diff
from nexus.services.local_heal.world_c_receipt import build_world_c_canonical_patch_projection

SENTINEL = "OUTSIDE-SENTINEL-RESIDUAL"
ORIGINAL = "def f():\n    return 1\n"
MALFORMED_DIFF = (
    "--- a/toy/m.py\n+++ b/toy/m.py\n@@ -9,1 +9,1 @@ bad\n-    return 1\n+    return 2\n"
)


def _outside(tmp_path: Path) -> Path:
    outside = tmp_path / "outside" / "secret.txt"
    outside.parent.mkdir()
    outside.write_text(f"def f():\n    {SENTINEL}\n", encoding="utf-8")
    return outside


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "toy").mkdir(parents=True)
    return repo


def _plant(kind: str, target: Path, outside: Path) -> None:
    if kind == "symlink":
        target.symlink_to(outside)
    elif kind == "hardlink":
        os.link(outside, target)
    elif kind == "parent_symlink":
        target.parent.rmdir()
        target.parent.symlink_to(outside.parent, target_is_directory=True)
        (outside.parent / target.name).write_text(outside.read_text(encoding="utf-8"))
    else:
        raise AssertionError(kind)


def _call_with_fifo_guard(fifo: Path, fn):
    """Run ``fn`` in a thread; if it blocks on ``fifo``, open the writer side to release it."""

    result: dict[str, object] = {}

    def run() -> None:
        try:
            result["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - reported to the test below
            result["error"] = exc

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(5)
    blocked = worker.is_alive()
    if blocked:
        fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        os.close(fd)
        worker.join(5)
    assert not blocked, "the read blocked on a FIFO"
    if "error" in result:
        raise result["error"]  # type: ignore[misc]
    return result.get("value")


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "parent_symlink"])
def test_diff_repair_does_not_read_linked_target(tmp_path: Path, kind: str) -> None:
    outside = _outside(tmp_path)
    repo = _repo(tmp_path)
    _plant(kind, repo / "toy" / "m.py", outside)

    repaired, receipt = repair_malformed_diff(
        MALFORMED_DIFF, "toy/m.py", "    return 1\n", span_start=2, source_root=str(repo)
    )

    assert SENTINEL not in repaired
    assert SENTINEL not in receipt.repaired_diff
    assert receipt.repair_success is True
    assert "-    return 1" in repaired


def test_diff_repair_reads_regular_target(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "toy" / "m.py").write_text("x = 0\n\tlocked_line\n", encoding="utf-8")

    repaired, receipt = repair_malformed_diff(
        "--- a/toy/m.py\n+++ b/toy/m.py\n-locked_line\n+new_line\n",
        "toy/m.py",
        "locked_line\n",
        span_start=2,
        source_root=str(repo),
    )

    assert receipt.repair_success is True
    assert "-\tlocked_line" in repaired
    assert "+\tnew_line" in repaired


def test_diff_repair_does_not_block_on_fifo(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    fifo = repo / "toy" / "m.py"
    os.mkfifo(fifo)

    repaired, receipt = _call_with_fifo_guard(
        fifo,
        lambda: repair_malformed_diff(
            MALFORMED_DIFF, "toy/m.py", "    return 1\n", source_root=str(repo)
        ),
    )

    assert receipt.repair_success is True
    assert "-    return 1" in repaired


def _world_c_roots(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    for root in (source, workspace):
        (root / "toy").mkdir(parents=True)
    return source, workspace


def test_world_c_projection_refuses_hard_link_in_source(tmp_path: Path) -> None:
    outside = _outside(tmp_path)
    source, workspace = _world_c_roots(tmp_path)
    os.link(outside, source / "toy" / "m.py")
    (workspace / "toy" / "m.py").write_text(ORIGINAL, encoding="utf-8")

    with pytest.raises(ValueError, match="regular single-link"):
        build_world_c_canonical_patch_projection(source, workspace, "toy/m.py")


def test_world_c_projection_refuses_hard_link_in_workspace(tmp_path: Path) -> None:
    outside = _outside(tmp_path)
    source, workspace = _world_c_roots(tmp_path)
    (source / "toy" / "m.py").write_text(ORIGINAL, encoding="utf-8")
    os.link(outside, workspace / "toy" / "m.py")

    with pytest.raises(ValueError, match="regular single-link"):
        build_world_c_canonical_patch_projection(source, workspace, "toy/m.py")


def test_world_c_projection_still_builds_from_regular_files(tmp_path: Path) -> None:
    source, workspace = _world_c_roots(tmp_path)
    (source / "toy" / "m.py").write_text(ORIGINAL, encoding="utf-8")
    (workspace / "toy" / "m.py").write_text(ORIGINAL.replace("1", "2"), encoding="utf-8")

    projection = build_world_c_canonical_patch_projection(source, workspace, "toy/m.py")

    assert projection["valid"] is True
    assert "-    return 1" in projection["patch"]
    assert "+    return 2" in projection["patch"]


def test_canonical_span_traceback_window_uses_given_source_text(tmp_path: Path) -> None:
    outside = _outside(tmp_path)
    repo = _repo(tmp_path)
    linked = repo / "toy" / "m.py"
    linked.symlink_to(outside)

    result = get_canonical_search_span(
        source_file=linked,
        failed_search_text="return 1",
        traceback_lines=[f'  File "{linked}", line 2, in f'],
        source_text=ORIGINAL,
    )

    assert result is not None
    assert result.source == "traceback_window"
    assert SENTINEL not in result.span
    assert result.span == ORIGINAL.rstrip("\n")
