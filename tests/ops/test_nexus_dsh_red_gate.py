from __future__ import annotations

import json
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-dsh-workflow"
guard = SourceFileLoader("nexus_dsh_workflow_red_test", str(SCRIPT)).load_module()

BUGGY = "SYNC_RUNTIME_TO_CURRENT_MAIN"
APP = """def derive(task_state, terminal):
    if task_state == "open":
        return "SAFE", "CONTINUE"
    if terminal:
        return "RECONCILE", "SYNC_RUNTIME_TO_CURRENT_MAIN"
    return "SAFE", "NO_PENDING_GATE"
"""
VALID_TEST = """from app import derive


def test_terminal_work_has_no_sync_gate():
    disposition, code = derive("closed", True)
    assert code != "SYNC_RUNTIME_TO_CURRENT_MAIN"
"""
WRONG_PRECONDITION = """from app import derive


def test_terminal_work_has_no_sync_gate():
    disposition, code = derive("open", True)
    assert disposition == "RECONCILE"
"""
BUGGY_ORACLE = """from app import derive


def test_terminal_work_has_no_sync_gate():
    disposition, code = derive("closed", True)
    assert code == "SYNC_RUNTIME_TO_CURRENT_MAIN"
"""
REGEX = "SYNC_RUNTIME_TO_CURRENT_MAIN"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    (path / "tests").mkdir(parents=True)
    (path / "app.py").write_text(APP, encoding="utf-8")
    (path / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (path / "tests" / "conftest.py").write_text(
        "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parents[1]))\n",
        encoding="utf-8",
    )
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@example.invalid")
    _git(path, "config", "user.name", "t")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base")
    return path


def _contract(**overrides: object) -> dict[str, object]:
    contract: dict[str, object] = {
        "schema": "nexus.dsh_red_contract.v1",
        "repository": "James3014/Nexus-new",
        "issue_number": 1599,
        "invariant": "terminal cross-repo work must not request runtime sync",
        "test_nodes": ["tests/test_red.py::test_terminal_work_has_no_sync_gate"],
        "expected_failure": {"kind": "assertion", "message_regex": REGEX},
        "forbidden_oracle_literals": [BUGGY],
        "test_path_globs": ["tests/**"],
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
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract or _contract()), encoding="utf-8")
    cmd = [
        sys.executable,
        str(SCRIPT),
        "red-gate",
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


def _write_test(repo: Path, text: str) -> None:
    (repo / "tests" / "test_red.py").write_text(text, encoding="utf-8")


def test_valid_red_is_ready_and_persisted(repo: Path, tmp_path: Path) -> None:
    # Terminal closed work currently returns the buggy gate, so `!=` fails
    # with the contracted signature.
    _write_test(repo, VALID_TEST)
    code, receipt = _gate(repo, tmp_path, state=True)
    assert code == 0, receipt
    assert receipt["decision"] == "RED_READY"
    assert receipt["red_semantics"] == "TARGET_DEFECT_REPRODUCED_BY_VALID_ORACLE"
    assert receipt["implementation_allowed"] is True
    assert receipt["reason_codes"] == []
    assert receipt["command"][1:3] == ["-m", "pytest"]
    assert receipt["changed_test_paths"] == ["tests/test_red.py"]
    _verify_hash(receipt)
    latest = tmp_path / "state" / "red-gates" / receipt["contract_hash"][7:] / "latest.json"
    assert json.loads(latest.read_text())["receipt_hash"] == receipt["receipt_hash"]


def test_missing_python_is_environment_failure(repo: Path, tmp_path: Path) -> None:
    _write_test(repo, VALID_TEST)
    code, receipt = _gate(repo, tmp_path, python=str(tmp_path / "nope" / "python"))
    assert code == 75
    assert "ENVIRONMENT_FAILURE" in receipt["reason_codes"]
    assert receipt["decision"] == "REVISE_RED"
    assert receipt["implementation_allowed"] is False


def test_wrong_precondition_is_unintended_failure(repo: Path, tmp_path: Path) -> None:
    _write_test(repo, WRONG_PRECONDITION)
    code, receipt = _gate(
        repo, tmp_path, _contract(expected_failure={"kind": "assertion", "message_regex": BUGGY})
    )
    assert code == 75
    assert receipt["reason_codes"] == ["UNINTENDED_FAILURE"]


def test_oracle_encoding_buggy_behavior(repo: Path, tmp_path: Path) -> None:
    _write_test(repo, BUGGY_ORACLE.replace("closed", "open"))
    code, receipt = _gate(repo, tmp_path)
    assert code == 75
    assert "ORACLE_ENCODES_BUGGY_BEHAVIOR" in receipt["reason_codes"]
    assert receipt["oracle_violations"][0]["literal"] == BUGGY


def test_duplicate_definitions(repo: Path, tmp_path: Path) -> None:
    _write_test(repo, VALID_TEST + "\n\n" + VALID_TEST.split("\n\n\n", 1)[1])
    code, receipt = _gate(repo, tmp_path)
    assert code == 75
    assert "DUPLICATE_TEST_DEFINITION" in receipt["reason_codes"]
    assert receipt["duplicate_definitions"][0]["name"] == "test_terminal_work_has_no_sync_gate"


def test_import_error_is_collection_failure(repo: Path, tmp_path: Path) -> None:
    _write_test(repo, "import module_that_does_not_exist\n" + VALID_TEST)
    code, receipt = _gate(repo, tmp_path)
    assert code == 75
    assert receipt["reason_codes"] == ["COLLECTION_OR_SETUP_FAILURE"]


def test_production_source_modified(repo: Path, tmp_path: Path) -> None:
    _write_test(repo, VALID_TEST)
    (repo / "app.py").write_text(APP.replace(BUGGY, "NO_PENDING_GATE"), encoding="utf-8")
    code, receipt = _gate(repo, tmp_path)
    assert code == 75
    assert "PRODUCTION_SOURCE_MODIFIED" in receipt["reason_codes"]
    assert "app.py" in receipt["changed_paths"]


def test_no_test_change_and_not_from_this_turn(repo: Path, tmp_path: Path) -> None:
    code, receipt = _gate(repo, tmp_path)
    assert code == 75
    assert {"NO_TEST_CHANGE", "RED_TEST_NOT_FROM_THIS_TURN"} <= set(receipt["reason_codes"])


def test_passing_test_is_no_red(repo: Path, tmp_path: Path) -> None:
    _write_test(repo, VALID_TEST.replace('derive("closed", True)', 'derive("closed", False)'))
    code, receipt = _gate(repo, tmp_path)
    assert code == 75
    assert receipt["reason_codes"] == ["NO_RED_OBSERVED"]


def test_unknown_node(repo: Path, tmp_path: Path) -> None:
    _write_test(repo, VALID_TEST)
    code, receipt = _gate(
        repo, tmp_path, _contract(test_nodes=["tests/test_red.py::test_does_not_exist"])
    )
    assert code == 75
    assert "TEST_NODE_NOT_FOUND" in receipt["reason_codes"]


def test_one_passing_node_among_failing(repo: Path, tmp_path: Path) -> None:
    _write_test(
        repo,
        VALID_TEST + "\n\ndef test_other():\n    assert derive('closed', False)[1] != 'x'\n",
    )
    nodes = [
        "tests/test_red.py::test_terminal_work_has_no_sync_gate",
        "tests/test_red.py::test_other",
    ]
    code, receipt = _gate(repo, tmp_path, _contract(test_nodes=nodes))
    assert code == 75
    assert receipt["reason_codes"] == ["NO_RED_OBSERVED"]


def test_dsh_1599_replay_reports_all_three_codes(repo: Path, tmp_path: Path) -> None:
    body = """from app import derive


def test_terminal_work_has_no_sync_gate():
    disposition, code = derive("open", True)
    assert disposition == "RECONCILE"
    assert code == "SYNC_RUNTIME_TO_CURRENT_MAIN"
"""
    _write_test(repo, body + "\n\n" + body.split("\n\n\n", 1)[1])
    code, receipt = _gate(repo, tmp_path)
    assert code == 75
    assert {
        "UNINTENDED_FAILURE",
        "ORACLE_ENCODES_BUGGY_BEHAVIOR",
        "DUPLICATE_TEST_DEFINITION",
    } <= set(receipt["reason_codes"])
    assert receipt["decision"] == "REVISE_RED"
    _verify_hash(receipt)


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema": "wrong"},
        {"test_nodes": []},
        {"unknown": 1},
        {"expected_failure": {"kind": "exception", "message_regex": "x"}},
        {"expected_failure": {"kind": "assertion", "message_regex": "("}},
    ],
)
def test_contract_validation_failure(
    repo: Path, tmp_path: Path, mutation: dict[str, object]
) -> None:
    _write_test(repo, VALID_TEST)
    code, receipt = _gate(repo, tmp_path, _contract(**mutation))
    assert code == 75
    assert receipt["reason_codes"] == ["RED_CONTRACT_INVALID"]
    assert receipt["implementation_allowed"] is False


