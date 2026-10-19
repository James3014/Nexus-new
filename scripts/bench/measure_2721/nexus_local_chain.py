"""Run one materialized task through the real P1 chain locally, zero-model.

Used only by the symmetry dry run.  In a fresh interpreter (module globals
are patched, as in the Nexus live-path test drivers) it:

1. makes a fresh Controller: a base-only copy of the task checkout plus one
   Task Card commit under ``tasks/`` (standing in for ``external_target``,
   which is not merged yet), with the task venv linked as ``../venv``;
2. calls the real Gateway ``nexus_worker_candidate`` (real planner, real
   measurement workforce policy and preflight);
3. runs the real ``SelfHostedTaskService`` inline with
   ``WorkerRegistry.default()``, i.e. the real ``ClaudeMeasurementWorkerAdapter``
   on whatever ``NEXUS_MEASUREMENT_CLAUDE_BIN`` names (a fake in dry runs).

Usage: ``python nexus_local_chain.py <spec.json>``; writes ``spec["out"]``.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def run(spec: dict[str, Any]) -> dict[str, Any]:
    import nexus.orchestrator.self_hosted_task_service as service_module
    import nexus.orchestrator.unified_mcp_gateway as gateway_module
    from nexus.orchestrator.ambient_core import LazyCanonicalCoreControlPort
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
    from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway
    from scripts.bench.measure_2721.common import git
    from scripts.bench.measure_2721.materialize import checkout_base, link_venv

    task = spec["task"]
    gw_task = spec["gateway_task_id"]
    root = Path(spec["work"]).resolve()
    ctl = root / "ctl" / "base"
    checkout_base(Path(task["base_checkout"]), task["base_commit"], ctl)
    link_venv(task, ctl)
    card_rel = f"tasks/measure-2721-dryrun/{gw_task}.md"
    (ctl / card_rel).parent.mkdir(parents=True)
    (ctl / card_rel).write_text(f"# Task Card: {gw_task}\n\ntask_id: `{gw_task}`\nAUTO_CHAIN: false\n",
                                encoding="utf-8")
    git(ctl, "add", card_rel)
    git(ctl, "commit", "-qm", "dry-run card")
    head = git(ctl, "rev-parse", "HEAD").strip()
    # Same namespace the Gateway derives from its source root (ctl.parent).
    os.environ["NEXUS_TARGET_ROOT_OVERRIDE"] = str(ctl.parent / "nexus-runtime-targets")
    service_module.CANONICAL_SOURCE_ROOT = ctl
    gateway_module.CANONICAL_SOURCE_ROOT = ctl
    gateway_module._git = lambda *args, **kwargs: head
    original_guard = gateway_module.pre_action_guard
    gateway_module.pre_action_guard = lambda action, **kwargs: original_guard(action, canonical_root=ctl, **kwargs)

    class Recording(SelfHostedTaskService):
        def submit_task(self, request):  # type: ignore[override]
            self.submitted = [json.loads(json.dumps(request))]
            return {"status": "RECORDED"}

    text = task["text"]
    arguments = {
        "task_id": gw_task, "what": text["what"], "why": text["why"],
        "allowed_files": list(text["allowed_files"]), "verifier_commands": list(text["verifier_commands"]),
        "owner_confirmation": True, "task_card_path": card_rel,
        "task_card_hash": hashlib.sha256((ctl / card_rel).read_bytes()).hexdigest(),
    }
    recorder = Recording(state_dir=root / "gateway-state", auto_reconcile=False, ephemeral=True)
    response = UnifiedMCPGateway(service=recorder).handle({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "nexus_worker_candidate", "arguments": arguments},
    })
    out: dict[str, Any] = {"gateway_is_error": bool(response["result"]["isError"]), "worker_args": arguments}
    if out["gateway_is_error"]:
        out["gateway_error"] = response["result"]["structuredContent"]
        return out
    request = recorder.submitted[0]
    out.update(provider=request.get("provider"), model=request.get("model"), worker_id=request.get("worker_id"))
    state_dir = root / "state"
    service = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True,
                                    ambient_core_port=LazyCanonicalCoreControlPort(state_dir))

    def launch_inline(task_id_arg, attempt_id):
        service._run_owned_task(task_id_arg, attempt_id)
        return service._read_state(task_id_arg)

    service._launch_worker = launch_inline  # type: ignore[method-assign]
    try:
        out["submit_status"] = service.submit_task(request).get("status")
    except Exception as exc:
        out["submit_error"] = f"{type(exc).__name__}: {exc}"
    state = service._read_state(gw_task) or {}
    out.update(status=state.get("status"), error=state.get("error"),
               selected_provider=state.get("selected_provider"), selected_model=state.get("selected_model"),
               executions=[e.get("provider") for e in state.get("executions") or [] if isinstance(e, dict)],
               base_prompt=SelfHostedTaskService._prompt(service._contract_from_state(state))
               if state.get("contract") else None)
    return out


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
