from __future__ import annotations
from pathlib import Path

import subprocess

from nexus.delivery.contract import contract_for_level
from nexus.delivery.models import CompletionRequest
from nexus.delivery.models import CompletionResult
from nexus.delivery.models import CompletionStatus
from nexus.delivery.models import TaskLevel
from nexus.delivery.models import VerificationRecord


def _run_verification_command(command: str, cwd: Path) -> VerificationRecord:
    completed = subprocess.run(
        command,
        shell=True,
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    return VerificationRecord(
        command=command,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        passed=completed.returncode == 0,
    )


def evaluate_completion(request: CompletionRequest) -> CompletionResult:
    from scripts.ops.content_quality_gate import check_content_quality
    contract = contract_for_level(request.task_level)
    records = [
        _run_verification_command(command, request.cwd)
        for command in request.verification_commands
    ]
    existing_artifacts = [path for path in request.artifact_paths if path.exists()]
    missing_artifacts = [path for path in request.artifact_paths if not path.exists()]
    
    # R1.1 Content Quality Hook
    quality_failures = []
    for art in existing_artifacts:
        if art.suffix == ".md":
            ok, reason = check_content_quality(art, min_words=50, min_paragraphs=2, blacklist=["高品質重鑄執行中"])
            if not ok:
                quality_failures.append(f"{art.name}: {reason}")

    passed_commands = sum(1 for record in records if record.passed)
    all_commands_passed = bool(records) and passed_commands == len(records)
    meets_command_floor = len(records) >= contract.min_verification_commands
    meets_artifact_floor = len(existing_artifacts) >= contract.required_artifacts
    has_substance = len(quality_failures) == 0

    if not records or passed_commands == 0:
        status = CompletionStatus.IMPLEMENTED
    elif not meets_command_floor or not all_commands_passed or not has_substance:
        status = CompletionStatus.PARTIALLY_VERIFIED
    elif request.task_level == TaskLevel.DELIVERY and meets_artifact_floor:
        status = CompletionStatus.DELIVERY_READY
    else:
        status = CompletionStatus.VERIFIED

    gate_passed = status in {
        CompletionStatus.VERIFIED,
        CompletionStatus.DELIVERY_READY,
    }
    if request.task_level == TaskLevel.DELIVERY:
        gate_passed = status == CompletionStatus.DELIVERY_READY

    summary = (
        f"{request.task_name}: {status.value} "
        f"({passed_commands}/{len(records)} verification commands passed)"
    )

    return CompletionResult(
        task_name=request.task_name,
        task_level=request.task_level,
        status=status,
        gate_passed=gate_passed,
        summary=summary,
        verification_records=records,
        existing_artifacts=existing_artifacts,
        missing_artifacts=missing_artifacts,
    )
