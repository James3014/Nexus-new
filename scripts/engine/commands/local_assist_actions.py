from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shlex
from typing import Any

from nexus.services.local_assist_closeout import run_local_assist_closeout
from nexus.services.local_assist_service import LocalAssistRequest, LocalAssistService
from nexus.services.local_assist_user_relay import write_user_relay_report


def run_local_assist_command(
    *,
    action: str,
    task_file: str | Path,
    workspace: str | Path,
    report_file: str | Path | None = None,
    target_file: str | None = None,
    allowed_files: tuple[str, ...] = (),
    verifier_command: str | None = None,
) -> tuple[dict[str, Any], int]:
    payload = json.loads(Path(task_file).read_text(encoding="utf-8"))
    request = LocalAssistRequest.from_dict(payload)
    command = request.verifier_command
    if verifier_command is not None:
        command = tuple(shlex.split(verifier_command))
    request = replace(
        request,
        action=action,
        workspace_root=str(Path(workspace).expanduser()),
        target_file=target_file if target_file is not None else request.target_file,
        allowed_files=allowed_files or request.allowed_files,
        verifier_command=command,
        requested_role="advisor" if action == "advisor" else "candidate",
    )
    response = LocalAssistService().handle(request, report_file=report_file)
    result = response.to_dict()
    receipt = json.loads(Path(response.receipt_path).read_text(encoding="utf-8"))
    result["receipt_complete"] = bool(receipt.get("receipt_complete", False))
    result["report_file"] = str(report_file) if report_file else ""
    return result, 0 if response.status == "SUCCEEDED" and result["receipt_complete"] else 1


def run_local_assist_closeout_command(
    *,
    closeout_file: str | Path,
    workspace: str | Path,
    report_file: str | Path | None = None,
) -> tuple[dict[str, Any], int]:
    result = run_local_assist_closeout(
        closeout_file=closeout_file,
        repo_root=workspace,
        report_file=report_file,
    )
    return result.report, result.exit_code


def run_local_assist_user_relay_command(
    *,
    package_file: str | Path,
    workspace: str | Path,
    response_file: str | Path | None,
    report_file: str | Path,
) -> tuple[dict[str, Any], int]:
    report = write_user_relay_report(
        package_file=package_file,
        repo_root=workspace,
        response_file=response_file,
        report_file=report_file,
    )
    return report, 0 if report.get("status") != "REJECTED" else 1
