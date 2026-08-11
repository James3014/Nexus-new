from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from nexus.services.local_heal.isolated_verifier import (
    IsolatedVerifierReceipt,
    IsolatedVerifierRequest,
    compute_semantic_correctness,
    run_isolated_verifier,
)
from nexus.services.local_heal.phases import verification


@dataclass(frozen=True)
class _Case:
    frozen: verification.FrozenOracleIdentity
    base_request: IsolatedVerifierRequest
    candidate_request: IsolatedVerifierRequest
    material: verification.OracleMaterialPaths


def _case(
    tmp_path: Path,
    *,
    base_state: str = "buggy",
    candidate_state: str = "fixed",
) -> _Case:
    material_dir = tmp_path / "material"
    material_dir.mkdir()
    oracle_path = material_dir / "oracle.py"
    source_path = material_dir / "source.txt"
    suite_path = material_dir / "suite.txt"
    for path, content in (
        (
            oracle_path,
            "from pathlib import Path\n"
            "raise SystemExit(0 if Path('state.txt').read_text() == 'fixed' else 7)\n",
        ),
        (source_path, "physical-reproduction"),
        (suite_path, "verified-repair-suite"),
    ):
        path.write_text(content, encoding="utf-8")

    base_workspace, candidate_workspace = tmp_path / "base", tmp_path / "candidate"
    for workspace, state in (
        (base_workspace, base_state),
        (candidate_workspace, candidate_state),
    ):
        workspace.mkdir()
        (workspace / "state.txt").write_text(state, encoding="utf-8")

    command = (
        str(Path(sys.executable).resolve(strict=True)),
        str(oracle_path.resolve(strict=True)),
        "literal-arg",
    )
    material = verification.OracleMaterialPaths(oracle_path, source_path, suite_path)
    request = {
        "verifier_command": command,
        "verifier_allowed": True,
    }
    return _Case(
        verification.freeze_oracle_identity(command=command, material=material),
        IsolatedVerifierRequest(task_id="g2-base", workspace_path=str(base_workspace), **request),
        IsolatedVerifierRequest(
            task_id="g2-candidate", workspace_path=str(candidate_workspace), **request
        ),
        material,
    )


def _run(
    case: _Case,
    candidate_material: verification.OracleMaterialPaths | None = None,
):
    return verification.run_frozen_same_oracle(
        frozen=case.frozen,
        base_request=case.base_request,
        candidate_request=case.candidate_request,
        base_material=case.material,
        candidate_material=candidate_material or case.material,
    )


def _assert_rejected(
    case: _Case,
    reason: str,
    candidate_material: verification.OracleMaterialPaths | None = None,
) -> None:
    result = _run(case, candidate_material)
    assert result.eligible is False
    assert result.reason_code == reason


def test_structured_oracle_uses_one_sealed_copy_for_fail_then_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case(tmp_path)
    executions: list[tuple[str, bytes, int]] = []

    def inspect(request: IsolatedVerifierRequest) -> IsolatedVerifierReceipt:
        sealed = Path(request.verifier_command[1])
        executions.append((str(sealed), sealed.read_bytes(), sealed.stat().st_mode))
        return run_isolated_verifier(request)

    monkeypatch.setattr(verification, "run_isolated_verifier", inspect)
    result = _run(case)
    assert (result.eligible, result.reason_code) == (True, "SAME_ORACLE_VERIFIED")
    assert result.base_receipt is not None and result.base_receipt.exit_code == 7
    assert result.candidate_receipt is not None and result.candidate_receipt.exit_code == 0
    assert len(executions) == 2
    assert executions[0][0] == executions[1][0] != str(case.material.oracle_path)
    assert executions[0][1] == executions[1][1] == case.frozen.oracle_bytes
    assert executions[0][2] & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH) == 0


@pytest.mark.parametrize(
    ("mode", "reason"),
    (
        ("python-c", "CANDIDATE_COMMAND_FORM_INVALID"),
        ("generic", "CANDIDATE_COMMAND_FORM_INVALID"),
        ("oracle-not-second", "CANDIDATE_COMMAND_FORM_INVALID"),
        ("duplicate", "CANDIDATE_COMMAND_FORM_INVALID"),
        ("python-wrapper", "CANDIDATE_COMMAND_FORM_INVALID"),
        ("oracle.txt", "CANDIDATE_ORACLE_NOT_PYTHON"),
        ("--injected-flag", "CANDIDATE_LITERAL_ARG_INVALID"),
        ("line\nbreak", "CANDIDATE_LITERAL_ARG_INVALID"),
        ("nul\0byte", "CANDIDATE_LITERAL_ARG_INVALID"),
    ),
)
def test_structured_oracle_rejects_unsafe_command_identity(
    tmp_path: Path,
    mode: str,
    reason: str,
) -> None:
    case = _case(tmp_path)
    python, oracle, *_ = case.candidate_request.verifier_command
    material = case.material
    commands = {
        "python-c": (python, "-c", "raise SystemExit(0)"),
        "generic": (str(Path("/bin/sh").resolve()), oracle),
        "oracle-not-second": (python, "--version", oracle),
        "duplicate": (python, oracle, oracle),
    }
    if mode == "python-wrapper":
        wrapper = tmp_path / mode
        wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        wrapper.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        command = (str(wrapper.resolve()), oracle, "literal-arg")
    elif mode == "oracle.txt":
        replacement = tmp_path / mode
        replacement.write_bytes(case.material.oracle_path.read_bytes())
        material = replace(material, oracle_path=replacement)
        command = (python, str(replacement.resolve()), "literal-arg")
    else:
        command = commands.get(mode, (python, oracle, mode))
    candidate = replace(case.candidate_request, verifier_command=command)
    _assert_rejected(replace(case, candidate_request=candidate), reason, material)


