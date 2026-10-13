from __future__ import annotations

import json
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-dsh-workflow"
guard = SourceFileLoader("nexus_dsh_workflow_sidecar_cli_test", str(SCRIPT)).load_module()

APP_RED = """def derive(task_state, terminal):
    if task_state == "open":
        return "SAFE", "CONTINUE"
    if terminal:
        return "RECONCILE", "SYNC_RUNTIME_TO_CURRENT_MAIN"
    return "SAFE", "NO_PENDING_GATE"
"""
VALID_RED_TEST = """from app import derive


def test_terminal_work_has_no_sync_gate():
    disposition, code = derive("closed", True)
    assert code != "SYNC_RUNTIME_TO_CURRENT_MAIN"
"""
WRONG_RED_TEST = """from app import derive


def test_terminal_work_has_no_sync_gate():
    disposition, code = derive("open", True)
    assert disposition == "RECONCILE"
"""
RED_REGEX = "SYNC_RUNTIME_TO_CURRENT_MAIN"
RED_TARGET = "tests/test_red.py::test_terminal_work_has_no_sync_gate"

GREEN_TARGET = "tests/test_app.py::test_value_is_two"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _init_repo(path: Path, files: dict[str, str]) -> Path:
    path.mkdir(parents=True)
    for rel, text in files.items():
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@example.invalid")
    _git(path, "config", "user.name", "t")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base")
    return path


@pytest.fixture
def red_repo(tmp_path: Path) -> Path:
    return _init_repo(tmp_path / "red-repo", {"app.py": APP_RED, "tests/__init__.py": ""})


@pytest.fixture
def green_repo(tmp_path: Path) -> Path:
    return _init_repo(
        tmp_path / "green-repo",
        {
            "app.py": "def value():\n    return 1\n",
            "tests/__init__.py": "",
            "tests/conftest.py": (
                "import sys\nfrom pathlib import Path\n"
                "sys.path.insert(0, str(Path(__file__).parents[1]))\n"
            ),
            "tests/test_app.py": "from app import value\n\n\ndef test_value_is_two():\n    assert value() == 2\n",
            "tests/test_other.py": "from app import value\n\n\ndef test_value_is_int():\n    assert isinstance(value(), int)\n",
        },
    )


def _red_contract() -> dict[str, object]:
    return {
        "schema": "nexus.dsh_red_contract.v1",
        "repository": "James3014/Nexus-new",
        "issue_number": 1599,
        "invariant": "terminal cross-repo work must not request runtime sync",
        "test_nodes": [RED_TARGET],
        "expected_failure": {"kind": "assertion", "message_regex": RED_REGEX},
        "forbidden_oracle_literals": ["SYNC_RUNTIME_TO_CURRENT_MAIN"],
        "test_path_globs": ["tests/**"],
    }


def _green_contract() -> dict[str, object]:
    return {
        "schema": "nexus.dsh_green_contract.v1",
        "repository": "James3014/Nexus-new",
        "issue_number": 1617,
        "target_test_nodes": [GREEN_TARGET],
        "regression_pytest_targets": ["tests/test_other.py"],
        "allowed_change_globs": ["app.py", "tests/**"],
        "lint": {"ruff_check_paths_from_changes": True, "ruff_format_preview": True},
    }


def _run_cli(
    subcommand: str,
    repo: Path,
    tmp_path: Path,
    contract: dict[str, object],
    *,
    state_root: Path | None,
) -> tuple[int, dict[str, object]]:
    contract_path = tmp_path / f"{subcommand}-contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    argv = [
        sys.executable,
        str(SCRIPT),
        subcommand,
        "--repo-root",
        str(repo),
        "--base-revision",
        _git(repo, "rev-parse", "HEAD"),
        "--contract",
        str(contract_path),
        "--python",
        sys.executable,
        "--timeout",
        "120",
    ]
    if state_root is not None:
        argv += ["--state-root", str(state_root)]
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    return proc.returncode, json.loads(proc.stdout)


def _sidecar_blobs(state: Path) -> list[bytes]:
    return [
        p.read_bytes()
        for p in (state / "gate-sidecars").rglob("*")
        if p.is_file() and p.parent.name == "blobs"
    ]


def test_red_cli_ready_persists_recoverable_sidecar(red_repo: Path, tmp_path: Path) -> None:
    (red_repo / "tests" / "test_red.py").write_text(VALID_RED_TEST, encoding="utf-8")
    state = tmp_path / "state"

    code, receipt = _run_cli("red-gate", red_repo, tmp_path, _red_contract(), state_root=state)

    assert code == 0, receipt
    assert receipt["decision"] == "RED_READY"
    assert "receipt_path" in receipt
    guard.verify_gate_sidecar(state, receipt, gate="red")
    assert VALID_RED_TEST.encode() in _sidecar_blobs(state)


def test_green_cli_ready_persists_recoverable_sidecar(green_repo: Path, tmp_path: Path) -> None:
    (green_repo / "app.py").write_text("def value():\n    return 2\n", encoding="utf-8")
    state = tmp_path / "state"

    code, receipt = _run_cli(
        "green-gate", green_repo, tmp_path, _green_contract(), state_root=state
    )

    assert code == 0, receipt
    assert receipt["decision"] == "GREEN_READY"
    assert "receipt_path" in receipt
    guard.verify_gate_sidecar(state, receipt, gate="green")
    assert b"return 2" in b"".join(_sidecar_blobs(state))


def test_red_cli_sidecar_write_failure_is_structured_blocked(
    red_repo: Path, tmp_path: Path
) -> None:
    (red_repo / "tests" / "test_red.py").write_text(VALID_RED_TEST, encoding="utf-8")
    state = tmp_path / "state"
    state.mkdir()
    (state / "gate-sidecars").write_text("not a directory", encoding="utf-8")

    code, payload = _run_cli("red-gate", red_repo, tmp_path, _red_contract(), state_root=state)

    assert code == guard.EXIT_BLOCKED
    assert payload["decision"] == "REVISE_RED"
    assert "GATE_SIDECAR_WRITE_FAILED" in payload["reason_codes"]
    assert not (state / "red-gates").exists()


def test_green_cli_sidecar_write_failure_is_structured_blocked(
    green_repo: Path, tmp_path: Path
) -> None:
    (green_repo / "app.py").write_text("def value():\n    return 2\n", encoding="utf-8")
    state = tmp_path / "state"
    state.mkdir()
    (state / "gate-sidecars").write_text("not a directory", encoding="utf-8")

    code, payload = _run_cli(
        "green-gate", green_repo, tmp_path, _green_contract(), state_root=state
    )

    assert code == guard.EXIT_BLOCKED
    assert payload["decision"] == "REVISE_GREEN"
    assert "GATE_SIDECAR_WRITE_FAILED" in payload["reason_codes"]
    assert not (state / "green-gates").exists()


def test_red_cli_non_ready_writes_no_sidecar(red_repo: Path, tmp_path: Path) -> None:
    (red_repo / "tests" / "test_red.py").write_text(WRONG_RED_TEST, encoding="utf-8")
    state = tmp_path / "state"

    code, receipt = _run_cli("red-gate", red_repo, tmp_path, _red_contract(), state_root=state)

    assert code == guard.EXIT_BLOCKED
    assert receipt["decision"] != "RED_READY"
    assert "receipt_path" in receipt
    assert not (state / "gate-sidecars").exists()
