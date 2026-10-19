"""Subprocess driver: the #2721 Claude measurement worker on the real P1 chain.

hashed task card -> Gateway ``nexus_worker_candidate`` (real planner, real
measurement workforce policy, real measurement preflight) -> exact submitted
request -> real ``SelfHostedTaskService`` with ``WorkerRegistry.default()`` ->
``ClaudeMeasurementWorkerAdapter`` -> a fake ``claude`` executable that edits
one file and prints stream-json -> CandidateVerifier -> durable state.

Only the provider binary is fake.  It runs in a fresh interpreter because the
Gateway and service modules are patched at module level (as in the #2181
live driver).  Usage: ``python <driver> <spec.json>``.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

import nexus.orchestrator.self_hosted_task_service as service_module  # noqa: E402
import nexus.orchestrator.unified_mcp_gateway as gateway_module  # noqa: E402
from nexus.orchestrator.ambient_core import LazyCanonicalCoreControlPort  # noqa: E402
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService  # noqa: E402
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway  # noqa: E402

_ORIGINAL_GUARD = gateway_module.pre_action_guard


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


class _RecordingService(SelfHostedTaskService):
    def submit_task(self, request):  # type: ignore[override]
        self.submitted = [*getattr(self, "submitted", []), json.loads(json.dumps(request))]
        return {"status": "RECORDED", "task_id": request["task_id"]}


def run(spec: dict[str, Any]) -> dict[str, Any]:
    if not spec.get("use_seatbelt", True):
        # Hosts without macOS Seatbelt (Linux CI) run the same chain unsandboxed.
        import nexus.executors.claude_measurement_worker as cmw

        cmw._USE_SEATBELT = False
    root = Path(spec["work"]).resolve()
    task_id = spec["task_id"]
    ctl = root / "ctl"
    ctl.mkdir(parents=True)
    _git(ctl, "init", "-q")
    _git(ctl, "config", "user.name", "Measurement Witness")
    _git(ctl, "config", "user.email", "measure@example.com")
    (ctl / "README.md").write_text("# Repo\n", encoding="utf-8")
    (ctl / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    card_rel = f"tasks/test/{task_id}.md"
    (ctl / card_rel).parent.mkdir(parents=True)
    (ctl / card_rel).write_text(
        f"# Task Card: {task_id}\n\ntask_id: `{task_id}`\nAUTO_CHAIN: false\n", encoding="utf-8"
    )
    _git(ctl, "add", "-A")
    _git(ctl, "commit", "-qm", "seed")
    head = _git(ctl, "rev-parse", "HEAD")
    os.environ["NEXUS_TARGET_ROOT_OVERRIDE"] = str(ctl.parent / "nexus-runtime-targets")
    service_module.CANONICAL_SOURCE_ROOT = ctl
    gateway_module.CANONICAL_SOURCE_ROOT = ctl
    gateway_module._git = lambda *args, **kwargs: head
    gateway_module.pre_action_guard = lambda action, **kwargs: _ORIGINAL_GUARD(
        action, canonical_root=ctl, **kwargs
    )
    arguments = {
        "task_id": task_id,
        "what": "Append the line 'bounded change' to README.md.",
        "why": "Measurement worker witness.",
        "allowed_files": ["README.md"],
        "verifier_commands": ["git diff --check"],
        "owner_confirmation": True,
        "task_card_path": card_rel,
        "task_card_hash": hashlib.sha256((ctl / card_rel).read_bytes()).hexdigest(),
    }
    recorder = _RecordingService(
        state_dir=root / "gateway-state", auto_reconcile=False, ephemeral=True
    )
    response = UnifiedMCPGateway(service=recorder).handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "nexus_worker_candidate", "arguments": arguments},
    })
    assert response is not None
    result: dict[str, Any] = {"gateway_is_error": bool(response["result"]["isError"])}
    if result["gateway_is_error"]:
        result["gateway_error"] = response["result"]["structuredContent"]
        return result
    request = recorder.submitted[0]
    result.update(
        request_provider=request.get("provider"),
        request_model=request.get("model"),
        request_worker_id=request.get("worker_id"),
        request_worker_order=request.get("worker_order"),
    )
    state_dir = root / "state"
    service = SelfHostedTaskService(
        state_dir=state_dir,
        auto_reconcile=False,
        ephemeral=True,
        ambient_core_port=LazyCanonicalCoreControlPort(state_dir),
    )

    def launch_inline(task_id_arg, attempt_id):
        service._run_owned_task(task_id_arg, attempt_id)
        return service._read_state(task_id_arg)

    service._launch_worker = launch_inline  # type: ignore[method-assign]
    try:
        result["submit_status"] = service.submit_task(request).get("status")
    except Exception as exc:
        result["submit_error"] = f"{type(exc).__name__}: {exc}"
    state = service._read_state(task_id) or {}
    receipt = state.get("verified_receipt") or {}
    executions = state.get("executions") or []
    result.update(
        status=state.get("status"),
        error=state.get("error"),
        selected_provider=state.get("selected_provider"),
        selected_model=state.get("selected_model"),
        candidate_commit_sha=state.get("candidate_commit_sha"),
        target_initial_revision=state.get("target_initial_revision"),
        receipt_verified=receipt.get("verified"),
        receipt_failure_reasons=receipt.get("failure_reasons"),
        execution_providers=[item.get("provider") for item in executions if isinstance(item, dict)],
        base_prompt=SelfHostedTaskService._prompt(service._contract_from_state(state))
        if state.get("contract")
        else None,
    )
    target = Path(str(state.get("target_worktree") or ""))
    if result["target_initial_revision"] and target.is_dir():
        # Ephemeral (rehearsal) state never promotes a Candidate commit; the
        # verified Candidate is the target's working tree.
        result["candidate_diff"] = _git(target, "diff", result["target_initial_revision"])
    return result


def main() -> int:
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    try:
        out = run(spec)
    except Exception as exc:
        out = {"driver_error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()}
    Path(spec["out"]).write_text(json.dumps(out, default=str, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