@pytest.mark.parametrize(
    ("mode", "reason"),
    (
        ("symlink-oracle_path", "CANDIDATE_MATERIAL_SYMLINK"),
        ("symlink-source_path", "CANDIDATE_MATERIAL_SYMLINK"),
        ("symlink-suite_path", "CANDIDATE_MATERIAL_SYMLINK"),
        ("hardlink", "CANDIDATE_MATERIAL_NOT_DISTINCT"),
        ("drift-oracle_path", "BASE_CONTENT_DRIFT"),
        ("drift-source_path", "BASE_SOURCE_HASH_DRIFT"),
        ("drift-suite_path", "BASE_SUITE_HASH_DRIFT"),
    ),
)
def test_structured_oracle_rejects_material_substitution(
    tmp_path: Path,
    mode: str,
    reason: str,
) -> None:
    case = _case(tmp_path)
    if mode == "hardlink":
        alias = tmp_path / "source-hardlink.txt"
        os.link(case.material.oracle_path, alias)
        _assert_rejected(case, reason, replace(case.material, source_path=alias))
    elif mode.startswith("symlink-"):
        field = mode.removeprefix("symlink-")
        link = tmp_path / f"{field}.link"
        link.symlink_to(getattr(case.material, field))
        _assert_rejected(case, reason, replace(case.material, **{field: link}))
    else:
        getattr(case.material, mode.removeprefix("drift-")).write_text("drift", encoding="utf-8")
        _assert_rejected(case, reason)


def test_structured_oracle_rejects_workspace_reuse(tmp_path: Path) -> None:
    case = _case(tmp_path)
    candidate = replace(
        case.candidate_request,
        workspace_path=case.base_request.workspace_path,
    )
    result = _run(replace(case, candidate_request=candidate))
    assert result.reason_code == "BASE_CANDIDATE_WORKSPACE_NOT_DISTINCT"
    assert result.base_receipt is None


@pytest.mark.parametrize(
    ("target_task", "reason"),
    (
        ("g2-base", "BASE_POST_WORKSPACE_IDENTITY_DRIFT"),
        ("g2-candidate", "CANDIDATE_POST_WORKSPACE_IDENTITY_DRIFT"),
    ),
)
def test_structured_oracle_rejects_workspace_replacement_during_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_task: str,
    reason: str,
) -> None:
    case = _case(tmp_path)

    def swap_workspace(request: IsolatedVerifierRequest) -> IsolatedVerifierReceipt:
        if request.task_id == target_task:
            workspace = Path(request.workspace_path)
            workspace.rename(workspace.with_name(f"{workspace.name}-original"))
            workspace.mkdir()
            (workspace / "state.txt").write_text("fixed", encoding="utf-8")
        return run_isolated_verifier(request)

    monkeypatch.setattr(verification, "run_isolated_verifier", swap_workspace)
    _assert_rejected(case, reason)


@pytest.mark.parametrize(
    ("base_state", "candidate_state", "reason"),
    (("fixed", "fixed", "BASE_ALREADY_PASS"), ("buggy", "buggy", "CANDIDATE_FAIL")),
)
def test_structured_oracle_requires_physical_fail_to_pass(
    tmp_path: Path,
    base_state: str,
    candidate_state: str,
    reason: str,
) -> None:
    _assert_rejected(
        _case(tmp_path, base_state=base_state, candidate_state=candidate_state), reason
    )


def test_structured_oracle_revalidates_live_material_after_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case(tmp_path)

    def mutate_source(request: IsolatedVerifierRequest) -> IsolatedVerifierReceipt:
        receipt = run_isolated_verifier(request)
        case.material.source_path.write_text("live drift", encoding="utf-8")
        return receipt

    monkeypatch.setattr(verification, "run_isolated_verifier", mutate_source)
    _assert_rejected(case, "BASE_POST_SOURCE_HASH_DRIFT")


def test_structured_oracle_rejects_frozen_hash_tamper(tmp_path: Path) -> None:
    case = _case(tmp_path)
    _assert_rejected(
        replace(case, frozen=replace(case.frozen, oracle_sha256="f" * 64)),
        "FROZEN_ORACLE_HASH_MISMATCH",
    )


