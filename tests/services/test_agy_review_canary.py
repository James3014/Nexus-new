"""CLI and installer tests for the RDC/Agy reviewer canary harness."""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANARY_PATH = ROOT / "scripts" / "ops" / "nexus-agy-review-canary"
INSTALLER_PATH = ROOT / "scripts" / "ops" / "install_nexus_agy_review_canary.sh"

os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
canary_cli = SourceFileLoader(
    "nexus_agy_review_canary_cli",
    str(CANARY_PATH),
).load_module()

EFFECT = "a" * 64
OPERATION_ID = "agyop_" + ("a" * 32)
RUNTIME = "b" * 40


def _fake_review_file(tmp_path: Path) -> Path:
    path = tmp_path / "nexus-agy-review"
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _start_args(tmp_path: Path) -> argparse.Namespace:
    contract = tmp_path / "contract.md"
    contract.write_text("canary contract\n", encoding="utf-8")
    return argparse.Namespace(
        cwd=str(tmp_path),
        repository="James3014/Nexus-new",
        base_revision="1" * 40,
        contract_file=str(contract),
        model="claude-sonnet-4-6",
        effort=None,
        packet_mode="full",
        compact_max_bytes=1_000_000,
        verification_receipt_file=[],
        authority_excerpt_file=[],
        timeout=60,
        operation_root=str(tmp_path / "operations-root"),
        lease_root=str(tmp_path / "leases"),
        expected_runtime_revision=RUNTIME,
        canary_root=str(tmp_path / "canaries"),
    )


def _terminal_status(operation_root: Path) -> dict:
    operation = {
        "operation_id": OPERATION_ID,
        "attempt_id": "attempt_" + ("d" * 32),
        "status": "COMPLETED",
        "review_effect_id": EFFECT,
        "runtime_revision": RUNTIME,
        "provider_session_id": "session-1",
        "account_alias_hash": "accthash",
        "lease_id_hash": "leasehash",
    }
    path = operation_root / "operations" / OPERATION_ID / "operation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    path.write_text(json.dumps(operation) + "\n", encoding="utf-8")
    return {
        "action": "STATUS",
        "operation": operation,
        "receipt": {
            "review_effect_id": EFFECT,
            "review_applicable": True,
            "subject_stable": True,
            "receipt_sha256": "e" * 64,
            "verdict": "ACCEPT",
        },
    }


def test_start_then_resume_uses_status_without_redispatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    review_file = _fake_review_file(tmp_path)
    args = _start_args(tmp_path)
    calls: list[list[str]] = []

    def fake_run_review(argv: list[str]) -> dict:
        calls.append(list(argv))
        if "--status" in argv:
            return _terminal_status(Path(args.operation_root))
        return {
            "action": "DISPATCHED",
            "operation": {
                "operation_id": OPERATION_ID,
                "attempt_id": "attempt_" + ("d" * 32),
                "pid": 4242,
                "model": "claude-sonnet-4-6",
                "review_effect_id": EFFECT,
                "review_launch_profile_id": "claude-sonnet-4-6.packet-review.v1",
            },
        }

    monkeypatch.setattr(canary_cli, "_review_path", lambda: review_file)
    monkeypatch.setattr(canary_cli, "_run_review", fake_run_review)

    started = canary_cli.start(args)
    canary_id = started["canary"]["canary_id"]
    resumed = canary_cli.resume(
        argparse.Namespace(
            canary_id=canary_id,
            canary_root=args.canary_root,
        )
    )

    assert started["action"] == "INTERRUPT_NOW"
    assert resumed["action"] == "PASSED"
    assert len(calls) == 2
    assert "--status" in calls[1]
    assert "--repository" not in calls[1]
    assert "--model" not in calls[1]


def test_resume_outcome_unknown_reconciles_same_operation_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    review_file = _fake_review_file(tmp_path)
    args = _start_args(tmp_path)
    calls: list[list[str]] = []

    def fake_run_review(argv: list[str]) -> dict:
        calls.append(list(argv))
        if "--status" in argv or "--reconcile" in argv:
            return {
                "action": "STATUS",
                "operation": {
                    "operation_id": OPERATION_ID,
                    "review_effect_id": EFFECT,
                    "status": "OUTCOME_UNKNOWN",
                },
                "receipt": None,
            }
        return {
            "action": "DISPATCHED",
            "operation": {
                "operation_id": OPERATION_ID,
                "attempt_id": "attempt_" + ("d" * 32),
                "pid": 4242,
                "model": "claude-sonnet-4-6",
                "review_effect_id": EFFECT,
                "review_launch_profile_id": "claude-sonnet-4-6.packet-review.v1",
            },
        }

    monkeypatch.setattr(canary_cli, "_review_path", lambda: review_file)
    monkeypatch.setattr(canary_cli, "_run_review", fake_run_review)

    started = canary_cli.start(args)
    resumed = canary_cli.resume(
        argparse.Namespace(
            canary_id=started["canary"]["canary_id"],
            canary_root=args.canary_root,
        )
    )

    assert resumed["action"] == "RECONCILE"
    assert len(calls) == 3
    assert "--status" in calls[1]
    assert "--reconcile" in calls[2]
    assert OPERATION_ID in calls[1]
    assert OPERATION_ID in calls[2]


def test_installer_deploys_exact_canary_entrypoint(tmp_path: Path) -> None:
    target = tmp_path / "nexus-agy-review-canary"
    env = os.environ.copy()
    env.update({
        "NEXUS_AGY_REPO_ROOT": str(ROOT),
        "NEXUS_AGY_SNAPSHOT": str(ROOT),
        "NEXUS_AGY_REVIEW_CANARY_TARGET": str(target),
    })

    proc = subprocess.run(
        ["bash", str(INSTALLER_PATH)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert target.read_bytes() == CANARY_PATH.read_bytes()
    mode = target.stat().st_mode
    assert mode & stat.S_IXUSR
    assert mode & stat.S_IXGRP
    assert mode & stat.S_IXOTH
