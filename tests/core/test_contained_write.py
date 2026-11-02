"""Host-side writes into a directory model output can also write stay inside it.

``nexus.core.contained_write`` opens the file relative to the root one component at a time
without following links, and only a regular single-link file is read or written.
"""

from __future__ import annotations

import os
import stat
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


def test_hard_link_unlinked_after_open_is_not_written(layout, monkeypatch):
    # The name in root is unlinked right after the host opens it, leaving the outside file
    # as the inode's only link: a check on the opened file would then pass.
    root, outside = layout
    os.link(outside / "f.py", root / "h.py")
    real_open = os.open

    def open_then_unlink(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if os.fspath(path) == "h.py":
            os.unlink(root / "h.py")
        return fd

    monkeypatch.setattr(os, "open", open_then_unlink)
    try:
        write_text_in_root(root, "h.py", "pwn")
    except PathContainmentError:
        pass
    monkeypatch.undo()
    assert (outside / "f.py").read_text(encoding="utf-8") == "orig"


def _stat_raced(monkeypatch, name: str, result):
    real_stat = os.stat

    def raced(path, *args, **kwargs):
        if os.fspath(path) == name and kwargs.get("dir_fd") is not None:
            if isinstance(result, BaseException):
                raise result
            return result
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", raced)


def test_hard_link_swapped_in_after_the_check_is_replaced_not_written(layout, monkeypatch):
    root, outside = layout
    os.link(outside / "f.py", root / "h.py")
    _stat_raced(monkeypatch, "h.py", os.stat(__file__))  # the check saw a plain file
    write_text_in_root(root, "h.py", "new")
    monkeypatch.undo()
    assert (outside / "f.py").read_text(encoding="utf-8") == "orig"
    assert (root / "h.py").read_text(encoding="utf-8") == "new"
    assert os.stat(root / "h.py").st_ino != os.stat(outside / "f.py").st_ino


def test_link_swapped_in_after_the_check_is_replaced_not_followed(layout, monkeypatch):
    root, outside = layout
    (root / "link.py").symlink_to(outside / "f.py")
    _stat_raced(monkeypatch, "link.py", FileNotFoundError("raced"))
    write_text_in_root(root, "link.py", "new")
    monkeypatch.undo()
    assert (outside / "f.py").read_text(encoding="utf-8") == "orig"
    assert not (root / "link.py").is_symlink()
    assert (root / "link.py").read_text(encoding="utf-8") == "new"


def test_write_keeps_the_mode_and_leaves_no_temp_file(layout):
    root, _ = layout
    (root / "run.sh").write_text("old", encoding="utf-8")
    os.chmod(root / "run.sh", 0o750)
    write_text_in_root(root, "run.sh", "new")
    assert (root / "run.sh").read_text(encoding="utf-8") == "new"
    assert stat.S_IMODE(os.stat(root / "run.sh").st_mode) == 0o750
    assert sorted(p.name for p in root.iterdir()) == ["run.sh"]


def test_write_does_not_carry_over_special_mode_bits(layout):
    root, _ = layout
    (root / "tool").write_text("old", encoding="utf-8")
    os.chmod(root / "tool", 0o4755)
    write_text_in_root(root, "tool", "new")
    assert stat.S_IMODE(os.stat(root / "tool").st_mode) == 0o755


def test_failed_replace_keeps_the_old_file_and_removes_the_temp_file(layout, monkeypatch):
    root, _ = layout
    (root / "a.py").write_text("old", encoding="utf-8")

    def no_rename(*args, **kwargs):
        raise OSError("rename failed")

    monkeypatch.setattr(os, "rename", no_rename)
    with pytest.raises(PathContainmentError):
        write_text_in_root(root, "a.py", "new")
    monkeypatch.undo()
    assert (root / "a.py").read_text(encoding="utf-8") == "old"
    assert sorted(p.name for p in root.iterdir()) == ["a.py"]


# The host runs git and the task interpreter in the work dir after model code (#2945, #3024):
# model-driven writes may not land in .git or .venv, in any spelling, at any depth.
@pytest.mark.parametrize(
    "relative",
    [
        ".git/config",
        ".git/hooks/post-checkout",
        ".git",
        ".venv/lib/site-packages/helper.py",
        ".venv/bin/python3",
        ".venv",
        ".GIT/config",
        ".Git/hooks/pre-commit",
        ".VENV/bin/python3",
        ".g\u200cit/config",  # U+200C ZERO WIDTH NON-JOINER, skipped by HFS+
        "sub/.git/config",
        "pkg/.venv/bin/python3",
    ],
)
def test_host_run_subtrees_are_refused(layout, relative):
    root, _ = layout
    with pytest.raises(PathContainmentError):
        write_text_in_root(root, relative, "x = 1\n", create_parents=True)
    assert sorted(p.name for p in root.iterdir()) == []


def test_host_run_subtree_refused_even_when_it_exists(layout):
    root, _ = layout
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("orig", encoding="utf-8")
    (root / ".venv" / "lib").mkdir(parents=True)
    (root / ".venv" / "lib" / "helper.py").write_text("orig", encoding="utf-8")
    for relative in (".git/config", ".venv/lib/helper.py"):
        with pytest.raises(PathContainmentError):
            write_text_in_root(root, relative, "changed")
        assert (root / relative).read_text(encoding="utf-8") == "orig"


@pytest.mark.parametrize(
    "relative", [".gitignore", ".github/workflows/ci.yml", "git/x.py", "venv.py"]
)
def test_names_near_host_run_subtrees_still_write(layout, relative):
    root, _ = layout
    write_text_in_root(root, relative, "ok", create_parents=True)
    assert (root / relative).read_text(encoding="utf-8") == "ok"


def test_model_sandbox_keeps_the_same_subtrees_read_only(tmp_path, monkeypatch):
    # One list for both barriers: what the sandbox keeps read-only is exactly what the host-side
    # writer refuses.
    from nexus.core.contained_write import HOST_RUN_SUBTREES
    from nexus.engine import model_output_sandbox

    assert {".git", ".venv"} <= set(HOST_RUN_SUBTREES)
    seen: dict = {}

    class _Bound:
        profile = "(version 1)"
        env: dict = {}

    def fake_confinement(**kwargs):
        seen.update(kwargs)
        return _Bound()

    monkeypatch.setattr(model_output_sandbox, "confinement", fake_confinement)
    monkeypatch.setattr(model_output_sandbox, "developer_toolchain_read_roots", lambda: ())
    work = tmp_path / "work"
    work.mkdir()
    with model_output_sandbox.model_sandbox(work):
        pass
    expected = {str(work.resolve() / name) for name in HOST_RUN_SUBTREES}
    assert set(seen["read_only_paths"]) == expected
    for name in HOST_RUN_SUBTREES:
        with pytest.raises(PathContainmentError):
            write_text_in_root(work, f"{name}/x", "x", create_parents=True)


def test_tree_copy_skips_ignored_names_under_any_letter_case(tmp_path):
    # The case variants are separate entries, so this holds on case-sensitive Linux as well as
    # on a case-insensitive macOS volume, where ".Git" is the ".git" directory.
    from nexus.core.contained_write import copy_tree_in_root

    src = tmp_path / "src"
    (src / "a" / ".Git").mkdir(parents=True)
    (src / "a" / ".Git" / "config").write_text("[core]\n", encoding="utf-8")
    (src / "b").mkdir()
    (src / "b" / ".GIT").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    (src / "keep.py").write_text("x = 1\n", encoding="utf-8")
    dst = tmp_path / "dst"
    dst.mkdir()

    copy_tree_in_root(src, dst, ignore_names={".git"})

    assert (dst / "keep.py").read_text(encoding="utf-8") == "x = 1\n"
    copied = {name.casefold() for _, dirs, files in os.walk(dst) for name in (*dirs, *files)}
    assert ".git" not in copied
