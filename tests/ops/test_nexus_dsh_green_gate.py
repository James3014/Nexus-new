from __future__ import annotations

import json
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-dsh-workflow"
guard = SourceFileLoader("nexus_dsh_workflow_green_test", str(SCRIPT)).load_module()

TARGET = "tests/test_app.py::test_value_is_two"
FIXED = "def value():\n    return 2\n"
# Stable under plain `ruff format`, but `--preview` splits the leading call of
# a method chain onto its own line.
PREVIEW_ONLY = (
    FIXED
    + """

def unused(session, model):
    return (
        session.query(model.id)
        .filter(model.account_id == 10000, model.email == "someone@example.invalid")
        .count()
    )
"""
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    (path / "tests").mkdir(parents=True)
    (path / "app.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    (path / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (path / "tests" / "conftest.py").write_text(
        "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parents[1]))\n",
        encoding="utf-8",
    )
    (path / "tests" / "test_app.py").write_text(
        "from app import value\n\n\ndef test_value_is_two():\n    assert value() == 2\n",
        encoding="utf-8",
    )
    (path / "tests" / "test_other.py").write_text(
        "from app import value\n\n\ndef test_value_is_int():\n    assert isinstance(value(), int)\n",
        encoding="utf-8",
    )
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@example.invalid")
    _git(path, "config", "user.name", "t")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base")
    return path


def _fix(repo: Path, body: str = FIXED) -> None:
    (repo / "app.py").write_text(body, encoding="utf-8")


def _no_lint() -> dict[str, bool]:
    return {"ruff_check_paths_from_changes": False, "ruff_format_preview": False}


def _contract(**overrides: object) -> dict[str, object]:
    contract: dict[str, object] = {
        "schema": "nexus.dsh_green_contract.v1",
        "repository": "James3014/Nexus-new",
        "issue_number": 1617,
        "target_test_nodes": [TARGET],
        "regression_pytest_targets": ["tests/test_other.py"],
        "allowed_change_globs": ["app.py", "tests/**"],
        "lint": {"ruff_check_paths_from_changes": True, "ruff_format_preview": True},
    }
    contract.update(overrides)
    return contract


def _gate(
    repo: Path,
    tmp_path: Path,
    contract: dict[str, object] | None = None,
    *,
    python: str = sys.executable,
    state: bool = False,
) -> tuple[int, dict[str, object]]:
    contract_path = tmp_path / "green-contract.json"
    contract_path.write_text(json.dumps(contract or _contract()), encoding="utf-8")
    cmd = [
        sys.executable,
        str(SCRIPT),
        "green-gate",
        "--repo-root",
        str(repo),
        "--base-revision",
        _git(repo, "rev-parse", "HEAD"),
        "--contract",
        str(contract_path),
        "--python",
        python,
        "--timeout",
        "120",
    ]
    if state:
        cmd += ["--state-root", str(tmp_path / "state")]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return proc.returncode, json.loads(proc.stdout)


def _verify_hash(receipt: dict[str, object]) -> None:
    body = {k: v for k, v in receipt.items() if k not in {"receipt_hash", "receipt_path"}}
    assert receipt["receipt_hash"] == guard._sha256_bytes(guard._canonical_json(body).encode())


def test_green_ready_and_persisted(repo: Path, tmp_path: Path) -> None:
    _fix(repo)
    code, receipt = _gate(repo, tmp_path, state=True)
    assert code == 0, receipt
    assert receipt["decision"] == "GREEN_READY"
    assert receipt["green_semantics"] == "TARGET_FIXED_REGRESSIONS_CLEAN_SCOPE_CLEAN"
    assert receipt["claim_ceiling"] == "POST_IMPLEMENTATION_EVIDENCE_GATE_NO_COMPLETION_AUTHORITY"
    assert receipt["schema"] == "nexus.dsh_green_gate_receipt.v1"
    assert receipt["reason_codes"] == []
    assert receipt["changed_paths"] == ["app.py"]
    assert receipt["node_results"][0]["outcome"] == "passed"
    exit_codes = receipt["exit_codes"]
    assert exit_codes["target_tests"] == 0
    assert exit_codes["regression_tests"] == 0
    assert exit_codes["ruff_check"] == 0
    assert exit_codes["ruff_format"] == 0
    assert "--preview" in receipt["commands"]["ruff_format"]
    assert str(receipt["worktree_diff_sha256"]).startswith("sha256:")
    _verify_hash(receipt)
    persisted = Path(str(receipt["receipt_path"]))
    assert persisted.is_file()
    stored = json.loads(persisted.read_text(encoding="utf-8"))
    assert stored["receipt_hash"] == receipt["receipt_hash"]
    assert persisted.parent.parent.name == "green-gates"
    assert not (repo / ".ruff_cache").exists()


def test_untracked_scratch_file_blocks(repo: Path, tmp_path: Path) -> None:
    _fix(repo)
    (repo / "fix.py").write_text("x = 1\n", encoding="utf-8")
    code, receipt = _gate(repo, tmp_path)
    assert code == guard.EXIT_BLOCKED
    assert receipt["decision"] == "REVISE_GREEN"
    assert receipt["reason_codes"] == ["UNTRACKED_FILE_OUTSIDE_ALLOWED_GLOBS"]
    assert receipt["untracked_outside_allowed_globs"] == ["fix.py"]


def test_tracked_change_outside_globs_blocks(repo: Path, tmp_path: Path) -> None:
    _fix(repo)
    (repo / "tests" / "__init__.py").write_text("# touched\n", encoding="utf-8")
    code, receipt = _gate(repo, tmp_path, _contract(allowed_change_globs=["app.py"]))
    assert code == guard.EXIT_BLOCKED
    assert receipt["reason_codes"] == ["CHANGE_OUTSIDE_ALLOWED_GLOBS"]
    assert receipt["paths_outside_allowed_globs"] == ["tests/__init__.py"]


def test_failing_target_blocks(repo: Path, tmp_path: Path) -> None:
    _fix(repo, "def value():\n    return 3\n")
    code, receipt = _gate(repo, tmp_path)
    assert code == guard.EXIT_BLOCKED
    assert "TARGET_TESTS_NOT_PASSING" in receipt["reason_codes"]
    assert receipt["node_results"][0]["outcome"] == "failed"


def test_failing_regression_blocks(repo: Path, tmp_path: Path) -> None:
    # The target now passes against a str result, but the regression test
    # (value must be an int) fails.
    _fix(repo, 'def value():\n    return "2"\n')
    (repo / "tests" / "test_app.py").write_text(
        'from app import value\n\n\ndef test_value_is_two():\n    assert value() == "2"\n',
        encoding="utf-8",
    )
    code, receipt = _gate(repo, tmp_path)
    assert code == guard.EXIT_BLOCKED
    assert receipt["reason_codes"] == ["REGRESSION_TESTS_FAILING"]
    assert receipt["regression_failures"][0]["name"] == "test_value_is_int"


def test_non_preview_format_violation_blocks(repo: Path, tmp_path: Path) -> None:
    _fix(repo, PREVIEW_ONLY)
    ruff = [sys.executable, "-m", "ruff", "format", "--check", "--no-cache", "app.py"]
    plain = subprocess.run(ruff, cwd=repo, capture_output=True, check=False)
    preview = subprocess.run(
        [*ruff[:5], "--preview", *ruff[5:]], cwd=repo, capture_output=True, check=False
    )
    if not (plain.returncode == 0 and preview.returncode == 1):
        pytest.skip("installed ruff does not distinguish preview formatting for this sample")
    code, receipt = _gate(repo, tmp_path)
    assert code == guard.EXIT_BLOCKED
    assert receipt["reason_codes"] == ["FORMAT_FAILURE"]


def test_lint_violation_blocks(repo: Path, tmp_path: Path) -> None:
    _fix(repo, "import os\n\n\ndef value():\n    return 2\n")
    code, receipt = _gate(repo, tmp_path)
    assert code == guard.EXIT_BLOCKED
    assert receipt["reason_codes"] == ["LINT_FAILURE"]
    assert "F401" in receipt["lint_output"]["ruff_check"]


def test_missing_python_is_environment_failure(repo: Path, tmp_path: Path) -> None:
    _fix(repo)
    code, receipt = _gate(repo, tmp_path, python=str(tmp_path / "no-such-python"))
    assert code == guard.EXIT_BLOCKED
    assert "ENVIRONMENT_FAILURE" in receipt["reason_codes"]


def test_diff_check_trailing_whitespace_blocks(repo: Path, tmp_path: Path) -> None:
    _fix(repo, "def value():\n    return 2  \n")
    code, receipt = _gate(repo, tmp_path, _contract(lint=_no_lint()))
    assert code == guard.EXIT_BLOCKED
    assert receipt["reason_codes"] == ["DIFF_CHECK_FAILURE"]


def test_untracked_allowed_file_whitespace_blocks(repo: Path, tmp_path: Path) -> None:
    _fix(repo)
    (repo / "tests" / "test_new.py").write_text("X = 1  \n", encoding="utf-8")
    code, receipt = _gate(repo, tmp_path, _contract(lint=_no_lint()))
    assert code == guard.EXIT_BLOCKED
    assert "DIFF_CHECK_FAILURE" in receipt["reason_codes"]


def test_no_change_blocks(repo: Path, tmp_path: Path) -> None:
    code, receipt = _gate(repo, tmp_path)
    assert code == guard.EXIT_BLOCKED
    assert "NO_CHANGE" in receipt["reason_codes"]
    assert "TARGET_TESTS_NOT_PASSING" in receipt["reason_codes"]


def test_missing_target_node_blocks(repo: Path, tmp_path: Path) -> None:
    _fix(repo)
    contract = _contract(target_test_nodes=["tests/test_app.py::test_absent"])
    code, receipt = _gate(repo, tmp_path, contract)
    assert code == guard.EXIT_BLOCKED
    assert "TEST_NODE_NOT_FOUND" in receipt["reason_codes"]


def test_extensionless_python_script_is_linted(repo: Path, tmp_path: Path) -> None:
    _fix(repo)
    script = repo / "scripts" / "tool"
    script.parent.mkdir()
    script.write_text("#!/usr/bin/env python3\nimport os\n", encoding="utf-8")
    code, receipt = _gate(repo, tmp_path, _contract(allowed_change_globs=["app.py", "scripts/*"]))
    assert code == guard.EXIT_BLOCKED
    assert "LINT_FAILURE" in receipt["reason_codes"]


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema": "nexus.dsh_green_contract.v0"},
        {"extra": 1},
        {"target_test_nodes": []},
        {"regression_pytest_targets": "tests"},
        {"allowed_change_globs": []},
        {"lint": {"ruff_check_paths_from_changes": True}},
        {"lint": {"ruff_check_paths_from_changes": 1, "ruff_format_preview": True}},
        {"issue_number": True},
    ],
)
def test_invalid_contract_fails_closed(repo: Path, tmp_path: Path, mutation: dict) -> None:
    _fix(repo)
    code, receipt = _gate(repo, tmp_path, _contract(**mutation))
    assert code == guard.EXIT_BLOCKED
    assert receipt["decision"] == "REVISE_GREEN"
    assert receipt["reason_codes"] == ["GREEN_CONTRACT_INVALID"]
