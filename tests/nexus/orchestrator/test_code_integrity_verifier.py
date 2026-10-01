from __future__ import annotations

from pathlib import Path

from nexus.orchestrator.code_integrity_verifier import run_code_integrity_v1


def test_code_integrity_passes_real_production_implementation(tmp_path: Path):
    source = tmp_path / "src" / "feature.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "def compute(value: int) -> int:\n    return value + 1\n",
        encoding="utf-8",
    )

    result = run_code_integrity_v1(
        tmp_path,
        changed_files=["src/feature.py"],
        untracked_files=[],
    )

    assert result.passed is True
    assert result.findings == ()
    assert result.production_paths == ("src/feature.py",)


def test_code_integrity_rejects_pass_and_ellipsis_stubs(tmp_path: Path):
    source = tmp_path / "src" / "feature.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "\n".join([
            "def first():",
            "    pass",
            "",
            "class Service:",
            "    def second(self):",
            '        """placeholder"""',
            "        ...",
            "",
        ]),
        encoding="utf-8",
    )

    result = run_code_integrity_v1(
        tmp_path,
        changed_files=["src/feature.py"],
        untracked_files=[],
    )

    codes = [finding.code for finding in result.findings]
    assert result.passed is False
    assert codes.count("OBVIOUS_IMPLEMENTATION_STUB") == 2


def test_code_integrity_rejects_executable_assert_true_but_not_fixture_text(tmp_path: Path):
    test_file = tmp_path / "tests" / "test_feature.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "\n".join([
            "FIXTURE = 'assert True'",
            "",
            "def test_feature():",
            "    assert True",
            "",
        ]),
        encoding="utf-8",
    )

    result = run_code_integrity_v1(
        tmp_path,
        changed_files=[],
        untracked_files=["tests/test_feature.py"],
    )

    codes = [finding.code for finding in result.findings]
    assert "TAUTOLOGICAL_TEST_ASSERT_TRUE" in codes
    assert "TEST_ONLY_REACHABILITY_UNPROVEN" in codes


def test_code_integrity_fixture_string_is_not_tautological_assertion(tmp_path: Path):
    source = tmp_path / "src" / "feature.py"
    source.parent.mkdir(parents=True)
    source.write_text("def compute():\n    return 1\n", encoding="utf-8")
    test_file = tmp_path / "tests" / "test_feature.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "FIXTURE = 'assert True'\n\ndef test_feature():\n    assert 1 == 1\n",
        encoding="utf-8",
    )

    result = run_code_integrity_v1(
        tmp_path,
        changed_files=["src/feature.py", "tests/test_feature.py"],
        untracked_files=[],
    )

    codes = [finding.code for finding in result.findings]
    assert "TAUTOLOGICAL_TEST_ASSERT_TRUE" not in codes
    assert "TEST_ONLY_REACHABILITY_UNPROVEN" not in codes
    assert result.passed is True


def test_code_integrity_test_only_accepts_traceable_repository_target_import(tmp_path: Path):
    source = tmp_path / "app" / "feature.py"
    source.parent.mkdir(parents=True)
    source.write_text("def compute():\n    return 1\n", encoding="utf-8")
    test_file = tmp_path / "tests" / "test_feature.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "from app.feature import compute\n\ndef test_feature():\n    assert compute() == 1\n",
        encoding="utf-8",
    )

    result = run_code_integrity_v1(
        tmp_path,
        changed_files=["tests/test_feature.py"],
        untracked_files=[],
    )

    assert result.passed is True
    assert result.target_references == ("app/feature.py",)
    assert "TEST_ONLY_REACHABILITY_UNPROVEN" not in {finding.code for finding in result.findings}


def test_code_integrity_skips_abstract_overload_and_protocol_declarations(tmp_path: Path):
    source = tmp_path / "src" / "contracts.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "\n".join([
            "from abc import ABC, abstractmethod",
            "from typing import Protocol, overload",
            "",
            "class Contract(ABC):",
            "    @abstractmethod",
            "    def run(self):",
            "        pass",
            "",
            "@overload",
            "def parse(value: int) -> int:",
            "    ...",
            "",
            "def parse(value):",
            "    return value",
            "",
            "class Port(Protocol):",
            "    def execute(self):",
            "        ...",
            "",
        ]),
        encoding="utf-8",
    )

    result = run_code_integrity_v1(
        tmp_path,
        changed_files=["src/contracts.py"],
        untracked_files=[],
    )

    assert result.passed is True
    assert result.findings == ()


def test_code_integrity_ignores_deleted_python_path(tmp_path: Path):
    result = run_code_integrity_v1(
        tmp_path,
        changed_files=["src/deleted.py"],
        untracked_files=[],
        deleted_files=["src/deleted.py"],
    )

    assert result.passed is True
    assert result.scanned_paths == ()
