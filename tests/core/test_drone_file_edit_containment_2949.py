"""#2949: DroneToolBox.file_edit keeps model-chosen targets inside the drone's own dir.

The old string-prefix check let ``../<dir>EXTRA/x.txt`` through, because the sibling's path
starts with the drone dir's path.
"""

from __future__ import annotations

from nexus.core.drone_engine import DroneToolBox


def _box(tmp_path):
    drone = tmp_path / "drone1"
    drone.mkdir()
    return drone, DroneToolBox(drone)


def test_sibling_dir_sharing_the_name_prefix_is_blocked(tmp_path):
    drone, box = _box(tmp_path)
    out = box.file_edit("../drone1EXTRA/x.txt", "pwn")
    assert out == {"status": "FAIL", "error": "Path traversal blocked"}
    assert not (tmp_path / "drone1EXTRA").exists()


def test_parent_dir_target_is_blocked(tmp_path):
    _, box = _box(tmp_path)
    assert box.file_edit("../outside.txt", "pwn")["status"] == "FAIL"
    assert not (tmp_path / "outside.txt").exists()


def test_symlink_out_of_the_dir_is_blocked(tmp_path):
    drone, box = _box(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (drone / "link").symlink_to(outside)
    assert box.file_edit("link/x.txt", "pwn")["status"] == "FAIL"
    assert not (outside / "x.txt").exists()


def test_target_inside_the_dir_is_written(tmp_path):
    drone, box = _box(tmp_path)
    assert box.file_edit("sub/x.txt", "ok") == {"status": "SUCCESS"}
    assert (drone / "sub" / "x.txt").read_text(encoding="utf-8") == "ok"


def test_link_swapped_in_after_the_check_is_not_followed(tmp_path, monkeypatch):
    # A sandboxed BASH child that outlives its command can swap a link in between the check and
    # the write. Simulate the check seeing the pre-swap state: resolve() follows nothing.
    import os
    from pathlib import Path

    drone, box = _box(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "f").write_text("orig", encoding="utf-8")
    (drone / "a").symlink_to(outside)
    (drone / "x").symlink_to(outside / "f")
    monkeypatch.setattr(Path, "resolve", lambda self, strict=False: Path(os.path.abspath(self)))

    assert box.file_edit("a/y.txt", "pwn")["status"] == "FAIL"
    assert box.file_edit("x", "pwn")["status"] == "FAIL"
    assert not (outside / "y.txt").exists()
    assert (outside / "f").read_text(encoding="utf-8") == "orig"


def test_fifo_target_fails_without_blocking(tmp_path):
    import os
    import threading

    drone, box = _box(tmp_path)
    os.mkfifo(drone / "p")
    out: list = []
    thread = threading.Thread(target=lambda: out.append(box.file_edit("p", "x")), daemon=True)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert out[0]["status"] == "FAIL"


def test_hard_linked_target_is_not_written(tmp_path):
    import os

    drone, box = _box(tmp_path)
    outside = tmp_path / "f"
    outside.write_text("orig", encoding="utf-8")
    os.link(outside, drone / "h")
    assert box.file_edit("h", "pwn")["status"] == "FAIL"
    assert outside.read_text(encoding="utf-8") == "orig"


def test_existing_file_inside_the_dir_is_overwritten(tmp_path):
    drone, box = _box(tmp_path)
    (drone / "x.txt").write_text("old and longer", encoding="utf-8")
    assert box.file_edit("x.txt", "new") == {"status": "SUCCESS"}
    assert (drone / "x.txt").read_text(encoding="utf-8") == "new"
