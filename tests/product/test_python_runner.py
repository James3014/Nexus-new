import json

from product.execution.python_runner import PythonOCIRunner, RunnerStatus


def request():
    return {"source_revision": "rev-a", "source_tree": "tree-a", "contract_hash": "sha256:" + "a" * 64, "plan_hash": "sha256:" + "b" * 64, "environment_hash": "sha256:" + "c" * 64, "attempt_id": "attempt-a"}


def executor(profile, request, index):
    return {"argv": profile.command, "stdout": b"ok", "stderr": b"", "exit_code": 0, "junit": b'<testsuite tests="1" failures="0" errors="0" />'}


def test_two_fresh_runs_bind_profile_and_artifacts():
    result = PythonOCIRunner().run(request(), executor)
    assert result.status is RunnerStatus.VERIFIED
    assert len(result.attempts) == 2
    assert result.artifact_hashes[0] == result.artifact_hashes[1]


def test_failure_and_inadequate_oracle_are_fail_closed():
    def failed(profile, request, index):
        return {"argv": profile.command, "stdout": b"fail", "stderr": b"", "exit_code": 1, "junit": b'<testsuite tests="1" failures="1" errors="0" />'}
    assert PythonOCIRunner().run(request(), failed).status is RunnerStatus.FAILED_VERIFICATION
    assert PythonOCIRunner().run(request(), lambda *_: {}).status is RunnerStatus.UNVERIFIABLE


def test_nondeterminism_and_exact_replay_are_safe():
    def varying(profile, request, index):
        return {"argv": profile.command, "stdout": str(index).encode(), "stderr": b"", "exit_code": 0, "junit": b'<testsuite tests="1" failures="0" errors="0" />'}
    runner = PythonOCIRunner()
    result = runner.run(request(), varying)
    assert result.status is RunnerStatus.UNVERIFIABLE
    called = []
    replay = runner.run(request(), lambda *_: called.append(1))
    assert replay == result and not called


def test_profile_file_and_shell_free_contract():
    from pathlib import Path
    data = json.loads((Path(__file__).parents[2] / "product/execution/profiles/python-oci-pytest-v1.json").read_text())
    assert data["network"] == "none" and data["rootfs"] == "read-only"
    assert "sh" not in data["command"]
