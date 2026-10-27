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
