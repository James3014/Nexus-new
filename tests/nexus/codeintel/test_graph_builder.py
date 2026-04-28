import json
from pathlib import Path

from nexus.services.codeintel.graph_builder import build_graph, scan_codebase


def test_build_graph_records_python_import_edges(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("import pkg.core\n", encoding="utf-8")

    graph = build_graph(tmp_path)

    assert {"id": "pkg.core", "type": "python_module", "path": "pkg/core.py"} in graph["nodes"]
    assert {"from": "pkg.consumer", "to": "pkg.core", "type": "imports"} in graph["edges"]


def test_scan_codebase_writes_index_and_ignores_nexus_cache(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    cache = tmp_path / ".nexus" / "reports"
    cache.mkdir(parents=True)
    (cache / "ignored.py").write_text("VALUE = 2\n", encoding="utf-8")

    index_path = tmp_path / "graph.json"
    result = scan_codebase(tmp_path, index_path=index_path)
    graph = json.loads(index_path.read_text(encoding="utf-8"))

    assert result.schema_version == "codeintel-v1"
    assert result.nodes_count == 1
    assert result.index_path == str(index_path)
    assert [node["path"] for node in graph["nodes"]] == ["pkg/core.py"]
