import json
from pathlib import Path

from scripts.ops.build_test_impact_index import build_index, main


def test_build_index_maps_imported_source_to_test(tmp_path):
    source = tmp_path / "nexus" / "core"
    tests = tmp_path / "tests" / "core"
    source.mkdir(parents=True)
    tests.mkdir(parents=True)
    (tmp_path / "nexus" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "nexus" / "core" / "__init__.py").write_text("", encoding="utf-8")
    (source / "state.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tests / "test_state.py").write_text(
        "from nexus.core.state import VALUE\n\n"
        "def test_value():\n"
        "    assert VALUE == 1\n",
        encoding="utf-8",
    )

    index = build_index(root=tmp_path, source_roots=("nexus",), test_roots=("tests",))

    assert index["version"] == 1
    assert index["mappings"]["nexus/core/state.py"] == ["tests/core/test_state.py"]
    assert index["stats"]["mapped_source_files"] == 1


def test_build_index_cli_writes_json(tmp_path):
    (tmp_path / "nexus").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "nexus" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "nexus" / "thing.py").write_text("def ok(): return True\n", encoding="utf-8")
    (tmp_path / "tests" / "test_thing.py").write_text(
        "import nexus.thing\n\n"
        "def test_ok():\n"
        "    assert nexus.thing.ok()\n",
        encoding="utf-8",
    )
    out = tmp_path / ".nexus" / "test_impact_index.json"

    assert main(["--root", str(tmp_path), "--output", str(out)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["mappings"]["nexus/thing.py"] == ["tests/test_thing.py"]
