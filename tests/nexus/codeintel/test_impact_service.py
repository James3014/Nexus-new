from pathlib import Path

from nexus.services.codeintel import analyze_impact


def test_analyze_impact_finds_reverse_imports(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "core.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    (package / "consumer.py").write_text("from pkg.core import run\n", encoding="utf-8")

    result = analyze_impact(tmp_path, ["pkg/core.py"])

    assert result.schema_version == "codeintel-v1"
    assert result.changed_files == ["pkg/core.py"]
    assert result.impacted_files == ["pkg/consumer.py", "pkg/core.py"]
    assert "pkg.consumer" in result.impacted_symbols
    assert "reverse_import_impact" in result.risk_reason


def test_analyze_impact_marks_missing_changed_file() -> None:
    result = analyze_impact(Path.cwd(), ["does/not/exist.py"])

    assert result.evidence_paths == []
    assert result.risk_reason == ["missing_changed_files"]


def test_analyze_impact_ignores_nexus_sandbox_cache(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    cache = tmp_path / ".nexus" / "reports" / "sandbox"
    cache.mkdir(parents=True)
    (cache / "consumer.py").write_text("import pkg.core\n", encoding="utf-8")

    result = analyze_impact(tmp_path, ["pkg/core.py"])

    assert result.impacted_files == ["pkg/core.py"]
