from __future__ import annotations

from pathlib import Path

from nexus.services.codeintel.skeleton_provider import PythonCodeSkeletonProvider, lookup_implementation


def test_lookup_implementation_returns_exact_span_and_signature(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "core.py").write_text(
        "\n".join(
            [
                "class Worker:",
                "    \"\"\"Does work.\"\"\"",
                "    def run(self, item):",
                "        return helper(item)",
                "",
                "def helper(item):",
                "    return item + 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = PythonCodeSkeletonProvider(tmp_path).lookup_implementation("pkg.core.Worker.run")

    assert result.found is True
    assert result.reason == ""
    assert len(result.matches) == 1
    match = result.matches[0]
    assert match.file_path == "pkg/core.py"
    assert match.start_line == 3
    assert match.end_line == 4
    assert match.signature == "def run(self, item)"


def test_lookup_implementation_accepts_unqualified_symbol(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text("def target(value):\n    return value\n", encoding="utf-8")

    result = lookup_implementation(tmp_path, "target")

    assert result.found is True
    assert result.matches[0].symbol == "mod.target"
    assert result.matches[0].start_line == 1
    assert result.matches[0].end_line == 2


def test_lookup_implementation_returns_not_found(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")

    result = lookup_implementation(tmp_path, "missing")

    assert result.found is False
    assert result.reason == "symbol_not_found"
    assert result.matches == []
