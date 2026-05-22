from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from nexus.learning.zero_trust_v2_physical_sandbox import run_macos_sandbox_probe
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
