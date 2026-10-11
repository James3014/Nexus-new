"""Repro: for any non-TRACKED_TASK_CARD submission (contract_kind NONE / OWNER_INLINE) the
self-hosted service selects a model worker WITHOUT Workforce Admission or a Planner envelope:
  - validate_workforce_dispatch_binding(request) returns None (no error) when admission is absent,
  - build_contract() picks the worker itself ('codex' default / worker_order[0] for 'auto'),
  - the pre-provider boundary (_revalidate_provider_boundary) passes with binding=None.
WORKFORCE_EXECUTION_OVERLAY.md: "Nexus runtime model execution always requires fresh Nexus
Workforce Admission." AGENTS.md: CapabilityPlanner is sole route/capability authority.
"""
import sys, tempfile, pathlib, subprocess
sys.path.insert(0, "/home/user/Nexus-new")
from nexus.orchestrator.self_hosted_task_service import (
    SelfHostedTaskService, validate_workforce_dispatch_binding)

tmp = pathlib.Path(tempfile.mkdtemp())
ctrl = tmp / "ctrl"; ctrl.mkdir()
subprocess.run(["git", "init", "-q"], cwd=ctrl, check=True)
svc = SelfHostedTaskService(state_dir=tmp / "state", auto_reconcile=False)
req = {"task_id": "t-noadmit", "what": "w", "why": "y", "allowed_files": ["src/"],
       "verifier_commands": ["python3 -c pass"], "worker": "auto",
       "worker_order": ["gemini", "codex"], "controller_repo_root": str(ctrl),
       "controller_revision": "a" * 40, "target_base_revision": "a" * 40}
print("validate_workforce_dispatch_binding ->", validate_workforce_dispatch_binding(req))
c = svc.build_contract(req)
print("contract.preferred_provider (chosen without Planner/Admission):", c.preferred_provider,
      "provider_order:", c.provider_order)
svc._write_state("t-noadmit", {"task_id": "t-noadmit", "status": "RUNNING", "contract_kind": "NONE"})
svc._revalidate_provider_boundary(c, req, "t-noadmit", None, active_provider=c.preferred_provider)
print("_revalidate_provider_boundary(binding=None, untracked): PASSED (no exception)")
try:
    svc._revalidate_provider_boundary(c, {**req, "contract_kind": "TRACKED_TASK_CARD"}, "t-noadmit", None)
except RuntimeError as e:
    print("contrast tracked:", e)