@pytest.mark.parametrize(
    ("fault", "reason"),
    (
        ("type", "BASE_RECEIPT_TYPE_INVALID"),
        ("task", "BASE_RECEIPT_TASK_ID_MISMATCH"),
        ("status", "BASE_RECEIPT_INCOHERENT"),
        ("exit", "BASE_RECEIPT_INCOHERENT"),
    ),
)
def test_structured_oracle_rejects_invalid_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    reason: str,
) -> None:
    case = _case(tmp_path)

    def invalid(request: IsolatedVerifierRequest):
        receipt = run_isolated_verifier(request)
        return {
            "type": object(),
            "task": replace(receipt, task_id="wrong"),
            "status": replace(receipt, verifier_status="pass"),
            "exit": replace(receipt, exit_code=True),
        }[fault]

    monkeypatch.setattr(verification, "run_isolated_verifier", invalid)
    _assert_rejected(case, reason)


def test_isolated_verifier_not_allowed() -> None:
    request = IsolatedVerifierRequest(
        task_id="t1",
        workspace_path=".",
        verifier_command=("python3", "-c", "print(1)"),
        verifier_allowed=False,
    )
    receipt = run_isolated_verifier(request)
    assert receipt.verifier_status == "blocked"
    assert receipt.verifier_error == "verifier_not_allowed"


def test_isolated_verifier_pass() -> None:
    request = IsolatedVerifierRequest(
        task_id="t2",
        workspace_path=".",
        verifier_command=("python3", "-c", "import sys; sys.exit(0)"),
        verifier_allowed=True,
    )
    receipt = run_isolated_verifier(request)
    assert receipt.verifier_status == "pass"
    assert receipt.exit_code == 0
    assert receipt.verifier_error == ""


def test_isolated_verifier_fail() -> None:
    request = IsolatedVerifierRequest(
        task_id="t3",
        workspace_path=".",
        verifier_command=("python3", "-c", "import sys; sys.exit(1)"),
        verifier_allowed=True,
    )
    receipt = run_isolated_verifier(request)
    assert receipt.verifier_status == "fail"
    assert receipt.exit_code == 1


def test_isolated_verifier_timeout() -> None:
    request = IsolatedVerifierRequest(
        task_id="t4",
        workspace_path=".",
        verifier_command=("python3", "-c", "import time; time.sleep(2)"),
        timeout_sec=0.1,
        verifier_allowed=True,
    )
    receipt = run_isolated_verifier(request)
    assert receipt.verifier_status == "blocked"
    assert "verifier_timeout" in receipt.verifier_error
    assert receipt.exit_code is None


def test_isolated_verifier_calls_semantic_correctness_after_tests() -> None:
    request = IsolatedVerifierRequest(
        task_id="t5",
        workspace_path=".",
        verifier_command=("python3", "-c", "import sys; sys.exit(0)"),
        verifier_allowed=True,
    )
    receipt = run_isolated_verifier(request)
    result = compute_semantic_correctness(receipt)
    assert isinstance(result, bool)


def test_semantic_correctness_true_when_tests_pass_no_buggy_symbol() -> None:
    receipt = IsolatedVerifierReceipt(
        task_id="t6",
        verifier_status="pass",
        exit_code=0,
        stdout_tail="all tests passed",
        stderr_tail="",
        verifier_error="",
        verifier_allowed=True,
        tests_run=[{"name": "test_a", "passed": True}],
    )
    assert compute_semantic_correctness(receipt) is True


def test_semantic_correctness_false_when_buggy_symbol_in_artifact() -> None:
    receipt = IsolatedVerifierReceipt(
        task_id="t7",
        verifier_status="pass",
        exit_code=0,
        stdout_tail="test output: view(NdarrayMixin) still present",
        stderr_tail="",
        verifier_error="",
        verifier_allowed=True,
        tests_run=[{"name": "test_a", "passed": True}],
    )
    assert compute_semantic_correctness(receipt) is False


def test_semantic_correctness_false_when_tests_fail() -> None:
    receipt = IsolatedVerifierReceipt(
        task_id="t8",
        verifier_status="fail",
        exit_code=1,
        stdout_tail="test failed",
        stderr_tail="",
        verifier_error="",
        verifier_allowed=True,
        tests_run=[{"name": "test_a", "passed": False}],
    )
    assert compute_semantic_correctness(receipt) is False


def test_completion_envelope_receives_semantic_correctness_passed() -> None:
    from nexus.engine.completion_contract import build_completion_envelope

    receipt = IsolatedVerifierReceipt(
        task_id="t9",
        verifier_status="pass",
        exit_code=0,
        stdout_tail="all tests passed",
        stderr_tail="",
        verifier_error="",
        verifier_allowed=True,
        tests_run=[{"name": "test_a", "passed": True}],
    )
    result = compute_semantic_correctness(receipt)
    payload = build_completion_envelope(
        command_name="run",
        task_name="test task",
        runtime_ok=True,
        execution_path="cli->engine",
        semantic_correctness_passed=result,
    )
    assert payload["semantic_correctness_passed"] is True
