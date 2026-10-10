"""Negative controls for scripts/ci/verify_physical_witness_junit.py (#1607).

These run on every platform (nothing here is skipped or hidden). They never stand
in for the physical Seatbelt proof: fake ``sandbox-exec`` binaries only show the
canary rejects a host that does not really confine writes. The live proof is the
macOS CI job that runs the verifier against the physical ``/usr/bin/sandbox-exec``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.ci import verify_physical_witness_junit as v

ROOT = Path(__file__).resolve().parents[2]
TEST_SOURCE = (ROOT / v.TEST_FILE).read_text(encoding="utf-8")
ALL_TESTS, _ = v.declared_witnesses(TEST_SOURCE)
HOST = "witness-host"
NOT_BEFORE = "2026-10-10T00:00:00+00:00"
STARTED = "2026-10-10T00:05:00+00:00"
NOW = datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc)
W1, W2 = v.EXPECTED_WITNESSES


def _junit(
    cases: list[tuple[str, str | None]] | None = None,
    *,
    classname: str = v.TEST_CLASSNAME,
    hostname: str = HOST,
    timestamp: str = STARTED,
    suite_attrs: dict[str, str] | None = None,
    extra_suite: bool = False,
) -> bytes:
    cases = [(name, None) for name in sorted(ALL_TESTS)] if cases is None else cases
    body = []
    counts = {"skipped": 0, "error": 0, "failure": 0}
    for name, outcome in cases:
        child = f'<{outcome} message="x"/>' if outcome else ""
        if outcome:
            counts[outcome] += 1
        body.append(
            f'<testcase classname="{classname}" name="{name}" time="0.1">{child}</testcase>'
        )
    attrs = {
        "name": "pytest",
        "errors": str(counts["error"]),
        "failures": str(counts["failure"]),
        "skipped": str(counts["skipped"]),
        "tests": str(len(cases)),
        "timestamp": timestamp,
        "hostname": hostname,
        **(suite_attrs or {}),
    }
    rendered = " ".join(f'{key}="{value}"' for key, value in attrs.items())
    suite = f"<testsuite {rendered}>{''.join(body)}</testsuite>"
    if extra_suite:
        suite += suite
    return f'<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests">{suite}</testsuites>'.encode()


def _verify(junit: bytes, source: str = TEST_SOURCE, **kw) -> dict:
    kw.setdefault("not_before", NOT_BEFORE)
    kw.setdefault("hostname", HOST)
    kw.setdefault("now", NOW)
    return v.verify_junit(junit, source, **kw)


def _reject(code: str, junit: bytes, source: str = TEST_SOURCE, **kw) -> None:
    with pytest.raises(v.WitnessError) as exc:
        _verify(junit, source, **kw)
    assert exc.value.code == code, exc.value


def _without(name: str) -> list[tuple[str, str | None]]:
    return [(n, None) for n in sorted(ALL_TESTS) if n != name]


def test_well_formed_junit_yields_exactly_the_two_passed_witnesses() -> None:
    result = _verify(_junit())

    assert [w["node_id"] for w in result["witnesses"]] == [
        f"{v.TEST_FILE}::{name}" for name in sorted(v.EXPECTED_WITNESSES)
    ]
    assert {w["outcome"] for w in result["witnesses"]} == {"passed"}
    assert result["testcases"] == len(ALL_TESTS)


def test_source_declares_exactly_the_expected_witnesses() -> None:
    tests, witnesses = v.declared_witnesses(TEST_SOURCE)
    assert witnesses == set(v.EXPECTED_WITNESSES)
    assert witnesses < tests


@pytest.mark.parametrize("witness", v.EXPECTED_WITNESSES)
@pytest.mark.parametrize("outcome", ["skipped", "error", "failure"])
def test_skipped_errored_or_failed_witness_is_rejected(witness: str, outcome: str) -> None:
    cases = [(n, outcome if n == witness else None) for n in sorted(ALL_TESTS)]
    _reject(f"JUNIT_TESTCASE_{outcome.upper()}", _junit(cases))


def test_any_skip_in_the_file_is_rejected_even_for_non_witness_tests() -> None:
    other = sorted(ALL_TESTS - set(v.EXPECTED_WITNESSES))[0]
    cases = [(n, "skipped" if n == other else None) for n in sorted(ALL_TESTS)]
    _reject("JUNIT_TESTCASE_SKIPPED", _junit(cases))


def test_suite_level_skip_count_is_rejected_without_testcase_markers() -> None:
    _reject("JUNIT_SUITE_NOT_CLEAN", _junit(suite_attrs={"skipped": "1"}))
    _reject("JUNIT_SUITE_COUNT_MISMATCH", _junit(suite_attrs={"tests": "99"}))


@pytest.mark.parametrize("witness", v.EXPECTED_WITNESSES)
def test_missing_witness_node_is_rejected(witness: str) -> None:
    # Exactly what a Linux run looks like: the witness is simply not collected.
    _reject("JUNIT_COLLECTION_MISMATCH", _junit(_without(witness)))


def test_linux_shaped_junit_without_both_witnesses_is_rejected() -> None:
    cases = [(n, None) for n in sorted(ALL_TESTS - set(v.EXPECTED_WITNESSES))]
    _reject("JUNIT_COLLECTION_MISMATCH", _junit(cases))


def test_duplicate_witness_node_is_rejected() -> None:
    cases = [(n, None) for n in sorted(ALL_TESTS)] + [(W1, None)]
    _reject("JUNIT_DUPLICATE_TESTCASE", _junit(cases))


def test_parametrized_or_extra_witness_variant_is_rejected() -> None:
    cases = [(n, None) for n in sorted(ALL_TESTS)] + [(f"{W2}[again]", None)]
    _reject("WITNESS_NODE_AMBIGUOUS", _junit(cases))


def test_third_declared_witness_in_source_is_rejected() -> None:
    source = TEST_SOURCE + (
        "\n\n@physical_seatbelt_witness\ndef test_third_physical_witness() -> None:\n    pass\n"
    )
    cases = [(n, None) for n in sorted(ALL_TESTS)] + [("test_third_physical_witness", None)]
    _reject("WITNESS_DECLARATION_MISMATCH", _junit(cases), source)


def test_undeclared_witness_in_source_is_rejected() -> None:
    source = TEST_SOURCE.replace(f"@physical_seatbelt_witness\ndef {W1}(", f"def {W1}(", 1)
    assert source != TEST_SOURCE
    _reject("WITNESS_DECLARATION_MISMATCH", _junit(), source)


def test_extra_testcase_not_in_file_is_rejected() -> None:
    cases = [(n, None) for n in sorted(ALL_TESTS)] + [("test_not_in_file", None)]
    _reject("JUNIT_COLLECTION_MISMATCH", _junit(cases))


def test_foreign_testcases_and_multiple_suites_are_rejected() -> None:
    _reject("JUNIT_FOREIGN_TESTCASES", _junit(classname="tests.ops.test_other"))
    _reject("JUNIT_SUITE_AMBIGUOUS", _junit(extra_suite=True))
    _reject("JUNIT_UNPARSEABLE", b"<testsuites><testsuite")


def test_stale_or_foreign_host_junit_is_rejected() -> None:
    _reject("JUNIT_HOST_MISMATCH", _junit(hostname="other-host"))
    _reject("JUNIT_NOT_FRESH", _junit(timestamp="2026-10-09T23:59:59+00:00"))
    future = (NOW + timedelta(minutes=1)).isoformat()
    _reject("JUNIT_NOT_FRESH", _junit(timestamp=future))
    _reject("JUNIT_TIMESTAMP_INVALID", _junit(timestamp="2026-10-10T00:05:00"))
    _reject("NOT_BEFORE_INVALID", _junit(), not_before="yesterday")


def test_non_darwin_is_rejected_before_any_physical_probe(tmp_path: Path) -> None:
    def must_not_run(*_args, **_kwargs):
        raise AssertionError("physical probe ran on a non-darwin host")

    for name in ("linux", "win32", "cygwin"):
        with pytest.raises(v.WitnessError) as exc:
            v.preflight(
                sys_platform=name,
                canary_parent=tmp_path,
                binary_check=must_not_run,
                canary=must_not_run,
            )
        assert exc.value.code == "NOT_DARWIN"


def test_preflight_is_pinned_to_the_physical_system_binary() -> None:
    assert v.SANDBOX_EXEC == "/usr/bin/sandbox-exec"
    assert v.preflight.__kwdefaults__["sandbox_exec"] == "/usr/bin/sandbox-exec"
    assert v.preflight.__kwdefaults__["binary_check"] is v.check_sandbox_binary
    assert v.preflight.__kwdefaults__["canary"] is v.run_seatbelt_canary


def _fake_sandbox(tmp_path: Path, body: str) -> Path:
    fake = tmp_path / "bin" / "sandbox-exec"
    fake.parent.mkdir(exist_ok=True)
    fake.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    fake.chmod(0o755)
    return fake


def test_sandbox_binary_check_rejects_missing_shadowed_or_user_owned(tmp_path: Path) -> None:
    with pytest.raises(v.WitnessError) as exc:
        v.check_sandbox_binary(str(tmp_path / "absent"))
    assert exc.value.code == "SANDBOX_EXEC_MISSING"

    fake = _fake_sandbox(tmp_path, 'shift 2; exec "$@"')
    link = tmp_path / "bin" / "link"
    link.symlink_to(fake)
    with pytest.raises(v.WitnessError) as exc:
        v.check_sandbox_binary(str(link))
    assert exc.value.code == "SANDBOX_EXEC_NOT_REGULAR_FILE"

    assert os.geteuid() != 0, "negative controls need a non-root test user"
    with pytest.raises(v.WitnessError) as exc:
        v.check_sandbox_binary(str(fake), which=lambda _name: str(fake))
    assert exc.value.code == "SANDBOX_EXEC_NOT_ROOT_OWNED"

    # A real root-owned regular executable that is not what PATH resolves to.
    root_owned = next(
        path
        for path in ("/usr/bin/env", "/usr/bin/true", "/bin/ls")
        if not Path(path).is_symlink() and Path(path).is_file() and Path(path).stat().st_uid == 0
    )
    with pytest.raises(v.WitnessError) as exc:
        v.check_sandbox_binary(root_owned, which=lambda _name: str(fake))
    assert exc.value.code == "SANDBOX_EXEC_PATH_SHADOWED"
    with pytest.raises(v.WitnessError) as exc:
        v.check_sandbox_binary(root_owned, which=lambda _name: None)
    assert exc.value.code == "SANDBOX_EXEC_PATH_SHADOWED"


def test_canary_rejects_a_sandbox_that_does_not_confine(tmp_path: Path) -> None:
    # Pretends to be Seatbelt but runs the command unconfined: the victim changes.
    fake = _fake_sandbox(tmp_path, 'shift 2; exec "$@"')
    with pytest.raises(v.WitnessError) as exc:
        v.run_seatbelt_canary(str(fake), tmp_path / "canary", temp_roots=())
    assert exc.value.code == "CANARY_OUT_OF_TEMP_WRITE_NOT_DENIED"


def test_canary_rejects_a_sandbox_that_only_claims_denial(tmp_path: Path) -> None:
    # Prints the denial text for everything: the allowed workspace write fails too.
    fake = _fake_sandbox(tmp_path, "echo 'Operation not permitted' >&2; exit 1")
    with pytest.raises(v.WitnessError) as exc:
        v.run_seatbelt_canary(str(fake), tmp_path / "canary", temp_roots=())
    assert exc.value.code == "CANARY_WORKSPACE_WRITE_NOT_ALLOWED"


def test_canary_rejects_silent_noop_denial_without_seatbelt_error(tmp_path: Path) -> None:
    # Allows workspace writes, drops other writes silently with exit 0.
    fake = _fake_sandbox(
        tmp_path,
        'shift 2; case "$5" in */workspace/*) exec "$@";; *) exit 0;; esac',
    )
    with pytest.raises(v.WitnessError) as exc:
        v.run_seatbelt_canary(str(fake), tmp_path / "canary", temp_roots=())
    assert exc.value.code == "CANARY_OUT_OF_TEMP_WRITE_NOT_DENIED"


def test_canary_rejects_denial_text_when_the_victim_was_still_written(tmp_path: Path) -> None:
    # Performs every write unconfined, then reports a Seatbelt-shaped denial.
    fake = _fake_sandbox(
        tmp_path,
        'shift 2; "$@"; case "$5" in */workspace/*) exit 0;; '
        "*) echo 'Operation not permitted' >&2; exit 1;; esac",
    )
    with pytest.raises(v.WitnessError) as exc:
        v.run_seatbelt_canary(str(fake), tmp_path / "canary", temp_roots=())
    assert exc.value.code == "CANARY_OUT_OF_TEMP_WRITE_NOT_DENIED"
    assert exc.value.detail == "victim changed"


def test_canary_root_under_temp_grant_is_rejected(tmp_path: Path) -> None:
    fake = _fake_sandbox(tmp_path, "exit 99")
    with pytest.raises(v.WitnessError) as exc:
        v.run_seatbelt_canary(str(fake), tmp_path / "canary", temp_roots=(v._real(tmp_path),))
    assert exc.value.code == "CANARY_ROOT_UNDER_TEMP_GRANT"
    assert not list((tmp_path / "canary").iterdir())


def _subject_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    for rel in v.SUBJECT_FILES.values():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=repo, text=True, capture_output=True, check=True
        ).stdout.strip()

    git("init", "-q")
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-m", "subject")
    return repo, git("rev-parse", "HEAD")


def test_git_subject_binds_exact_head_tree_and_blobs(tmp_path: Path) -> None:
    repo, head = _subject_repo(tmp_path)

    subject = v.git_subject(repo, head)

    assert subject["head_sha"] == head
    assert set(subject["blobs"]) == set(v.SUBJECT_FILES)
    assert len(subject["head_tree"]) == 40


def test_git_subject_rejects_wrong_invalid_or_dirty_identity(tmp_path: Path) -> None:
    repo, head = _subject_repo(tmp_path)
    for expected, code in (
        ("0" * 40, "HEAD_SHA_MISMATCH"),
        (head[:12], "EXPECTED_HEAD_SHA_INVALID"),
        (head.upper(), "EXPECTED_HEAD_SHA_INVALID"),
        ("", "EXPECTED_HEAD_SHA_INVALID"),
    ):
        with pytest.raises(v.WitnessError) as exc:
            v.git_subject(repo, expected)
        assert exc.value.code == code, expected

    (repo / v.TEST_FILE).write_text(TEST_SOURCE + "\n# drift\n", encoding="utf-8")
    with pytest.raises(v.WitnessError) as exc:
        v.git_subject(repo, head)
    assert exc.value.code == "WORKTREE_DIRTY"

    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(v.WitnessError) as exc:
        v.git_subject(plain, head)
    assert exc.value.code == "GIT_IDENTITY_UNAVAILABLE"


def test_git_subject_rejects_committed_subject_file_missing(tmp_path: Path) -> None:
    repo, _ = _subject_repo(tmp_path)
    subprocess.run(["git", "rm", "-q", v.SUBJECT_FILES["conftest"]], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-m", "drop"],
        cwd=repo,
        check=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True
    ).stdout.strip()
    with pytest.raises(v.WitnessError) as exc:
        v.git_subject(repo, head)
    assert exc.value.code == "GIT_IDENTITY_UNAVAILABLE"


def test_github_context_requires_hosted_macos_run_identity() -> None:
    env = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": "James3014/Nexus-new",
        "GITHUB_WORKFLOW_REF": "James3014/Nexus-new/.github/workflows/pytest.yml@refs/pull/1/merge",
        "GITHUB_JOB": "dsh-seatbelt-physical-witness",
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_REF": "refs/pull/1/merge",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "RUNNER_NAME": "GitHub Actions 1",
        "RUNNER_OS": "macOS",
        "RUNNER_ARCH": "ARM64",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "ImageOS": "macos15",
        "ImageVersion": "20261001.1",
    }
    assert v.github_context(env)["run_id"] == "123"
    for key, value, code in (
        ("RUNNER_ENVIRONMENT", "self-hosted", "GITHUB_HOSTED_CONTEXT_MISSING"),
        ("RUNNER_OS", "Linux", "GITHUB_HOSTED_CONTEXT_MISSING"),
        ("GITHUB_ACTIONS", None, "GITHUB_HOSTED_CONTEXT_MISSING"),
        ("GITHUB_RUN_ID", None, "GITHUB_HOSTED_CONTEXT_MISSING"),
        ("ImageVersion", "", "GITHUB_HOSTED_CONTEXT_MISSING"),
        ("GITHUB_RUN_ATTEMPT", "first", "GITHUB_RUN_IDENTITY_INVALID"),
    ):
        broken = dict(env)
        if value is None:
            broken.pop(key)
        else:
            broken[key] = value
        with pytest.raises(v.WitnessError) as exc:
            v.github_context(broken)
        assert exc.value.code == code, key


def test_cli_verify_on_non_darwin_writes_fail_receipt_and_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(v.sys, "platform", "linux")
    junit = tmp_path / "junit.xml"
    junit.write_bytes(_junit())
    output = tmp_path / "receipt.json"

    status = v.main([
        "verify",
        "--repo-root",
        str(ROOT),
        "--expected-head-sha",
        "0" * 40,
        "--junit",
        str(junit),
        "--not-before",
        NOT_BEFORE,
        "--command",
        "pytest",
        "--canary-parent",
        str(tmp_path / "canary"),
        "--output",
        str(output),
    ])

    assert status == 1
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "FAIL"
    assert receipt["reason_code"] == "NOT_DARWIN"
    assert v.main(["preflight", "--canary-parent", str(tmp_path / "canary")]) == 1


def test_cli_verify_cannot_pass_with_a_mocked_platform_but_no_physical_canary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Spoofing the platform does not help: the CLI still demands the root-owned
    # /usr/bin/sandbox-exec and a live denial. A fake on PATH is rejected.
    monkeypatch.setattr(v.sys, "platform", "darwin")
    fake = _fake_sandbox(tmp_path, 'shift 2; exec "$@"')
    monkeypatch.setenv("PATH", f"{fake.parent}:/usr/bin:/bin")
    junit = tmp_path / "junit.xml"
    junit.write_bytes(_junit())
    output = tmp_path / "receipt.json"

    status = v.main([
        "verify",
        "--repo-root",
        str(ROOT),
        "--expected-head-sha",
        "0" * 40,
        "--junit",
        str(junit),
        "--not-before",
        NOT_BEFORE,
        "--command",
        "pytest",
        "--canary-parent",
        str(tmp_path / "canary"),
        "--output",
        str(output),
    ])

    assert status == 1
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "FAIL"
    assert receipt["reason_code"] in {"SANDBOX_EXEC_MISSING", "SANDBOX_EXEC_PATH_SHADOWED"}


def _witness_job() -> dict:
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/pytest.yml").read_text(encoding="utf-8"))
    return workflow["jobs"]["dsh-seatbelt-physical-witness"]


def _witness_step(job: dict, name: str) -> dict:
    (step,) = [step for step in job["steps"] if step.get("name") == name]
    return step


def test_witness_job_cannot_be_skipped_or_soft_failed() -> None:
    job = _witness_job()
    assert job["runs-on"] == "macos-15"
    assert job["permissions"] == {"contents": "read"}
    for key in ("if", "continue-on-error"):
        assert key not in job
    for step in job["steps"]:
        assert "continue-on-error" not in step, step.get("name")


@pytest.mark.parametrize("pytest_status", [0, 1, 3, 137])
def test_witness_pytest_step_propagates_the_pytest_exit_status(
    tmp_path: Path, pytest_status: int
) -> None:
    # Runs the workflow step's real shell with a stub pytest that prints
    # green-looking output and exits with ``pytest_status``.
    step = _witness_step(_witness_job(), "Run DSH Seatbelt physical witnesses")
    assert step.get("shell", "bash") == "bash"
    stub = tmp_path / ".venv" / "bin" / "python"
    stub.parent.mkdir(parents=True)
    stub.write_text(f"#!/bin/sh\necho '12 passed'\nexit {pytest_status}\n", encoding="utf-8")
    stub.chmod(0o755)
    witness_dir = tmp_path / "witness"
    witness_dir.mkdir()

    proc = subprocess.run(
        ["bash", "-e", "-c", step["run"]],
        cwd=tmp_path,
        env={"PATH": os.environ["PATH"], "WITNESS_DIR": str(witness_dir), **step["env"]},
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == pytest_status, proc.stdout + proc.stderr
    assert (witness_dir / "pytest-exit.txt").read_text(encoding="utf-8").strip() == str(
        pytest_status
    )
    assert "12 passed" in (witness_dir / "pytest.log").read_text(encoding="utf-8")
