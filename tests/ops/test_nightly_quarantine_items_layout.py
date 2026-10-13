from __future__ import annotations

import re
from pathlib import Path

from tests import nightly_quarantine_items as package
from tests.nightly_quarantine import load_quarantine

PACKAGE_DIR = Path(package.__file__).resolve().parent


def _slug(file: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", file.removesuffix(".py").lower()).strip("_")


def _entry_modules() -> list[Path]:
    return sorted(p for p in PACKAGE_DIR.glob("*.py") if not p.name.startswith("_"))


def _entry(path: Path) -> object:
    return __import__(f"{package.__name__}.{path.stem}", fromlist=["ENTRY"]).ENTRY


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
