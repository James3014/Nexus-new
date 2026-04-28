import json
from pathlib import Path

from nexus.services.codeintel.context_service import context_for_symbol
from nexus.services.codeintel.graph_builder import scan_codebase


def test_context_for_symbol_reports_callers_and_callees(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "core.py").write_text("import pkg.util\n", encoding="utf-8")
    (package / "consumer.py").write_text("import pkg.core\n", encoding="utf-8")
    (package / "util.py").write_text("VALUE = 1\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_core.py").write_text("import pkg.core\n", encoding="utf-8")
    index_path = tmp_path / "graph.json"
    scan_codebase(tmp_path, index_path=index_path)

    result = context_for_symbol(tmp_path, "pkg.core", index_path=index_path)

    assert result.found is True
    assert result.files == ["pkg/core.py"]
    assert result.callers == ["pkg.consumer", "tests.test_core"]
    assert result.callees == ["pkg.util"]
    assert result.related_tests == ["tests/test_core.py"]


def test_context_for_symbol_returns_not_found(tmp_path: Path) -> None:
    graph = tmp_path / "graph.json"
    graph.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")

    result = context_for_symbol(tmp_path, "missing.symbol", index_path=graph)

    assert result.found is False
    assert result.reason == "symbol_not_found"
