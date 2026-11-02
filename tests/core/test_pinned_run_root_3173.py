"""#3173: a host write given the root identity recorded at setup lands in that directory or
nowhere.

Every "outside" directory lives in ``tmp_path`` and carries sentinel content; the tests check it
is left exactly as it was.
"""

from __future__ import annotations

import os

import pytest

from nexus.core.contained_write import PathContainmentError, root_identity, write_text_in_root


@pytest.fixture
def layout(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "f.txt").write_text("orig", encoding="utf-8")
    return root, outside


def test_a_write_with_the_recorded_identity_lands_in_the_root(layout):
    root, _ = layout
    pinned = root_identity(root)
    write_text_in_root(root, "sub/a.txt", "ok", create_parents=True, pinned_root=pinned)
    assert (root / "sub" / "a.txt").read_text(encoding="utf-8") == "ok"


def test_a_root_under_a_linked_parent_keeps_its_identity(layout, tmp_path):
    # Only the root's own entry is pinned: a link higher up (such as /tmp -> /private/tmp) is
    # part of the path every caller already uses and still resolves.
    root, _ = layout
    alias_parent = tmp_path / "alias-parent"
    alias_parent.symlink_to(root.parent)
    via_link = alias_parent / root.name
    pinned = root_identity(via_link)
    assert pinned == root_identity(root)
    write_text_in_root(via_link, "a.txt", "ok", pinned_root=pinned)
    assert (root / "a.txt").read_text(encoding="utf-8") == "ok"


def test_the_root_identity_is_only_taken_from_a_directory_itself(layout, tmp_path):
    root, _ = layout
    alias = tmp_path / "alias"
    alias.symlink_to(root)
    with pytest.raises(PathContainmentError, match="root_not_a_directory"):
        root_identity(alias)
    with pytest.raises(PathContainmentError, match="root_refused"):
        root_identity(tmp_path / "missing")


def test_a_host_write_after_the_root_became_a_link_stays_out_of_the_link_target(layout, tmp_path):
    root, outside = layout
    pinned = root_identity(root)
    root.rename(tmp_path / "moved")
    root.symlink_to(outside)

    with pytest.raises(PathContainmentError, match="root_replaced"):
        write_text_in_root(root, "f.txt", "changed", pinned_root=pinned)
    with pytest.raises(PathContainmentError, match="root_replaced"):
        write_text_in_root(root, "new.txt", "changed", pinned_root=pinned)
    assert sorted(os.listdir(outside)) == ["f.txt"]
    assert (outside / "f.txt").read_text(encoding="utf-8") == "orig"


def test_a_host_write_after_the_root_was_swapped_for_another_directory_writes_nothing(
    layout, tmp_path
):
    root, _ = layout
    pinned = root_identity(root)
    moved = tmp_path / "moved"
    root.rename(moved)
    root.mkdir()

    with pytest.raises(PathContainmentError, match="root_replaced"):
        write_text_in_root(root, "a.txt", "changed", pinned_root=pinned)
    assert os.listdir(root) == []
    assert os.listdir(moved) == []
