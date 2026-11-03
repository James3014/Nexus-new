from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from nexus.learning.zero_trust_v2_physical_sandbox import (
    _macos_sandbox_profile,
    _profile_confines_writes,
    run_macos_sandbox_probe,
)
from nexus.learning.zero_trust_v2_sandbox import validate_sandbox_attestation


def _completed(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")


def test_macos_physical_sandbox_probe_emits_promotion_valid_attestation(tmp_path: Path) -> None:
    result = run_macos_sandbox_probe(
        ["/bin/echo", "ok"],
        signing_secret="test-secret",
        sandbox_exec_path="/usr/bin/sandbox-exec",
        subprocess_run=_completed,
        base_tmp_dir=tmp_path,
        env_source={"PATH": "/usr/bin:/bin", "NEXUS_SYSTEM_SALT": "must-not-leak"},
    )

    assert result["status"] == "PASS"
    assert result["promotion_eligible"] is True
    attestation = result["sandbox_attestation"]
    assert attestation["issuer"] == "nexus.runner"
    assert attestation["sandbox_mode"] == "macos_sandbox"
    assert attestation["network_disabled"] is True
    assert attestation["workspace_isolated"] is True
    assert attestation["tmp_isolated"] is True
    assert attestation["teardown_status"] == "PASS"
    assert attestation["signature"]
    assert "test-secret" not in str(attestation)
    assert "must-not-leak" not in str(attestation)
    assert validate_sandbox_attestation(attestation) == {"status": "PASS", "reasons": [], "sandbox_mode": "macos_sandbox"}


def test_macos_physical_sandbox_probe_blocks_when_sandbox_apply_fails(tmp_path: Path) -> None:
    def sandbox_apply_failure(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 71, stdout="", stderr="sandbox-exec: sandbox_apply: Operation not permitted")

    result = run_macos_sandbox_probe(
        ["/bin/echo", "ok"],
        signing_secret="test-secret",
        sandbox_exec_path="/usr/bin/sandbox-exec",
        subprocess_run=sandbox_apply_failure,
        base_tmp_dir=tmp_path,
        env_source={"PATH": "/usr/bin:/bin"},
    )

    assert result["status"] == "BLOCKED"
    assert result["promotion_eligible"] is False
    attestation = result["sandbox_attestation"]
    assert attestation["network_disabled"] is False
    assert attestation["raw_observation"]["sandbox_apply_failed"] is True
    verdict = validate_sandbox_attestation(attestation)
    assert verdict["status"] == "BLOCKED"
    assert "sandbox_status_not_pass" in verdict["reasons"]
    assert "network_not_disabled" in verdict["reasons"]


def test_macos_physical_sandbox_probe_blocks_timeout(tmp_path: Path) -> None:
    def timeout(_: list[str], **__: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(["sandbox-exec"], timeout=1)

    result = run_macos_sandbox_probe(
        ["/bin/sleep", "5"],
        signing_secret="test-secret",
        sandbox_exec_path="/usr/bin/sandbox-exec",
        subprocess_run=timeout,
        base_tmp_dir=tmp_path,
        env_source={"PATH": "/usr/bin:/bin"},
        timeout_sec=1,
    )

    assert result["status"] == "BLOCKED"
    assert result["sandbox_attestation"]["raw_observation"]["timed_out"] is True
    assert validate_sandbox_attestation(result["sandbox_attestation"])["status"] == "BLOCKED"


def test_probe_reports_workspace_not_isolated_when_sandbox_exec_unavailable(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr("nexus.learning.zero_trust_v2_physical_sandbox.shutil.which", lambda _name, **_kw: None)
    seen: list[list[str]] = []

    def record(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        seen.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    result = run_macos_sandbox_probe(
        ["/bin/echo", "ok"],
        signing_secret="test-secret",
        subprocess_run=record,
        base_tmp_dir=tmp_path,
        env_source={"PATH": "/usr/bin:/bin"},
    )

    assert seen == [["/bin/echo", "ok"]]
    attestation = result["sandbox_attestation"]
    assert attestation["workspace_isolated"] is False
    assert attestation["workspace_isolation_reason"] == "sandbox_exec_unavailable"
    assert attestation["network_disabled"] is False
    assert result["promotion_eligible"] is False
    assert result["status"] == "BLOCKED"
    verdict = validate_sandbox_attestation(attestation)
    assert verdict["status"] == "BLOCKED"
    assert "workspace_not_isolated" in verdict["reasons"]


def test_probe_reports_workspace_isolated_when_sandbox_exec_available(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "nexus.learning.zero_trust_v2_physical_sandbox.shutil.which", lambda _name, **_kw: "/usr/bin/sandbox-exec"
    )
    result = run_macos_sandbox_probe(
        ["/bin/echo", "ok"],
        signing_secret="test-secret",
        subprocess_run=_completed,
        base_tmp_dir=tmp_path,
        env_source={"PATH": "/usr/bin:/bin"},
    )
    attestation = result["sandbox_attestation"]
    assert attestation["workspace_isolated"] is True
    assert attestation["workspace_isolation_reason"] is None
    assert result["promotion_eligible"] is True


def test_probe_reports_workspace_not_isolated_when_sandbox_apply_fails(tmp_path: Path) -> None:
    def failure(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 71, stdout="", stderr="sandbox_apply: denied")

    result = run_macos_sandbox_probe(
        ["/bin/echo", "ok"],
        signing_secret="test-secret",
        sandbox_exec_path="/usr/bin/sandbox-exec",
        subprocess_run=failure,
        base_tmp_dir=tmp_path,
        env_source={"PATH": "/usr/bin:/bin"},
    )
    attestation = result["sandbox_attestation"]
    assert attestation["workspace_isolated"] is False
    assert attestation["workspace_isolation_reason"] == "sandbox_apply_failed"


def _probe_with_profile_capture(tmp_path: Path, **kwargs: Any) -> tuple[dict[str, Any], list[str]]:
    profiles: list[str] = []

    def capture(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        profiles.append(Path(cmd[cmd.index("-f") + 1]).read_text(encoding="utf-8"))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    result = run_macos_sandbox_probe(
        ["/bin/echo", "ok"],
        signing_secret="test-secret",
        sandbox_exec_path="/usr/bin/sandbox-exec",
        subprocess_run=capture,
        env_source={"PATH": "/usr/bin:/bin"},
        **kwargs,
    )
    return result, profiles


def _profile_rules(profile: str) -> list[str]:
    return [line.strip() for line in profile.splitlines() if line.strip()]


def test_probe_profile_denies_writes_outside_workspace_and_tmp(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    result, profiles = _probe_with_profile_capture(tmp_path, base_tmp_dir=base)

    rules = _profile_rules(profiles[0])
    assert "(deny network*)" in rules
    assert "(deny file-write*)" in rules
    assert rules.index("(deny file-write*)") > rules.index("(allow default)")
    write_rules = [rule for rule in rules if "file-write" in rule and rule != "(deny file-write*)"]
    assert len(write_rules) == 1
    allowed = write_rules[0]
    assert allowed.startswith("(allow file-write* ")
    assert rules.index(allowed) > rules.index("(deny file-write*)")
    resolved_base = str(base.resolve())
    filters = allowed[len("(allow file-write* ") : -1]
    assert filters.count("(subpath ") == 2
    assert f'(subpath "{resolved_base}/' in filters
    assert filters.endswith('(literal "/dev/null")')
    for subpath in filters.split("(subpath ")[1:]:
        path = subpath.split('"')[1]
        assert path.startswith(resolved_base + "/nexus-ztv2-runner-")
        assert path.endswith(("/workspace", "/tmp"))
    attestation = result["sandbox_attestation"]
    assert attestation["raw_observation"]["write_scope_confined"] is True
    assert attestation["tmp_isolated"] is True
    assert attestation["workspace_isolated"] is True


def test_probe_profile_uses_resolved_paths_for_symlinked_base(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    _, profiles = _probe_with_profile_capture(tmp_path, base_tmp_dir=link)

    profile = profiles[0]
    assert str(link) + "/" not in profile
    assert f'(subpath "{real.resolve()}/' in profile


def test_probe_tmp_not_isolated_when_sandbox_exec_unavailable(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        "nexus.learning.zero_trust_v2_physical_sandbox.shutil.which", lambda _name, **_kw: None
    )
    result = run_macos_sandbox_probe(
        ["/bin/echo", "ok"],
        signing_secret="test-secret",
        subprocess_run=_completed,
        base_tmp_dir=tmp_path,
        env_source={"PATH": "/usr/bin:/bin"},
    )
    attestation = result["sandbox_attestation"]
    assert attestation["tmp_isolated"] is False
    assert "tmp_not_isolated" in validate_sandbox_attestation(attestation)["reasons"]


def _assert_not_isolated(result: dict[str, Any], reason: str) -> None:
    attestation = result["sandbox_attestation"]
    assert attestation["network_disabled"] is False
    assert attestation["workspace_isolated"] is False
    assert attestation["tmp_isolated"] is False
    assert attestation["workspace_isolation_reason"] == reason
    assert attestation["status"] == "BLOCKED"
    assert result["status"] == "BLOCKED"
    assert result["promotion_eligible"] is False
    verdict = validate_sandbox_attestation(attestation)
    assert verdict["status"] == "BLOCKED"
    assert {"network_not_disabled", "workspace_not_isolated", "tmp_not_isolated"} <= set(
        verdict["reasons"]
    )


def _probe_returning(tmp_path: Path, returncode: int, stderr: str) -> dict[str, Any]:
    def finished(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, returncode, stdout="", stderr=stderr)

    return run_macos_sandbox_probe(
        ["/bin/echo", "ok"],
        signing_secret="test-secret",
        sandbox_exec_path="/usr/bin/sandbox-exec",
        subprocess_run=finished,
        base_tmp_dir=tmp_path,
        env_source={"PATH": "/usr/bin:/bin"},
    )


def test_probe_not_isolated_when_profile_fails_to_parse(tmp_path: Path) -> None:
    result = _probe_returning(tmp_path, 65, "sandbox-exec: syntax error: expecting ')'\n")
    _assert_not_isolated(result, "sandbox_launch_failed")
    assert result["sandbox_attestation"]["raw_observation"]["sandbox_apply_failed"] is True


def test_probe_not_isolated_when_sandbox_exec_cannot_exec_command(tmp_path: Path) -> None:
    result = _probe_returning(
        tmp_path, 71, "sandbox-exec: execvp() of '/bin/missing' failed: No such file or directory\n"
    )
    _assert_not_isolated(result, "sandbox_launch_failed")


def test_probe_not_isolated_on_sandbox_exec_usage_error_without_diagnostic(tmp_path: Path) -> None:
    _assert_not_isolated(_probe_returning(tmp_path, 64, ""), "sandbox_launch_failed")


def test_probe_not_isolated_on_sandbox_exec_diagnostic_with_other_code(tmp_path: Path) -> None:
    _assert_not_isolated(
        _probe_returning(tmp_path, 1, "sandbox-exec: unexpected failure\n"), "sandbox_launch_failed"
    )


def test_probe_not_isolated_when_killed_by_signal(tmp_path: Path) -> None:
    _assert_not_isolated(_probe_returning(tmp_path, -9, ""), "sandbox_launch_failed")


def test_probe_not_isolated_on_timeout(tmp_path: Path) -> None:
    def timeout(_: list[str], **__: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(["sandbox-exec"], timeout=1)

    result = run_macos_sandbox_probe(
        ["/bin/sleep", "5"],
        signing_secret="test-secret",
        sandbox_exec_path="/usr/bin/sandbox-exec",
        subprocess_run=timeout,
        base_tmp_dir=tmp_path,
        env_source={"PATH": "/usr/bin:/bin"},
        timeout_sec=1,
    )
    _assert_not_isolated(result, "sandbox_outcome_unknown_timeout")


def test_probe_keeps_isolation_for_child_failure_under_applied_sandbox(tmp_path: Path) -> None:
    result = _probe_returning(tmp_path, 1, "child: assertion failed\n")
    attestation = result["sandbox_attestation"]
    assert attestation["workspace_isolated"] is True
    assert attestation["tmp_isolated"] is True
    assert attestation["network_disabled"] is True
    assert attestation["status"] == "BLOCKED"
    assert result["promotion_eligible"] is False


def test_probe_not_isolated_when_profile_allows_writes_by_default(
    tmp_path: Path, monkeypatch: Any
) -> None:
    def allow_default_profile(workspace_dir: Path, tmp_dir: Path) -> str:
        return f'(version 1)\n(allow default)\n(deny network*)\n(allow file-write* (subpath "{workspace_dir}"))\n'

    monkeypatch.setattr(
        "nexus.learning.zero_trust_v2_physical_sandbox._macos_sandbox_profile",
        allow_default_profile,
    )
    result = run_macos_sandbox_probe(
        ["/bin/echo", "ok"],
        signing_secret="test-secret",
        sandbox_exec_path="/usr/bin/sandbox-exec",
        subprocess_run=_completed,
        base_tmp_dir=tmp_path,
        env_source={"PATH": "/usr/bin:/bin"},
    )
    attestation = result["sandbox_attestation"]
    assert attestation["workspace_isolated"] is False
    assert attestation["tmp_isolated"] is False
    assert attestation["workspace_isolation_reason"] == "profile_write_scope_unconfined"
    assert attestation["raw_observation"]["write_scope_confined"] is False
    assert result["promotion_eligible"] is False
    assert result["status"] == "BLOCKED"


def test_profile_write_scope_check_rejects_widened_profiles(tmp_path: Path) -> None:
    workspace, tmp = tmp_path / "workspace", tmp_path / "tmp"
    good = _macos_sandbox_profile(workspace, tmp)
    assert _profile_confines_writes(good, workspace_dir=workspace, tmp_dir=tmp) is True
    widened = {
        "allow_default_after_deny": good + "(allow default)\n",
        "extra_write_rule": good + '(allow file-write* (subpath "/"))\n',
        "write_in_read_rule": good + '(allow file-read* file-write* (subpath "/"))\n',
        "no_deny": good.replace("(deny file-write*)\n", ""),
        "write_rule_before_deny": good.replace(
            "(deny network*)\n", '(deny network*)\n(allow file-write* (subpath "/"))\n'
        ),
    }
    for name, profile in widened.items():
        assert _profile_confines_writes(profile, workspace_dir=workspace, tmp_dir=tmp) is False, (
            name
        )
    assert _profile_confines_writes(good, workspace_dir=tmp_path / "other", tmp_dir=tmp) is False


if os.environ.get("NEXUS_RUN_REAL_SANDBOX_EXEC") == "1":
    # Opt-in only (CI is Linux and has no sandbox-exec, #2190): runs the real profile.

    def _real_sandbox_exec() -> str:
        path = shutil.which("sandbox-exec")
        if not path:
            pytest.fail("NEXUS_RUN_REAL_SANDBOX_EXEC=1 but sandbox-exec is not on PATH")
        return path

    def test_real_sandbox_profile_refuses_write_outside_workspace(tmp_path: Path) -> None:
        base = tmp_path / "base"
        base.mkdir()
        outside = tmp_path / "outside.txt"
        result = run_macos_sandbox_probe(
            ["/bin/sh", "-c", 'echo escaped > "$0"', str(outside)],
            signing_secret="test-secret",
            sandbox_exec_path=_real_sandbox_exec(),
            base_tmp_dir=base,
            env_source={"PATH": "/usr/bin:/bin"},
        )
        assert not outside.exists()
        assert result["sandbox_attestation"]["raw_observation"]["returncode"] != 0
        assert result["status"] == "BLOCKED"

    def test_real_sandbox_profile_allows_workspace_tmp_and_dev_null_writes(tmp_path: Path) -> None:
        script = 'echo in > inside.txt && echo t > "$TMPDIR/t.txt" && echo n > /dev/null && cat inside.txt'
        result = run_macos_sandbox_probe(
            ["/bin/sh", "-c", script],
            signing_secret="test-secret",
            sandbox_exec_path=_real_sandbox_exec(),
            base_tmp_dir=tmp_path,
            env_source={"PATH": "/usr/bin:/bin"},
        )
        attestation = result["sandbox_attestation"]
        assert attestation["raw_observation"]["returncode"] == 0
        assert result["status"] == "PASS"
        assert result["promotion_eligible"] is True
        assert validate_sandbox_attestation(attestation)["status"] == "PASS"

    def test_real_sandbox_profile_parse_failure_is_not_isolated(
        tmp_path: Path, monkeypatch: Any
    ) -> None:
        monkeypatch.setattr(
            "nexus.learning.zero_trust_v2_physical_sandbox._macos_sandbox_profile",
            lambda _workspace, _tmp: "(version 1)\n(allow default\n",
        )
        result = run_macos_sandbox_probe(
            ["/bin/echo", "ok"],
            signing_secret="test-secret",
            sandbox_exec_path=_real_sandbox_exec(),
            base_tmp_dir=tmp_path,
            env_source={"PATH": "/usr/bin:/bin"},
        )
        _assert_not_isolated(result, "sandbox_launch_failed")


# #3229: the attestation names only limits the runner enforces, and its signature is checked
# when the validator knows the secret.


def _probe_attestation(tmp_path: Path) -> dict[str, Any]:
    return run_macos_sandbox_probe(
        ["/bin/echo", "ok"],
        signing_secret="test-secret",
        sandbox_exec_path="/usr/bin/sandbox-exec",
        subprocess_run=_completed,
        base_tmp_dir=tmp_path,
        env_source={"PATH": "/usr/bin:/bin"},
    )["sandbox_attestation"]


def test_probe_does_not_report_a_memory_limit_it_does_not_enforce(tmp_path: Path) -> None:
    limits = _probe_attestation(tmp_path)["resource_limits"]
    assert limits["memory_mb"] is None
    assert limits["memory_enforced"] is False
    assert limits["memory_mb_requested"] == 512
    assert limits["cpu"] == "process_timeout" and limits["timeout_sec"] == 3


def test_attestation_signature_is_verified_when_the_secret_is_known(tmp_path: Path) -> None:
    attestation = _probe_attestation(tmp_path)
    assert validate_sandbox_attestation(attestation, signing_secret="test-secret")["reasons"] == []
    tampered = {**attestation, "artifact_hash": "another-artifact"}
    assert (
        "invalid_sandbox_signature"
        in validate_sandbox_attestation(tampered, signing_secret="test-secret")["reasons"]
    )
    assert (
        "invalid_sandbox_signature"
        in validate_sandbox_attestation(attestation, signing_secret="other-secret")["reasons"]
    )
    # Without the secret the field checks stand alone, as before.
    assert validate_sandbox_attestation(tampered)["reasons"] == []


def _shadow_sandbox_exec(directory: Path) -> Path:
    shadow = directory / "sandbox-exec"
    shadow.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
    shadow.chmod(0o755)
    return shadow


def test_probe_default_lookup_ignores_observer_path_3240(tmp_path: Path, monkeypatch: Any) -> None:
    shadow_dir = tmp_path / "shadow"
    shadow_dir.mkdir()
    shadow = _shadow_sandbox_exec(shadow_dir)
    monkeypatch.setenv("PATH", f"{shadow_dir}:/usr/bin:/bin")
    seen: list[list[str]] = []

    def record(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        seen.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    result = run_macos_sandbox_probe(
        ["/bin/echo", "ok"],
        signing_secret="test-secret",
        subprocess_run=record,
        base_tmp_dir=tmp_path,
        env_source={"PATH": "/usr/bin:/bin"},
    )
    assert all(str(shadow) not in cmd for cmd in seen)
    observed = result["sandbox_attestation"]["raw_observation"]["sandbox_exec_path"]
    assert observed in (None, "/usr/bin/sandbox-exec")


def test_probe_shadowed_sandbox_exec_path_is_not_isolated_3240(tmp_path: Path) -> None:
    shadow = _shadow_sandbox_exec(tmp_path)
    result = run_macos_sandbox_probe(
        ["/bin/echo", "ok"],
        signing_secret="test-secret",
        sandbox_exec_path=str(shadow),
        subprocess_run=_completed,
        base_tmp_dir=tmp_path,
        env_source={"PATH": "/usr/bin:/bin"},
    )
    attestation = result["sandbox_attestation"]
    assert attestation["workspace_isolated"] is False
    assert attestation["workspace_isolation_reason"] == "sandbox_exec_path_unexpected"
    assert attestation["raw_observation"]["sandbox_exec_path"] == str(shadow)
    assert result["promotion_eligible"] is False