def test_missing_contract_field_fails_closed(repo: Path, tmp_path: Path) -> None:
    contract = _contract()
    del contract["invariant"]
    code, receipt = _gate(repo, tmp_path, contract)
    assert code == 75
    assert receipt["reason_codes"] == ["RED_CONTRACT_INVALID"]


def _fake_python(tmp_path: Path, body: str) -> str:
    script = tmp_path / "fakepy"
    script.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    script.chmod(0o755)
    return str(script)


def test_pytest_not_importable_is_environment_failure(repo: Path, tmp_path: Path) -> None:
    _write_test(repo, VALID_TEST)
    fake = _fake_python(tmp_path, "echo '/x/python: No module named pytest' >&2\nexit 1")
    code, receipt = _gate(repo, tmp_path, python=fake)
    assert code == 75
    assert receipt["reason_codes"] == ["ENVIRONMENT_FAILURE"]


def test_missing_junit_is_collection_failure(repo: Path, tmp_path: Path) -> None:
    _write_test(repo, VALID_TEST)
    fake = _fake_python(tmp_path, "echo boom >&2\nexit 1")
    code, receipt = _gate(repo, tmp_path, python=fake)
    assert code == 75
    assert receipt["reason_codes"] == ["COLLECTION_OR_SETUP_FAILURE"]


def test_not_found_text_in_assertion_message_is_not_node_missing(
    repo: Path, tmp_path: Path
) -> None:
    _write_test(
        repo,
        VALID_TEST.replace(
            'assert code != "SYNC_RUNTIME_TO_CURRENT_MAIN"',
            'assert code != "SYNC_RUNTIME_TO_CURRENT_MAIN", "not found: thing"',
        ),
    )
    code, receipt = _gate(repo, tmp_path)
    assert code == 0, receipt


def test_missing_python_receipt_records_intended_argv(repo: Path, tmp_path: Path) -> None:
    _write_test(repo, VALID_TEST)
    python_path = str(tmp_path / "nope" / "python")
    code, receipt = _gate(repo, tmp_path, python=python_path)
    command = receipt.get("command", [])
    assert command[:6] == [python_path, "-m", "pytest", "-p", "no:cacheprovider", "-q"]
    assert command[-1:] == receipt["contract"]["test_nodes"]
