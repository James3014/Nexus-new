import json
from pathlib import Path

import pytest

from product.execution.python_runner import PythonOCIProfile, PythonOCIRunner, RunnerStatus


def request():
    return {"source_revision": "rev-a", "source_tree": "tree-a", "contract_hash": "sha256:" + "a" * 64, "plan_hash": "sha256:" + "b" * 64, "environment_hash": "sha256:" + "c" * 64, "attempt_id": "attempt-a"}


def executor(profile, request, index):
    return {"source_revision": request["source_revision"], "source_tree": request["source_tree"], "contract_hash": request["contract_hash"], "plan_hash": request["plan_hash"], "environment_hash": request["environment_hash"], "profile_id": profile.profile_id, "image": profile.image, "image_digest": profile.image_digest, "lock_digest": profile.lock_digest, "execution_id": f"exec-{index}", "argv": profile.command, "stdout": b"ok", "stderr": b"", "exit_code": 0, "junit": b'<testsuite tests="1" failures="0" errors="0" />'}


def test_two_fresh_runs_bind_profile_and_artifacts():
    result = PythonOCIRunner().run(request(), executor)
    assert result.status is RunnerStatus.VERIFIED
    assert len(result.attempts) == 2
    assert result.artifact_hashes[0] == result.artifact_hashes[1]


def test_failure_and_inadequate_oracle_are_fail_closed():
    def failed(profile, request, index):
        result = executor(profile, request, index)
        return {**result, "stdout": b"fail", "exit_code": 1, "junit": b'<testsuite tests="1" failures="1" errors="0" />'}
    assert PythonOCIRunner().run(request(), failed).status is RunnerStatus.FAILED_VERIFICATION
    assert PythonOCIRunner().run(request(), lambda *_: {}).status is RunnerStatus.UNVERIFIABLE


def test_nondeterminism_and_exact_replay_are_safe():
    def varying(profile, request, index):
        result = executor(profile, request, index)
        return {**result, "stdout": str(index).encode()}
    runner = PythonOCIRunner()
    result = runner.run(request(), varying)
    assert result.status is RunnerStatus.UNVERIFIABLE
    called = []
    replay = runner.run(request(), lambda *_: called.append(1))
    assert replay == result and not called


def test_profile_file_and_shell_free_contract():
    data = json.loads((Path(__file__).parents[2] / "product/execution/profiles/python-oci-pytest-v1.json").read_text())
    assert data["network"] == "none" and data["rootfs"] == "read-only"
    assert "sh" not in data["command"]


@pytest.mark.parametrize("field", ["source_revision", "source_tree", "environment_hash", "profile_id", "image", "image_digest", "lock_digest", "argv"])
def test_wrong_observed_binding_is_unverifiable(field):
    def hostile(profile, req, index):
        value = executor(profile, req, index)
        value[field] = (profile.command + ("wrong",)) if field == "argv" else "wrong"
        return value
    assert PythonOCIRunner().run(request(), hostile).status is RunnerStatus.UNVERIFIABLE


@pytest.mark.parametrize("exit_code", [2, 3, 4, 5])
def test_pytest_non_test_exit_codes_are_unknown(exit_code):
    def unavailable(profile, req, index):
        return {**executor(profile, req, index), "exit_code": exit_code}
    assert PythonOCIRunner().run(request(), unavailable).status is RunnerStatus.UNVERIFIABLE


def test_duplicate_physical_execution_id_and_exit_mismatch_are_unknown():
    def duplicate(profile, req, index):
        return {**executor(profile, req, index), "execution_id": "same"}
    assert "DUPLICATE_EXECUTION_ID" in PythonOCIRunner().run(request(), duplicate).reason_codes

    def mismatch(profile, req, index):
        return {**executor(profile, req, index), "exit_code": 0, "junit": b'<testsuite tests="1" failures="1" errors="0" />'}
    assert PythonOCIRunner().run(request(), mismatch).status is RunnerStatus.UNVERIFIABLE


def test_manifest_lock_reload_binds_actual_uv_lock():
    root = Path(__file__).parents[2]
    profile = PythonOCIProfile.load(root / "product/execution/profiles/python-oci-pytest-v1.json", root / "product/execution/profiles/python-oci-pytest-v1.lock", root / "uv.lock")
    assert profile.profile_id == "python-oci-pytest-v1"
