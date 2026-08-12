from pathlib import Path

import pytest

from nexus.services.local_heal.world_c_receipt import (
    build_world_c_canonical_patch_projection,
)


def test_canonical_patch_projection_rebuilds_deterministic_diff(tmp_path: Path) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    (source / "module.py").write_text("value = 1\n", encoding="utf-8")
    (workspace / "module.py").write_text("value = 2\n", encoding="utf-8")

    first = build_world_c_canonical_patch_projection(source, workspace, "module.py")
    second = build_world_c_canonical_patch_projection(source, workspace, "module.py")

    assert first["valid"] is True
    assert first["patch"] == second["patch"]
    assert first["patch_hash"] == second["patch_hash"]
    assert "-value = 1" in first["patch"]
    assert "+value = 2" in first["patch"]


@pytest.mark.parametrize("relative_path", ("../module.py", "/module.py"))
def test_canonical_patch_projection_rejects_path_escape(tmp_path: Path, relative_path: str) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()

    with pytest.raises(ValueError, match="path"):
        build_world_c_canonical_patch_projection(source, workspace, relative_path)


def test_canonical_patch_projection_rejects_stale_source_hash(tmp_path: Path) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    (source / "module.py").write_text("value = 1\n", encoding="utf-8")
    (workspace / "module.py").write_text("value = 2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="source hash"):
        build_world_c_canonical_patch_projection(
            source, workspace, "module.py", expected_source_hash="sha256:stale"
        )


def test_canonical_patch_projection_rejects_workspace_substitution(tmp_path: Path) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    (source / "module.py").write_text("value = 1\n", encoding="utf-8")
    target = workspace / "module.py"
    target.write_text("value = 2\n", encoding="utf-8")
    expected = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="workspace hash"):
        build_world_c_canonical_patch_projection(
            source, workspace, "module.py", expected_workspace_hash=expected
        )


def test_canonical_patch_projection_rejects_tampered_patch_hash(tmp_path: Path) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    (source / "module.py").write_text("value = 1\n", encoding="utf-8")
    (workspace / "module.py").write_text("value = 2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="patch hash"):
        build_world_c_canonical_patch_projection(
            source, workspace, "module.py", expected_patch_hash="sha256:" + "0" * 64
        )


@pytest.mark.parametrize("symlink_root", ("source", "workspace"))
def test_canonical_patch_projection_rejects_symlinked_root(
    tmp_path: Path, symlink_root: str
) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "module.py").write_text("value = 1\n", encoding="utf-8")
    link = tmp_path / f"{symlink_root}-link"
    link.symlink_to(outside, target_is_directory=True)
    roots = (link, workspace) if symlink_root == "source" else (source, link)

    with pytest.raises(ValueError, match="roots must not be symlinks"):
        build_world_c_canonical_patch_projection(*roots, "module.py")
