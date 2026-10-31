"""Host-side writes into a directory model output can also write stay inside it.

``nexus.core.contained_write`` opens the file relative to the root one component at a time
without following links, and only a regular single-link file is read or written.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from nexus.core.contained_write import (
    PathContainmentError,
    contained_relative_path,
    read_text_in_root,
    write_text_in_root,
)


@pytest.fixture
def layout(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "f.py").write_text("orig", encoding="utf-8")
    return root, outside


def test_writes_and_reads_a_regular_file(layout):
    root, _ = layout
    (root / "pkg").mkdir()
    write_text_in_root(root, "pkg/a.py", "x = 1\n")
    assert (root / "pkg" / "a.py").read_text(encoding="utf-8") == "x = 1\n"
    write_text_in_root(root, "pkg/a.py", "y")
    assert read_text_in_root(root, "pkg/a.py") == "y"


def test_creates_parents_only_when_asked(layout):
    root, _ = layout
    with pytest.raises(PathContainmentError):
        write_text_in_root(root, "new/dir/a.txt", "x")
    assert not (root / "new").exists()
    write_text_in_root(root, "new/dir/a.txt", "x", create_parents=True)
    assert (root / "new" / "dir" / "a.txt").read_text(encoding="utf-8") == "x"


@pytest.mark.parametrize("bad", ["", ".", "..", "../outside/f.py", "a/../b", "/etc/passwd", "a\0b"])
def test_refuses_paths_that_are_not_plain_relative(layout, bad):
    root, _ = layout
    with pytest.raises(PathContainmentError):
        write_text_in_root(root, bad, "pwn", create_parents=True)
    with pytest.raises(PathContainmentError):
        read_text_in_root(root, bad)


def test_absolute_path_is_refused_even_inside_or_outside_the_root(layout):
    root, outside = layout
    (root / "a.py").write_text("in", encoding="utf-8")
    for target in (outside / "f.py", root / "a.py"):
        with pytest.raises(PathContainmentError):
            write_text_in_root(root, str(target), "pwn")
        with pytest.raises(PathContainmentError):
            read_text_in_root(root, str(target))
    assert (outside / "f.py").read_text(encoding="utf-8") == "orig"
    assert (root / "a.py").read_text(encoding="utf-8") == "in"


def test_final_symlink_is_not_followed(layout):
    root, outside = layout
    (root / "link.py").symlink_to(outside / "f.py")
    with pytest.raises(PathContainmentError):
        write_text_in_root(root, "link.py", "pwn")
    with pytest.raises(PathContainmentError):
        read_text_in_root(root, "link.py")
    assert (outside / "f.py").read_text(encoding="utf-8") == "orig"


def test_dangling_symlink_does_not_create_its_target(layout):
    root, outside = layout
    (root / "link.py").symlink_to(outside / "new.py")
    with pytest.raises(PathContainmentError):
        write_text_in_root(root, "link.py", "pwn")
    assert not (outside / "new.py").exists()


def test_symlinked_directory_is_not_followed(layout):
    root, outside = layout
    (root / "d").symlink_to(outside)
    with pytest.raises(PathContainmentError):
        write_text_in_root(root, "d/f.py", "pwn")
    with pytest.raises(PathContainmentError):
        write_text_in_root(root, "d/new.py", "pwn", create_parents=True)
    with pytest.raises(PathContainmentError):
        read_text_in_root(root, "d/f.py")
    assert (outside / "f.py").read_text(encoding="utf-8") == "orig"
    assert not (outside / "new.py").exists()


def test_hard_link_to_another_file_is_not_written(layout):
    root, outside = layout
    os.link(outside / "f.py", root / "h.py")
    with pytest.raises(PathContainmentError):
        write_text_in_root(root, "h.py", "pwn")
    with pytest.raises(PathContainmentError):
        read_text_in_root(root, "h.py")
    assert (outside / "f.py").read_text(encoding="utf-8") == "orig"


def _finishes(fn) -> tuple[bool, BaseException | None]:
    box: list[BaseException | None] = [None]

    def run():
        try:
            fn()
        except BaseException as exc:  # noqa: BLE001 - reported to the test
            box[0] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=5)
    return (not thread.is_alive()), box[0]


def test_fifo_is_refused_without_blocking(layout):
    root, _ = layout
    os.mkfifo(root / "p")
    done, error = _finishes(lambda: write_text_in_root(root, "p", "x"))
    assert done and isinstance(error, PathContainmentError)
    done, error = _finishes(lambda: read_text_in_root(root, "p"))
    assert done and isinstance(error, PathContainmentError)


def test_directory_target_is_refused(layout):
    root, _ = layout
    (root / "d").mkdir()
    with pytest.raises(PathContainmentError):
        write_text_in_root(root, "d", "x")


def test_contained_relative_path(layout):
    root, outside = layout
    (root / "a.py").write_text("", encoding="utf-8")
    (root / "in_link.py").symlink_to(root / "a.py")
    (root / "out_link.py").symlink_to(outside / "f.py")
    assert str(contained_relative_path(root, "a.py")) == "a.py"
    assert str(contained_relative_path(root, root / "a.py")) == "a.py"
    assert str(contained_relative_path(root, "in_link.py")) == "a.py"
    assert str(contained_relative_path(root, "sub/../a.py")) == "a.py"
    for bad in ("out_link.py", "../outside/f.py", str(outside / "f.py"), ".", str(root)):
        with pytest.raises(PathContainmentError):
            contained_relative_path(root, bad)


def test_root_given_through_a_symlink_still_works(layout, tmp_path):
    root, _ = layout
    alias = tmp_path / "alias"
    alias.symlink_to(root)
    write_text_in_root(alias, "a.txt", "ok")
    assert (root / "a.txt").read_text(encoding="utf-8") == "ok"
    assert str(contained_relative_path(alias, Path("a.txt"))) == "a.txt"
