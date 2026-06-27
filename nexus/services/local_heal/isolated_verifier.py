from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Any


@dataclass(frozen=True)
class IsolatedVerifierRequest:
    task_id: str
    workspace_path: str
    verifier_command: tuple[str, ...]
    timeout_sec: float = 30.0
    verifier_allowed: bool = False


@dataclass(frozen=True)
class IsolatedVerifierReceipt:
    task_id: str
    verifier_status: str
    exit_code: int | None
    stdout_tail: str
    stderr_tail: str
    verifier_error: str
    verifier_allowed: bool
    public_claim_allowed: bool = False
    production_ready: bool = False


def run_isolated_verifier(request: IsolatedVerifierRequest) -> IsolatedVerifierReceipt:
    if not request.verifier_allowed:
        return IsolatedVerifierReceipt(
            task_id=request.task_id,
            verifier_status="blocked",
            exit_code=None,
            stdout_tail="",
            stderr_tail="",
            verifier_error="verifier_not_allowed",
            verifier_allowed=False,
        )
        
    if not isinstance(request.verifier_command, tuple):
        return IsolatedVerifierReceipt(
            task_id=request.task_id,
            verifier_status="blocked",
            exit_code=None,
            stdout_tail="",
            stderr_tail="",
            verifier_error="verifier_command_must_be_tuple",
            verifier_allowed=True,
        )
        
    if not request.verifier_command:
        return IsolatedVerifierReceipt(
            task_id=request.task_id,
            verifier_status="blocked",
            exit_code=None,
            stdout_tail="",
            stderr_tail="",
            verifier_error="verifier_command_empty",
            verifier_allowed=True,
        )
        
    try:
        res = subprocess.run(
            request.verifier_command,
            cwd=request.workspace_path,
            shell=False,
            capture_output=True,
            timeout=request.timeout_sec,
        )
        
        stdout_str = res.stdout.decode("utf-8", errors="replace")[-1000:]
        stderr_str = res.stderr.decode("utf-8", errors="replace")[-1000:]
        
        status = "pass" if res.returncode == 0 else "fail"
        
        return IsolatedVerifierReceipt(
            task_id=request.task_id,
            verifier_status=status,
            exit_code=res.returncode,
            stdout_tail=stdout_str,
            stderr_tail=stderr_str,
            verifier_error="",
            verifier_allowed=True,
        )
    except subprocess.TimeoutExpired as e:
        stdout_str = (e.stdout or b"").decode("utf-8", errors="replace")[-1000:]
        stderr_str = (e.stderr or b"").decode("utf-8", errors="replace")[-1000:]
        return IsolatedVerifierReceipt(
            task_id=request.task_id,
            verifier_status="blocked",
            exit_code=None,
            stdout_tail=stdout_str,
            stderr_tail=stderr_str,
            verifier_error=f"verifier_timeout: execution exceeded {request.timeout_sec} seconds",
            verifier_allowed=True,
        )
    except Exception as e:
        return IsolatedVerifierReceipt(
            task_id=request.task_id,
            verifier_status="blocked",
            exit_code=None,
            stdout_tail="",
            stderr_tail="",
            verifier_error=f"verifier_internal_error: {str(e)}",
            verifier_allowed=True,
        )
