"""#3198: drone setup checks the drone id itself and refuses a link below the drone temp area.

The drone id names one directory under ``.nexus/tmp`` and one crystal file, so it must match the
CLI's pattern in the drone layer too. The drone root is created without following a link below
the temp area, and must resolve to exactly ``<temp area>/<drone id>``. Every "outside" directory
lives in ``tmp_path`` with sentinel content that must stay as it was. Nothing here needs a
sandbox, so the tests run the same on every host.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import nexus.core.contained_write as cw
import nexus.core.drone_engine as drone_engine
from nexus.core.contained_write import PathContainmentError
from nexus.core.drone_engine import TacticalDrone

_SENTINEL = "ORIGINAL\n"


class _NoModel:
    def ask_structured(self, messages):  # pragma: no cover - must never be reached
        raise AssertionError("model called for a refused drone setup")


class _DoneModel:
    def ask_structured(self, messages):
        return {"action": "DONE", "reasoning": "nothing to do"}


def _project(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "project"
    (project / ".nexus" / "tmp").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "victim.txt").write_text(_SENTINEL, encoding="utf-8")
    return project, outside


def _assert_outside_untouched(outside: Path) -> None:
    assert sorted(os.listdir(outside)) == ["victim.txt"]
    assert (outside / "victim.txt").read_text(encoding="utf-8") == _SENTINEL


def _run(project: Path, drone_id: str, model: object | None = None) -> dict:
    drone = TacticalDrone(drone_id, project)
    drone.local_brain = model or _NoModel()
    return drone.sense_think_act("edit victim.txt")


def test_a_drone_id_with_a_path_separator_under_a_linked_drone_dir_is_refused(tmp_path):
    # An earlier drone's dir became a link to an outside directory; an id that nests below it
    # would create (and then write) the new root out there.
    project, outside = _project(tmp_path)
    (project / ".nexus" / "tmp" / "drone-a").symlink_to(outside)

    result = _run(project, "drone-a/b")

    assert result["outcome"] == "FAIL"
    assert "drone_id_invalid" in result["error"]
    _assert_outside_untouched(outside)


@pytest.mark.parametrize(
    "drone_id", ["a/b", "../escaped", "..", ".hidden", "", "drone x", "x" * 65, "d\x00"]
)
def test_a_drone_id_outside_the_cli_pattern_is_refused_before_any_path_is_built(tmp_path, drone_id):
    project, outside = _project(tmp_path)

    result = _run(project, drone_id)

    assert result["outcome"] == "FAIL"
    assert "drone_id_invalid" in result["error"]
    assert os.listdir(project / ".nexus" / "tmp") == []
    # The FAIL crystal is named after the id too: none is written anywhere for a refused id.
    assert sorted(p.name for p in project.rglob("*_crystal.json")) == []
    assert not (project / ".nexus" / "escaped_crystal.json").exists()
    _assert_outside_untouched(outside)


@pytest.mark.parametrize("drone_id", ["d", "drone-1", "Drone_2.b-c", "x" * 64])
def test_a_drone_id_inside_the_cli_pattern_gets_its_root(tmp_path, drone_id):
    project, _ = _project(tmp_path)

    result = _run(project, drone_id, _DoneModel())

    # Setup passed: the drone reached the model (whose bare DONE is not accepted).
    assert result["outcome"] == "REPAIR_NEEDED"
    assert (project / ".nexus" / "tmp" / drone_id).is_dir()


def test_the_crystal_path_refuses_an_invalid_id():
    with pytest.raises(ValueError, match="drone_id_invalid"):
        TacticalDrone("../../escaped", Path(".")).crystal_path()


def test_a_drone_root_that_resolves_outside_the_temp_area_is_refused(tmp_path, monkeypatch):
    # The temp area is replaced by a link after the root was created and recorded: the recorded
    # root is no longer <temp area>/<id>, so setup refuses it.
    project, outside = _project(tmp_path)
    temp_area = project / ".nexus" / "tmp"
    real_box = drone_engine.DroneToolBox

    def box_then_move(path):
        box = real_box(path)
        temp_area.rename(temp_area.with_name("tmp-old"))
        (outside / "drone-x").mkdir()
        temp_area.symlink_to(outside)
        return box

    monkeypatch.setattr(drone_engine, "DroneToolBox", box_then_move)

    result = _run(project, "drone-x")

    assert result["outcome"] == "FAIL"
    assert "root_outside_temp_area" in result["error"]
    assert os.listdir(outside / "drone-x") == []


# --- make_dirs_in_root -------------------------------------------------------------------------


def test_make_dirs_in_root_creates_the_missing_levels(tmp_path):
    cw.make_dirs_in_root(tmp_path, "a/b/c")
    cw.make_dirs_in_root(tmp_path, "a/b/c")  # existing levels are kept

    assert (tmp_path / "a" / "b" / "c").is_dir()


@pytest.mark.parametrize("depth", ["first", "last"])
def test_make_dirs_in_root_refuses_a_link_below_the_root(tmp_path, depth):
    root = tmp_path / "root"
    (root / "a").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "victim.txt").write_text(_SENTINEL, encoding="utf-8")
    if depth == "first":
        (root / "a").rmdir()
        (root / "a").symlink_to(outside)
        relative = "a/b/c"
    else:
        (root / "a" / "b").symlink_to(outside)
        relative = "a/b"

    with pytest.raises(PathContainmentError, match="path_component_refused"):
        cw.make_dirs_in_root(root, relative)

    _assert_outside_untouched(outside)


def test_make_dirs_in_root_refuses_a_file_on_the_way(tmp_path):
    (tmp_path / "a").write_text("x", encoding="utf-8")

    with pytest.raises(PathContainmentError, match="path_component_refused"):
        cw.make_dirs_in_root(tmp_path, "a/b")


@pytest.mark.parametrize("relative", ["../x", "/abs", "a/../b", ""])
def test_make_dirs_in_root_refuses_a_path_that_is_not_plainly_relative(tmp_path, relative):
    with pytest.raises(PathContainmentError):
        cw.make_dirs_in_root(tmp_path, relative)
