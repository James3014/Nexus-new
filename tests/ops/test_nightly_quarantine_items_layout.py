from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests import nightly_quarantine_items as package
from tests.nightly_quarantine import load_quarantine

PACKAGE_DIR = Path(package.__file__).resolve().parent


def _slug(file: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", file.removesuffix(".py").lower()).strip("_")


def _entry_modules() -> list[Path]:
    return package.discover(PACKAGE_DIR)


def _entry(path: Path) -> object:
    return package.load_entry(path)


def test_every_entry_module_is_named_after_its_test_file() -> None:
    modules = _entry_modules()
    assert modules
    for path in modules:
        entry = _entry(path)
        if entry is None:
            continue  # tombstone: the module name is the only record of the slug
        assert isinstance(entry, dict), path.name
        assert path.stem == _slug(str(entry["file"])), path.name


def test_tombstones_are_bare_none() -> None:
    for path in _entry_modules():
        source = path.read_text(encoding="utf-8")
        if _entry(path) is None:
            assert re.search(r"^ENTRY = None(\s+#.*)?$", source, re.M), path.name
            assert "ENTRY: dict" not in source and '"file"' not in source, path.name


def test_package_assembles_one_entry_per_module_in_sorted_order() -> None:
    names = [p.stem for p in _entry_modules()]
    assert names == sorted(names)
    live = [p.stem for p in _entry_modules() if _entry(p) is not None]
    assert [_slug(str(e["file"])) for e in package.QUARANTINE] == live
    assert len(load_quarantine()) == len(live)


def test_compat_shim_reexports_the_assembled_collection() -> None:
    from tests import nightly_quarantine_entries as shim

    assert shim.QUARANTINE is package.QUARANTINE


def _write_item(directory: Path, name: str, file: str) -> None:
    (directory / f"{name}.py").write_text(
        "ENTRY = {\n"
        f'    "file": "{file}",\n'
        '    "disposition": "quarantine",\n'
        '    "issue": "#1",\n'
        '    "cause": "c",\n'
        '    "tests": ("test_a",),\n'
        "}\n",
        encoding="utf-8",
    )


def test_assemble_ignores_stray_pyc(tmp_path: Path) -> None:
    _write_item(tmp_path, "tests_a", "tests/a.py")
    (tmp_path / "tests_b.pyc").write_bytes(b"\x00not python")
    (tmp_path / "tests_c.pyc").write_bytes(b"\x00not python")
    assert [e["file"] for e in package.assemble(tmp_path)] == ["tests/a.py"]


def test_assemble_ignores_subpackages(tmp_path: Path) -> None:
    _write_item(tmp_path, "tests_a", "tests/a.py")
    sub = tmp_path / "nested"
    sub.mkdir()
    (sub / "__init__.py").write_text("raise RuntimeError('must not import')\n", encoding="utf-8")
    _write_item(sub, "tests_z", "tests/z.py")
    assert [e["file"] for e in package.assemble(tmp_path)] == ["tests/a.py"]


def test_assemble_rejects_duplicate_file_values(tmp_path: Path) -> None:
    _write_item(tmp_path, "tests_a", "tests/a.py")
    _write_item(tmp_path, "tests_b", "tests/a.py")
    with pytest.raises(ValueError, match="duplicate quarantine item file"):
        package.assemble(tmp_path)


def test_assemble_skips_tombstones(tmp_path: Path) -> None:
    _write_item(tmp_path, "tests_a", "tests/a.py")
    (tmp_path / "tests_b.py").write_text("ENTRY = None  # retired\n", encoding="utf-8")
    assert [e["file"] for e in package.assemble(tmp_path)] == ["tests/a.py"]
